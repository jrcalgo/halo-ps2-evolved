"""Build and run the actual object renderer with host chain/model/platform shims."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"
SDK = ROOT / "submodules/ps2sdk"


def test_real_object_renderer_span_and_view_setup(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        return
    source = (ENGINE / "src/render/obj_render.c").read_text()
    source = source.replace('#include "platform/timer.h"', '#include "tests/obj_render_shim/timer.h"')
    renderer = tmp_path / "obj_render_host.c"
    renderer.write_text(source)
    exe = tmp_path / "obj_render_host"
    subprocess.run([
        compiler, "-D_EE", "-std=c11", "-w", "-ffunction-sections", "-fdata-sections",
        "-I" + str(ROOT), "-I" + str(SDK / "common/include"),
        "-I" + str(SDK / "ee/draw/include"), "-I" + str(SDK / "ee/packet2/include"),
        "-I" + str(SDK / "ee/math3d/include"),
        "-I" + str(ENGINE / "src"), str(ROOT / "tests/hcu_obj_render_host_main.c"), str(renderer),
        "-Wl,--gc-sections", "-lm", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "obj_render span/table/setup and reservation retry behavior passed" in result.stdout
