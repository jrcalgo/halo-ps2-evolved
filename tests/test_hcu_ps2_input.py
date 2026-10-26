"""Exercise the HCU PS2 XInput semantics with host-compiled code."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


class HcuPs2Input(unittest.TestCase):
    @staticmethod
    def extract_function(source, signature):
        # CE files commonly have a prototype before the definition. Select the
        # final occurrence so the extracted fragment is a function body.
        start = source.rindex(signature)
        opening = source.index("{", start)
        depth = 0
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[start:index + 1]
        raise AssertionError(f"unterminated source function {signature}")

    def test_ps2_pad_logical_order_for_both_multitap_arrangements(self):
        for port0_tap in (1, 0):
            with self.subTest(port0_tap=port0_tap), tempfile.TemporaryDirectory() as temp:
                exe = Path(temp) / "hcu-pad-poll"
                subprocess.run(
                    ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                     f"-DPAD_TEST_PORT0_TAP={port0_tap}",
                     "-I" + str(ROOT / "tests/hcu_pad_shim"),
                     "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                     str(ROOT / "tests/hcu_pad_poll_main.c"),
                     str(ROOT / "submodules/halo-ps2/engine/src/platform/pad.c"),
                     "-o", str(exe)],
                    check=True, capture_output=True)
                result = subprocess.run([str(exe)], check=True, text=True,
                                        capture_output=True)
                self.assertTrue(result.stdout.strip().endswith(
                    "PS2 pad logical port/slot fixture passed"))

    def test_ps2_pad_configuration_state_machine(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hcu-pad-state-machine"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "tests/hcu_pad_shim"),
                 "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                 str(ROOT / "tests/hcu_pad_poll_main.c"),
                 str(ROOT / "submodules/halo-ps2/engine/src/platform/pad.c"),
                 "-o", str(exe)],
                check=True, capture_output=True, text=True)
            for scenario in ("async", "unsupported", "failure", "pressfailure",
                             "reconnect"):
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(exe), scenario], check=False,
                                            text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("PS2 pad state-machine fixture passed",
                                  result.stdout)

    def test_dualshock_conversion_connection_and_packet_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hcu-ps2-input"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-DHALO_PS2_C3_FRAME_SNAPSHOT",
                 "-D__stdcall=", "-D__fastcall=", "-D__int64=long long",
                 "-I" + str(HCU / "port/include"),
                 "-I" + str(HCU / "port/ps2/include"),
                 str(ROOT / "tests/hcu_ps2_input_main.c"),
                 str(HCU / "port/ps2/src/ps2_input.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)

    def test_parent_pad_bridge_publishes_samples_before_ce_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hcu-input-bridge"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-D__stdcall=", "-D__fastcall=", "-D__int64=long long",
                 "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                 "-I" + str(HCU / "port/include"),
                 "-I" + str(HCU / "port/ps2/include"),
                 str(ROOT / "tests/hcu_input_bridge_main.c"),
                 str(ROOT / "src/stream/hcu_input_bridge.c"),
                 str(HCU / "port/ps2/src/ps2_input.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)

    def test_ce_frame_begin_polls_parent_before_snapshotting_devices(self):
        source = (HCU / "source/input/input_xbox.c").read_text()
        match = re.search(
            r"void\s+input_frame_begin\s*\(\s*void\s*\)\s*\{(.*?)\n\}",
            source, re.S)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("#ifdef HALO_PS2", body)
        self.assertLess(body.index("ps2_input_poll_devices()"),
                        body.index("input_get_device_states()"))
        self.assertLess(body.index("input_get_device_states()"),
                        body.index("input_globals.frame_active = TRUE"))

    def test_ce_frame_begin_executes_poll_snapshot_then_frame_activation(self):
        source = (HCU / "source/input/input_xbox.c").read_text()
        match = re.search(
            r"void\s+input_frame_begin\s*\(\s*void\s*\)\s*\{(.*?)\n\}",
            source, re.S)
        self.assertIsNotNone(match)
        body = match.group(0)
        fixture = r"""
