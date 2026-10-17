from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .episode import Episode, Shot
from .subtitles import Cue, build_ass

CLIP_EXTS = (".mp4", ".mov", ".webm", ".mkv")
AUDIO_FMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


@dataclass
class Probe:
    duration: float
    has_audio: bool
    width: int
    height: int


@dataclass
class Segment:
    shot: Shot
    clip: Path | None
    duration: float
    probe: Probe | None = None


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"找不到 {tool}，請先安裝 ffmpeg（Mac：brew install ffmpeg）")


def probe(path: Path) -> Probe:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    info = json.loads(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    return Probe(
        duration=float(info["format"]["duration"]),
        has_audio=any(s["codec_type"] == "audio" for s in info["streams"]),
        width=int(video["width"]),
        height=int(video["height"]),
    )


def find_clip(folder: Path, shot_id: str) -> Path | None:
    for ext in CLIP_EXTS:
        p = folder / f"{shot_id}{ext}"
        if p.exists():
            return p
    return None


def plan_segments(ep: Episode, cfg: Config, placeholder: bool) -> list[Segment]:
    folder = cfg.path("media") / ep.id
    segments, missing = [], []
    for shot in ep.shots:
        clip = find_clip(folder, shot.id)
        if clip is None:
            if not placeholder:
                missing.append(shot.id)
            segments.append(Segment(shot, None, shot.duration))
            continue
        pr = probe(clip)
        # 片段比腳本長就裁掉，比腳本短就用片段本身的長度
        segments.append(Segment(shot, clip, min(pr.duration, shot.duration), pr))
    if missing:
        raise SystemExit(
            f"{ep.id} 缺少片段：{', '.join(missing)}（放在 {folder}/<鏡頭id>.mp4），"
            "或加上 --placeholder 先輸出動態分鏡預覽"
        )
    return segments


def episode_cues(segments: list[Segment]) -> list[Cue]:
    cues, t = [], 0.0
    for seg in segments:
        s = seg.shot
        if seg.clip is None:
            cues.append(Cue(t, t + seg.duration, f"{s.id} · {s.beat} · {seg.duration:g}s（placeholder）", style="Label"))
            cues.append(Cue(t, t + seg.duration, s.action, style="Action"))
        if s.caption:
            cues.append(Cue(t, t + seg.duration, s.caption, s.caption_en))
        t += seg.duration
    return cues


def fit_filter(src: str, out: str, w: int, h: int, mode: str, tag: str) -> str:
    if mode == "blur":
        return (
            f"{src}split[f{tag}][b{tag}];"
            f"[b{tag}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=40,eq=brightness=-0.08[bb{tag}];"
            f"[f{tag}]scale={w}:{h}:force_original_aspect_ratio=decrease[ff{tag}];"
            f"[bb{tag}][ff{tag}]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p{out}"
        )
    return f"{src}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p{out}"


def _encode_args(fps: int) -> list[str]:
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"]


def _run(args: list[str], cwd: Path) -> None:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg 失敗：\n{proc.stderr[-3000:]}")


def build_episode(ep: Episode, cfg: Config, placeholder: bool = False, music: Path | None = None) -> Path:
    require_ffmpeg()
    v = cfg.video
    w, h, fps = v["width"], v["height"], v["fps"]
    out_dir = cfg.path("build") / ep.id
    out_dir.mkdir(parents=True, exist_ok=True)
    segments = plan_segments(ep, cfg, placeholder)

    args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    filters: list[str] = []
    n = 0
    for i, seg in enumerate(segments):
        d = f"{seg.duration:.3f}"
        if seg.clip is not None:
            args += ["-i", str(seg.clip.resolve())]
            vin, n = n, n + 1
            if v["keep_clip_audio"] and seg.probe and seg.probe.has_audio:
                ain, vol = vin, v["clip_audio_volume"]
            else:
                args += ["-f", "lavfi", "-t", d, "-i", "anullsrc=r=48000:cl=stereo"]
                ain, n, vol = n, n + 1, 1.0
        else:
            args += ["-f", "lavfi", "-t", d, "-i", f"color=c=0x2B2B30:s={w}x{h}:r={fps}"]
            args += ["-f", "lavfi", "-t", d, "-i", "anullsrc=r=48000:cl=stereo"]
            vin, ain, n, vol = n, n + 1, n + 2, 1.0
        filters.append(fit_filter(f"[{vin}:v]trim=duration={d},setpts=PTS-STARTPTS,fps={fps},", f"[v{i}]", w, h, v["fit"], str(i)))
        filters.append(f"[{ain}:a]{AUDIO_FMT},apad,atrim=duration={d},asetpts=PTS-STARTPTS,volume={vol}[a{i}]")
    filters.append("".join(f"[v{i}][a{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=1:a=1[vc][ac]")

    cues = episode_cues(segments)
    if cues:
        (out_dir / f"{ep.id}.ass").write_text(build_ass(cues, v), encoding="utf-8")
        # 在輸出資料夾執行 ffmpeg，字幕檔用相對路徑，避免各作業系統的路徑跳脫問題
        filters.append(f"[vc]subtitles={ep.id}.ass[vout]")
    else:
        filters.append("[vc]null[vout]")

    music = music or (cfg.path("media") / ep.music_file if ep.music_file else None)
    total = sum(s.duration for s in segments)
    if music is not None:
        if not music.exists():
            raise SystemExit(f"找不到配樂：{music}")
        args += ["-stream_loop", "-1", "-i", str(music.resolve())]
        fade = max(total - 1.5, 0)
        filters.append(
            f"[{n}:a]{AUDIO_FMT},atrim=duration={total:.3f},afade=t=in:d=0.5,"
            f"afade=t=out:st={fade:.3f}:d=1.5,volume={v['music_volume']}[mus]"
        )
        filters.append("[ac][mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        filters.append("[ac]anull[aout]")

    name = f"{ep.id}-placeholder.mp4" if placeholder and any(s.clip is None for s in segments) else f"{ep.id}.mp4"
    args += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", *_encode_args(fps), name]
    _run(args, out_dir)
    return out_dir / name


def compile_videos(videos: list[tuple[str, Path]], out: Path, cfg: Config) -> list[tuple[str, float]]:
    """把多支 Shorts 接成一支 16:9 長影片（模糊背景補邊），回傳章節時間點。"""
    require_ffmpeg()
    w, h, fps = 1920, 1080, cfg.video["fps"]
    out.parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    filters, entries, t = [], [], 0.0
    for i, (title, path) in enumerate(videos):
        pr = probe(path)
        args += ["-i", str(path.resolve())]
        filters.append(fit_filter(f"[{i}:v]fps={fps},", f"[v{i}]", w, h, "blur", str(i)))
        if pr.has_audio:
            filters.append(f"[{i}:a]{AUDIO_FMT},apad,atrim=duration={pr.duration:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={pr.duration:.3f}[a{i}]")
        entries.append((title, t))
        t += pr.duration
    filters.append("".join(f"[v{i}][a{i}]" for i in range(len(videos))) + f"concat=n={len(videos)}:v=1:a=1[vout][aout]")
    args += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", *_encode_args(fps), str(out.resolve())]
    _run(args, out.parent)
    return entries
