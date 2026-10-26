#!/usr/bin/env python3
"""Re-key the Step 7 schema-gap source-discovery report to the current inventory.

The discovery report has no standalone generator; its only inputs that change
with a schema ELF rebuild are definition_id (an ELF address) and the schema ELF
hash.  This tool carries every gap's source declarations forward unchanged,
matching old->new gaps by (definition name, range offset, range size), and
refuses to run if the 54 gaps do not match one-to-one.
"""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "docs/reports/m2-step7-schema-gap-source-discovery-2026-10-22.json"
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", type=Path, default=DISCOVERY)
    ap.add_argument("--inventory", type=Path, default=INVENTORY)
    ap.add_argument("--output", type=Path, default=DISCOVERY)
    a = ap.parse_args()
    disc = json.loads(a.discovery.read_text())
    inv = json.loads(a.inventory.read_text())
    rows = {(m["definition"], m["offset_within_definition"], m["size"]): m
            for m in inv["members"] if m["classification"] == "unclassified"}
    seen = set()
    for gap in disc["gaps"]:
        key = (gap["definition"], gap["schema_range"]["offset"], gap["schema_range"]["size"])
        if key not in rows or key in seen:
            raise SystemExit(f"gap {key} has no one-to-one inventory row")
        seen.add(key)
        gap["definition_id"] = rows[key]["definition_id"]
    if seen != set(rows) or len(disc["gaps"]) != disc["gap_count"]:
        raise SystemExit("inventory unclassified rows and discovery gaps differ")
    disc["schema_elf_sha256"] = inv["schema_elf_sha256"]
    a.output.write_text(json.dumps(disc, indent=2) + "\n")
    print(f"rekeyed {len(seen)} gaps to schema ELF {inv['schema_elf_sha256']}")


if __name__ == "__main__":
    main()
