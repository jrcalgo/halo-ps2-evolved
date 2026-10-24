#!/usr/bin/env python3
"""Exercise CE's real fog-region selector against every retail MP cluster.

This derives a test-only raw-BSP oracle and extends the existing package-backed
13-map lifecycle fixture in a temporary generated test. No production source is
changed.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    base = (ROOT / "tests/test_hcu_mp_capacity.py").read_text()
    root_seam = "ROOT = Path(__file__).resolve().parents[1]"
    if base.count(root_seam) != 1:
        raise SystemExit("capacity fixture ROOT seam changed")
    source = base.replace(root_seam, f"ROOT = Path({str(ROOT)!r})")

    oracle = r'''from test_hcu_scenario_bsp_switch import (
    STRUCTURE_BSP_SIZE, STRUCTURE_BSP_CLUSTERS_OFFSET,
    STRUCTURE_BSP_FOG_PLANES_OFFSET, STRUCTURE_BSP_FOG_REGIONS_OFFSET)

def retail_source_all_fog_selection_oracle(map_path, map_id, expected_sha256):
    """Decode every raw cluster fog reference and independently predict CE's
    position-independent region result. Values come only from raw retail BSP
    bytes; malformed indices are classified as NONE, never dereferenced."""
    if hashlib.sha256(map_path.read_bytes()).hexdigest() != expected_sha256:
        raise AssertionError(f"source map hash changed: {map_path}")
    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, tag_region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"expected one stock MP BSP in {map_path}, got {len(locations)}")
    location = locations[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    if len(image) != location.size:
        raise AssertionError(f"truncated raw BSP image: {map_path}")
    raw_bsp_sha256 = hashlib.sha256(image).hexdigest()
    root_address = struct.unpack_from("<I", image, 0)[0]
    root = root_address - location.address
    if root < 0 or root + STRUCTURE_BSP_SIZE > len(image):
        raise AssertionError(f"raw BSP root outside image: {map_path}")

    def block(block_offset, stride, label):
        count, address = struct.unpack_from("<iI", image, root + block_offset)
        offset = address - location.address if address else 0
        if count < 0 or (count and
                (offset < 0 or offset + count * stride > len(image))):
            raise AssertionError(f"invalid {label} block extent: {map_path}")
        return count, offset

    cluster_count, clusters = block(STRUCTURE_BSP_CLUSTERS_OFFSET, 0x68, "cluster")
    plane_count, planes = block(STRUCTURE_BSP_FOG_PLANES_OFFSET, 0x20, "fog-plane")
    region_count, regions = block(STRUCTURE_BSP_FOG_REGIONS_OFFSET, 0x28, "fog-region")
    rows = []
    for cluster_index in range(cluster_count):
        reference = struct.unpack_from("<h", image, clusters + cluster_index * 0x68 + 2)[0]
        if reference == -1:
            result, kind = -1, 0  # CE NONE reference
        elif reference & 0x8000:
            plane_index = reference & 0x7fff
            if plane_index >= plane_count:
                result, kind = -1, 3  # malformed plane index; CE port guard
            else:
                region_index = struct.unpack_from(
                    "<h", image, planes + plane_index * 0x20)[0]
                if not 0 <= region_index < region_count:
                    result, kind = -1, 3  # invalid plane->region; CE yields NONE
                else:
                    result, kind = region_index, 2  # valid high-bit plane chain
        elif reference < region_count:
            result, kind = reference, 1  # valid direct region selector
        else:
            result, kind = -1, 4  # malformed direct region; CE bounds guard
        rows.append({"map_id": map_id, "cluster_index": cluster_index,
                     "reference": reference, "expected_region": result,
                     "kind": kind, "source_map_sha256": expected_sha256,
                     "raw_bsp_sha256": raw_bsp_sha256,
                     "bsp_path": location.path})
    return rows
'''
    class_seam = "class MultiplayerHostCollisionMatrix(unittest.TestCase):"
    if source.count(class_seam) != 1:
        raise SystemExit("capacity fixture class seam changed")
    source = source.replace(class_seam, oracle + "\n\n" + class_seam, 1)

    source_seam = '            sources = [ROOT / "tests/hcu_mp_capacity_main.c",'
    generated_main_injection = r'''            fog_selection_by_map = {
                name: retail_source_all_fog_selection_oracle(
                    ROOT / f"build/retail-maps/decompressed/{name}.map",
                    map_id_by_name[name], MP_SOURCE_SHA256[name])
                for name in packages
            }
            fog_selection_rows = [row for name in packages
                                  for row in fog_selection_by_map[name]]
            self.assertTrue(fog_selection_rows)
            fog_selection_inventory = {
                "scope": "all clusters in each of 13 hash-pinned stock MP source BSPs",
                "oracle": "raw Xbox BSP cluster fog_reference and bounded plane/region blocks",
                "result_semantics": "scenario_get_fog_region_index(location, NULL)",
                "rows": fog_selection_rows,
            }
            (temp / "mp_fog_selection_source_inventory.json").write_text(
                json.dumps(fog_selection_inventory, indent=2, sort_keys=True) + "\n")
            kinds = {"none": 0, "direct": 1, "plane": 2,
                     "invalid_plane": 3, "invalid_direct": 4}
            header_lines = [
                "typedef struct hcu_mp_fog_selection_golden {",
                "    unsigned map_id, cluster_index; short reference, expected_region; unsigned char kind;",
                "} hcu_mp_fog_selection_golden;",
                "static const hcu_mp_fog_selection_golden hcu_mp_fog_selection_goldens[] = {",
            ]
            for row in fog_selection_rows:
                header_lines.append("    {%du, %du, %d, %d, %du}," % (
                    row["map_id"], row["cluster_index"], row["reference"],
                    row["expected_region"], row["kind"]))
            header_lines += ["};", "#define HCU_MP_FOG_SELECTION_GOLDEN_COUNT %du" %
                             len(fog_selection_rows), ""]
            (temp / "hcu_mp_fog_selection_golden.h").write_text("\n".join(header_lines))

            main_source = (ROOT / "tests/hcu_mp_capacity_main.c").read_text()
            include_seam = '#include "hcu_mp_lifecycle_generated.h"'
            if main_source.count(include_seam) != 1:
                raise SystemExit("generated lifecycle include seam changed")
            main_source = main_source.replace(
                include_seam, include_seam + '\n#include "hcu_mp_fog_selection_golden.h"', 1)
            function_seam = "static void assert_mp_sound_obstruction(unsigned map_id)"
            fog_function = r"""
