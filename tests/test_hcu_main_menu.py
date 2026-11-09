from pathlib import Path
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src/stream/assets"
RETAIL_ISO = Path(os.environ.get(
    "HALO_RETAIL_XISO", Path.home() / "Documents/Halo/Halo - Combat Evolved.xiso.iso"))


def _ensure_retail_assets():
    """Retail-derived art is untracked: pull it from the disc, or skip."""
    if (ASSETS / "halo_ce_ring_inner.t8").is_file() and (ASSETS / "halo_ce_ring_mesh.bin").is_file():
        return
    if not RETAIL_ISO.is_file():
        pytest.skip("retail menu assets need the Halo CE XISO (set HALO_RETAIL_XISO)")
    build = subprocess.run(["python3", "tools/build_hcu_menu_assets.py", str(RETAIL_ISO)],
                           cwd=ROOT, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr


def test_controller_glyph_atlas_layout():
    atlas = (ROOT / "src/stream/assets/ps2_button_glyphs.rgb5a1").read_bytes()
    width, height, cell, count = 256, 16, 16, 13
    assert len(atlas) == width * height * 2

    def opaque(x, y):
        word = atlas[(y * width + x) * 2] | (atlas[(y * width + x) * 2 + 1] << 8)
        return bool(word & 0x8000)

    for index in range(count):
        assert any(opaque(x, y) for y in range(height) for x in range(index * cell, index * cell + cell))
    assert not any(opaque(x, y) for y in range(height) for x in range(count * cell, width))


def test_main_menu_state_and_ring_texture(tmp_path):
    _ensure_retail_assets()
    binary = tmp_path / "hcu-main-menu"
    build = subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Isrc",
            "tests/hcu_main_menu_main.c",
            "src/stream/hcu_main_menu.c",
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "main-menu-ok" in run.stdout
