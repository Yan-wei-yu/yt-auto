from __future__ import annotations

import re
from dataclasses import dataclass

TRAILING = "，。；：、,;: "


@dataclass
class Cue:
    start: float
    end: float
    text: str


def ass_escape(text: str) -> str:
    # ASS 會把 {} 當成樣式標籤、\N 當換行
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def chunk(text: str, max_chars: int = 18) -> list[str]:
    """把旁白切成一行一行的字幕：先照標點切，太短的合併、太長的硬切。"""
    parts = [p for p in re.split(r"(?<=[，。！？；：,!?;])", text) if p.strip()]
    lines: list[str] = []
    for part in parts:
        part = part.strip()
        while len(part) > max_chars:
            lines.append(part[:max_chars])
            part = part[max_chars:]
        if lines and len(lines[-1]) + len(part) <= max_chars * 0.75 and lines[-1][-1:] not in "。！？!?":
            lines[-1] += part
        else:
            lines.append(part)
    return [ln.rstrip(TRAILING) for ln in lines if ln.rstrip(TRAILING)]


def timed_cues(text: str, start: float, duration: float, max_chars: int = 18) -> list[Cue]:
    """依字數比例分配時間（沒有逐字時間碼時的近似做法）。"""
    lines = chunk(text, max_chars)
    total = sum(len(x) for x in lines) or 1
    cues, t = [], start
    for line in lines:
        d = duration * len(line) / total
        cues.append(Cue(t, t + d, line))
        t += d
    return cues


def build_ass(cues: list[Cue], width: int, height: int, font: str, size: int, margin_v: int) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [f"Dialogue: 0,{ass_time(c.start)},{ass_time(c.end)},Main,,0,0,0,,{ass_escape(c.text)}" for c in cues]
    return header + "\n".join(events) + "\n"