static void assert_all_mp_fog_selections(unsigned map_id,
	struct structure_bsp *bsp)
{
	unsigned i, rows = 0, kind_counts[5] = {0, 0, 0, 0, 0};
	short published_index = global_structure_bsp_index;
	short collision_depth = global_current_collision_user_depth;
	short collision_users[MAXIMUM_COLLISION_USER_STACK_DEPTH];
	struct collision_bsp *published_collision_bsp = global_collision_bsp;
	struct bsp3d *published_bsp3d = global_bsp3d;
	assert(bsp && global_structure_bsp == bsp);
	assert(collision_depth >= 0 && collision_depth <= MAXIMUM_COLLISION_USER_STACK_DEPTH);
	memcpy(collision_users, global_current_collision_users, sizeof collision_users);
	for (i = 0; i < HCU_MP_FOG_SELECTION_GOLDEN_COUNT; ++i)
	{
		const hcu_mp_fog_selection_golden *golden =
			&hcu_mp_fog_selection_goldens[i];
		struct structure_cluster *cluster;
		struct location location;
		short result;
		if (golden->map_id != map_id)
			continue;
		assert(golden->cluster_index < (unsigned)bsp->clusters.count);
		cluster = TAG_BLOCK_GET_ELEMENT(&bsp->clusters,
			(short)golden->cluster_index, struct structure_cluster);
		assert(cluster->fog_reference == golden->reference);
		memset(&location, 0, sizeof location);
		location.leaf_index = NONE;
		location.cluster_index = (short)golden->cluster_index;
		location.bonus = 0;
		result = scenario_get_fog_region_index(&location, NULL);
		assert(result == golden->expected_region);
		assert(global_structure_bsp == bsp &&
			global_collision_bsp == published_collision_bsp &&
			global_bsp3d == published_bsp3d &&
			global_structure_bsp_index == published_index &&
			scenario_globals->structure_bsp_index == published_index);
		assert(global_current_collision_user_depth == collision_depth &&
			memcmp(collision_users, global_current_collision_users,
				sizeof collision_users) == 0);
		assert(golden->kind < 5);
		kind_counts[golden->kind]++;
		rows++;
		printf("mp-fog-selection map=%u cluster=%u ref=%d result=%d kind=%u status=passed\n",
			map_id, golden->cluster_index, golden->reference, result,
			(unsigned)golden->kind);
	}
	assert(rows > 0);
	printf("mp-fog-selection-summary map=%u rows=%u none=%u direct=%u plane=%u invalid_plane=%u invalid_direct=%u status=passed\n",
		map_id, rows, kind_counts[0], kind_counts[1], kind_counts[2],
		kind_counts[3], kind_counts[4]);
}
"""
            if main_source.count(function_seam) != 1:
                raise SystemExit("fog selection function insertion seam changed")
            main_source = main_source.replace(function_seam, fog_function + "\n" + function_seam, 1)
            query_seam = "\tassert_mp_location_queries(map_id, bsp, g);"
            if main_source.count(query_seam) != 1:
                raise SystemExit("fog selection call seam changed")
            main_source = main_source.replace(
                query_seam, query_seam + "\n\tassert_all_mp_fog_selections(map_id, bsp);", 1)
            generated_main = temp / "hcu_mp_capacity_main_fog_selection.c"
            generated_main.write_text(main_source)
'''
    if source.count(source_seam) != 1:
        raise SystemExit("capacity C source seam changed")
    source = source.replace(source_seam,
                            generated_main_injection + '\n            sources = [generated_main,', 1)

    output_seam = '            self.assertEqual(run.stdout.count("mp-host-map map="), 2 * len(packages))'
    if source.count(output_seam) != 1:
        raise SystemExit("all-map lifecycle output assertion seam changed")
    output_assertions = r'''            fog_selection_output = [tuple(map(int, row)) for row in re.findall(
                r"^mp-fog-selection map=(\d+) cluster=(\d+) ref=(-?\d+) "
                r"result=(-?\d+) kind=(\d+) status=passed$", run.stdout, re.MULTILINE)]
            expected_fog_selection_output = [
                (row["map_id"], row["cluster_index"], row["reference"],
                 row["expected_region"], row["kind"])
                for row in fog_selection_rows]
            self.assertEqual(sorted(fog_selection_output),
                             sorted(expected_fog_selection_output * 2),
                             "CE fog-region selector differs from independent raw-BSP oracle")
            fog_summaries = [tuple(map(int, row)) for row in re.findall(
                r"^mp-fog-selection-summary map=(\d+) rows=(\d+) none=(\d+) "
                r"direct=(\d+) plane=(\d+) invalid_plane=(\d+) "
                r"invalid_direct=(\d+) status=passed$", run.stdout, re.MULTILINE)]
            self.assertEqual(len(fog_summaries), 2 * len(packages))
            self.assertEqual({row[0] for row in fog_summaries},
                             set(map_id_by_name.values()))
'''
    source = source.replace(output_seam, output_seam + '\n' + output_assertions, 1)

    # Require the production CE resolver in the actual linked executable.
    link_seam = '                           "scenario_get_current_from_weather_palette",'
    if source.count(link_seam) != 1:
        raise SystemExit("CE scenario link-map assertion seam changed")
    source = source.replace(link_seam,
                            link_seam + '\n                           "scenario_get_fog_region_index",', 1)

    # Retain the generated C source and raw oracle beside the candidate binary.
    retention_seam = '            retained = ROOT / retained_relative'
    if source.count(retention_seam) != 1:
        raise SystemExit("capacity fixture retention seam changed")
    source = source.replace(retention_seam,
        retention_seam + '\n'
        '            retained.mkdir(parents=True, exist_ok=True)\n'
        '            shutil.copy2(generated_main, retained / "hcu_mp_capacity_main_fog_selection.c")\n'
        '            shutil.copy2(temp / "hcu_mp_fog_selection_golden.h", retained / "hcu_mp_fog_selection_golden.h")\n'
        '            shutil.copy2(temp / "mp_fog_selection_source_inventory.json", retained / "mp_fog_selection_source_inventory.json")', 1)
    source_sha_seam = '            source_sha256["generated/hcu_scenario_bsp_switch_main.c"] = hashlib.sha256('
    if source.count(source_sha_seam) != 1:
        raise SystemExit("capacity manifest source hash seam changed")
    source = source.replace(source_sha_seam,
        '            source_sha256["generated/hcu_mp_capacity_main_fog_selection.c"] = hashlib.sha256(\n'
        '                (retained / "hcu_mp_capacity_main_fog_selection.c").read_bytes()).hexdigest()\n'
        '            source_sha256["generated/hcu_mp_fog_selection_golden.h"] = hashlib.sha256(\n'
        '                (retained / "hcu_mp_fog_selection_golden.h").read_bytes()).hexdigest()\n'
        '            source_sha256["generated/mp_fog_selection_source_inventory.json"] = hashlib.sha256(\n'
        '                (retained / "mp_fog_selection_source_inventory.json").read_bytes()).hexdigest()\n'
        + source_sha_seam, 1)

    generated_dir = ROOT / "build" / f"m2-mp-fog-selection-{time.time_ns()}"
    generated_dir.mkdir(parents=True)
    generated_test = generated_dir / "test_hcu_mp_fog_selection_generated.py"
    generated_test.write_text(source)
    env = os.environ.copy()
    retention = f"build/mp-fog-selection-{time.time_ns()}"
    env["HCU_MP_CAPACITY_RETENTION_DIR"] = retention
    env["PYTHONPATH"] = os.pathsep.join((
        str(generated_dir), str(ROOT), str(ROOT / "tests"), str(ROOT / "tools"),
        str(ROOT / "submodules/halo-ps2/tools")))
    command = [sys.executable, "-m", "unittest", "-v",
               f"{generated_test.stem}.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision"]
    result = subprocess.run(command, cwd=generated_dir, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = generated_dir / "runner.log"
    log.write_text(result.stdout)
    print(result.stdout, end="")
    print(f"generated_test={generated_test.relative_to(ROOT)}")
    print(f"retention_dir={retention}")
    print(f"runner_log={log.relative_to(ROOT)}")
    print(f"exit={result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
