"""Exercise the bounded PS2 HP2 decoder against a retail-derived CTAG section."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import os

from tools.ctag import _hp2_module


class RetailHp2StreamingTests(unittest.TestCase):
    def test_bloodgulch_ctag_stream_matches_python_section_byte_for_byte(self):
        root = Path(__file__).resolve().parents[1]
        pack_path = root / "build/retail-maps/bloodgulch-with-bsps.hp2"
        if not pack_path.is_file():
            self.skipTest("build tests/test_pack_retail_ctag_hp2.py fixture first")
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")

        pack = _hp2_module().parse(pack_path.read_bytes())
        ctag = pack.find("CTAG")
        self.assertEqual((ctag.raw_size, ctag.stored_size),
                         (4_556_496, 1_901_809))
        expected = pack.read("CTAG")
        self.assertEqual(len(expected), ctag.raw_size)

        with tempfile.TemporaryDirectory(prefix="hcu-hp2-stream-") as temp:
            temp_path = Path(temp)
            expected_path = temp_path / "ctag.raw"
            expected_path.write_bytes(expected)
            executable = temp_path / "test-hp2-stream-retail"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined",
                "-I" + str(root / "submodules/halo-ps2/engine/src"),
                str(root / "submodules/halo-ps2/engine/tests/test_hp2_stream_retail.c"),
                str(root / "submodules/halo-ps2/engine/src/stream/hp2.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([
                str(executable), str(pack_path), "CTAG", str(expected_path),
            ], check=True, capture_output=True, text=True,
            env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})

        self.assertIn("HP2 stream exact: CTAG raw=4556496 stored=1901809 scratch=86010",
                      result.stdout)


if __name__ == "__main__":
    unittest.main()
