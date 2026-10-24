#!/usr/bin/env python3
"""Guard the Step 8 fixture's CE local-match frame/queue producer order."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c"


def main() -> int:
	text = SOURCE.read_text()
	start = text.index("HALO_PS2_LOCAL step8-mp-workload-profile")
	end = text.index("HALO_PS2_LOCAL step8-mp-workload map=sidewinder", start)
	fixture = text[start:end]
	control = fixture.index("player_control_update(1.0f / 30.0f)")
	clock = fixture.index("game_time_update(1.0f / 30.0f)")
	if control > clock:
		raise AssertionError("CE input collection must precede local game-time tick production")
	if "game_tick();" in fixture:
		raise AssertionError("fixture must not bypass CE's update queue by calling game_tick directly")
	if "update_client_dequeue" in fixture or "update_server_next_update" in fixture:
		raise AssertionError("fixture must use the real CE producer/consumer path, not queue internals")
	cleanup_start = text.index("static boolean step8_workload_cleanup(void)\n{")
	cleanup_end = text.index("\n}\n#endif", cleanup_start)
	cleanup = text[cleanup_start:cleanup_end]
	if cleanup.index("game_dispose_from_old_map();") > cleanup.index("game_unload();"):
		raise AssertionError("old-map CE state must be disposed before scenario unload releases tags")
	if "!player_data->valid" not in cleanup or "!team_data->valid" not in cleanup:
		raise AssertionError("teardown must verify player/team datum arrays were invalidated")
	if "local_player_count() == 0" in cleanup or "local_player_exists(" in cleanup:
		raise AssertionError("cached player count is retained and invalid datum arrays cannot be iterated")
	if "MAXIMUM_LOCAL_PLAYERS = 4" not in (ROOT / "submodules/halo-ce-universal/source/game/players.h").read_text():
		raise AssertionError("four-player fixture must track CE's supported local-player maximum")
	if "HALO_PS2_STEP8_MP_WORKLOAD_PLAYERS != 2 && HALO_PS2_STEP8_MP_WORKLOAD_PLAYERS != 4" not in text:
		raise AssertionError("workload must retain 2-player baseline and constrain the four-player profile")
	if "player < STEP8_MP_WORKLOAD_PLAYERS" not in fixture or "duplicate-player-index" not in fixture:
		raise AssertionError("each requested local slot must resolve to a distinct CE player and live unit")
	if "HALO_PS2_STEP8_MP_WORKLOAD_PLAYERS={args.step8_mp_workload_players}" not in (ROOT / "tools/hcu_ps2_closure.py").read_text():
		raise AssertionError("closure profile must define the chosen workload player count")
	print("step8-workload-source frame_order=player_control_update,game_time_update players=2-or-4 distinct-live-units=yes teardown=dispose-before-unload direct_game_tick=absent")
	return 0


if __name__ == "__main__":
	main()
