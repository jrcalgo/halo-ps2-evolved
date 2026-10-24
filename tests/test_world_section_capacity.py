"""Exercise the converted retail UI HP2 sections in their assigned EE arenas."""
from pathlib import Path
import shutil
import subprocess
import unittest

from tools.ctag import _hp2_module


class RetailSectionCapacityTests(unittest.TestCase):
    def _compile_section_fixture(self, root):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        exe = root / "build/test-world-section-capacity"
        subprocess.run([
            compiler, "-std=gnu11", "-D_EE", "-Wall", "-Wextra", "-Werror",
            "-I" + str(root / "tests/hcu_ctag_mount_shim"),
            "-I" + str(root / "submodules/halo-ce-universal/port/ps2/include"),
            "-I" + str(root / "submodules/halo-ps2/engine/src"),
            "-I" + str(root / "submodules/ps2sdk/common/include"),
            str(root / "tests/world_section_capacity_main.c"),
            str(root / "submodules/halo-ps2/engine/src/world/section.c"),
            str(root / "submodules/halo-ps2/engine/src/stream/hp2.c"),
            str(root / "submodules/halo-ps2/engine/src/stream/file.c"),
            str(root / "submodules/halo-ps2/engine/src/core/mem.c"),
            str(root / "submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c"),
            "-o", str(exe),
        ], check=True, capture_output=True, text=True)
        return exe

    def test_ui_ctag_crng_fit_streaming_with_frame_scratch(self):
        root = Path(__file__).resolve().parents[1]
        pack_path = root / "build/retail-ui-component.hp2"
        if not pack_path.is_file():
            self.skipTest("build retail-ui-component.hp2 from the local Halo CE ISO first")

        hp2 = _hp2_module()
        pack_bytes = pack_path.read_bytes()
        parsed = hp2.parse(pack_bytes)
        ctag = parsed.find("CTAG")
        crng = parsed.find("CRNG")
        # Pin the measured conversion so a changed source image or converter
        # cannot silently turn this bounded startup fixture into a different case.
        self.assertEqual(ctag.raw_size, 1_547_396)
        self.assertEqual(crng.raw_size, 2_900)
        self.assertEqual(ctag.stored_size, 275_491)
        self.assertEqual(crng.stored_size, 1_931)

        exe = self._compile_section_fixture(root)
        result = subprocess.run([
            str(exe), str(pack_path), str(ctag.raw_size), str(crng.raw_size),
        ], check=True, capture_output=True, text=True)
        self.assertIn("streaming_high=1550356/1572864", result.stdout)
        self.assertIn("frame_scratch_high=98304/393216", result.stdout)

    def test_bloodgulch_ctag_capacity_failure_is_bounded_and_leak_free(self):
        root = Path(__file__).resolve().parents[1]
        pack_path = root / "build/retail-maps/bloodgulch-with-bsps.hp2"
        if not pack_path.is_file():
            self.skipTest("build the package with tests/test_pack_retail_ctag_hp2.py first")

        parsed = _hp2_module().parse(pack_path.read_bytes())
        ctag = parsed.find("CTAG")
        bsp = parsed.find("B000")
        self.assertEqual((ctag.raw_size, ctag.stored_size), (4_556_496, 1_901_809))
        self.assertEqual((bsp.raw_size, bsp.stored_size), (1_303_092, 914_977))

        exe = self._compile_section_fixture(root)
        result = subprocess.run([
            str(exe), str(pack_path), str(ctag.raw_size), "0",
        ], check=True, capture_output=True, text=True)
        self.assertIn("expected=bounded-reject", result.stdout)
        self.assertIn("streaming=0/1572864", result.stdout)
        self.assertIn("frame_scratch=98304/393216", result.stdout)
        self.assertIn("B000=bounded-decode", result.stdout)
        self.assertIn("owner_high=1303092/6291456", result.stdout)


if __name__ == "__main__":
    unittest.main()
