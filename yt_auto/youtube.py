from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .episode import Episode
from .metadata import description, publish_at_utc

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]

# 現行 YPP 門檻（2027/2/1 起新申請者改為 8,000 小時或 2,000 萬次 Shorts 觀看）
YPP_FAN_FUNDING = {"subs": 500, "shorts_views_90d": 3_000_000}
YPP_ADS_2027 = {"subs": 1000, "shorts_views_90d": 20_000_000}


def _google():
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise SystemExit("缺少套件，請先執行：pip install -r requirements.txt")
    return build, MediaFileUpload


def upload_body(ep: Episode, cfg: Config) -> dict:
    yt, ycfg = ep.youtube, cfg.youtube
    status = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": ycfg["made_for_kids"],
        "containsSyntheticMedia": ycfg["contains_synthetic_media"],
        "license": ycfg["license"],
        "embeddable": True,
    }
    publish = publish_at_utc(ep)
    if publish and ep.publish_at > datetime.now(timezone.utc):
        # 排程發布：必須先設成 private，時間到 YouTube 會自動公開
        status["publishAt"] = publish
    return {
        "snippet": {
            "title": yt["title"],
            "description": description(ep, cfg, "zh"),
            "tags": yt.get("tags", []),
            "categoryId": ycfg["category_id"],
            "defaultLanguage": cfg.channel["default_language"],
        },
        "localizations": {
            "en": {"title": yt["title_en"], "description": description(ep, cfg, "en")},
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


def upload(ep: Episode, video: Path, cfg: Config) -> str:
    build, MediaFileUpload = _google()
    done = uploaded(cfg)
    if ep.id in done:
        raise SystemExit(f"{ep.id} 已經上傳過：https://youtu.be/{done[ep.id]['video_id']}")
    service = build("youtube", "v3", credentials=credentials(cfg))
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = service.videos().insert(part="snippet,status,localizations", body=upload_body(ep, cfg), media_body=media)
    response = None
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(f"  上傳中 {int(progress.progress() * 100)}%")
    video_id = response["id"]
    done[ep.id] = {"video_id": video_id, "uploaded_at": datetime.now(timezone.utc).isoformat(), "publish_at": publish_at_utc(ep)}
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
        f"- 近 90 天發布的影片累計觀看：{recent_views:,}（YouTube 的 90 天 Shorts 觀看數只能在 Studio 看到，這是近似值）",
        "",
        "## YPP 進度",
        f"- 粉絲贊助層（500 訂閱 + 90 天 300 萬 Shorts 觀看）：訂閱 {pct(subs, YPP_FAN_FUNDING['subs'])}、觀看 {pct(recent_views, YPP_FAN_FUNDING['shorts_views_90d'])}",
        f"- 廣告分潤（2027/2/1 後新門檻：1,000 訂閱 + 90 天 2,000 萬 Shorts 觀看）：訂閱 {pct(subs, YPP_ADS_2027['subs'])}、觀看 {pct(recent_views, YPP_ADS_2027['shorts_views_90d'])}",
        "",
        "## 影片",
        "| 發布 | 標題 | 觀看 | 讚 | 留言 |",
        "|---|---|---:|---:|---:|",
        *rows,
        "",
        "## 本週檢討（自己填）",
        "- 哪一支的「觀看 vs. 滑走」最好？為什麼？（YouTube Studio → 數據分析 → 觸及率）",
        "- 哪一支平均觀看百分比最高？開頭 1 秒做了什麼？",
        "- 下週要改的一件事：",
        "",
    ])
