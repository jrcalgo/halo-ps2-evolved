"""Host tests for the C3.objects pure core (synthetic builder, selection, pin/unpin, parity)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_render_objects_host_contract(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "hcu_render_objects_test"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-Isrc", "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        "tests/hcu_render_objects_main.c",
        "src/stream/hcu_render_objects.c",
        "src/stream/hcu_render_content.c",
        "src/stream/hcu_snapshot_bank.c",
        "-lm", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu_render_objects tests passed" in result.stdout


def test_objects_table_generator_is_exact(tmp_path):
    package = ROOT / "build/c3/render-tree/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
    if not package.exists():
        pytest.skip("Blood Gulch render package not built")
    out = tmp_path / "hcu_c3_objects_table.h"
    subprocess.run(["python3", "-I", str(ROOT / "tools/hcu_c3_objects_table.py"),
                    "--package-json", str(package), "--output", str(out)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    text = out.read_text()
    assert "HCU_C3_OBJECTS_TABLE_COUNT 4u" in text
    assert "characters\\\\cyborg\\\\cyborg" in text
    assert "vehicles\\\\ghost\\\\ghost" in text
