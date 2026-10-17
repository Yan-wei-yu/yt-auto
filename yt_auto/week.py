from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from .cartoon import ARMS, HOLDING, MOODS, load_cast
from .config import Config

SEGMENT_TYPES = {"title", "indices", "topic", "movers", "concept", "calendar", "outro"}
SHORTS_MAX_SECONDS = 180

# 在台灣沒有投顧執照公開推薦個股可能違法；旁白出現這些字只警告，因為引述新聞時可能合理出現
ADVICE_PHRASES = [
    "建議買", "建議賣", "可以買", "可以進場", "快買", "快賣", "趕快買", "目標價", "必漲", "穩賺",
    "保證獲利", "明牌", "抄底", "梭哈", "all in", "進場點", "停損點", "加碼",
]


@dataclass
class Segment:
    id: str
    type: str
    narration: str
    chapter: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)


@dataclass
class Short:
    id: str
    segments: list[str]
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    publish_at: datetime | None = None


@dataclass
class Week:
    id: str
    label: str
    title: str
    publish_at: datetime | None
    youtube: dict[str, Any]
    thumbnail: dict[str, Any]
    segments: list[Segment]
    shorts: list[Short]
    market: dict[str, Any]
    dir: Path

    def segment(self, seg_id: str) -> Segment:
        for s in self.segments:
            if s.id == seg_id:
                return s
        raise KeyError(seg_id)


def _parse_time(value: Any, tz: ZoneInfo) -> datetime | None:
    if value in (None, ""):
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def load_week(folder: Path, cfg: Config) -> Week:
    raw = yaml.safe_load((folder / "episode.yaml").read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg.channel["timezone"])
    segments = []
    for s in raw["segments"]:
        s = dict(s)
        segments.append(Segment(
            id=s.pop("id"), type=s.pop("type"), narration=" ".join(str(s.pop("narration", "")).split()),
            chapter=s.pop("chapter", None), fields=s,
        ))
    shorts = [
        Short(id=sh["id"], segments=list(sh["segments"]), title=sh["title"], description=sh.get("description", ""),
              tags=sh.get("tags", []), publish_at=_parse_time(sh.get("publish_at"), tz))
        for sh in raw.get("shorts", [])
    ]
    market_file = folder / "market.json"
    market = json.loads(market_file.read_text(encoding="utf-8")) if market_file.exists() else {}
    return Week(
        id=raw["id"], label=raw["label"], title=raw["title"], publish_at=_parse_time(raw.get("publish_at"), tz),
        youtube=raw["youtube"], thumbnail=raw.get("thumbnail", {}), segments=segments, shorts=shorts,
        market=market, dir=folder,
    )


def load_weeks(cfg: Config) -> list[Week]:
    folders = sorted(p.parent for p in cfg.path("weeks").glob("*/episode.yaml"))
    return [load_week(f, cfg) for f in folders]


def find_week(cfg: Config, ref: str | None) -> Week:
    weeks = load_weeks(cfg)
    if not weeks:
        raise SystemExit("weeks/ 裡還沒有任何一集")
    if ref in (None, "latest"):
        return weeks[-1]
    for w in weeks:
        if w.id == ref:
            return w
    raise SystemExit(f"找不到 {ref}（可用 `python -m yt_auto list` 查看）")


def tags_length(tags: list[str]) -> int:
    # YouTube 的 500 字元上限：含空白的標籤會被加上引號，標籤之間用逗號
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)


def check_cast(label: str, entries: list[dict], cast: dict, errors: list[str]) -> None:
    for e in entries:
        who = e.get("who")
        if who not in cast:
            errors.append(f"{label}: channel/cast.yaml 裡沒有角色 {who}")
            continue
        if e.get("mood", "neutral") not in MOODS:
            errors.append(f"{label}: mood 必須是 {sorted(MOODS)} 其中之一")
        if e.get("arms", "down") not in ARMS | {"none"}:
            errors.append(f"{label}: arms 必須是 {sorted(ARMS)} 其中之一")
        if e.get("holding") and e["holding"].get("type") not in HOLDING:
            errors.append(f"{label}: holding.type 必須是 {sorted(HOLDING)} 其中之一")
        # 真實人物的對話框只能放他真的說過的話
        if cast[who].get("real") and e.get("say") and not e.get("quote"):
            errors.append(f"{label}: {cast[who]['name']} 是真實人物，對話框只能放真實引述（確認後加 quote: true），玩笑請放旁白")


def validate(week: Week, cfg: Config, descriptions: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    cast = load_cast(cfg.path("cast"))
    check_cast("thumbnail", week.thumbnail.get("cast", []), cast, errors)

    if not re.fullmatch(r"\d{4}-w\d{2}", week.id):
        errors.append(f"id 要像 2026-w42：{week.id}")
    ids = [s.id for s in week.segments]
    if len(ids) != len(set(ids)):
        errors.append("段落 id 重複")
    if week.segments and not week.segments[0].chapter:
        errors.append("第一段要有 chapter（YouTube 章節必須從 00:00 開始）")
    for s in week.segments:
        if s.type not in SEGMENT_TYPES:
            errors.append(f"{s.id}: type 必須是 {sorted(SEGMENT_TYPES)} 其中之一")
        check_cast(s.id, s.get("cast", []), cast, errors)
        if not s.narration:
            errors.append(f"{s.id}: 缺少 narration（旁白）")
        if s.type in ("indices", "movers") and not week.market:
            errors.append(f"{s.id}: 需要 market.json，先跑 `python -m yt_auto fetch {week.id}`")
        if s.type == "topic" and s.get("chart") and s.get("chart") not in {x["symbol"] for x in week.market.get("stocks", [])}:
            errors.append(f"{s.id}: market.json 裡沒有 {s.get('chart')} 的資料")
        if s.type == "concept":
            if not s.get("series") or len(s.get("series")) < 3:
                errors.append(f"{s.id}: 概念股需要 series（至少 3 個點）")
            if "虛構" not in s.narration:
                errors.append(f"{s.id}: 概念股的旁白要講明是「虛構」的，避免觀眾誤會是真的股票")
        lowered = s.narration.lower().replace("不報明牌", "")
        for phrase in ADVICE_PHRASES:
            if phrase.lower() in lowered:
                warnings.append(f"{s.id}: 旁白出現「{phrase}」，確認不是在推薦買賣")

    for sh in week.shorts:
        for seg_id in sh.segments:
            if seg_id not in ids:
                errors.append(f"{sh.id}: 找不到段落 {seg_id}")
        if len(sh.title) > 100:
            errors.append(f"{sh.id}: 標題超過 100 字元")

    yt = week.youtube
    if not 0 < len(yt.get("title", "")) <= 100:
        errors.append("youtube.title 必須是 1–100 字元")
    for text in [yt.get("title", ""), *descriptions]:
        if "<" in text or ">" in text:
            errors.append("標題或說明不能包含 < 或 >（YouTube 會拒絕）")
    for d in descriptions:
        if len(d.encode("utf-8")) > 5000:
            errors.append("說明欄超過 5000 bytes")
    if tags_length(yt.get("tags", [])) > 500:
        errors.append("tags 總長超過 500 字元")
    if week.publish_at is None:
        warnings.append("還沒排發布時間（publish_at）")
    return errors, warnings
