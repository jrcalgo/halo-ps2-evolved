"""Execute the pinned CE game_tick body with deterministic phase stubs."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
GAME_C = ROOT / "submodules/halo-ce-universal/source/game/game.c"
UNITS_C = ROOT / "submodules/halo-ce-universal/source/units/units.c"


def extract_function(source: str, signature: str) -> str:
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
    raise AssertionError(f"unterminated function: {signature}")


def extract_unique_function(source: str, name: str) -> str:
    import re

    matches = list(re.finditer(
        r"^[ \t]*(?:static\s+)?[\w\s*]+\b" + re.escape(name) +
        r"\s*\([^;{}]*\)\s*\{", source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition of {name}, found {len(matches)}")
    start = matches[0].start()
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
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


def test_real_ce_game_tick_executes_local_phases_once_in_source_order():
    source = GAME_C.read_text()
    tick = extract_function(source, "void game_tick(")
    units_source = UNITS_C.read_text()
    units_update = extract_unique_function(units_source, "units_update")
    unit_globals_struct = extract_struct(units_source, "unit_globals")
    harness = r"""
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef float real;
typedef unsigned char byte;
typedef byte boolean;
#include "ps2_animation_trace.h"
#define TRUE 1
#define FALSE 0
#define TICKS_PER_SECOND 30
""" + unit_globals_struct + r"""
enum {
  game_update_section = 1, game_tick_cheats_enforce_section,
  game_tick_remove_quitting_players_section, game_tick_allegiance_section,
  game_tick_units_section, game_tick_ai_section,
  game_tick_actors_drive_section, game_tick_players_before_section,
  game_tick_effects_section, game_tick_antennas_section,
  game_tick_first_person_section, game_tick_game_engine_section,
  game_tick_editor_section, game_tick_hs_section,
  game_tick_recorded_animations_section, game_tick_objects_section,
  game_tick_players_after_section, game_tick_hud_section,
  game_tick_player_effect_section
};
struct game_globals_definition {
  boolean active;
  boolean players_are_double_speed;
};
static struct game_globals_definition globals;
static struct game_globals_definition *game_globals = &globals;
static struct unit_globals unit_globals_storage;
static struct unit_globals *unit_globals = &unit_globals_storage;
static unsigned events[64], event_count;
static uint32_t state_hash = 2166136261u;
static unsigned simulated_rng = 0x12345678u;
static real expected_delta;
static struct ps2_animation_trace_event trace_events[8];
static struct ps2_animation_trace_context trace_contexts[8];
static unsigned long trace_tick_sample(void)
{
  long row = ps2_animation_trace_count();
  ps2_animation_trace_record(_ps2_animation_trace_frame_info, NULL, NULL,
    0, 0, 0, 1);
  assert(ps2_animation_trace_count() == row + 1);
  assert(ps2_animation_trace_events()[row].context_token == row + 1);
  assert(ps2_animation_trace_contexts()[row].valid_mask &
    _ps2_animation_trace_context_tick);
  return ps2_animation_trace_contexts()[row].tick;
}
static void event(unsigned code)
{
  assert(event_count < sizeof(events) / sizeof(events[0]));
  events[event_count++] = code;
  state_hash = (state_hash ^ code) * 16777619u;
}
#define profile_scope(section, ...) do { event((unsigned)(section) + 100u); \
  __VA_ARGS__; } while (0);
