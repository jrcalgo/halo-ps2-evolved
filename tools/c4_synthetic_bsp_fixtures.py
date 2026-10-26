#!/usr/bin/env python3
"""Generate deterministic synthetic nonempty BSP fixtures for C4 empty fields.

One fixture per BSP block/data field that is empty in every retail BSP
(m2-step7-empty-bsp-fields-2026-10-22.json: empty_across_retail). Each image is
built by tools/audit_step7_empty_bsp_fields.make_synthetic_block against the
linked schema ELF pinned in the inventory. Output: tests/fixtures/c4/<path>.bin
plus tests/fixtures/c4/manifest.json (sha256 and recipe per field).

Usage: python3 -I tools/c4_synthetic_bsp_fixtures.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_step7_empty_bsp_fields import make_synthetic_block  # noqa: E402
from tools.hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402

SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
EMPTY_REPORT = ROOT / "docs/reports/m2-step7-empty-bsp-fields-2026-10-22.json"
FIXTURE_DIR = ROOT / "tests/fixtures/c4"


def empty_across_retail() -> list[str]:
    return json.loads(EMPTY_REPORT.read_text())["empty_across_retail"]


def build_all() -> dict:
    """Return {path: (image, location, payload, recipe)} for each fully-empty field."""
    manifest = SchemaManifest(Elf32(SCHEMA_ELF)).build()
    inventory = json.loads(INVENTORY.read_text())
    out = {}
    for path in empty_across_retail():
        member = next(m for m in inventory["members"]
                      if m["path"] == path and m["kind"] in ("block", "data"))
        out[path] = (manifest,) + make_synthetic_block(manifest, member)
    return out


def write_fixtures() -> dict:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    entries = {}
    for path, (_manifest, image, location, payload, recipe) in build_all().items():
        name = path.replace(".", "__") + ".bin"
        (FIXTURE_DIR / name).write_bytes(image)
        entries[path] = {
            "file": name,
            "sha256": hashlib.sha256(image).hexdigest(),
            "image_bytes": len(image),
            "payload_bytes": len(payload),
            "construction_recipe": recipe,
        }
    manifest = {"schema_elf": SCHEMA_ELF.relative_to(ROOT).as_posix(),
                "fields": entries}
    (FIXTURE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify checked-in fixtures match regeneration instead of writing")
    args = ap.parse_args(argv)
    if args.check:
        expected = json.loads((FIXTURE_DIR / "manifest.json").read_text())
        generated = write_fixtures_in_memory()
        if generated != expected:
            print("fixtures stale; regenerate without --check", file=sys.stderr)
            return 1
        return 0
    write_fixtures()
    return 0


def write_fixtures_in_memory() -> dict:
    entries = {}
    for path, (_manifest, image, location, payload, recipe) in build_all().items():
        entries[path] = {
            "file": path.replace(".", "__") + ".bin",
            "sha256": hashlib.sha256(image).hexdigest(),
            "image_bytes": len(image),
            "payload_bytes": len(payload),
            "construction_recipe": recipe,
        }
    return {"schema_elf": SCHEMA_ELF.relative_to(ROOT).as_posix(), "fields": entries}


if __name__ == "__main__":
    raise SystemExit(main())
