"""Exercise CE's actual fixed-step scheduler body with deterministic host stubs.

This ILP32 host fixture compiles the source-extracted ``game_time_update`` body,
not a Python reimplementation. Engine services are stubs, so it proves scheduler
control flow and call ordering only; it does not qualify EE timing or gameplay.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
UNITS_C = HCU / "source/units/units.c"
sys.path.insert(0, str(ROOT / "tools"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402


def extract_function(source: str, name: str) -> str:
    """Return one C function by balanced-brace extraction, failing closed."""
    import re

    matches = list(re.finditer(
        r"^[ \t]*(?:static\s+)?[\w\s*]+\b" + re.escape(name) +
        r"\s*\([^;{}]*\)\s*\{", source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition of {name}, found {len(matches)}")
    start = matches[0].start()
    brace = source.find("{", matches[0].start())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function {name}")


def extract_struct(source: str, name: str) -> str:
    import re

    matches = list(re.finditer(
        r"^[ \t]*struct\s+" + re.escape(name) + r"\s*\{",
        source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition of struct {name}, found {len(matches)}")
    start = matches[0].start()
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1] + ";"
    raise AssertionError(f"unterminated struct {name}")


HARNESS_PREFIX = r'''
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef float real;
typedef int boolean;
#define TRUE 1
#define FALSE 0
#define TICKS_PER_SECOND 30
#define SOME_LARGE_NUMBER_OF_TICKS 1000
#define PIN(x, lo, hi) ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define match_assert(file, line, condition) ((void)0)
#define profile_scope(section, statement) statement
enum { _game_connection_local, _game_connection_network_client,
       _game_connection_network_server, _game_connection_film_playback };
struct game_time_globals_struct {
    boolean initialized, active, paused;
    short monitor_state, monitor_counter, monitor_latency;
    long local_time;
    short last_local_time_elapsed;
    long server_time;
    real speed, leftover_dt;
};
static struct game_time_globals_struct *game_time_globals;
static long selected_connection = _game_connection_local;
static long maximum_server_time = 100000;
static int events[128], event_count, local_update_ticks;
static int frame_begin_count, frame_end_count, game_frame_count;
static real game_frame_delta;
long game_connection(void);
void update_client_local_ticks(long ticks);
void network_game_server_update_ticks(void *server, short ticks);
void *global_network_game_server_get(void);
long update_client_get_maximum_possible_server_time(void);
boolean game_time_held(void);
void game_tick(void);
void render_interpolation_tick(void);
void network_distributed_tick(void);
void render_interpolation_frame_begin(void);
real game_time_get_speed(void);
void game_frame(real delta);
void render_interpolation_frame_end(void);
'''

HARNESS_SUFFIX = r'''
long game_connection(void) { return selected_connection; }
void update_client_local_ticks(long ticks) { local_update_ticks += (int)ticks; events[event_count++] = 4; }
void network_game_server_update_ticks(void *server, short ticks) { (void)server; (void)ticks; }
void *global_network_game_server_get(void) { return NULL; }
long update_client_get_maximum_possible_server_time(void) { return maximum_server_time; }
boolean game_time_held(void) { return FALSE; }
real game_time_get_speed(void) { return game_time_globals->speed; }
void game_tick(void) { events[event_count++] = 1; }
void render_interpolation_tick(void) { events[event_count++] = 2; }
void network_distributed_tick(void) { events[event_count++] = 3; }
void render_interpolation_frame_begin(void) { frame_begin_count++; events[event_count++] = 5; }
void game_frame(real delta) { game_frame_count++; game_frame_delta = delta; events[event_count++] = 6; }
void render_interpolation_frame_end(void) { frame_end_count++; events[event_count++] = 7; }

static void reset_case(real speed, real leftover, long local_time) {
    static struct game_time_globals_struct globals;
    memset(&globals, 0, sizeof(globals));
    globals.active = TRUE; globals.speed = speed; globals.leftover_dt = leftover;
    globals.local_time = local_time; globals.server_time = local_time;
    game_time_globals = &globals;
    selected_connection = _game_connection_local;
    maximum_server_time = 100000;
    event_count = local_update_ticks = frame_begin_count = frame_end_count = game_frame_count = 0;
    game_frame_delta = -1.0f;
}
static int expect(int condition, const char *message) {
    if (!condition) { fprintf(stderr, "FAIL: %s\n", message); return 0; }
    return 1;
}
static int run_case(real delta, int expected_ticks, int expected_leftover_zero) {
    int i, tick_events = 0, ok = 1;
    game_time_update(delta);
    for (i = 0; i < event_count; i++) if (events[i] == 1) tick_events++;
    ok &= expect(tick_events == expected_ticks, "actual CE body tick count");
    ok &= expect(local_update_ticks == expected_ticks, "local-tick callback count");
    ok &= expect(frame_begin_count == 1 && game_frame_count == 1 && frame_end_count == 1,
                 "frame interpolation/game_frame executes once per scheduler call");
    ok &= expect(game_time_globals->last_local_time_elapsed == expected_ticks,
                 "elapsed time reports ticks for this frame only");
    ok &= expect(game_time_globals->local_time == expected_ticks,
                 "local clock advances once for each executed tick");
    ok &= expect(unit_globals_storage.next_timer ==
                 (expected_ticks ? expected_ticks : 42),
                 "real CE unit phase runs once per scheduled tick");
    ok &= expect(unit_globals_storage.highest_timer == 0 &&
                 unit_globals_storage.used_time == FALSE,
                 "real CE unit phase clears the per-tick timer state");
    if (expected_leftover_zero)
        ok &= expect(game_time_globals->leftover_dt < 0.00001f,
                     "capped local frame discards excess accumulated time");
    for (i = 0; i < expected_ticks; i++) {
        int base = 1 + i * 3;
        ok &= expect(events[base] == 1 && events[base + 1] == 2 && events[base + 2] == 3,
                     "each tick orders game, interpolation, then distributed state");
    }
    ok &= expect(events[event_count - 3] == 5 && events[event_count - 2] == 6 &&
                 events[event_count - 1] == 7,
                 "one frame begin/game_frame/frame end follows all fixed ticks");
    return ok;
}
int main(void) {
    int ok = 1;
    reset_case(1.0f, 0.0f, 0);
    ok &= run_case(0.01f, 0, 0);
    reset_case(1.0f, 0.0f, 0);
    ok &= run_case(0.034f, 1, 0);
    reset_case(1.0f, 0.0f, 0);
    ok &= run_case(0.101f, 3, 0);
    reset_case(1.0f, 0.0f, 0);
    ok &= run_case(0.5f, 7, 1);
    if (!ok) return 1;
    puts("actual-ce-game-time-update ticks=0,1,3,7 local-cap=7 frame-sampling=once status=passed");
    return 0;
}
'''


class HcuGameTimeSchedulerTest(unittest.TestCase):
    def test_extracted_ce_scheduler_and_main_loop_frame_boundary(self):
        """Host stubs isolate scheduler arithmetic; main-loop sampling is source-checked."""
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC unavailable for HCU scheduler host fixture")
        game_time_path = HCU / "source/game/game_time.c"
        main_path = HCU / "source/main/main.c"
        units_source = UNITS_C.read_text()
        game_time_source = game_time_path.read_text()
        main_source = main_path.read_text()
        update_body = extract_function(game_time_source, "game_time_update")
        main_iteration = extract_function(main_source, "main_loop_iteration")
        unit_struct = extract_struct(units_source, "unit_globals")
        unit_update = extract_function(units_source, "units_update")
        self.assertEqual(units_source.count("void units_update("), 1)

        # Input is sampled outside the fixed-tick body, once in each source loop
        # iteration, and game_time_update is invoked at most once in that iteration.
        self.assertEqual(update_body.count("input_frame_begin("), 0)
        self.assertEqual(main_iteration.count("input_frame_begin("), 1)
        self.assertEqual(main_iteration.count("game_time_update("), 1)
        self.assertLess(main_iteration.index("input_frame_begin("),
                        main_iteration.index("game_time_update("))

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            harness = temp / "scheduler.c"
            executable = temp / "scheduler-test"
            prefix = HARNESS_PREFIX.replace(
                "typedef int boolean;",
                "typedef unsigned char byte; typedef byte boolean;")
            prefix = prefix.replace(
                "#define TICKS_PER_SECOND 30",
                "#define TICKS_PER_SECOND 30\n" + unit_struct +
                "\nstatic struct unit_globals unit_globals_storage;" +
                "\nstatic struct unit_globals *unit_globals = &unit_globals_storage;" +
                "\nstatic short unit_test_tick;")
            prefix += "\n" + unit_update + "\n"
            suffix = HARNESS_SUFFIX.replace(
                "void game_tick(void) { events[event_count++] = 1; }",
                "void game_tick(void) { unit_globals->highest_timer = ++unit_test_tick; "
                "unit_globals->used_time = TRUE; units_update(); events[event_count++] = 1; }")
            suffix = suffix.replace(
                "game_time_globals = &globals;",
                "game_time_globals = &globals; memset(&unit_globals_storage, 0, "
                "sizeof(unit_globals_storage)); unit_globals_storage.next_timer = 42; "
                "unit_test_tick = 0;")
            harness.write_text(prefix + update_body + suffix)
            command = [compiler, *host_abi32_flags(), "-std=gnu89", "-Werror",
                       str(harness), "-lm", "-o", str(executable)]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            if run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout.strip(),
                             "actual-ce-game-time-update ticks=0,1,3,7 local-cap=7 "
                             "frame-sampling=once status=passed")


if __name__ == "__main__":
    unittest.main()
