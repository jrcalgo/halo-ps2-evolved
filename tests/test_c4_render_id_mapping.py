"""C4 item 4: render-mapping identity and presentation-isolation checks on the 13 stock MP maps."""
import copy
import dataclasses
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))

import audit_c4_render_id_mapping as c4  # noqa: E402
from halo2ps2 import bsp, bspconv, mapinfo, tagindex  # noqa: E402

REPORT = ROOT / "docs/reports/m4-c4-render-mapping-2026-10-26.json"


@pytest.fixture(scope="module")
def regenerated():
	result = c4.build()
	c4.OUT_JSON.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
	c4.OUT_MD.write_text(c4.render_md(result))
	return result


def test_regenerated_report_covers_exactly_the_mp_maps(regenerated):
	assert [m["map"] for m in regenerated["maps"]] == list(c4.MP_MAPS)
	assert len(c4.MP_MAPS) == 13
	for m in regenerated["maps"]:
		assert m["structure_bsp_count"] >= 1
		assert m["surfaces_checked"] > 0 and m["ids_checked"] > 0
		assert m["host_engine_points_checked"] > 0


def test_every_surface_round_trips_with_zero_mismatches(regenerated):
	assert regenerated["mismatches_total"] == 0
	for m in regenerated["maps"]:
		assert m["mismatches"] == 0, m["map"]
		for b in m["bsps"]:
			assert b["round_trip_mismatches"] == 0
			assert b["shader_mismatches"] == 0
			assert b["lightmap_page_mismatches"] == 0
			assert b["cluster_mismatches"] == 0
			assert b["geometry_mismatches"] == 0
			assert b["host_engine_mismatch_total"] == 0
			assert b["problems"] == []


def test_dropped_surfaces_have_no_cluster_route(regenerated):
	for m in regenerated["maps"]:
		for b in m["bsps"]:
			assert b["surfaces_dropped_no_cluster_route"] == len(b["dropped_surface_ids"])


def test_presentation_output_keeps_simulation_members(regenerated):
	assert regenerated["preservation_binding_ok"] is True
	assert regenerated["omissions_gate"]["ok"] is True
	for m in regenerated["maps"]:
		for b in m["bsps"]:
			assert b["ce_input_unchanged_by_conversion"] is True
			assert b["presentation_members_dropped_or_rewritten"] == []


def test_runtime_surface_id_gap_is_recorded_not_hidden(regenerated):
	assert regenerated["findings"][0]["id"] == "F1"
	for m in regenerated["maps"]:
		for b in m["bsps"]:
			assert b["runtime_surface_id_available"] is False


def _first_bsp(map_name):
	path = c4.DECOMPRESSED / f"{map_name}.map"
	hdr = mapinfo.read_header(path)
	idx = tagindex.TagIndex.read(path)
	with path.open("rb") as src:
		src.seek(hdr.tag_data_offset)
		region = src.read(hdr.tag_data_size)
		loc = bsp.locate(idx, region, hdr.decompressed_size)[0]
	with path.open("rb") as src:
		src.seek(loc.file_offset)
		block = src.read(loc.size)
	st = bsp.read_structure(loc, block)
	materials, bounds = bspconv.read_materials(block, loc)
	section = bspconv.parse_section(bspconv.build_section(materials, bounds, st))
	return st, section, bounds


@pytest.mark.parametrize("mutation", [
	lambda sec: sec.leaves.pop(),
	lambda sec: sec.nodes.pop(),
	lambda sec: sec.clusters[0].__setitem__("fog", sec.clusters[0]["fog"] + 1),
	lambda sec: sec.clusters[0].__setitem__("background_sound", 7),
	lambda sec: sec.portals.pop(),
])
def test_guard_fails_when_presentation_drops_or_rewrites_a_member(mutation):
	st, section, bounds = _first_bsp("bloodgulch")
	assert c4.presentation_members_preserved(st, section, bounds) == []
	bad = copy.deepcopy(section)
	mutation(bad)
	assert c4.presentation_members_preserved(st, bad, bounds) != []


def test_guard_fails_when_planes_are_rewritten():
	st, section, bounds = _first_bsp("bloodgulch")
	bad = copy.deepcopy(section)
	bad.planes[0] = (bad.planes[0][0], bad.planes[0][1], bad.planes[0][2], bad.planes[0][3] + 1.0)
	assert "bsp3d planes" in c4.presentation_members_preserved(st, bad, bounds)