#include <assert.h>
#include <limits.h>
#define HALO_PS2 1
#define TRUE 1
struct { int frame_active; } input_globals;
static int calls[4], count;
void ps2_input_poll_devices(void) { calls[count++] = 1; }
void input_get_device_states(void) { calls[count++] = 2; }
void acquire_input_mutex(void) { calls[count++] = 3; }
""" + body + r"""
int main(void)
{
	input_frame_begin();
	assert(count == 3);
	assert(calls[0] == 1 && calls[1] == 2 && calls[2] == 3);
	assert(input_globals.frame_active == TRUE);
	return 0;
}
"""
        with tempfile.TemporaryDirectory() as temp:
            cfile = Path(temp) / "input-frame-begin.c"
            exe = Path(temp) / "input-frame-begin"
            cfile.write_text(fixture)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(cfile), "-o", str(exe)], check=True,
                           capture_output=True, text=True)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ce_game_initialization_and_tick_phase_order_is_preserved(self):
        game_source = (HCU / "source/game/game.c").read_text()
        initialize = self.extract_function(game_source, "void game_initialize(")
        tick = self.extract_function(game_source, "void game_tick(")

        initialize_phases = [
            "scenario_initialize()", "objects_initialize()",
            "structures_initialize()", "players_initialize()",
            "effects_initialize()", "ai_initialize()",
            "hs_initialize()", "input_abstraction_initialize()",
        ]
        positions = [initialize.index(phase) for phase in initialize_phases]
        self.assertEqual(positions, sorted(positions))
        for phase in initialize_phases:
            self.assertEqual(initialize.count(phase), 1, phase)

        tick_phases = [
            "game_allegiance_update()", "units_update()", "ai_update()",
            "players_update_before_game()", "effects_update(seconds_per_tick)",
            "antennas_update(seconds_per_tick)", "first_person_weapons_update()",
            "game_engine_update()", "hs_update()",
            "recorded_animations_update()", "objects_update()",
            "players_update_after_game()", "hud_update()",
            "player_effect_update()",
        ]
        positions = [tick.index(phase) for phase in tick_phases]
        self.assertEqual(positions, sorted(positions))
        for phase in tick_phases:
            self.assertEqual(tick.count(phase), 1, phase)
        self.assertLess(tick.index("lock_global_random_seed()"),
                        tick.index("first_person_weapons_update()"))
        self.assertLess(tick.index("first_person_weapons_update()"),
                        tick.index("unlock_global_random_seed()"))

        main_source = (HCU / "source/main/main.c").read_text()
        main_loop_start = main_source.rindex("void main_loop(")
        # The function has an #ifdef HALO_WEB branch that closes syntactically
        # before the native #else body; inspect the native source tail rather
        # than treating preprocessor alternatives as nested C blocks.
        main_loop = main_source[main_loop_start:]
        # main_loop also holds the C2/C3 production tick loop, which has its
        # own player_control_update() call earlier in the text (its input is
        # sampled by hcu_c3_workload_prepare_actions(); see the C3 test
        # below). The frame order of CE's own loop is the last
        # input_frame_begin() onward.
        self.assertLess(main_loop.index("game_initialize()"),
                        main_loop.index("input_frame_begin()"))
        native = main_loop[main_loop.rindex("input_frame_begin()"):]
        self.assertLess(native.index("input_frame_begin()"),
                        native.index("input_update()"))
        self.assertLess(native.index("input_update()"),
                        native.index("input_abstraction_update()"))
        self.assertLess(native.index("input_abstraction_update()"),
                        native.index("player_control_update("))
        self.assertLess(native.index("player_control_update("),
                        native.index("game_time_update("))

    def test_c3_workload_input_is_sampled_before_player_control_each_tick(self):
        main_source = (HCU / "source/main/main.c").read_text()
        prepare = self.extract_function(
            main_source, "static void hcu_c3_workload_prepare_actions(")
        # The injected trigger must be published before the frame's pad poll
        # (XInputGetState runs inside input_frame_begin) and the abstraction
        # must run after the poll, all before player_control_update().
        self.assertLess(prepare.index("ps2_input_c3_workload_primary_trigger("),
                        prepare.index("input_frame_begin()"))
        self.assertLess(prepare.index("input_frame_begin()"),
                        prepare.index("input_update()"))
        self.assertLess(prepare.index("input_update()"),
                        prepare.index("input_abstraction_update()"))
        # Fire from tick 0, two ticks on and two off for the whole run.
        self.assertIn("fire = tick >= 0 && (tick % 4) < 2;", prepare)
        self.assertIn("#if !defined(HCU_C3_WORKLOAD_AUTOFIRE) || HCU_C3_WORKLOAD_AUTOFIRE", prepare)
        self.assertIn("fire = FALSE;", prepare)
        self.assertIn("state=armed controllers=%d pattern=2-on-2-off", prepare)
        self.assertIn("state=manual controllers=%d input=physical", prepare)
        loop_start = main_source.index("hcu_c3_workload_prepare_actions(tick);")
        loop = main_source[loop_start:loop_start + 600]
        order = ["hcu_c3_workload_prepare_actions(tick)",
                 "player_control_update(", "hcu_c3_workload_finish_actions()",
                 "game_time_update("]
        positions = [loop.index(item) for item in order]
        self.assertEqual(positions, sorted(positions))

    def test_c3_workload_reports_how_far_the_trigger_gets(self):
        weapons = (HCU / "source/items/weapons.c").read_text()
        main_source = (HCU / "source/main/main.c").read_text()
        update = weapons[weapons.index("boolean weapon_update("):]
        self.assertLess(update.index("triggers_down[0]= FALSE;"),
                        update.index("++c3_weapon_trigger_down_ticks"))
        fire = self.extract_function(weapons, "static void weapon_trigger_fire(")
        self.assertIn("++c3_weapon_shots_fired", fire)
        self.assertIn("c3-workload-fire tick=%d trigger-flag-ticks=%lu "
                      "trigger-down-ticks=%lu shots=%lu", main_source)

    def test_ce_frame_boundary_polls_four_tick_indexed_pads_before_snapshot(self):
        source = (HCU / "source/input/input_xbox.c").read_text()
        frame_begin = self.extract_function(source, "void input_frame_begin(")
        frame_end = self.extract_function(source, "void input_frame_end(")
        fixture = r"""
