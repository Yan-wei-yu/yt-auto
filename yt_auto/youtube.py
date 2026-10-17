from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .metadata import publish_at_utc

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]

# 2027/2/1 起新申請者的 YPP 門檻：1,000 訂閱＋12 個月 8,000 小時長片觀看（或 90 天 2,000 萬次 Shorts 觀看）
YPP_ADS_2027 = {"subs": 1000, "watch_hours_12m": 8000}


def _google():
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise SystemExit("缺少套件，請先執行：pip install -r requirements.txt")
    return build, MediaFileUpload


def upload_body(title: str, description: str, tags: list[str], publish_at: datetime | None, cfg: Config) -> dict:
    ycfg = cfg.youtube
    status = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": ycfg["made_for_kids"],
        "containsSyntheticMedia": ycfg["contains_synthetic_media"],
        "license": ycfg["license"],
        "embeddable": True,
    }
    if publish_at and publish_at > datetime.now(timezone.utc):
        # 排程發布：必須先設成 private，時間到 YouTube 會自動公開
        status["publishAt"] = publish_at_utc(publish_at)
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": ycfg["category_id"],
            "defaultLanguage": cfg.channel["default_language"],
        },
        "status": status,
    }


def credentials(cfg: Config):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise SystemExit("缺少套件，請先執行：pip install -r requirements.txt")
    secrets = cfg.path("secrets")
    token, client = secrets / "token.json", secrets / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not client.exists():
            raise SystemExit(f"找不到 {client}。請照 README「自動上傳」一節建立 OAuth 用戶端並下載到這個位置。")
        creds = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES).run_local_server(port=0)
    secrets.mkdir(exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _state_file(cfg: Config) -> Path:
    return cfg.path("state") / "uploads.json"


def uploaded(cfg: Config) -> dict:
    f = _state_file(cfg)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def upload(key: str, video: Path, body: dict, cfg: Config, thumbnail: Path | None = None) -> str:
    """上傳一支影片；key 例如 2026-w42 或 2026-w42/short1，用來避免重複上傳。"""
    build, MediaFileUpload = _google()
    done = uploaded(cfg)
    if key in done:
        raise SystemExit(f"{key} 已經上傳過：https://youtu.be/{done[key]['video_id']}")
    service = build("youtube", "v3", credentials=credentials(cfg))
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(f"  上傳中 {int(progress.progress() * 100)}%")
    video_id = response["id"]
    if thumbnail and thumbnail.exists():
        # 自訂縮圖需要頻道已驗證電話
        service.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail), mimetype="image/png")).execute()
    done[key] = {"video_id": video_id, "uploaded_at": datetime.now(timezone.utc).isoformat(),
                 "publish_at": body["status"].get("publishAt")}
    f = _state_file(cfg)
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
    return video_id


def channel_report(cfg: Config, api_key: str | None = None) -> str:
    """用公開資料（只要 API 金鑰，不用登入）產生頻道週報。"""
    build, _ = _google()
    api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit("請設定環境變數 YOUTUBE_API_KEY（Google Cloud Console → 憑證 → API 金鑰）")
    yt = build("youtube", "v3", developerKey=api_key)
    ch = yt.channels().list(part="statistics,contentDetails,snippet", id=cfg.channel["channel_id"]).execute()["items"][0]
    stats = ch["statistics"]
    uploads_playlist = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, token = [], None
    while True:
        page = yt.playlistItems().list(part="contentDetails", playlistId=uploads_playlist, maxResults=50, pageToken=token).execute()
        ids += [it["contentDetails"]["videoId"] for it in page["items"]]
        token = page.get("nextPageToken")
        if not token:
            break
    videos = []
    for i in range(0, len(ids), 50):
        videos += yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()["items"]

    now = datetime.now(timezone.utc)
    recent_views = 0
    rows = []
    for vid in sorted(videos, key=lambda x: x["snippet"]["publishedAt"], reverse=True):
        published = datetime.fromisoformat(vid["snippet"]["publishedAt"].replace("Z", "+00:00"))
        s = vid["statistics"]
        views = int(s.get("viewCount", 0))
        if now - published <= timedelta(days=90):
            recent_views += views
        rows.append(
            f"| {published:%m-%d} | [{vid['snippet']['title'][:40]}](https://youtu.be/{vid['id']}) "
            f"| {views:,} | {int(s.get('likeCount', 0)):,} | {int(s.get('commentCount', 0)):,} |"
        )

    subs = int(stats.get("subscriberCount", 0))
    hidden = " （訂閱數已隱藏）" if stats.get("hiddenSubscriberCount") else ""

    def pct(value: int, target: int) -> str:
        return f"{min(value / target, 1):.1%}"

    return "\n".join([
        f"# 頻道週報 {now.astimezone():%Y-%m-%d}",
        "",
        f"- 訂閱：**{subs:,}**{hidden}",
        f"- 總觀看：{int(stats.get('viewCount', 0)):,}",
        f"- 影片數：{stats.get('videoCount', 0)}",
        f"- 近 90 天發布的影片累計觀看：{recent_views:,}",
        "",
        "## YPP 進度（2027/2/1 起新申請者門檻）",
        f"- 訂閱 {subs:,} / {YPP_ADS_2027['subs']:,}（{pct(subs, YPP_ADS_2027['subs'])}）",
        f"- 長片觀看時數目標 {YPP_ADS_2027['watch_hours_12m']:,} 小時：公開資料看不到，請到 YouTube Studio → 收益 查看",
        "",
        "## 影片",
        "| 發布 | 標題 | 觀看 | 讚 | 留言 |",
        "|---|---|---:|---:|---:|",
        *rows,
        "",
        "## 本週檢討（自己填）",
        "- 長片的平均觀看時間和「觀眾留存」在哪一段掉最多？（Studio → 數據分析 → 參與度）",
        "- 縮圖點閱率（CTR）多少？哪種縮圖文字最有效？",
        "- 哪一支 Short 帶來最多訂閱？",
        "- 下週要改的一件事：",
        "",
    ])
