import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"


def test_hud_emits_from_reserve_after_general_limit(tmp_path):
    exe = tmp_path / "hcu_render_hud_reserve_test"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ENGINE / "src"), "-I", str(ROOT / "src"),
        str(ROOT / "tests/hcu_render_hud_reserve_main.c"),
        str(ROOT / "src/stream/hcu_bitmap_quad.c"),
        str(ENGINE / "src/render/chain.c"), str(ENGINE / "src/world/tex.c"),
        "-lm", "-o", str(exe),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
