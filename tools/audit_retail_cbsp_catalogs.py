#!/usr/bin/env python3
"""Verify HP2 CBIX catalogs against every BSP reference in a retail map corpus.

This is a package/extent audit only. It does not assert PS2 memory fit or guest
loadability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from . import cbsp, ctag
    from .audit_retail_bsp_capacity import audit_map
except ImportError:
    import cbsp
    import ctag
    from audit_retail_bsp_capacity import audit_map


def audit_catalogs(map_dir: Path, package_dir: Path) -> dict:
    rows = []
    for map_path in sorted(map_dir.glob("*.map")):
        package_path = package_dir / (map_path.stem + ".hp2")
        if not package_path.is_file():
            raise ValueError(f"missing HP2 package for {map_path.name}")
        source = audit_map(map_path, capacity=0xFFFFFFFF)
        package_bytes = package_path.read_bytes()
        parsed = ctag._hp2_module().parse(package_bytes)
        catalog = cbsp.decode_catalog(parsed.read("CBIX"),
                                      expected_file_length=source["decompressed_file_size"])
        expected = {(row["file_offset"], row["file_size"])
                    for row in source["structure_bsps"]}
        actual = set()
        section_tags = set()
        cbsp_bytes = 0
        for entry in catalog:
            if entry.section_tag in section_tags:
                raise ValueError(f"{map_path.stem}: duplicate CBSP section tag")
            payload = parsed.read(entry.section_tag)
            decoded = cbsp.decode(payload, max_image_size=len(payload))
            extent = (decoded.source_file_offset, decoded.source_file_size)
            if extent != (entry.file_offset, entry.file_size):
                raise ValueError(f"{map_path.stem}: catalog/CBSP extent mismatch")
            if extent not in expected:
                raise ValueError(f"{map_path.stem}: CBSP targets a non-reference extent")
            actual.add(extent)
            section_tags.add(entry.section_tag)
            cbsp_bytes += len(payload)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"{map_path.stem}: incomplete BSP catalog; missing={missing}, extra={extra}")
        rows.append({
            "map": map_path.stem,
            "source_sha256": source["source_sha256"],
            "package_sha256": hashlib.sha256(package_bytes).hexdigest(),
            "package_bytes": len(package_bytes),
            "bsp_count": len(expected),
            "cbsp_payload_bytes": cbsp_bytes,
        })
    if not rows:
        raise ValueError("no retail maps found")
    return {
        "format": "retail-ce-hp2-cbsp-catalog-audit-v1",
        "map_count": len(rows),
        "bsp_count": sum(row["bsp_count"] for row in rows),
        "total_package_bytes": sum(row["package_bytes"] for row in rows),
        "total_cbsp_payload_bytes": sum(row["cbsp_payload_bytes"] for row in rows),
        "interpretation": "Every catalog maps each audited retail BSP extent to one valid CBSP section; no memory-fit or runtime-load claim.",
        "maps": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", type=Path, help="directory containing decompressed retail maps")
    parser.add_argument("packages", type=Path, help="directory containing same-stem HP2 packages")
    parser.add_argument("--output", type=Path, required=True,
                        help="new JSON report path; refuses to overwrite")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite existing report: {args.output}")
    try:
        report = audit_catalogs(args.maps, args.packages)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"CBSP catalog audit failed: {error}\n")
    print(json.dumps({key: value for key, value in report.items() if key != "maps"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
