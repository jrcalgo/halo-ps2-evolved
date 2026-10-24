"""C3.1-C3.3 snapshot publication: the CE publisher and the parent's per-tick report.

Host checks only: they pin the contract between the CE publisher (ps2_render.c),
the CE tick hook (main.c C3:snapshot) and the parent report (hcu_main.c), and run
the bank's host contract with the wire-size change. The in-guest proof is the
PCSX2 run recorded in the C3 snapshot report, not this test.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CE = ROOT / "submodules/halo-ce-universal"


def _publisher_body():
    source = (CE / "port/ps2/src/ps2_render.c").read_text()
    start = source.index("static void ps2_c3_publish_frame_snapshot(")
    end = source.index("\n}\n", source.index("halo_ps2_frame_snapshot_commit(snapshot)", start)) + 3
    return source, source[start:end]


def test_publisher_fills_units_palettes_attachments_and_views():
    _, body = _publisher_body()
    # objects: interned by {datum index, magic}, once per object
    assert "halo_ps2_frame_snapshot_intern_object(snapshot, id," in body
    assert "id.generation = (uint32_t)object->object.magic_number;" in body
    # node palettes for bipeds, vehicles and weapons from the CE render pose
    assert "object_get_node_matrices(iterator.index)" in body
    assert "_object_type_biped || type == _object_type_vehicle" in body
    # attachments: child parent link, resolved through the live object table
    assert "object->object.parent_object_index" in body
    assert "HALO_PS2_FRAME_ATTACHMENT_PARENT_LINK" in body
    # resources: model tag per object definition
    assert "definition->object.model.index" in body
    # views: the player's unit from CE player state, and HUD values from the unit
    assert "local_player_get_player_index(window->local_player_index)" in body
    assert "player_try_and_get(player_index)" in body
    assert "view->hud_values[0] = object_get(unit_index)->object.body_vitality;" in body
    assert "view->unit_object = HALO_PS2_FRAME_NONE_U16;" in body
    # every view reference resolves through the bank (dedupe hits)
    assert "halo_ps2_frame_snapshot_intern_object(snapshot,\n\t\t\t\tsnapshot->objects[object_index].id, &resolved)" in body
    # the publisher never moves CE state
    for forbidden in ("object_set_world_matrix(", "object_set_position(", "player_control_update(",
                      "game_time_update(", "object_destroy("):
        assert forbidden not in body


def test_ce_tick_publishes_through_the_render_path_and_reports():
    source = (CE / "source/main/main.c").read_text()
    assert "main_game_render((double)(1.0f / 30.0f));" in source
    assert source.index("main_game_render((double)(1.0f / 30.0f));") < source.index("hcu_c3_snapshot_tick(tick);")
    assert "hcu_c3_snapshot_map_loaded(map_name);" in source
    assert "__attribute__((weak)) void hcu_c3_snapshot_tick(int tick)" in source


def test_parent_report_prints_every_30_frames_with_counters():
    source = (ROOT / "src/stream/hcu_main.c").read_text()
    block = source[source.index("void hcu_c3_snapshot_tick(int tick)"):]
    block = block[:block.index("/* C3:snapshot end */")]
    assert "s_c3s_ticks % 30u" in block
    assert "HALO_PS2_LOCAL c3-snapshot frame=" in block
    for field in ("views=", "biped=", "weapon=", "vehicle=", "other=", "palette=", "dedupe-hits=",
                  "bank-slot=", "reader-pins=", "refused-writes="):
        assert field in block, field
    assert "hcu_snapshot_bank_end_read(&reader);" in block


def test_bank_host_contract_with_intern_and_pins():
    root = ROOT
    with tempfile.TemporaryDirectory(prefix="c3-snapshot-publish-") as temp:
        executable = Path(temp) / "hcu-snapshot-bank-test"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Isrc",
            "-I" + str(CE / "port/ps2/include"),
            "tests/hcu_snapshot_bank_main.c", "src/stream/hcu_snapshot_bank.c",
            "-lm", "-o", str(executable),
        ], cwd=root, check=True, capture_output=True, text=True)
        result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    assert "hcu_snapshot_bank tests passed" in result.stdout