#define profile_enter(section) event((unsigned)(section) + 200u)
#define profile_exit(section) event((unsigned)(section) + 300u)
void profile_tick_start(void) { event(1); }
void collision_log_begin_period(int value) { event(2u + (unsigned)value); }
void collision_log_end_period(void) { event(4); }
void profile_tick_end(void) { event(5); }
void real_math_reset_precision(void) { event(6); }
void match_assert(const char *file, int line, int condition)
{ (void)file; (void)line; assert(condition); }
void game_state_check_data_arrays(void) { event(7); }
void lights_port_recover(void) { event(8); }
void cheats_network_client_enforce(void) { event(9); }
void remove_quitting_players_from_game(void) { event(10); }
void game_allegiance_update(void) { event(11); }
""" + units_update + r"""
boolean network_game_distributed_client(void) { return FALSE; }
void ai_update(void) { event(13); }
void network_actors_drive(void) { event(14); }
void players_update_before_game(void) { event(15); }
void effects_update(real delta) { assert(delta == expected_delta); event(16); }
void antennas_update(real delta) { assert(delta == expected_delta); event(17); }
void lock_global_random_seed(void) { event(18); }
void rumble_update(void) { event(19); }
void first_person_weapons_update(void)
{ event(20); simulated_rng = simulated_rng * 1664525u + 1013904223u; }
void unlock_global_random_seed(void) { event(21); }
void game_engine_update(void) { event(22); }
void editor_update(void) { event(23); }
boolean network_coop_active(void) { return FALSE; }
void hs_update(void) { event(24); }
void recorded_animations_update(void) { event(25); }
void objects_update(void) { event(26); }
void players_update_after_game(void) { event(27); }
void hud_update(void) { event(28); }
void player_effect_update(void) { event(29); }
""" + tick + r"""
static void reset_fixture(boolean double_speed)
{
  ps2_animation_trace_reset();
  memset(events, 0, sizeof(events));
  event_count = 0;
  state_hash = 2166136261u;
  simulated_rng = 0x12345678u;
  globals.active = TRUE;
  globals.players_are_double_speed = double_speed;
  unit_globals_storage.next_timer = 7;
  unit_globals_storage.highest_timer = 19;
  unit_globals_storage.used_time = TRUE;
  expected_delta = double_speed ? 1.0f / 60.0f : 1.0f / 30.0f;
}
int main(void)
{
  static const unsigned expected[] = {
    1, 2, 6, 201, 7, 8, 102, 9, 103, 10, 104, 11,
    105, 106, 13, 108, 15, 109, 16, 110, 17,
    111, 18, 19, 20, 21, 112, 22, 113, 23, 114,
    24, 115, 25, 116, 26, 117, 27, 118, 28, 119,
    29, 7, 8, 301, 4, 5
  };
  uint32_t first_hash, double_hash;
  unsigned first_rng, double_rng, i;
  assert(ps2_animation_trace_bind(trace_events, 8));
  assert(ps2_animation_trace_bind_contexts(trace_contexts, 8));
  reset_fixture(FALSE);
  game_tick();
  assert(trace_tick_sample() == 1);
  assert(unit_globals_storage.next_timer == 19);
  assert(unit_globals_storage.highest_timer == 0);
  assert(unit_globals_storage.used_time == FALSE);
  if (event_count != sizeof(expected) / sizeof(expected[0])) {
    fprintf(stderr, "event count %u expected %u\n", event_count,
      (unsigned)(sizeof(expected) / sizeof(expected[0])));
    for (i = 0; i < event_count; ++i) fprintf(stderr, "%u ", events[i]);
    fputc('\n', stderr);
  }
  assert(event_count == sizeof(expected) / sizeof(expected[0]));
  for (i = 0; i < event_count; ++i) {
    if (events[i] != expected[i])
      fprintf(stderr, "event[%u]=%u expected=%u\n", i, events[i], expected[i]);
    assert(events[i] == expected[i]);
  }
  assert(simulated_rng != 0x12345678u);
  first_hash = state_hash;
  first_rng = simulated_rng;
  reset_fixture(FALSE);
  game_tick();
  assert(trace_tick_sample() == 1);
  assert(unit_globals_storage.next_timer == 19);
  assert(unit_globals_storage.highest_timer == 0);
  assert(unit_globals_storage.used_time == FALSE);
  assert(state_hash == first_hash && simulated_rng == first_rng);
  reset_fixture(TRUE);
  game_tick();
  assert(trace_tick_sample() == 1);
  assert(unit_globals_storage.next_timer == 19);
  assert(unit_globals_storage.highest_timer == 0);
  assert(unit_globals_storage.used_time == FALSE);
  assert(simulated_rng != 0x12345678u);
  double_hash = state_hash;
  double_rng = simulated_rng;
  reset_fixture(TRUE);
  game_tick();
  assert(trace_tick_sample() == 1);
  assert(unit_globals_storage.next_timer == 19);
  assert(unit_globals_storage.highest_timer == 0);
  assert(unit_globals_storage.used_time == FALSE);
  assert(state_hash == double_hash && simulated_rng == double_rng);
  return 0;
}
"""
    with tempfile.TemporaryDirectory(prefix="hcu-ce-game-tick-") as temp:
        cfile = Path(temp) / "game-tick-fixture.c"
        exe = Path(temp) / "game-tick-fixture"
        cfile.write_text(harness)
        built = subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
             "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
             str(cfile),
             str(ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_animation_trace.c"),
             "-o", str(exe)], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr
        result = subprocess.run([str(exe)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
