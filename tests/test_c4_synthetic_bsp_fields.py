"""C4 synthetic nonempty fixtures for BSP fields empty in every retail map.

For each field in m2-step7-empty-bsp-fields (empty_across_retail): the
checked-in fixture must match tools/c4_synthetic_bsp_fixtures.py regeneration,
the schema walker must accept it with the image preserved byte-exact, and a
truncated variant must be rejected.
"""
import hashlib
import json
import unittest
from pathlib import Path

from tools.ctag_schema_walk import SchemaWalkError, walk_structure_bsp
import tools.c4_synthetic_bsp_fixtures as fx

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/c4"
SOURCE_BASE = 0x70000000


@unittest.skipUnless(fx.SCHEMA_ELF.is_file(), "linked compiler schema ELF is required")
class C4SyntheticBspFieldsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = fx.build_all()
        cls.manifest_file = json.loads((FIXTURE_DIR / "manifest.json").read_text())

    def test_checked_in_fixtures_match_regeneration(self):
        self.assertEqual(fx.write_fixtures_in_memory(), self.manifest_file)
        for path, (_m, image, *_rest) in self.built.items():
            with self.subTest(path=path):
                on_disk = (FIXTURE_DIR / self.manifest_file["fields"][path]["file"]).read_bytes()
                self.assertEqual(on_disk, image)

    def test_every_fully_empty_field_round_trips_and_rejects_truncation(self):
        for path, (manifest, image, location, payload, _recipe) in self.built.items():
            with self.subTest(path=path):
                target, _size, _field_address = location
                result = walk_structure_bsp(manifest, image, SOURCE_BASE)
                self.assertTrue(any(
                    span[0] == target and span[1] == target + len(payload)
                    for span in result.spans), path)
                self.assertEqual(result.image[target:target + len(payload)], payload)
                reloc = set()
                for off in result.relocations:
                    reloc.update(range(off, off + 4))
                same = [i for i in range(len(image))
                        if i not in reloc and result.image[i] != image[i]]
                self.assertEqual(same, [], path)
                with self.assertRaises(SchemaWalkError):
                    walk_structure_bsp(manifest, bytes(image[:-1]), SOURCE_BASE)

    def test_fixture_manifest_records_hashes(self):
        for path, (_m, image, *_rest) in self.built.items():
            entry = self.manifest_file["fields"][path]
            self.assertEqual(entry["sha256"], hashlib.sha256(image).hexdigest())
            self.assertEqual(entry["image_bytes"], len(image))


if __name__ == "__main__":
    unittest.main()
