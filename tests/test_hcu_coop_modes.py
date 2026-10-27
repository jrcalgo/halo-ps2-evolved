"""Host tests for the C5 cooperative mode table, admission gate, and team assignment."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_coop_modes_host_contract(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "hcu_coop_modes_test"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-Isrc", "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        "tests/hcu_coop_modes_main.c",
        "src/stream/hcu_coop_modes.c",
        "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu_coop_modes tests passed" in result.stdout


def test_coop_rules_match_ce_builders():
    """The table's stock values must equal the CE build_game_variant_* results in game_engine.c."""
    import re

    src = (ROOT / "submodules/halo-ce-universal/source/game/game_engine.c").read_text(errors="replace")
    header = (ROOT / "src/stream/hcu_coop_modes.c").read_text()
    rows = re.findall(r'\{ HCU_COOP_MODE_\w+, HCU_COOP_ENGINE_\w+, "(build_game_variant_\w+)", (\d), (\d+), (\d+), (\d+), (\d) \}', header)
    assert len(rows) == 9
    for builder, teams, respawn, score, suicide, _coop in rows:
        m = re.search(r"struct game_variant \*%s\(.*?\n\}\n" % builder, src, re.S)
        assert m, builder
        body = m.group(0)
        assert re.search(r"teams\s*=\s*%s;" % ("TRUE" if teams == "1" else "FALSE"), body), builder
        assert re.search(r"respawn_time\s*=\s*%s;" % respawn, body), builder
        assert re.search(r"score_to_win\s*=\s*%s;" % score, body), builder
        assert re.search(r"suicide_penalty\s*=\s*%s;" % suicide, body), builder
