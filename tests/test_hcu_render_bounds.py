import shutil
import subprocess
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_render_bounds_metadata_and_actual_boulder_witness(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "hcu_render_bounds"
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Isrc",
                    "tests/hcu_render_bounds_main.c", "src/stream/hcu_render_bounds.c",
                    "-lm", "-o", str(exe)], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu_render_bounds tests passed" in result.stdout


def test_c727_hcp_emits_identity_bound_metadata_for_all_models(tmp_path):
    package = ROOT / "build/c3/quiet-c727-v6-cache-allocator-fix-builder/source-freeze/current-r1/packages/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
    if not package.exists():
        pytest.skip("exact c727 frozen package unavailable")
    out = tmp_path / "hcu_c3_objects_table.h"
    subprocess.run(["python3", str(ROOT / "tools/hcu_c3_objects_table.py"),
                    "--package-json", str(package), "--output", str(out)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    text = out.read_text()
    assert "HCU_C3_OBJECTS_TABLE_COUNT 69u" in text
    assert text.count(", 1u },") == 69
    assert "{ 16u, 650u, 1124u, 3784507423u" in text
    assert re.search(r"0x86, 0xbf, 0x78, 0xd6", text)
