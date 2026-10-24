#!/usr/bin/env python3
"""Check the workload runner enforces distinct live CE player/unit evidence."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_hcu_step8_mp_workload import validate_log  # noqa: E402


def make_log(players: int, units: list[int]) -> str:
	unit_text = ",".join(map(str, units))
	return f"""HALO_PS2_LOCAL step8-mp-workload-profile workload_only=1 query_maps_skipped=1
HALO_PS2_LOCAL step8-mp-workload map=sidewinder local_players={players} units={players} unit_indices={unit_text} ticks=3 objects=90 active_objects=83 game_state_used=3107656 game_state_peak=3107656 game_state_fail=0 object_pool_used=78104 object_pool_peak=78104 object_pool_fail=0 dynamic_simulation=separate workload=local-splitscreen-only bots=not-exercised
HALO_PS2_LOCAL step8-mp-workload-teardown map=sidewinder state=empty
HALO_PS2_LOCAL step8-mp-workload-teardown-state map_loaded=0 cached_local_count={players} player_array_valid=0 team_array_valid=0 tags_empty=1 tag_count=0 scenario_unpublished=1 bsp_unpublished=1 collision_unpublished=1 bsp3d_unpublished=1
HALO_PS2_LOCAL step8-mp-workload-complete map=sidewinder local_players={players} ticks=3 teardown=clean
"""


def main() -> None:
	for count in (2, 4):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "guest.log"
			path.write_text(make_log(count, list(range(100, 100 + count))))
			result = validate_log(path, count)
			assert result["local_players"] == count
			assert len(result["unit_indices"]) == count
			assert len(set(result["unit_indices"])) == count
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "guest.log"
			path.write_text(make_log(count, [100] * count))
			try:
				validate_log(path, count)
			except RuntimeError as error:
				assert "fixture did not produce" in str(error)
			else:
				raise AssertionError(f"{count}-player duplicate unit evidence was accepted")
	print("step8-workload-runner synthetic_profiles=2,4 distinct-unit-gate=pass duplicate-unit-rejection=pass")


if __name__ == "__main__":
	main()
