"""Per-view bitmap placement: CE window -> layout rect, viewport-relative offset, and per-view GS scissor."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"


def test_per_view_placement_and_scissor_for_1_to_4_views(tmp_path):
    exe = tmp_path / "hcu_bitmap_view_test"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ENGINE / "src"), "-I", str(ROOT / "src"),
        str(ROOT / "tests/hcu_bitmap_view_main.c"),
        str(ROOT / "src/stream/hcu_bitmap_quad.c"),
        str(ROOT / "src/stream/hcu_render_frame.c"),
        str(ENGINE / "src/render/chain.c"), str(ENGINE / "src/world/tex.c"),
        "-lm", "-o", str(exe),
    ], check=True, capture_output=True, text=True)
    run = subprocess.run([str(exe)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "HCU_BITMAP_VIEW_OK" in run.stdout
