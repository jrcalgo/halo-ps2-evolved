#!/usr/bin/env python3
"""Crosswalk compiler-inventory BSP block/data fields against retail occupancy.

The retail CBSP audit emits nonzero schema-owned extents by owner. For each
serialized top-level block in the compiler inventory, absence of that owner
from a BSP's emitted owner map means the field serialized no element bytes in
that BSP. This tool deliberately says nothing about runtime consumer use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.hcu_schema_manifest import Elf32, SchemaManifest
DEFAULT_INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
DEFAULT_RETAIL_AUDIT = ROOT / "docs/reports/retail-bsp-cbsp-audit-c0-2026-10-22.json"
DEFAULT_OUTPUT = ROOT / "docs/reports/m2-step7-empty-bsp-fields-2026-10-22.json"
SOURCE_BASE = 0x70000000
ROOT_OFFSET = 32


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_synthetic_block(manifest: dict, member: dict):
    """Build a deterministic minimal nonempty BSP image for one inventory row."""
    group = next(item for item in manifest["groups"] if item["group"] == "sbsp")
    root_def = manifest["definitions"][str(group["definition"])]
    target_container_id = str(member["definition_id"])

    def find_route(definition_id, seen):
        if str(definition_id) == target_container_id:
            return []
        if str(definition_id) in seen:
            return None
        seen = seen | {str(definition_id)}
        definition = manifest["definitions"][str(definition_id)]
        for field in definition["fields"]:
            child_id = field.get("definition")
            if field["kind"] not in ("struct", "block") or child_id is None:
                continue
            suffix = find_route(child_id, seen)
            if suffix is not None:
                return [field["name"], *suffix]
        return None

    route = find_route(group["definition"], set())
    if route is None:
        raise ValueError(f"cannot reach containing definition for {member['path']}")
    prefix = member["definition"] + "."
    if not member["path"].startswith(prefix):
        raise ValueError(f"inventory path does not match its definition: {member['path']}")
    route.append(member["path"][len(prefix):])
    image = bytearray(ROOT_OFFSET + root_def["size"])
    struct.pack_into("<I", image, 0, SOURCE_BASE + ROOT_OFFSET)
    image[20:24] = b"psbs"
    cursor = len(image)
    target_location = None
    target_payload = None
    route_blocks = []

    def descend(definition, base, remaining):
        nonlocal cursor, target_location, target_payload
        name = remaining[0]
        field = next(field for field in definition["fields"] if field["name"] == name)
        field_address = base + field["offset"]
        target_definition = manifest["definitions"].get(str(field.get("definition")))
        if field["kind"] == "struct":
            descend(target_definition, field_address, remaining[1:])
            return
        if field["kind"] == "data" and len(remaining) == 1:
            payload = b"DATA"
            element_offset = (cursor + 3) & ~3
            cursor = element_offset + len(payload)
            if len(image) < cursor:
                image.extend(bytes(cursor - len(image)))
            struct.pack_into("<i", image, field_address, len(payload))
            struct.pack_into("<I", image, field_address + 12, SOURCE_BASE + element_offset)
            target_location = (element_offset, len(payload), field_address)
            target_payload = payload
            image[element_offset:element_offset + len(payload)] = payload
            return
        if field["kind"] != "block":
            raise ValueError(f"unsupported path member {member['path']}: {field['kind']} {name}")
        element_definition = target_definition
        payload_size = max(1, element_definition["size"])
        element_offset = (cursor + 3) & ~3
        cursor = element_offset + payload_size
        if len(image) < cursor:
            image.extend(bytes(cursor - len(image)))
        struct.pack_into("<iII", image, field_address, 1,
                         SOURCE_BASE + element_offset, 0)
        route_blocks.append({"field": name, "element_count": 1})
        if len(remaining) == 1:
            target_location = (element_offset, payload_size, field_address)
            target_payload = bytes(payload_size)
            image[element_offset:element_offset + payload_size] = target_payload
            return
        descend(element_definition, element_offset, remaining[1:])

    descend(root_def, ROOT_OFFSET, route)
    recipe = {
        "route": route,
        "ancestor_block_counts": route_blocks[:-1],
        "target_kind": member["kind"],
        "target_block_count": 1 if member["kind"] == "block" else None,
        "payload_encoding": ("zero bytes" if member["kind"] == "block" else "ASCII DATA"),
        "payload_bytes": len(target_payload),
        "alignment_bytes": 4,
        "root_offset": ROOT_OFFSET,
        "source_base": SOURCE_BASE,
        "malformed_variant": "truncate the final image byte; schema walker rejects the leaving extent",
    }
    return bytes(image), target_location, target_payload, recipe


def build_report(inventory_path: Path, audit_path: Path) -> dict:
    inventory = json.loads(inventory_path.read_text())
    audit = json.loads(audit_path.read_text())
    schema_elf_path = ROOT / inventory["schema_elf"]
    if sha256(schema_elf_path) != inventory["schema_elf_sha256"]:
        raise ValueError("compiler schema ELF does not match the inventory pin")
    manifest = SchemaManifest(Elf32(schema_elf_path)).build()
    fields = [m for m in inventory["members"] if m["kind"] in ("block", "data")]
    bsp_rows = []
    for map_row in audit["maps"]:
        for bsp in map_row["structure_bsps"]:
            bsp_rows.append({
                "map": map_row["map"],
                "path": bsp["path"],
                "owners": set(bsp["schema_bytes_by_owner"]),
            })
    field_rows = []
    for field in fields:
        owner = f"{field['kind']} {field['path']}"
        present = [row for row in bsp_rows if owner in row["owners"]]
        row = {
            "path": field["path"],
            "kind": field["kind"],
            "inventory_definition_id": field["definition_id"],
            "inventory_offset": field["offset_within_definition"],
            "element_size": field["element_size"],
            "retail_bsp_count": len(bsp_rows),
            "retail_nonempty_bsp_count": len(present),
            "retail_empty_bsp_count": len(bsp_rows) - len(present),
            "nonempty_examples": [f"{r['map']}:{r['path']}" for r in present[:5]],
            "consumer_semantics_proven": False,
        }
        if row["retail_empty_bsp_count"]:
            image, _location, payload, recipe = make_synthetic_block(manifest, field)
            row["synthetic_fixture"] = {
                "sha256": hashlib.sha256(image).hexdigest(),
                "image_bytes": len(image),
                "schema_elf_sha256": inventory["schema_elf_sha256"],
                "construction_recipe": recipe,
            }
        field_rows.append(row)
    return {
        "format": "hcu-step7-empty-retail-bsp-field-audit-v1",
        "status": "complete-corpus-occupancy-crosswalk",
        "interpretation": (
            "Counts whether each compiler-inventory serialized BSP block/data field "
            "has serialized element bytes in the supplied audited retail corpus. "
            "Empty means no emitted owner extent; it does not establish that the "
            "field is unused or that the retail parser/consumer can be removed."
        ),
        "inputs": {
            "inventory": str(inventory_path.relative_to(ROOT)),
            "inventory_sha256": sha256(inventory_path),
            "retail_audit": str(audit_path.relative_to(ROOT)),
            "retail_audit_sha256": sha256(audit_path),
            "schema_elf_sha256": inventory["schema_elf_sha256"],
            "retail_schema_elf_sha256": audit["schema_elf_sha256"],
        },
        "retail_map_count": audit["map_count"],
        "retail_structure_bsp_count": len(bsp_rows),
        "serialized_block_and_data_field_count": len(fields),
        "empty_across_retail": [r["path"] for r in field_rows
                                if r["retail_empty_bsp_count"] == len(bsp_rows)],
        "empty_in_any_retail": [r["path"] for r in field_rows
                                if r["retail_empty_bsp_count"] > 0],
        "fields": field_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--retail-audit", type=Path, default=DEFAULT_RETAIL_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report(args.inventory, args.retail_audit)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    try:
        output_label = args.output.relative_to(ROOT)
    except ValueError:
        output_label = args.output
    print(f"wrote {output_label}: {report['retail_structure_bsp_count']} BSPs, "
          f"{len(report['empty_across_retail'])} fields empty across corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
