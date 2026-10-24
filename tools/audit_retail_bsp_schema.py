#!/usr/bin/env python3
"""Measure compiler-schema-owned extents inside retail structure-BSP blocks.

This is an inventory, not a strip/conversion policy. It separates pointers
that resolve within one BSP from tag-reference names that resolve into CTAG,
and records every schema-owned extent so candidate capacity work can be based
on field evidence rather than block names.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MEMORY_BUDGET = json.loads((ROOT / "config/memory-budget.json").read_text())
CURRENT_BSP_CAPACITY = next(
    region["bytes"] for region in MEMORY_BUDGET["regions"]
    if region["name"] == "current_bsp"
)
COMPRESSED_VERTEX_OWNER = "data structure_material.compressed_vertex_data"


def capacity_projection(raw_bytes: int, owner_bytes: dict[str, int]) -> tuple[int, bool]:
    """Return the hypothetical remaining BSP bytes and cap result.

    This deliberately does not claim the externalized payload is disposable,
    schema-valid outside the BSP, or already charged to another region.
    """
    projected = raw_bytes - owner_bytes.get(COMPRESSED_VERTEX_OWNER, 0)
    return projected, projected <= CURRENT_BSP_CAPACITY
PS2_TOOLS = ROOT / "submodules/halo-ps2/tools"
if str(PS2_TOOLS) not in sys.path:
    sys.path.insert(0, str(PS2_TOOLS))

from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from cbsp import CbspError, decode as decode_cbsp, encode as encode_cbsp  # noqa: E402
from ctag_schema_walk import SchemaWalkError, read_xbox_tag_region, walk_structure_bsp  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tag_name_mapper(tag_region: bytes, source_base: int, removed_ranges):
    """Map a retail Xbox tag-name VA into the compacted CTAG image offset."""
    ranges = sorted((int(start), int(end)) for start, end in removed_ranges)
    previous_end = 0
    for start, end in ranges:
        if start < previous_end or start < 0 or end < start or end > len(tag_region):
            raise ValueError("removed tag-image ranges overlap or leave the source region")
        previous_end = end

    def map_pointer(address: int) -> int:
        source_offset = address - source_base
        if source_offset < 0 or source_offset >= len(tag_region):
            raise ValueError(f"tag-reference name {address:#x} leaves the retail tag region")
        removed_before = 0
        for start, end in ranges:
            if start <= source_offset < end:
                raise ValueError(f"tag-reference name {address:#x} intersects removed render bytes")
            if end <= source_offset:
                removed_before += end - start
        if tag_region.find(0, source_offset, min(len(tag_region), source_offset + 256)) < 0:
            raise ValueError(f"tag-reference name {address:#x} is not terminated within 256 bytes")
        return source_offset - removed_before

    return map_pointer


def audit_map(path: Path, manifest: dict) -> dict:
    header = mapinfo.read_header(path)
    index = tagindex.TagIndex.read(path)
    tag_region, source_tag_base, source = read_xbox_tag_region(path)
    model_start = index.header.model_vertex_address - source_tag_base
    model_end = index.header.model_index_address - source_tag_base + index.index_region[1]
    if model_start < 0 or model_end < model_start or model_end > len(tag_region):
        raise ValueError(f"{path}: render vertex/index interval leaves tag image")
    map_name = tag_name_mapper(tag_region, source_tag_base, ((model_start, model_end),))
    locations = bsp.locate(index, tag_region, header.decompressed_size)
    records = []
    with path.open("rb") as stream:
        for location in locations:
            stream.seek(location.file_offset)
            block = stream.read(location.size)
            if len(block) != location.size:
                raise ValueError(f"{path}: truncated BSP {location.path}")
            result = walk_structure_bsp(
                manifest, block, location.address, map_name, file_data_policy="inventory")
            cbsp_payload = encode_cbsp(
                result.image, result.relocations, result.tag_relocations,
                source_file_offset=location.file_offset,
                source_file_size=len(block))
            cbsp_image = decode_cbsp(cbsp_payload, max_image_size=len(block))
            if (cbsp_image.image != result.image or
                    cbsp_image.relocations != result.relocations or
                    cbsp_image.tag_relocations != result.tag_relocations):
                raise ValueError(f"{path}: CBSP round-trip changed {location.path}")
            field_bytes = Counter()
            for start, end, owner in result.spans:
                field_bytes[owner] += end - start
            compressed_vertices = field_bytes[COMPRESSED_VERTEX_OWNER]
            projected_bytes, projected_fits = capacity_projection(
                location.size, field_bytes
            )
            records.append({
                "path": location.path,
                "file_offset": location.file_offset,
                "source_xbox_base": location.address,
                "raw_bytes": location.size,
                "compressed_vertex_data_bytes": compressed_vertices,
                # Projection only: this does not prove a schema-valid conversion,
                # visual-equivalent query, or a second region for the externalized bytes.
                "bytes_if_compressed_vertices_externalized": projected_bytes,
                "fits_current_bsp_if_compressed_vertices_externalized": projected_fits,
                "schema_owned_bytes": result.visited_bytes,
                "cbsp_envelope_bytes": len(cbsp_payload),
                "cbsp_sha256": hashlib.sha256(cbsp_payload).hexdigest(),
                "cbsp_round_trip_valid": True,
                "source_bytes_preserved_except_schema_normalizations": True,
                "normalization_word_count": len(result.normalizations),
                "normalizations_by_reason": dict(sorted(Counter(
                    reason for _offset, _old, _new, reason in
                    result.normalizations).items())),
                "bytes_without_schema_extent": location.size - result.visited_bytes,
                "bsp_internal_pointer_fields": len(result.relocations),
                "tag_name_pointer_fields": len(result.tag_relocations),
                "file_data_fields": [list(item) for item in result.file_data_records],
                "schema_extents": [
                    {"owner": owner, "offset": start, "size": end - start}
                    for start, end, owner in result.spans
                ],
                "schema_bytes_by_owner": dict(sorted(field_bytes.items())),
            })
    return {
        "map": path.stem,
        "source_sha256": sha256(path),
        "tag_data_size": source["tag_data_size"],
        "render_interval_bytes_removed_by_ctag": model_end - model_start,
        "bsp_count": len(records),
        "bsp_raw_bytes_sum": sum(item["raw_bytes"] for item in records),
        "bsp_schema_bytes_sum": sum(item["schema_owned_bytes"] for item in records),
        "structure_bsps": records,
    }


def audit(maps: list[Path], schema_elf: Path) -> dict:
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    rows = [audit_map(path, manifest) for path in sorted(maps)]
    blocks = [block for row in rows for block in row["structure_bsps"]]
    largest = sorted(blocks, key=lambda item: (-item["raw_bytes"], item["path"]))
    externalized = sorted(
        blocks,
        key=lambda item: (-item["bytes_if_compressed_vertices_externalized"], item["path"]),
    )
    return {
        "format": "retail-ce-bsp-schema-audit-v4",
        "schema_elf_sha256": manifest["elf_sha256"],
        "map_count": len(rows),
        "structure_bsp_count": len(blocks),
        "current_bsp_capacity_bytes": CURRENT_BSP_CAPACITY,
        "raw_current_bsp_capacity_failures": sum(
            item["raw_bytes"] > CURRENT_BSP_CAPACITY for item in blocks
        ),
        "projected_capacity_failures_if_compressed_vertices_externalized": sum(
            not item["fits_current_bsp_if_compressed_vertices_externalized"]
            for item in blocks
        ),
        "total_raw_bsp_bytes": sum(item["raw_bytes"] for item in blocks),
        "total_schema_owned_bytes": sum(item["schema_owned_bytes"] for item in blocks),
        "total_cbsp_envelope_bytes": sum(item["cbsp_envelope_bytes"] for item in blocks),
        "cbsp_round_trip_failure_count": sum(
            not item["cbsp_round_trip_valid"] for item in blocks),
        "largest_raw_bsp": largest[0] if largest else None,
        "largest_projected_bsp_if_compressed_vertices_externalized":
            externalized[0] if externalized else None,
        "maps": rows,
        "interpretation": (
            "Schema-owned byte counts are not a license to strip fields: they include "
            "simulation, pathfinding, cluster/PVS, sound, and presentation data. "
            "The compressed-vertex projection is arithmetic only; the data supports "
            "CE visual surface/material/light queries and has no proven equivalent "
            "in the PS2 BSPS pack. CBSP v1 round trips are checked per block, but no "
            "block is stripped or declared PS2-capacity-safe. It does not charge storage "
            "for an external copy. Each omission still requires CE consumer and parity evidence."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", type=Path, help="directory of decompressed retail Xbox maps")
    parser.add_argument("schema_elf", type=Path, help="linked HCU PS2 ELF with compiler-derived schemas")
    parser.add_argument("--output", type=Path, help="new JSON report path; stdout by default")
    args = parser.parse_args(argv)
    paths = sorted(args.maps.glob("*.map"))
    if not paths:
        parser.error(f"no .map files in {args.maps}")
    if args.output and args.output.exists():
        parser.error(f"refusing to overwrite existing report: {args.output}")
    try:
        result = audit(paths, args.schema_elf)
        rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered)
        else:
            print(rendered, end="")
    except (OSError, ValueError, CbspError, SchemaWalkError) as error:
        parser.exit(2, f"retail BSP schema audit failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
