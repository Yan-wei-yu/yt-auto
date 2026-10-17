from __future__ import annotations

from datetime import timezone

from .config import Config
from .episode import Episode


def _hashtags(tags: list[str]) -> str:
    return " ".join(f"#{t.lstrip('#')}" for t in tags)


def description(ep: Episode, cfg: Config, lang: str = "zh") -> str:
    yt = ep.youtube
    if lang == "zh":
        parts = [yt.get("description", ""), cfg.youtube["description_footer"], _hashtags(yt.get("hashtags", []))]
    else:
        parts = [yt.get("description_en", ""), cfg.youtube["description_footer_en"], _hashtags(yt.get("hashtags_en", []))]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def publish_at_utc(ep: Episode) -> str | None:
    if ep.publish_at is None:
        return None
    return ep.publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def timestamp(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def chapters(entries: list[tuple[str, float]]) -> str:
    # YouTube 章節規則：第一個要是 00:00、至少 3 段、每段至少 10 秒
    return "\n".join(f"{timestamp(start)} {title}" for title, start in entries)


def upload_sheet(ep: Episode, cfg: Config, video_file: str) -> str:
    """手動上傳用的複製貼上清單（API 專案還沒通過審核前，用這份在 YouTube Studio 上傳）。"""
    yt = ep.youtube
    when = ep.publish_at.strftime("%Y-%m-%d %H:%M") + f"（{cfg.channel['timezone']}）" if ep.publish_at else "未排程"
    kids = "是，為兒童打造" if cfg.youtube["made_for_kids"] else "否，不是為兒童打造"
    synthetic = "是" if cfg.youtube["contains_synthetic_media"] else "否（明顯是卡通，不需要揭露）"
    return f"""# {ep.id} 上傳清單：{ep.title}

影片檔：`{video_file}`
長度：約 {ep.duration:g} 秒（9:16 直式，會自動歸類為 Shorts）

## 標題
```
{yt['title']}
```

## 說明
```
{description(ep, cfg, 'zh')}
```

## 標籤（貼到「顯示更多 → 標籤」）
```
{', '.join(yt.get('tags', []))}
```

## 英文翻譯（「語言」→ 新增語言 → 英文）
標題：
```
{yt['title_en']}
```
說明：
```
{description(ep, cfg, 'en')}
```

## 設定
- 觀眾：{kids}
- 經過修改或合成的內容：{synthetic}
- 類別：電影與動畫
- 影片語言：不需要（沒有對白）
- 瀏覽權限：排定時間 → {when}
- 播放清單：阿炭的小火廚房
"""
