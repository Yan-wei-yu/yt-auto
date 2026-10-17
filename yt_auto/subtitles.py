from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Cue:
    start: float
    end: float
    text: str
    text_en: str = ""
    style: str = "Main"


def ass_escape(text: str) -> str:
    # ASS 會把 {} 當成樣式標籤、\N 當換行
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(cues: list[Cue], video: dict) -> str:
    w, h = video["width"], video["height"]
    font = video["font"]
    size, size_en = video["caption_size"], video["caption_en_size"]
    margin = video["caption_margin_bottom"]
    # 白字黑邊，夜市招牌感的黃色英文小字；Label 給 placeholder 預覽用
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00201A1A,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{margin},1
Style: Label,{font},{max(size // 2, 20)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,0,7,40,40,60,1
Style: Action,{font},{max(size // 2, 20)},&H00E0E0E0,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,0,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for c in cues:
        text = ass_escape(c.text)
        if c.text_en:
            text += f"\\N{{\\fs{size_en}\\c&H5EC1FF&}}{ass_escape(c.text_en)}"
        fade = "{\\fad(120,120)}" if c.style == "Main" else ""
        events.append(f"Dialogue: 0,{ass_time(c.start)},{ass_time(c.end)},{c.style},,0,0,0,,{fade}{text}")
    return header + "\n".join(events) + "\n"
