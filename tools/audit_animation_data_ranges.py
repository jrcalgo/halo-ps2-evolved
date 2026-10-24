#!/usr/bin/env python3
"""Inventory exact retail source-file ranges for schema-owned animation.data.

This report is evidence for a possible bounded animation-data store. It does
not rewrite tag_data pointers or claim that the animation cache fits runtime
memory/performance limits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .ctag_schema_walk import read_xbox_tag_region, walk_tag_image
    from .hcu_schema_manifest import Elf32, SchemaManifest
except ImportError:
    from ctag_schema_walk import read_xbox_tag_region, walk_tag_image
    from hcu_schema_manifest import Elf32, SchemaManifest


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_map(map_path: Path, manifest: dict) -> dict:
    image, source_base, source = read_xbox_tag_region(map_path)
    result = walk_tag_image(
        manifest, image, source_base,
        file_data_policy="inventory", unknown_group_policy="inventory")
    tag_data_offset = int(source["tag_data_offset"])
    file_size = int(source["file_size"])
    records = []
    for definition, field, size, image_offset in result.in_image_data_records:
        if (definition, field) != ("animation", "data"):
            continue
        file_offset = tag_data_offset + image_offset
        if (image_offset < 0 or size <= 0 or image_offset > len(image) or
                size > len(image) - image_offset or file_offset > file_size or
                size > file_size - file_offset):
            raise ValueError(
                f"animation.data source extent is out of bounds: "
                f"image={image_offset:#x}+{size:#x}, file={file_offset:#x}")
        payload = image[image_offset:image_offset + size]
        records.append({
            "tag_image_offset": image_offset,
            "source_file_offset": file_offset,
            "size": size,
            "payload_sha256": sha256(payload),
        })
    records.sort(key=lambda row: (row["source_file_offset"], row["size"]))
    previous_end = tag_data_offset
    overlap_bytes = 0
    for row in records:
        start = row["source_file_offset"]
        overlap_bytes += max(0, previous_end - start)
        previous_end = max(previous_end, start + row["size"])
    return {
        "map": source["map"],
        "source_sha256": sha256(map_path.read_bytes()),
        "source_file_size": file_size,
        "tag_data_offset": tag_data_offset,
        "tag_data_size": int(source["tag_data_size"]),
        "record_count": len(records),
        "payload_bytes_sum": sum(row["size"] for row in records),
        "maximum_record_bytes": max((row["size"] for row in records), default=0),
        "source_extent_bytes": (previous_end - records[0]["source_file_offset"]
                                if records else 0),
        "source_gap_bytes": ((previous_end - records[0]["source_file_offset"] -
                              sum(row["size"] for row in records)) if records else 0),
        "overlap_bytes": overlap_bytes,
        "records": records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", type=Path,
                        help="directory of decompressed retail Xbox .map files")
    parser.add_argument("schema_elf", type=Path,
                        help="linked HCU ELF with compiler-derived schemas")
    parser.add_argument("--output", type=Path,
                        help="new JSON report path; refuses overwrite")
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        parser.error(f"refusing to overwrite existing report: {args.output}")
    paths = sorted(args.maps.glob("*.map"))
    if not paths:
        parser.error(f"no .map files in {args.maps}")
    try:
        manifest = SchemaManifest(Elf32(args.schema_elf)).build()
        rows = [audit_map(path, manifest) for path in paths]
    except (OSError, ValueError) as error:
        parser.exit(2, f"animation data range audit failed: {error}\n")
    report = {
        "format": "retail-animation-data-ranges-v1",
        "schema_elf_sha256": manifest["elf_sha256"],
        "map_count": len(rows),
        "interpretation": (
            "Ranges identify schema-owned animation.data bytes in each original "
            "decompressed map. They are not an external-store format, a runtime "
            "working-set measurement, or evidence that direct tag_data.address "
            "consumers can operate through a bounded cache."
        ),
        "maps": rows,
    }
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
