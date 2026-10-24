"""Host ILP32 test of the CE bitmap quad capture bridge (no PS2 rendering claim)."""
from pathlib import Path
import shutil
import signal
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def test_bitmap_request_capture_and_frame_lifetime(tmp_path):
    compiler = shutil.which("gcc-13") or shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable for the CE ILP32 bitmap request fixture")
    include_dirs = [
        HCU / "source", HCU / "source/cseries", HCU / "source/math", HCU / "source/render", HCU / "source/tag_files",
        HCU / "source/bitmaps", HCU / "source/rasterizer",
        HCU / "source/rasterizer/common", HCU / "port/ps2/include",
        HCU / "port/linux/game", HCU / "port/include", HCU / "port/include/xdk",
    ]
    exe = tmp_path / "bitmap-requests-fixture"
    cmd = [compiler, "-m32", "-std=gnu99", "-fms-extensions", "-fshort-wchar",
           "-fwrapv", "-fno-strict-aliasing", "-w", "-ffunction-sections",
           "-fdata-sections", "-include", str(ROOT / "tests/soundreq_host_prefix.h")]
    for directory in include_dirs:
        cmd.extend(["-I", str(directory)])
    cmd.extend(["-Wl,--gc-sections", "-o", str(exe),
                str(ROOT / "tests/hcu_bitmap_requests_fixture.c"),
                str(HCU / "port/ps2/src/ps2_bitmap_requests.c")])
    built = subprocess.run(cmd, capture_output=True, text=True)
    if built.returncode:
        if "bits/libc-header-start.h" in built.stderr or "cannot find -lc" in built.stderr:
            pytest.skip("32-bit host C development files unavailable")
        pytest.fail(f"ILP32 fixture compile/link failed:\n{built.stderr[-4000:]}")
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    if result.returncode == -signal.SIGSYS:
        pytest.skip("sandbox blocks native ILP32 execution with SIGSYS")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "bitmap-requests-ok records=128 captured=128 queue_end_consumer=1 bounded=1 pointers_retained=0" in result.stdout
