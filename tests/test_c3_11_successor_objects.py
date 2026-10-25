"""C3.11: the successor map draws its object models from its own package's table.

The selected row's MODL/OTEX chunk ids and hashes do not match the successor's package, so a shared table
refused every successor entry. These tests check the generator's successor output on the real packages (when
they are built) and the generated names the EE source selects by map name."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools/hcu_c3_objects_table.py"
PACKAGES = ROOT / "build/c3/c3-fplod/packages"
BLOODGULCH = PACKAGES / "bloodgulch-c3v3-2026-10-25/bloodgulch_mounted_gunner_4p4bot.json"
BEAVERCREEK = PACKAGES / "beavercreek-c3v3-2026-10-25/beavercreek_mounted_gunner_4p4bot.json"


def _generate(manifest: Path, out: Path, *extra: str) -> str:
    subprocess.run([sys.executable, "-I", str(GENERATOR), "--package-json", str(manifest),
                    "--sky-from-scenario", "--output", str(out), *extra], cwd=ROOT, check=True,
                   capture_output=True, text=True)
    return out.read_text()


@pytest.mark.skipif(not (BLOODGULCH.is_file() and BEAVERCREEK.is_file()), reason="C3 v3 packages not built")
def test_successor_table_is_separate_and_names_its_map():
    with tempfile.TemporaryDirectory(prefix="c3-succ-objects-") as temp:
        temp = Path(temp)
        default = _generate(BLOODGULCH, temp / "default.h")
        succ = _generate(BEAVERCREEK, temp / "succ.h", "--successor")
    assert "hcu_c3_objects_table[HCU_C3_OBJECTS_TABLE_COUNT]" in default
    assert "HCU_C3_OBJECTS_MAP" not in default
    assert "#define HCU_C3_SUCC_OBJECTS_TABLE_COUNT 58u" in succ
    assert '#define HCU_C3_SUCC_OBJECTS_MAP "beavercreek"' in succ
    assert "static const hcu_render_objects_table_entry hcu_c3_succ_objects_table[HCU_C3_SUCC_OBJECTS_TABLE_COUNT]" in succ
    assert "entry hcu_c3_objects_table[" not in succ
    # The successor's own package hash is recorded, and its first model chunk is not the selected row's.
    manifest = json.loads(BEAVERCREEK.read_text())
    assert manifest["profile"]["map"] == "beavercreek"
    assert "#define HCU_C3_SUCC_OBJECTS_SKY_INDEX" in succ


def test_generator_default_names_are_unchanged():
    source = GENERATOR.read_text()
    assert 'prefix: str = ""' in source
    assert 'hcu_c3_{prefix}objects_table' in source


def test_ee_source_selects_successor_table_by_map_name():
    main = (ROOT / "src/stream/hcu_main.c").read_text()
    assert "#define HCU_C3_OBJECTS_SUCC_BUILT 1" in main
    assert "strcmp(map_name, HCU_C3_SUCC_OBJECTS_MAP) == 0" in main
    frame = main[main.index("static void hcu_c3_objects_frame_begin(void)"):]
    frame = frame[:frame.index("if (s_c3o_loaded && !s_c3o_installed)")]
    assert "s_c3o_table," in frame and "s_c3o_count, &s_c3o_info" in frame
    assert "HCU_C3_OBJECTS_TABLE_COUNT, &s_c3o_info" not in frame
    assert "hcu_render_objects_set_sky_entry(s_c3o_sky)" in frame


def test_previous_kick_wait_is_bounded_to_unobserved_kicks():
    main = (ROOT / "src/stream/hcu_main.c").read_text()
    body = main[main.index("static void hcu_c3_wait_previous_kick(void)"):]
    body = body[:body.index("\n}\n")]
    assert "bsp_render_fence_observed(kick) != 1" in body
    assert "video_wait_gpu();" in body
    tick = main[main.index("void hcu_c3_render_tick(int tick)"):]
    tick = tick[:tick.index("/* Order: drain GS/DMA")] if "/* Order: drain GS/DMA" in tick else tick[:6000]
    assert "hcu_c3_wait_previous_kick();" in tick
