from __future__ import annotations

from .config import Config
from .episode import Episode, Shot


def shot_prompt(shot: Shot, ep: Episode, cfg: Config) -> str:
    p = cfg.character["prompt"]
    parts = [
        p["style"],
        p["character"],
        f"Setting: {cfg.character['settings'][ep.setting]}",
        f"Camera: {shot.camera}" if shot.camera else "",
        f"Action: {shot.prompt}",
        f"Duration: about {shot.duration:g} seconds",
        p["format"],
    ]
    return ". ".join(" ".join(x.split()).rstrip(".") for x in parts if x) + "."


def prompt_sheet(ep: Episode, cfg: Config) -> str:
    p = cfg.character["prompt"]
    media = cfg.data["paths"]["media"]
    lines = [
        f"# {ep.id} {ep.title}（{ep.title_en}）",
        "",
        f"> {ep.logline}",
        "",
        f"總長約 {ep.duration:g} 秒，{len(ep.shots)} 個鏡頭。音樂：{ep.music}",
        "",
        "## 生成步驟",
        f"1. 在 AI 影片工具選 **9:16**、image-to-video（或「角色參考 / reference」功能），上傳定裝照 `{media}/reference/a-tan.png`。",
        "2. 逐鏡頭貼上下面的英文 prompt；工具有「負面提示」欄位的話，貼上負面提示。",
        f"3. 每個鏡頭挑最好的一版，存成 `{media}/{ep.id}/<鏡頭 id>.mp4`（例如 `{media}/{ep.id}/s01.mp4`）。",
        f"4. 全部放好後執行 `python -m yt_auto build {ep.id}`。",
        "",
        "負面提示（通用）：",
        "```",
        " ".join(p["negative"].split()),
        "```",
        "",
    ]
    for s in ep.shots:
        lines += [
            f"## {s.id}｜{s.beat}｜{s.duration:g} 秒",
            f"- 畫面：{s.action}",
            f"- 音效：{s.sfx or '—'}",
            f"- 字幕：{s.caption or '—'}" + (f" / {s.caption_en}" if s.caption_en else ""),
            f"- 存檔：`{media}/{ep.id}/{s.id}.mp4`",
            "",
            "```",
            shot_prompt(s, ep, cfg),
            "```",
            "",
        ]
    return "\n".join(lines)
