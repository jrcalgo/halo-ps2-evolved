"""Composite parent-HP2/arena to HCU-PS2 cache-owner regression."""
import hashlib
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import ctag
from tools import ctag_resources
from tools import cbsp
from tools import hmap
from tools.ctag import _hp2_module


def synthetic_image():
    image = bytearray(76)
    struct.pack_into("<9I", image, 0, 36, 0x00010000, 0x12345678,
                     1, 0, 0, 0, 0, ctag.TAG_SIGNATURE)
    struct.pack_into("<I", image, 52, 68)
    struct.pack_into("<I", image, 56, 72)
    image[68:70] = b"x\0"
    image[72:76] = b"root"
    return bytes(image)


class CtagMountTests(unittest.TestCase):
    def test_parent_hp2_arena_mount_retains_then_releases_cache_payload(self):
        root = Path(__file__).resolve().parents[1]
        engine = root / "submodules/halo-ps2/engine/src"
        hcu = root / "submodules/halo-ce-universal/port/ps2"
        resource_index = ctag_resources.encode(
            0x8000, 0x4000, 0x1000, [(0x1000, 0x1000)])
        bsp_image = bytearray(24)
        bsp_image[4] = 0x11
        bsp_image[20:24] = b"psbs"
        bsp_payload = cbsp.encode(bytes(bsp_image), (), (),
                                  source_file_offset=0x2000,
                                  source_file_size=len(bsp_image))
        bsp_image_two = bytearray(bsp_image)
        bsp_image_two[0] = 0x42
        bsp_payload_two = cbsp.encode(bytes(bsp_image_two), (), (),
                                      source_file_offset=0x3000,
                                      source_file_size=len(bsp_image_two))
        catalog = cbsp.encode_catalog((
            cbsp.CatalogEntry(0x2000, len(bsp_image), "B000"),
            cbsp.CatalogEntry(0x3000, len(bsp_image_two), "B001"),
        ), file_length=0x8000)
        source_bytes = bytes((i * 19 + 5) & 0xFF for i in range(0x8000))
        identity = hmap.encode("ui", 0x8000, 0x4000, 0x1000,
                               hashlib.sha256(source_bytes).digest())
        packed = ctag.pack_hp2(
            "synthetic", synthetic_image(), [0, 20, 28, 52, 56],
            scenario_tag_index=0x00010000,
            sections=[("CRNG", resource_index), ("HMAP", identity),
                      ("CBIX", catalog),
                      ("B000", bsp_payload), ("B001", bsp_payload_two),
                      ("DATA", bytes(8192))],
        )
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            pack_path = tmp / "map.hp2"
            pack_path.write_bytes(packed)
            source_path = tmp / "ui.map"
            source_path.write_bytes(source_bytes)
            wrong_source_path = tmp / "same-length-wrong-map.map"
            wrong_source = bytearray(source_bytes)
            wrong_source[4096] ^= 1
            wrong_source_path.write_bytes(wrong_source)
            parsed = _hp2_module().parse(packed)
            section = parsed.find("CTAG")
            damaged = bytearray(packed)
            damaged[section.offset] ^= 1
            damaged_path = tmp / "damaged.hp2"
            damaged_path.write_bytes(damaged)
            bad_header = bytearray(packed)
            bad_header[:4] = b"BAD!"
            bad_header_path = tmp / "bad-header.hp2"
            bad_header_path.write_bytes(bad_header)
            bad_codec = bytearray(packed)
            section_count = struct.unpack_from("<H", bad_codec, 6)[0]
            ctag_entry = next(
                64 + index * 32 for index in range(section_count)
                if bad_codec[64 + index * 32:68 + index * 32] == b"CTAG")
            struct.pack_into("<I", bad_codec, ctag_entry + 16, 0xFFFFFFFF)
            bad_codec_path = tmp / "bad-codec.hp2"
            bad_codec_path.write_bytes(bad_codec)
            ctag_offset = struct.unpack_from("<I", packed, ctag_entry + 4)[0]
            bad_extent = bytearray(packed)
            struct.pack_into("<I", bad_extent, ctag_entry + 4, 0xFFFFF800)
            bad_extent_path = tmp / "bad-extent.hp2"
            bad_extent_path.write_bytes(bad_extent)
            hmap_entry = next(
                64 + index * 32 for index in range(section_count)
                if packed[64 + index * 32:68 + index * 32] == b"HMAP")
            bad_overlap = bytearray(packed)
            struct.pack_into("<I", bad_overlap, hmap_entry + 4, ctag_offset)
            bad_overlap_path = tmp / "overlapping-sections.hp2"
            bad_overlap_path.write_bytes(bad_overlap)
            corrupt_resource_index = bytearray(resource_index)
            corrupt_resource_index[-1] ^= 1
            resource_section_bad_crc = _hp2_module().build(
                "synthetic", [("CTAG", ctag.encode(
                    synthetic_image(), [0, 20, 28, 52, 56],
                    scenario_tag_index=0x00010000)),
                    ("CRNG", bytes(corrupt_resource_index)),
                    ("HMAP", identity)]
            )
            resource_bad_path = tmp / "resource-bad-crc.hp2"
            resource_bad_path.write_bytes(resource_section_bad_crc)
            bsp_bad = bytearray(bsp_payload)
            bsp_bad[36] ^= 1
            ctag_payload = ctag.encode(
                synthetic_image(), [0, 20, 28, 52, 56],
                scenario_tag_index=0x00010000)
            bsp_bad_pack = _hp2_module().build(
                "synthetic", [("CTAG", ctag_payload), ("CRNG", resource_index),
                              ("HMAP", identity),
                              ("CBIX", catalog), ("B000", bsp_payload),
                              ("B001", bytes(bsp_bad))]
            )
            bsp_bad_path = tmp / "bsp-bad-checksum.hp2"
            bsp_bad_path.write_bytes(bsp_bad_pack)
            exe = tmp / "ctag-mount-test"
            subprocess.run([
                "cc", "-std=gnu11", "-D_EE", "-DHALO_FILE_USE_FILEXIO",
                "-Wall", "-Wextra", "-Werror", "-Wno-int-to-pointer-cast",
                "-no-pie",
                "-I" + str(root / "tests/hcu_ctag_mount_shim"),
                "-I" + str(root / "tests/hcu_ps2_cache_shim"),
                "-I" + str(engine), "-Isrc",
                "-I" + str(hcu / "include"),
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
                str(engine / "world/section.c"), str(engine / "stream/hp2.c"),
                str(engine / "stream/file.c"),
                str(engine / "core/mem.c"),
                str(hcu / "src/ps2_cache.c"), str(hcu / "src/ps2_ctag.c"),
                str(hcu / "src/ps2_cbsp.c"),
                "-o", str(exe),
            ], check=True, capture_output=True, text=True)
            run = subprocess.run([str(exe), str(pack_path), str(damaged_path),
                                  str(resource_bad_path), str(source_path),
                                  str(bsp_bad_path), str(wrong_source_path),
                                  str(bad_header_path), str(bad_codec_path),
                                  str(bad_extent_path), str(bad_overlap_path)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
