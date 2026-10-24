#!/usr/bin/env python3
"""Classify BSP schema gaps by compiler-proven source ownership only.

This report deliberately does not call a range padding, removable, or semantically
closed. It separates exact C-member coverage from ranges without a compiled source
declaration and records partial overlaps as unresolved layout associations.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
LAYOUT = ROOT / "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json"
OUT = ROOT / "docs/reports/m2-step7-unclassified-range-dispositions-2026-10-22.json"
EXACT = ROOT / "docs/reports/m2-step7-eight-unmapped-exact-layout-2026-10-22.json"
RETENTION_TEST = ROOT / "tests/test_step7_unmapped_bsp_range_retention.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(row: dict, exact: dict | None = None) -> dict:
    if exact is not None:
        return {
            "classification": "compiler_exact_member_ownership",
            "basis": "Dedicated R5900 compilation of the schema translation unit passed exact type-size and member-offset/extent assertions for this inventory range.",
            "member_names": [m["name"] for m in exact["members"]],
            "disposition": "open_schema_gap",
        }
    candidates = row["candidate_c_members"]
    if row["compiler_source_type_probe_status"] != "passed":
        return {
            "classification": "source_layout_unresolved",
            "basis": "No compiler-selected declaration produced exact member offsets.",
            "member_names": [],
            "disposition": "open_schema_gap",
        }
    partial = [m for m in candidates if m["relation"] != "fully-contained-by-range"]
    if partial:
        return {
            "classification": "partial_compiler_member_overlap",
            "basis": "Compiler-derived member extent crosses the schema gap boundary.",
            "member_names": [m["name"] for m in candidates],
            "disposition": "open_schema_gap",
        }
    return {
        "classification": "compiler_named_member_ownership",
        "basis": "Every reported compiler-derived C member extent lies wholly within this schema gap.",
        "member_names": [m["name"] for m in candidates],
        "disposition": "open_schema_gap",
    }


def interval_coverage(source: dict, members: list[dict]) -> dict:
    start = source["schema_range"]["offset"]
    end = start + source["schema_range"]["size"]
    clipped = sorted((max(start, m["offset"]), min(end, m["offset"] + m["size"]))
                     for m in members if m["offset"] < end and start < m["offset"] + m["size"])
    merged = []
    for left, right in clipped:
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    uncovered = []
    cursor = start
    for left, right in merged:
        if left > cursor:
            uncovered.append({"offset": cursor, "size": left - cursor})
        cursor = max(cursor, right)
    if cursor < end:
        uncovered.append({"offset": cursor, "size": end - cursor})
    crossing = [m["name"] for m in members
                if m["offset"] < end and start < m["offset"] + m["size"]
                and (m["offset"] < start or m["offset"] + m["size"] > end)]
    covered_bytes = sum(right - left for left, right in merged)
    return {
        "status": "complete" if not uncovered else "incomplete",
        "covered_bytes": covered_bytes,
        "range_bytes": end - start,
        "uncovered_intervals": uncovered,
        "intersecting_member_count": len(clipped),
        "fully_contained_member_count": sum(m["offset"] >= start and m["offset"] + m["size"] <= end for m in members),
        "boundary_crossing_members": crossing,
    }


def main() -> int:
    inventory = json.loads(INV.read_text())
    layout = json.loads(LAYOUT.read_text())
    exact_layout = json.loads(EXACT.read_text())
    if exact_layout.get("status") != "passed":
        raise ValueError("exact R5900 layout probe did not pass")
    if exact_layout.get("inventory_sha256") != sha(INV):
        raise ValueError("exact layout probe is bound to a different BSP inventory")
    if exact_layout.get("schema_source_report_sha256") != sha(LAYOUT):
        raise ValueError("exact layout probe is bound to a different source/layout report")
    exact_by_path = {r["inventory_path"]: r for r in exact_layout["ranges"]}
    rows = []
    for source in layout["ranges"]:
        exact = exact_by_path.get(source["inventory_path"])
        ownership = classify(source, exact)
        candidate_members = exact["members"] if exact else source["candidate_c_members"]
        coverage = interval_coverage(source, candidate_members)
        rows.append({
            "inventory_path": source["inventory_path"],
            "definition": source["definition"],
            "definition_id": source["definition_id"],
            "schema_range": source["schema_range"],
            **ownership,
            "candidate_members": candidate_members,
            "compiler_byte_interval_coverage": coverage,
            "source_declaration": source["source_declaration"],
            "source_declaration_sha256": source["source_declaration_sha256"],
            "probe_status": "exact_r5900_passed" if exact else source["compiler_source_type_probe_status"],
            "byte_disposition": "retained_bytes_verified_semantics_open",
            "retained_byte_evidence": {
                "path": RETENTION_TEST.relative_to(ROOT).as_posix(),
                "sha256": sha(RETENTION_TEST),
                "test": "UnmappedBspRangeRetentionTest.test_all_54_exact_unclassified_ranges_survive_schema_walk",
                "scope": "Two exact-offset payloads per range are passed through the actual linked compiler-derived definition and child schemas, checking the entire output against declared normalizations and retaining all gap bytes. This proves preservation, not runtime member semantics or target consumer execution.",
            },
        })
    counts = {name: sum(row["classification"] == name for row in rows) for name in (
        "compiler_named_member_ownership", "compiler_exact_member_ownership",
        "partial_compiler_member_overlap", "source_layout_unresolved")}
    result = {
        "format": "hcu-step7-unclassified-range-dispositions-v1",
        "generated_by": "tools/audit_step7_unclassified_range_dispositions.py",
        "inventory_path": INV.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha(INV),
        "layout_report_path": LAYOUT.relative_to(ROOT).as_posix(),
        "layout_report_sha256": sha(LAYOUT),
        "exact_layout_report_path": EXACT.relative_to(ROOT).as_posix(),
        "exact_layout_report_sha256": sha(EXACT),
        "schema_elf_sha256": inventory["schema_elf_sha256"],
        "interpretation": "Compiler ownership and byte disposition are separate. Each range has a synthetic exact-offset retained-byte check; its serialized bytes are dispositioned as opaque retained data. Consumer semantics and target execution remain open.",
        "summary": {"ranges": len(rows), **counts,
                    "compiler_owned_layout_ranges": sum(counts[k] for k in ("compiler_named_member_ownership", "compiler_exact_member_ownership", "partial_compiler_member_overlap")),
                    "complete_compiler_byte_coverage_ranges": sum(r["compiler_byte_interval_coverage"]["status"] == "complete" for r in rows),
                    "incomplete_compiler_byte_coverage_ranges": sum(r["compiler_byte_interval_coverage"]["status"] != "complete" for r in rows),
                    "ranges_with_boundary_crossing_members": sum(bool(r["compiler_byte_interval_coverage"]["boundary_crossing_members"]) for r in rows),
                    "open_schema_gaps": sum(r["disposition"] == "open_schema_gap" for r in rows),
                    "retained_byte_dispositions": sum(r["byte_disposition"] == "retained_bytes_verified_semantics_open" for r in rows),
                    "semantic_dispositions_open": len(rows)},
        "ranges": rows,
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
