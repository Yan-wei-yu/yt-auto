from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .slides import render_segment
from .subtitles import build_ass, timed_cues
from .voice import Voice, estimate_seconds, voice_for
from .week import Segment, Week

AUDIO_FMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


@dataclass
class Part:
    seg: Segment
    slide: Path
    voice: Voice
    speech: float  # 旁白長度
    duration: float  # 旁白＋段落間停頓


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"找不到 {tool}，請先安裝 ffmpeg（Mac：brew install ffmpeg）")


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def plan_parts(week: Week, cfg: Config, portrait: bool, use_tts: bool, seg_ids: list[str] | None = None) -> list[Part]:
    kind = "short" if portrait else "long"
    segments = [week.segment(i) for i in seg_ids] if seg_ids else week.segments
    parts = []
    for seg in segments:
        slide = render_segment(seg, week, cfg, cfg.path("build") / week.id / "slides" / kind / f"{seg.id}.png", portrait)
        voice = voice_for(week, seg, cfg, use_tts)
        speech = probe_duration(voice.path) if voice.path else estimate_seconds(seg.narration, cfg)
        parts.append(Part(seg, slide, voice, speech, round(speech + cfg.video["segment_pad"], 3)))
    return parts


def _run(args: list[str], cwd: Path) -> None:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg 失敗：\n{proc.stderr[-3000:]}")


def assemble(parts: list[Part], out: Path, cfg: Config, portrait: bool, music: Path | None = None) -> list[tuple[str, float]]:
    """把投影片＋旁白接成影片，燒字幕、混配樂。回傳章節（標題, 開始秒數）。"""
    require_ffmpeg()
    v = cfg.video
    w, h = (v["short_width"], v["short_height"]) if portrait else (v["width"], v["height"])
    fps = v["fps"]
    out.parent.mkdir(parents=True, exist_ok=True)

    args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    filters, cues, chapters = [], [], []
    n, t = 0, 0.0
    for i, p in enumerate(parts):
        d = f"{p.duration:.3f}"
        args += ["-loop", "1", "-framerate", str(fps), "-t", d, "-i", str(p.slide.resolve())]
        vin, n = n, n + 1
        if p.voice.path:
            args += ["-i", str(p.voice.path.resolve())]
        else:
            args += ["-f", "lavfi", "-t", d, "-i", "anullsrc=r=48000:cl=stereo"]
        ain, n = n, n + 1
        if v["ken_burns"]:
            frames = int(p.duration * fps)
            zoom = f"zoompan=z='1+0.04*on/{max(frames, 1)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps},"
        else:
            zoom = ""
        filters.append(f"[{vin}:v]scale={w}:{h},{zoom}setsar=1,format=yuv420p[v{i}]")
        filters.append(f"[{ain}:a]{AUDIO_FMT},apad,atrim=duration={d},asetpts=PTS-STARTPTS[a{i}]")
        cues += timed_cues(p.seg.narration, t, p.speech, max_chars=14 if portrait else 22)
        if p.seg.chapter:
            chapters.append((p.seg.chapter, t))
        t += p.duration
    filters.append("".join(f"[v{i}][a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=1[vc][ac]")

    ass_name = out.with_suffix(".ass").name
    size = v["short_subtitle_size"] if portrait else v["subtitle_size"]
    margin = int(h * 0.40) if portrait else 46
    (out.parent / ass_name).write_text(build_ass(cues, w, h, v["subtitle_font"], size, margin), encoding="utf-8")
    # 在輸出資料夾執行 ffmpeg，字幕檔用相對路徑，避免各作業系統的路徑跳脫問題
    filters.append(f"[vc]subtitles={ass_name}[vout]")

    if music is not None:
        args += ["-stream_loop", "-1", "-i", str(music.resolve())]
        filters.append(f"[{n}:a]{AUDIO_FMT},atrim=duration={t:.3f},afade=t=out:st={max(t - 2, 0):.3f}:d=2,volume={v['music_volume']}[mus]")
        filters.append("[ac][mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        filters.append("[ac]anull[aout]")

    args += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out.name]
    _run(args, out.parent)
    return chapters
