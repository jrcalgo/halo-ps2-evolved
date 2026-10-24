import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def test_ps2_rasterizer_bounds_cpu_adapter():
    cc = shutil.which(os.environ.get("HOST_CC", "cc"))
    assert cc
    with tempfile.TemporaryDirectory(prefix="hcu-ps2-bounds-") as temp:
        exe = Path(temp) / "bounds"
        subprocess.run([
            cc, "-std=c89", "-Wall", "-Wextra", "-Werror",
            "-I", str(HCU / "port/ps2/include"),
            str(ROOT / "tests/ps2_rasterizer_bounds_main.c"), "-o", str(exe),
        ], check=True, cwd=ROOT)
        result = subprocess.run([str(exe)], check=True, text=True,
                                capture_output=True)
        assert result.stdout.strip() == "PS2 rasterizer bounds fixture passed"
