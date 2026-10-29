"""The native post-world compositor must report bounded work, including no-op and refused frames."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"
SDK = ROOT / "build/toolchain/install/ps2sdk"


def _command(compiler, output, timer_include, diagnostic, screen_effect_source=None, p4=False):
    cmd = [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
           "-Wno-int-to-pointer-cast", "-Wno-pointer-to-int-cast",
           "-Wno-incompatible-pointer-types", "-D_EE", "-include", "tamtypes.h"]
    if diagnostic:
        cmd += ["-DHALO_PS2_C3_PERF_PROBE=1", "-I" + str(timer_include)]
    if p4:
        cmd += ["-DHCU_SCREEN_EFFECT_TEST_P4=1"]
        freeze = ROOT / "build/c3/quiet-c727-v6-cache-allocator-fix-builder/source-freeze/current-r1"
        overlay = ROOT / "build/c3/sniper-fps-regression-new/probe-overlay"
        cmd += ["-I" + str(freeze / "src"),
                "-I" + str(overlay / "submodules/halo-ps2/engine/src")]
    cmd += ["-Isrc", "-I" + str(ENGINE),
            "-Isubmodules/halo-ce-universal/port/ps2/include",
            "-Isubmodules/halo-ce-universal/source",
            "-I" + str(SDK / "ee/include"), "-I" + str(SDK / "common/include"),
            str(ROOT / "tests/hcu_bitmap_screen_effect_probe_main.c"),
            str(screen_effect_source or (ROOT / "src/stream/hcu_bitmap_screen_effect.c")),
            str(ENGINE / "render/chain.c"), "-lm", "-o", str(output)]
    return cmd


def test_screen_effect_probe_production_backend(tmp_path):
    compiler = shutil.which("gcc-13") or shutil.which("gcc")
    if not compiler or not (SDK / "common/include/tamtypes.h").exists():
        pytest.skip("GCC or the installed PS2SDK headers are unavailable")

    fake_include = tmp_path / "include/platform"
    fake_include.mkdir(parents=True)
    (fake_include / "timer.h").write_text(
        "#pragma once\n#include <stdint.h>\n"
        "uint32_t test_timer_cycles(void);\n#define timer_cycles test_timer_cycles\n")

    exe = tmp_path / "screen-effect-probe"
    built = subprocess.run(_command(compiler, exe, tmp_path / "include", True),
                           cwd=ROOT, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "screen-effect-probe-ok no-effect=0 multi-view-copy=1 capacity-refusal=1 fence-refusal=1" in ran.stdout

    # When the immutable P4 candidate overlay is staged, run the same production backend
    # with its original 64-byte/16-entry CLUT contract.
    p4_source = ROOT / "build/c3/sniper-fps-regression-new/probe-overlay/src/stream/hcu_bitmap_screen_effect.c"
    if p4_source.exists():
        p4_exe = tmp_path / "screen-effect-probe-p4"
        p4_build = subprocess.run(_command(compiler, p4_exe, tmp_path / "include", True,
                                            p4_source, p4=True),
                                  cwd=ROOT, capture_output=True, text=True)
        assert p4_build.returncode == 0, p4_build.stdout + p4_build.stderr
        p4_run = subprocess.run([str(p4_exe)], capture_output=True, text=True)
        assert p4_run.returncode == 0, p4_run.stdout + p4_run.stderr

    # The quiet build compiles the same production backend without a timer reference.
    obj = tmp_path / "quiet-screen-effect.o"
    quiet = subprocess.run([compiler, "-std=gnu11", "-D_EE", "-include", "tamtypes.h",
                            "-Wno-int-to-pointer-cast", "-Wno-pointer-to-int-cast",
                            "-Wno-incompatible-pointer-types", "-Isrc", "-I" + str(ENGINE),
                            "-Isubmodules/halo-ce-universal/port/ps2/include",
                            "-Isubmodules/halo-ce-universal/source",
                            "-I" + str(SDK / "ee/include"), "-I" + str(SDK / "common/include"),
                            "-c", str(ROOT / "src/stream/hcu_bitmap_screen_effect.c"), "-o", str(obj)],
                           cwd=ROOT, capture_output=True, text=True)
    assert quiet.returncode == 0, quiet.stdout + quiet.stderr
    symbols = subprocess.run([shutil.which("nm") or "nm", str(obj)],
                             capture_output=True, text=True, check=True).stdout
    assert "test_timer_cycles" not in symbols and "g_bsp_render_screen_effect_probe" not in symbols

    quiet_probe = tmp_path / "quiet-probe"
    quiet_check = subprocess.run([compiler, "-std=gnu11", "-D_EE", "-include", "tamtypes.h",
                                  "-Wno-int-to-pointer-cast", "-Wno-pointer-to-int-cast",
                                  "-Wno-incompatible-pointer-types", "-I" + str(ENGINE),
                                  "-I" + str(SDK / "ee/include"), "-I" + str(SDK / "common/include"),
                                  str(ROOT / "tests/hcu_screen_effect_probe_quiet.c"), "-o", str(quiet_probe)],
                                 cwd=ROOT, capture_output=True, text=True)
    assert quiet_check.returncode == 0, quiet_check.stdout + quiet_check.stderr
    quiet_run = subprocess.run([str(quiet_probe)], capture_output=True, text=True)
    assert quiet_run.returncode == 0, quiet_run.stdout + quiet_run.stderr
