"""Check that the linked HCU schemas can be exported without guessing ABI offsets."""
from collections import Counter
from pathlib import Path
import unittest

from tools.hcu_schema_manifest import Elf32, SchemaManifest


ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT / "build/hcu-ps2-closure/all/halo-local.elf"


class HcuSchemaManifestTest(unittest.TestCase):
    def test_linked_ps2_schema_export_is_complete_and_deterministic(self):
        if not ELF.is_file():
            self.skipTest("build the HCU PS2 closure ELF before schema export test")
        first = SchemaManifest(Elf32(ELF)).build()
        second = SchemaManifest(Elf32(ELF)).build()
        self.assertEqual(first, second)
        self.assertEqual(first["format"], "hcu-schema-manifest-v1")
        self.assertEqual(first["group_lists"], [
            "tag_schema_object_groups", "tag_schema_model_groups",
            "tag_schema_collision_groups", "tag_schema_render_groups",
            "tag_schema_effect_groups", "tag_schema_scenario_groups",
        ])
        self.assertGreaterEqual(len(first["groups"]), 70)
        self.assertGreaterEqual(len(first["definitions"]), 300)
        field_kinds = Counter(
            field["kind"]
            for definition in first["definitions"].values()
            for field in definition["fields"]
        )
        for kind in ("block", "struct", "data", "file_data", "reference", "tag_index"):
            self.assertGreater(field_kinds[kind], 0, kind)
        self.assertTrue(any(group.get("custom_edition_layout") for group in first["groups"]))


if __name__ == "__main__":
    unittest.main()
