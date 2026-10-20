#!/usr/bin/env python3
"""Convert one retail CE structure-BSP block to a schema-relocatable CBSP.

The output preserves the full BSP payload. It does not omit compressed render
vertices, claim a PS2 capacity fit, or make the resulting section runtime-ready.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PS2_TOOLS = ROOT / "submodules/halo-ps2/tools"
if str(PS2_TOOLS) not in sys.path:
    sys.path.insert(0, str(PS2_TOOLS))

from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
try:
    from .cbsp import CbspError, encode
    from .ctag_schema_walk import SchemaWalkError, read_xbox_tag_region, walk_structure_bsp
    from .hcu_schema_manifest import Elf32, SchemaManifest
except ImportError:
    from cbsp import CbspError, encode  # noqa: E402
    from ctag_schema_walk import SchemaWalkError, read_xbox_tag_region, walk_structure_bsp  # noqa: E402
    from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_tag_name_mapper(tag_region: bytes, source_base: int, removed_ranges):
    """Return a strict Xbox-name-VA to compact CTAG-offset mapper."""
    ranges = sorted((int(start), int(end)) for start, end in removed_ranges)
    previous_end = 0
    for start, end in ranges:
        if start < previous_end or start < 0 or end < start or end > len(tag_region):
            raise ValueError("removed tag ranges overlap or leave source image")
        previous_end = end

    def map_name(address: int) -> int:
        offset = address - source_base
        if offset < 0 or offset >= len(tag_region):
            raise ValueError(f"BSP tag name {address:#x} leaves retail tag image")
        if any(start <= offset < end for start, end in ranges):
            raise ValueError(f"BSP tag name {address:#x} targets removed render data")
        if tag_region.find(b"\0", offset, min(len(tag_region), offset + 256)) < 0:
            raise ValueError(f"BSP tag name {address:#x} is not bounded/terminated")
        return offset - sum(end - start for start, end in ranges if end <= offset)

    return map_name


def convert_one(map_path: Path, schema_elf: Path, bsp_name: str) -> tuple[bytes, dict]:
    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, tag_base, source = read_xbox_tag_region(map_path)
    render_start = index.header.model_vertex_address - tag_base
    render_end = index.header.model_index_address - tag_base + index.index_region[1]
    if render_start < 0 or render_end < render_start or render_end > len(tag_region):
        raise ValueError("retail render interval leaves tag image")
    locations = bsp.locate(index, tag_region, header.decompressed_size)
    matches = [item for item in locations if item.path == bsp_name]
    if len(matches) != 1:
        available = ", ".join(item.path for item in locations)
        raise ValueError(f"expected one BSP path {bsp_name!r}; available: {available}")
    location = matches[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        block = stream.read(location.size)
    if len(block) != location.size:
        raise ValueError("retail BSP block is truncated")
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    mapper = make_tag_name_mapper(tag_region, tag_base, ((render_start, render_end),))
    walked = walk_structure_bsp(
        manifest, block, location.address, mapper, file_data_policy="reject")
    payload = encode(
        walked.image, walked.relocations, walked.tag_relocations,
        source_file_offset=location.file_offset, source_file_size=len(block))
    metadata = {
        "format": "retail-ce-bsp-conversion-v1",
        "map": source["map"],
        "map_sha256": sha256(map_path.read_bytes()),
        "schema_elf_sha256": manifest["elf_sha256"],
        "bsp_path": location.path,
        "bsp_source_file_offset": location.file_offset,
        "bsp_source_xbox_base": location.address,
        "raw_bsp_bytes": len(block),
        "cbsp_bytes": len(payload),
        "cbsp_sha256": sha256(payload),
        "internal_pointer_fields": len(walked.relocations),
        "tag_name_pointer_fields": len(walked.tag_relocations),
        "schema_visited_bytes": walked.visited_bytes,
        "compressed_vertex_bytes_retained": sum(
            end - start for start, end, owner in walked.spans
            if owner == "data structure_material.compressed_vertex_data"),
        "policy": "full CE BSP retained; no render-data stripping or capacity claim",
    }
    return payload, metadata


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", type=Path, help="decompressed retail Xbox map")
    parser.add_argument("schema_elf", type=Path, help="linked HCU ELF with CE schemas")
    parser.add_argument("bsp_path", help="exact CE BSP tag path reported by the audit")
    parser.add_argument("output", type=Path, help="new CBSP payload path")
    args = parser.parse_args(argv)
    metadata_path = args.output.with_suffix(args.output.suffix + ".json")
    if args.output.exists() or metadata_path.exists():
        parser.error(f"refusing to overwrite output or metadata: {args.output}")
    try:
        payload, metadata = convert_one(args.map, args.schema_elf, args.bsp_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
        metadata_path.write_text(
            json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    except (OSError, ValueError, CbspError, SchemaWalkError) as error:
        parser.exit(2, f"retail BSP conversion failed: {error}\n")
    print(json.dumps(metadata, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
