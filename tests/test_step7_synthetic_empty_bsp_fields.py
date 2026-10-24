"""Synthetic schema coverage for BSP fields empty in the stock MP corpus.

The retail multiplayer corpus has zero pathfinding-edge records on every map,
but CE's path builder still owns this schema field. This fixture makes the
block non-empty without pretending retail occupancy demonstrates traversal.
"""
import struct
import json
import hashlib
from pathlib import Path
import unittest

from tools.ctag_schema_walk import SchemaWalkError, walk_structure_bsp
from tools.hcu_schema_manifest import Elf32, SchemaManifest
from tools.audit_step7_empty_bsp_fields import build_report, make_synthetic_block


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
SOURCE_BASE = 0x70000000
ROOT_OFFSET = 32
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
RETAIL_AUDIT = ROOT / "docs/reports/retail-bsp-cbsp-audit-c0-2026-10-22.json"
EMPTY_REPORT = ROOT / "docs/reports/m2-step7-empty-bsp-fields-2026-10-22.json"


def make_synthetic_bsp(manifest, edge_bytes=b"\x03\x05\x07"):
    group = next(item for item in manifest["groups"] if item["group"] == "sbsp")
    definition = manifest["definitions"][str(group["definition"])]
    edge = next(field for field in definition["fields"]
                if field["name"] == "pathfinding_edges")
    target = ROOT_OFFSET + definition["size"]
    target = (target + 3) & ~3
    image = bytearray(target + len(edge_bytes))
    struct.pack_into("<I", image, 0, SOURCE_BASE + ROOT_OFFSET)
    image[20:24] = b"psbs"
    struct.pack_into("<iII", image, ROOT_OFFSET + edge["offset"],
                     len(edge_bytes), SOURCE_BASE + target, 0xDEADBEEF)
    image[target:target + len(edge_bytes)] = edge_bytes
    return bytes(image), edge["offset"], target, edge_bytes


class SyntheticEmptyBspFieldTest(unittest.TestCase):
    @unittest.skipUnless(SCHEMA_ELF.is_file(), "linked compiler schema ELF is required")
    def test_pathfinding_edges_nonempty_block_is_checked_and_preserved(self):
        manifest = SchemaManifest(Elf32(SCHEMA_ELF)).build()
        image, field_offset, target, payload = make_synthetic_bsp(manifest)

        result = walk_structure_bsp(manifest, image, SOURCE_BASE)

        self.assertIn((target, target + len(payload),
                       "block structure_bsp.pathfinding_edges"), result.spans)
        self.assertIn(ROOT_OFFSET + field_offset + 4, result.relocations)
        self.assertEqual(struct.unpack_from(
            "<I", result.image, ROOT_OFFSET + field_offset + 4)[0], target)
        self.assertEqual(result.image[target:target + len(payload)], payload)
        self.assertEqual(struct.unpack_from(
            "<I", result.image, ROOT_OFFSET + field_offset + 8)[0], 0)

    @unittest.skipUnless(SCHEMA_ELF.is_file(), "linked compiler schema ELF is required")
    def test_pathfinding_edges_nonempty_extent_outside_image_is_rejected(self):
        manifest = SchemaManifest(Elf32(SCHEMA_ELF)).build()
        image, field_offset, _target, payload = make_synthetic_bsp(manifest)
        truncated = bytearray(image[:-1])

        with self.assertRaisesRegex(SchemaWalkError, "leaves"):
            walk_structure_bsp(manifest, bytes(truncated), SOURCE_BASE)

    @unittest.skipUnless(SCHEMA_ELF.is_file(), "linked compiler schema ELF is required")
    def test_every_bsp_block_or_data_field_empty_in_any_retail_bsp_has_synthetic_coverage(self):
        """Empty-on-some-maps is structural coverage debt, not consumer proof."""
        generated = build_report(INVENTORY, RETAIL_AUDIT)
        recorded = json.loads(EMPTY_REPORT.read_text())
        self.assertEqual(generated, recorded)
        self.assertEqual(generated["retail_map_count"], 24)
        self.assertEqual(generated["retail_structure_bsp_count"], 82)
        self.assertEqual(len(generated["empty_across_retail"]), 9)

        manifest = SchemaManifest(Elf32(SCHEMA_ELF)).build()
        group = next(item for item in manifest["groups"] if item["group"] == "sbsp")
        candidate_paths = set(generated["empty_in_any_retail"])
        self.assertEqual(len(candidate_paths), 41)
        inventory = json.loads(INVENTORY.read_text())
        tested_paths = {m["path"] for m in inventory["members"]
                        if m["kind"] in ("block", "data") and m["path"] in candidate_paths}
        self.assertEqual(tested_paths, candidate_paths)

        for path in sorted(candidate_paths):
            with self.subTest(path=path):
                member = next(m for m in inventory["members"] if m["path"] == path
                              and m["kind"] in ("block", "data"))
                image, location, payload, recipe = make_synthetic_block(manifest, member)
                field_report = next(f for f in generated["fields"] if f["path"] == path)
                descriptor = field_report["synthetic_fixture"]
                self.assertEqual(descriptor["sha256"], hashlib.sha256(image).hexdigest())
                self.assertEqual(descriptor["image_bytes"], len(image))
                self.assertEqual(descriptor["schema_elf_sha256"], inventory["schema_elf_sha256"])
                self.assertEqual(descriptor["construction_recipe"], recipe)
                target, size, field_address = location
                result = walk_structure_bsp(manifest, image, SOURCE_BASE)
                span = (target, target + len(payload), f"{member['kind']} {path}")
                self.assertIn(span, result.spans)
                pointer_offset = field_address + (12 if member["kind"] == "data" else 4)
                self.assertIn(pointer_offset, result.relocations)
                self.assertEqual(struct.unpack_from(
                    "<I", result.image, pointer_offset)[0], target)
                self.assertEqual(result.image[target:target + len(payload)], payload)

                malformed = image[:-1]
                with self.assertRaisesRegex(SchemaWalkError, "leaves"):
                    walk_structure_bsp(manifest, bytes(malformed), SOURCE_BASE)


if __name__ == "__main__":
    unittest.main()
