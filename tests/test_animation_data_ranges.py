"""Bounds and source identity for the animation-data extraction audit."""
from pathlib import Path
import re
import unittest

from tools.audit_animation_data_ranges import audit_map
from tools.hcu_schema_manifest import Elf32, SchemaManifest


class AnimationDataRangeAuditTests(unittest.TestCase):
    def test_animation_data_direct_pointer_uses_match_the_audit(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        candidates = [
            path for base in (hcu / "source", hcu / "port")
            for suffix in ("*.c", "*.h")
            for path in base.rglob(suffix)
        ]
        tag_data_accesses = {}
        direct_addresses = {}
        default_pose_macros = {}
        frame_info_cursors = {}
        frame_info_accesses = {}
        tag_data_pattern = re.compile(
            r"tag_data_get_pointer\s*\(\s*&\s*animation\s*->\s*data\b")
        address_pattern = re.compile(r"animation\s*->\s*data\s*\.\s*address\b")
        default_pattern = re.compile(
            r"#define\s+animation_get_default_data\(animation\)\s+"
            r"\(\(animation\)->default_data\.address\)")
        frame_info_address_pattern = re.compile(
            r"animation\s*->\s*frame_info\s*\.\s*address\b")
        frame_info_pointer_pattern = re.compile(
            r"tag_data_get_pointer\s*\(\s*&\s*animation\s*->\s*frame_info\b")
        for path in candidates:
            source = path.read_text(errors="replace")
            data_count = len(tag_data_pattern.findall(source))
            address_count = len(address_pattern.findall(source))
            default_count = len(default_pattern.findall(source))
            frame_cursor_count = len(frame_info_address_pattern.findall(source))
            frame_pointer_count = len(frame_info_pointer_pattern.findall(source))
            relative = path.relative_to(hcu).as_posix()
            if data_count:
                tag_data_accesses[relative] = data_count
            if address_count:
                direct_addresses[relative] = address_count
            if default_count:
                default_pose_macros[relative] = default_count
            if frame_cursor_count:
                frame_info_cursors[relative] = frame_cursor_count
            if frame_pointer_count:
                frame_info_accesses[relative] = frame_pointer_count
        self.assertEqual(tag_data_accesses, {
            "source/models/model_animation_definitions.c": 1,
            "source/models/model_animations.c": 3,
        })
        self.assertEqual(direct_addresses, {
            "port/linux/game/tag_schema_models.c": 1,
        })
        self.assertEqual(default_pose_macros, {
            "source/models/model_animation_definitions.h": 1,
        })
        self.assertEqual(frame_info_cursors, {
            "source/models/model_animations.c": 1,
        })
        self.assertEqual(frame_info_accesses, {
            "source/models/model_animation_definitions.c": 1,
        })

        # This exact reader inventory is also the observer-coverage gate. A
        # newly added CE data pointer above must not silently bypass tracing.
        accessors = (hcu / "source/models/model_animation_definitions.c").read_text()
        animations = (hcu / "source/models/model_animations.c").read_text()
        schema = (hcu / "port/linux/game/tag_schema_models.c").read_text()
        for site in (
            "_ps2_animation_trace_frame_data",
            "_ps2_animation_trace_frame_info",
        ):
            self.assertIn(site, accessors)
        for site in (
            "_ps2_animation_trace_frame_info_bulk",
            "_ps2_animation_trace_default_data",
            "_ps2_animation_trace_compressed_rotation",
            "_ps2_animation_trace_compressed_translation",
            "_ps2_animation_trace_compressed_scale",
        ):
            self.assertIn(site, animations)
        self.assertIn("_ps2_animation_trace_schema_data", schema)

    def test_bloodgulch_animation_data_ranges_are_bounded_and_nonoverlapping(self):
        root = Path(__file__).resolve().parents[1]
        map_path = root / "data/retail/weapon-audit-maps/bloodgulch.map"
        elf_path = root / "build/hcu-ps2-closure/all/halo-local.elf"
        if not map_path.is_file() or not elf_path.is_file():
            self.skipTest("retail Blood Gulch fixture and linked schema ELF are required")
        manifest = SchemaManifest(Elf32(elf_path)).build()
        result = audit_map(map_path, manifest)

        self.assertEqual(result["record_count"], 343)
        self.assertEqual(result["payload_bytes_sum"], 1_440_988)
        self.assertEqual(result["maximum_record_bytes"], 41_000)
        self.assertEqual(result["overlap_bytes"], 0)
        self.assertGreater(result["source_gap_bytes"], 0)
        records = result["records"]
        for record in records:
            self.assertGreaterEqual(record["source_file_offset"], result["tag_data_offset"])
            self.assertLessEqual(
                record["source_file_offset"] + record["size"],
                result["tag_data_offset"] + result["tag_data_size"],
            )
        for previous, current in zip(records, records[1:]):
            self.assertLessEqual(
                previous["source_file_offset"] + previous["size"],
                current["source_file_offset"],
            )


if __name__ == "__main__":
    unittest.main()
