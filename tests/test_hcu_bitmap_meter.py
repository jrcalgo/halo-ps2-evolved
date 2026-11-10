"""Ammo meter palette: N rounds fill exactly N bullets for the retail HUD parameters (native, no package needed)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def _meter_source() -> str:
    text = (ROOT / "src/stream/hcu_bitmap_dispatch.c").read_text()
    start = text.index("static const uint8_t k_meter_shape_level")
    end = text.index("/* Draws a meter from a texture built by convert_meter_rgba", start)
    return "#include <stdint.h>\n#include \"halo_ps2_bitmap_requests.h\"\n" + text[start:end]


def test_meter_palette_fills_exactly_the_requested_bullets(tmp_path):
    compiler = shutil.which("gcc-13") or shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable")
    source = tmp_path / "meter_palette.inc"
    source.write_text(_meter_source())
    exe = tmp_path / "meter-main"
    cmd = [compiler, "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-DMETER_SOURCE=\"%s\"" % source,
           "-I", str(HCU / "port/ps2/include"), str(ROOT / "tests/hcu_bitmap_meter_main.c"), "-o", str(exe), "-lm"]
    built = subprocess.run(cmd, capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
