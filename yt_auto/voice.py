"""每段旁白的聲音：你的錄音 > AI 配音 > 靜音（只估長度）。

AI 配音預設用 Kokoro（sherpa-onnx 離線執行，模型 Apache 2.0、可商用），
第一次使用先跑 `python -m yt_auto tts-setup` 下載模型。
"""
from __future__ import annotations

import asyncio
import hashlib
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


def _tts(text: str, out: Path, cfg: Config) -> bool:
    engine = cfg.voice.get("engine", "kokoro")
    settings = cfg.voice.get(engine, {}) if engine == "kokoro" else (cfg.voice["tts_voice"], cfg.voice["tts_rate"])
    stamp = out.with_suffix(".txt")
    key = hashlib.sha1(f"{engine}|{settings}|{text}".encode()).hexdigest()
    if out.exists() and stamp.exists() and stamp.read_text() == key:
        return True
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        (_synth_kokoro if engine == "kokoro" else _synth_edge)(text, out, cfg)
    except Exception as exc:  # 沒裝套件、沒模型、沒網路時，退回靜音
        print(f"  ⚠ 配音失敗（{type(exc).__name__}: {exc}），改用靜音估長度")
        return False
    stamp.write_text(key)
    return True


def voice_for(week: Week, seg: Segment, cfg: Config, use_tts: bool = True) -> Voice:
    rec = recording(week, seg)
    if rec:
        return Voice(rec, "recording")
    if use_tts:
        ext = ".wav" if cfg.voice.get("engine", "kokoro") == "kokoro" else ".mp3"
        out = cfg.path("build") / week.id / "voice" / f"{seg.id}{ext}"
        if _tts(speech_text(seg.narration, cfg), out, cfg):
            return Voice(out, "tts")
    return Voice(None, "silent")
