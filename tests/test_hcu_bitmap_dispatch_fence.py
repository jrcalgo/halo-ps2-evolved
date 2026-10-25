import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_pending_or_unknown_fence_keeps_bitmap_lease_and_readers(tmp_path):
    compiler = shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable")
    engine = ROOT / "submodules/halo-ps2/engine"
    hcu = ROOT / "submodules/halo-ce-universal/port/ps2/include"
    exe = tmp_path / "bitmap-dispatch-fence"
    command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
               "-I", str(ROOT / "src"), "-I", str(engine / "src"), "-I", str(hcu),
               str(ROOT / "tests/hcu_bitmap_dispatch_fence_main.c"),
               str(ROOT / "src/stream/hcu_bitmap_dispatch.c"),
               str(engine / "src/render/texcache.c"), str(engine / "src/render/chain.c"),
               "-lm", "-o", str(exe)]
    built = subprocess.run(command, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "bitmap-dispatch-fence-ok" in ran.stdout
