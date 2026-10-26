"""Host-compiled prepared-object cache behavior checks for C3."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_object_prepare_cache_host_behavior(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "hcu_object_prepare_cache_test"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-Isrc", "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        "tests/hcu_object_prepare_cache_main.c", "src/stream/hcu_render_objects.c",
        "src/stream/hcu_render_content.c", "src/stream/hcu_snapshot_bank.c", "-lm", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu object prepare cache tests passed" in result.stdout


def test_object_prepare_cache_actual_ee_adapter_state(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    sdk = ROOT / "build/toolchain/install/ps2sdk"
    generated = ROOT / "build/c3/objects/gen"
    if not compiler or not (sdk / "ee/include").exists() or not (generated / "hcu_c3_objects_table.h").exists():
        pytest.skip("host compiler, installed PS2SDK headers, or generated object table unavailable")
    exe = tmp_path / "hcu_object_prepare_cache_ee_test"
    subprocess.run([
        compiler, "-std=c11", "-D_EE", "-include", "tamtypes.h", "-ffunction-sections", "-fdata-sections",
        "-Wno-unused-parameter", "-Wno-int-to-pointer-cast", "-Wno-pointer-to-int-cast",
        "-Isrc", "-I" + str(generated), "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/source"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/port/include"),
        "-I" + str(ROOT / "submodules/halo-ce-universal/source/cseries"),
        "-I" + str(sdk / "ee/include"), "-I" + str(sdk / "common/include"),
        "tests/hcu_object_prepare_cache_ee_fixture.c", "-Wl,--gc-sections", "-lm", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu object prepare EE cache fixture passed" in result.stdout
