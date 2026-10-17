import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from yt_auto import metadata, prompts, video, youtube
from yt_auto.config import ROOT, load_config
from yt_auto.episode import load_episode, load_episodes, tags_length, validate
from yt_auto.subtitles import ass_escape, ass_time

has_ffmpeg = shutil.which("ffmpeg") is not None


def check(ep, cfg):
    return validate(ep, cfg, metadata.description(ep, cfg, "zh"), metadata.description(ep, cfg, "en"))


def test_all_episodes_valid():
    cfg = load_config()
    eps = load_episodes(cfg)
    assert len(eps) >= 10
    for ep in eps:
        errors, _ = check(ep, cfg)
        assert errors == [], (ep.id, errors)
    publish = [ep.publish_at for ep in eps]
    assert publish == sorted(publish), "發布時間要跟集數順序一致"
    assert len(set(publish)) == len(publish)


def test_banned_terms_and_lengths():
    cfg = load_config()
    ep = load_episodes(cfg)[0]
    ep.youtube = {**ep.youtube, "title": "小火龍煮滷肉飯", "tags": ["x" * 300, "y" * 300]}
    errors, _ = check(ep, cfg)
    assert any("小火龍" in e for e in errors)
    assert any("tags" in e for e in errors)
    assert tags_length(["a b", "cd"]) == 3 + 2 + 2 + 1


def test_ass_helpers():
    assert ass_time(65.5) == "0:01:05.50"
    assert ass_escape("a{b}\nc") == "a(b)\\Nc"


def test_shot_prompt_includes_character_and_setting():
    cfg = load_config()
    ep = load_episodes(cfg)[0]
    text = prompts.shot_prompt(ep.shots[0], ep, cfg)
    assert "lump of charcoal" in text
    assert "Taiwanese apartment kitchen" in text
    assert "9:16" in text


def test_upload_body():
    cfg = load_config()
    ep = load_episodes(cfg)[0]
    ep.publish_at = datetime.now(timezone.utc) + timedelta(days=3)
    body = youtube.upload_body(ep, cfg)
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"].endswith("Z")
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert body["localizations"]["en"]["title"] == ep.youtube["title_en"]
    ep.publish_at = datetime.now(timezone.utc) - timedelta(days=1)
    assert "publishAt" not in youtube.upload_body(ep, cfg)["status"]


def test_chapters():
    assert metadata.chapters([("a", 0), ("b", 65.2), ("c", 3700)]) == "00:00 a\n01:05 b\n1:01:40 c"


@pytest.fixture
def small_root(tmp_path: Path) -> Path:
    (tmp_path / "channel").mkdir()
    (tmp_path / "episodes").mkdir()
    shutil.copy(ROOT / "channel" / "character.yaml", tmp_path / "channel")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["video"].update(width=270, height=480, fps=10, caption_size=24, caption_en_size=14, caption_margin_bottom=100)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    ep = yaml.safe_load((ROOT / "episodes" / "ep01-lu-rou-fan.yaml").read_text(encoding="utf-8"))
    ep["shots"] = ep["shots"][:3]
    for s in ep["shots"]:
        s["duration"] = 2
    ep["music"]["file"] = "music/test.wav"
    (tmp_path / "episodes" / "ep01-test.yaml").write_text(yaml.safe_dump(ep, allow_unicode=True), encoding="utf-8")
    return tmp_path


def make_clip(path: Path, size: str, seconds: float, audio: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=s={size}:r=24:d={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-shortest"]
    subprocess.run([*args, "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.mark.skipif(not has_ffmpeg, reason="需要 ffmpeg")
def test_build_and_compile(small_root: Path):
    cfg = load_config(small_root)
    media = small_root / "media"
    make_clip(media / "ep01" / "s01.mp4", "640x360", 3, audio=True)   # 橫式、比腳本長、有聲音
    make_clip(media / "ep01" / "s02.mp4", "360x640", 1, audio=False)  # 直式、比腳本短、沒聲音
    make_clip(media / "ep01" / "s03.mov", "480x480", 2, audio=True)   # 方形、.mov
    (media / "music").mkdir()
    # 配樂只有 1 秒，用來確認會循環補滿整支影片
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=1",
                    str(media / "music" / "test.wav")], check=True)

    ep = load_episode(small_root / "episodes" / "ep01-test.yaml", cfg)
    out = video.build_episode(ep, cfg)
    pr = video.probe(out)
    assert (pr.width, pr.height) == (270, 480)
    assert pr.has_audio
    assert pr.duration == pytest.approx(5.0, abs=0.2)
    assert (out.parent / "ep01.ass").exists()

    comp = small_root / "build" / "compilations" / "test.mp4"
    entries = video.compile_videos([("A", out), ("B", out)], comp, cfg)
    assert [round(t) for _, t in entries] == [0, 5]
    cp = video.probe(comp)
    assert (cp.width, cp.height) == (1920, 1080)
    assert cp.duration == pytest.approx(10.0, abs=0.4)


@pytest.mark.skipif(not has_ffmpeg, reason="需要 ffmpeg")
def test_missing_clips_need_placeholder(small_root: Path):
    cfg = load_config(small_root)
    ep = load_episode(small_root / "episodes" / "ep01-test.yaml", cfg)
    ep.music_file = None
    with pytest.raises(SystemExit, match="缺少片段"):
        video.build_episode(ep, cfg)
    out = video.build_episode(ep, cfg, placeholder=True)
    assert out.name == "ep01-placeholder.mp4"
    assert video.probe(out).duration == pytest.approx(6.0, abs=0.2)
