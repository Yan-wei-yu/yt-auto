from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import metadata, prompts, video, youtube
from .config import load_config
from .episode import find_episode, load_episodes, validate


def _check(ep, cfg) -> bool:
    errors, warnings = validate(ep, cfg, metadata.description(ep, cfg, "zh"), metadata.description(ep, cfg, "en"))
    for w in warnings:
        print(f"  ⚠ {ep.id}: {w}")
    for e in errors:
        print(f"  ✗ {ep.id}: {e}")
    return not errors


def cmd_list(args, cfg) -> int:
    done = youtube.uploaded(cfg)
    print(f"{'集數':<6}{'發布時間':<18}{'秒數':>5}  {'片段':<6}{'成片':<4}{'上傳':<4}標題")
    for ep in load_episodes(cfg):
        folder = cfg.path("media") / ep.id
        clips = sum(1 for s in ep.shots if video.find_clip(folder, s.id))
        built = (cfg.path("build") / ep.id / f"{ep.id}.mp4").exists()
        when = ep.publish_at.strftime("%Y-%m-%d %a %H:%M") if ep.publish_at else "—"
        print(f"{ep.id:<6}{when:<18}{ep.duration:>5g}  {clips}/{len(ep.shots):<4}{'✓' if built else '·':<4}"
              f"{'✓' if ep.id in done else '·':<4}{ep.title}")
    return 0


def cmd_validate(args, cfg) -> int:
    eps = [find_episode(cfg, r) for r in args.episodes] if args.episodes else load_episodes(cfg)
    ok = all([_check(ep, cfg) for ep in eps])
    print("全部通過 ✓" if ok else "有錯誤，請修正上面標 ✗ 的項目")
    return 0 if ok else 1


def cmd_prompts(args, cfg) -> int:
    eps = load_episodes(cfg) if args.episode == "all" else [find_episode(cfg, args.episode)]
    for ep in eps:
        out = cfg.path("build") / ep.id / "prompts.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompts.prompt_sheet(ep, cfg), encoding="utf-8")
        (cfg.path("media") / ep.id).mkdir(parents=True, exist_ok=True)
        print(f"✓ {out.relative_to(cfg.root)}")
    return 0


def cmd_build(args, cfg) -> int:
    ep = find_episode(cfg, args.episode)
    if not _check(ep, cfg):
        return 1
    out = video.build_episode(ep, cfg, placeholder=args.placeholder, music=Path(args.music) if args.music else None)
    sheet = out.parent / "upload.md"
    sheet.write_text(metadata.upload_sheet(ep, cfg, str(out.relative_to(cfg.root))), encoding="utf-8")
    print(f"✓ 影片：{out.relative_to(cfg.root)}")
    print(f"✓ 上傳清單：{sheet.relative_to(cfg.root)}")
    return 0


def cmd_compile(args, cfg) -> int:
    eps = [find_episode(cfg, r) for r in args.episodes]
    items = []
    for ep in eps:
        path = cfg.path("build") / ep.id / f"{ep.id}.mp4"
        if not path.exists():
            raise SystemExit(f"{ep.id} 還沒有成片，先執行 build {ep.id}")
        items.append((f"{ep.dish}｜{ep.title}", path))
    out = cfg.path("build") / "compilations" / f"{args.name}.mp4"
    entries = video.compile_videos(items, out, cfg)
    notes = out.with_suffix(".md")
    notes.write_text(f"# {args.name}\n\n貼到說明欄的章節：\n\n```\n{metadata.chapters(entries)}\n```\n", encoding="utf-8")
    print(f"✓ 合集：{out.relative_to(cfg.root)}")
    print(f"✓ 章節：{notes.relative_to(cfg.root)}")
    return 0


def cmd_upload(args, cfg) -> int:
    ep = find_episode(cfg, args.episode)
    if not _check(ep, cfg):
        return 1
    body = youtube.upload_body(ep, cfg)
    if args.dry_run:
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return 0
    path = cfg.path("build") / ep.id / f"{ep.id}.mp4"
    if not path.exists():
        raise SystemExit(f"找不到成片 {path}，先執行 build {ep.id}")
    video_id = youtube.upload(ep, path, cfg)
    print(f"✓ 已上傳 https://youtu.be/{video_id}")
    if "publishAt" in body["status"]:
        print(f"  排程公開：{ep.publish_at:%Y-%m-%d %H:%M}")
    print("  提醒：API 專案還沒通過 YouTube 審核前，上傳的影片會被鎖在「私人」。")
    return 0


def cmd_stats(args, cfg) -> int:
    report = youtube.channel_report(cfg)
    out = cfg.path("reports") / f"{datetime.now():%Y-%m-%d}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"✓ 已存到 {out.relative_to(cfg.root)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yt_auto", description="LittleFire 小火：Shorts 產線")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出所有集數和製作進度").set_defaults(func=cmd_list)

    p = sub.add_parser("validate", help="檢查腳本和 metadata")
    p.add_argument("episodes", nargs="*")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("prompts", help="輸出某一集（或 all）的逐鏡頭 AI 影片 prompt")
    p.add_argument("episode")
    p.set_defaults(func=cmd_prompts)

    p = sub.add_parser("build", help="把片段剪成 9:16 成片＋字幕＋配樂，並輸出上傳清單")
    p.add_argument("episode")
    p.add_argument("--placeholder", action="store_true", help="缺片段時用色塊代替，先看節奏")
    p.add_argument("--music", help="配樂檔（覆蓋腳本裡的 music.file）")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("compile", help="把多支 Shorts 接成 16:9 長影片合集")
    p.add_argument("episodes", nargs="+")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("upload", help="用 YouTube API 上傳並排程")
    p.add_argument("episode")
    p.add_argument("--dry-run", action="store_true", help="只印出要送出的 metadata")
    p.set_defaults(func=cmd_upload)

    sub.add_parser("stats", help="產生頻道週報（需要 YOUTUBE_API_KEY）").set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args, load_config())


if __name__ == "__main__":
    sys.exit(main())
