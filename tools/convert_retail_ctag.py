"""Convert a decompressed stock Halo CE retail map to a schema-walked CTAG.

This emits the gameplay tag image only. Bitmap and file-backed sample bytes
remain in the source-file offset space and must be served by the mounted map
resource reader. The audited null-schema ``metr`` roots are retained opaque;
all other missing schemas and external resource stores fail closed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

try:
    from . import ctag
    from .audit_ctag_retail_maps import audit_map
    from .ctag_schema_walk import compact_pointer_image, read_xbox_tag_region, walk_tag_image
    from .hcu_schema_manifest import Elf32, SchemaManifest
except ImportError:
    import ctag
    from audit_ctag_retail_maps import audit_map
    from ctag_schema_walk import compact_pointer_image, read_xbox_tag_region, walk_tag_image
    from hcu_schema_manifest import Elf32, SchemaManifest


def convert_retail_map(map_path: Path, schema_elf: Path | None = None, *,
                       manifest: dict | None = None) -> tuple[bytes, dict]:
    """Return deterministic CTAG bytes and a small reproducibility summary."""
    if manifest is None:
        if schema_elf is None:
            raise ValueError("schema_elf or a prebuilt manifest is required")
        manifest = SchemaManifest(Elf32(schema_elf)).build()
    source_image, source_base, source = read_xbox_tag_region(map_path)
    audit = audit_map(map_path, manifest)

    # This v1 port's cache source exposes the selected decompressed retail map
    # as one virtual file. Do not silently emit offsets that require bitmaps.map
    # or sounds.map, or resources that collide with the substituted tag image.
    for kind in ("bitmap_source_extents", "file_data_source_extents"):
        extents = audit[kind]
        if set(extents) - {"map"}:
            raise ValueError(f"{kind} requires an external cache file: {sorted(set(extents) - {'map'})}")
        if any(row["invalid_range_count"] for row in extents.values()):
            raise ValueError(f"{kind} contains an out-of-file resource extent")
    resources = audit["map_file_resources"]
    if resources["tag_data_overlap_interval_count"]:
        raise ValueError("map resource extent overlaps the original tag-data region")
    if audit["invalid_file_data_range_count"] or audit["invalid_bitmap_range_count"]:
        raise ValueError("map contains an invalid file-backed resource extent")
    if audit["references_to_unsupported_groups"].get("metr", 0):
        raise ValueError("retail map has a stored reference to opaque metr tags")

    walked = walk_tag_image(
        manifest,
        source_image,
        source_base,
        file_data_policy="inventory",
        unknown_group_policy="reject",
        opaque_groups=("metr",),
    )
    if walked.unsupported_groups:
        raise ValueError(f"unsupported tag roots remain: {walked.unsupported_groups!r}")
    if walked.stripped_file_data_bytes:
        raise ValueError("converter unexpectedly stripped file-backed data")
    ps2_tools = Path(__file__).resolve().parents[1] / "submodules/halo-ps2/tools"
    if str(ps2_tools) not in sys.path:
        sys.path.insert(0, str(ps2_tools))
    from halo2ps2 import tagindex
    index = tagindex.TagIndex.read(map_path)
    model_start = index.header.model_vertex_address - source_base
    model_end = (index.header.model_index_address - source_base) + index.index_region[1]
    compacted_image, compacted_relocations = compact_pointer_image(
        walked.image,
        walked.relocations,
        ((model_start, model_end),),
    )
    payload = ctag.encode(
        compacted_image,
        compacted_relocations,
        scenario_tag_index=walked.scenario_tag_index,
    )
    # Re-open the exact bytes that will be emitted. This catches mismatch
    # between the schema walk and the wire-format invariants before writing.
    decoded = ctag.decode(payload, max_image_size=len(compacted_image))
    if decoded.image != compacted_image or decoded.relocations != compacted_relocations:
        raise ValueError("CTAG round-trip differs from schema-walk output")
    return payload, {
        "map": source["map"],
        "file_size": source["file_size"],
        "tag_count": source["tag_count"],
        "tag_data_offset": source["tag_data_offset"],
        "tag_data_size": source["tag_data_size"],
        "scenario_tag_index": walked.scenario_tag_index,
        "image_size": len(compacted_image),
        "relocation_count": len(compacted_relocations),
        "removed_model_vertex_index_bytes": model_end - model_start,
        "opaque_metr_count": len(walked.opaque_groups),
        "file_data_record_count": len(walked.file_data_records),
        "bitmap_image_count": audit["bitmap_image_count"],
        "resource_range_count": resources["range_count"],
        "resource_tag_overlap_count": resources["tag_data_overlap_interval_count"],
        "payload_size": len(payload),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", type=Path, help="decompressed stock Xbox Halo CE map")
    parser.add_argument("schema_elf", type=Path, help="linked HCU ELF for compiler-derived schemas")
    parser.add_argument("output", type=Path, help="new CTAG output path (must not already exist)")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    try:
        payload, summary = convert_retail_map(args.map, args.schema_elf)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    except (OSError, ValueError) as error:
        parser.exit(2, f"retail CTAG conversion failed: {error}\n")
    print(" ".join(f"{key}={value}" for key, value in summary.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
