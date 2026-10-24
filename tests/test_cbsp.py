import struct
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zlib

from tools.cbsp import (CbspError, CatalogEntry, HEADER, decode,
                        decode_catalog, encode, encode_catalog)
from tools import ctag


def synthetic_ctag_image():
    image = bytearray(76)
    struct.pack_into("<9I", image, 0,
                     36, 0x00010000, 0x12345678, 1, 0, 0, 0, 0,
                     ctag.TAG_SIGNATURE)
    struct.pack_into("<I", image, 52, 68)
    struct.pack_into("<I", image, 56, 72)
    image[68:70] = b"x\0"
    image[72:76] = b"root"
    return bytes(image)


def fixture():
    image = bytearray(64)
    struct.pack_into("<I", image, 0, 24)  # internal pointer to BSP header body
    struct.pack_into("<I", image, 8, 128)  # typed tag-name offset into CTAG
    image[20:24] = b"psbs"
    return bytes(image)


class CbspEnvelopeTest(unittest.TestCase):
    def test_catalog_round_trip_and_extent_lookup(self):
        entries = (CatalogEntry(2048, 64, "B000"),
                   CatalogEntry(6144, 64, "B001"))
        wire = encode_catalog(entries, file_length=8192)
        self.assertEqual(decode_catalog(wire, expected_file_length=8192), entries)
        with self.assertRaises(CbspError):
            decode_catalog(wire, expected_file_length=8191)
        with self.assertRaises(CbspError):
            encode_catalog((entries[0], CatalogEntry(2100, 64, "B001")),
                           file_length=8192)

    def test_parent_catalog_reader_matches_python_encoder(self):
        root = Path(__file__).resolve().parents[1]
        wire = encode_catalog((CatalogEntry(2048, 64, "B000"),
                               CatalogEntry(6144, 64, "B001")),
                              file_length=8192)
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            (tmp / "catalog.cbix").write_bytes(wire)
            executable = tmp / "catalog-test"
            engine = root / "submodules/halo-ps2/engine/src"
            compile_result = subprocess.run([
                "cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-no-pie",
                "-I" + str(root / "src"), "-I" + str(engine),
                str(root / "tests/cbsp_catalog_main.c"),
                str(root / "src/stream/cbsp_catalog.c"),
                str(engine / "stream/hp2.c"), "-o", str(executable),
            ], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            subprocess.run([str(executable), str(tmp / "catalog.cbix")],
                           check=True, capture_output=True, text=True)

    def test_round_trip_and_two_pointer_domains_materialize(self):
        payload = encode(fixture(), (0,), ((8, 128),))
        decoded = decode(payload, max_image_size=1024)
        self.assertEqual(decoded.image, fixture())
        self.assertEqual(decoded.relocations, (0,))
        self.assertEqual(decoded.tag_relocations, ((8, 128),))
        materialized = decoded.materialize(0x100000, 0x200000, bytes(256))
        self.assertEqual(struct.unpack_from("<I", materialized, 0)[0], 0x100018)
        self.assertEqual(struct.unpack_from("<I", materialized, 8)[0], 0x200080)

    def test_rejects_corruption_bad_domain_and_noncanonical_table(self):
        payload = bytearray(encode(fixture(), (0,), ((8, 128),)))
        payload[HEADER.size + 30] ^= 1
        with self.assertRaisesRegex(CbspError, "checksum"):
            decode(payload, max_image_size=1024)

        payload = bytearray(encode(fixture(), (0,), ((8, 128),)))
        table = HEADER.size + len(fixture())
        payload[table + 4] = 7
        image = payload[HEADER.size:table]
        struct.pack_into("<I", payload, 20, zlib.crc32(image) & 0xFFFFFFFF)
        with self.assertRaisesRegex(CbspError, "domain"):
            decode(payload, max_image_size=1024)

    def test_rejects_bad_pointer_targets_and_materialization_bounds(self):
        image = bytearray(fixture())
        struct.pack_into("<I", image, 0, len(image))
        with self.assertRaisesRegex(CbspError, "target leaves"):
            encode(bytes(image), (0,), ((8, 128),))
        decoded = decode(encode(fixture(), (0,), ((8, 128),)), max_image_size=1024)
        with self.assertRaisesRegex(CbspError, "leaves CTAG"):
            decoded.materialize(0x100000, 0x200000, bytes(128))
        with self.assertRaisesRegex(CbspError, "wraps"):
            decoded.materialize(0xFFFFFFF0, 0x200000, bytes(256))
        with self.assertRaisesRegex(CbspError, "16-byte aligned"):
            decoded.materialize(0x100001, 0x200000, bytes(256))
        with self.assertRaisesRegex(CbspError, "overlap"):
            decoded.materialize(0x200000, 0x200000, bytes(256))
        with self.assertRaisesRegex(CbspError, "NUL-terminated"):
            decoded.materialize(0x100000, 0x200000, b"x" * 256)
        with self.assertRaisesRegex(CbspError, "4-byte aligned"):
            encode(fixture(), (1,), ())

    def test_source_extent_is_bounded_and_round_tripped(self):
        payload = encode(fixture(), (0,), ((8, 128),),
                         source_file_offset=2048, source_file_size=64)
        decoded = decode(payload, max_image_size=4096)
        self.assertEqual((decoded.source_file_offset, decoded.source_file_size), (2048, 64))
        with self.assertRaisesRegex(CbspError, "source BSP file extent"):
            encode(fixture(), (0,), ((8, 128),),
                   source_file_offset=2048, source_file_size=63)

    def test_ps2_c_decoder_matches_python_materialization(self):
        root = Path(__file__).resolve().parents[1]
        port = root / "submodules/halo-ce-universal/port/ps2"
        payload = encode(fixture(), (0,), ((8, 128),),
                         source_file_offset=2048, source_file_size=len(fixture()))
        expected = decode(payload, max_image_size=4096).materialize(
            0x02000000, 0x01400000, bytes(256))
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "source.cbsp").write_bytes(payload)
            (temp_path / "expected.bin").write_bytes(expected)
            executable = temp_path / "ps2-cbsp-test"
            compile_result = subprocess.run([
                "cc", "-std=c89", "-Wall", "-Wextra", "-Werror", "-no-pie",
                "-I" + str(port / "include"),
                str(root / "tests/ps2_cbsp_main.c"),
                str(port / "src/ps2_cbsp.c"), "-o", str(executable),
            ], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            subprocess.run([
                str(executable), str(temp_path / "source.cbsp"),
                str(temp_path / "expected.bin")], check=True, capture_output=True, text=True)

            damaged = bytearray(payload)
            damaged[HEADER.size + 30] ^= 1
            (temp_path / "damaged.cbsp").write_bytes(damaged)
            rejected = subprocess.run([
                str(executable), str(temp_path / "damaged.cbsp"),
                str(temp_path / "expected.bin")], capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)

    def test_real_bloodgulch_cbsp_materializes_identically_in_ps2_c(self):
        """When the local licensed retail fixture exists, compare every relocation.

        CI remains independent of copyrighted map inputs. Developers with the
        generated diagnostic package get a full-size C/Python materialization
        comparison over the schema-walked retail BSP rather than only the tiny
        synthetic image above.
        """
        root = Path(__file__).resolve().parents[1]
        package_path = root / "build/retail-maps/bloodgulch-with-bsps.hp2"
        if not package_path.is_file():
            self.skipTest("local Blood Gulch CBSP package is not available")

        from tools import cbsp as cbsp_module
        from tools import ctag as ctag_module
        hp2_tools = root / "submodules/halo-ps2/tools"
        import sys
        if str(hp2_tools) not in sys.path:
            sys.path.insert(0, str(hp2_tools))
        from halo2ps2 import hp2

        package = hp2.parse(package_path.read_bytes())
        tag_image = ctag_module.decode(package.read("CTAG"),
                                       max_image_size=16 * 1024 * 1024)
        encoded_bsp = package.read("B000")
        decoded_bsp = cbsp_module.decode(encoded_bsp,
                                         max_image_size=len(encoded_bsp))
        # The converter only emits typed names after proving the source address
        # is in the tag region and the NUL terminator is within 256 bytes.
        for _field, target in decoded_bsp.tag_relocations:
            self.assertLess(target, len(tag_image.image))
            self.assertGreaterEqual(
                tag_image.image.find(b"\0", target,
                                     min(len(tag_image.image), target + 256)), 0)

        bsp_base, tag_base = 0x02000000, 0x01000000
        expected = decoded_bsp.materialize(bsp_base, tag_base,
                                           tag_image.image)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "bsp.cbsp").write_bytes(encoded_bsp)
            (temp_path / "expected.bin").write_bytes(expected)
            (temp_path / "tag-image.bin").write_bytes(tag_image.image)
            executable = temp_path / "ps2-cbsp-retail-test"
            port = root / "submodules/halo-ce-universal/port/ps2"
            subprocess.run([
                "cc", "-std=c89", "-Wall", "-Wextra", "-Werror", "-no-pie",
                "-I" + str(port / "include"),
                str(root / "tests/ps2_cbsp_main.c"),
                str(port / "src/ps2_cbsp.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([
                str(executable), str(temp_path / "bsp.cbsp"),
                str(temp_path / "expected.bin"), hex(bsp_base), hex(tag_base),
                str(temp_path / "tag-image.bin"), str(len(decoded_bsp.image)),
            ], check=True, capture_output=True, text=True)

    def test_longest_b000_split_span_rebase_matches_python(self):
        """Run streamed-form CBSP parsing/rebase against the Longest candidate.

        This validates only the split-span parser and unpublished in-place
        rebase. The package is local retail-derived test input, and this is not
        a claim that the CE callback or guest map load is integrated.
        """
        root = Path(__file__).resolve().parents[1]
        package_path = (root / "build/m2-artifacts/"
                        "longest-2fba411b-hcu6933490-all-bsps.hp2")
        if not package_path.is_file():
            self.skipTest("local Longest retail HP2 package is not available")

        package_bytes = package_path.read_bytes()
        self.assertEqual(hashlib.sha256(package_bytes).hexdigest(),
                         "6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b")
        from halo2ps2 import hp2
        parsed = hp2.parse(package_bytes)
        from tools import cbsp as cbsp_module
        from tools import ctag as ctag_module
        tag_image = ctag_module.decode(parsed.read("CTAG"),
                                       max_image_size=8 * 1024 * 1024)
        encoded_bsp = parsed.read("B000")
        decoded_bsp = cbsp_module.decode(encoded_bsp,
                                         max_image_size=1814336)
        self.assertEqual(len(decoded_bsp.image), 374784)
        self.assertEqual(len(decoded_bsp.relocations) +
                         len(decoded_bsp.tag_relocations), 214)
        bsp_base, tag_base = 0x01800000, 0x01000000
        expected = decoded_bsp.materialize(bsp_base, tag_base,
                                           tag_image.image)

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "bsp.cbsp").write_bytes(encoded_bsp)
            (temp_path / "expected.bin").write_bytes(expected)
            (temp_path / "tag-image.bin").write_bytes(tag_image.image)
            executable = temp_path / "ps2-cbsp-longest-test"
            port = root / "submodules/halo-ce-universal/port/ps2"
            subprocess.run([
                "cc", "-std=c89", "-Wall", "-Wextra", "-Werror", "-no-pie",
                "-I" + str(port / "include"),
                str(root / "tests/ps2_cbsp_main.c"),
                str(port / "src/ps2_cbsp.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([
                str(executable), str(temp_path / "bsp.cbsp"),
                str(temp_path / "expected.bin"), hex(bsp_base), hex(tag_base),
                str(temp_path / "tag-image.bin"), str(1814336),
            ], check=True, capture_output=True, text=True)

    def test_longest_b000_uses_production_ctag_mount_visitor_and_ps2_cache(self):
        """Exercise real Longest CTAG/B000 through the parent-to-CE bridge.

        This is a host integration test of the production mount, section
        visitor, cache reader, and CE relocation code. Its 8 MiB package owner
        is deliberately host-only; it does not prove the complete map fits the
        PS2 streaming arena or qualify gameplay-map admission.
        """
        root = Path(__file__).resolve().parents[1]
        package_path = (root / "build/m2-artifacts/"
                        "longest-2fba411b-hcu6933490-all-bsps.hp2")
        map_path = root / "build/retail-maps/decompressed/longest.map"
        if not package_path.is_file() or not map_path.is_file():
            self.skipTest("local Longest retail HP2 package/map are not available")

        package_bytes = package_path.read_bytes()
        self.assertEqual(hashlib.sha256(package_bytes).hexdigest(),
                         "6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b")
        self.assertEqual(hashlib.sha256(map_path.read_bytes()).hexdigest(),
                         "e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9")
        from halo2ps2 import hp2
        parsed = hp2.parse(package_bytes)
        from tools import cbsp as cbsp_module
        from tools import ctag as ctag_module
        tag_image = ctag_module.decode(parsed.read("CTAG"),
                                       max_image_size=8 * 1024 * 1024)
        encoded_bsp = parsed.read("B000")
        decoded_bsp = cbsp_module.decode(encoded_bsp,
                                         max_image_size=1814336)
        self.assertEqual((decoded_bsp.source_file_offset,
                          decoded_bsp.source_file_size), (2048, 374784))
        self.assertEqual(len(decoded_bsp.image), 374784)
        self.assertEqual(len(decoded_bsp.relocations) +
                         len(decoded_bsp.tag_relocations), 214)

        engine = root / "submodules/halo-ps2/engine/src"
        hcu = root / "submodules/halo-ce-universal/port/ps2"
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            executable = temp / "ps2-cache-cbsp-longest"
            compile_result = subprocess.run([
                "cc", "-std=gnu11", "-D_EE", "-Wall", "-Wextra",
                "-Werror", "-Wno-int-to-pointer-cast", "-no-pie",
                "-I" + str(root / "tests/hcu_ctag_mount_shim"),
                "-I" + str(root / "tests/hcu_ps2_cache_shim"),
                "-I" + str(engine), "-Isrc", "-I" + str(hcu / "include"),
                "-I" + str(root / "submodules/ps2sdk/common/include"),
                "-I" + str(root / "submodules/ps2sdk/ee/include"),
                str(root / "tests/ps2_cache_cbsp_longest_main.c"),
                str(root / "src/stream/ctag_mount.c"),
                str(root / "src/stream/ctag_ps2_backend.c"),
                str(root / "src/stream/cbsp_catalog.c"),
                str(root / "src/stream/ctag_resource_index.c"),
                str(root / "src/stream/ctag_map_source.c"),
                str(root / "src/stream/sha256.c"),
                str(root / "src/stream/hmap.c"),
                str(engine / "world/section.c"),
                str(engine / "stream/hp2.c"),
                str(engine / "stream/file.c"),
                str(engine / "core/mem.c"),
                str(hcu / "src/ps2_cache.c"),
                str(hcu / "src/ps2_ctag.c"),
                str(hcu / "src/ps2_cbsp.c"), "-o", str(executable),
            ], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            bases = subprocess.run([str(executable), "--bases"],
                                   check=True, capture_output=True, text=True)
            match = re.search(r"tag_base=0x([0-9a-fA-F]+) bsp_base=0x([0-9a-fA-F]+)",
                              bases.stdout)
            self.assertIsNotNone(match, bases.stdout)
            tag_base, bsp_base = (int(value, 16) for value in match.groups())
            expected = bytearray(decoded_bsp.materialize(
                bsp_base, tag_base, tag_image.image))
            # Production cache normalization clears Xbox vertex/index handles
            # before CE's bounded structure-BSP validator receives the image.
            for offset in (4, 8, 12, 16):
                struct.pack_into("<I", expected, offset, 0)
            (temp / "tag-image.bin").write_bytes(
                tag_image.materialize(tag_base))
            (temp / "expected-bsp.bin").write_bytes(expected)
            result = subprocess.run([
                str(executable), str(package_path), str(map_path),
                str(temp / "tag-image.bin"), str(temp / "expected-bsp.bin"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            self.assertIn("longest B000 direct visitor passed", result.stdout)
            self.assertIn("source=2048/374784 image=374784 rows=214", result.stdout)
            self.assertIn("tag=4263624/4477120 bsp=374784/1814336", result.stdout)
            self.assertRegex(result.stdout,
                             r"scratch=\d+/124224 owner=\d+/8388608")

    def test_ps2_cache_serves_cbsp_only_at_audited_extent(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        port = hcu / "port/ps2"
        tag_payload = ctag.encode(
            synthetic_ctag_image(), [0, 20, 28, 52, 56],
            scenario_tag_index=0x00010000)
        bsp_image = bytearray(fixture())
        struct.pack_into("<I", bsp_image, 8, 68)
        bsp_image[4] = 0x11
        # This adapter fixture has one nonzero Xbox count and deliberately
        # nonzero handles for both arrays. The PS2 adapter must clear both
        # count/pointer pairs while preserving a distinct typed name pointer.
        struct.pack_into("<I", bsp_image, 12, 0)
        struct.pack_into("<I", bsp_image, 16, 0xCAFEBABE)
        struct.pack_into("<I", bsp_image, 28, 68)
        bsp_image[60] = 0x11
        bsp_payload = encode(bytes(bsp_image), (0,), ((28, 68),),
                             source_file_offset=2048, source_file_size=64)
        bsp_image_two = bytearray(bsp_image)
        bsp_image_two[60] = 0x42
        bsp_payload_two = encode(bytes(bsp_image_two), (0,), ((28, 68),),
                                 source_file_offset=6144, source_file_size=64)
        bad_extent = encode(bytes(bsp_image), (0,), ((28, 68),),
                            source_file_offset=9000, source_file_size=64)
        tag_overlap = encode(bytes(bsp_image), (0,), ((28, 68),),
                             source_file_offset=4096, source_file_size=64)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "map.ctag").write_bytes(tag_payload)
            (temp_path / "map.cbsp").write_bytes(bsp_payload)
            (temp_path / "map-second.cbsp").write_bytes(bsp_payload_two)
            (temp_path / "bad-extent.cbsp").write_bytes(bad_extent)
            (temp_path / "tag-overlap.cbsp").write_bytes(tag_overlap)
            executable = temp_path / "ps2-cache-cbsp-test"
            subprocess.run([
                "cc", "-std=c89", "-Wall", "-Wextra", "-Werror", "-no-pie",
                "-I" + str(root / "tests/hcu_ps2_cache_shim"),
                "-I" + str(port / "include"),
                str(root / "tests/ps2_cache_cbsp_main.c"),
                str(port / "src/ps2_cache.c"),
                str(port / "src/ps2_ctag.c"),
                str(port / "src/ps2_cbsp.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([
                str(executable), str(temp_path / "map.ctag"),
                str(temp_path / "map.cbsp"),
                str(temp_path / "bad-extent.cbsp"),
                str(temp_path / "tag-overlap.cbsp"),
                str(temp_path / "map-second.cbsp")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ps2_cache_rematerializes_two_exact_retail_cbix_extents(self):
        """Exercise real two-BSP package payloads through the PS2 cache adapter.

        This is adapter evidence only: it deliberately does not claim to run
        CE's scenario switch or its global publication/verification code.
        """
        root = Path(__file__).resolve().parents[1]
        package_root_text = os.environ.get("HALO_HCU_M2_PACKAGE_ROOT")
        manifest_text = os.environ.get("HALO_HCU_M2_PACKAGE_MANIFEST")
        if not package_root_text or not manifest_text:
            self.skipTest("set package root and audit manifest for retail CBSP transaction inputs")

        from halo2ps2 import hp2
        from tools import hmap as hmap_module
        package_path = Path(package_root_text) / "a30.hp2"
        manifest = json.loads(Path(manifest_text).read_text())
        row = next((item for item in manifest["maps"] if item["map"] == "a30"), None)
        self.assertIsNotNone(row, "package audit must include the two-BSP a30 map")
        package_bytes = package_path.read_bytes()
        self.assertEqual(hashlib.sha256(package_bytes).hexdigest(), row["package_sha256"])
        self.assertEqual(len(package_bytes), row["package_bytes"])

        package = hp2.parse(package_bytes)
        identity = hmap_module.decode(package.read("HMAP"))
        self.assertEqual(identity.map_name, "a30")
        self.assertEqual(identity.source_sha256.hex(), row["source_sha256"])
        ctag_wire = package.read("CTAG")
        tag_image = ctag.decode(ctag_wire, max_image_size=16 * 1024 * 1024)
        entries = decode_catalog(package.read("CBIX"),
                                 expected_file_length=identity.file_length)
        self.assertEqual(tuple(entry.section_tag for entry in entries),
                         tuple(f"B{i:03d}" for i in range(2)))
        payloads = [package.read(entry.section_tag) for entry in entries]
        decoded = [decode(payload, max_image_size=8 * 1024 * 1024)
                   for payload in payloads]
        for entry, cbsp in zip(entries, decoded):
            self.assertEqual((cbsp.source_file_offset, cbsp.source_file_size),
                             (entry.file_offset, entry.file_size))
            self.assertEqual(cbsp.source_file_size, len(cbsp.image))

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            (temp / "a30.ctag").write_bytes(ctag_wire)
            (temp / "bsp-0.cbsp").write_bytes(payloads[0])
            (temp / "bsp-1.cbsp").write_bytes(payloads[1])
            executable = temp / "ps2-cache-retail-cbsp-test"
            port = root / "submodules/halo-ce-universal/port/ps2"
            subprocess.run([
                "cc", "-std=c89", "-Wall", "-Wextra", "-Werror", "-no-pie",
                "-I" + str(root / "tests/hcu_ps2_cache_shim"),
                "-I" + str(port / "include"),
                str(root / "tests/ps2_cache_cbsp_retail_main.c"),
                str(port / "src/ps2_cache.c"),
                str(port / "src/ps2_ctag.c"),
                str(port / "src/ps2_cbsp.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([
                str(executable), str(temp / "a30.ctag"),
                str(temp / "bsp-0.cbsp"), str(temp / "bsp-1.cbsp"),
                str(entries[0].file_offset), str(entries[0].file_size),
                str(entries[1].file_offset), str(entries[1].file_size),
                str(identity.tag_data_offset), str(len(tag_image.image)),
                str(identity.file_length),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ce_structure_bsp_switch_preserves_verify_and_rollback_order(self):
        """Guard the production CE transaction paired with the adapter fixture.

        The executable fixture exercises the PS2 cache adapter and a caller
        contract driver. This source check makes sure the decompiled CE caller
        still unloads-before-load, verifies before publishing globals, and
        retries the old reference after a failed or rejected candidate.
        """
        root = Path(__file__).resolve().parents[1]
        source_path = root / "submodules/halo-ce-universal/source/scenario/scenario.c"
        source = source_path.read_text()
        signature = "boolean scenario_switch_structure_bsp("
        start = source.index(signature)
        opening = source.index("{", start)
        depth = 0
        end = None
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        self.assertIsNotNone(end, "scenario switch body is balanced")
        body = source[opening:end]

        # Invalid and same-index requests must be rejected before the caller
        # disconnects or releases the current BSP.
        guard = body.index("if (structure_bsp_index != global_structure_bsp_index")
        disconnect = body.index("scenario_call_disconnect_from_structure_bsp_procs()")
        first_unload = body.index("scenario_structure_bsp_unload(")
        first_load = body.index("loaded = scenario_structure_bsp_load(reference)")
        self.assertLess(guard, disconnect)
        self.assertLess(disconnect, first_unload)
        self.assertLess(first_unload, first_load)
        self.assertIn("structure_bsp_index < global_scenario->structure_bsp_references.count", body)
        self.assertIn("structure_bsp_index < MAXIMUM_STRUCTURE_BSPS_PER_SCENARIO", body)

        # A loaded candidate is verified before publication; a rejected one
        # is unloaded and enters the same fallback path as a load failure.
        verify_positions = [m.start() for m in re.finditer(
            r"structure_bsp_port_verify\(structure_bsp_definition_get\(", body)]
        self.assertEqual(len(verify_positions), 2)
        rejected_unload = body.index("scenario_structure_bsp_unload(reference)", first_load)
        failure = body.index("if (!loaded)", first_load)
        old_retry = body.index("loaded = scenario_structure_bsp_load(reference)", first_load + 1)
        publish = body.index("global_structure_bsp_index = structure_bsp_index")
        self.assertLess(first_load, verify_positions[0])
        self.assertLess(verify_positions[0], rejected_unload)
        self.assertLess(rejected_unload, failure)
        self.assertLess(failure, old_retry)
        self.assertLess(old_retry, verify_positions[1])
        self.assertLess(verify_positions[1], publish)

        # Failure clears stale pointers; rollback failure takes the safe menu
        # path rather than leaving the old globals pointing into replaced data.
        for cleared in ("global_structure_bsp = NULL", "global_collision_bsp = NULL",
                       "global_bsp3d = NULL"):
            self.assertIn(cleared, body)
        self.assertIn("if (!loaded && had_old_structure_bsp)", body)
        self.assertIn("main_goto_main_menu()", body)
        self.assertIn("scenario_globals->structure_bsp_index = structure_bsp_index", body)


if __name__ == "__main__":
    unittest.main()
