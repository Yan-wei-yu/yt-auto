from __future__ import annotations

from datetime import datetime, timezone

from .config import Config
from .week import Short, Week


def _hashtags(tags: list[str]) -> str:
    return " ".join(f"#{t.lstrip('#')}" for t in tags)


def timestamp(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def chapters_text(entries: list[tuple[str, float]], total: float | None = None) -> str:
    """YouTube 章節：第一個 00:00、至少 3 段、每段至少 10 秒，不符合的段落併進前一段。"""
    kept: list[tuple[str, float]] = []
    for i, (title, start) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else total
        if kept and end is not None and end - start < 10:
            continue
        kept.append((title, start))
    if len(kept) < 3:
        return ""
    return "\n".join(f"{timestamp(start)} {title}" for title, start in kept)


def long_description(week: Week, cfg: Config, chapters: list[tuple[str, float]] | None = None,
                     total: float | None = None) -> str:
    yt = week.youtube
    parts = [yt.get("description", "")]
    chap = chapters_text(chapters or [], total)
    if chap:
        parts.append("📌 章節\n" + chap)
    parts += [cfg.youtube["description_footer"], _hashtags(yt.get("hashtags", []))]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def short_description(short: Short, week: Week, cfg: Config) -> str:
    parts = [short.description, f"完整的一週美股整理：頻道裡的「{week.title}」", cfg.youtube["description_footer"],
             _hashtags(week.youtube.get("hashtags", [])[:3])]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def publish_at_utc(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _when(dt: datetime | None, cfg: Config) -> str:
    return dt.strftime("%Y-%m-%d（%a）%H:%M") + f"（{cfg.channel['timezone']}）" if dt else "未排程"


def upload_sheet(week: Week, cfg: Config, video: str, thumbnail: str | None, chapters, total,
                 shorts: list[tuple[Short, str]]) -> str:
    """手動上傳用的複製貼上清單（API 專案還沒通過 YouTube 審核前，用這份在 Studio 上傳）。"""
    yt = week.youtube
    out = [f"# {week.id} 上傳清單：{week.title}", "",
           "## 長片", "",
           f"- 影片檔：`{video}`（約 {timestamp(total)}）",
           f"- 縮圖：`{thumbnail}`" if thumbnail else "- 縮圖：無",
           f"- 排程：{_when(week.publish_at, cfg)}",
           "- 觀眾：否，不是為兒童打造｜經過修改或合成的內容：否｜類別：教育",
           "", "標題：", "```", yt["title"], "```",
           "說明：", "```", long_description(week, cfg, chapters, total), "```",
           "標籤（顯示更多 → 標籤）：", "```", ", ".join(yt.get("tags", [])), "```", ""]
    for short, path in shorts:
        out += [f"## Short：{short.id}", "",
                f"- 影片檔：`{path}`",
                f"- 排程：{_when(short.publish_at, cfg)}",
                "- 上傳後在「相關影片」選這週的長片，觀眾可以從 Short 點進長片", "",
                "標題：", "```", short.title, "```",
                "說明：", "```", short_description(short, week, cfg), "```", ""]
    return "\n".join(out)
