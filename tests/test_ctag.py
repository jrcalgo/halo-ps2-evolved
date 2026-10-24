"""Host-side CTAG v1 wire-format and relocation safety tests."""
import struct
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zlib

from tools import ctag


def synthetic_image():
    # CE cache_file_tag_header (36 bytes) followed by one tag instance.
    image = bytearray(76)
    struct.pack_into("<9I", image, 0,
                     36, 0x00010000, 0x12345678, 1, 0, 0, 0, 0,
                     ctag.TAG_SIGNATURE)
    # Tag instance name pointer and root pointer target bytes within image.
    struct.pack_into("<I", image, 36 + 16, 68)
    struct.pack_into("<I", image, 36 + 20, 72)
    image[68:70] = b"x\0"
    image[72:76] = b"root"
    return bytes(image)


class CtagWireFormat(unittest.TestCase):
    def test_ctag_signature_matches_decompressed_retail_cache(self):
        root = Path(__file__).resolve().parents[1]
        retail_map = root / "data/retail/weapon-audit-maps/bloodgulch.map"
        if not retail_map.is_file():
            self.skipTest("retail Blood Gulch fixture is not present")
        import sys
        sys.path.insert(0, str(root / "submodules/halo-ps2/tools"))
        from halo2ps2 import mapinfo, tagindex
        header = mapinfo.read_header(retail_map)
        with retail_map.open("rb") as stream:
            stream.seek(header.tag_data_offset + 32)
            raw_signature = stream.read(4)
        self.assertEqual(raw_signature, b"sgat")
        self.assertEqual(struct.unpack("<I", raw_signature)[0], tagindex.TAGS_MAGIC)
        self.assertEqual(tagindex.TAGS_MAGIC, ctag.TAG_SIGNATURE)

    def test_round_trip_and_relocation_materialization(self):
        image = synthetic_image()
        encoded = ctag.encode(image, [0, 20, 28, 52, 56], scenario_tag_index=0x00010000)
        self.assertEqual(encoded, ctag.encode(image, [0, 20, 28, 52, 56], scenario_tag_index=0x00010000))
        decoded = ctag.decode(encoded, max_image_size=4096)
        self.assertEqual(decoded.image, image)
        self.assertEqual(decoded.relocations, (0, 20, 28, 52, 56))
        loaded = decoded.materialize(0x00100000)
        self.assertEqual(struct.unpack_from("<I", loaded, 0)[0], 0x00100024)
        self.assertEqual(struct.unpack_from("<I", loaded, 52)[0], 0x00100044)
        self.assertEqual(struct.unpack_from("<I", loaded, 56)[0], 0x00100048)
        with self.assertRaisesRegex(ctag.CtagError, "wraps"):
            decoded.materialize(0xFFFFFFF0)

    def test_null_relocations_remain_null(self):
        image = bytearray(synthetic_image())
        struct.pack_into("<I", image, 56, 0)
        encoded = ctag.encode(bytes(image), [0, 20, 28, 52, 56], scenario_tag_index=0x00010000)
        self.assertEqual(struct.unpack_from("<I", ctag.decode(
            encoded, max_image_size=4096).materialize(0x1000), 56)[0], 0)

    def test_rejects_corrupt_header_and_checksum(self):
        payload = bytearray(ctag.encode(synthetic_image(), [0, 20, 28, 52, 56], scenario_tag_index=0x00010000))
        payload[0] = ord("X")
        with self.assertRaisesRegex(ctag.CtagError, "magic"):
            ctag.decode(bytes(payload), max_image_size=4096)
        payload = bytearray(ctag.encode(synthetic_image(), [0, 20, 28, 52, 56], scenario_tag_index=0x00010000))
        payload[ctag.HEADER_SIZE + 40] ^= 1
        with self.assertRaisesRegex(ctag.CtagError, "checksum"):
            ctag.decode(bytes(payload), max_image_size=4096)

    def test_rejects_size_and_relocation_errors(self):
        valid = ctag.encode(synthetic_image(), [0, 20, 28, 52, 56], scenario_tag_index=0x00010000)
        with self.assertRaisesRegex(ctag.CtagError, "configured bound"):
            ctag.decode(valid, max_image_size=75)
        for relocations in ([0, 56, 56], [0, 57], [0, 76], [56]):
            with self.subTest(relocations=relocations), self.assertRaises(ctag.CtagError):
                ctag.encode(synthetic_image(), relocations, scenario_tag_index=0x00010000)

    def test_rejects_bad_scenario_and_pointer_target(self):
        with self.assertRaisesRegex(ctag.CtagError, "scenario index"):
            ctag.encode(synthetic_image(), [], scenario_tag_index=0x00020000)
        with self.assertRaisesRegex(ctag.CtagError, "missing from relocations"):
            ctag.encode(synthetic_image(), [0], scenario_tag_index=0x00010000)
        image = bytearray(synthetic_image())
        struct.pack_into("<I", image, 56, 0xFFFFFFFF)
        with self.assertRaisesRegex(ctag.CtagError, "target"):
            ctag.encode(bytes(image), [0, 20, 28, 52, 56], scenario_tag_index=0x00010000)

    def test_rejects_trailing_or_truncated_payload(self):
        payload = ctag.encode(synthetic_image(), [0, 20, 28, 52, 56], scenario_tag_index=0x00010000)
        for malformed in (payload[:-1], payload + b"\0"):
            with self.subTest(size=len(malformed)), self.assertRaisesRegex(ctag.CtagError, "payload length"):
                ctag.decode(malformed, max_image_size=4096)

    def test_hp2_map_pack_round_trip_and_integrity(self):
        image = synthetic_image()
        packed = ctag.pack_hp2("synthetic", image, [0, 20, 28, 52, 56],
                               scenario_tag_index=0x00010000,
                               sections=[("SCEN", b"presentation"), ("BSP0", b"collision")])
        name, loaded = ctag.unpack_hp2(packed, max_image_size=4096)
        self.assertEqual(name, "synthetic")
        self.assertEqual(loaded.image, image)
        hp2 = ctag._hp2_module()
        parsed = hp2.parse(packed)
        self.assertEqual(parsed.read("SCEN"), b"presentation")
        self.assertEqual(parsed.read("BSP0"), b"collision")
        with self.assertRaisesRegex(ctag.CtagError, "CTAG section"):
            ctag.pack_hp2("synthetic", image, [0, 20, 28, 52, 56],
                          scenario_tag_index=0x00010000,
                          sections=[("CTAG", b"duplicate")])
        damaged = bytearray(packed)
        section = parsed.find("CTAG")
        damaged[section.offset + section.stored_size - 1] ^= 1
        with self.assertRaisesRegex(ctag.CtagError, "HP2 section"):
            ctag.unpack_hp2(bytes(damaged), max_image_size=4096)

    def test_pack_is_read_by_production_hp2_c_reader(self):
        root = Path(__file__).resolve().parents[1]
        ps2 = root / "submodules/halo-ps2/engine/src"
        image = synthetic_image()
        scenario = b"scenario presentation"
        bsp = bytes(range(256)) * 9
        packed = ctag.pack_hp2("synthetic", image, [0, 20, 28, 52, 56],
                               scenario_tag_index=0x00010000,
                               sections=[("SCEN", scenario), ("BSP0", bsp)])
        envelope = ctag.encode(image, [0, 20, 28, 52, 56], scenario_tag_index=0x00010000)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "map.hp2").write_bytes(packed)
            (temp_path / "ctag.bin").write_bytes(envelope)
            (temp_path / "scen.bin").write_bytes(scenario)
            (temp_path / "bsp.bin").write_bytes(bsp)
            executable = temp_path / "hp2-ctag-test"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I" + str(ps2), str(root / "tests/hp2_ctag_main.c"),
                str(ps2 / "stream/hp2.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            args = [str(executable), str(temp_path / "map.hp2"),
                    str(temp_path / "ctag.bin"), str(temp_path / "scen.bin"),
                    str(temp_path / "bsp.bin")]
            subprocess.run(args, check=True, capture_output=True, text=True)

            parsed = ctag._hp2_module().parse(packed)
            section = parsed.find("CTAG")
            damaged = bytearray(packed)
            damaged[section.offset + section.stored_size - 1] ^= 1
            (temp_path / "damaged.hp2").write_bytes(damaged)
            args[1] = str(temp_path / "damaged.hp2")
            rejected = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)

    def test_ps2_runtime_decoder_matches_python_relocation(self):
        root = Path(__file__).resolve().parents[1]
        port = root / "submodules/halo-ce-universal/port/ps2"
        image = synthetic_image()
        payload = ctag.encode(image, [0, 20, 28, 52, 56], scenario_tag_index=0x00010000)
        expected = ctag.decode(payload, max_image_size=4096).materialize(0x00100000)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "image.ctag").write_bytes(payload)
            (temp_path / "expected.bin").write_bytes(expected)
            executable = temp_path / "ps2-ctag-test"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I" + str(port / "include"), str(root / "tests/ps2_ctag_main.c"),
                str(port / "src/ps2_ctag.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            args = [str(executable), str(temp_path / "image.ctag"),
                    str(temp_path / "expected.bin")]
            subprocess.run(args, check=True, capture_output=True, text=True)

            # A modified relocation target with a matching envelope checksum
            # must be rejected by the C parser rather than materialized.
            malformed = bytearray(payload)
            struct.pack_into("<I", malformed, ctag.HEADER_SIZE + 56, 0xFFFFFFFF)
            struct.pack_into("<I", malformed, 32,
                             zlib.crc32(malformed[ctag.HEADER_SIZE:
                                                  ctag.HEADER_SIZE + len(image)]) & 0xFFFFFFFF)
            (temp_path / "bad-relocation.ctag").write_bytes(malformed)
            args[1] = str(temp_path / "bad-relocation.ctag")
            rejected = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)

            missing_relocation = bytearray(payload)
            relocation_table = ctag.HEADER_SIZE + len(image)
            struct.pack_into("<I", missing_relocation, relocation_table + 8, 24)
            (temp_path / "missing-relocation.ctag").write_bytes(missing_relocation)
            args[1] = str(temp_path / "missing-relocation.ctag")
            rejected = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)

    def test_ps2_split_parser_and_in_place_rebase_match_retail_longest(self):
        root = Path(__file__).resolve().parents[1]
        retail = root / "build/retail-maps/decompressed/longest.map"
        schema_elf = root / "build/hcu-ps2-closure/all/halo-local.elf"
        compiler = shutil.which("cc")
        if not retail.is_file() or not schema_elf.is_file() or not compiler:
            self.skipTest("decompressed Longest, schema ELF, and host C compiler are required")

        from tools.pack_retail_ctag_hp2 import pack_retail_map
        package_bytes, summary = pack_retail_map(retail, schema_elf,
                                                  include_all_bsps=True)
        package = ctag._hp2_module().parse(package_bytes)
        payload = package.read("CTAG")
        decoded = ctag.decode(payload, max_image_size=summary["image_size"])
        expected = decoded.materialize(0x00100000)
        raw_image = decoded.image

        port = root / "submodules/halo-ce-universal/port/ps2"
        with tempfile.TemporaryDirectory(prefix="hcu-ctag-longest-") as temp:
            temp_path = Path(temp)
            payload_path = temp_path / "longest.ctag"
            expected_path = temp_path / "longest-rebased.bin"
            raw_path = temp_path / "longest-relative.bin"
            payload_path.write_bytes(payload)
            expected_path.write_bytes(expected)
            raw_path.write_bytes(raw_image)
            executable = temp_path / "ps2-ctag-longest-test"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I" + str(port / "include"),
                str(root / "tests/ps2_ctag_main.c"),
                str(port / "src/ps2_ctag.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable), str(payload_path),
                            str(expected_path)], check=True,
                           capture_output=True, text=True)
        self.assertEqual(len(decoded.image), 4_263_624)
        self.assertEqual(len(decoded.relocations), 18_855)

    def test_hp2_visitor_streams_retail_longest_into_ctag_final_spans(self):
        root = Path(__file__).resolve().parents[1]
        retail = root / "build/retail-maps/decompressed/longest.map"
        schema_elf = root / "build/hcu-ps2-closure/all/halo-local.elf"
        compiler = shutil.which("cc")
        if not retail.is_file() or not schema_elf.is_file() or not compiler:
            self.skipTest("decompressed Longest, schema ELF, and host C compiler are required")

        from tools.pack_retail_ctag_hp2 import pack_retail_map
        package_bytes, summary = pack_retail_map(retail, schema_elf,
                                                  include_all_bsps=True)
        package = ctag._hp2_module().parse(package_bytes)
        ctag_payload = package.read("CTAG")
        decoded = ctag.decode(ctag_payload,
                              max_image_size=summary["image_size"])
        expected = decoded.materialize(0x00100000)
        raw_image = decoded.image
        engine = root / "submodules/halo-ps2/engine"
        hcu_port = root / "submodules/halo-ce-universal/port/ps2"

        with tempfile.TemporaryDirectory(prefix="hcu-ctag-visitor-") as temp:
            temp_path = Path(temp)
            package_path = temp_path / "longest.hp2"
            damaged_path = temp_path / "longest-bad-outer-crc.hp2"
            expected_path = temp_path / "longest-rebased.bin"
            raw_path = temp_path / "longest-relative.bin"
            executable = temp_path / "hp2-ctag-stream-test"
            package_path.write_bytes(package_bytes)
            expected_path.write_bytes(expected)
            raw_path.write_bytes(raw_image)
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined",
                "-I" + str(engine / "src"),
                "-I" + str(engine / "tests/hp2_world_shim"),
                "-I" + str(hcu_port / "include"),
                str(root / "tests/hp2_ctag_stream_main.c"),
                str(engine / "src/world/section.c"),
                str(engine / "src/core/mem.c"),
                str(engine / "src/stream/hp2.c"),
                str(engine / "src/stream/file.c"),
                str(hcu_port / "src/ps2_ctag.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([
                str(executable), str(package_path), str(expected_path),
                str(summary["image_size"]),
            ], check=True, capture_output=True, text=True,
                   env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})
            damaged = bytearray(package_bytes)
            hp2 = ctag._hp2_module()
            ctag_index = next(i for i, section in enumerate(package.sections)
                              if section.tag == "CTAG")
            crc_field = hp2.HEADER_SIZE + ctag_index * hp2.ENTRY_SIZE + 20
            damaged[crc_field] ^= 1
            damaged_path.write_bytes(damaged)
            failed = subprocess.run([
                str(executable), str(damaged_path), str(expected_path),
                str(summary["image_size"]), "expect-crc-fail",
                str(raw_path),
            ], check=True, capture_output=True, text=True,
               env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})
            damaged_inner_ctag = bytearray(ctag_payload)
            damaged_inner_ctag[ctag.HEADER_SIZE + 128] ^= 1
            damaged_inner_raw = bytes(damaged_inner_ctag[
                ctag.HEADER_SIZE:ctag.HEADER_SIZE + summary["image_size"]])
            inner_raw_path = temp_path / "longest-inner-corrupt-relative.bin"
            inner_raw_path.write_bytes(damaged_inner_raw)
            sections = [("CTAG", bytes(damaged_inner_ctag))]
            sections.extend((section.tag, package.read(section.tag))
                            for section in package.sections
                            if section.tag != "CTAG")
            inner_bad_package = hp2.build(package.name, sections)
            inner_bad_path = temp_path / "longest-bad-inner-crc.hp2"
            inner_bad_path.write_bytes(inner_bad_package)
            inner_failed = subprocess.run([
                str(executable), str(inner_bad_path), str(expected_path),
                str(summary["image_size"]), "expect-inner-crc-fail",
                str(inner_raw_path),
            ], check=True, capture_output=True, text=True,
               env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})
            partial_failed = subprocess.run([
                str(executable), str(package_path), str(expected_path),
                str(summary["image_size"]), "expect-partial-sink-fail",
                str(raw_path),
            ], check=True, capture_output=True, text=True,
               env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})
        self.assertIn("streamed CTAG commit: image=4263624 relocations=18855",
                      result.stdout)
        self.assertIn("scratch_high=173760", result.stdout)
        self.assertIn("outer-CRC rejected", failed.stdout)
        self.assertIn("inner-CRC rejected", inner_failed.stdout)
        self.assertIn("partial sink failure", partial_failed.stdout)

    def test_ps2_cache_mount_exposes_ctag_to_ce_header_contract(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        port = hcu / "port/ps2"
        payload = ctag.encode(synthetic_image(), [0, 20, 28, 52, 56],
                              scenario_tag_index=0x00010000)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "ui.ctag").write_bytes(payload)
            executable = temp_path / "ps2-cache-mount-test"
            subprocess.run([
                "cc", "-std=c89", "-Wall", "-Wextra", "-Werror", "-no-pie",
                "-I" + str(root / "tests/hcu_ps2_cache_shim"),
                "-I" + str(port / "include"),
                str(root / "tests/ps2_cache_mount_main.c"),
                str(port / "src/ps2_cache.c"), str(port / "src/ps2_ctag.c"),
                str(port / "src/ps2_cbsp.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable), str(temp_path / "ui.ctag")],
                           check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
