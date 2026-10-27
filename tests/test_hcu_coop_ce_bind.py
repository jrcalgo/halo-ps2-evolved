"""C5: humans-on-one-team-vs-bots keeps CE's team victory and respawn rules.

The CE bodies of game_engine_should_end_game, multiple_teams_alive, game_engine_player_killed and
game_engine_should_spawn_player (with the CE helpers they call) are copied verbatim from
submodules/halo-ce-universal/source/game/game_engine.c into one generated translation unit, the same way
tests/c4_host_shims/ce_host_link_closure.py copies its bodies. Their types and host services are mocked in a
prelude; the mock field names are checked against the real CE headers below. tests/hcu_coop_ce_bind_main.c drives
them for the five team variants (team_slayer, ctf, team_oddball, team_king, team_race).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tests/c4_host_shims"))

GAME_ENGINE_C = HCU / "source/game/game_engine.c"
BUILDERS = {
    "build_game_variant_team_slayer": "team_slayer",
    "build_game_variant_ctf": "ctf",
    "build_game_variant_team_oddball": "team_oddball",
    "build_game_variant_team_king": "team_king",
    "build_game_variant_team_race": "team_race",
}
CE_FUNCTIONS = (
    "players_in_game",
    "game_engine_player_killed",
    "game_engine_should_end_game",
    "game_engine_player_is_odd_man_out",
    "game_engine_player_is_out_of_lives",
    "multiple_teams_alive",
    "game_engine_should_spawn_player",
)
CE_ENUMS = ("enum game_engine_mode", "enum game_engine_message")

# (CE header, struct tag, fields the mock must share with the real struct)
REAL_STRUCTS = (
    ("source/game/players.h", "struct player_datum", (
        "team_index", "unit_index", "quit_out_of_game", "quit_out_of_game_time", "respawn_timer",
        "respawn_penalty", "death_time", "statistics", "network_player_data", "local_player_index")),
    ("source/game/players.h", "struct network_player", ("team_index", "player_list_index")),
    ("source/game/game.h", "struct game_statistics", ("deaths", "multiple_kills", "kills_in_a_row")),
    ("source/game/game_engine.h", "struct universal_variant", (
        "teams", "odd_man_out", "respawn_time_growth", "respawn_time", "suicide_penalty", "lives",
        "score_to_win")),
    ("source/game/game_engine.h", "struct game_variant", ("game_engine_index", "universal_variant")),
    ("source/game/game_engine.h", "struct game_variant_options", (
        "time_limit", "friendly_fire_penalty", "auto_team_balance")),
    ("source/game/game_engine.h", "struct game_engine", ("player_killed_player",)),
    ("source/game/game_engine.c", "struct game_engine_globals", ("postgame_state",)),
    ("source/networking/network_game_manager.h", "struct network_game", ("players",)),
)

PRELUDE = r"""
#include <stddef.h>
#include <string.h>

typedef char boolean;
typedef unsigned char byte;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define TICKS_PER_SECOND 30
#define UNSIGNED_SHORT_MAX 0xFFFF
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 16
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define VALID_INDEX(index, count) (index>=0 && index<count)
#define DATUM_INDEX_TO_ABSOLUTE_INDEX(datum_index) ((datum_index)&UNSIGNED_SHORT_MAX)
#define match_assert(file, line, expression) ce_match_assert((expression) != 0, (long)(line))

enum { _multiplayer_sound_countdown_for_respawn = 1, _multiplayer_sound_respawn };
enum { _object_type_biped = 1, _object_type_vehicle };

struct data_array { int unused; };
struct data_iterator { long datum_index; long cursor; };
struct game_statistics { long deaths; long multiple_kills; long kills_in_a_row; };
struct network_player { char team_index; char player_list_index; };
struct player_datum {
	long team_index; long unit_index; boolean quit_out_of_game; long quit_out_of_game_time;
	long respawn_timer; long respawn_penalty; long death_time; short local_player_index;
	struct network_player network_player_data; struct game_statistics statistics;
};
struct universal_variant {
	boolean teams; boolean odd_man_out; long respawn_time_growth; long respawn_time;
	long suicide_penalty; long lives; long score_to_win;
};
struct game_variant {
	long game_engine_index; struct universal_variant universal_variant;
	union { long pad[8]; } game_engine_variant;
};
struct game_variant_options { short time_limit; short friendly_fire_penalty; boolean auto_team_balance; };
struct game_engine { long type; void (*player_killed_player)(long, long, long, boolean); };
struct game_engine_globals { long postgame_state; };
struct object_datum { struct { short type; } object; };
struct network_game_player { char team_index; };
struct network_game { struct network_game_player players[HALO_PORT_MAXIMUM_NETWORK_PLAYERS]; };
struct network_game_server { int unused; };

