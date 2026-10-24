"""Compare the bounded engine section visitor with the legacy full-output API."""
import hashlib
import os
from pathlib import Path
import subprocess
import unittest


class WorldSectionVisitorTests(unittest.TestCase):
    def test_longest_ctag_and_bsp_stream_bytes_match_full_section_load(self):
        root = Path(__file__).resolve().parents[1]
        package_cases = (
            (root / "build/hcu-parent-link-probe/maps/ui.hp2",
             "a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90",
             (("CTAG", 1_547_396), ("CRNG", 2_900), ("HMAP", 72),
              ("B000", 2_288), ("CBIX", 44))),
            (root / "build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2",
             "6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b",
             (("CTAG", 4_339_096), ("CRNG", 9_380), ("HMAP", 72),
              ("B000", 377_388), ("CBIX", 44))),
            (root / "build/retail-maps/bloodgulch-with-bsps.hp2",
             "ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011",
             (("CTAG", 4_556_496), ("CRNG", 9_636), ("HMAP", 72),
              ("B000", 1_303_092), ("CBIX", 44))),
        )
        available = [(path, digest, sections)
                     for path, digest, sections in package_cases
                     if path.is_file()]
        if not available:
            self.skipTest("frozen UI/Longest/Blood Gulch HP2 packages are not available")
        engine = root / "submodules/halo-ps2/engine"
        executable = root / "build/test-world-section-visitor"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-I" + str(engine / "src"),
            "-I" + str(root / "submodules/halo-ps2/engine/tests/hp2_world_shim"),
            str(engine / "tests/test_world_section_visitor.c"),
            str(engine / "src/world/section.c"),
            str(engine / "src/core/mem.c"),
            str(engine / "src/stream/hp2.c"),
            str(engine / "src/stream/file.c"),
            "-o", str(executable),
        ], check=True, capture_output=True, text=True)
        for package, expected_digest, sections in available:
            self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(),
                             expected_digest)
            for tag, size in sections:
                result = subprocess.run([
                    str(executable), str(package), tag, str(size),
                ], check=True, capture_output=True, text=True,
                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})
                self.assertIn(
                    f"visitor parity: tag={tag} bytes={size} scratch_high=98304",
                    result.stdout)


if __name__ == "__main__":
    unittest.main()
