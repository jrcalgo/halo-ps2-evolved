#!/usr/bin/env python3
"""Verify compiler-inventory BSP check descriptors have no serialized bytes."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
EXPECTED = {
    "structure_bsp.structure_bsp_check": ("2981296", 0),
    "structure_detail_object_data.structure_detail_object_data_check": ("2982912", 0),
    "collision_bsp.structure_collision_bsp_check": ("2988624", 0),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ZeroSizeSentinelTest(unittest.TestCase):
    def test_check_descriptors_are_nonserialized_sentinels(self) -> None:
        inventory = json.loads(INVENTORY.read_text())
        # The report pins the compiler-produced schema image that generated the
        # inventory; this guards against silently testing a stale inventory.
        schema_elf = ROOT / inventory["schema_elf"]
        self.assertTrue(schema_elf.is_file(), schema_elf)
        self.assertEqual(sha256(schema_elf), inventory["schema_elf_sha256"])

        actual = {m["path"]: m for m in inventory["members"] if m["kind"] == "check"}
        self.assertEqual(set(actual), set(EXPECTED))
        for path, (definition_id, size) in EXPECTED.items():
            with self.subTest(path=path):
                member = actual[path]
                self.assertEqual(member["definition_id"], definition_id)
                self.assertEqual(member["size"], size)
                self.assertEqual(member["count"], 1)
                self.assertEqual(member["target_level"], 0)
                self.assertEqual(member["target_offset"], 0)
                self.assertEqual(member["element_size"], 0)


if __name__ == "__main__":
    unittest.main()
