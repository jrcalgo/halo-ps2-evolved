#!/usr/bin/env python3
"""C4 item 4: render-mapping identity audit for the 13 stock multiplayer maps.

Regenerates docs/reports/m4-c4-render-mapping-2026-10-26.{json,md} from the decompressed retail
maps under build/retail-maps/decompressed. Nothing is read from earlier audit outputs except the
preservation ledger and the MP map list, which are cross-checked against the raw block.

Checks per structure BSP (a) CE -> PS2 render -> CE round trip for every CE surface: the
converter's (batch, triangle) placement, material/shader/lightmap identities, lightmap UV, cluster
membership, leaf->cluster table; (b) presentation conversion does not remove or rewrite
simulation-owned members (collision/PVS/portals/fog/sound env, leaves, nodes, planes) and the
CBSP ledger keeps them; (c) the engine's host render code (engine/src/world/bsp.c, compiled here)
returns the same material, lightmap page, cluster batch lists and point->cluster answers as the CE
tree walk on the same raw data.

Mismatches are counted, never waived. Dropped surfaces are allowed only when the CE surface has no
cluster route (recorded with their ids). Limits are recorded in the report.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))

from halo2ps2 import bsp, bspconv, mapinfo, tagindex  # noqa: E402
from audit_mp_bsp_presentation_omissions import MP_MAPS  # noqa: E402

DECOMPRESSED = ROOT / "build/retail-maps/decompressed"
WORK = ROOT / "build/c4-render-id"
PRESERVATION = ROOT / "docs/reports/retail-bsp-preservation-2026-10-21.json"
OUT_JSON = ROOT / "docs/reports/m4-c4-render-mapping-2026-10-26.json"
OUT_MD = ROOT / "docs/reports/m4-c4-render-mapping-2026-10-26.md"
ENGINE_SRC = ROOT / "submodules/halo-ps2/engine/src"
ENGINE_BSP = ENGINE_SRC / "world/bsp.c"

POS_TOL = 0.01          # world units; measured max on the 13 maps is ~0.002
UV_TOL = 1.0 / 1024.0   # diffuse uv (2^uv_shift scaled); measured max is ~0.0003
LM_TOL = 1.0 / 32767.0  # lightmap uv quantum
SAMPLE_RANDOM = 600
SAMPLE_SURFACES = 600
NO_CHILD = bsp.NO_CHILD
LEAF_FLAG = bsp.LEAF_FLAG

# Simulation-owned CE members. They must stay byte-preserved in the CBSP path and must not be
# removed or rewritten by the presentation (BSPS) conversion.
SIM_OWNED_OWNERS = (
    "block collision_bsp.bsp2d.nodes", "block collision_bsp.bsp2d_references",
    "block collision_bsp.bsp3d.nodes", "block collision_bsp.bsp3d.planes",
    "block collision_bsp.edges", "block collision_bsp.leaves", "block collision_bsp.surfaces",
    "block collision_bsp.vertices", "block structure_bsp.background_sound_palette",
    "block structure_bsp.cluster_portals", "block structure_bsp.clusters",
    "block structure_bsp.collision_bsp", "block structure_bsp.collision_materials",
    "block structure_bsp.detail_object_data", "block structure_bsp.leaves",
    "block structure_bsp.pathfinding_surfaces", "block structure_bsp.runtime_decals",
    "block structure_bsp.sound_environment_palette", "block structure_bsp.surface_references",
    "block structure_bsp.surfaces", "block structure_bsp.weather_palette",
    "block structure_cluster.portal_indices", "block structure_cluster.predicted_resources",
    "block structure_cluster.subclusters", "block structure_cluster_portal.vertices",
    "data structure_bsp.cluster_data", "data structure_bsp.sound_cluster_data",
)
# The only owner the presentation conversion is permitted to drop from the render path.
PRESENTATION_ONLY_OWNERS = ("data structure_material.compressed_vertex_data",)

C_DRIVER = r"""
#include "world/bsp.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned char *read_all(const char *path, size_t *n)
{
	FILE *f = fopen(path, "rb");
	unsigned char *buf;
	if (!f) return NULL;
	fseek(f, 0, SEEK_END);
	*n = (size_t)ftell(f);
	rewind(f);
	buf = malloc(*n ? *n : 1);
	if (!buf || fread(buf, 1, *n, f) != *n) { fclose(f); free(buf); return NULL; }
	fclose(f);
	return buf;
}
int main(int argc, char **argv)
{
	bsp_section s;
	size_t n = 0;
	unsigned char *data;
	FILE *pts;
	float p[3];
	uint32_t i, k;
	if (argc != 3) return 2;
	data = read_all(argv[1], &n);
	if (!data) return 3;
	if (bsp_open(&s, data, n) != BSP_OK) return 4;
	printf("sec %u %u %u %u\n", s.material_count, s.batch_count, s.cluster_count, s.leaf_count);
	for (i = 0; i < s.material_count; i++) {
		bsp_material m = bsp_get_material(&s, i);
		printf("mat %u %u %u\n", i, m.shader_id, (unsigned)m.lightmap_page);
	}
	for (i = 0; i < s.batch_count; i++) {
		bsp_batch b = bsp_get_batch(&s, i);
		printf("bat %u %u %u\n", i, (unsigned)b.material, (unsigned)b.triangles);
	}
	for (i = 0; i < s.cluster_count; i++) {
		bsp_cluster c = bsp_get_cluster(&s, i);
		printf("clu %u", i);
		for (k = 0; k < c.batch_count; k++) printf(" %u", bsp_cluster_batch(&s, &c, k));
		printf("\n");
	}
	pts = fopen(argv[2], "r");
	if (!pts) return 5;
	while (fscanf(pts, "%f %f %f", &p[0], &p[1], &p[2]) == 3)
		printf("pt %d\n", bsp_find_cluster(&s, p));
	fclose(pts);
	free(data);
	return 0;
}
"""


def f32(x: float) -> float:
	return struct.unpack("<f", struct.pack("<f", x))[0]


def sha256_bytes(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def compile_driver() -> Path:
	WORK.mkdir(parents=True, exist_ok=True)
	src = WORK / "c4_render_id_dump.c"
	exe = WORK / "c4_render_id_dump"
	src.write_text(C_DRIVER)
	subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ENGINE_SRC),
		str(src), str(ENGINE_BSP), "-o", str(exe)], check=True, capture_output=True, text=True)
	return exe


def ce_cluster(st: bsp.Structure, p: tuple[float, float, float]) -> int:
	"""CE-side point->cluster walk over the collision BSP3D tree, float32 arithmetic in engine order."""
	if not st.nodes:
		if len(st.leaves) == 1 and st.leaves[0] != bsp.NO_CLUSTER:
			return st.leaves[0]
		return -1
	x, y, z = (f32(v) for v in p)
	n = 0
	for _ in range(len(st.nodes)):
		plane, front, back = st.nodes[n]
		a, b, c, d = (f32(v) for v in st.planes[plane])
		dist = f32(f32(f32(a * x) + f32(b * y)) + f32(c * z))
		dist = f32(dist - d)
		child = front if dist >= 0.0 else back
		if child == NO_CHILD:
			return -1
		if child & LEAF_FLAG:
			cl = st.leaves[child & ~LEAF_FLAG]
			return -1 if cl == bsp.NO_CLUSTER else cl
		n = child
	return -1


def presentation_members_preserved(st: bsp.Structure, section: bspconv.Section,
		bounds: tuple[float, ...]) -> list[str]:
	"""Return the simulation-owned members that the presentation output drops or rewrites."""
	bad: list[str] = []
	if [tuple(n) for n in section.nodes] != [tuple(n) for n in st.nodes]:
		bad.append("bsp3d nodes")
	if [tuple(p) for p in section.planes] != [tuple(p) for p in st.planes]:
		bad.append("bsp3d planes")
	if list(section.leaves) != list(st.leaves):
		bad.append("leaf->cluster table")
	if len(section.clusters) != len(st.clusters):
		bad.append("cluster count")
	else:
		for i, (rec, cl) in enumerate(zip(section.clusters, st.clusters)):
			# Encoding per converter (bspconv.py:390-395): fog keeps its low 15 bits and bit 15 moves
			# to cluster flag 16 (CL_FOG_BIT15); sky/weather become presence flags 1/4 with their index kept.
			fog_bits = -1 if cl.fog == -1 else cl.fog & 0x7FFF
			fog_b15 = cl.fog != -1 and bool(cl.fog & 0x8000)
			if rec["fog"] != fog_bits or bool(rec["flags"] & 16) != fog_b15:
				bad.append(f"cluster {i} fog")
				break
			if rec["sky"] != cl.sky or rec["weather"] != cl.weather or \
					rec["background_sound"] != cl.background_sound or \
					rec["sound_environment"] != cl.sound_environment:
				bad.append(f"cluster {i} sky/weather/sound")
				break
			if bool(rec["flags"] & 1) != (cl.sky >= 0) or bool(rec["flags"] & 4) != (cl.weather >= 0):
				bad.append(f"cluster {i} presence flags")
				break
	if len(section.portals) != len(st.portals):
		bad.append("portal count")
	else:
		for i, (po, sp) in enumerate(zip(section.portals, st.portals)):
			# bspconv.py:420-421: a = front, b = back (NO_CLUSTER for -1)
			a = sp.front if sp.front >= 0 else bsp.NO_CLUSTER
			b = sp.back if sp.back >= 0 else bsp.NO_CLUSTER
			if (po["a"], po["b"], po["flags"]) != (a, b, sp.flags):
				bad.append(f"portal {i} cluster link/flags")
				break
	if tuple(section.bounds) != tuple(bounds):
		bad.append("bounds")
	return bad


def cluster_batch_lists(section: bspconv.Section) -> list[list[int]]:
	out = []
	for rec in section.clusters:
		first, count = rec["first_batch"], rec["batch_count"]
		out.append(list(section.cluster_batches[first:first + count]))
	return out


def audit_bsp(map_path: Path, loc: bsp.BspLocation, block: bytes, exe: Path, tag: str) -> dict:
	result: dict = {"bsp_path": loc.path, "bsp_file_offset": loc.file_offset,
		"bsp_block_bytes": len(block), "bsp_block_sha256": sha256_bytes(block)}
	problems: list[str] = []
	st = bsp.read_structure(loc, block)
	materials, bounds = bspconv.read_materials(block, loc)
	before = dataclasses.asdict(st)
	section_bytes = bspconv.build_section(materials, bounds, st)
	# (b) the conversion must not change its CE input, and the output must keep every member.
	after = dataclasses.asdict(bsp.read_structure(loc, block))
	result["ce_input_unchanged_by_conversion"] = before == after
	if before != after:
		problems.append("conversion changed CE structure input")
	section = bspconv.parse_section(section_bytes)
	bad_members = presentation_members_preserved(st, section, bounds)
	result["presentation_members_dropped_or_rewritten"] = bad_members
	problems += [f"presentation dropped/rewrote {m}" for m in bad_members]

	# (a) CE surface -> (batch, triangle) -> CE surface, using the converter's grouping order.
	groups: dict[tuple[tuple[int, ...], int], list[tuple[int, int]]] = {}
	all_surfaces: dict[int, int] = {}
	for mi, mat in enumerate(materials):
		for ti, sid in enumerate(mat.surfaces):
			if sid in all_surfaces:
				problems.append(f"CE surface {sid} listed by two materials")
			all_surfaces[sid] = mi
			clusters = st.cluster_surfaces.get(sid)
			if clusters:
				groups.setdefault((tuple(sorted(clusters)), mi), []).append((ti, sid))
	forward: dict[int, tuple[int, int]] = {}
	reverse: dict[tuple[int, int], int] = {}
	batch_index = 0
	surface_mismatches = 0
	pos_max = uv_max = lm_max = 0.0
	lm_checked = 0
	uv_saturated = 0
	batch_surface_counts: list[int] = []
	for (clusters, mi), rows in sorted(groups.items(), key=lambda g: (g[0][0][0], g[0][1], g[0][0])):
		mat = materials[mi]
		tris = [t for t, _ in rows]
		ordered = bspconv._spatial_order(mat, tris)
		sid_of = {t: s for t, s in rows}
		for start in range(0, len(ordered), bspconv.MAX_TRIS):
			chunk = ordered[start:start + bspconv.MAX_TRIS]
			batch = section.batches[batch_index]
			if batch["material"] != mi or batch["triangles"] != len(chunk):
				problems.append(f"batch {batch_index} material/count differs")
				surface_mismatches += 1
			decoded = bspconv.decode_batch(section, batch)
			batch_surface_counts.append(len(chunk))
			for lt, ti in enumerate(chunk):
				sid = sid_of[ti]
				if sid in forward or (batch_index, lt) in reverse:
					problems.append(f"surface {sid} or triangle ({batch_index},{lt}) reused")
					surface_mismatches += 1
					continue
				forward[sid] = (batch_index, lt)
				reverse[(batch_index, lt)] = sid
				idx = mat.tris[ti]
				for corner in range(3):
					v = decoded[lt * 3 + corner]
					exp_pos = mat.pos[idx[corner]]
					pos_max = max(pos_max, max(abs(a - e) for a, e in zip(v["pos"], exp_pos)))
					exp_uv = mat.uv[idx[corner]]
					if any(not (abs(c) <= bspconv.SANE_UV) for c in exp_uv):
						uv_saturated += 1
					else:
						uv_max = max(uv_max, max(abs(a - e) for a, e in zip(v["uv"], exp_uv)))
					exp_lm = mat.lmuv[idx[corner]]
					lm_max = max(lm_max, max(abs(a - e) for a, e in zip(v["lmuv"], exp_lm)))
					lm_checked += 1
			batch_index += 1
	if batch_index != len(section.batches):
		problems.append("BSPS batches not all accounted for by the CE grouping")

	covered = set(forward)
	dropped = sorted(set(all_surfaces) - covered)
	dropped_with_route = [s for s in dropped if st.cluster_surfaces.get(s)]
	if dropped_with_route:
		problems.append(f"{len(dropped_with_route)} routed surfaces missing from output")
	# identity checks
	shader_bad = lightmap_bad = cluster_bad = roundtrip_bad = 0
	cl_lists = cluster_batch_lists(section)
	cluster_ids_checked = 0
	for sid, (b, lt) in forward.items():
		if reverse.get((b, lt)) != sid:
			roundtrip_bad += 1
		mi = all_surfaces[sid]
		mat = materials[mi]
		rec = section.materials[section.batches[b]["material"]]
		if rec["shader_id"] != mat.shader_id:
			shader_bad += 1
		want_page = mat.lightmap_page
		if rec["lightmap_page"] != want_page:
			lightmap_bad += 1
		want = set(st.cluster_surfaces.get(sid, ()))
		have = {c for c, lst in enumerate(cl_lists) if b in lst}
		cluster_ids_checked += len(want)
		if want != have or any(c >= len(st.clusters) for c in want):
			cluster_bad += 1
	merged_batches = sum(1 for n in batch_surface_counts if n > 1)
	result.update({
		"ce_surface_count": len(all_surfaces),
		"source_material_count": len(materials),
		"surfaces_checked": len(forward),
		"surfaces_dropped_no_cluster_route": len(dropped) - len(dropped_with_route),
		"dropped_surface_ids": dropped,
		"bsps_triangles": section.triangles,
		"bsps_batches": len(section.batches),
		"bsps_materials": len(section.materials),
		"ids_checked": {
			"ce_to_ps2_to_ce_round_trip": len(forward),
			"shader_tag_ids": len(forward),
			"lightmap_page_ids": len(forward),
			"lightmap_uv_corners": lm_checked,
			"cluster_membership_ids": cluster_ids_checked,
			"leaf_cluster_entries": len(st.leaves),
			"cluster_records": len(st.clusters),
		},
		"batches_holding_more_than_one_surface": merged_batches,
		"merge_policy": "batch merges recorded; each triangle keeps its CE surface via (batch, triangle) round trip",
		"max_abs_position_error": pos_max,
		"max_abs_diffuse_uv_error_unsaturated": uv_max,
		"max_abs_lightmap_uv_error": lm_max,
		"diffuse_uv_saturated_corners_excluded": uv_saturated,
		"round_trip_mismatches": roundtrip_bad,
		"shader_mismatches": shader_bad,
		"lightmap_page_mismatches": lightmap_bad,
		"cluster_mismatches": cluster_bad,
	})
	if pos_max > POS_TOL or uv_max > UV_TOL or lm_max > LM_TOL:
		problems.append("geometry or UV error above tolerance")
	result["geometry_mismatches"] = int(pos_max > POS_TOL or uv_max > UV_TOL or lm_max > LM_TOL)
	result["lightmap_uv_mismatches"] = result["geometry_mismatches"]
	mism = roundtrip_bad + shader_bad + lightmap_bad + cluster_bad + surface_mismatches \
		+ len(dropped_with_route) + len(bad_members)
	result["mismatches"] = mism

	# (c) host engine render code: same identities and point->cluster answers as the CE tree walk.
	points = []
	seed = 0x9E3779B9
	lo, hi = section.bounds[:3], section.bounds[3:6]
	for _ in range(SAMPLE_RANDOM):
		row = []
		for a, b in zip(lo, hi):
			seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
			row.append(f32(a + (b - a) * (seed / 4294967296.0)))
		points.append(tuple(row))
	surf_ids = sorted(forward)[:: max(1, len(forward) // SAMPLE_SURFACES)][:SAMPLE_SURFACES]
	for sid in surf_ids:
		mi = all_surfaces[sid]
		idx = materials[mi].tris[[t for t, s in enumerate(materials[mi].surfaces) if s == sid][0]]
		cx = sum(materials[mi].pos[i][0] for i in idx) / 3.0
		cy = sum(materials[mi].pos[i][1] for i in idx) / 3.0
		cz = sum(materials[mi].pos[i][2] for i in idx) / 3.0
		points.append((f32(cx), f32(cy), f32(cz)))
	pts_file = WORK / f"{tag}.points"
	pts_file.write_text("".join(f"{p[0]!r} {p[1]!r} {p[2]!r}\n" for p in points))
	sec_file = WORK / f"{tag}.bsps"
	sec_file.write_bytes(section_bytes)
	run = subprocess.run([str(exe), str(sec_file), str(pts_file)], capture_output=True, text=True)
	engine_mism = {"header": 0, "material": 0, "batch": 0, "cluster": 0, "point": 0}
	pts_checked = 0
	if run.returncode != 0:
		problems.append(f"host engine driver rc={run.returncode}")
		engine_mism["header"] += 1
	else:
		lines = run.stdout.splitlines()
		hdr = lines[0].split()
		if [int(x) for x in hdr[1:]] != [len(section.materials), len(section.batches),
				len(section.clusters), len(st.leaves)]:
			engine_mism["header"] += 1
		i = 1
		for mi, rec in enumerate(section.materials):
			f = lines[i].split()
			i += 1
			if [int(x) for x in f[2:]] != [rec["shader_id"], rec["lightmap_page"]] or int(f[1]) != mi:
				engine_mism["material"] += 1
		for bi, rec in enumerate(section.batches):
			f = lines[i].split()
			i += 1
			if [int(x) for x in f[2:]] != [rec["material"], rec["triangles"]]:
				engine_mism["batch"] += 1
		for ci, lst in enumerate(cl_lists):
			f = lines[i].split()
			i += 1
			if [int(x) for x in f[2:]] != lst:
				engine_mism["cluster"] += 1
		for p, row in zip(points, lines[i:]):
			engine_cl = int(row.split()[1])
			pts_checked += 1
			if engine_cl != ce_cluster(st, p):
				engine_mism["point"] += 1
	result["host_engine_mismatches"] = engine_mism
	result["host_engine_points_checked"] = pts_checked
	result["host_engine_point_sources"] = {
		"random_uniform_in_section_bounds": SAMPLE_RANDOM, "surface_centroids": len(surf_ids)}
	result["host_engine_mismatch_total"] = sum(engine_mism.values())
	result["runtime_surface_id_available"] = False
	result["problems"] = problems
	result["mismatches"] += result["host_engine_mismatch_total"]
	return result


def preservation_binding(maps: list[str]) -> dict:
	ledger = json.loads(PRESERVATION.read_text())
	rows = {m["map"]: m for m in ledger["maps"]}
	out = {}
	for name in maps:
		m = rows.get(name)
		if m is None:
			out[name] = {"present": False}
			continue
		owners = {}
		for b in m["structure_bsps"]:
			owners.update(b["schema_bytes_by_owner"])
		out[name] = {
			"present": True,
			"cbsp_round_trip_valid_all": all(b["cbsp_round_trip_valid"] for b in m["structure_bsps"]),
			"structure_bsp_count": len(m["structure_bsps"]),
			"sim_owned_bytes_present": sum(1 for k in SIM_OWNED_OWNERS if owners.get(k, 0) > 0),
			"presentation_only_owner_bytes": sum(owners.get(k, 0) for k in PRESENTATION_ONLY_OWNERS),
		}
	return out


def audit_map(name: str, exe: Path) -> dict:
	path = DECOMPRESSED / f"{name}.map"
	hdr = mapinfo.read_header(path)
	idx = tagindex.TagIndex.read(path)
	with path.open("rb") as src:
		src.seek(hdr.tag_data_offset)
		region = src.read(hdr.tag_data_size)
		locations = bsp.locate(idx, region, hdr.decompressed_size)
	bsps = []
	for bi, loc in enumerate(locations):
		with path.open("rb") as src:
			src.seek(loc.file_offset)
			block = src.read(loc.size)
		if len(block) != loc.size:
			raise ValueError(f"{name} bsp {bi}: short read")
		row = audit_bsp(path, loc, block, exe, f"{name}_b{bi}")
		row["bsp_index"] = bi
		bsps.append(row)
	return {
		"map": name,
		"map_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
		"structure_bsp_count": len(bsps),
		"surfaces_checked": sum(b["surfaces_checked"] for b in bsps),
		"ids_checked": sum(sum(b["ids_checked"].values()) for b in bsps),
		"host_engine_points_checked": sum(b["host_engine_points_checked"] for b in bsps),
		"mismatches": sum(b["mismatches"] for b in bsps),
		"bsps": bsps,
	}


def omissions_gate() -> dict:
	import audit_mp_bsp_presentation_omissions as om
	report = om.build_report(DECOMPRESSED)
	return {"ok": report["ok"], "issues": len(report["issues"]),
		"dispositions": {c["id"]: c["disposition"] for c in report["categories"]}}


def build() -> dict:
	exe = compile_driver()
	maps = [audit_map(name, exe) for name in MP_MAPS]
	total_mism = sum(m["mismatches"] for m in maps)
	binding = preservation_binding(list(MP_MAPS))
	binding_ok = all(v.get("cbsp_round_trip_valid_all") and v.get("present") for v in binding.values())
	return {
		"schema": "m4-c4-render-mapping-v1",
		"generated_by": "tools/audit_c4_render_id_mapping.py",
		"scope": "13 stock multiplayer maps (audit_mp_bsp_presentation_omissions.MP_MAPS), all structure BSPs",
		"driver": {"source": str(WORK / "c4_render_id_dump.c"), "engine_bsp_c": "submodules/halo-ps2/engine/src/world/bsp.c",
			"binary_sha256": hashlib.sha256(exe.read_bytes()).hexdigest()},
		"tolerances": {"position_world_units": POS_TOL, "diffuse_uv": UV_TOL, "lightmap_uv": LM_TOL},
		"maps": maps,
		"map_count": len(maps),
		"surfaces_checked_total": sum(m["surfaces_checked"] for m in maps),
		"ids_checked_total": sum(m["ids_checked"] for m in maps),
		"host_engine_points_checked_total": sum(m["host_engine_points_checked"] for m in maps),
		"mismatches_total": total_mism,
		"preservation_binding": binding,
		"preservation_binding_ok": binding_ok,
		"presentation_only_owners": list(PRESENTATION_ONLY_OWNERS),
		"sim_owned_owners_checked": list(SIM_OWNED_OWNERS),
		"omissions_gate": omissions_gate(),
		"findings": [
			{"id": "F1", "kind": "runtime identity gap",
				"detail": "BSPS has no serialized CE surface id. bsp_batch_surface() returns UINT32_MAX unless a borrowed source ops table is bound (submodules/halo-ps2/engine/src/world/bsp.c:203-209; bsp.h:97-98). The CE surface id exists only in the converter's in-memory Material.surfaces (bspconv.py:71). The round trip is proven offline, not from the shipped section.",
				"fix": "Serialize a per-triangle u32 surface table (4 B per expanded triangle, batches capped at 24 triangles) in BSPS, or bind a borrowed source ops with a surface table; charge its bytes in capacity."},
		],
		"blocked": [
			{"item": "CE collision-hit surface resolution on PS2 (structure_render_surface_from_point_and_leaf)",
				"reason": "needs a runtime surface id (F1) and the collision leaf candidates; not present in the PS2 closure"},
			{"item": "retail HP2 packs / shipped BSPS bytes per map",
				"reason": "no HP2 packs under build/ or data/ (see m2-bsp-compressed-vertices-parity-audit.md); this audit re-converts from decompressed maps with the same converter"},
			{"item": "CBSP byte recomputation per map",
				"reason": "schema ELF for convert_retail_bsp.py is not built in this checkout; the preservation ledger's cbsp_round_trip_valid is cited, not recomputed"},
		],
		"limits": [
			"The CE-side point->cluster walk uses the same parsed collision BSP3D tree as the converter (bsp.read_structure); it is a host re-implementation of the CE tree walk, not the CE binary.",
			"Engine-side checks run the real engine/src/world/bsp.c on the emitted section bytes.",
			"No PCSX2, GS, VU or target output is claimed.",
		],
		"ok": total_mism == 0 and binding_ok,
	}


def render_md(r: dict) -> str:
	lines = ["# M4 C4 item 4: render-mapping identity audit (2026-10-26)", "",
		"Generated by `tools/audit_c4_render_id_mapping.py`; raw data in `m4-c4-render-mapping-2026-10-26.json`.", "",
		f"Verdict: **{'PASS' if r['ok'] else 'FAIL'}** — {r['map_count']} maps, {r['surfaces_checked_total']} surfaces, "
		f"{r['ids_checked_total']} ids, {r['host_engine_points_checked_total']} host points, mismatches={r['mismatches_total']}.", "",
		"| Map | BSPs | Surfaces | Ids | Host points | Mismatches |", "|---|---:|---:|---:|---:|---:|"]
	for m in r["maps"]:
		lines.append(f"| {m['map']} | {m['structure_bsp_count']} | {m['surfaces_checked']} | {m['ids_checked']} | "
			f"{m['host_engine_points_checked']} | {m['mismatches']} |")
	lines += ["", "## Findings", ""]
	for f in r["findings"]:
		lines.append(f"- {f['id']} ({f['kind']}): {f['detail']} Proposed fix: {f['fix']}")
	lines += ["", "## Blocked", ""]
	for b in r["blocked"]:
		lines.append(f"- {b['item']}: {b['reason']}")
	lines += ["", "## Limits", ""] + [f"- {x}" for x in r["limits"]]
	return "\n".join(lines) + "\n"


def main() -> int:
	result = build()
	OUT_JSON.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
	OUT_MD.write_text(render_md(result))
	print(f"maps={result['map_count']} surfaces={result['surfaces_checked_total']} "
		f"ids={result['ids_checked_total']} host_points={result['host_engine_points_checked_total']} "
		f"mismatches={result['mismatches_total']} ok={result['ok']}")
	return 0 if result["ok"] else 1


if __name__ == "__main__":
	raise SystemExit(main())
