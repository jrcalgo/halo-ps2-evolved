"""Host checks for the PS2 Spartan bot adapter's pure helpers (submodules/halo-ce-universal/port/ps2/src/ps2_bots.c).

The helpers are extracted from the adapter source, so the test checks the code that ships, not a copy. The adapter's
CE calls cannot be linked on the host (they need the whole engine); those are covered by the review of the hunk in
source/game/player_queues_new.c, checked here as text.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
ADAPTER = HCU / "port/ps2/src/ps2_bots.c"
ADAPTER_HEADER = HCU / "port/ps2/include/halo_ps2_bots.h"
QUEUES = HCU / "source/game/player_queues_new.c"
CORE_HEADER = ROOT / "src/stream/hcu_bot.h"
MAIN = ROOT / "tests/hcu_ps2_bots_adapter_main.c"
PURE = ("ps2_bots_aim_to_facing", "ps2_bots_seat_player", "ps2_bots_seat_machine", "ps2_bots_weapon_lookup", "ps2_bots_name_slot")


def extract_function(source, name):
    match = re.search(r"^[\w ]+\b" + re.escape(name) + r"\(", source, re.M)
    if not match:
        raise AssertionError(f"function not found: {name}")
    start = match.start()
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise AssertionError(f"unterminated function {name}")


def pure_source(mutate=None):
    source = ADAPTER.read_text()
    text = [
        '#include "stream/hcu_c5_limits.h"',
        "#define HCU_BOT_MAX_TEST HCU_C5_BOT_SEATS_MAX",
        "#define SLOT_BASE_TEST HCU_C5_LOCAL_HUMAN_SLOTS",
        "#define SEATS_PER_MACHINE_TEST HCU_C5_MACHINE_SEATS",
        # CE's math names, as the adapter spells them (source/math/real_math.h), mapped to the host's libm
        "#include <math.h>",
        "#define square_root(x) sqrtf(x)",
        "#define arctangent(y, x) atan2f(y, x)",
        "#define arcsine(x) asinf(x)",
        "#define HALO_PS2_BOTS_SLOT_BASE SLOT_BASE_TEST",
        "#define HALO_PS2_BOTS_SEATS_PER_MACHINE SEATS_PER_MACHINE_TEST",
    ]
    text += [extract_function(source, name) for name in PURE]
    result = "\n".join(text) + "\n"
    if mutate:
        before, after = mutate
        assert result.count(before) == 1, before
        result = result.replace(before, after)
    return result


def build_and_run(tmp_path, mutate=None):
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        pytest.skip("C compiler unavailable")
    (tmp_path / "ps2_bots_pure.inc").write_text(pure_source(mutate))
    exe = tmp_path / "ps2_bots_adapter_test"
    subprocess.run([
        compiler, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
        f"-I{tmp_path}", f"-I{ROOT / 'src'}", str(MAIN), "-o", str(exe), "-lm",
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    return subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)


def test_pure_helpers_match_the_contract(tmp_path):
    result = build_and_run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ps2_bots adapter tests passed" in result.stdout


def test_negative_control_yaw_swap_fails(tmp_path):
    """A fault in the aim conversion must be caught by the round-trip check."""
    result = build_and_run(tmp_path, mutate=("*yaw = arctangent(aim[1], aim[0]);", "*yaw = arctangent(aim[0], aim[1]);"))
    assert result.returncode != 0


def test_hunk_is_guarded_and_minimal():
    queues = QUEUES.read_text(encoding="latin-1")
    assert queues.count("#ifdef HALO_PS2_BOTS") == 2
    assert "ps2_bots_update_actions();" in queues
    assert "update_server_bot_action_set(" in queues
    hook = queues.index("ps2_bots_update_actions();")
    assert queues.index("update_server_next_update();", hook) > hook
    # bots must never draw from CE's global random seed, nor use the local one
    adapter = ADAPTER.read_text()
    # (the name pool's tag path is "ui\\random_player_names"; the banned call is CE's name picker, which draws from the
    # global local seed)
    for banned in ("seed_random", "network_game_get_random_player_name", "get_global_random_seed_address",
                   "system_milliseconds", "rand("):
        assert banned not in adapter, banned
    # no N64 cap, throttle or cut
    for banned in ("MAXIMUM_BOTS", "TICKS_BETWEEN_PATHS", "DIRECT_TESTS_PER_TICK", "SIGHT_RANGE"):
        assert banned not in adapter, banned
    # the adapter never reads or writes update_server queues directly; it goes through the guarded setter
    assert "update_server_globals" not in adapter


def test_hooks_are_guarded_and_bind_the_mode():
    """The kill event and the objective's goal table are the only game_engine.c hunks, both under HALO_PS2_BOTS."""
    engine = (HCU / "source/game/game_engine.c").read_text(encoding="latin-1")
    assert engine.count("#ifdef HALO_PS2_BOTS") >= 3
    hook = engine.index("ps2_bots_player_killed(killing_player_index, dead_player_index);")
    assert engine.rfind("#ifdef HALO_PS2_BOTS", 0, hook) > engine.rfind("#endif", 0, hook)
    adapter = ADAPTER.read_text()
    # the team indices come from the binding, not from CE's default
    assert "hcu_coop_ce_bind" in adapter or "struct hcu_coop_ce_binding" in adapter
    assert "human->team_index = binding->team_index[i];" in adapter
    assert "player->team_index = config->bot_team;" in adapter
    # the death is the event: no polling of the unit to detect a death
    assert "ps2_bots_player_killed" in adapter and "hcu_bot_note_death" in adapter
    # melee: CE's use-equipment bit, not sent with equipment held
    assert "FLAG(_unit_control_use_equipment_bit)" in adapter and "has_equipment" in adapter


def test_weapon_pickup_and_name_sources_are_ce_objects():
    adapter = ADAPTER.read_text()
    assert "object_iterator_new(&weapons, FLAG(_object_type_weapon), 0)" in adapter
    assert "ui\\random_player_names" in adapter
    assert "hcu_bot_name_index(ps2_bots_state.seed, bot)" in adapter
    assert "game_engine_ps2_bots_nearest_goal" in adapter
