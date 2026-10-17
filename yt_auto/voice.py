"""每段旁白的聲音：你的錄音 > AI 配音 > 靜音（只估長度）。

AI 配音照 config.yaml 的 voice.engines 順序嘗試：
- google：Google Cloud Text-to-Speech 的台灣華語（cmn-TW）聲音，需要 API 金鑰
- kokoro：離線執行（模型 Apache 2.0、可商用），大陸口音；先跑 `python -m yt_auto tts-setup` 下載模型
- edge：微軟 Edge 線上朗讀，商用條款不明確，只建議預覽
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import tarfile
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .week import Segment, Week

AUDIO_EXTS = (".wav", ".mp3", ".m4a")
KOKORO_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_1.tar.bz2"
GOOGLE_TTS = "https://texttospeech.googleapis.com/v1"

CJK = "\u4e00-\u9fff，。！？、；：「」（）"
_engines: dict[str, object] = {}


@dataclass
class Voice:
    path: Path | None
    source: str  # recording / tts / silent


def recording(week: Week, seg: Segment) -> Path | None:
    for ext in AUDIO_EXTS:
        p = week.dir / "voice" / f"{seg.id}{ext}"
        if p.exists():
            return p
    return None


def estimate_seconds(text: str, cfg: Config) -> float:
    return round(len(text) / cfg.voice["chars_per_second"] + 0.5, 2)


def speech_text(text: str, cfg: Config) -> str:
    """只給配音用的唸法替換（字幕不變），例如 S&P 500 → 標普五百。長的詞先換。"""
    for src, dst in sorted(cfg.voice.get("pronounce", {}).items(), key=lambda kv: -len(kv[0])):
        text = text.replace(src, dst)
    # 中文旁邊的空白會被模型當成未知符號唸出怪聲，拿掉；英文單字之間的空白保留
    return re.sub(rf"\s+(?=[{CJK}])|(?<=[{CJK}])\s+", "", text)


def kokoro_dir(cfg: Config) -> Path:
    return Path(cfg.voice["kokoro"]["model_dir"]).expanduser()


def setup_kokoro(cfg: Config) -> Path:
    folder = kokoro_dir(cfg)
    if (folder / "model.onnx").exists():
        return folder
    folder.parent.mkdir(parents=True, exist_ok=True)
    archive = folder.parent / "kokoro.tar.bz2"
    print(f"下載 Kokoro 配音模型（約 330 MB）→ {folder}")
    urllib.request.urlretrieve(KOKORO_URL, archive)
    with tarfile.open(archive) as tar:
        tar.extractall(folder.parent)
    archive.unlink()
    return folder


def _kokoro(cfg: Config):
    if "kokoro" not in _engines:
        import sherpa_onnx

        m = kokoro_dir(cfg)
        if not (m / "model.onnx").exists():
            raise FileNotFoundError("還沒下載配音模型，請先執行 python -m yt_auto tts-setup")
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=str(m / "model.onnx"), voices=str(m / "voices.bin"), tokens=str(m / "tokens.txt"),
                    data_dir=str(m / "espeak-ng-data"), dict_dir=str(m / "dict"),
                    lexicon=f"{m / 'lexicon-us-en.txt'},{m / 'lexicon-zh.txt'}"),
                num_threads=4),
            rule_fsts=f"{m / 'phone-zh.fst'},{m / 'date-zh.fst'},{m / 'number-zh.fst'}",
            max_num_sentences=1)
        _engines["kokoro"] = sherpa_onnx.OfflineTts(config)
    return _engines["kokoro"]


def _synth_kokoro(text: str, out: Path, cfg: Config) -> None:
    import numpy as np

    k = cfg.voice["kokoro"]
    audio = _kokoro(cfg).generate(text, sid=int(k["speaker"]), speed=float(k["speed"]))
    pcm = (np.clip(np.asarray(audio.samples), -1, 1) * 32767).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.sample_rate)
        w.writeframes(pcm.tobytes())


def _synth_edge(text: str, out: Path, cfg: Config) -> None:
    import edge_tts

    asyncio.run(edge_tts.Communicate(text, cfg.voice["tts_voice"], rate=cfg.voice["tts_rate"]).save(str(out)))


def google_key(cfg: Config) -> str | None:
    """API 金鑰：環境變數 GOOGLE_TTS_API_KEY，或 .secrets/google_tts_key.txt（不進 git）。"""
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    f = cfg.path("secrets") / "google_tts_key.txt"
    if not key and f.exists():
        key = f.read_text(encoding="utf-8").strip()
    return key or None


def _google(path: str, cfg: Config, body: dict | None = None) -> dict:
    key = google_key(cfg)
    if not key:
        raise RuntimeError("沒有 Google TTS 金鑰（.secrets/google_tts_key.txt）")
    req = urllib.request.Request(f"{GOOGLE_TTS}/{path}{'&' if '?' in path else '?'}key={key}",
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = json.loads(exc.read() or b"{}").get("error", {}).get("message", "")
        raise RuntimeError(f"Google TTS {exc.code}: {detail}") from None


def google_voices(cfg: Config, language: str = "cmn-TW") -> list[dict]:
    return _google(f"voices?languageCode={language}", cfg).get("voices", [])


def _synth_google(text: str, out: Path, cfg: Config) -> None:
    g = cfg.voice["google"]
    body = {
        "input": {"text": text},
        "voice": {"languageCode": g.get("language", "cmn-TW"), "name": g["voice"]},
        "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000, "speakingRate": g.get("speed", 1.0)},
    }
    # LINEAR16 回傳的內容本身就是含檔頭的 WAV
    out.write_bytes(base64.b64decode(_google("text:synthesize", cfg, body)["audioContent"]))


SYNTH = {"google": _synth_google, "kokoro": _synth_kokoro, "edge": _synth_edge}


def _available(engine: str, cfg: Config) -> bool:
    if engine == "google":
        return google_key(cfg) is not None
    if engine == "kokoro":
        return (kokoro_dir(cfg) / "model.onnx").exists()
    return True


def _tts(text: str, out_base: Path, cfg: Config) -> Path | None:
    """依序試 voice.engines，第一個成功的就用；結果用文字＋設定的雜湊快取。"""
    engines = cfg.voice.get("engines") or [cfg.voice.get("engine", "kokoro")]
    for engine in engines:
        if not _available(engine, cfg):
            continue
        out = out_base.with_suffix(".mp3" if engine == "edge" else ".wav")
        settings = cfg.voice.get(engine, (cfg.voice.get("tts_voice"), cfg.voice.get("tts_rate")))
        stamp = out.with_suffix(".txt")
        key = hashlib.sha1(f"{engine}|{settings}|{text}".encode()).hexdigest()
        if out.exists() and stamp.exists() and stamp.read_text() == key:
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            SYNTH[engine](text, out, cfg)
        except Exception as exc:  # 沒裝套件、沒網路、金鑰錯誤時，換下一個引擎
            print(f"  ⚠ {engine} 配音失敗（{exc}），改用下一個")
            continue
        stamp.write_text(key)
        return out
    return None


def voice_for(week: Week, seg: Segment, cfg: Config, use_tts: bool = True) -> Voice:
    rec = recording(week, seg)
    if rec:
        return Voice(rec, "recording")
    if use_tts:
        out = _tts(speech_text(seg.narration, cfg), cfg.path("build") / week.id / "voice" / seg.id, cfg)
        if out:
            return Voice(out, "tts")
    return Voice(None, "silent")
