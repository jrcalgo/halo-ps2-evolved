import unittest
from pathlib import Path
import shutil
import subprocess
import tempfile

from tools import hmap


class HmapTests(unittest.TestCase):
    def identity(self):
        return hmap.MapIdentity("ui", 1000, 400, 100, bytes(range(32)))

    def test_round_trip_and_exact_resolver_identity(self):
        value = self.identity()
        payload = hmap.encode(value.map_name, value.file_length,
                              value.tag_data_offset, value.tag_data_size,
                              value.source_sha256)
        self.assertEqual(len(payload), 72)
        self.assertEqual(hmap.decode(payload, expected_map_name="ui"), value)
        with self.assertRaisesRegex(hmap.HmapError, "resolver"):
            hmap.decode(payload, expected_map_name="b30")

    def test_rejects_malformed_identity_and_bounds(self):
        value = self.identity()
        payload = bytearray(hmap.encode(value.map_name, value.file_length,
                                        value.tag_data_offset,
                                        value.tag_data_size,
                                        value.source_sha256))
        for offset, replacement in ((0, b"NOPE"), (4, b"\x02\0\0\0"),
                                    (8, b"\x00\0\0\0"),
                                    (68, b"\xff\0\0\0")):
            damaged = bytearray(payload)
            damaged[offset:offset + len(replacement)] = replacement
            with self.subTest(offset=offset), self.assertRaises(hmap.HmapError):
                hmap.decode(bytes(damaged))
        with self.assertRaises(hmap.HmapError):
            hmap.encode("../ui", 1000, 400, 100, bytes(32))
        with self.assertRaises(hmap.HmapError):
            hmap.encode("ui", 1000, 999, 2, bytes(32))

    def test_parent_c_parser_matches_python_record(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            record = directory / "ui.hmap"
            record.write_bytes(hmap.encode("ui", 1000, 400, 100,
                                           bytes(range(32))))
            executable = directory / "hmap-test"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Isrc", str(root / "tests/hmap_main.c"),
                str(root / "src/stream/hmap.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable), str(record), "ui"], check=True)
            rejected = subprocess.run([str(executable), str(record), "b30"])
            self.assertEqual(rejected.returncode, 2)


if __name__ == "__main__":
    unittest.main()
