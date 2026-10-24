from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_profile_chunks as profile


class Hcp2SegmentedProfileTests(unittest.TestCase):
    def test_c_reader_maps_ranges_across_segments(self):
        with tempfile.TemporaryDirectory() as td:
            exe = Path(td) / "fixture"
            package = Path(td) / "profile.hcp"
            subprocess.run(["cc", "-std=c99", "-I", str(ROOT / "src"),
                            str(ROOT / "tests/hcu_asset_profile_hcp2_main.c"),
                            str(ROOT / "src/stream/hcu_asset_profile.c"),
                            str(ROOT / "src/stream/sha256.c"), "-o", str(exe)], check=True)
            ce = bytes((i * 13 + 7) & 255 for i in range(140123))
            package.write_bytes(profile.encode(7, {(1, 0): ce, (3, 0): b"sound"}))
            result = subprocess.run([str(exe), str(package)], capture_output=True,
                                    text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "HCP2 segmented range OK")


if __name__ == "__main__":
    unittest.main()
