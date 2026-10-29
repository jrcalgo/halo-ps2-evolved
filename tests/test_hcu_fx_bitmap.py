"""Host execution of the production FX bitmap helpers and their C fixture."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_production_fx_bitmap_fixture(tmp_path):
    compiler = shutil.which("gcc-13") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        pytest.skip("C compiler unavailable for FX bitmap host fixture")

    artifact_dir = Path(os.environ.get(
        "HCU_FX_BITMAP_ARTIFACTS", ROOT / "build/c3/harness-finish-atomic"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    includes = [ROOT / "src", ROOT / "submodules/halo-ps2/engine/src",
                ROOT / "submodules/halo-ce-universal/port/ps2/include"]
    fixture = ROOT / "tests/hcu_fx_bitmap_main.c"
    production = ROOT / "src/stream/hcu_fx_bitmap.c"
    exe = tmp_path / "hcu-fx-bitmap-fixture"
    command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror"]
    for include in includes:
        command.extend(["-I", str(include)])
    command.extend([str(fixture), str(production), "-o", str(exe)])
    built = subprocess.run(command, capture_output=True, text=True)
    (artifact_dir / "fx-bitmap-compile.json").write_text(json.dumps({
        "command": command, "returncode": built.returncode,
        "stdout": built.stdout, "stderr": built.stderr,
    }, indent=2) + "\n")
    assert built.returncode == 0, built.stdout + built.stderr

    run = subprocess.run([str(exe)], capture_output=True, text=True)
    (artifact_dir / "fx-bitmap-run.log").write_text(run.stdout + run.stderr)
    shutil.copy2(exe, artifact_dir / "hcu-fx-bitmap-fixture")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "hcu_fx_bitmap_main: all checks passed" in run.stdout
