"""CRNG range-index writer/parser and parent C authorization parity."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import ctag_resources


class CtagResourceIndexTests(unittest.TestCase):
    def fixture(self):
        return ctag_resources.encode(1000, 400, 100,
                                     [(100, 20), (200, 50), (600, 100)])

    def test_round_trip_and_exact_read_authorization(self):
        decoded = ctag_resources.decode(self.fixture(), expected_file_length=1000,
                                        expected_tag_data_offset=400,
                                        expected_tag_data_size=100)
        self.assertEqual(decoded.intervals, ((100, 120), (200, 250), (600, 700)))
        self.assertTrue(decoded.allows(110, 10))
        self.assertFalse(decoded.allows(119, 2))
        self.assertFalse(decoded.allows(150, 1))
        self.assertFalse(decoded.allows(400, 1))
        self.assertFalse(decoded.allows(999, 2))
        self.assertFalse(decoded.allows(100, 0))

    def test_rejects_wrong_identity_crc_and_noncanonical_ranges(self):
        payload = self.fixture()
        for kwargs in (
            dict(expected_file_length=999, expected_tag_data_offset=400,
                 expected_tag_data_size=100),
            dict(expected_file_length=1000, expected_tag_data_offset=401,
                 expected_tag_data_size=100),
            dict(expected_file_length=1000, expected_tag_data_offset=400,
                 expected_tag_data_size=99),
        ):
            with self.assertRaises(ctag_resources.ResourceIndexError):
                ctag_resources.decode(payload, **kwargs)
        damaged = bytearray(payload)
        damaged[-1] ^= 1
        with self.assertRaisesRegex(ctag_resources.ResourceIndexError, "checksum"):
            ctag_resources.decode(damaged, expected_file_length=1000,
                                  expected_tag_data_offset=400,
                                  expected_tag_data_size=100)
        for rows in ([(100, 20), (119, 4)], [(100, 20), (120, 10)],
                     [(450, 1)], [(1000, 1)]):
            with self.assertRaises(ctag_resources.ResourceIndexError):
                ctag_resources.encode(1000, 400, 100, rows)

    def test_parent_c_parser_matches_python_wire_contract(self):
        root = Path(__file__).resolve().parents[1]
        cc = shutil.which("cc")
        if not cc:
            self.skipTest("host C compiler is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            payload = directory / "fixture.crng"
            payload.write_bytes(self.fixture())
            executable = directory / "ctag-resource-test"
            subprocess.run([
                cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Isrc", "-I" + str(root / "submodules/halo-ps2/engine/src"),
                str(root / "tests/ctag_resource_index_main.c"),
                str(root / "src/stream/ctag_resource_index.c"),
                str(root / "submodules/halo-ps2/engine/src/stream/hp2.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable), str(payload)], check=True,
                           capture_output=True, text=True)

    def test_retail_bloodgulch_index_matches_audited_file_ranges(self):
        root = Path(__file__).resolve().parents[1]
        retail = root / "data/retail/weapon-audit-maps/bloodgulch.map"
        elf = root / "build/hcu-ps2-closure/all/halo-local.elf"
        if not retail.is_file() or not elf.is_file():
            self.skipTest("retail Blood Gulch map and schema ELF are required")
        from tools.audit_ctag_retail_maps import audit_map
        from tools.hcu_schema_manifest import Elf32, SchemaManifest

        manifest = SchemaManifest(Elf32(elf)).build()
        map_audit = audit_map(retail, manifest)
        payload = ctag_resources.from_audit(map_audit)
        index = ctag_resources.decode(
            payload, expected_file_length=map_audit["file_size"],
            expected_tag_data_offset=map_audit["tag_data_offset"],
            expected_tag_data_size=map_audit["tag_data_size"],
        )
        self.assertEqual(len(index.intervals), 1200)
        self.assertEqual(sum(end - start for start, end in index.intervals), 35_348_740)
        self.assertTrue(index.allows(1_298_432, 4096))
        self.assertFalse(index.allows(36_943_360, 16))


if __name__ == "__main__":
    unittest.main()
