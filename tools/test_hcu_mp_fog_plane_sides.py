#!/usr/bin/env python3
"""Run the MP fog-region fixture with raw-plane side and water assertions.

This is a thin, deterministic extension of test_hcu_mp_fog_selection_all.py.
It keeps the same source-pinned retail-map oracle and package-backed HCU
ILP32 lifecycle build, adding position-sensitive calls for valid plane chains.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tools/test_hcu_mp_fog_selection_all.py"


def main() -> int:
    source = BASE.read_text()
    oracle_row = '''        rows.append({"map_id": map_id, "cluster_index": cluster_index,
                     "reference": reference, "expected_region": result,
                     "kind": kind, "source_map_sha256": expected_sha256,
                     "raw_bsp_sha256": raw_bsp_sha256,
                     "bsp_path": location.path})'''
    oracle_row_with_plane = '''        raw_plane = (struct.unpack_from(
            "<4f", image, planes + (reference & 0x7fff) * 0x20 + 4)
            if kind == 2 else (0.0, 0.0, 0.0, 0.0))
        rows.append({"map_id": map_id, "cluster_index": cluster_index,
                     "reference": reference, "expected_region": result,
                     "kind": kind, "raw_plane": raw_plane,
                     "source_map_sha256": expected_sha256,
                     "raw_bsp_sha256": raw_bsp_sha256,
                     "bsp_path": location.path})'''
    if source.count(oracle_row) != 1:
        raise SystemExit("raw-BSP fog oracle row seam changed")
    source = source.replace(oracle_row, oracle_row_with_plane, 1)
    header_field = '                "    unsigned map_id, cluster_index; short reference, expected_region; unsigned char kind;",'
    header_field_new = '                "    unsigned map_id, cluster_index; short reference, expected_region; unsigned char kind; float raw_plane[4];",'
    if source.count(header_field) != 1:
        raise SystemExit("raw fog golden header seam changed")
    source = source.replace(header_field, header_field_new, 1)
    header_append = '''                header_lines.append("    {%du, %du, %d, %d, %du}," % (
                    row["map_id"], row["cluster_index"], row["reference"],
                    row["expected_region"], row["kind"]))'''
    header_append_new = '''                plane_values = []
                for value in row["raw_plane"]:
                    spelling = f"{value:.9g}"
                    if "." not in spelling and "e" not in spelling.lower():
                        spelling += ".0"
                    plane_values.append(spelling + "f")
                header_lines.append("    {%du, %du, %d, %d, %du, {%s}}," % (
                    row["map_id"], row["cluster_index"], row["reference"],
                    row["expected_region"], row["kind"], ", ".join(plane_values)))'''
    if source.count(header_append) != 1:
        raise SystemExit("raw fog golden initializer seam changed")
    source = source.replace(header_append, header_append_new, 1)
    old = '''		result = scenario_get_fog_region_index(&location, NULL);
		assert(result == golden->expected_region);
		assert(global_structure_bsp == bsp &&'''
    new = r'''		result = scenario_get_fog_region_index(&location, NULL);
		assert(result == golden->expected_region);
		if (golden->kind == 2)
		{
			short plane_index = (short)(golden->reference & SHORT_MAX);
			struct structure_fog_plane *plane;
			struct structure_fog_region *region;
			struct fog_definition *fog;
			long fog_index;
			real_point3d selected_side, rejected_side;
			real norm_squared, scale;
			short expected_weather, selected_weather, rejected_weather;
			boolean expected_underwater, selected_underwater, rejected_underwater;
			assert(plane_index >= 0 && plane_index < bsp->fog_planes.count);
			plane = TAG_BLOCK_GET_ELEMENT(&bsp->fog_planes, plane_index,
				struct structure_fog_plane);
			assert(plane->region_index == golden->expected_region);
			assert(fabsf(plane->plane.n.i - golden->raw_plane[0]) < 0.00001f);
			assert(fabsf(plane->plane.n.j - golden->raw_plane[1]) < 0.00001f);
			assert(fabsf(plane->plane.n.k - golden->raw_plane[2]) < 0.00001f);
			assert(fabsf(plane->plane.d - golden->raw_plane[3]) < 0.0001f);
			region = TAG_BLOCK_GET_ELEMENT(&bsp->fog_regions,
				plane->region_index, struct structure_fog_region);
			fog_index = scenario_fog_region_get_fog_index(plane->region_index);
			assert(fog_index != NONE);
			fog = fog_definition_get(fog_index);
			assert(fog != NULL);
			norm_squared = golden->raw_plane[0] * golden->raw_plane[0] +
				golden->raw_plane[1] * golden->raw_plane[1] +
				golden->raw_plane[2] * golden->raw_plane[2];
			assert(norm_squared > 0.0f);
			scale = (fabsf(golden->raw_plane[3]) + fabsf(fog->plane_distance) + 1000.0f) /
				norm_squared;
			selected_side.x = -golden->raw_plane[0] * scale;
			selected_side.y = -golden->raw_plane[1] * scale;
			selected_side.z = -golden->raw_plane[2] * scale;
			rejected_side.x = golden->raw_plane[0] * scale;
			rejected_side.y = golden->raw_plane[1] * scale;
			rejected_side.z = golden->raw_plane[2] * scale;
			assert(scenario_get_fog_region_index(&location, &selected_side) ==
				golden->expected_region);
			assert(scenario_get_fog_region_index(&location, &rejected_side) == NONE);
			expected_underwater = TEST_FLAG(fog->flags, 0);
			expected_weather = region->weather_palette_index != NONE ?
				region->weather_palette_index : cluster->weather_palette_index;
			if (expected_weather < 0 || expected_weather >= bsp->weather_palette.count)
				expected_weather = NONE;
			selected_underwater = scenario_location_underwater(
				&location, &selected_side, &selected_weather);
			rejected_underwater = scenario_location_underwater(
				&location, &rejected_side, &rejected_weather);
			assert(selected_underwater == expected_underwater);
			assert(selected_weather == expected_weather);
			assert(rejected_underwater == FALSE);
			assert(rejected_weather ==
				(cluster->weather_palette_index >= 0 &&
				cluster->weather_palette_index < bsp->weather_palette.count ?
				cluster->weather_palette_index : NONE));
			printf("mp-fog-plane-sides map=%u cluster=%u plane=%d region=%d "
				"underwater=%d weather=%d selected=1 opposite=none status=passed\n",
				map_id, golden->cluster_index, plane_index,
				golden->expected_region, selected_underwater, selected_weather);
		}
		assert(global_structure_bsp == bsp &&'''
    if source.count(old) != 1:
        raise SystemExit("fog-selection C assertion seam changed")
    source = source.replace(old, new, 1)
    namespace = {"__name__": "__main__", "__file__": str(BASE)}
    exec(compile(source, str(BASE), "exec"), namespace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
