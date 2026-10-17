"""把每個段落畫成一張投影片（16:9 給長片、9:16 給 Shorts），以及長片縮圖。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager, patheffects  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

from .config import Config  # noqa: E402
from .week import Segment, Week  # noqa: E402

NAVY = "#0F1420"
PANEL = "#18233D"
TEXT = "#F5F5F0"
MUTED = "#9AA3B2"
GOLD = "#FFD54A"
WEEKDAYS = "一二三四五六日"

# Linux 的文泉驛只有一種字重，matplotlib 會一直警告，這裡關掉
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)


@dataclass
class Theme:
    up: str
    down: str
    poses: Path

    def sign_color(self, value: float) -> str:
        return self.up if value >= 0 else self.down


@dataclass
class Layout:
    portrait: bool
    width: int
    height: int
    content: tuple[float, float, float, float]  # x0, y0, x1, y1（圖的比例座標）
    pose: tuple[float, float, float, float]
    scale: float  # 字級倍率


# Shorts：上半部放內容，中間留給字幕，下面放阿韭；右側和底部會被 YouTube 的按鈕和標題蓋住
LANDSCAPE = dict(content=(0.05, 0.20, 0.66, 0.86), pose=(0.68, 0.12, 0.98, 0.88), scale=1.0)
PORTRAIT = dict(content=(0.07, 0.50, 0.93, 0.92), pose=(0.22, 0.10, 0.78, 0.39), scale=1.2)


def setup_fonts(families: list[str]) -> None:
    installed = {f.name for f in font_manager.fontManager.ttflist}
    usable = [f for f in families if f in installed]
    if not usable:
        print(f"  ⚠ 找不到中文字型 {families}，中文可能會變成方框")
    plt.rcParams["font.family"] = [*usable, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def text_units(text: str) -> float:
    return sum(1.0 if ord(ch) > 0x2E80 else 0.55 for ch in text)


def wrap(text: str, max_units: float) -> list[str]:
    """中英混排的簡易換行：中文逐字斷、英文以單字為單位。"""
    tokens, buf = [], ""
    for ch in text:
        if ord(ch) > 0x2E80 or ch == " ":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    lines, line = [], ""
    for tok in tokens:
        if line and text_units(line + tok) > max_units:
            lines.append(line.rstrip())
            line = tok.lstrip()
        else:
            line += tok
    if line.strip():
        lines.append(line.rstrip())
    return lines


class Slide:
    def __init__(self, layout: Layout, theme: Theme, week: Week):
        self.l, self.t, self.week = layout, theme, week
        self.fig = plt.figure(figsize=(layout.width / 100, layout.height / 100), dpi=100)
        self.fig.patch.set_facecolor(NAVY)

    def px(self, size: float) -> float:
        # dpi=100 時 1pt ≈ 1.39px；size 以 1080p 的像素為準
        return size * 0.72 * self.l.scale * (self.l.height if not self.l.portrait else self.l.width) / 1080

    def text(self, x, y, s, size, color=TEXT, weight="bold", ha="left", va="top", stroke=0, **kw):
        effects = [patheffects.withStroke(linewidth=stroke, foreground="#000000")] if stroke else None
        return self.fig.text(x, y, s, fontsize=self.px(size), color=color, fontweight=weight, ha=ha, va=va,
                             path_effects=effects, **kw)

    def lines(self, x, y, lines, size, color=TEXT, gap=1.35, **kw) -> float:
        step = size * gap * self.l.scale / self.l.height * (self.l.height if not self.l.portrait else self.l.width) / 1080
        for i, line in enumerate(lines):
            self.text(x, y - i * step, line, size, color, **kw)
        return y - len(lines) * step

    def max_units(self, size: float, x0: float, x1: float) -> float:
        width_px = (x1 - x0) * self.l.width
        return width_px / (size * self.l.scale * (self.l.height if not self.l.portrait else self.l.width) / 1080)

    def axes(self, x0, y0, x1, y1):
        ax = self.fig.add_axes((x0, y0, x1 - x0, y1 - y0))
        ax.set_facecolor("none")
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=MUTED, length=0)
        return ax

    def header(self):
        y = 0.975 if self.l.portrait else 0.955
        self.text(0.05 if self.l.portrait else 0.04, y, "韭菜週報", 34, GOLD)
        self.text(0.95 if self.l.portrait else 0.96, y, self.week.label, 26, MUTED, weight="normal", ha="right")

    def pose(self, name: str):
        path = self.t.poses / f"{name}.png"
        if not path.exists():
            return
        x0, y0, x1, y1 = self.l.pose
        ax = self.fig.add_axes((x0, y0, x1 - x0, y1 - y0))
        ax.imshow(mpimg.imread(path))
        ax.set_anchor("S")
        ax.axis("off")

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(path, dpi=100, facecolor=NAVY)
        plt.close(self.fig)


def _heading(s: Slide, title: str, size: float = 66, tag: str | None = None, right: tuple[str, str] | None = None) -> float:
    x0, _, x1, y1 = s.l.content
    y = y1
    if tag or right:
        if tag:
            s.text(x0, y, f" {tag} ", 32, NAVY, bbox=dict(boxstyle="round,pad=0.35", fc=GOLD, ec="none"))
        if right:
            s.text(x1, y + 0.01, right[0], 60, right[1], ha="right")
        y -= 0.075 if not s.l.portrait else 0.04
    return s.lines(x0, y, wrap(title, s.max_units(size, x0, x1)), size)


def _bullets(s: Slide, items: list[str], y: float, size: float = 42) -> float:
    x0, _, x1, _ = s.l.content
    for item in items:
        wrapped = wrap(item, s.max_units(size, x0 + 0.03, x1))
        s.text(x0, y, "•", size, GOLD)
        y = s.lines(x0 + (0.025 if not s.l.portrait else 0.045), y, wrapped, size, weight="normal")
        y -= 0.015
    return y


def draw_title(s: Slide, seg: Segment):
    x0, y0, x1, y1 = s.l.content
    y = s.lines(x0, y1 - 0.02, wrap(seg.get("headline", ""), s.max_units(92, x0, x1)), 92, stroke=0)
    stat = seg.get("stat")
    if stat:
        value = float(str(stat["value"]).replace("%", ""))
        s.text(x0, y - 0.04, stat["label"], 40, MUTED, weight="normal")
        s.text(x0, y - (0.10 if not s.l.portrait else 0.06), f"{value:+.2f}%", 150, s.t.sign_color(value))
        y -= 0.30 if not s.l.portrait else 0.16
    if seg.get("subhead"):
        s.lines(x0, y - 0.02, wrap(seg.get("subhead"), s.max_units(46, x0, x1)), 46, MUTED, weight="normal")


def _barh(s: Slide, rows: list[tuple[str, float]], top: float):
    x0, y0, x1, _ = s.l.content
    ax = s.axes(x0 + (0.17 if not s.l.portrait else 0.32), y0, x1, top)
    labels = [r[0] for r in rows][::-1]
    values = [r[1] for r in rows][::-1]
    colors = [s.t.sign_color(v) for v in values]
    ax.barh(range(len(values)), values, color=colors, height=0.66)
    span = max(abs(v) for v in values) or 1
    ax.set_xlim(min(min(values), 0) - span * 0.5, max(max(values), 0) + span * 0.5)
    ax.axvline(0, color=MUTED, lw=1.5)
    ax.set_yticks(range(len(values)), labels, fontsize=s.px(36), color=TEXT, fontweight="bold")
    ax.set_xticks([])
    for i, v in enumerate(values):
        ax.text(v + (span * 0.03 if v >= 0 else -span * 0.03), i, f"{v:+.2f}%", va="center",
                ha="left" if v >= 0 else "right", color=s.t.sign_color(v), fontsize=s.px(34), fontweight="bold")


def draw_indices(s: Slide, seg: Segment):
    y = _heading(s, seg.get("heading", "本週指數表現"))
    rows = [(f"{i['name']}", i["change_pct"]) for i in s.week.market["indices"]]
    _barh(s, rows, y - 0.03)


def draw_movers(s: Slide, seg: Segment):
    y = _heading(s, seg.get("heading", "本週漲跌排行"))
    stocks = sorted(s.week.market["stocks"], key=lambda x: x["change_pct"], reverse=True)
    if seg.get("symbols"):
        stocks = [x for x in stocks if x["symbol"] in seg.get("symbols")]
    rows = [(f"{x['name']} {x['symbol']}", x["change_pct"]) for x in stocks[: seg.get("top", 9)]]
    _barh(s, rows, y - 0.03)


def _weekday(d: str) -> str:
    return "週" + WEEKDAYS[date.fromisoformat(d).weekday()]


def draw_topic(s: Slide, seg: Segment):
    x0, y0, x1, y1 = s.l.content
    y = _heading(s, seg.get("heading", ""), tag=seg.get("tag"))
    symbol = seg.get("chart")
    if symbol:
        stock = next(x for x in s.week.market["stocks"] if x["symbol"] == symbol)
        color = s.t.sign_color(stock["change_pct"])
        s.text(x0, y - 0.01, f"{stock['name']} {symbol}　一週 {stock['change_pct']:+.2f}%", 44, color)
        top = y - (0.08 if not s.l.portrait else 0.045)
        bottom = top - (top - y0) * (0.55 if seg.get("bullets") else 0.95)
        ax = s.axes(x0 + 0.04, bottom, x1, top)
        xs = ["上週五"] + [_weekday(d) for d, _ in stock["closes"]]
        ys = [stock["base_close"]] + [c for _, c in stock["closes"]]
        ax.plot(range(len(ys)), ys, color=color, lw=5, marker="o", ms=11)
        ax.fill_between(range(len(ys)), ys, min(ys) * 0.995, color=color, alpha=0.15)
        ax.set_ylim(min(ys) * 0.99, max(ys) * 1.01)
        ax.set_xticks(range(len(xs)), xs, fontsize=s.px(28), color=MUTED)
        ax.tick_params(axis="y", labelsize=s.px(24))
        ax.grid(axis="y", color="#2A3550", lw=1)
        y = bottom - (0.07 if not s.l.portrait else 0.035)
    if seg.get("bullets"):
        _bullets(s, seg.get("bullets"), y, 38 if symbol else 42)


def draw_concept(s: Slide, seg: Segment):
    x0, y0, x1, y1 = s.l.content
    series = [float(v) for v in seg.get("series")]
    color = s.t.sign_color(series[-1] - series[0])
    y = _heading(s, seg.get("name", ""), size=70, tag="本週時事概念股（虛構）", right=(seg.get("change", ""), color))
    bottom = y0 + (y - y0) * (0.34 if seg.get("bullets") else 0.0)
    ax = s.axes(x0, bottom, x1, y - 0.03)
    for i in range(1, len(series)):
        o, c = series[i - 1], series[i]
        col = s.t.sign_color(c - o)
        lo, hi = min(o, c), max(o, c)
        span = max(series) - min(series) or 1
        ax.plot([i, i], [lo - span * 0.04, hi + span * 0.04], color=col, lw=2.5)
        ax.add_patch(Rectangle((i - 0.3, lo), 0.6, max(hi - lo, span * 0.01), color=col))
    labels = seg.get("labels") or [""] * (len(series) - 1)
    ax.set_xticks(range(1, len(series)), labels, fontsize=s.px(28), color=MUTED)
    ax.set_yticks([])
    ax.set_xlim(0.3, len(series) - 0.3)
    ax.text(0.01, 0.98, "虛構・純屬娛樂", transform=ax.transAxes, rotation=0, ha="left", va="top",
            fontsize=s.px(28), color="#FF8A8A", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", fc="none", ec="#FF8A8A", lw=3))
    if seg.get("bullets"):
        _bullets(s, seg.get("bullets"), bottom - (0.07 if not s.l.portrait else 0.035), 40)


def draw_calendar(s: Slide, seg: Segment):
    x0, _, x1, _ = s.l.content
    y = _heading(s, seg.get("heading", "下週行事曆")) - 0.03
    step = 0.085 if not s.l.portrait else 0.05
    for ev in seg.get("events", []):
        s.fig.patches.append(FancyBboxPatch((x0, y - step * 0.85), x1 - x0, step * 0.78, boxstyle="round,pad=0.004",
                                            transform=s.fig.transFigure, fc=PANEL, ec="none"))
        s.text(x0 + 0.015, y - step * 0.42, ev["date"], 38, GOLD, va="center")
        s.text(x0 + (0.20 if not s.l.portrait else 0.36), y - step * 0.42, ev["item"], 38, TEXT, weight="normal", va="center")
        y -= step


def draw_outro(s: Slide, seg: Segment):
    y = _heading(s, seg.get("headline", ""), size=72)
    y = _bullets(s, seg.get("bullets", []), y - 0.04, 40)
    x0, y0, x1, _ = s.l.content
    s.lines(x0, y0 + 0.06, wrap("本頻道內容僅為新聞整理與娛樂，不構成投資建議。", s.max_units(26, x0, x1)), 26, MUTED, weight="normal")


DRAW = {
    "title": draw_title, "indices": draw_indices, "movers": draw_movers, "topic": draw_topic,
    "concept": draw_concept, "calendar": draw_calendar, "outro": draw_outro,
}


def theme(cfg: Config) -> Theme:
    return Theme(up=cfg.market["up_color"], down=cfg.market["down_color"], poses=cfg.path("poses"))


def layout(cfg: Config, portrait: bool) -> Layout:
    v = cfg.video
    if portrait:
        return Layout(True, v["short_width"], v["short_height"], **PORTRAIT)
    return Layout(False, v["width"], v["height"], **LANDSCAPE)


def render_segment(seg: Segment, week: Week, cfg: Config, out: Path, portrait: bool = False) -> Path:
    setup_fonts(cfg.video["fonts"])
    s = Slide(layout(cfg, portrait), theme(cfg), week)
    s.header()
    DRAW[seg.type](s, seg)
    s.pose(seg.pose)
    s.save(out)
    return out


def render_thumbnail(week: Week, cfg: Config, out: Path) -> Path:
    """1280×720 縮圖：大字＋阿韭表情。thumbnail.lines 第二行通常放漲跌幅。"""
    setup_fonts(cfg.video["fonts"])
    th = week.thumbnail
    lay = Layout(False, 1280, 720, content=(0.05, 0.08, 0.62, 0.92), pose=(0.56, 0.0, 1.0, 1.0), scale=1.0)
    s = Slide(lay, theme(cfg), week)
    s.pose(th.get("pose", "flat"))
    color = s.t.up if th.get("color") == "up" else s.t.down if th.get("color") == "down" else GOLD
    if th.get("tag"):
        s.text(0.05, 0.90, f" {th['tag']} ", 64, NAVY, bbox=dict(boxstyle="round,pad=0.3", fc=GOLD, ec="none"))
    lines = th.get("lines", [])
    y = 0.76
    for i, line in enumerate(lines):
        size = 270 if i == len(lines) - 1 else 180
        s.text(0.05, y, line, size, color if i == len(lines) - 1 else TEXT, stroke=14)
        y -= size / 1080 * 1.15
    s.text(0.05, 0.06, "韭菜週報", 44, GOLD, va="bottom")
    s.save(out)
    return out
