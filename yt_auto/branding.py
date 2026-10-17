"""頻道頭像（800×800）、橫幅（2560×1440），以及放到 YouTube 上的樣子預覽。"""
from __future__ import annotations

import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

from .cartoon import draw_stage, load_cast  # noqa: E402
from .config import Config  # noqa: E402
from .slides import GOLD, NAVY, setup_fonts  # noqa: E402

GREEN_LIGHT, GREEN_DARK = "#4CAF50", "#1F7A34"
INK = "#0F1420"

# YouTube 橫幅：電視顯示整張；桌機只顯示中間 2560×423；手機約 1546×423；
# 文字和 logo 放在最保守的安全區 1235×338，任何裝置都不會被裁掉
BANNER_W, BANNER_H = 2560, 1440
SAFE = (BANNER_W - 1235) / 2, (BANNER_H - 338) / 2, 1235, 338
DESKTOP = 0, (BANNER_H - 423) / 2, BANNER_W, 423
MOBILE = (BANNER_W - 1546) / 2, (BANNER_H - 423) / 2, 1546, 423


def _canvas(w: int, h: int):
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def _pt(px: float) -> float:
    return px * 0.72  # dpi=100：1pt ≈ 1.39px


def _stroke(width: float, color: str = INK):
    return [patheffects.withStroke(linewidth=width, foreground=color)]


def _gradient(ax, x0, y0, x1, y1, c_top: str, c_bottom: str, z=0):
    top, bottom = np.array(matplotlib.colors.to_rgb(c_top)), np.array(matplotlib.colors.to_rgb(c_bottom))
    t = np.linspace(0, 1, 256)[:, None]
    img = (bottom * t + top * (1 - t))[:, None, :].repeat(2, axis=1)
    ax.imshow(img, extent=(x0, x1, y0, y1), aspect="auto", zorder=z, interpolation="bicubic")


def _trend(ax, pts, width: float, z=5):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=INK, lw=width * 1.7, solid_capstyle="round", solid_joinstyle="round", zorder=z)
    ax.plot(xs, ys, color="#FF4D4F", lw=width, solid_capstyle="round", solid_joinstyle="round", zorder=z + 1)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    d = np.array([x2 - x1, y2 - y1]) / np.hypot(x2 - x1, y2 - y1)
    n = np.array([-d[1], d[0]])
    tip = np.array([x2, y2]) + d * width * 2.2
    base = np.array([x2, y2]) - d * width * 0.6
    head = [tip, base + n * width * 1.6, base - n * width * 1.6]
    ax.add_patch(Polygon(head, fc="#FF4D4F", ec=INK, lw=width * 0.35, joinstyle="round", zorder=z + 2))


def render_avatar(cfg: Config, out: Path) -> Path:
    """綠底白字「韭」＋紅色上漲線。縮到 24px 還看得出來；不用真實人物的卡通當頭像。"""
    setup_fonts(cfg)
    fig, ax = _canvas(800, 800)
    _gradient(ax, 0, 0, 800, 800, GREEN_LIGHT, GREEN_DARK)
    ax.text(400, 480, "韭", ha="center", va="center", fontsize=_pt(470), color="#FFFFFF", fontweight="bold",
            path_effects=_stroke(26), zorder=3)
    _trend(ax, [(140, 110), (290, 175), (390, 140), (520, 235), (640, 285)], 26)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def _candles(ax, rng: random.Random, y_lo: float, y_hi: float, up: str, down: str, alpha: float = 0.22):
    """背景的 K 線：一條隨機漫步，畫得很淡，當作底紋。"""
    n = 58
    step = BANNER_W / n
    prices, p = [], 100.0
    for _ in range(n + 1):
        p *= 1 + rng.uniform(-0.035, 0.037)
        prices.append(p)
    lo, hi = min(prices), max(prices)
    scale = lambda v: y_lo + (v - lo) / (hi - lo) * (y_hi - y_lo)  # noqa: E731
    for i in range(n):
        o, c = scale(prices[i]), scale(prices[i + 1])
        color = up if c >= o else down
        x = step * (i + 0.5)
        wick = abs(c - o) * 0.6 + 12
        ax.plot([x, x], [min(o, c) - wick, max(o, c) + wick], color=color, lw=3, alpha=alpha, zorder=1)
        ax.add_patch(Rectangle((x - step * 0.3, min(o, c)), step * 0.6, max(abs(c - o), 6), fc=color, ec="none",
                               alpha=alpha, zorder=1))


