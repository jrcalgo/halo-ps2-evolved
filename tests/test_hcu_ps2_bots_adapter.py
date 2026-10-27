"""Host checks for the PS2 Spartan bot adapter's pure helpers (submodules/halo-ce-universal/port/ps2/src/ps2_bots.c).

The helpers are extracted from the adapter source, so the test checks the code that ships, not a copy. The adapter's
CE calls cannot be linked on the host (they need the whole engine); those are covered by the review of the hunk in
source/game/player_queues_new.c, checked here as text.
"""
import re
import shutil
import subprocess
import sys
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


# ---- C5 bot events (HALO_PS2_BOTS) -------------------------------------------------------------------------------------
# The events are the only additions to ps2_bots.c. Everything they add sits under #ifdef HALO_PS2_BOTS, so a default
# build compiles the same code as before. The PS2 compiler checks run when the toolchain is built; the rest is host-only.
import json

HCU_TOOLCHAIN = ROOT / "build/toolchain/install"
PS2_GCC = HCU_TOOLCHAIN / "ee/bin/mips64r5900el-ps2-elf-gcc"
PS2_FLAGS = [
    "-std=gnu89", "-Os", "-mabi=n32", "-fms-extensions", "-fshort-wchar", "-fcommon",
    "-fno-strict-aliasing", "-fno-delete-null-pointer-checks", "-ffp-contract=off",
    "-fsigned-char", "-fwrapv", "-ffunction-sections", "-fdata-sections",
    "-G0", "-D_EE", "-D__STRICT_ANSI__", "-w", "-DHALO_PS2=1",
]
GUARD_OPEN = re.compile(r"^#\s*(if|ifdef|ifndef)\b")
BOTS_GUARD = re.compile(r"^#\s*ifdef\s+HALO_PS2_BOTS\s*$")


def guard_states(source: str):
    """For each line: (text, inside_bots_guard). A guard's own #ifdef and #endif lines count as inside."""
    stack = []
    states = []
    for line in source.splitlines():
        stripped = line.strip()
        if GUARD_OPEN.match(stripped):
            stack.append(bool(BOTS_GUARD.match(stripped)))
            states.append((line, any(stack)))
        elif re.match(r"^#\s*endif\b", stripped):
            states.append((line, any(stack)))
            if stack:
                stack.pop()
        else:
            if stripped.startswith(("#else", "#elif")):
                assert not any(stack), "an #else/#elif inside a HALO_PS2_BOTS guard is not supported"
            states.append((line, any(stack)))
    assert not stack, "unterminated preprocessor block"
    return states


def without_bots_guards(source: str) -> str:
    return "\n".join(text for text, inside in guard_states(source) if not inside) + "\n"


def ps2_compile(src: Path, out: Path, workdir: Path, *defines: str):
    if not PS2_GCC.is_file():
        pytest.skip("PS2 toolchain is not built (build/toolchain/install)")
    semantics = workdir / "halo_ps2_msvc_semantics.h"
    subprocess.run([
        sys.executable, str(HCU / "tools/linux_msvc_semantics.py"), "--output", str(semantics), "--all-inlines",
        "--tags", str(HCU / "source"), "--inlines", str(HCU / "source"), "--inlines", str(HCU / "port/include/xdk"),
    ], check=True, capture_output=True, text=True)
    manifest = json.loads((HCU / "port/ps2/port.json").read_text())
    includes = ["-I" + str(HCU / item) for item in manifest["include_dirs"]]
    includes += ["-I" + str(ROOT / "src"), "-I" + str(ROOT / "src/stream")]
    includes += ["-I" + str(HCU_TOOLCHAIN / "ps2sdk/common/include"), "-I" + str(HCU_TOOLCHAIN / "ps2sdk/ee/include")]
    command = [str(PS2_GCC), *PS2_FLAGS, *defines, *includes,
               "-include", str(HCU / manifest["prefix"]), "-include", str(semantics), "-c", str(src), "-o", str(out)]
    return subprocess.run(command, cwd=HCU, capture_output=True, text=True)


def test_every_event_call_is_under_the_bots_guard():
    source = ADAPTER.read_text()
    calls = [(text, inside) for text, inside in guard_states(source)
             if "ps2_bots_note(" in text or "ps2_bots_event_sink" in text or "ps2_bots_set_event_sink(" in text]
    assert len(calls) >= 8
    assert all(inside for _, inside in calls), [text for text, inside in calls if not inside]
    kinds = set(re.findall(r"ps2_bots_note\(PS2_BOTS_EVENT_(\w+)", source))
    assert kinds == {"NAV", "FIGHT", "KILL", "DEATH", "RESPAWN", "SCORE"}, kinds
    header_decl = [inside for text, inside in guard_states(ADAPTER_HEADER.read_text())
                   if "ps2_bots_set_event_sink(" in text]
    assert header_decl == [True], "the sink declaration must sit under HALO_PS2_BOTS"


