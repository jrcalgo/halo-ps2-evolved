"""Asset-free host regression for the production HCU first-person pose callback."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_camera_local_and_world_inverse_bind_use_production_pose_fn(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    sdk = ROOT / "build/toolchain/install/ps2sdk"
    if not compiler or not (sdk / "ee/include").exists():
        pytest.skip("host compiler or installed PS2SDK headers unavailable")
    exe = tmp_path / "hcu_fp_pose_bind_test"
    subprocess.run([
        compiler, "-std=c11", "-D_EE", "-include", "tamtypes.h", "-ffunction-sections", "-fdata-sections",
        "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-Wno-int-to-pointer-cast",
        "-Wno-pointer-to-int-cast", "-Isrc",
        "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/source"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/port/include"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/source/cseries"),
        "-I" + str(sdk / "ee/include"), "-I" + str(sdk / "common/include"),
        "tests/hcu_fp_pose_bind_ee_fixture.c",
        "submodules/halo-ps2/engine/src/core/mat.c",
        "submodules/halo-ps2/engine/src/sim/skeleton.c",
        "-Wl,--gc-sections", "-lm", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu inverse-bind production pose_fn fixture passed" in result.stdout
