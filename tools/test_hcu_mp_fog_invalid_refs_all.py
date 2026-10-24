#!/usr/bin/env python3
"""Run invalid fog-reference guards on every stock MP map.

The generated host fixture uses the existing package-backed 13-map CE
lifecycle/collision matrix. Only temporary test source is changed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    source = (ROOT / "tests/test_hcu_mp_capacity.py").read_text()
    root_seam = "ROOT = Path(__file__).resolve().parents[1]"
    if source.count(root_seam) != 1:
        raise SystemExit("capacity fixture ROOT seam changed")
    source = source.replace(root_seam, f"ROOT = Path({str(ROOT)!r})")
    retained_name = f"build/mp-fog-{time.time_ns()}"

    source_seam = '            sources = [ROOT / "tests/hcu_mp_capacity_main.c",'
    injected = r'''            main_source = (ROOT / "tests/hcu_mp_capacity_main.c").read_text()
            invalid_ref_probe = r"""
	{
		struct structure_cluster *probe_cluster;
		short saved_reference;
		short malformed_plane;
		short malformed_region;
		short published_index = global_structure_bsp_index;
		short collision_depth = global_current_collision_user_depth;
		short collision_users[MAXIMUM_COLLISION_USER_STACK_DEPTH];
		struct collision_bsp *published_collision_bsp = global_collision_bsp;
		struct bsp3d *published_bsp3d = global_bsp3d;
		struct location probe_location;
		assert(g->cluster_index >= 0 && g->cluster_index < bsp->clusters.count);
		assert(collision_depth >= 0 &&
			collision_depth <= MAXIMUM_COLLISION_USER_STACK_DEPTH);
		memcpy(collision_users, global_current_collision_users,
			sizeof collision_users);
		probe_cluster = TAG_BLOCK_GET_ELEMENT(&bsp->clusters, g->cluster_index,
			struct structure_cluster);
		assert(bsp->fog_planes.count >= 0 && bsp->fog_planes.count < SHORT_MAX);
		assert(bsp->fog_regions.count >= 0 && bsp->fog_regions.count < SHORT_MAX);
		saved_reference = probe_cluster->fog_reference;
		memset(&probe_location, 0, sizeof probe_location);
		probe_location.leaf_index = g->leaf_index;
		probe_location.cluster_index = g->cluster_index;
		malformed_plane = (short)(0x8000u | (unsigned)bsp->fog_planes.count);
		malformed_region = (short)bsp->fog_regions.count;
		probe_cluster->fog_reference = malformed_plane;
		assert(scenario_get_fog_region_index(&probe_location, NULL) == NONE);
		assert(global_structure_bsp == bsp &&
			global_collision_bsp == published_collision_bsp &&
			global_bsp3d == published_bsp3d &&
			global_structure_bsp_index == published_index &&
			scenario_globals->structure_bsp_index == published_index);
		assert(global_current_collision_user_depth == collision_depth &&
			memcmp(collision_users, global_current_collision_users,
				sizeof collision_users) == 0);
		probe_cluster->fog_reference = malformed_region;
		assert(scenario_get_fog_region_index(&probe_location, NULL) == NONE);
		assert(global_structure_bsp == bsp &&
			global_collision_bsp == published_collision_bsp &&
			global_bsp3d == published_bsp3d &&
			global_structure_bsp_index == published_index &&
			scenario_globals->structure_bsp_index == published_index);
		assert(global_current_collision_user_depth == collision_depth &&
			memcmp(collision_users, global_current_collision_users,
				sizeof collision_users) == 0);
		probe_cluster->fog_reference = saved_reference;
		assert(probe_cluster->fog_reference == saved_reference);
		assert(global_structure_bsp == bsp &&
			global_collision_bsp == published_collision_bsp &&
			global_bsp3d == published_bsp3d &&
			global_structure_bsp_index == published_index &&
			scenario_globals->structure_bsp_index == published_index);
		assert(global_current_collision_user_depth == collision_depth);
		printf("mp-fog-invalid-reference map=%u plane=%d region=%d "
			"restored=%d status=passed\n", map_id, malformed_plane,
			malformed_region, probe_cluster->fog_reference);
	}
