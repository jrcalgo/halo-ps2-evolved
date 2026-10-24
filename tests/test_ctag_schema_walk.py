"""Schema-driven pointer inventory and normalization tests."""
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.ctag_schema_walk import SchemaWalkError, Walker, compact_pointer_image, read_xbox_tag_region
from tools.ctag_schema_walk import tag_group_coverage, walk_structure_bsp, walk_tag_image
from tools.cbsp import decode as decode_cbsp, encode as encode_cbsp
from tools.convert_retail_bsp import make_tag_name_mapper
from tools.audit_ctag_retail_maps import audit_map
from tools.convert_retail_ctag import convert_retail_map
from tools.hcu_schema_manifest import Elf32, SchemaManifest


def manifest():
    return {
        "format": "hcu-schema-manifest-v1",
        "groups": [{"group": "test", "definition": 100}],
        "definitions": {
            "100": {"name": "root", "size": 84, "fields": [
                {"kind": "block", "name": "items", "size": 12, "count": 1,
                 "offset": 0, "maximum": 4, "definition": 101},
                {"kind": "struct", "name": "nested", "size": 16, "count": 1,
                 "offset": 12, "definition": 102},
                {"kind": "data", "name": "bytes", "size": 20, "count": 1,
                 "offset": 28, "maximum": 8},
                {"kind": "reference", "name": "ref", "size": 16, "count": 1,
                 "offset": 48},
                {"kind": "file_data", "name": "external", "size": 20, "count": 1,
                 "offset": 64, "maximum": 256},
            ]},
            "101": {"name": "item", "size": 8, "fields": [
                {"kind": "tag_index", "name": "index", "size": 4, "count": 1,
                 "offset": 0},
            ]},
            "102": {"name": "nested", "size": 16, "fields": [
                {"kind": "reference", "name": "nested_ref", "size": 16, "count": 1,
                 "offset": 0},
            ]},
        },
    }


def image(source_base=0):
    data = bytearray(256)
    pointer = lambda offset: offset + source_base if offset else 0
    struct.pack_into("<9I", data, 0, pointer(36), 0x00010000, 0x12345678,
                     1, 0, 0, 0, 0, 0x74616773)
    struct.pack_into("<IIII", data, 36, 0x74657374, 0, 0, 0x00010000)
    struct.pack_into("<I", data, 52, pointer(80))
    struct.pack_into("<I", data, 56, pointer(100))
    data[80:83] = b"tag\0"
    data[88:96] = b"nested\0\0"
    data[96:100] = b"ref\0"
    struct.pack_into("<iII", data, 100, 1, pointer(200), 0xDEADBEEF)
    struct.pack_into("<I", data, 116, pointer(96))
    struct.pack_into("<iIIII", data, 128, 4, 0, 0, pointer(220), 0xDEADBEEF)
    struct.pack_into("<I", data, 152, pointer(96))
    struct.pack_into("<iIIII", data, 164, 0, 0, 0, 0, 0xDEADBEEF)
    struct.pack_into("<I", data, 204, 0x12345678)
    data[220:224] = b"data"
    return bytes(data)


def bsp_manifest():
    return {
        "format": "hcu-schema-manifest-v1",
        "groups": [{"group": "sbsp", "definition": 200}],
        "definitions": {
            "200": {"name": "structure_bsp", "size": 32, "fields": [
                {"kind": "reference", "name": "lightmap_group", "size": 16,
                 "count": 1, "offset": 0},
                {"kind": "block", "name": "nodes", "size": 12,
                 "count": 1, "offset": 16, "maximum": 8, "definition": 201},
            ]},
            "201": {"name": "node", "size": 4, "fields": []},
        },
    }


def bsp_data_manifest():
    return {
        "format": "hcu-schema-manifest-v1",
        "groups": [{"group": "sbsp", "definition": 210}],
        "definitions": {
            "210": {"name": "structure_bsp", "size": 20, "fields": [
                {"kind": "data", "name": "collision_data", "size": 20,
                 "count": 1, "offset": 0, "maximum": 16},
            ]},
        },
    }


