#!/usr/bin/env python3
"""Pin the Step 8 workload boundary between player units and CE AI actors."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CE = ROOT / "submodules/halo-ce-universal/source"


def function_body(source: str, signature: str) -> str:
	start = source.index(signature)
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


def main() -> None:
	fixture_source = (CE / "main/ps2_m2_ui_lifecycle_test.c").read_text()
	fixture_start = fixture_source.index('char scenario_name[] = "levels\\\\test\\\\sidewinder')
	fixture_end = fixture_source.index("step8-mp-workload-complete", fixture_start)
	fixture = fixture_source[fixture_start:fixture_end]
	players_source = (CE / "game/players.c").read_text()
	actors_source = (CE / "ai/actors.c").read_text()
	ai_source = (CE / "ai/ai.c").read_text()
	limits = (ROOT / "submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h").read_text()

	spawn = function_body(players_source, "static void player_spawn(")
	actor_new = function_body(actors_source, "long actor_new(")
	actor_create = function_body(actors_source, "long actor_create_for_unit(")
	actors_initialize = function_body(actors_source, "void actors_initialize(")
	ai_initialize = function_body(ai_source, "void ai_initialize(")

	assert "player_control_update(1.0f / 30.0f)" in fixture
	assert "game_time_update(1.0f / 30.0f)" in fixture
	assert "object_new(&placement_data)" in spawn
	assert "actor_new(" not in spawn and "actor_create_for_unit(" not in spawn
	assert "actor_create_for_unit(" not in fixture and "actor_new(" not in fixture
	assert "actor_index = actor_new(actor_variant_definition_index)" in actor_create
	assert "actor_index = datum_new(actor_data)" in actor_new
	assert 'game_state_data_new("actor", MAXIMUM_ACTORS, sizeof(struct actor_datum))' in actors_initialize
	assert "actors_initialize();" in ai_initialize
	assert "HALO_PORT_GAME_STATE_CPU_SIZE 0x305000" in limits
	assert "HALO_PORT_GAME_STATE_GPU_SIZE 0x40000" in limits
	assert "HALO_PORT_OBJECT_MEMORY_POOL_SIZE 0x100000" in limits
	assert "HALO_PORT_MAXIMUM_ACTORS 256" in limits
	print("step8-ce-actor-boundary local_players=real-ce-player-spawn units=object_new ai_actor_records=not-spawned actor_pool=game_state_data_new max_actors=256 actor_objects=not-measured")


if __name__ == "__main__":
	main()