def render_banner(cfg: Config, out: Path) -> Path:
    setup_fonts(cfg)
    up, down = cfg.market["up_color"], cfg.market["down_color"]
    cast = load_cast(cfg.path("cast"))
    fig, ax = _canvas(BANNER_W, BANNER_H)
    fig.patch.set_facecolor(INK)
    ax.add_patch(Rectangle((0, 0), BANNER_W, BANNER_H, fc=INK, zorder=0))
    for y in range(80, BANNER_H, 120):
        ax.plot([0, BANNER_W], [y, y], color="#FFFFFF", alpha=0.04, lw=2, zorder=0.5)
    # 電視會顯示整張：上下各再鋪一層更淡的 K 線，不會空一大片
    _candles(ax, random.Random(3), 120, 480, up, down, alpha=0.10)
    _candles(ax, random.Random(11), BANNER_H - 480, BANNER_H - 120, up, down, alpha=0.10)
    _candles(ax, random.Random(7), DESKTOP[1] + 40, DESKTOP[1] + DESKTOP[3] - 40, up, down)
    # 文字後面壓暗，K 線再熱鬧都看得清楚
    for i, a in enumerate((0.25, 0.35, 0.5, 0.7)):
        ax.add_patch(Ellipse((BANNER_W / 2, BANNER_H / 2), 1700 - i * 180, 560 - i * 60, fc=INK, alpha=a, ec="none", zorder=2))

    # 兩側的卡通：都是擬人化的指數、數據、公司，不放真實人物
    sides = [
        ((0.03, 0.26), [{"who": "nasdaq", "mood": "cry"}, {"who": "coreweave", "mood": "nervous", "arms": "up"}], "down"),
        ((0.74, 0.97), [{"who": "cpi", "mood": "angry", "arms": "up"}, {"who": "dow", "mood": "smug"}], "up"),
    ]
    y0, y1 = (DESKTOP[1] + 10) / BANNER_H, (DESKTOP[1] + DESKTOP[3] - 10) / BANNER_H
    for (x0, x1), entries, arrow in sides:
        sax = fig.add_axes((x0, y0, x1 - x0, y1 - y0))
        sax.set_zorder(3)
        draw_stage(sax, cast, entries, (x1 - x0) * BANNER_W, (y1 - y0) * BANNER_H, arrow=arrow, up=up, down=down,
                   panel=None, tags=False)

    # 安全區內：logo＋頻道名＋一句話＋更新時間
    sx, sy, sw, sh = SAFE
    cx = BANNER_W / 2
    icon = 170
    ix, iy = sx + 70, sy + sh - icon - 30
    ax.add_patch(FancyBboxPatch((ix, iy), icon, icon, boxstyle="round,pad=0,rounding_size=34", fc=GREEN_LIGHT,
                                ec=INK, lw=6, zorder=5))
    ax.text(ix + icon / 2, iy + icon / 2 + 6, "韭", ha="center", va="center", fontsize=_pt(122), color="#FFFFFF",
            path_effects=_stroke(9), zorder=6)
    ax.text(ix + icon + 40, iy + icon / 2 + 4, "韭菜週報", ha="left", va="center", fontsize=_pt(150), color="#FFFFFF",
            path_effects=_stroke(12), zorder=6)
    ax.text(cx, sy + 98, "用搞笑卡通，每週看完一週美股", ha="center", va="center", fontsize=_pt(56), color="#E6EAF2",
            path_effects=_stroke(8), zorder=6)
    ax.text(cx, sy + 30, "  每週日 20:00 更新  ", ha="center", va="center", fontsize=_pt(40), color=INK, zorder=6,
            bbox=dict(boxstyle="round,pad=0.35", fc=GOLD, ec="none"))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100, facecolor=INK)
    plt.close(fig)
    return out


def _crop(img, box):
    x, y, w, h = (int(v) for v in box)
    rows = img.shape[0]
    return img[rows - (y + h):rows - y, x:x + w]


def render_preview(banner_png: Path, avatar_png: Path, out: Path, name: str, handle: str) -> Path:
    """模擬頻道頁：桌機（深色模式）、手機、整張橫幅的安全區，以及頭像縮小後的樣子。"""
    banner, avatar = mpimg.imread(banner_png), mpimg.imread(avatar_png)
    W, H = 1600, 1640
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor("#FFFFFF")

    def box(x, y, w, h):  # 以左上角為原點的像素座標
        ax = fig.add_axes((x / W, 1 - (y + h) / H, w / W, h / H))
        ax.axis("off")
        return ax

    def text(x, y, s, size, color="#333333", bold=True):
        fig.text(x / W, 1 - y / H, s, fontsize=size, color=color, fontweight="bold" if bold else "normal", va="top")

    def panel(x, y, w, h, color, edge="none"):
        ax = box(x, y, w, h)
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.02", fc=color, ec=edge,
                                    lw=2, transform=ax.transAxes))

    def round_avatar(x, y, size):
        ax = box(x, y, size, size)
        ax.imshow(avatar)
        ax.images[0].set_clip_path(Circle((399.5, 399.5), 400, transform=ax.transData))

    # 桌機（深色模式）
    text(20, 16, "桌機（YouTube 深色模式）：橫幅只顯示中間一條", 16)
    panel(20, 50, 1560, 520, "#0F0F0F")
    bw = 1520
    box(40, 70, bw, bw * 423 / 2560).imshow(_crop(banner, DESKTOP))
    round_avatar(60, 360, 160)
    text(250, 400, name, 28, "#F1F1F1")
    text(250, 460, f"{handle}・訂閱者 0 位・影片 0 部", 15, "#AAAAAA", bold=False)

    # 手機
    text(20, 600, "手機：左右再被裁掉", 16)
    panel(20, 634, 420, 560, "#FFFFFF", "#CCCCCC")
    mw = 400
    box(30, 644, mw, mw * 423 / 1546).imshow(_crop(banner, MOBILE))
    round_avatar(40, 780, 96)
    text(150, 795, name, 20, "#0F0F0F")
    text(150, 835, handle, 12, "#777777", bold=False)

    # 整張橫幅＋範圍標示
    text(480, 600, "電視顯示整張｜白虛線＝桌機範圍｜黃框＝任何裝置都看得到的安全區", 16)
    fw = 1100
    fax = box(480, 634, fw, fw * BANNER_H / BANNER_W)
    fax.imshow(banner, extent=(0, BANNER_W, 0, BANNER_H))
    fax.add_patch(Rectangle(DESKTOP[:2], DESKTOP[2], DESKTOP[3], fill=False, ec="#FFFFFF", lw=2, ls="--"))
    fax.add_patch(Rectangle(SAFE[:2], SAFE[2], SAFE[3], fill=False, ec=GOLD, lw=3))

    # 頭像實際大小
    text(20, 1300, "頭像實際大小：頻道頁 160px、首頁 98px、影片下方 48px、留言 24px", 16)
    x = 30
    for size in (160, 98, 48, 24):
        round_avatar(x, 1350 + (160 - size) / 2, size)
        x += size + 50
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out
