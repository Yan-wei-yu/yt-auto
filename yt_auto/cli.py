from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import market, metadata, slides, video, youtube
from .config import load_config
from .voice import recording
from .week import find_week, load_weeks, validate

TEMPLATE = Path(__file__).with_name("template.yaml")


def _check(week, cfg) -> bool:
    descriptions = [metadata.long_description(week, cfg)] + [metadata.short_description(s, week, cfg) for s in week.shorts]
    errors, warnings = validate(week, cfg, descriptions)
    for w in warnings:
        print(f"  ⚠ {week.id}: {w}")
    for e in errors:
        print(f"  ✗ {week.id}: {e}")
    return not errors


def _rel(p: Path, cfg) -> str:
    return str(p.relative_to(cfg.root))


def cmd_list(args, cfg) -> int:
    done = youtube.uploaded(cfg)
    print(f"{'週次':<10}{'發布時間':<20}{'段落':>4}  {'錄音':<6}{'成片':<4}{'上傳':<4}標題")
    for w in load_weeks(cfg):
        recs = sum(1 for s in w.segments if recording(w, s))
        built = (cfg.path("build") / w.id / f"{w.id}.mp4").exists()
        when = w.publish_at.strftime("%Y-%m-%d %a %H:%M") if w.publish_at else "—"
        print(f"{w.id:<10}{when:<20}{len(w.segments):>4}  {recs}/{len(w.segments):<4}{'✓' if built else '·':<4}"
              f"{'✓' if w.id in done else '·':<4}{w.title}")
    return 0


def cmd_new(args, cfg) -> int:
    folder = cfg.path("weeks") / args.week
    if (folder / "episode.yaml").exists():
        raise SystemExit(f"{folder} 已經存在")
    monday, friday = market.week_dates(args.week)
    folder.mkdir(parents=True)
    text = TEMPLATE.read_text(encoding="utf-8").replace("{id}", args.week).replace(
        "{label}", f"{monday:%m/%d}–{friday:%m/%d}")
    (folder / "episode.yaml").write_text(text, encoding="utf-8")
    print(f"✓ {_rel(folder / 'episode.yaml', cfg)}，接著跑 `python -m yt_auto fetch {args.week}`")
    return 0


def cmd_fetch(args, cfg) -> int:
    week = find_week(cfg, args.week)
    result = market.fetch(week.id, cfg, week.dir / "market.json")
    for row in result["indices"] + result["stocks"]:
        print(f"  {row['name']:<10}{row['change_pct']:+7.2f}%")
    print(f"✓ {_rel(week.dir / 'market.json', cfg)}（{result['base_date']} → {result['as_of']}）")
    return 0


def cmd_validate(args, cfg) -> int:
    weeks = [find_week(cfg, args.week)] if args.week else load_weeks(cfg)
    ok = all([_check(w, cfg) for w in weeks])
    print("全部通過 ✓" if ok else "有錯誤，請修正上面標 ✗ 的項目")
    return 0 if ok else 1


def cmd_slides(args, cfg) -> int:
    week = find_week(cfg, args.week)
    if not _check(week, cfg):
        return 1
    out = cfg.path("build") / week.id / "slides"
    for seg in week.segments:
        slides.render_segment(seg, week, cfg, out / "long" / f"{seg.id}.png")
    for seg_id in {i for s in week.shorts for i in s.segments}:
        slides.render_segment(week.segment(seg_id), week, cfg, out / "short" / f"{seg_id}.png", portrait=True)
    slides.render_thumbnail(week, cfg, cfg.path("build") / week.id / "thumbnail.png")
    print(f"✓ 投影片：{_rel(out, cfg)}/")
    return 0