"""
            fog_seam = '\tassert_mp_location_queries(map_id, bsp, g);'
            if main_source.count(fog_seam) != 1:
                raise SystemExit("all-map collision query seam changed")
            main_source = main_source.replace(fog_seam, fog_seam + "\n" + invalid_ref_probe)
            generated_main = temp / "hcu_mp_capacity_main_invalid_all.c"
            generated_main.write_text(main_source)
'''
    if source.count(source_seam) != 1:
        raise SystemExit("capacity C source seam changed")
    source = source.replace(source_seam, injected + '\n            sources = [generated_main,', 1)

    output_seam = '            self.assertEqual(run.stdout.count("mp-host-map map="), 2 * len(packages))'
    if source.count(output_seam) != 1:
        raise SystemExit("all-map output validation seam changed")
    source = source.replace(
        output_seam,
        output_seam + '\n'
        '            invalid_fog_rows = re.findall(\n'
        '                r"^mp-fog-invalid-reference map=(\\d+) plane=(-?\\d+) "\n'
        '                r"region=(-?\\d+) restored=(-?\\d+) status=passed$",\n'
        '                run.stdout, re.MULTILINE)\n'
        '            self.assertEqual(len(invalid_fog_rows), 2 * len(packages),\n'
        '                             "both malformed fog references must be rejected in both cycles on every map")\n'
        '            self.assertEqual({int(row[0]) for row in invalid_fog_rows},\n'
        '                             set(map_id_by_name.values()))', 1)

    link_symbol_seam = '                           "scenario_get_current_from_weather_palette",'
    if source.count(link_symbol_seam) != 1:
        raise SystemExit("CE BSP consumer link-map assertion seam changed")
    source = source.replace(
        link_symbol_seam,
        '                           "scenario_get_current_from_weather_palette",\n'
        '                           "scenario_get_fog_region_index",', 1)

    retained_seam = '            retained = ROOT / retained_relative'
    if source.count(retained_seam) != 1:
        raise SystemExit("capacity fixture retention setup seam changed")
    source = source.replace(
        retained_seam,
        retained_seam + '\n'
        '            retained.mkdir(parents=True, exist_ok=True)\n'
        '            shutil.copy2(temp / "hcu_mp_capacity_main_invalid_all.c",\n'
        '                         retained / "hcu_mp_capacity_main_invalid_all.c")', 1)

    source_sha_seam = '            source_sha256["generated/hcu_scenario_bsp_switch_main.c"] = hashlib.sha256('
    if source.count(source_sha_seam) != 1:
        raise SystemExit("capacity fixture source-hash table seam changed")
    source = source.replace(
        source_sha_seam,
        '            source_sha256["generated/hcu_mp_capacity_main_invalid_all.c"] = hashlib.sha256(\n'
        '                (retained / "hcu_mp_capacity_main_invalid_all.c").read_bytes()).hexdigest()\n'
        + source_sha_seam, 1)

    out = ROOT / "build" / f"m2-mp-invalid-fog-all-{time.time_ns()}"
    out.mkdir(parents=True)
    generated = out / "test_hcu_mp_capacity_fog_invalid_all.py"
    generated.write_text(source)
    env = os.environ.copy()
    env["HCU_MP_CAPACITY_RETENTION_DIR"] = retained_name
    env["PYTHONPATH"] = os.pathsep.join((
        str(out), str(ROOT), str(ROOT / "tests"), str(ROOT / "tools"),
        str(ROOT / "submodules/halo-ps2/tools"),
    ))
    cmd = [sys.executable, "-m", "unittest", "-v",
           f"{generated.stem}.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision"]
    result = subprocess.run(cmd, cwd=out, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = out / "runner.log"
    log.write_text(result.stdout)
    print(result.stdout, end="")
    print(f"generated_test={generated.relative_to(ROOT)} sha256={sha(generated)}")
    print(f"runner_log={log.relative_to(ROOT)} sha256={sha(log)}")
    print(f"exit={result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
