"""Capture reliability: window lookup, non-black statistics, the held-capture gate and the
private display's lifecycle (C3 capture-reliability lane)."""
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_guest_run as g  # noqa: E402
import c2_profile_boot_matrix as matrix  # noqa: E402


def _png(path: Path, fill, box=None, size=(1280, 1024)):
    image = Image.new("RGB", size, (0, 0, 0))
    if box is not None:
        image.paste(fill, box)
    image.save(path)
    return path


def test_all_black_frame_has_zero_fraction(tmp_path):
    stats = g.nonblack_stats(_png(tmp_path / "black.png", (0, 0, 0)))
    assert stats["nonblack_fraction"] == 0.0
    assert stats["game_pixels"] == 1280 * 1024 - 460 * 120


def test_osd_box_alone_does_not_count_as_game_pixels(tmp_path):
    # Bright OSD text only inside the top-left box must not make a black frame pass.
    stats = g.nonblack_stats(_png(tmp_path / "osd.png", (255, 255, 255), box=(10, 10, 400, 90)))
    assert stats["nonblack_fraction"] == 0.0


def test_textured_game_area_counts(tmp_path):
    # Half the game area bright: fraction is about 0.5, well above the 1 % gate.
    stats = g.nonblack_stats(_png(tmp_path / "half.png", (120, 120, 120), box=(0, 512, 1280, 1024)))
    assert 0.45 < stats["nonblack_fraction"] < 0.55
    assert stats["nonblack_fraction"] >= g.CAPTURE_MIN_NONBLACK


def test_faint_noise_below_black_level_is_black(tmp_path):
    stats = g.nonblack_stats(_png(tmp_path / "faint.png", (g.CAPTURE_BLACK_LEVEL, 0, 0), box=(0, 0, 1280, 1024)))
    assert stats["nonblack_fraction"] == 0.0


def test_clear_sky_and_hud_do_not_qualify_as_rendered_scene(tmp_path):
    image = Image.new("RGB", (640, 448), (15, 25, 40))
    image.paste((255, 255, 255), (310, 220, 330, 221))
    path = tmp_path / "clear-with-crosshair.png"
    image.save(path)
    stats = g.nonblack_stats(path)
    assert stats["nonblack_fraction"] > 0.5
    assert not matrix.capture_has_scene_variation(stats)


def test_scene_variation_gate_accepts_detailed_content(tmp_path):
    image = Image.new("RGB", (640, 448))
    for column in range(640):
        value = column % 256
        image.paste((value, (value * 3) % 256, 255 - value), (column, 120, column + 1, 448))
    path = tmp_path / "content.png"
    image.save(path)
    assert matrix.capture_has_scene_variation(g.nonblack_stats(path))


def test_find_window_picks_largest_pcsx2_window(monkeypatch):
    tree = (
        '  0x1 "root":\n'
        '     0x400001 "PCSX2": ("pcsx2-qt" "PCSX2")  640x480+0+0  +0+0\n'
        '     0x400002 "PCSX2": ("pcsx2-qt" "PCSX2")  1024x768+0+0  +0+0\n'
        '     0x400003 "xterm": ("xterm" "XTerm")  2000x2000+0+0  +0+0\n'
        '     0x400004 "PCSX2": ("pcsx2-qt" "PCSX2")  32x32+0+0  +0+0\n'
    )
    monkeypatch.setattr(g.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=tree, stderr=""))
    assert g.find_pcsx2_window(":100") == ("0x400002", 1024, 768)


def test_find_window_none_when_absent(monkeypatch):
    monkeypatch.setattr(g.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout='0x1 "xterm": ("x" "X")  9x9+0+0\n', stderr=""))
    assert g.find_pcsx2_window(":100") is None


def test_private_display_starts_and_stops_its_own_server():
    display = g.PrivateDisplay(first=190, last=200)
    try:
        name = display.start()
        assert name.startswith(":")
        assert display.process is not None and display.process.poll() is None
        pid = display.process.pid
    finally:
        display.stop()
    assert display.process is None
    assert subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode != 0