def cmd_build(args, cfg) -> int:
    week = find_week(cfg, args.week)
    if not _check(week, cfg):
        return 1
    out_dir = cfg.path("build") / week.id
    music = Path(args.music) if args.music else None
    use_tts = not args.no_tts

    parts = video.plan_parts(week, cfg, portrait=False, use_tts=use_tts)
    sources = {p.voice.source for p in parts}
    long_path = out_dir / f"{week.id}.mp4"
    chapters = video.assemble(parts, long_path, cfg, portrait=False, music=music)
    total = sum(p.duration for p in parts)
    thumb = slides.render_thumbnail(week, cfg, out_dir / "thumbnail.png")
    print(f"✓ 長片：{_rel(long_path, cfg)}（{metadata.timestamp(total)}，配音：{'、'.join(sorted(sources))}）")

    shorts = []
    for short in [] if args.skip_shorts else week.shorts:
        sp = video.plan_parts(week, cfg, portrait=True, use_tts=use_tts, seg_ids=short.segments)
        path = out_dir / "shorts" / f"{short.id}.mp4"
        video.assemble(sp, path, cfg, portrait=True, music=music)
        length = sum(p.duration for p in sp)
        warn = "  ⚠ 超過 60 秒，建議縮短旁白" if length > 60 else ""
        print(f"✓ Short：{_rel(path, cfg)}（{length:.0f} 秒）{warn}")
        shorts.append((short, _rel(path, cfg)))

    (out_dir / "chapters.json").write_text(json.dumps({"chapters": chapters, "total": total}, ensure_ascii=False), encoding="utf-8")
    sheet = out_dir / "upload.md"
    sheet.write_text(metadata.upload_sheet(week, cfg, _rel(long_path, cfg), _rel(thumb, cfg), chapters, total, shorts),
                     encoding="utf-8")
    print(f"✓ 上傳清單：{_rel(sheet, cfg)}")
    if "silent" in sources:
        print("  提醒：有段落沒有錄音也沒有 TTS，影片是靜音的（只用來預覽節奏）")
    return 0


def cmd_upload(args, cfg) -> int:
    week = find_week(cfg, args.week)
    if not _check(week, cfg):
        return 1
    out_dir = cfg.path("build") / week.id
    info_file = out_dir / "chapters.json"
    info = json.loads(info_file.read_text(encoding="utf-8")) if info_file.exists() else {"chapters": [], "total": None}
    jobs = []
    if args.only in (None, "long"):
        body = youtube.upload_body(week.youtube["title"], metadata.long_description(week, cfg, info["chapters"], info["total"]),
                                   week.youtube.get("tags", []), week.publish_at, cfg)
        jobs.append((week.id, out_dir / f"{week.id}.mp4", body, out_dir / "thumbnail.png"))
    for short in week.shorts:
        if args.only in (None, short.id):
            body = youtube.upload_body(short.title, metadata.short_description(short, week, cfg),
                                       short.tags or week.youtube.get("tags", []), short.publish_at, cfg)
            jobs.append((f"{week.id}/{short.id}", out_dir / "shorts" / f"{short.id}.mp4", body, None))
    for key, path, body, thumb in jobs:
        if args.dry_run:
            print(f"--- {key}")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            continue
        if not path.exists():
            raise SystemExit(f"找不到 {path}，先執行 build {week.id}")
        video_id = youtube.upload(key, path, body, cfg, thumb)
        print(f"✓ {key} 已上傳 https://youtu.be/{video_id}")
    if not args.dry_run:
        print("  提醒：API 專案還沒通過 YouTube 審核前，上傳的影片會被鎖在「私人」。")
    return 0


def cmd_cast(args, cfg) -> int:
    """把角色庫全部畫成一張總表，方便確認造型（新增角色後跑一次）。"""
    import matplotlib.pyplot as plt

    from .cartoon import draw_stage, load_cast

    slides.setup_fonts(cfg)
    cast = load_cast(cfg.path("cast"))
    keys = list(cast)
    cols = 4
    rows = (len(keys) + cols - 1) // cols
    fig = plt.figure(figsize=(19.2, 4.2 * rows), dpi=100)
    fig.patch.set_facecolor(slides.NAVY)
    for i, key in enumerate(keys):
        r, c = divmod(i, cols)
        ax = fig.add_axes((0.01 + c * 0.2475, 1 - (r + 1) / rows + 0.01 / rows, 0.2375, 0.98 / rows))
        draw_stage(ax, cast, [{"who": key, "mood": "happy" if i % 2 else "neutral"}], 0.2375 * 1920, 0.98 / rows * 420 * rows)
        ax.text(0.04, 0.96, key, transform=ax.transAxes, va="top", color=slides.MUTED, fontsize=16)
    out = Path(args.out) if args.out else cfg.path("build") / "cast_sheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=slides.NAVY)
    plt.close(fig)
    print(f"✓ 角色總表：{out}")
    return 0