struct game_variant global_variant;
struct game_engine *game_engine = NULL;
struct game_engine_globals game_engine_globals;
struct data_array *player_data;

static struct data_array ce_player_array;
static struct player_datum ce_players[HALO_PORT_MAXIMUM_NETWORK_PLAYERS];
static int ce_in_use[HALO_PORT_MAXIMUM_NETWORK_PLAYERS];
static struct game_variant_options ce_options;
static struct game_engine ce_engine;
static long ce_game_time;
static long ce_asserts;

void ce_match_assert(int ok, long line);
void data_iterator_new(struct data_iterator *iterator, struct data_array *data);
void *data_iterator_next(struct data_iterator *iterator);
struct player_datum *player_get(long player_index);
struct player_datum *player_try_and_get(long player_index);
long unit_try_and_get(long unit_index);
struct object_datum *object_get(long object_index);
long game_time_get(void);
struct game_variant_options *game_variant_options_get(void);
void game_show_score_extended(long player_index, long message, long killing_player_index);
void multiplayer_message(long player_index, long message, long other_player_index);
void game_engine_play_multiplayer_sound(long sound);
void network_distributed_player_killed(long *killing_player_index, long *killing_object_index,
	long dead_player_index, boolean *friendly_fire);
boolean network_game_distributed_client(void);
struct network_game_server *global_network_game_server_get(void);
struct network_game *network_game_server_get_game(struct network_game_server *server);
long players_in_game(void);
boolean game_engine_should_end_game(void);
void game_engine_player_killed(long killing_player_index, long killing_object_index, long dead_player_index,
	boolean friendly_fire);
boolean game_engine_should_spawn_player(long player_index);
boolean multiple_teams_alive(void);
boolean game_engine_player_is_out_of_lives(long player_index);
static boolean game_engine_player_is_odd_man_out(long player_index);
"""

HOST_SERVICES = r"""
void ce_match_assert(int ok, long line)
{
	(void)line;
	if (!ok)
		ce_asserts++;
}

void data_iterator_new(struct data_iterator *iterator, struct data_array *data)
{
	(void)data;
	iterator->datum_index = NONE;
	iterator->cursor = 0;
}

void *data_iterator_next(struct data_iterator *iterator)
{
	while (iterator->cursor < HALO_PORT_MAXIMUM_NETWORK_PLAYERS)
	{
		long index = iterator->cursor++;

		if (ce_in_use[index])
		{
			iterator->datum_index = index;
			return &ce_players[index];
		}
	}
	return NULL;
}

struct player_datum *player_get(long player_index)
{
	return &ce_players[player_index];
}

struct player_datum *player_try_and_get(long player_index)
{
	if (player_index >= 0 && player_index < HALO_PORT_MAXIMUM_NETWORK_PLAYERS && ce_in_use[player_index])
		return &ce_players[player_index];
	return NULL;
}

long unit_try_and_get(long unit_index)
{
	return unit_index;
}

static struct object_datum ce_object;

struct object_datum *object_get(long object_index)
{
	(void)object_index;
	ce_object.object.type = _object_type_biped;
	return &ce_object;
}

long game_time_get(void)
{
	return ce_game_time;
}

struct game_variant_options *game_variant_options_get(void)
{
	return &ce_options;
}

void game_show_score_extended(long player_index, long message, long killing_player_index)
{
	(void)player_index; (void)message; (void)killing_player_index;
}

void multiplayer_message(long player_index, long message, long other_player_index)
{
	(void)player_index; (void)message; (void)other_player_index;
}

void game_engine_play_multiplayer_sound(long sound)
{
	(void)sound;
}

void network_distributed_player_killed(long *killing_player_index, long *killing_object_index,
	long dead_player_index, boolean *friendly_fire)
{
	(void)killing_player_index; (void)killing_object_index; (void)dead_player_index; (void)friendly_fire;
}

