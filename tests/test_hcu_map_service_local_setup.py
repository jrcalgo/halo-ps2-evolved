"""C5 local setup gate in hcu_map_service_preflight(): every rejection leaves the
loaded-map state byte-identical, and the printed reason names the setup check.

The production hcu_map_service.c is compiled with the same host shims as the
map-service profile test. The loaded state is seeded by the C driver, not
produced by a real package load."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"
PORT = ROOT / "submodules/halo-ce-universal/port/ps2"


class MapServiceLocalSetupGateTest(unittest.TestCase):
    def test_gate_rejects_before_teardown_and_admits_a_qualified_control(self) -> None:
        compiler = shutil.which("gcc-13") or shutil.which("gcc") or shutil.which("cc")
        if compiler is None:
            self.skipTest("no C compiler available")
        with tempfile.TemporaryDirectory(prefix="hcu-local-setup-gate-") as tmp_name:
            tmp = Path(tmp_name)
            exe = tmp / "hcu-map-service-local-setup"
            asset_root = tmp / "assets"
            asset_root.mkdir()
            cmd = [
                compiler, "-std=gnu11", "-D_EE", "-DHALO_FILE_USE_FILEXIO",
                "-DHCU_M2_MP_HOST_ORACLE",
                "-Wall", "-Wextra", "-Werror", "-Wno-int-to-pointer-cast", "-no-pie",
                "-I" + str(ROOT / "tests/hcu_ctag_mount_shim"),
                "-I" + str(ROOT / "tests/hcu_ps2_cache_shim"),
                "-I" + str(ENGINE), "-I" + str(ROOT / "src"),
                "-I" + str(PORT / "include"),
                "-I" + str(ROOT / "submodules/ps2sdk/common/include"),
                "-I" + str(ROOT / "submodules/ps2sdk/ee/include"),
                "-I" + str(ROOT / "submodules/ps2sdk/ee/rpc/filexio/include"),
                str(ROOT / "tests/hcu_map_service_local_setup_main.c"),
                str(ROOT / "src/stream/ctag_mount.c"),
                str(ROOT / "src/stream/ctag_ps2_backend.c"),
                str(ROOT / "src/stream/cbsp_catalog.c"),
                str(ROOT / "src/stream/ctag_resource_index.c"),
                str(ROOT / "src/stream/ctag_map_source.c"),
                str(ROOT / "src/stream/sha256.c"),
                str(ROOT / "src/stream/hcu_asset_profile.c"),
                str(ROOT / "src/stream/hmap.c"),
                str(ROOT / "src/stream/hcu_map_catalog.c"),
                str(ROOT / "src/stream/hcu_profile_metadata.c"),
                str(ROOT / "src/stream/hcu_local_setup.c"),
                str(ENGINE / "world/section.c"), str(ENGINE / "stream/hp2.c"),
                str(ENGINE / "stream/file.c"),
                str(ENGINE / "core/mem.c"),
                str(PORT / "src/ps2_cache.c"), str(PORT / "src/ps2_ctag.c"),
                str(PORT / "src/ps2_cbsp.c"),
                "-o", str(exe),
            ]
            built = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([str(exe), str(asset_root) + "/"],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        out = run.stdout
        self.assertIn("map-preflight rejected map=beavercreek reason=local-setup-difficulty-not-qualified", out)
        self.assertIn("PASS generated-table setup refused before teardown", out)
        self.assertIn("PASS setup for another map refused", out)
        self.assertIn("PASS empty roster refused", out)
        self.assertIn("PASS qualified control setup admitted by the gate", out)
        self.assertIn("PASS cleared gate restores unchanged preflight", out)
        self.assertIn("hcu-map-service-local-setup passed", out)
        self.assertNotIn("local-setup-map-not", out)


if __name__ == "__main__":
    unittest.main()
