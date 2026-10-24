#!/usr/bin/env python3
"""Emit source-pinned dispositions for the 12 omitted structure-BSP root fields."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reports/m2-step7-open-root-bsp-dispositions-2026-10-22.json"
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
FIXTURE = ROOT / "tests/test_hcu_step7_open_root_bsp_dispositions.py"
UNUSED_FIXTURES = {
    "structure_bsp.sad_unused[5]": "test_sad_unused_bytes_are_preserved_without_interpretation",
    "structure_bsp.lonely_unused": "test_lonely_unused_bytes_are_preserved_without_interpretation",
    "structure_bsp.render_unused[3]": "test_render_unused_bytes_are_preserved_without_interpretation",
    "structure_bsp.cluster_unused[3]": "test_cluster_unused_bytes_are_preserved_without_interpretation",
    "structure_bsp.fog_unused[6]": "test_fog_unused_bytes_are_preserved_without_interpretation",
    "structure_bsp.weather_unused[6]": "test_weather_unused_bytes_are_preserved_without_interpretation",
    "structure_bsp.sound_unused[6]": "test_sound_unused_bytes_are_preserved_without_interpretation",
    "structure_bsp.diminishing_misc_unused[2]": "test_diminishing_misc_unused_bytes_are_preserved_without_interpretation",
}
CE = ROOT / "submodules/halo-ce-universal"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(path: str, lines: str, claim: str) -> dict:
    file_path = ROOT / path
    return {"path": path, "lines": lines, "claim": claim,
            "sha256": digest(file_path)}


def search_source_member(symbol: str) -> dict:
    """Find explicit member syntax without treating same-name declarations as readers."""
    roots = (CE / "source", CE / "port", ROOT / "submodules/halo-ps2/engine/src", ROOT / "src")
    suffixes = {".c", ".h", ".cc", ".cpp", ".hpp"}
    identifier = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(symbol) + r"(?![A-Za-z0-9_])")
    access = re.compile(r"(?:->|\.)\s*" + re.escape(symbol) + r"(?![A-Za-z0-9_])")
    identifiers = []
    accesses = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                lines = path.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, 1):
                if identifier.search(line):
                    record = {"path": path.relative_to(ROOT).as_posix(),
                              "line": line_number, "text": line.strip(),
                              "sha256": digest(path)}
                    identifiers.append(record)
                    if access.search(line):
                        accesses.append(record)
    return {
        "scope": [root.relative_to(ROOT).as_posix() for root in roots],
        "method": "case-sensitive whole-identifier scan; member readers additionally require .field or ->field syntax",
        "identifier_hits": identifiers,
        "member_access_hits": accesses,
        "result": "no explicit .field or ->field source access found" if not accesses else "explicit member access found",
        "limitation": "Does not prove absence of raw-offset, aliased, generated, assembly, or otherwise indirect consumers; semantic disposition remains open.",
    }


def main() -> None:
    inventory = json.loads(INVENTORY.read_text())
    open_rows = {row["path"]: row for row in inventory["members"]
                 if row["classification"] == "consumer-disposition-open"}
    expected = [
        "structure_bsp.vehicle_floor", "structure_bsp.vehicle_ceiling",
        "structure_bsp.sad_unused[5]", "structure_bsp.lonely_unused",
        "structure_bsp.world_bounds", "structure_bsp.render_unused[3]",
        "structure_bsp.cluster_unused[3]", "structure_bsp.fog_unused[6]",
        "structure_bsp.weather_unused[6]", "structure_bsp.sound_unused[6]",
        "structure_bsp.markers", "structure_bsp.diminishing_misc_unused[2]",
    ]
    if set(open_rows) != set(expected):
        raise SystemExit(f"expected exactly 12 inventory rows, found {sorted(open_rows)}")
    declared_types = {
        "structure_bsp.vehicle_floor": "real",
        "structure_bsp.vehicle_ceiling": "real",
        "structure_bsp.sad_unused[5]": "long[5]",
        "structure_bsp.lonely_unused": "long",
        "structure_bsp.world_bounds": "real_rectangle3d",
        "structure_bsp.render_unused[3]": "long[3]",
        "structure_bsp.cluster_unused[3]": "long[3]",
        "structure_bsp.fog_unused[6]": "long[6]",
        "structure_bsp.weather_unused[6]": "long[6]",
        "structure_bsp.sound_unused[6]": "long[6]",
        "structure_bsp.markers": "struct tag_block",
        "structure_bsp.diminishing_misc_unused[2]": "long[2]",
    }

    layout = source(
        "submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h",
        "178-220", "CE compiler structure_bsp declaration and member order")
    vehicle = source(
        "submodules/halo-ce-universal/source/units/vehicles.c", "2681-2694",
        "vehicle physics reads floor and ceiling and applies them to vertical velocity")
    visibility = source(
        "submodules/halo-ce-universal/source/structures/structure_visibility.c", "1578-1653",
        "CPU visibility traversal passes structure_bsp.world_bounds to node traversal")
    schema = source(
        "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c", "932-990",
        "schema explicitly documents markers as never read and leaves them out of the schema")
    nested_audit = source(
        "docs/reports/m2-step7-nested-bsp-field-consumers-2026-10-22.md", "21-22",
        "prior source audit says markers are retained opaque and not schema-relocated")

    resolved = {
        "structure_bsp.vehicle_floor": {
            "status": "disposition_resolved_target_behavior_open",
            "disposition": "Retain the four serialized bytes as the typed real value; do not normalize or strip. CE vehicle physics reads this value.",
            "consumer": [vehicle],
            "fixture": "test_vehicle_floor_scalar_survives_schema_walk",
        },
        "structure_bsp.vehicle_ceiling": {
            "status": "disposition_resolved_target_behavior_open",
            "disposition": "Retain the four serialized bytes as the typed real value; do not normalize or strip. CE vehicle physics reads this value.",
            "consumer": [vehicle],
            "fixture": "test_vehicle_ceiling_scalar_survives_schema_walk",
        },
        "structure_bsp.world_bounds": {
            "status": "disposition_resolved_target_behavior_open",
            "disposition": "Retain all six real bounds unchanged. CE CPU visibility traversal passes this member to node traversal; target execution remains unproven.",
            "consumer": [visibility],
            "fixture": "test_world_bounds_survive_schema_walk",
        },
        "structure_bsp.markers": {
            "status": "disposition_resolved_opaque_pointer_unusable",
            "disposition": "Retain the 12-byte block descriptor and payload as opaque bytes. The CE schema explicitly says the legacy block is never read; it is not schema-relocated and must not be dereferenced as a usable pointer.",
            "consumer": [schema, nested_audit],
            "fixture": "test_legacy_markers_bytes_are_preserved_without_relocation_claim",
        },
    }

    rows = []
    for path in expected:
        item = open_rows[path]
        if path in resolved:
            decision = resolved[path]
            evidence = [layout, *decision["consumer"]]
        else:
            symbol = path.removeprefix("structure_bsp.").split("[")[0]
            decision = {
                "status": "open_preserve_only_semantics_unresolved",
                "disposition": "Retain the complete C-layout byte range unchanged; no stripping, zeroing, normalization, or pointer interpretation is authorized.",
                "reason": "The field name/declaration and absence of a discovered named reader do not establish complete reachability or semantic irrelevance. Keep the consumer assignment open.",
                "fixture": UNUSED_FIXTURES[path],
                "fixture_sha256": digest(FIXTURE),
                "fixture_scope": "Exact compiler-layout byte interval survives schema walk unchanged; no relocation site or nested schema span intersects it. This proves preservation only, not field meaning or target execution.",
                "source_search": {"exact_symbol": symbol, **search_source_member(symbol)},
            }
            evidence = [layout]
        rows.append({
            "inventory_path": path,
            "definition": item["definition"],
            "member_type": declared_types[path],
            "offset_within_definition": item["offset_within_definition"],
            "size": item["size"],
            "inventory_classification_before": item["classification"],
            **decision,
        })

    ce_pin = subprocess.check_output(
        ["git", "-C", str(CE), "rev-parse", "HEAD"], text=True).strip()
    report = {
        "format": "m2-step7-open-root-bsp-dispositions-v1",
        "generated_by": "tools/generate_m2_step7_open_root_dispositions.py",
        "ce_source_pin": ce_pin,
        "inventory_path": str(INVENTORY.relative_to(ROOT)),
        "inventory_sha256": digest(INVENTORY),
        "schema_elf_path": inventory.get("schema_elf"),
        "schema_elf_sha256": inventory.get("schema_elf_sha256"),
        "fixture_path": str(FIXTURE.relative_to(ROOT)),
        "fixture_sha256": digest(FIXTURE),
        "generator_path": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": digest(Path(__file__)),
        "counts": {
            "source_backed_disposition_resolved": sum(
                row["status"].startswith("disposition_resolved") for row in rows),
            "consumer_behavior_target_unverified": 3,
            "opaque_pointer_unusable": 1,
            "preserve_only_semantics_open": sum(
                row["status"] == "open_preserve_only_semantics_unresolved" for row in rows),
            "preserve_only_with_exact_host_retention_fixture": sum(
                row["status"] == "open_preserve_only_semantics_unresolved" and
                bool(row.get("fixture")) for row in rows),
            "total_rows": len(rows),
        },
        "interpretation": (
            "Resolved means the byte-preservation/consumer disposition is source-backed; it does not mean a target consumer executed. "
            "The eight explicitly unused scalar ranges have exact host preservation/non-interpretation fixtures, but remain open semantically; their safe handling is to preserve unchanged. "
            "The legacy markers block is retained without claiming relocation or dereference safety."
        ),
        "layout_evidence": layout,
        "rows": rows,
        "fixture_evidence_level": "host execution using current linked compiler schema; no target execution",
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"{OUT.relative_to(ROOT)} rows={len(rows)} resolved={report['counts']['source_backed_disposition_resolved']} open={report['counts']['preserve_only_semantics_open']}")


if __name__ == "__main__":
    main()