def bsp_data_image(source_base=0x70000000, data_target=68):
    data = bytearray(96)
    struct.pack_into("<I", data, 0, source_base + 24)
    data[20:24] = b"psbs"
    struct.pack_into("<iIIII", data, 24, 4, 0, 0,
                     source_base + data_target, 0)
    data[68:72] = b"DATA"
    return bytes(data)


def bsp_image(source_base=0x70000000, tag_name=0x803A6080, block_target=64):
    data = bytearray(96)
    struct.pack_into("<I", data, 0, source_base + 24)
    data[20:24] = b"psbs"
    struct.pack_into("<I", data, 28, tag_name)
    struct.pack_into("<I", data, 36, 0xFFFFFFFF)
    struct.pack_into("<iII", data, 40, 1, source_base + block_target, 0xDEADBEEF)
    if 0 <= block_target <= len(data) - 4:
        struct.pack_into("<I", data, block_target, 0x12345678)
    return bytes(data)


class CtagSchemaWalkTest(unittest.TestCase):
    def test_bsp_preservation_journal_explains_every_changed_word(self):
        source = bsp_image()
        result = walk_structure_bsp(
            bsp_manifest(), source, 0x70000000,
            tag_reference_mapper=lambda address: address - 0x803A6000)
        replay = bytearray(source)
        for offset, previous, value, reason in result.normalizations:
            self.assertEqual(struct.unpack_from("<I", replay, offset)[0], previous)
            struct.pack_into("<I", replay, offset, value)
        self.assertEqual(bytes(replay), result.image)
        self.assertEqual({reason for _, _, _, reason in result.normalizations},
                         {"internal-pointer", "external-name", "runtime-definition"})
        self.assertEqual(result.image[64:68], source[64:68])
        self.assertEqual(result.image[68:], source[68:])

    def test_bsp_preservation_rejects_unrecorded_scalar_and_opaque_writes(self):
        for changed_offset in (64, 90):
            class CorruptingWalker(Walker):
                def walk_definition(self, definition_address, base, depth=0):
                    super().walk_definition(definition_address, base, depth)
                    if base == 24:
                        self.image[changed_offset] ^= 1
            with self.subTest(offset=changed_offset):
                walker = CorruptingWalker(
                    bsp_manifest(), bsp_image(), 0x70000000,
                    external_reference_mapper=lambda address: address - 0x803A6000)
                with self.assertRaisesRegex(SchemaWalkError, "outside schema"):
                    walker.run_structure_bsp()

    def test_bsp_preservation_rejects_forged_pointer_and_nonzero_reset(self):
        for reason in ("internal-pointer", "runtime-definition"):
            walker = Walker(bsp_manifest(), bsp_image(), 0x70000000)
            walker.write_u32(64, 123, reason)
            with self.subTest(reason=reason), self.assertRaises(SchemaWalkError):
                walker.verify_bsp_preservation()

    def test_walks_bsp_internal_and_cross_tag_name_pointers_separately(self):
        result = walk_structure_bsp(
            bsp_manifest(), bsp_image(), 0x70000000,
            tag_reference_mapper=lambda address: address - 0x803A6000)
        self.assertEqual(result.relocations, (0, 44))
        self.assertEqual(result.tag_relocations, ((28, 128),))
        self.assertEqual(struct.unpack_from("<I", result.image, 0)[0], 24)
        self.assertEqual(struct.unpack_from("<I", result.image, 28)[0], 128)
        self.assertEqual(struct.unpack_from("<I", result.image, 44)[0], 64)
        self.assertEqual(struct.unpack_from("<I", result.image, 48)[0], 0)
        self.assertEqual(result.visited_bytes, 36)

    def test_schema_walked_bsp_round_trips_through_cbsp_runtime_envelope(self):
        walked = walk_structure_bsp(
            bsp_manifest(), bsp_image(), 0x70000000,
            tag_reference_mapper=lambda address: address - 0x803A6000)
        payload = encode_cbsp(walked.image, walked.relocations, walked.tag_relocations)
        decoded = decode_cbsp(payload, max_image_size=96)
        names = bytearray(256)
        names[128:132] = b"tag\0"
        materialized = decoded.materialize(0x100000, 0x200000, bytes(names))
        self.assertEqual(struct.unpack_from("<I", materialized, 0)[0], 0x100018)
        self.assertEqual(struct.unpack_from("<I", materialized, 28)[0], 0x200080)
        self.assertEqual(struct.unpack_from("<I", materialized, 44)[0], 0x100040)

    def test_bsp_tag_name_mapper_rebases_only_audited_removed_range(self):
        names = bytearray(256)
        names[128:134] = b"tag\0xx"
        mapper = make_tag_name_mapper(bytes(names), 0x803A6000, ((0, 64),))
        self.assertEqual(mapper(0x803A6080), 64)
        with self.assertRaisesRegex(ValueError, "removed render data"):
            mapper(0x803A6010)
        with self.assertRaisesRegex(ValueError, "leaves retail tag image"):
            mapper(0x803A7000)

    def test_bsp_walk_rejects_unmapped_external_names_and_bad_internal_ranges(self):
        with self.assertRaisesRegex(SchemaWalkError, "leaves tag image"):
            walk_structure_bsp(bsp_manifest(), bsp_image(), 0x70000000)
        with self.assertRaisesRegex(SchemaWalkError, "leaves tag image"):
            walk_structure_bsp(
                bsp_manifest(), bsp_image(block_target=0x200), 0x70000000,
                tag_reference_mapper=lambda address: address - 0x803A6000)

    def test_bsp_walk_rejects_overlapping_schema_extents(self):
        with self.assertRaisesRegex(SchemaWalkError, "overlaps"):
            walk_structure_bsp(
                bsp_manifest(), bsp_image(block_target=24), 0x70000000,
                tag_reference_mapper=lambda address: address - 0x803A6000)

    def test_bsp_walk_requires_aligned_root_block_and_data_targets(self):
        unaligned_root = bytearray(bsp_image())
        struct.pack_into("<I", unaligned_root, 0, 0x70000019)
        with self.assertRaisesRegex(SchemaWalkError, "root target is not 4-byte aligned"):
            walk_structure_bsp(
                bsp_manifest(), bytes(unaligned_root), 0x70000000,
                tag_reference_mapper=lambda address: address - 0x803A6000)
        with self.assertRaisesRegex(SchemaWalkError, "tag_block target .* not 4-byte aligned"):
            walk_structure_bsp(
                bsp_manifest(), bsp_image(block_target=65), 0x70000000,
                tag_reference_mapper=lambda address: address - 0x803A6000)
        valid = walk_structure_bsp(bsp_data_manifest(), bsp_data_image(), 0x70000000)
        self.assertIn((68, 72, "data structure_bsp.collision_data"), valid.spans)
        with self.assertRaisesRegex(SchemaWalkError, "tag_data target .* not 4-byte aligned"):
            walk_structure_bsp(bsp_data_manifest(),
                              bsp_data_image(data_target=69), 0x70000000)

    def test_bsp_walk_accepts_empty_block_and_null_cross_tag_reference(self):
        source = bytearray(bsp_image())
        # The zero-count block must be canonicalized even if its source image
        # contains a stale pointer; a null reference name stays a typed null.
        struct.pack_into("<iI", source, 40, 0, 0x70000040)
        struct.pack_into("<I", source, 28, 0)
        result = walk_structure_bsp(
            bsp_manifest(), bytes(source), 0x70000000,
            tag_reference_mapper=lambda address: address - 0x803A6000)
        self.assertEqual(struct.unpack_from("<I", result.image, 28)[0], 0)
        self.assertEqual(struct.unpack_from("<I", result.image, 44)[0], 0)
        self.assertIn(28, result.relocations)
        self.assertNotIn(44, result.relocations)

    def test_bsp_walk_rejects_one_past_and_overflow_targets_atomically(self):
        for target, message in ((96, "leaves tag image"),
                                (0xFFFFFFFF, "leaves tag image")):
            with self.subTest(target=target):
                source = bytearray(bsp_image(block_target=64))
                struct.pack_into("<I", source, 44, target)
                original = bytes(source)
                with self.assertRaisesRegex(SchemaWalkError, message):
                    walk_structure_bsp(
                        bsp_manifest(), source, 0x70000000,
                        tag_reference_mapper=lambda address: address - 0x803A6000)
                # The walker owns a private working image; failure must not
                # leak partially normalized offsets back into caller storage.
                self.assertEqual(bytes(source), original)

    def test_bsp_walk_rejects_data_extent_past_end_without_mutating_input(self):
        source = bytearray(bsp_data_image(data_target=92))
        struct.pack_into("<i", source, 24, 8)
        original = bytes(source)
        with self.assertRaisesRegex(SchemaWalkError, "leaves 0x60-byte image"):
            walk_structure_bsp(bsp_data_manifest(), source, 0x70000000)
        self.assertEqual(bytes(source), original)

    def test_compacts_removed_ranges_and_rebases_all_schema_pointers(self):
        source = image()
        walked = walk_tag_image(manifest(), source)
        compacted, relocations = compact_pointer_image(
            walked.image, walked.relocations, ((180, 200),))
        self.assertEqual(len(compacted), len(source) - 20)
        self.assertEqual(relocations, walked.relocations)
        self.assertEqual(struct.unpack_from("<I", compacted, 104)[0], 180)
        self.assertEqual(struct.unpack_from("<I", compacted, 140)[0], 200)

    def test_compaction_fails_if_a_pointer_or_relocation_field_is_removed(self):
        walked = walk_tag_image(manifest(), image())
        with self.assertRaisesRegex(SchemaWalkError, "target intersects"):
            compact_pointer_image(walked.image, walked.relocations, ((200, 204),))
        with self.assertRaisesRegex(SchemaWalkError, "field or target intersects"):
            compact_pointer_image(walked.image, walked.relocations, ((104, 108),))

    def test_walks_nested_schema_pointers_and_normalizes_xbox_addresses(self):
        result = walk_tag_image(manifest(), image(0x803A6000), 0x803A6000)
        self.assertEqual(result.scenario_tag_index, 0x00010000)
        self.assertEqual(result.relocations,
                         (0, 20, 28, 52, 56, 104, 116, 140, 152))
        for field_offset, target in ((0, 36), (52, 80), (56, 100),
                                     (104, 200), (116, 96), (140, 220), (152, 96)):
            self.assertEqual(struct.unpack_from("<I", result.image, field_offset)[0], target)
        self.assertEqual(struct.unpack_from("<I", result.image, 108)[0], 0)
        self.assertEqual(struct.unpack_from("<I", result.image, 144)[0], 0)
        self.assertEqual(struct.unpack_from("<I", result.image, 180)[0], 0)

    def test_rejects_file_data_without_resource_policy(self):
        source = bytearray(image())
        struct.pack_into("<i", source, 164, 4)
        with self.assertRaisesRegex(SchemaWalkError, "needs a resource policy"):
            walk_tag_image(manifest(), bytes(source))

    def test_explicit_diagnostic_strip_clears_file_data_extent(self):
        source = bytearray(image())
        struct.pack_into("<iIIII", source, 164, 4, 0, 0x1234, 0, 0xDEADBEEF)
        result = walk_tag_image(manifest(), bytes(source), file_data_policy="strip")
        self.assertEqual(result.stripped_file_data_bytes, 4)
        self.assertEqual(struct.unpack_from("<i", result.image, 164)[0], 0)
        self.assertEqual(struct.unpack_from("<i", result.image, 172)[0], 0)
        self.assertEqual(struct.unpack_from("<I", result.image, 176)[0], 0)

    def test_diagnostic_inventory_preserves_file_data_coordinates(self):
        source = bytearray(image())
        struct.pack_into("<iIIII", source, 164, 4, 0x1234, 0x5678, 0, 0xDEADBEEF)
        result = walk_tag_image(manifest(), bytes(source), file_data_policy="inventory")
        self.assertEqual(result.file_data_records, (("root", "external", 4, 0x1234, 0x5678),))
        self.assertEqual(result.stripped_file_data_bytes, 0)
        self.assertEqual(struct.unpack_from("<i", result.image, 164)[0], 4)
        self.assertEqual(struct.unpack_from("<i", result.image, 172)[0], 0x5678)
        self.assertEqual(struct.unpack_from("<I", result.image, 176)[0], 0)

    def test_rejects_overlapping_nested_storage(self):
        source = bytearray(image())
        struct.pack_into("<I", source, 140, 204)
        with self.assertRaisesRegex(SchemaWalkError, "overlaps"):
            walk_tag_image(manifest(), bytes(source))

    def test_rejects_unknown_top_level_group(self):
        source = bytearray(image())
        struct.pack_into("<I", source, 36, 0x756E6B6E)
        with self.assertRaisesRegex(SchemaWalkError, "no linked CE schema"):
            walk_tag_image(manifest(), bytes(source))

    def test_explicit_opaque_group_is_preserved_but_not_walked(self):
        source = bytearray(image())
        struct.pack_into("<I", source, 36, 0x6D657472)
        schemas = manifest()
        schemas["groups"].append({"group": "metr", "definition": None})
        with self.assertRaisesRegex(SchemaWalkError, "no linked CE schema.*metr"):
            walk_tag_image(schemas, bytes(source))
        result = walk_tag_image(schemas, bytes(source), opaque_groups=("metr",))
        self.assertEqual(result.opaque_groups, ((0, "metr", 100),))
        self.assertEqual(result.unsupported_groups, ())
        self.assertIn(56, result.relocations)
        self.assertEqual(struct.unpack_from("<I", result.image, 56)[0], 100)
        with self.assertRaisesRegex(SchemaWalkError, "declared by CE with a null schema"):
            walk_tag_image(schemas, bytes(source), opaque_groups=("test",))

    def test_retail_bloodgulch_exposes_remaining_converter_gaps(self):
        root = Path(__file__).resolve().parents[1]
        retail = root / "data/retail/weapon-audit-maps/bloodgulch.map"
        elf = root / "build/hcu-ps2-closure/all/halo-local.elf"
        if not retail.is_file() or not elf.is_file():
            self.skipTest("retail map and linked HCU schema ELF are required")
        schemas = SchemaManifest(Elf32(elf)).build()
        source, source_base, metadata = read_xbox_tag_region(retail)
        self.assertEqual(metadata["tag_count"], 1806)
        audit = audit_map(retail, schemas)
        self.assertEqual(len(audit["source_sha256"]), 64)
        self.assertGreater(audit["schema_visited_bytes_lower_bound"], 0)
        self.assertEqual(
            audit["schema_visited_bytes_lower_bound"] +
            audit["tag_region_bytes_not_counted_by_schema_walk"],
            metadata["tag_data_size"],
        )
        self.assertEqual(
            sum(audit["schema_bytes_by_owner"].values()),
            audit["schema_visited_bytes_lower_bound"],
        )
        self.assertEqual(
            sum(audit["in_image_data_record_count_by_owner"].values()),
            audit["in_image_data_record_count"],
        )
        self.assertLessEqual(
            sum(audit["in_image_data_bytes_by_owner"].values()),
            audit["schema_visited_bytes_lower_bound"],
        )
        self.assertGreater(audit["in_image_data_record_count"], 0)
        self.assertEqual(audit["bitmap_image_count"], 516)
        self.assertEqual(audit["bitmap_source_extents"]["map"], {
            "count": 516, "payload_bytes_sum": 23_119_360,
            "minimum_offset": 1_298_432, "maximum_end": 24_488_192,
            "invalid_range_count": 0,
        })
        self.assertEqual(audit["reference_count"], 9463)
        self.assertEqual(audit["unresolved_reference_count"], 0)
        self.assertEqual(audit["map_file_resources"], {
            "range_count": 1432,
            "payload_bytes_sum": 35_348_740,
            "union_bytes": 35_348_740,
            "span_bytes": 35_644_736,
            "gap_bytes": 295_996,
            "merged_interval_count": 1200,
            "overlapping_range_count": 0,
            "minimum_offset": 1_298_432,
            "maximum_end": 36_943_168,
            "original_tag_data_offset": 36_943_360,
            "original_tag_data_end": 44_328_544,
            "tag_data_overlap_interval_count": 0,
            "tag_data_overlap_bytes": 0,
        })
        resource_index = audit["resource_interval_index"]
        self.assertEqual(set(resource_index), {"map"})
        self.assertEqual(resource_index["map"]["interval_count"], 1200)
        self.assertEqual(resource_index["map"]["union_bytes"], 35_348_740)
        self.assertEqual(resource_index["map"]["intervals"][0], [1_298_432, 1_648_000])
        self.assertEqual(resource_index["map"]["intervals"][-1], [36_940_288, 36_943_168])
        for start, end in resource_index["map"]["intervals"]:
            self.assertLessEqual(end, audit["map_file_resources"]["original_tag_data_offset"])
        from halo2ps2.tagindex import TagIndex
        coverage = tag_group_coverage(schemas, TagIndex.read(retail).entries)
        metr = coverage["groups"]["metr"]
        self.assertEqual(metr["count"], 2)
        self.assertFalse(metr["has_schema"])
        self.assertEqual(metr["declared_reference_fields"], 0)
        self.assertEqual([row["path"] for row in metr["examples"]], [
            "ui\\hud\\cyborg shield", "ui\\hud\\cyborg body",
        ])
        with self.assertRaisesRegex(SchemaWalkError, "sound_permutation.samples.*resource policy"):
            walk_tag_image(schemas, source, source_base)
        with self.assertRaisesRegex(SchemaWalkError, "tag 1691.*metr"):
            walk_tag_image(schemas, source, source_base, file_data_policy="strip")
        inventory = walk_tag_image(schemas, source, source_base,
                                   file_data_policy="inventory", unknown_group_policy="inventory")
        self.assertEqual(len(inventory.file_data_records), 916)
        self.assertEqual(sum(record[2] for record in inventory.file_data_records), 12_229_380)
        self.assertEqual({record[3] for record in inventory.file_data_records}, {0})
        self.assertEqual(inventory.unsupported_groups, (
            (1691, "metr", 7_294_088), (1692, "metr", 7_303_900),
        ))
        self.assertNotIn("metr", dict(inventory.reference_target_counts))
        self.assertEqual(inventory.stripped_file_data_bytes, 0)
        opaque = walk_tag_image(schemas, source, source_base,
                                file_data_policy="inventory", opaque_groups=("metr",))
        self.assertEqual(opaque.opaque_groups, (
            (1691, "metr", 7_294_088), (1692, "metr", 7_303_900),
        ))
        self.assertEqual(opaque.unsupported_groups, ())
        self.assertNotIn("metr", dict(opaque.reference_target_counts))

    def test_retail_bloodgulch_ctag_conversion_is_deterministic_and_c_loadable(self):
        root = Path(__file__).resolve().parents[1]
        retail = root / "data/retail/weapon-audit-maps/bloodgulch.map"
        elf = root / "build/hcu-ps2-closure/all/halo-local.elf"
        if not retail.is_file() or not elf.is_file():
            self.skipTest("retail Blood Gulch fixture and linked schema ELF are required")
        first, summary = convert_retail_map(retail, elf)
        second, repeated_summary = convert_retail_map(retail, elf)
        self.assertEqual(first, second)
        self.assertEqual(summary, repeated_summary)
        self.assertEqual(summary["image_size"], 4_477_116)
        self.assertEqual(summary["relocation_count"], 19_832)
        self.assertEqual(summary["removed_model_vertex_index_bytes"], 2_908_068)
        self.assertEqual(summary["opaque_metr_count"], 2)
        self.assertEqual(summary["file_data_record_count"], 916)
        self.assertEqual(summary["bitmap_image_count"], 516)
        self.assertEqual(summary["resource_tag_overlap_count"], 0)

        from tools import ctag
        decoded = ctag.decode(first, max_image_size=summary["image_size"])
        expected = decoded.materialize(0x00100000)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "retail.ctag").write_bytes(first)
            (temp_path / "expected.bin").write_bytes(expected)
            executable = temp_path / "retail-ctag-test"
            port = root / "submodules/halo-ce-universal/port/ps2"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I" + str(port / "include"), str(root / "tests/ps2_ctag_main.c"),
                str(port / "src/ps2_ctag.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([
                str(executable), str(temp_path / "retail.ctag"),
                str(temp_path / "expected.bin"),
            ], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
