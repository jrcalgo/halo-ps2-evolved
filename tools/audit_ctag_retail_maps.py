"""Inventory linked-schema coverage and file-backed data across decompressed Xbox maps.

This is an audit, not a converter: diagnostic file-data and unknown-group
policies are explicit, and no CTAG image is emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

try:
    from .ctag_schema_walk import read_xbox_tag_region, walk_tag_image
    from .hcu_schema_manifest import Elf32, SchemaManifest
except ImportError:
    from ctag_schema_walk import read_xbox_tag_region, walk_tag_image
    from hcu_schema_manifest import Elf32, SchemaManifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_map(path: Path, manifest: dict) -> dict:
    image, base, metadata = read_xbox_tag_region(path)
    from halo2ps2.texconv import MapData

    result = walk_tag_image(manifest, image, base,
                            file_data_policy="inventory",
                            unknown_group_policy="inventory")
    unknown_counts = Counter(group for _index, group, _root in result.unsupported_groups)
    reference_targets = dict(result.reference_target_counts)
    resources = result.file_data_records
    in_image_data_bytes = Counter()
    in_image_data_counts = Counter()
    in_image_data_maximum = Counter()
    for definition, field, size, _offset in result.in_image_data_records:
        owner = f"{definition}.{field}"
        in_image_data_bytes[owner] += size
        in_image_data_counts[owner] += 1
        in_image_data_maximum[owner] = max(in_image_data_maximum[owner], size)
    file_size = metadata["file_size"]
    flags = Counter(record[3] for record in resources)
    file_data_sources: dict[str, list] = {}
    resource_intervals: dict[str, list[tuple[int, int]]] = {}
    for definition, field, size, resource_flags, offset in resources:
        source = "sounds.map" if resource_flags & 1 else "map"
        row = file_data_sources.setdefault(source, [0, 0, None, None, 0])
        row[0] += 1
        row[1] += size
        row[2] = offset if row[2] is None else min(row[2], offset)
        end = offset + size
        row[3] = end if row[3] is None else max(row[3], end)
        invalid = (offset < 0 or size < 0 or
                   (source == "map" and (size > file_size or offset > file_size - size)))
        row[4] += int(invalid)
        if not invalid and size > 0:
            resource_intervals.setdefault(source, []).append((offset, end))
    map_data = MapData.open(path)
    bitmap_images = []
    for entry in map_data.index.entries:
        if entry.group != "bitm":
            continue
        for bitmap in map_data.images(entry.tag_id):
            bitmap_images.append(bitmap)
            source = "bitmaps.map" if bitmap.flags & (1 << 8) else "map"
            invalid = (bitmap.pixel_offset < 0 or bitmap.pixel_size < 0 or
                       (source == "map" and (bitmap.pixel_size > file_size or
                                              bitmap.pixel_offset > file_size - bitmap.pixel_size)))
            if not invalid and bitmap.pixel_size > 0:
                resource_intervals.setdefault(source, []).append(
                    (bitmap.pixel_offset, bitmap.pixel_offset + bitmap.pixel_size)
                )
    bitmap_sources: dict[str, list] = {}
    invalid_bitmap_ranges = 0
    for bitmap in bitmap_images:
        source = "bitmaps.map" if bitmap.flags & (1 << 8) else "map"
        row = bitmap_sources.setdefault(source, [0, 0, None, None, 0])
        row[0] += 1
        row[1] += bitmap.pixel_size
        row[2] = bitmap.pixel_offset if row[2] is None else min(row[2], bitmap.pixel_offset)
        end = bitmap.pixel_offset + bitmap.pixel_size
        row[3] = end if row[3] is None else max(row[3], end)
        invalid = (bitmap.pixel_offset < 0 or bitmap.pixel_size < 0 or
                   (source == "map" and (bitmap.pixel_size > file_size or
                                         bitmap.pixel_offset > file_size - bitmap.pixel_size)))
        row[4] += int(invalid)
        invalid_bitmap_ranges += int(invalid)
    map_resource_ranges = [
        (bitmap.pixel_offset, bitmap.pixel_offset + bitmap.pixel_size)
        for bitmap in bitmap_images
        if not (bitmap.flags & (1 << 8)) and bitmap.pixel_size > 0
    ]
    map_resource_ranges.extend(
        (offset, offset + size)
        for _definition, _field, size, resource_flags, offset in resources
        if not (resource_flags & 1) and size > 0
    )
    map_resource_ranges.sort()
    merged_resource_ranges: list[list[int]] = []
    overlapping_resource_ranges = 0
    for start, end in map_resource_ranges:
        if not merged_resource_ranges or start > merged_resource_ranges[-1][1]:
            merged_resource_ranges.append([start, end])
        else:
            overlapping_resource_ranges += int(start < merged_resource_ranges[-1][1])
            merged_resource_ranges[-1][1] = max(merged_resource_ranges[-1][1], end)
    merged_by_source: dict[str, list[list[int]]] = {}
    for source, intervals in sorted(resource_intervals.items()):
        merged: list[list[int]] = []
        for start, end in sorted(intervals):
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        merged_by_source[source] = merged
    map_resource_union_bytes = sum(end - start for start, end in merged_resource_ranges)
    map_resource_span_bytes = (
        merged_resource_ranges[-1][1] - merged_resource_ranges[0][0]
        if merged_resource_ranges else 0
    )
    tag_start = metadata["tag_data_offset"]
    tag_end = tag_start + metadata["tag_data_size"]
    tag_resource_overlaps = [
        (max(start, tag_start), min(end, tag_end))
        for start, end in merged_resource_ranges
        if start < tag_end and tag_start < end
    ]
    return {
        "map": path.name,
        "source_sha256": sha256_file(path),
        "file_size": file_size,
        "tag_data_offset": tag_start,
        "tag_data_size": tag_end - tag_start,
        "tag_count": metadata["tag_count"],
        # The schema walker counts all bytes in typed root/block/data spans.
        # It intentionally does not count tag-name strings or opaque null-schema
        # payloads, so this is a lower bound on retained tag-image storage.
        "schema_visited_bytes_lower_bound": result.visited_bytes,
        "tag_region_bytes_not_counted_by_schema_walk":
            len(image) - result.visited_bytes,
        "schema_bytes_by_owner": dict(result.schema_bytes_by_owner),
        "in_image_data_record_count": len(result.in_image_data_records),
        "in_image_data_bytes_by_owner": dict(sorted(in_image_data_bytes.items())),
        "in_image_data_record_count_by_owner": dict(sorted(in_image_data_counts.items())),
        "in_image_data_maximum_record_bytes_by_owner": dict(sorted(in_image_data_maximum.items())),
        "largest_in_image_data_records": [
            {"definition": definition, "field": field, "size": size, "offset": offset}
            for definition, field, size, offset in sorted(
                result.in_image_data_records, key=lambda item: (-item[2], item[0], item[1])
            )[:25]
        ],
        "unsupported_roots": [
            {"index": index, "group": group, "root_offset": root}
            for index, group, root in result.unsupported_groups
        ],
        "unsupported_group_counts": dict(sorted(unknown_counts.items())),
        "references_to_unsupported_groups": {
            group: reference_targets.get(group, 0) for group in unknown_counts
        },
        "reference_count": sum(reference_targets.values()),
        "unresolved_reference_count": reference_targets.get("UNRESOLVED", 0),
        "file_data_record_count": len(resources),
        "file_data_payload_bytes_sum": sum(record[2] for record in resources),
        "file_data_flags": dict(sorted(flags.items())),
        "file_data_source_extents": {
            source: {
                "count": row[0], "payload_bytes_sum": row[1],
                "minimum_offset": row[2], "maximum_end": row[3],
                "invalid_range_count": row[4],
            }
            for source, row in sorted(file_data_sources.items())
        },
        "invalid_file_data_range_count": sum(row[4] for row in file_data_sources.values()),
        "bitmap_image_count": len(bitmap_images),
        "bitmap_source_extents": {
            source: {
                "count": row[0], "payload_bytes_sum": row[1],
                "minimum_offset": row[2], "maximum_end": row[3],
                "invalid_range_count": row[4],
            }
            for source, row in sorted(bitmap_sources.items())
        },
        "invalid_bitmap_range_count": invalid_bitmap_ranges,
        "map_file_resources": {
            "range_count": len(map_resource_ranges),
            "payload_bytes_sum": sum(end - start for start, end in map_resource_ranges),
            "union_bytes": map_resource_union_bytes,
            "span_bytes": map_resource_span_bytes,
            "gap_bytes": map_resource_span_bytes - map_resource_union_bytes,
            "merged_interval_count": len(merged_resource_ranges),
            "overlapping_range_count": overlapping_resource_ranges,
            "minimum_offset": merged_resource_ranges[0][0] if merged_resource_ranges else None,
            "maximum_end": merged_resource_ranges[-1][1] if merged_resource_ranges else None,
            "original_tag_data_offset": tag_start,
            "original_tag_data_end": tag_end,
            "tag_data_overlap_interval_count": len(tag_resource_overlaps),
            "tag_data_overlap_bytes": sum(end - start for start, end in tag_resource_overlaps),
        },
        # Exact source-separated allowlist for a future bounded random-access
        # reader. These are file-offset intervals, not EE-resident payloads.
        "resource_interval_index": {
            source: {
                "interval_count": len(intervals),
                "union_bytes": sum(end - start for start, end in intervals),
                "intervals": intervals,
            }
            for source, intervals in sorted(merged_by_source.items())
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", type=Path, help="directory of decompressed retail Xbox .map files")
    parser.add_argument("schema_elf", type=Path, help="linked HCU ELF with compiler-derived schemas")
    parser.add_argument("--output", type=Path, help="new JSON report path; refuses overwrite")
    args = parser.parse_args(argv)
    paths = sorted(args.maps.glob("*.map"))
    if not paths:
        parser.error(f"no .map files in {args.maps}")
    try:
        manifest = SchemaManifest(Elf32(args.schema_elf)).build()
        reports = []
        for path in paths:
            try:
                reports.append(audit_map(path, manifest))
            except (OSError, ValueError) as error:
                reports.append({"map": path.name, "error": str(error)})
    except (OSError, ValueError) as error:
        parser.exit(2, f"schema audit failed: {error}\n")

    group_maps: dict[str, list[str]] = {}
    total_reference_count = 0
    for report in reports:
        total_reference_count += report.get("reference_count", 0)
        for group in report.get("unsupported_group_counts", {}):
            group_maps.setdefault(group, []).append(report["map"])
    output = {
        "format": "retail-ctag-coverage-audit-v3",
        "schema_elf_sha256": manifest["elf_sha256"],
        "map_count": len(paths),
        "successful_map_count": sum("error" not in report for report in reports),
        "total_reference_fields": total_reference_count,
        "unsupported_groups": {
            group: {"map_count": len(names), "maps": names}
            for group, names in sorted(group_maps.items())
        },
        "maps": reports,
        "interpretation": (
            "schema_visited_bytes_lower_bound counts schema-declared root, block, "
            "and in-image data spans, but not tag-name strings or opaque null-schema "
            "payloads. It is therefore a lower bound, not a compaction result; "
            "unvisited bytes are not presumed disposable."
        ),
    }
    rendered = json.dumps(output, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            parser.error(f"refusing to overwrite existing report: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if output["successful_map_count"] == len(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
