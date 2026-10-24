#!/usr/bin/env python3
"""Measure CE source-surface to halo-ps2 BSPS triangle correspondence.

This is an offline, read-only experiment. It does not strip BSP bytes or qualify
an HP2 section as a replacement for any CE gameplay/query data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HALO2PS2 = ROOT / "submodules/halo-ps2/tools"
sys.path.insert(0, str(HALO2PS2))
from halo2ps2 import bsp, bspconv, mapinfo, tagindex  # noqa: E402


def audit(path: Path, bsp_index: int) -> dict:
	path = path.resolve()
	hdr = mapinfo.read_header(path)
	idx = tagindex.TagIndex.read(path)
	with path.open("rb") as src:
		src.seek(hdr.tag_data_offset)
		region = src.read(hdr.tag_data_size)
		locations = bsp.locate(idx, region, hdr.decompressed_size)
	if not 0 <= bsp_index < len(locations):
		raise ValueError(f"BSP index {bsp_index} outside 0..{len(locations) - 1}")
	loc = locations[bsp_index]
	with path.open("rb") as src:
		src.seek(loc.file_offset)
		block = src.read(loc.size)
	if len(block) != loc.size:
		raise ValueError("short BSP block read")

	materials, bounds = bspconv.read_materials(block, loc)
	structure = bsp.read_structure(loc, block)
	section_bytes = bspconv.build_section(materials, bounds, structure)
	section = bspconv.parse_section(section_bytes)

	# Mirror build_section's grouping/order/chunking to retain an offline map from
	# each BSPS expanded triangle back to its CE material surface ID. This check
	# intentionally fails if converter ordering changes without updating the audit.
	groups: dict[tuple[tuple[int, ...], int], list[int]] = {}
	all_source_surfaces: set[int] = set()
	for material_index, material in enumerate(materials):
		for triangle_index, surface_id in enumerate(material.surfaces):
			if surface_id in all_source_surfaces:
				raise ValueError(f"duplicate source surface id {surface_id}")
			all_source_surfaces.add(surface_id)
			clusters = structure.cluster_surfaces.get(surface_id)
			if clusters:
				groups.setdefault((tuple(sorted(clusters)), material_index), []).append(
					triangle_index)

	batch_index = 0
	covered: dict[int, tuple[int, int, int]] = {}
	max_axis_error = 0.0
	max_distance_error = 0.0
	max_diffuse_uv_error = 0.0
	max_lightmap_uv_error = 0.0
	diffuse_uv_components_over_sane_limit = 0
	max_source_diffuse_uv_abs = 0.0
	position_comparisons = 0
	for (clusters, material_index), triangles in sorted(
		groups.items(), key=lambda row: (row[0][0][0], row[0][1], row[0][0])
	):
		material = materials[material_index]
		ordered = bspconv._spatial_order(material, triangles)
		for start in range(0, len(ordered), bspconv.MAX_TRIS):
			chunk = ordered[start:start + bspconv.MAX_TRIS]
			if batch_index >= len(section.batches):
				raise ValueError("converter batch sequence is shorter than reconstructed source")
			batch = section.batches[batch_index]
			if batch["material"] != material_index or batch["triangles"] != len(chunk):
				raise ValueError(f"batch {batch_index} material/count differs from source grouping")
			decoded = bspconv.decode_batch(section, batch)
			for local_triangle, source_triangle_index in enumerate(chunk):
				surface_id = material.surfaces[source_triangle_index]
				if surface_id in covered:
					raise ValueError(f"surface {surface_id} maps to multiple BSPS triangles")
				covered[surface_id] = (batch_index, local_triangle, material_index)
				source_indices = material.tris[source_triangle_index]
				for corner in range(3):
					expected = material.pos[source_indices[corner]]
					actual_vertex = decoded[local_triangle * 3 + corner]
					actual = actual_vertex["pos"]
					delta = [abs(a - e) for a, e in zip(actual, expected)]
					max_axis_error = max(max_axis_error, *delta)
					distance = sum(d * d for d in delta) ** 0.5
					max_distance_error = max(max_distance_error, distance)
					expected_uv = material.uv[source_indices[corner]]
					for component in expected_uv:
						if not math.isfinite(component) or abs(component) > bspconv.SANE_UV:
							diffuse_uv_components_over_sane_limit += 1
						if math.isfinite(component):
							max_source_diffuse_uv_abs = max(max_source_diffuse_uv_abs,
								abs(component))
					uv_delta = [abs(a - e) for a, e in zip(actual_vertex["uv"], expected_uv)]
					max_diffuse_uv_error = max(max_diffuse_uv_error, *uv_delta)
					expected_lmuv = material.lmuv[source_indices[corner]]
					lmuv_delta = [abs(a - e) for a, e in
						zip(actual_vertex["lmuv"], expected_lmuv)]
					max_lightmap_uv_error = max(max_lightmap_uv_error, *lmuv_delta)
					position_comparisons += 1
			batch_index += 1

	if batch_index != len(section.batches):
		raise ValueError("reconstructed source grouping left unaccounted BSPS batches")
	root = struct.unpack_from("<I", block, 0)[0] - loc.address
	if root < 0 or root + 0xFC > len(block):
		raise ValueError("structure_bsp root outside source block")
	all_surface_count = struct.unpack_from("<I", block, root + 0xF8)[0]
	missing_cluster_route = sorted(all_source_surfaces - set(covered))
	# Candidate direct lookup table: one 4-byte row per CE source surface, using
	# 0xffff for absent batch and (batch:u16, triangle-in-batch:u8, flags:u8).
	# This is only a lower-bound format estimate, not a selected runtime ABI.
	lookup_bytes = all_surface_count * 4
	return {
		"map_path": str(path),
		"map_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
		"source_block_offset": loc.file_offset,
		"source_block_bytes": loc.size,
		"source_block_sha256": hashlib.sha256(block).hexdigest(),
		"bsp_index": bsp_index,
		"bsp_path": loc.path,
		"ce_surface_count": all_surface_count,
		"source_material_triangles": len(all_source_surfaces),
		"bsps_triangles": section.triangles,
		"bsps_batches": len(section.batches),
		"bsps_raw_bytes": len(section_bytes),
		"bsps_sha256": hashlib.sha256(section_bytes).hexdigest(),
		"rendered_source_surfaces_mapped": len(covered),
		"source_surfaces_missing_cluster_route": len(missing_cluster_route),
		"missing_cluster_route_ids": missing_cluster_route,
		"candidate_lookup_bytes_u16_batch_u8_triangle_u8_flags": lookup_bytes,
		"position_corner_comparisons": position_comparisons,
		"maximum_absolute_axis_error": max_axis_error,
		"maximum_euclidean_position_error": max_distance_error,
		"maximum_absolute_diffuse_uv_error": max_diffuse_uv_error,
		"maximum_absolute_lightmap_uv_error": max_lightmap_uv_error,
		"diffuse_uv_components_over_sane_limit_or_nonfinite":
			diffuse_uv_components_over_sane_limit,
		"maximum_finite_source_diffuse_uv_abs": max_source_diffuse_uv_abs,
		"note": "Offline render-geometry correspondence only; not CE collision, lighting, target RAM, or admission evidence.",
	}


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("map", type=Path)
	parser.add_argument("--bsp", type=int, required=True)
	parser.add_argument("--output", type=Path)
	args = parser.parse_args()
	result = audit(args.map, args.bsp)
	text = json.dumps(result, indent=2, sort_keys=True) + "\n"
	if args.output:
		args.output.write_text(text)
	else:
		sys.stdout.write(text)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
