"""End-to-end host fixture for mounting the local retail UI CTAG package."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib


class RetailUICtagMountTests(unittest.TestCase):
    def test_parent_file_owner_and_hcu_cache_mount_actual_ui_package(self):
        root = Path(__file__).resolve().parents[1]
        pack_path = root / "build/hcu-parent-link-probe/maps/ui-with-bsp.hp2"
        map_path = root / "build/retail-maps/decompressed/ui.map"
        if not pack_path.is_file() or not map_path.is_file():
            self.skipTest("build the BSP-catalogued retail UI HP2 and decompressed ui.map")

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
            str(root / "src/stream/hcu_asset_profile.c"),
            str(root / "src/stream/hmap.c"),
            str(root / "src/stream/hcu_map_service.c"),
            str(root / "src/stream/hcu_profile_mount.c"),
            str(root / "src/stream/hcu_profile_metadata.c"),
            str(root / "src/stream/hcu_map_catalog.c"),
            str(root / "src/stream/hcu_local_setup.c"),
            str(engine / "world/section.c"), str(engine / "stream/hp2.c"),
            str(engine / "stream/file.c"), str(engine / "core/mem.c"),
            str(hcu / "src/ps2_cache.c"), str(hcu / "src/ps2_ctag.c"),
            str(hcu / "src/ps2_cbsp.c"), "-o", str(exe),
        ], check=True, capture_output=True, text=True)
        result = subprocess.run([
            str(exe), "--retail-ui", str(pack_path), str(map_path),
        ], check=True, capture_output=True, text=True)
        self.assertIn("retail-ui mounted: CTAG=1510628", result.stdout)
        self.assertIn("streaming=1550444/1572864", result.stdout)
        self.assertIn("scratch_high=100608/393216", result.stdout)
        with tempfile.TemporaryDirectory() as temporary:
            asset_root = Path(temporary)
            maps = asset_root / "maps"
            maps.mkdir()
            shutil.copyfile(pack_path, maps / "ui.hp2")
            shutil.copyfile(map_path, maps / "ui.map")
            service_result = subprocess.run([
                str(exe), "--retail-ui-service", str(asset_root) + "/",
            ], check=True, capture_output=True, text=True)
            self.assertIn(
                "retail-ui service: streaming=39832/1572864 preflight=verified",
                service_result.stdout,
            )
            self.assertIn(
                "same-map unload/revalidate/fail-closed/retry and active-owner guard passed",
                service_result.stdout,
            )
            self.assertIn(
                "late cache-mount capacity rejection rolled back and closed source",
                service_result.stdout,
            )
            self.assertIn(
                "authorized resource EOF left completion false; retry passed",
                service_result.stdout,
            )
            late_crc_result = subprocess.run([
                str(exe), "--retail-ui-service-bsp-crc-failure",
                str(asset_root) + "/",
            ], capture_output=True, text=True)
            self.assertEqual(late_crc_result.returncode, 0,
                             late_crc_result.stdout + late_crc_result.stderr)
            self.assertIn(
                "late CBSP section-CRC failure stayed unpublished; exact retry passed",
                late_crc_result.stdout,
            )
            self.assertRegex(
                service_result.stdout,
                r"m2-ui-owner cycle=0 phase=owner-start base=0x[0-9a-fA-F]+ "
                r"cap=1572864 used=39704 high=39832 mount=1 source=1 "
                r"descriptor=\d+ preflight=0 reload=0 staged=-",
            )
            self.assertRegex(
                service_result.stdout,
                r"m2-ui-owner cycle=1 phase=owner-released base=0x[0-9a-fA-F]+ "
                r"cap=1572864 used=0 high=39832 mount=0 source=0 "
                r"descriptor=-1 preflight=0 reload=1 staged=ui",
            )
            self.assertRegex(
                service_result.stdout,
                r"m2-ui-owner cycle=1 phase=owner-reloaded base=0x[0-9a-fA-F]+ "
                r"cap=1572864 used=39704 high=39832 mount=1 source=1 "
                r"descriptor=\d+ preflight=0 reload=0 staged=-",
            )

            # Corrupt the catalog semantically while keeping the HP2 section
            # CRC valid. Preflight must reject it before a cache/BSP owner is
            # published or the source handle is retained.
            rejected_root = Path(temporary) / "bad-catalog-root"
            rejected_maps = rejected_root / "maps"
            rejected_maps.mkdir(parents=True)
            (rejected_maps / "ui.map").symlink_to(map_path)
            bad_pack = bytearray(pack_path.read_bytes())
            section_count = struct.unpack_from("<H", bad_pack, 6)[0]
            cbix_entry = None
            for index in range(section_count):
                entry = 64 + index * 32
                if bad_pack[entry:entry + 4] == b"CBIX":
                    cbix_entry = entry
                    break
            self.assertIsNotNone(cbix_entry, "generated package has a CBIX section")
            cbix_offset = struct.unpack_from("<I", bad_pack, cbix_entry + 4)[0]
            cbix_size = struct.unpack_from("<I", bad_pack, cbix_entry + 12)[0]
            self.assertGreaterEqual(cbix_size, 12)
            # First catalog row's BSP extent is part of the CBIX payload.
            bad_pack[cbix_offset + 8] ^= 0x01
            struct.pack_into("<I", bad_pack, cbix_entry + 20,
                             zlib.crc32(bad_pack[cbix_offset:cbix_offset + cbix_size]))
            (rejected_maps / "ui.hp2").write_bytes(bad_pack)
            reject_result = subprocess.run([
                str(exe), "--retail-ui-service-reject", str(rejected_root) + "/",
            ], check=True, capture_output=True, text=True)
            self.assertIn("corrupt package rejected before publication",
                          reject_result.stdout)

            # Send a table-reserved-field violation through the composed
            # retail service as well as the direct hp2_open_header parser
            # matrix. Rejection must precede mount/cache publication.
            header_root = Path(temporary) / "bad-header-root"
            header_maps = header_root / "maps"
            header_maps.mkdir(parents=True)
            (header_maps / "ui.map").symlink_to(map_path)
            bad_header = bytearray(pack_path.read_bytes())
            header_count = struct.unpack_from("<H", bad_header, 6)[0]
            self.assertGreater(header_count, 0)
            bad_header[64 + 28] = 1
            (header_maps / "ui.hp2").write_bytes(bad_header)
            header_result = subprocess.run([
                str(exe), "--retail-ui-service-reject", str(header_root) + "/",
            ], check=True, capture_output=True, text=True)
            self.assertIn(
                "corrupt package rejected before publication",
                header_result.stdout,
            )

            crc_root = Path(temporary) / "bad-section-crc-root"
            crc_maps = crc_root / "maps"
            crc_maps.mkdir(parents=True)
            (crc_maps / "ui.map").symlink_to(map_path)
            bad_crc = bytearray(pack_path.read_bytes())
            crc_count = struct.unpack_from("<H", bad_crc, 6)[0]
            hmap_entry = next(
                64 + index * 32 for index in range(crc_count)
                if bad_crc[64 + index * 32:68 + index * 32] == b"HMAP"
            )
            hmap_offset = struct.unpack_from("<I", bad_crc, hmap_entry + 4)[0]
            hmap_stored = struct.unpack_from("<I", bad_crc, hmap_entry + 8)[0]
            self.assertGreater(hmap_stored, 0)
            bad_crc[hmap_offset] ^= 0x80
            (crc_maps / "ui.hp2").write_bytes(bad_crc)
            crc_result = subprocess.run([
                str(exe), "--retail-ui-service-reject", str(crc_root) + "/",
            ], check=True, capture_output=True, text=True)
            self.assertIn(
                "corrupt package rejected before publication",
                crc_result.stdout,
            )

            # L0 source-open and L1 missing-container failures must both leave
            # the service retryable and the singleton cache unpublished. The
            # C fixture compares fixed arena identities/capacities, owner and
            # staging flags, source descriptor, and FileXio open/close balance.
            for label, present_name, present_path in (
                    ("missing-map", "ui.hp2", pack_path),
                    ("missing-hp2", "ui.map", map_path)):
                incomplete_root = Path(temporary) / label
                incomplete_maps = incomplete_root / "maps"
                incomplete_maps.mkdir(parents=True)
                (incomplete_maps / present_name).symlink_to(present_path)
                open_failure = subprocess.run([
                    str(exe), "--retail-ui-service-open-failure",
                    str(incomplete_root) + "/",
                ], check=True, capture_output=True, text=True)
                self.assertIn(
                    "missing source/package failed closed without owner publication",
                    open_failure.stdout,
                )
            short_root = Path(temporary) / "short-map"
            short_maps = short_root / "maps"
            short_maps.mkdir(parents=True)
            (short_maps / "ui.hp2").symlink_to(pack_path)
            (short_maps / "ui.map").write_bytes(map_path.read_bytes()[:4096])
            short_source = subprocess.run([
                str(exe), "--retail-ui-service-open-failure",
                str(short_root) + "/",
            ], check=True, capture_output=True, text=True)
            self.assertIn(
                "missing source/package failed closed without owner publication",
                short_source.stdout,
            )

            # Keep the reported map length valid, but make the FileXio shim
            # return one byte and then EOF during the HP2 header/table read.
            # This exercises the production reader's short-I/O loop and the
            # composed service rollback, not merely stat/length validation.
            mid_read_root = Path(temporary) / "mid-read-eof"
            mid_read_maps = mid_read_root / "maps"
            mid_read_maps.mkdir(parents=True)
            (mid_read_maps / "ui.hp2").symlink_to(pack_path)
            shutil.copyfile(map_path, mid_read_maps / "ui.map")
            mid_read = subprocess.run([
                str(exe), "--retail-ui-service-short-read",
                str(mid_read_root) + "/",
            ], capture_output=True, text=True)
            self.assertEqual(mid_read.returncode, 0,
                             mid_read.stdout + mid_read.stderr)
            self.assertIn(
                "HP2 header short-read EOF failed closed after valid open/seek",
                mid_read.stdout,
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
