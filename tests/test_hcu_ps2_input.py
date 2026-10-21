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

    def test_dualshock_conversion_connection_and_packet_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hcu-ps2-input"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
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
            subprocess.run([str(exe)], check=True, capture_output=True,
                           text=True)

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
	XINPUT_GAMEPAD sample;
	void *handle;
	const struct gamepad_state *state;
	memset(&sample, 0, sizeof(sample));
	sample.wButtons = XINPUT_GAMEPAD_DPAD_UP;
	sample.bAnalogButtons[XINPUT_GAMEPAD_A] = 200;
	sample.sThumbLX = 16000;
	ps2_input_publish_state(0, 1, &sample);
	handle = XInputOpen(&XDEVICE_TYPE_GAMEPAD_TABLE, 0, XDEVICE_NO_SLOT, 0);
	assert(handle != 0);
	input_globals.gamepad_handles[0] = handle;
	fake_now = 100;
	update_from_ps2_sample();
	state = input_get_gamepad_state(0);
	assert(state != 0);
	assert(state->buttons[0] == 1); /* analog A press */
	assert(state->buttons[8] == 1); /* D-pad up press */
	assert(state->analog_buttons[0] == 200);
	assert(state->sticks[_gamepad_stick_left].x > 9000);
	fake_now = 150;
	update_from_ps2_sample();
	state = input_get_gamepad_state(0);
	assert(state->buttons[0] == 2 && state->buttons[8] == 2); /* held */
	sample.wButtons = 0;
	sample.bAnalogButtons[XINPUT_GAMEPAD_A] = 0;
	ps2_input_publish_state(0, 1, &sample);
	fake_now = 200;
	update_from_ps2_sample();
	state = input_get_gamepad_state(0);
	assert(state->buttons[0] == 0 && state->buttons[8] == 0); /* released */
	XInputClose(handle);
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
            subprocess.run([str(exe)], check=True, capture_output=True,
                           text=True)


if __name__ == "__main__":
    unittest.main()
