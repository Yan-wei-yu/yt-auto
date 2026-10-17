"""每段旁白的聲音：你的錄音 > edge-tts 預覽配音 > 靜音（只估長度）。"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .week import Segment, Week

AUDIO_EXTS = (".wav", ".mp3", ".m4a")


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


def _tts(text: str, out: Path, cfg: Config) -> bool:
    try:
        import edge_tts
    except ImportError:
        return False
    stamp = out.with_suffix(".txt")
    key = hashlib.sha1(f"{cfg.voice['tts_voice']}|{cfg.voice['tts_rate']}|{text}".encode()).hexdigest()
    if out.exists() and stamp.exists() and stamp.read_text() == key:
        return True
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(edge_tts.Communicate(text, cfg.voice["tts_voice"], rate=cfg.voice["tts_rate"]).save(str(out)))
    except Exception as exc:  # 沒網路或服務暫時無法使用時，退回靜音
        print(f"  ⚠ TTS 失敗（{type(exc).__name__}），改用靜音估長度")
        return False
    stamp.write_text(key)
    return True


def voice_for(week: Week, seg: Segment, cfg: Config, use_tts: bool = True) -> Voice:
    rec = recording(week, seg)
    if rec:
        return Voice(rec, "recording")
    if use_tts:
        out = cfg.path("build") / week.id / "voice" / f"{seg.id}.mp3"
        if _tts(seg.narration, out, cfg):
            return Voice(out, "tts")
    return Voice(None, "silent")
