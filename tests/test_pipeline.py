import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from yt_auto import metadata, video, youtube
from yt_auto.config import ROOT, load_config
from yt_auto.market import week_dates
from yt_auto.subtitles import ass_escape, ass_time, chunk, timed_cues
from yt_auto.week import load_week, load_weeks, tags_length, validate

has_ffmpeg = shutil.which("ffmpeg") is not None


def check(week, cfg):
    descriptions = [metadata.long_description(week, cfg)] + [metadata.short_description(s, week, cfg) for s in week.shorts]
    return validate(week, cfg, descriptions)


def test_all_weeks_valid():
    cfg = load_config()
    weeks = load_weeks(cfg)
    assert weeks
    for w in weeks:
        errors, _ = check(w, cfg)
        assert errors == [], (w.id, errors)


def test_week_dates():
    assert week_dates("2026-w42") == (date(2026, 10, 12), date(2026, 10, 16))


def test_validation_rules():
    cfg = load_config()
    week = load_weeks(cfg)[0]
    concept = next(s for s in week.segments if s.type == "concept")
    concept.narration = "這檔一定會漲，目標價一百"
    topic = next(s for s in week.segments if s.type == "topic")
    topic.fields["chart"] = "NOPE"
    # 真實人物的對話框沒標 quote: true（不是真實引述）要擋下來
    topic.fields["cast"] = [{"who": "warsh", "mood": "laugh", "say": "我要升息啦"}, {"who": "nobody"}]
    errors, warnings = check(week, cfg)
    assert any("虛構" in e for e in errors)
    assert any("NOPE" in e for e in errors)
    assert any("真實引述" in e for e in errors)
    assert any("nobody" in e for e in errors)
    assert any("目標價" in w for w in warnings)
    assert tags_length(["a b", "cd"]) == 3 + 2 + 2 + 1


def test_subtitles():
    assert ass_time(65.5) == "0:01:05.50"
    assert ass_escape("a{b}\nc") == "a(b)\\Nc"
    lines = chunk("大家好，我是阿韭。這週美股，那斯達克一週跌了四點四八趴，是六月以來最慘的一週。", 14)
    assert all(len(x) <= 14 for x in lines)
    assert not any(x.endswith(("，", "。")) for x in lines)
    cues = timed_cues("一二三，四五六七八九。", 10, 6)
    assert cues[0].start == 10 and cues[-1].end == pytest.approx(16)


def test_chapters():
    entries = [("a", 0), ("b", 20), ("c", 25), ("d", 60)]
    # b 只有 5 秒（20→25），不滿 10 秒的章節會被併進前一段
    assert metadata.chapters_text(entries, 90) == "00:00 a\n00:25 c\n01:00 d"
    assert metadata.chapters_text([("a", 0), ("b", 30)], 60) == ""


def test_upload_body():
    cfg = load_config()
    future = datetime.now(timezone.utc) + timedelta(days=2)
    body = youtube.upload_body("t", "d", ["x"], future, cfg)
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"].endswith("Z")
    assert body["status"]["selfDeclaredMadeForKids"] is False
    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert "publishAt" not in youtube.upload_body("t", "d", [], past, cfg)["status"]


@pytest.fixture
def small_root(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "channel", tmp_path / "channel")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["video"].update(width=480, height=270, short_width=270, short_height=480, fps=10)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    src = ROOT / "weeks" / "2026-w42"
    dst = tmp_path / "weeks" / "2026-w42"
    dst.mkdir(parents=True)
    shutil.copy(src / "market.json", dst)
    ep = yaml.safe_load((src / "episode.yaml").read_text(encoding="utf-8"))
    keep = {"s01", "s04", "s08"}
    ep["segments"] = [s for s in ep["segments"] if s["id"] in keep]
    for s in ep["segments"]:
        s["narration"] = s["narration"][:30] + "（虛構）"
    ep["shorts"] = [sh for sh in ep["shorts"] if sh["segments"] == ["s08"]]
    (dst / "episode.yaml").write_text(yaml.safe_dump(ep, allow_unicode=True), encoding="utf-8")
    # s01 用「錄音」，其他段落用靜音估長度
    (dst / "voice").mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=2.5", str(dst / "voice" / "s01.wav")], check=True)
    return tmp_path


@pytest.mark.skipif(not has_ffmpeg, reason="需要 ffmpeg")
def test_build(small_root: Path):
    cfg = load_config(small_root)
    week = load_week(small_root / "weeks" / "2026-w42", cfg)
    assert check(week, cfg)[0] == []

    parts = video.plan_parts(week, cfg, portrait=False, use_tts=False)
    assert [p.voice.source for p in parts] == ["recording", "silent", "silent"]
    assert parts[0].speech == pytest.approx(2.5, abs=0.05)
    out = small_root / "build" / "long.mp4"
    chapters = video.assemble(parts, out, cfg, portrait=False)
    assert [c for c, _ in chapters] == [s.chapter for s in week.segments if s.chapter]
    assert video.probe_duration(out) == pytest.approx(sum(p.duration for p in parts), abs=0.3)

    sp = video.plan_parts(week, cfg, portrait=True, use_tts=False, seg_ids=week.shorts[0].segments)
    short = small_root / "build" / "short.mp4"
    video.assemble(sp, short, cfg, portrait=True)
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(short)], capture_output=True, text=True, check=True).stdout.strip()
    assert info == "270,480"
