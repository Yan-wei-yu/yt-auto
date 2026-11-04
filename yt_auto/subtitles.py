"""字幕：照句子切，時間照配音實際唸到哪裡。

旁白先切成「子句」（逗號、句號等標點後面切開），配音時每個子句前面放一個時間標記，
Google 配音會回傳每個標記的秒數。字幕把同一句裡的子句合併到一行放得下為止，
所以每一則字幕都是完整的句子或子句，出現和消失的時間也跟聲音對齊。
沒有時間標記（自己的錄音、其他配音引擎）時，用字數和標點停頓估算。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SENTENCE_END = "。！？!?"
CLAUSE_END = "，。！？；：,!?;:"
CLOSERS = "」』）)"
OPENERS = "「『（("
# 字幕行尾不需要的標點（問號、驚嘆號和引號留著）
TRAILING = re.compile(r"[，。；：、,;:\s]+([」』）)]*)$")
# 子句太長、一定要換行的時候，優先斷在這些字後面（虛詞）或前面（介詞、連接詞）
BREAK_AFTER = set("的了是都也還就說著過嗎呢吧")
BREAK_BEFORE = set("在從到把被但而對向給讓比和跟與為因")
# 中文數字後面不斷（「一千五百七十三｜位」會變成兩半）
NUMERALS = set("零一二三四五六七八九十百千萬億兩點")


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


def clauses(text: str) -> list[str]:
    """旁白切成子句，標點（和後面的右引號）跟著前一個子句。配音的時間標記也照這個切法放。"""
    text = " ".join(text.split())
    out, cur, i = [], "", 0
    while i < len(text):
        cur += text[i]
        if text[i] in CLAUSE_END:
            while i + 1 < len(text) and text[i + 1] in CLOSERS:
                i += 1
                cur += text[i]
            out.append(cur.strip())
            cur = ""
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return [c for c in out if c]


def display(text: str) -> str:
    return TRAILING.sub(r"\1", text.strip())


def _ascii_word(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in "&.%+-")


def _break_points(s: str) -> list[tuple[int, int]]:
    """可以斷開的位置和優先度（數字小的優先）；不會斷在英文單字、數字或引號中間。"""
    points = []
    for i in range(1, len(s)):
        a, b = s[i - 1], s[i]
        if (_ascii_word(a) and _ascii_word(b)) or a in NUMERALS:
            continue
        if b in CLAUSE_END + CLOSERS + "、" or a in OPENERS:
            continue
        if a == " " or b == " " or a == "、":
            points.append((i, 0))
        elif a in BREAK_AFTER or b in BREAK_BEFORE:
            points.append((i, 1))
        else:
            points.append((i, 2))
    return points


def _split_at(s: str, target: int, lo: int, hi: int) -> int:
    """在 [lo, hi] 之間挑離 target 最近、又最自然的斷點；範圍內沒有就放寬範圍，也不硬切英文單字。"""
    points = _break_points(s)
    inside = [p for p in points if lo <= p[0] <= hi]
    if not inside and not points:
        return min(max(target, lo), hi)
    return min(inside or points, key=lambda p: abs(p[0] - target) + (0, 1, 4)[p[1]] * 1.5)[0]


def two_lines(text: str, max_chars: int) -> str:
    """一行放不下時，在中間附近找個自然的地方換行（兩行都不超過 max_chars）。"""
    if len(text) <= max_chars:
        return text
    i = _split_at(text, len(text) // 2, len(text) - max_chars, max_chars)
    return text[:i].rstrip() + "\n" + text[i:].lstrip()


def _pieces(clause: str, max_chars: int) -> list[str]:
    """超過兩行的超長子句，切成幾段（每段最多兩行）。"""
    out = []
    while len(display(clause)) > max_chars * 2:
        n = len(clause)
        count = -(-n // (max_chars * 2))
        i = _split_at(clause, n // count, max_chars // 2, max_chars * 2)
        out.append(clause[:i])
        clause = clause[i:]
    return out + [clause]


def _weight(text: str) -> float:
    """估算唸這段要多久（相對值）：中文一字一拍，英文單字約一拍半，標點有停頓。"""
    w = len(re.findall(r"[一-鿿]", text))
    w += 1.5 * len(re.findall(r"[A-Za-z]+", text)) + 0.5 * len(re.findall(r"\d", text))
    w += sum(1.0 if ch in SENTENCE_END else 0.5 for ch in text if ch in CLAUSE_END)
    return max(w, 0.5)


def estimate_marks(parts: list[str], start: float, duration: float) -> list[float]:
    weights = [_weight(p) for p in parts]
    total, marks, t = sum(weights), [start], start
    for w in weights:
        t += duration * w / total
        marks.append(t)
    return marks


def timed_cues(text: str, start: float, duration: float, max_chars: int = 18,
               marks: list[float] | None = None) -> list[Cue]:
    """整段旁白的字幕。marks：每個子句開始的秒數（多一個結尾），由 Google 配音提供；沒有就估算。"""
    parts = clauses(text)
    if not parts:
        return []
    if marks and len(marks) == len(parts) + 1 and all(m is not None for m in marks):
        times = [start + m for m in marks]
        times[-1] = max(times[-1], times[-2] + 0.3)
    else:
        times = estimate_marks(parts, start, duration)

    cues: list[Cue] = []
    i = 0
    while i < len(parts):
        j = i
        # 同一句裡的子句合併到一行放得下為止；句號、問號、分號就是一則字幕的結尾
        while (j + 1 < len(parts) and parts[j][-1:] not in SENTENCE_END + "；;" + CLOSERS
               and len(display("".join(parts[i:j + 2]))) <= max_chars):
            j += 1
        group = "".join(parts[i:j + 1])
        if j == i and len(display(group)) > max_chars * 2:
            # 超長子句：拆段，段內時間照字數估
            pieces = _pieces(group, max_chars)
            sub = estimate_marks(pieces, times[i], times[i + 1] - times[i])
            for k, piece in enumerate(pieces):
                cues.append(Cue(sub[k], sub[k + 1], two_lines(display(piece), max_chars)))
        else:
            cues.append(Cue(times[i], times[j + 1], two_lines(display(group), max_chars)))
        i = j + 1
    return [c for c in cues if c.text]


def build_ass(cues: list[Cue], width: int, height: int, font: str, size: int, margin_v: int) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [f"Dialogue: 0,{ass_time(c.start)},{ass_time(c.end)},Main,,0,0,0,,{ass_escape(c.text)}" for c in cues]
    return header + "\n".join(events) + "\n"
