#!/usr/bin/env python3
"""Run the test-only CE 2/4-player local split-screen workload in PCSX2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from test_hcu_boot import ROOT, boot_once
from test_emulator import save


ELF = ROOT / "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-2p-tagcache-4477120.elf"
PROFILE = "HALO_PS2_LOCAL step8-mp-workload-profile workload_only=1 query_maps_skipped=1"
WORKLOAD = re.compile(
    r"HALO_PS2_LOCAL step8-mp-workload map=sidewinder local_players=(\d+) "
	r"units=(\d+) unit_indices=([\d,-]+) ticks=(\d+) objects=(\d+) active_objects=(\d+) "
    r"game_state_used=(\d+) game_state_peak=(\d+) game_state_fail=(\d+) "
    r"object_pool_used=(\d+) object_pool_peak=(\d+) object_pool_fail=(\d+) "
    r"dynamic_simulation=separate workload=local-splitscreen-only bots=not-exercised")
TEARDOWN = re.compile(
    r"HALO_PS2_LOCAL step8-mp-workload-teardown-state map_loaded=(\d+) "
    r"cached_local_count=(-?\d+) player_array_valid=(\d+) team_array_valid=(\d+) "
    r"tags_empty=(\d+) tag_count=(\d+) scenario_unpublished=(\d+) "
    r"bsp_unpublished=(\d+) collision_unpublished=(\d+) bsp3d_unpublished=(\d+)")


def validate_log(log_path: Path, expected_players: int) -> dict:
	text = log_path.read_text(errors="replace")
	if "HALO_PS2_FAIL" in text:
		raise RuntimeError("guest emitted a HALO_PS2_FAIL marker")
	match = WORKLOAD.search(text)
	if not match:
		raise RuntimeError("missing two-local-player allocator ownership snapshot")
	players, units = map(int, match.group(1, 2))
	unit_indices = [int(value) for value in match.group(3).split(",")]
	ticks, objects, active, gs_used, gs_peak, gs_fail, pool_used, pool_peak, pool_fail = map(
		int, match.groups()[3:])
	# CE datum handles may be signed-negative; only NONE (-1) is invalid.
	if (players != expected_players or units != expected_players or
		len(unit_indices) != expected_players or any(index == -1 for index in unit_indices) or
		len(set(unit_indices)) != expected_players or ticks != 3 or objects <= 0):
		raise RuntimeError("fixture did not produce its required spawned-player/tick/object evidence")
	if gs_peak < gs_used or pool_peak < pool_used:
		raise RuntimeError("owner high-water is below its final used-byte snapshot")
	teardown_match = TEARDOWN.search(text)
	if not teardown_match:
		raise RuntimeError("missing map/tag/player-array teardown state snapshot")
	map_loaded, cached_players, player_valid, team_valid, tags_empty, tag_count, scenario_empty, bsp_empty, collision_empty, bsp3d_empty = map(int, teardown_match.groups())
	if (map_loaded != 0 or player_valid != 0 or team_valid != 0 or tags_empty != 1 or
		tag_count != 0 or scenario_empty != 1 or bsp_empty != 1 or
		collision_empty != 1 or bsp3d_empty != 1):
		raise RuntimeError("CE map/tag owner or player/team data arrays remain published")
	if "HALO_PS2_LOCAL step8-mp-workload-teardown map=sidewinder state=empty" not in text:
		raise RuntimeError("CE map teardown did not reach the empty-state marker")
	success = (f"HALO_PS2_LOCAL step8-mp-workload-complete map=sidewinder "
		f"local_players={expected_players} ticks=3 teardown=clean")
	if success not in text:
		raise RuntimeError("CE gameplay workload completion marker is missing")
	if PROFILE not in text or text.index(PROFILE) > text.index(success):
		raise RuntimeError("workload-only profile marker is missing or out of order")
	return {
		"local_players": players, "spawned_units": units,
		"unit_indices": unit_indices, "game_ticks": ticks, "object_count": objects,
		"active_object_count": active,
		"game_state": {"used_bytes": gs_used, "high_water_bytes": gs_peak,
			"failed_allocations": gs_fail},
		"object_pool": {"used_bytes": pool_used, "high_water_bytes": pool_peak,
			"failed_allocations": pool_fail},
		"dynamic_simulation": "separate owner; not summed",
		"bots_and_network_coop": "not exercised",
		"teardown": "map and tags empty; player/team datum arrays invalidated",
		"cached_local_count_after_dispose": cached_players,
	}


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--elf", type=Path, default=ELF)
	parser.add_argument("--players", type=int, choices=(2, 4), default=2,
		help="expected local split-screen players; four is CE MAXIMUM_LOCAL_PLAYERS")
	parser.add_argument("--mode", choices=("interpreter", "recompiler"), default="interpreter")
	parser.add_argument("--timeout", type=int, default=300)
	parser.add_argument("--stable-seconds", type=float, default=2.0)
	args = parser.parse_args()
	success = (f"HALO_PS2_LOCAL step8-mp-workload-complete map=sidewinder "
		f"local_players={args.players} ticks=3 teardown=clean")
	elf = args.elf
	if args.players == 4 and elf == ELF:
		elf = ROOT / "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-4p-tagcache-4477120.elf"
	elf = elf.resolve()
	if not elf.is_file():
		raise RuntimeError(f"workload ELF does not exist: {elf}")
	config = json.loads((ROOT / ".local/emulator.json").read_text())
	result = boot_once(config, elf, args.mode, os.environ.get("DISPLAY", config["display"]),
		args.timeout, "step8-mp-workload", success, stable_seconds=args.stable_seconds)
	assertions = validate_log(Path(result["log"]), args.players)
	report = {"status": "passed", "elf": str(elf), "mode": args.mode,
		"guest_result": result, "assertions": assertions,
		"requested_local_players": args.players,
		"scope_limit": "one Sidewinder local split-screen fixture; four local players are not AI bots or network co-op"}
	report_path = ROOT / "build/hcu-step8-mp-workload" / f"{args.mode}-result.json"
	report_path.parent.mkdir(parents=True, exist_ok=True)
	save(report_path, report)
	print(json.dumps({"status": report["status"], "report": str(report_path),
		"assertions": assertions}, indent=2))
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except (OSError, RuntimeError, ValueError, KeyError) as error:
		sys.exit(f"HCU Step 8 workload failed: {error}")