boolean network_game_distributed_client(void)
{
	return FALSE;
}

/* no network server in the host proof: the lobby team write is skipped */
struct network_game_server *global_network_game_server_get(void)
{
	return NULL;
}

struct network_game *network_game_server_get_game(struct network_game_server *server)
{
	(void)server;
	return NULL;
}

/* ---- harness: state setters and result readers used by tests/hcu_coop_ce_bind_main.c ---- */
void ce_harness_reset(void)
{
	memset(ce_players, 0, sizeof(ce_players));
	memset(ce_in_use, 0, sizeof(ce_in_use));
	memset(&global_variant, 0, sizeof(global_variant));
	memset(&ce_options, 0, sizeof(ce_options));
	memset(game_engine_betrayal_penalty, 0, sizeof(game_engine_betrayal_penalty));
	ce_game_time = 0;
	ce_asserts = 0;
	player_data = &ce_player_array;
	ce_engine.type = 0;
	ce_engine.player_killed_player = NULL;
	game_engine = &ce_engine;
	game_engine_globals.postgame_state = game_engine_mode_active;
}

void ce_harness_set_variant(long engine_index, int teams, long respawn_time, long respawn_time_growth,
	long suicide_penalty, long score_to_win, long lives, int odd_man_out)
{
	global_variant.game_engine_index = engine_index;
	global_variant.universal_variant.teams = (boolean)(teams != 0);
	global_variant.universal_variant.respawn_time = respawn_time;
	global_variant.universal_variant.respawn_time_growth = respawn_time_growth;
	global_variant.universal_variant.suicide_penalty = suicide_penalty;
	global_variant.universal_variant.score_to_win = score_to_win;
	global_variant.universal_variant.lives = lives;
	global_variant.universal_variant.odd_man_out = (boolean)(odd_man_out != 0);
}

void ce_harness_set_auto_team_balance(int on)
{
	ce_options.auto_team_balance = (boolean)(on != 0);
}

void ce_harness_set_friendly_fire_penalty(long seconds)
{
	ce_options.friendly_fire_penalty = (short)seconds;
}

void ce_harness_set_time_limit(long minutes)
{
	ce_options.time_limit = (short)minutes;
}

void ce_harness_set_game_time(long ticks)
{
	ce_game_time = ticks;
}

void ce_harness_add_player(long index, long team_index, int has_unit)
{
	struct player_datum *player = &ce_players[index];

	memset(player, 0, sizeof(*player));
	ce_in_use[index] = 1;
	player->team_index = team_index;
	player->network_player_data.team_index = (char)team_index;
	player->network_player_data.player_list_index = (char)index;
	player->unit_index = has_unit ? index + 100 : NONE;
	player->quit_out_of_game_time = NONE;
	player->local_player_index = NONE;
}

void ce_harness_set_quit(long index)
{
	ce_players[index].quit_out_of_game = TRUE;
}

void ce_harness_set_unit(long index, int has_unit)
{
	ce_players[index].unit_index = has_unit ? index + 100 : NONE;
}

void ce_harness_set_deaths(long index, long deaths)
{
	ce_players[index].statistics.deaths = deaths;
}

long ce_harness_team_of(long index)
{
	return ce_players[index].team_index;
}

long ce_harness_respawn_timer(long index)
{
	return ce_players[index].respawn_timer;
}

long ce_harness_match_asserts(void)
{
	return ce_asserts;
}

/* ---- entry points with plain C types for the driver ---- */
int ce_entry_should_end_game(void)
{
	return game_engine_should_end_game() ? 1 : 0;
}

int ce_entry_multiple_teams_alive(void)
{
	return multiple_teams_alive() ? 1 : 0;
}

void ce_entry_player_killed(long killer, long object, long dead, int friendly_fire)
{
	game_engine_player_killed(killer, object, dead, friendly_fire ? TRUE : FALSE);
}

