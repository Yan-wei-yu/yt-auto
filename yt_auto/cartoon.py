"""Q 版卡通：把當週新聞人物（或擬人化的公司、數據）畫在舞台上。

全部用 matplotlib 的圖形畫，不需要另外的繪圖軟體。人物外觀寫在 channel/cast.yaml，
每段腳本用 cast 指定誰上台、什麼表情、什麼動作、手上拿什麼、說什麼。
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml
from matplotlib.patches import Arc, Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle, Wedge

OUTLINE = "#1B1B1F"
WHITE = "#FFFFFF"
MOODS = {"neutral", "happy", "laugh", "shocked", "nervous", "cry", "smug", "angry", "zipped"}
ARMS = {"down", "up", "hold", "shrug", "facepalm", "point"}
HOLDING = {"card", "sign", "cash"}
SHAPES = {"server", "gas_pump", "barrel", "bank", "podium", "screen"}


def load_cast(path: Path) -> dict[str, dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class Painter:
    """在一個 Axes 上畫圖；lw 是線寬基準（隨畫面大小縮放）。"""

    def __init__(self, ax, lw: float, font_pt: float):
        self.ax, self.lw, self.font_pt = ax, lw, font_pt

    def add(self, patch, z=2):
        patch.set_zorder(z)
        self.ax.add_patch(patch)
        return patch

    def line(self, xs, ys, color=OUTLINE, w=1.0, z=3, cap="round"):
        self.ax.plot(xs, ys, color=color, lw=self.lw * w, solid_capstyle=cap, zorder=z)

    # ---------- 臉 ----------
    def face(self, cx, cy, R, mood, z=6):
        ex, ey, my = 0.36 * R, cy + 0.02 * R, cy - 0.40 * R
        lw = 1.0
        for sgn in (-1, 1):
            x = cx + sgn * ex
            if mood in ("happy", "laugh"):
                self.add(Arc((x, ey - 0.04 * R), 0.30 * R, 0.26 * R, theta1=20, theta2=160, lw=self.lw * 1.3, color=OUTLINE), z)
            elif mood == "cry":
                self.add(Arc((x, ey + 0.06 * R), 0.30 * R, 0.24 * R, theta1=200, theta2=340, lw=self.lw * 1.3, color=OUTLINE), z)
                self.line([x, x - sgn * 0.02 * R, x], [ey - 0.04 * R, my, cy - 0.85 * R], "#6EC6FF", 2.2, z)
            elif mood == "shocked":
                self.add(Circle((x, ey), 0.17 * R, fc=WHITE, ec=OUTLINE, lw=self.lw), z)
                self.add(Circle((x, ey), 0.06 * R, fc=OUTLINE, ec="none"), z + 1)
            elif mood == "smug":
                self.add(Circle((x, ey - 0.03 * R), 0.075 * R, fc=OUTLINE, ec="none"), z)
                self.line([x - 0.13 * R, x + 0.13 * R], [ey + 0.03 * R, ey + 0.03 * R], OUTLINE, 1.3, z)
            else:
                self.add(Circle((x, ey), 0.085 * R, fc=OUTLINE, ec="none"), z)
                self.add(Circle((x + 0.03 * R, ey + 0.03 * R), 0.028 * R, fc=WHITE, ec="none"), z + 1)
            # 眉毛
            by = cy + 0.30 * R
            inner, outer = x - sgn * 0.12 * R, x + sgn * 0.14 * R
            tilt = {"nervous": (0.07, -0.03), "cry": (0.07, -0.03), "angry": (-0.07, 0.05), "shocked": (0.10, 0.10),
                    "smug": (0.0, 0.08 if sgn > 0 else 0.0)}.get(mood, (0.0, 0.0))
            self.line([inner, outer], [by + tilt[0] * R, by + tilt[1] * R], OUTLINE, 1.2, z)
        # 嘴巴
        if mood in ("happy", "laugh"):
            h = 0.30 if mood == "laugh" else 0.20
            self.add(Polygon([(cx - 0.26 * R, my + 0.06 * R), (cx + 0.26 * R, my + 0.06 * R),
                              *[(cx + 0.26 * R * math.cos(t), my + 0.06 * R - h * R * math.sin(t))
                                for t in [i * math.pi / 12 for i in range(13)]]],
                             fc="#7A2A2A", ec=OUTLINE, lw=self.lw), z)
            for sgn in (-1, 1):
                self.add(Ellipse((cx + sgn * 0.58 * R, cy - 0.22 * R), 0.22 * R, 0.12 * R, fc="#FF8A8A", alpha=0.55, ec="none"), z)
        elif mood in ("shocked", "cry"):
            self.add(Ellipse((cx, my - 0.04 * R), 0.20 * R, 0.26 * R, fc="#5A1E1E", ec=OUTLINE, lw=self.lw), z)
        elif mood == "nervous":
            xs = [cx - 0.22 * R + i * 0.088 * R for i in range(6)]
            self.line(xs, [my + (0.04 if i % 2 else -0.04) * R for i in range(6)], OUTLINE, 1.1, z)
            self.add(Polygon([(cx + 1.0 * R, cy + 0.55 * R), (cx + 0.92 * R, cy + 0.28 * R), (cx + 1.08 * R, cy + 0.28 * R)],
                             fc="#6EC6FF", ec=OUTLINE, lw=self.lw * 0.6), z)
            self.add(Circle((cx + 1.0 * R, cy + 0.27 * R), 0.08 * R, fc="#6EC6FF", ec=OUTLINE, lw=self.lw * 0.6), z)
        elif mood == "angry":
            self.add(Arc((cx, my - 0.10 * R), 0.36 * R, 0.22 * R, theta1=20, theta2=160, lw=self.lw * 1.2, color=OUTLINE), z)
            ax_, ay_ = cx + 0.78 * R, cy + 0.78 * R
            for a in (0, 90, 180, 270):
                t = math.radians(a + 45)
                self.line([ax_ + 0.06 * R * math.cos(t), ax_ + 0.18 * R * math.cos(t)],
                          [ay_ + 0.06 * R * math.sin(t), ay_ + 0.18 * R * math.sin(t)], "#FF4D4F", 1.6, z)
        elif mood == "smug":
            self.add(Arc((cx + 0.06 * R, my + 0.04 * R), 0.36 * R, 0.18 * R, theta1=200, theta2=330, lw=self.lw * 1.2, color=OUTLINE), z)
        elif mood == "zipped":
            self.line([cx - 0.24 * R, cx + 0.24 * R], [my, my], OUTLINE, 1.3, z)
            for i in range(7):
                xx = cx - 0.21 * R + i * 0.07 * R
                self.line([xx, xx], [my - 0.05 * R, my + 0.05 * R], OUTLINE, 0.8, z)
            self.add(Rectangle((cx + 0.22 * R, my - 0.07 * R), 0.07 * R, 0.14 * R, fc="#C9CDD2", ec=OUTLINE, lw=self.lw * 0.6), z)
        else:
            self.add(Arc((cx, my + 0.06 * R), 0.34 * R, 0.18 * R, theta1=200, theta2=340, lw=self.lw * 1.2, color=OUTLINE), z)

    # ---------- 頭髮 ----------
    def hair(self, cx, cy, R, style, color, z=5):
        if style == "bald":
            for sgn in (-1, 1):
                self.add(Ellipse((cx + sgn * 0.88 * R, cy + 0.15 * R), 0.28 * R, 0.5 * R, fc=color, ec=OUTLINE, lw=self.lw * 0.8), z)
            return
        outer = 1.14 if style == "swept" else 1.06
        self.add(Wedge((cx, cy), outer * R, 8, 172, width=(outer - 0.62) * R, fc=color, ec=OUTLINE, lw=self.lw), z)
        if style == "side_part":
            # 旁分：右邊一片瀏海，左邊一條分線
            self.add(Ellipse((cx + 0.28 * R, cy + 0.62 * R), 1.15 * R, 0.36 * R, angle=-16, fc=color, ec="none"), z)
            self.line([cx - 0.30 * R, cx - 0.16 * R], [cy + 0.98 * R, cy + 0.66 * R], OUTLINE, 0.8, z + 1)
        elif style == "swept":
            # 往後梳：沒有瀏海，額頭露出來，頭頂比較蓬
            for t in (60, 90, 120):
                a = math.radians(t)
                self.line([cx + 0.70 * R * math.cos(a), cx + 1.02 * R * math.cos(a - 0.25)],
                          [cy + 0.70 * R * math.sin(a), cy + 1.02 * R * math.sin(a - 0.25)], "#9A9A9A", 0.6, z + 1)
        elif style == "spiky":
            pts = []
            for i in range(9):
                t = math.radians(20 + i * 17.5)
                rr = 1.32 * R if i % 2 else 0.98 * R
                pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t)))
            self.add(Polygon(pts, fc=color, ec=OUTLINE, lw=self.lw), z)
        elif style == "long":
            for sgn in (-1, 1):
                self.add(FancyBboxPatch((cx + sgn * 0.95 * R - 0.18 * R, cy - 0.9 * R), 0.36 * R, 1.3 * R,
                                        boxstyle="round,pad=0,rounding_size=0.15", fc=color, ec=OUTLINE, lw=self.lw), z - 2)
        else:  # short
            self.add(Ellipse((cx - 0.2 * R, cy + 0.68 * R), 0.9 * R, 0.32 * R, angle=-12, fc=color, ec="none"), z)

    # ---------- 手上的東西 ----------
    def held(self, item, x, y, s, z=9):
        kind, text = item["type"], str(item.get("text", ""))
        if kind == "card":
            self.add(FancyBboxPatch((x - 16 * s, y - 2 * s), 32 * s, 20 * s, boxstyle="round,pad=0.4",
                                    fc="#FFF8E1", ec=OUTLINE, lw=self.lw), z)
            self.ax.text(x, y + 8 * s, text, ha="center", va="center", fontsize=self.font_pt * 0.75 * s, color=OUTLINE,
                         fontweight="bold", zorder=z + 1)
        elif kind == "sign":
            self.line([x, x], [y, y + 26 * s], "#8B5A2B", 1.6, z)
            self.add(FancyBboxPatch((x - 20 * s, y + 24 * s), 40 * s, 18 * s, boxstyle="round,pad=0.3",
                                    fc="#FFFFFF", ec=OUTLINE, lw=self.lw), z)
            self.ax.text(x, y + 33 * s, text, ha="center", va="center", fontsize=self.font_pt * 0.9 * s, color=OUTLINE,
                         fontweight="bold", zorder=z + 1)
        elif kind == "cash":
            for i in range(3):
                self.add(Rectangle((x - 13 * s + i * 1.5 * s, y - 2 * s + i * 3 * s), 26 * s, 10 * s, fc="#5DBB63",
                                   ec=OUTLINE, lw=self.lw * 0.8), z + i)
            self.ax.text(x + 2 * s, y + 9 * s, text or "$", ha="center", va="center", fontsize=self.font_pt * 0.6 * s,
                         color=OUTLINE, fontweight="bold", zorder=z + 4)

    # ---------- 手臂 ----------
    def arms(self, x, shoulder_y, ground, face_y, s, arms, color, skin, item, z=7):
        sx = 13 * s
        targets = {
            "down": [(-19, -18), (19, -18)],
            "up": [(-24, 22), (24, 22)],
            "hold": [(-9, -10), (9, -10)],
            "shrug": [(-26, 4), (26, 4)],
            "point": [(-19, -18), (30, 10)],
        }
        if arms == "facepalm":
            ends = [(x - 19 * s, shoulder_y - 18 * s), (x + 6 * s, face_y)]
        else:
            ends = [(x + dx * s, shoulder_y + dy * s) for dx, dy in targets.get(arms, targets["down"])]
        for sgn, (hx, hy) in zip((-1, 1), ends):
            self.line([x + sgn * sx, hx], [shoulder_y, hy], color, 4.2, z)
            self.add(Circle((hx, hy), 4.2 * s, fc=skin, ec=OUTLINE, lw=self.lw * 0.8), z + 1)
        if item:
            if item["type"] == "sign" and arms == "up":
                self.held(item, x, shoulder_y + 20 * s, s, z + 2)
            elif item["type"] == "sign":
                self.held(item, ends[1][0], ends[1][1], s, z + 2)
            else:
                self.held(item, x, shoulder_y - 22 * s, s, z + 2)

    # ---------- 人物 ----------
    def person(self, look, x, ground, s, mood, arms, item):
        skin = look.get("skin", "#F2C9A0")
        outfit = look.get("outfit", {})
        color = outfit.get("color", "#2B3A55")
        self.add(Ellipse((x, ground), 34 * s, 5 * s, fc="#000000", alpha=0.25, ec="none"), 1)
        for sgn in (-1, 1):
            self.add(Rectangle((x + sgn * 6 * s - 3.5 * s, ground + 2 * s), 7 * s, 14 * s, fc=outfit.get("pants", "#2A2A33"),
                               ec=OUTLINE, lw=self.lw * 0.8), 2)
            self.add(Ellipse((x + sgn * 7 * s, ground + 2 * s), 12 * s, 5 * s, fc="#1E1E22", ec=OUTLINE, lw=self.lw * 0.6), 3)
        bx, by, bw, bh = x - 15 * s, ground + 14 * s, 30 * s, 30 * s
        self.add(FancyBboxPatch((bx, by), bw, bh, boxstyle=f"round,pad=0,rounding_size={7 * s}", fc=color,
                                ec=OUTLINE, lw=self.lw), 4)
        top = by + bh
        kind = outfit.get("type", "suit")
        if kind == "suit":
            self.add(Polygon([(x - 7 * s, top - 0.5 * s), (x + 7 * s, top - 0.5 * s), (x, top - 13 * s)], fc=WHITE,
                             ec=OUTLINE, lw=self.lw * 0.7), 5)
            self.add(Polygon([(x - 2.2 * s, top - 2 * s), (x + 2.2 * s, top - 2 * s), (x + 3 * s, top - 15 * s),
                              (x, top - 19 * s), (x - 3 * s, top - 15 * s)], fc=outfit.get("tie", "#C0392B"),
                             ec=OUTLINE, lw=self.lw * 0.7), 6)
        elif kind == "leather":
            for sgn in (-1, 1):
                self.add(Polygon([(x, top - 2 * s), (x + sgn * 10 * s, top - 1 * s), (x + sgn * 6 * s, top - 11 * s)],
                                 fc="#2C2C2C", ec=OUTLINE, lw=self.lw * 0.7), 5)
            self.line([x, x], [top - 8 * s, by + 2 * s], "#8A8A8A", 0.7, 5)
            self.line([x - 11 * s, x - 7 * s], [top - 14 * s, by + 6 * s], "#FFFFFF", 0.6, 5)
        else:  # tshirt
            self.add(Arc((x, top - 0.5 * s), 12 * s, 7 * s, theta1=180, theta2=360, lw=self.lw * 0.8, color=OUTLINE), 5)
        R = 21 * s
        cy = top + R * 0.82
        self.add(Circle((x - R * 0.98, cy), R * 0.2, fc=skin, ec=OUTLINE, lw=self.lw * 0.8), 4)
        self.add(Circle((x + R * 0.98, cy), R * 0.2, fc=skin, ec=OUTLINE, lw=self.lw * 0.8), 4)
        hair = look.get("hair", {})
        if hair.get("style") == "long":
            self.hair(x, cy, R, "long", hair.get("color", "#333333"), z=5)
        self.add(Circle((x, cy), R, fc=skin, ec=OUTLINE, lw=self.lw), 5)
        self.face(x, cy, R, mood, z=7)
        self.hair(x, cy, R, hair.get("style", "short"), hair.get("color", "#333333"), z=8)
        if look.get("glasses"):
            for sgn in (-1, 1):
                self.add(Circle((x + sgn * 0.36 * R, cy + 0.02 * R), 0.22 * R, fc="none", ec=OUTLINE, lw=self.lw * 1.1), 9)
            self.line([x - 0.14 * R, x + 0.14 * R], [cy + 0.04 * R, cy + 0.04 * R], OUTLINE, 1.0, 9)
        self.arms(x, top - 5 * s, ground, cy - 0.2 * R, s, arms, color, skin, item, z=10)
        return cy + R

    # ---------- 擬人化物件 ----------
    def obj(self, look, x, ground, s, mood, arms, item):
        shape, color = look.get("shape", "server"), look.get("color", "#4B5BD7")
        self.add(Ellipse((x, ground), 40 * s, 5 * s, fc="#000000", alpha=0.25, ec="none"), 1)
        if shape == "server":
            w, h = 36 * s, 64 * s
            self.add(FancyBboxPatch((x - w / 2, ground), w, h, boxstyle=f"round,pad=0,rounding_size={4 * s}", fc=color,
                                    ec=OUTLINE, lw=self.lw), 3)
            for i in range(3):
                yy = ground + 6 * s + i * 9 * s
                self.add(Rectangle((x - 13 * s, yy), 26 * s, 5 * s, fc="#1B1F2E", ec="none"), 4)
                self.add(Circle((x + 9 * s, yy + 2.5 * s), 1.4 * s, fc="#22C55E" if i else "#FF4D4F", ec="none"), 5)
            fx, fy, R = x, ground + h - 17 * s, 15 * s
            self.add(Rectangle((fx - 14 * s, fy - 12 * s), 28 * s, 26 * s, fc="#E8ECF8", ec=OUTLINE, lw=self.lw * 0.8), 4)
        elif shape == "gas_pump":
            w, h = 34 * s, 58 * s
            self.add(FancyBboxPatch((x - w / 2, ground), w, h, boxstyle=f"round,pad=0,rounding_size={5 * s}", fc=color,
                                    ec=OUTLINE, lw=self.lw), 3)
            self.add(Rectangle((x - 12 * s, ground + h - 16 * s), 24 * s, 11 * s, fc="#FFF8E1", ec=OUTLINE, lw=self.lw * 0.8), 4)
            self.ax.text(x, ground + h - 10.5 * s, look.get("display", ""), ha="center", va="center", color="#C0392B",
                         fontsize=self.font_pt * 0.85 * s, fontweight="bold", zorder=5)
            self.line([x + w / 2, x + w / 2 + 8 * s, x + w / 2 + 6 * s], [ground + h * 0.7, ground + h * 0.5, ground + h * 0.25],
                      OUTLINE, 2.2, 3)
            self.add(Rectangle((x + w / 2 + 2 * s, ground + h * 0.2), 7 * s, 8 * s, fc="#444444", ec=OUTLINE, lw=self.lw * 0.6), 4)
            fx, fy, R = x, ground + h * 0.42, 14 * s
        elif shape == "barrel":
            w, h = 34 * s, 46 * s
            self.add(FancyBboxPatch((x - w / 2, ground), w, h, boxstyle=f"round,pad=0,rounding_size={8 * s}", fc=color,
                                    ec=OUTLINE, lw=self.lw), 3)
            for yy in (ground + 8 * s, ground + h - 8 * s):
                self.line([x - w / 2, x + w / 2], [yy, yy], OUTLINE, 1.2, 4)
            fx, fy, R = x, ground + h / 2, 14 * s
        elif shape == "bank":
            w, h = 46 * s, 34 * s
            self.add(Rectangle((x - w / 2, ground), w, h, fc=color, ec=OUTLINE, lw=self.lw), 3)
            self.add(Polygon([(x - w / 2 - 4 * s, ground + h), (x + w / 2 + 4 * s, ground + h), (x, ground + h + 16 * s)],
                             fc=color, ec=OUTLINE, lw=self.lw), 3)
            for i in (-1, 1):
                self.add(Rectangle((x + i * 17 * s - 2.5 * s, ground + 2 * s), 5 * s, h - 4 * s, fc="#F2F2F2", ec=OUTLINE,
                                   lw=self.lw * 0.6), 4)
            fx, fy, R = x, ground + h / 2 + 1 * s, 12 * s
        elif shape == "screen":
            # 報價螢幕：給指數、個股用；螢幕上畫一小段走勢
            w, h = 48 * s, 34 * s
            self.add(Rectangle((x - 3 * s, ground), 6 * s, 12 * s, fc="#5A5F6B", ec=OUTLINE, lw=self.lw * 0.8), 2)
            self.add(Rectangle((x - 12 * s, ground), 24 * s, 3 * s, fc="#5A5F6B", ec=OUTLINE, lw=self.lw * 0.8), 2)
            self.add(FancyBboxPatch((x - w / 2, ground + 12 * s), w, h, boxstyle=f"round,pad=0,rounding_size={4 * s}",
                                    fc="#2B2F3A", ec=OUTLINE, lw=self.lw), 3)
            self.add(Rectangle((x - w / 2 + 3 * s, ground + 15 * s), w - 6 * s, h - 6 * s, fc=color, ec="none"), 4)
            fx, fy, R = x, ground + 12 * s + h / 2, 12 * s
        else:  # podium：講台（給「政府」「黨團」這種團體角色用）
            w, h = 40 * s, 36 * s
            self.add(Polygon([(x - w / 2, ground + h), (x + w / 2, ground + h), (x + w / 2 - 4 * s, ground), (x - w / 2 + 4 * s, ground)],
                             fc=color, ec=OUTLINE, lw=self.lw), 3)
            fx, fy, R = x, ground + h / 2, 13 * s
        self.face(fx, fy, R, mood, z=6)
        if arms != "none":
            self.arms(x, fy - 2 * s, ground, fy, s * 0.9, arms, OUTLINE, "#FFFFFF", item, z=8)
        return ground + (80 if shape == "server" else 66) * s

    # ---------- 對話框與名牌 ----------
    def bubble(self, x, y, text, xlim, s):
        bx = min(max(x, xlim[0] + 26 * s), xlim[1] - 26 * s)
        self.add(Polygon([(x - 3 * s, y), (x + 3 * s, y + 4 * s), (bx - 1 * s, y + 9 * s), (bx + 6 * s, y + 9 * s)],
                         fc=WHITE, ec=OUTLINE, lw=self.lw * 0.9), 20)
        self.ax.text(bx, y + 8 * s, text, ha="center", va="bottom", fontsize=self.font_pt * 0.95, color=OUTLINE,
                     fontweight="bold", zorder=21, linespacing=1.2,
                     bbox=dict(boxstyle="round,pad=0.55", fc=WHITE, ec=OUTLINE, lw=self.lw * 0.9))

    def nametag(self, x, y, name, role, s):
        label = f"{name}" + (f"\n{role}" if role else "")
        self.ax.text(x, y, label, ha="center", va="top", fontsize=self.font_pt * 0.7, color="#F5F5F0", fontweight="bold",
                     zorder=22, linespacing=1.15,
                     bbox=dict(boxstyle="round,pad=0.35", fc="#000000", alpha=0.55, ec="none"))


def _wrap_bubble(text: str, max_chars: int = 9) -> str:
    out, line = [], ""
    for ch in text:
        line += ch
        if len(line) >= max_chars and ch not in "」』）":
            out.append(line)
            line = ""
    if line:
        out.append(line)
    return "\n".join(out)


def draw_stage(ax, cast_lib: dict, entries: list[dict], width_px: float, height_px: float,
               arrow: str | None = None, up: str = "#FF4D4F", down: str = "#22C55E", panel: str | None = "#1A2542",
               tags: bool = True):
    """在 ax 上畫一個舞台：背景、可選的大箭頭、1–3 位角色。panel=None 時不畫背景（例如橫幅）。"""
    H = 140.0
    W = H * width_px / height_px
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")
    lw = max(height_px / 260, 0.8)
    font_pt = height_px / 140 * 7.5 * 0.72 * 1.2
    p = Painter(ax, lw, font_pt)
    if panel:
        p.add(FancyBboxPatch((1, 1), W - 2, H - 2, boxstyle="round,pad=0,rounding_size=8", fc=panel, ec="none"), 0)
        p.add(Ellipse((W / 2, 30), W * 0.9, 40, fc="#24345C", alpha=0.7, ec="none"), 0)
    if arrow in ("up", "down"):
        # 背景的大趨勢線＋箭頭（紅漲綠跌）
        c = up if arrow == "up" else down
        fx = [0.08, 0.3, 0.42, 0.62, 0.74, 0.9]
        fy = [0.25, 0.48, 0.40, 0.66, 0.58, 0.84] if arrow == "up" else [0.84, 0.60, 0.68, 0.42, 0.50, 0.24]
        xs_, ys_ = [W * f for f in fx], [H * f for f in fy]
        ax.plot(xs_, ys_, color=c, lw=lw * 9, alpha=0.25, solid_joinstyle="round", solid_capstyle="round", zorder=0.5)
        ang = math.atan2(ys_[-1] - ys_[-2], xs_[-1] - xs_[-2])
        tip = (xs_[-1] + 6 * math.cos(ang), ys_[-1] + 6 * math.sin(ang))
        left = (xs_[-1] + 9 * math.cos(ang + 2.4), ys_[-1] + 9 * math.sin(ang + 2.4))
        right = (xs_[-1] + 9 * math.cos(ang - 2.4), ys_[-1] + 9 * math.sin(ang - 2.4))
        p.add(Polygon([tip, left, right], fc=c, alpha=0.25, ec="none"), 0.5)
    n = len(entries)
    if not n:
        return
    s = {1: 1.0, 2: 0.74, 3: 0.6}.get(n, 0.52)
    if W / H > 1.3:
        # 寬舞台（Shorts、縮圖）左右空間多，角色放大；有對話框時頭上要留位置
        s *= 1.12 if any(e.get("say") for e in entries) else 1.3
        s = min(s, 1.15 if n == 1 else 1.0)
    spots = {1: [0.5], 2: [0.28, 0.72], 3: [0.19, 0.5, 0.81]}
    xs = [W * f for f in spots.get(n, [(i + 1) / (n + 1) for i in range(n)])]
    ground = 26
    for x, e in zip(xs, entries):
        look = cast_lib[e["who"]]
        mood, arms, item = e.get("mood", "neutral"), e.get("arms", "down"), e.get("holding")
        if look.get("kind") == "object":
            top = p.obj(look, x, ground, s, mood, e.get("arms", "none"), item)
        else:
            top = p.person(look, x, ground, s, mood, arms, item)
        # 人多的時候名牌只放名字，避免互相擋到
        if tags:
            p.nametag(x, ground - 4, look["name"], look.get("role", "") if n == 1 else "", s)
        if e.get("say"):
            p.bubble(x, top + 3 * s, _wrap_bubble(e["say"], 7 if n > 1 else 9), (0, W), s)