def test_default_build_matches_the_guard_stripped_source(tmp_path):
    """Compiling without HALO_PS2_BOTS must give the same object as the source with the guarded blocks removed."""
    stripped_dir = tmp_path / "stripped"
    stripped_dir.mkdir()
    stripped = stripped_dir / "ps2_bots.c"
    stripped.write_text(without_bots_guards(ADAPTER.read_text()))
    real_obj = tmp_path / "real.o"
    stripped_obj = tmp_path / "stripped.o"
    real = ps2_compile(ADAPTER, real_obj, tmp_path)
    assert real.returncode == 0, real.stderr
    stripped_run = ps2_compile(stripped, stripped_obj, tmp_path)
    assert stripped_run.returncode == 0, stripped_run.stderr
    assert real_obj.read_bytes() == stripped_obj.read_bytes()


def test_bots_build_compiles_with_the_event_hooks(tmp_path):
    obj = tmp_path / "bots.o"
    result = ps2_compile(ADAPTER, obj, tmp_path, "-DHALO_PS2_BOTS=1")
    assert result.returncode == 0, result.stderr
    assert obj.stat().st_size > 0


SINK_DRIVER = r"""
#include <stdio.h>
#include <string.h>
#include "stream/hcu_c5_session.h"

static void emit(void *user, const char *line)
{
	(void)user;
	printf("%s\n", line);
}

static int teardown(void *user, const hcu_local_setup_result *accepted)
{
	(void)user;
	(void)accepted;
	return 0;
}

int main(void)
{
	struct hcu_c5_session_ops ops;
	struct hcu_c5_session session;
	hcu_local_setup request;
	const hcu_local_qualified_row *rows;
	size_t row_count = 0u;
	enum hcu_c5_session_status status;

	memset(&ops, 0, sizeof ops);
	ops.emit = emit;
	ops.teardown = teardown;
	rows = hcu_local_setup_rows(&row_count);
	memset(&request, 0, sizeof request);
	request.mode = HCU_LOCAL_MODE_STOCK_COOP;
	request.variant = HCU_LOCAL_VARIANT_SLAYER;
	request.teams = HCU_LOCAL_TEAMS_ON;
	request.difficulty = HCU_LOCAL_DIFFICULTY_NORMAL;
	request.human_mask = 0x3u;
	request.seed = 1u;
	strcpy(request.map_name, "bloodgulch");

	request.intent = HCU_LOCAL_INTENT_PLAY;
	status = hcu_c5_session_start(&session, &request, rows, row_count, &ops, NULL);
	printf("play: %s\n", hcu_c5_session_status_name(status));

	request.intent = HCU_LOCAL_INTENT_MEASURE;
	status = hcu_c5_session_start(&session, &request, rows, row_count, &ops, NULL);
	printf("measure: %s\n", hcu_c5_session_status_name(status));
	hcu_c5_session_bot_sink(&session, HCU_C5_EVENT_NAV, 2u, 7L);
	hcu_c5_session_bot_sink(&session, 9, 2u, 7L);
	hcu_c5_session_bot_sink(NULL, HCU_C5_EVENT_NAV, 2u, 7L);
	printf("nav-steps: %u\n", (unsigned)session.metrics.nav_steps);
	return 0;
}
"""


def test_sink_reaches_the_session_and_measure_is_marked(tmp_path):
    """Through the registered sink a bot event is a session event; a MEASURE start says so, and PLAY is refused."""
    if not shutil.which("cc"):
        pytest.skip("C compiler unavailable")
    driver = tmp_path / "sink_driver.c"
    driver.write_text(SINK_DRIVER)
    exe = tmp_path / "sink_driver"
    subprocess.run([
        "cc", "-std=gnu89", "-Wall", "-Wextra", "-Werror", "-Isrc", str(driver),
        "src/stream/hcu_c5_session.c", "src/stream/hcu_bot.c", "src/stream/hcu_coop_ce_bind.c",
        "src/stream/hcu_coop_modes.c", "src/stream/hcu_local_setup.c", "src/stream/hcu_survival.c",
        "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, check=True).stdout
    assert "play: setup-refused" in out
    assert "session-refused reason=difficulty-not-qualified" in out
    assert "measure: ok" in out
    assert "status=measuring" in out
    assert "HALO_PS2_C5 bot-event tick=0 kind=nav bot=2 arg=7" in out
    assert out.count("bot-event") == 1, "an out-of-range kind must be dropped"
    assert "nav-steps: 1" in out
