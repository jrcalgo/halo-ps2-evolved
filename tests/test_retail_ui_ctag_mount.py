"""End-to-end host fixture for mounting the local retail UI CTAG package."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class RetailUICtagMountTests(unittest.TestCase):
    def test_parent_file_owner_and_hcu_cache_mount_actual_ui_package(self):
        root = Path(__file__).resolve().parents[1]
        pack_path = root / "build/retail-ui-hmap.hp2"
        map_path = root / "data/retail/weapon-audit-maps/ui.map"
        if not pack_path.is_file() or not map_path.is_file():
            self.skipTest("build the retail UI HP2 package and provide the decompressed ui.map")

        engine = root / "submodules/halo-ps2/engine/src"
        hcu = root / "submodules/halo-ce-universal/port/ps2"
        exe = root / "build/test-retail-ui-ctag-mount"
        subprocess.run([
            "cc", "-std=gnu11", "-D_EE", "-DHALO_FILE_USE_FILEXIO",
            "-Wall", "-Wextra", "-Werror", "-Wno-int-to-pointer-cast",
            "-no-pie",
            "-I" + str(root / "tests/hcu_ctag_mount_shim"),
            "-I" + str(root / "tests/hcu_ps2_cache_shim"),
            "-I" + str(engine), "-Isrc", "-I" + str(hcu / "include"),
            "-I" + str(root / "submodules/ps2sdk/common/include"),
            "-I" + str(root / "submodules/ps2sdk/ee/include"),
            "-I" + str(root / "submodules/ps2sdk/ee/rpc/filexio/include"),
            str(root / "tests/ctag_mount_main.c"),
            str(root / "src/stream/ctag_mount.c"),
            str(root / "src/stream/ctag_ps2_backend.c"),
            str(root / "src/stream/cbsp_catalog.c"),
            str(root / "src/stream/ctag_resource_index.c"),
            str(root / "src/stream/ctag_map_source.c"),
            str(root / "src/stream/sha256.c"),
            str(root / "src/stream/hmap.c"),
            str(root / "src/stream/hcu_map_service.c"),
            str(engine / "world/section.c"), str(engine / "stream/hp2.c"),
            str(engine / "stream/file.c"), str(engine / "core/mem.c"),
            str(hcu / "src/ps2_cache.c"), str(hcu / "src/ps2_ctag.c"),
            str(hcu / "src/ps2_cbsp.c"), "-o", str(exe),
        ], check=True, capture_output=True, text=True)
        result = subprocess.run([
            str(exe), "--retail-ui", str(pack_path), str(map_path),
        ], check=True, capture_output=True, text=True)
        self.assertIn("retail-ui mounted: CTAG=1510628", result.stdout)
        self.assertIn("streaming=1550356/1572864", result.stdout)
        self.assertIn("scratch_high=275491/393216", result.stdout)
        with tempfile.TemporaryDirectory() as temporary:
            asset_root = Path(temporary)
            maps = asset_root / "maps"
            maps.mkdir()
            (maps / "ui.hp2").symlink_to(pack_path)
            (maps / "ui.map").symlink_to(map_path)
            service_result = subprocess.run([
                str(exe), "--retail-ui-service", str(asset_root) + "/",
            ], check=True, capture_output=True, text=True)
            self.assertIn(
                "retail-ui service: streaming=1550484/1572864 preflight=verified",
                service_result.stdout,
            )
            changed_source = Path(temporary) / "same-length-wrong-map.map"
            shutil.copyfile(map_path, changed_source)
            with changed_source.open("r+b") as file:
                file.seek(4096)
                byte = file.read(1)
                file.seek(4096)
                file.write(bytes([byte[0] ^ 0x80]))
            verified = subprocess.run([
                str(exe), "--verify-ui-source", str(map_path),
            ], capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            rejected = subprocess.run([
                str(exe), "--verify-ui-source", str(changed_source),
            ], capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 5)


if __name__ == "__main__":
    unittest.main()