int ce_entry_should_spawn_player(long index)
{
	return game_engine_should_spawn_player(index) ? 1 : 0;
}
"""


def extract_function(source: str, name: str) -> str:
    """Verbatim definition of `name`: a column-0 return type, the name, a braced body (as ce_host_link_closure).

    The stricter prefix matters here: game_engine.c calls players_in_game() inside an if whose brace is on the
    next line, which the looser pattern in ce_host_link_closure also matches.
    """
    pattern = re.compile(r"^(?:static\s+)?[A-Za-z_][\w ]*\s+" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", re.M)
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition of {name}, found {len(matches)}")
    start = matches[0].start()
    depth = 0
    for index in range(source.index("{", matches[0].start()), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated definition of {name}")


def extract_block(source: str, header: str) -> str:
    """Return a top-level `header` + braced block + ';' verbatim (enums)."""
    matches = list(re.finditer(r"^" + re.escape(header) + r"\n\{", source, re.M))
    if len(matches) != 1:
        raise AssertionError(f"expected one {header!r}, found {len(matches)}")
    depth = 0
    for index in range(matches[0].end() - 1, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[matches[0].start():source.index(";", index) + 1]
    raise AssertionError(f"unterminated {header!r}")


def extract_betrayal_declaration(source: str) -> str:
    matches = list(re.finditer(r"^static short game_engine_betrayal_penalty\[[^\n]*\n", source, re.M))
    if len(matches) != 1:
        raise AssertionError(f"expected one betrayal penalty declaration, found {len(matches)}")
    return matches[0].group(0)


def _ce_source() -> str:
    """game_engine.c without its leading symbol-map comment, which mentions every function name."""
    source = GAME_ENGINE_C.read_text(errors="replace")
    return re.sub(r"\A/\*.*?\*/", "", source, count=1, flags=re.S)


def build_closure_source() -> str:
    source = _ce_source()
    parts = [PRELUDE]
    for header in CE_ENUMS:
        parts.append(extract_block(source, header) + "\n")
    parts.append(extract_betrayal_declaration(source) + "\n")
    for name in CE_FUNCTIONS:
        parts.append(extract_function(source, name) + "\n")
    parts.append(HOST_SERVICES)
    return "\n".join(parts)


def _struct_body(source: str, tag: str) -> str:
    matches = list(re.finditer(r"^" + re.escape(tag) + r"\s*\n\{", source, re.M))
    assert len(matches) == 1, tag
    depth = 0
    for index in range(matches[0].end() - 1, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[matches[0].start():index + 1]
    raise AssertionError(tag)


def test_mock_fields_exist_in_real_ce_structs():
    for relative, tag, fields in REAL_STRUCTS:
        body = _struct_body((HCU / relative).read_text(errors="replace"), tag)
        for field in fields:
            assert re.search(r"\b" + re.escape(field) + r"\b", body), f"{tag}.{field} missing in {relative}"


def test_builders_match_bound_team_values():
    """The bound values (lives 0, no odd-man-out, no respawn growth, teams TRUE) are the CE builder values."""
    source = GAME_ENGINE_C.read_text(errors="replace")
    for builder in BUILDERS:
        match = re.search(r"struct game_variant \*%s\(.*?\n\}\n" % builder, source, re.S)
        assert match, builder
        body = match.group(0)
        assert re.search(r"teams\s*=\s*TRUE;", body), builder
        assert re.search(r"lives\s*=\s*0;", body), builder
        assert re.search(r"odd_man_out\s*=\s*FALSE;", body), builder
        assert re.search(r"respawn_time_growth\s*=\s*0;", body), builder


def test_extracted_bodies_are_single_definitions():
    source = _ce_source()
    for name in CE_FUNCTIONS:
        extract_function(source, name)
    assert "game_engine_betrayal_penalty" in extract_betrayal_declaration(source)


def test_bind_table_matches_ce_teams_and_runs(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")

    closure = tmp_path / "hcu_coop_ce_closure.c"
    closure.write_text(build_closure_source())
    exe = tmp_path / "hcu_coop_ce_bind_test"
    compile_cmd = [
        compiler, "-std=gnu11", "-Wall", "-Wno-unused-function", "-Wno-unused-variable",
        "-Wno-unused-but-set-variable", "-Wno-unused-parameter", "-Wno-unused-value",
        "-Wno-sign-compare", "-Wno-pointer-sign", "-Isrc",
        "tests/hcu_coop_ce_bind_main.c",
        "src/stream/hcu_coop_ce_bind.c",
        "src/stream/hcu_coop_modes.c",
        str(closure),
        "-o", str(exe),
    ]
    compiled = subprocess.run(compile_cmd, cwd=ROOT, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu_coop_ce_bind tests passed" in result.stdout, result.stdout
