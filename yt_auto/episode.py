from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from .config import Config

# Shorts 上限是 3 分鐘；超過 60 秒只警告，因為這個頻道的節奏是 20–40 秒
SHORTS_MAX_SECONDS = 180
SOFT_MAX_SECONDS = 60

# 角色和寶可夢無關，metadata 裡出現這些字會被當成誤導性標籤，也會引來版權問題
BANNED_TERMS = [
    "pokemon", "pokémon", "charmander", "charmeleon", "charizard", "pikachu", "nintendo",
    "寶可夢", "神奇寶貝", "小火龍", "火恐龍", "噴火龍", "皮卡丘", "任天堂",
]

BEATS = {"hook", "setup", "trouble", "twist", "ending"}


@dataclass
class Shot:
    id: str
    beat: str
    duration: float
    action: str
    prompt: str
    camera: str = ""
    sfx: str = ""
    caption: str = ""
    caption_en: str = ""


@dataclass
class Episode:
    id: str
    slug: str
    dish: str
    title: str
    title_en: str
    setting: str
    logline: str
    music: str
    shots: list[Shot]
    youtube: dict[str, Any]
    publish_at: datetime | None
    music_file: str | None = None
    path: Path | None = None

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.shots)


def _parse_publish(value: Any, tz: ZoneInfo) -> datetime | None:
    if value in (None, ""):
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def load_episode(path: Path, cfg: Config) -> Episode:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg.channel["timezone"])
    shots = [Shot(**s) for s in raw["shots"]]
    music = raw.get("music") or {}
    return Episode(
        id=raw["id"],
        slug=raw["slug"],
        dish=raw["dish"],
        title=raw["title"],
        title_en=raw["title_en"],
        setting=raw["setting"],
        logline=raw["logline"],
        music=music.get("mood", ""),
        music_file=music.get("file"),
        shots=shots,
        youtube=raw["youtube"],
        publish_at=_parse_publish(raw.get("publish_at"), tz),
        path=path,
    )


def load_episodes(cfg: Config) -> list[Episode]:
    files = sorted(cfg.path("episodes").glob("ep*.yaml"))
    return [load_episode(f, cfg) for f in files]


def find_episode(cfg: Config, ref: str) -> Episode:
    for ep in load_episodes(cfg):
        if ep.id == ref or ep.slug == ref or (ep.path and ep.path.stem == ref):
            return ep
    raise SystemExit(f"找不到集數：{ref}（可用 `python -m yt_auto list` 查看）")


def tags_length(tags: list[str]) -> int:
    # YouTube 的 500 字元上限：含空白的標籤會被加上引號，標籤之間用逗號
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)


def validate(ep: Episode, cfg: Config, description: str, description_en: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not re.fullmatch(r"ep\d{2,3}", ep.id):
        errors.append(f"id 必須像 ep01：{ep.id}")
    if ep.setting not in cfg.character["settings"]:
        errors.append(f"setting `{ep.setting}` 不在 channel/character.yaml 的 settings 裡")

    if not ep.shots:
        errors.append("至少要有一個鏡頭")
    ids = [s.id for s in ep.shots]
    if len(ids) != len(set(ids)):
        errors.append("鏡頭 id 重複")
    for s in ep.shots:
        if s.beat not in BEATS:
            errors.append(f"{s.id}: beat 必須是 {sorted(BEATS)} 其中之一")
        if not 1 <= s.duration <= 15:
            errors.append(f"{s.id}: duration 要在 1–15 秒之間")
        if not s.prompt.strip():
            errors.append(f"{s.id}: 缺少 prompt")
    if ep.duration > SHORTS_MAX_SECONDS:
        errors.append(f"總長 {ep.duration:g}s 超過 Shorts 上限 {SHORTS_MAX_SECONDS}s")
    elif ep.duration > SOFT_MAX_SECONDS:
        warnings.append(f"總長 {ep.duration:g}s，超過頻道建議的 60 秒")

    yt = ep.youtube
    for key in ("title", "title_en"):
        title = yt.get(key, "")
        if not title:
            errors.append(f"youtube.{key} 是空的")
        elif len(title) > 100:
            errors.append(f"youtube.{key} 超過 100 字元（{len(title)}）")
    for label, text in (("description", description), ("description_en", description_en)):
        if len(text.encode("utf-8")) > 5000:
            errors.append(f"{label} 超過 5000 bytes")
    for label, text in (("title", yt.get("title", "")), ("title_en", yt.get("title_en", "")),
                        ("description", description), ("description_en", description_en)):
        if "<" in text or ">" in text:
            errors.append(f"{label} 不能包含 < 或 >（YouTube 會拒絕）")
    tags = yt.get("tags", [])
    if tags_length(tags) > 500:
        errors.append(f"tags 總長 {tags_length(tags)} 超過 500 字元")

    haystack = " ".join([yt.get("title", ""), yt.get("title_en", ""), description, description_en, *tags]).lower()
    for term in BANNED_TERMS:
        if term in haystack:
            errors.append(f"metadata 出現禁用字「{term}」")

    if ep.publish_at is None:
        warnings.append("還沒排發布時間（publish_at）")
    return errors, warnings