#include <assert.h>
#include <string.h>
#include "halo_ps2_input.h"
#include "platform/pad.h"
#include "xdk/xdk_xbox.h"
#define HALO_PS2 1
#define TRUE 1
struct { int frame_active; } input_globals;
static int frame, poll_count, event_count, events[64];
static struct _XINPUT_STATE states[4];
static void *handles[4];
XPP_DEVICE_TYPE XDEVICE_TYPE_GAMEPAD_TABLE;
static void input_get_device_states(void)
{
    unsigned long inserted = 0, removed = 0;
    int i;
    events[event_count++] = 2;
    if (XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &inserted, &removed)) {
        for (i = 0; i < 4; ++i) {
            if (removed & (1UL << i)) {
                XInputClose(handles[i]);
                handles[i] = 0;
            }
            if (inserted & (1UL << i))
                handles[i] = XInputOpen(XDEVICE_TYPE_GAMEPAD, (unsigned long)i,
                    XDEVICE_NO_SLOT, 0);
        }
    }
    for (i = 0; i < 4; ++i)
        if (handles[i])
            assert(XInputGetState(handles[i], &states[i]) == ERROR_SUCCESS);
    /* This fixture models CE's frame snapshot boundary; gamepad-state
       edge/hold conversion is exercised against the source loop separately. */
    for (i = 0; i < 4; ++i)
        if (handles[i] && (states[i].Gamepad.wButtons & XINPUT_GAMEPAD_START))
            events[event_count++] = 10 + i;
}
static void acquire_input_mutex(void) { events[event_count++] = 3; }
static void release_input_mutex(void) { }
void SetLastError(unsigned long error) { (void)error; }
int pad_poll_players(pad_sample samples[4])
{
    int i;
    ++poll_count;
    events[event_count++] = 1;
    memset(samples, 0, sizeof(pad_sample) * 4);
    if (frame == 0) {
        for (i = 0; i < 4; ++i) {
            samples[i].connected = 1;
            samples[i].buttons = PAD_BTN_START;
        }
    } else if (frame == 1) {
        samples[0].connected = 1; samples[0].buttons = PAD_BTN_START;
        samples[1].connected = 1;
        samples[3].connected = 1; samples[3].buttons = PAD_BTN_START;
    } else {
        samples[0].connected = 1; samples[0].buttons = PAD_BTN_START;
        samples[1].connected = 1;
        samples[2].connected = 1; samples[2].buttons = PAD_BTN_START;
        samples[3].connected = 1; samples[3].buttons = PAD_BTN_START;
    }
    ++frame;
    return 1;
}
""" + frame_begin + frame_end + r"""
int main(void)
{
    int expected[3][4] = {{1,1,1,1}, {1,0,0,1}, {1,0,1,1}};
    int tick, i;
    for (tick = 0; tick < 3; ++tick) {
        int begin = event_count;
        input_frame_begin();
        assert(poll_count == tick + 1);
        assert(input_globals.frame_active == TRUE);
        assert(events[begin] == 1 && events[begin + 1] == 2 &&
            events[event_count - 1] == 3);
        for (i = 0; i < 4; ++i) {
            int found = 0, j;
            for (j = begin; j < event_count; ++j)
                if (events[j] == 10 + i) found = 1;
            assert(found == expected[tick][i]);
        }
        input_frame_end();
    }
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as temp:
            cfile = Path(temp) / "ce-pad-tick-boundary.c"
            exe = Path(temp) / "ce-pad-tick-boundary"
            cfile.write_text(fixture)
            compiled = subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-D__stdcall=", "-D__fastcall=", "-D__int64=long long",
                "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                "-I" + str(HCU / "port/include"),
                "-I" + str(HCU / "port/ps2/include"),
                str(cfile), str(ROOT / "src/stream/hcu_input_bridge.c"),
                str(HCU / "port/ps2/src/ps2_input.c"), "-o", str(exe),
            ], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ce_hold_tick_helper_executes_press_hold_release_transitions(self):
        source = (HCU / "source/input/input_xbox.c").read_text()
        helper = self.extract_function(source, "static void update_hold_ticks(")
        fixture = r"""
#include <assert.h>
typedef unsigned char byte;
typedef unsigned char boolean;
#define TRUE 1
#define FALSE 0
#define UNSIGNED_CHAR_MAX 255
#define TICKS_PER_SECOND 30
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define PIN(v, lo, hi) ((v) < (lo) ? (lo) : ((v) > (hi) ? (hi) : (v)))
static long fake_now;
long system_milliseconds(void) { return fake_now; }
""" + helper + r"""
int main(void)
{
	byte ticks = 0;
	long down_time = 0;
	update_hold_ticks(&ticks, &down_time, FALSE);
	assert(ticks == 0); /* released */
	fake_now = 50;
	update_hold_ticks(&ticks, &down_time, TRUE);
	assert(ticks == 1 && down_time == 50); /* pressed edge */
	fake_now = 100;
	update_hold_ticks(&ticks, &down_time, TRUE);
	assert(ticks == 2); /* held; never repeats as another fresh press */
	fake_now = 250;
	update_hold_ticks(&ticks, &down_time, TRUE);
	assert(ticks == 7); /* 30 Hz CE hold cadence */
	update_hold_ticks(&ticks, &down_time, FALSE);
	assert(ticks == 0); /* release edge clears the held state */
	fake_now = 500;
	update_hold_ticks(&ticks, &down_time, TRUE);
	assert(ticks == 1 && down_time == 500); /* subsequent press */
	return 0;
}
"""
        with tempfile.TemporaryDirectory() as temp:
            cfile = Path(temp) / "ce-hold-ticks.c"
            exe = Path(temp) / "ce-hold-ticks"
            cfile.write_text(fixture)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(cfile), "-o", str(exe)], check=True,
                           capture_output=True, text=True)
            subprocess.run([str(exe)], check=True, capture_output=True,
                           text=True)

    def test_ce_gamepad_snapshot_reads_real_ps2_xinput_state(self):
        source = (HCU / "source/input/input_xbox.c").read_text()
        state_source = (HCU / "source/input/input.h").read_text()
        hold = self.extract_function(source, "static void update_hold_ticks(")
        analog = self.extract_function(
            source, "static void input_update_analog_button_state(")
        dead_zone = self.extract_function(source, "short fix_dead_zone(")
        getter = self.extract_function(
            source, "const struct gamepad_state *input_get_gamepad_state(")
        state_struct = self.extract_function(state_source, "struct gamepad_state\n{")
        update_start = source.rindex("static void input_get_device_states(")
        update_body = source[update_start:]
        loop_start = update_body.index("\tfor (gamepad_index = 0; gamepad_index < MAXIMUM_GAMEPADS; gamepad_index++)", update_body.index("input_abstraction_update_device_changes(device_change_flags)"))
        opening = update_body.index("{", loop_start)
        depth = 0
        loop_end = None
        for index in range(opening, len(update_body)):
            if update_body[index] == "{":
                depth += 1
            elif update_body[index] == "}":
                depth -= 1
                if depth == 0:
                    loop_end = index + 1
                    break
        self.assertIsNotNone(loop_end)
        gamepad_loop = update_body[loop_start:loop_end]
        globals_start = source.index("static const byte gamepad_analog_button_indices")
        globals_source = source[globals_start:]
        globals_source = globals_source[:globals_source.index(";", globals_source.index("static const byte gamepad_binary_button_masks")) + 1]

        fixture = r"""
#include <assert.h>
#include <string.h>
#define __stdcall
#define __fastcall
#define __int64 long long
#include "xdk/xdk_xbox.h"
#include "halo_ps2_input.h"
#define TRUE 1
#define FALSE 0
#define NONE -1
#define MAXIMUM_GAMEPADS 4
#define NUMBER_OF_GAMEPAD_ANALOG_BUTTONS 8
#define FIRST_GAMEPAD_ANALOG_BUTTON 0
#define FIRST_GAMEPAD_BINARY_BUTTON 8
#define NUMBER_OF_GAMEPAD_BINARY_BUTTONS 8
#define NUMBER_OF_GAMEPAD_BUTTONS 16
#define NUMBER_OF_GAMEPAD_STICKS 2
#define _gamepad_stick_left 0
#define _gamepad_stick_right 1
#define GAMEPAD_STICK_DEAD_RANGE 9000
#define ANALOG_BUTTON_PRESS_THRESHOLD_OFFSET 32
#define ANALOG_BUTTON_RELEASE_THRESHOLD_OFFSET 64
#define ANALOG_BUTTON_RELEASE_SATURATION 191
#define TICKS_PER_SECOND 30
#define SHORT_MAX SHRT_MAX
#define SHORT_MIN SHRT_MIN
#define UNSIGNED_CHAR_MAX 255
#define _error_silent 0
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define PIN(v,lo,hi) ((v) < (lo) ? (lo) : ((v) > (hi) ? (hi) : (v)))
#define match_assert(file,line,condition) ((void)0)
#define TEST_FLAG(flags,bit) (((flags) & (1UL << (bit))) != 0)
typedef unsigned char byte;
typedef unsigned char boolean;
typedef struct { short x, y; } point2d;
""" + state_struct + ";\n" + r"""
struct raw_gamepad_state { point2d sticks[NUMBER_OF_GAMEPAD_STICKS]; };
struct input_globals {
	void *gamepad_handles[MAXIMUM_GAMEPADS];
	struct raw_gamepad_state raw_gamepad_states[MAXIMUM_GAMEPADS];
	boolean suppressed;
	struct gamepad_state gamepad_states[MAXIMUM_GAMEPADS];
	struct gamepad_state suppressed_gamepad_state;
};
static struct input_globals input_globals;
XPP_DEVICE_TYPE XDEVICE_TYPE_GAMEPAD_TABLE;
static long gamepad_button_down_times[MAXIMUM_GAMEPADS][NUMBER_OF_GAMEPAD_BUTTONS];
static long fake_now;
long system_milliseconds(void) { return fake_now; }
short fix_dead_zone(short value, short dead_range);
void SetLastError(unsigned long error) { (void)error; }
unsigned long GetLastError(void) { return 0; }
void error(int type, const char *format, ...) { (void)type; (void)format; }
void input_abstraction_update_device_changes(unsigned long flags) { (void)flags; }
""" + globals_source + "\n" + hold + "\n" + analog + "\n" + dead_zone + "\n" + getter + "\n" + r"""
static void update_from_ps2_sample(void)
{
	short gamepad_index;
	""" + gamepad_loop + r"""
}
int main(void)
{
	XINPUT_GAMEPAD sample[MAXIMUM_GAMEPADS];
	void *handle[MAXIMUM_GAMEPADS];
	const struct gamepad_state *state;
	int i;
	memset(sample, 0, sizeof(sample));
	for (i = 0; i < MAXIMUM_GAMEPADS; ++i) {
		sample[i].wButtons = XINPUT_GAMEPAD_DPAD_UP;
		sample[i].bAnalogButtons[XINPUT_GAMEPAD_A] = (unsigned char)(200 - i);
		sample[i].sThumbLX = (short)(16000 - i * 500);
		ps2_input_publish_state((unsigned long)i, 1, &sample[i]);
		handle[i] = XInputOpen(&XDEVICE_TYPE_GAMEPAD_TABLE,
			(unsigned long)i, XDEVICE_NO_SLOT, 0);
		assert(handle[i] != 0);
		input_globals.gamepad_handles[i] = handle[i];
	}
	fake_now = 100;
	update_from_ps2_sample();
	for (i = 0; i < MAXIMUM_GAMEPADS; ++i) {
		state = input_get_gamepad_state((short)i);
		assert(state != 0);
		assert(state->buttons[0] == 1); /* analog A press */
		assert(state->buttons[8] == 1); /* D-pad up press */
		assert(state->analog_buttons[0] == (unsigned char)(200 - i));
		assert(state->sticks[_gamepad_stick_left].x > 0);
	}
	fake_now = 150;
	update_from_ps2_sample();
	for (i = 0; i < MAXIMUM_GAMEPADS; ++i) {
		state = input_get_gamepad_state((short)i);
		assert(state->buttons[0] == 2 && state->buttons[8] == 2); /* held */
		sample[i].wButtons = 0;
		sample[i].bAnalogButtons[XINPUT_GAMEPAD_A] = 0;
		ps2_input_publish_state((unsigned long)i, 1, &sample[i]);
	}
	fake_now = 200;
	update_from_ps2_sample();
	for (i = 0; i < MAXIMUM_GAMEPADS; ++i) {
		state = input_get_gamepad_state((short)i);
		assert(state->buttons[0] == 0 && state->buttons[8] == 0); /* released */
		XInputClose(handle[i]);
	}
	return 0;
}
"""
        with tempfile.TemporaryDirectory() as temp:
            cfile = Path(temp) / "ce-xinput-snapshot.c"
            exe = Path(temp) / "ce-xinput-snapshot"
            cfile.write_text(fixture)
            compiled = subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-D__stdcall=", "-D__fastcall=", "-D__int64=long long",
                "-I" + str(HCU / "port/include"),
                "-I" + str(HCU / "port/ps2/include"),
                str(cfile), str(HCU / "port/ps2/src/ps2_input.c"),
                "-o", str(exe),
            ], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0,
                             compiled.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