def cmd_branding(args, cfg) -> int:
    from . import branding

    folder = cfg.path("branding")
    avatar = branding.render_avatar(cfg, folder / "avatar.png")
    banner = branding.render_banner(cfg, folder / "banner.png")
    preview = branding.render_preview(banner, avatar, cfg.path("build") / "branding_preview.png",
                                      cfg.channel["name"], args.handle)
    print(f"✓ 頭像：{_rel(avatar, cfg)}（800×800）")
    print(f"✓ 橫幅：{_rel(banner, cfg)}（2560×1440）")
    print(f"✓ 預覽：{_rel(preview, cfg)}")
    return 0


def cmd_tts_setup(args, cfg) -> int:
    from .voice import setup_kokoro

    folder = setup_kokoro(cfg)
    print(f"✓ 配音模型：{folder}")
    return 0


def cmd_voices(args, cfg) -> int:
    from .voice import google_voices

    for v in google_voices(cfg, args.language):
        gender = {"FEMALE": "女", "MALE": "男"}.get(v.get("ssmlGender"), "")
        print(f"{v['name']:<32}{gender}")
    return 0


def cmd_stats(args, cfg) -> int:
    report = youtube.channel_report(cfg)
    out = cfg.path("reports") / f"{datetime.now():%Y-%m-%d}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"✓ 已存到 {_rel(out, cfg)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yt_auto", description="韭菜週報：每週美股週報產線")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出每一週的製作進度").set_defaults(func=cmd_list)

    p = sub.add_parser("new", help="建立新的一週，例如 new 2026-w43")
    p.add_argument("week")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("fetch", help="用 Yahoo Finance 抓本週行情寫進 market.json")
    p.add_argument("week", nargs="?", default="latest")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("validate", help="檢查腳本（格式、長度、禁用說法）")
    p.add_argument("week", nargs="?")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("slides", help="只畫投影片和縮圖，先看畫面")
    p.add_argument("week", nargs="?", default="latest")
    p.set_defaults(func=cmd_slides)

    p = sub.add_parser("build", help="剪出長片＋Shorts＋縮圖＋上傳清單")
    p.add_argument("week", nargs="?", default="latest")
    p.add_argument("--no-tts", action="store_true", help="不用 AI 配音，沒錄音的段落用靜音預覽")
    p.add_argument("--music", help="背景音樂檔")
    p.add_argument("--skip-shorts", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("upload", help="用 YouTube API 上傳並排程")
    p.add_argument("week", nargs="?", default="latest")
    p.add_argument("--only", help="只傳 long 或某支 short 的 id")
    p.add_argument("--dry-run", action="store_true", help="只印出要送出的 metadata")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("cast", help="把 channel/cast.yaml 的角色畫成總表")
    p.add_argument("--out")
    p.set_defaults(func=cmd_cast)

    p = sub.add_parser("branding", help="產生頻道頭像、橫幅和頻道頁預覽")
    p.add_argument("--handle", default="@LeekWeekly", help="預覽圖上顯示的 handle")
    p.set_defaults(func=cmd_branding)

    sub.add_parser("tts-setup", help="下載 AI 配音模型（Kokoro，約 330 MB，只要一次）").set_defaults(func=cmd_tts_setup)

    p = sub.add_parser("voices", help="列出 Google 台灣華語的可用聲音（需要金鑰）")
    p.add_argument("--language", default="cmn-TW")
    p.set_defaults(func=cmd_voices)

    sub.add_parser("stats", help="產生頻道週報（需要 YOUTUBE_API_KEY）").set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args, load_config())


if __name__ == "__main__":
    sys.exit(main())
