"""Retention checks for ranges omitted by the compiler-derived BSP schemas.

Each fixture uses the real SchemaManifest and all of its child definitions;
only the sbsp group's root definition is redirected to the inventory target.
"""
from __future__ import annotations

import copy
import hashlib
import json
import struct
import unittest
from pathlib import Path

from tools.ctag_schema_walk import walk_structure_bsp
from tools.hcu_schema_manifest import Elf32, SchemaManifest

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
SOURCE_BASE = 0x70000000
ROOT_OFFSET = 24


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UnmappedBspRangeRetentionTest(unittest.TestCase):
    def test_all_54_exact_unclassified_ranges_survive_schema_walk(self) -> None:
        inventory = json.loads(INVENTORY.read_text())
        schema_elf = ROOT / inventory["schema_elf"]
        self.assertTrue(schema_elf.is_file())
        self.assertEqual(sha256(schema_elf), inventory["schema_elf_sha256"])
        real_manifest = SchemaManifest(Elf32(schema_elf)).build()
        rows = [row for row in inventory["members"]
                if row["classification"] == "unclassified"]
        self.assertEqual(len(rows), 54)
        inventory_definitions = {item["definition_id"]: item
                                 for item in inventory["definitions"]}

        for row in rows:
            definition_id = row["definition_id"]
            offset = row["offset_within_definition"]
            byte_count = row["size"]
            definition = inventory_definitions[definition_id]
            definition_size = definition["serialized_size"]
            with self.subTest(member=row["path"]):
                self.assertIn(str(definition_id), real_manifest["definitions"])
                self.assertGreater(byte_count, 0)
                self.assertGreaterEqual(offset, 0)
                self.assertLessEqual(offset + byte_count, definition_size)

                # Keep every compiler-derived field and child definition. The
                # root slot alone selects the exact definition under test.
                manifest = copy.deepcopy(real_manifest)
                sbsp = next(group for group in manifest["groups"]
                            if group["group"] == "sbsp")
                sbsp["definition"] = int(definition_id)
                self.assertEqual(manifest["definitions"][str(definition_id)]["size"],
                                 definition_size)

                root_size = definition_size
                source = bytearray(ROOT_OFFSET + root_size)
                struct.pack_into("<I", source, 0, SOURCE_BASE + ROOT_OFFSET)
                source[20:24] = b"psbs"

                # Inject two payloads into the inventoried gap, leaving all
                # schema-declared fields zero so the real walker can traverse
                # the complete definition without fabricated child records.
                for salt in (0x31, 0xD7):
                    candidate = bytearray(source)
                    marker = bytes((salt + i * 17) & 0xFF
                                   for i in range(byte_count))
                    candidate[ROOT_OFFSET + offset:
                              ROOT_OFFSET + offset + byte_count] = marker
                    result = walk_structure_bsp(manifest, bytes(candidate), SOURCE_BASE)
                    expected = bytearray(candidate)
                    # Replay the walker's declared root/schema normalizations;
                    # all other bytes, including the injected gap, must match.
                    for field_offset, previous, value, _reason in result.normalizations:
                        self.assertEqual(
                            struct.unpack_from("<I", expected, field_offset)[0], previous)
                        struct.pack_into("<I", expected, field_offset, value)
                    self.assertEqual(result.image, bytes(expected))
                    self.assertEqual(
                        result.image[ROOT_OFFSET + offset:
                                     ROOT_OFFSET + offset + byte_count], marker)
                    self.assertEqual(result.normalizations[0],
                                     (0, SOURCE_BASE + ROOT_OFFSET, ROOT_OFFSET,
                                      "internal-pointer"))


if __name__ == "__main__":
    unittest.main()
