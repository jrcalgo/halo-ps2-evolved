"""Focused preservation fixtures for omitted root structure-BSP members.

These tests deliberately prove only the PS2 schema walk's byte behavior. They
do not claim the CE gameplay/render consumers ran on the target.
"""
import json
import hashlib
import struct
import unittest
from pathlib import Path

from tools.ctag_schema_walk import walk_structure_bsp
from tools.hcu_schema_manifest import Elf32, SchemaManifest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
DISPOSITIONS = ROOT / "docs/reports/m2-step7-open-root-bsp-dispositions-2026-10-22.json"
SOURCE_BASE = 0x70000000
ROOT_OFFSET = 32


def omitted_members():
    inventory = json.loads(INVENTORY.read_text())
    names = {
        "structure_bsp.vehicle_floor", "structure_bsp.vehicle_ceiling",
        "structure_bsp.sad_unused[5]", "structure_bsp.lonely_unused",
        "structure_bsp.world_bounds", "structure_bsp.render_unused[3]",
        "structure_bsp.cluster_unused[3]", "structure_bsp.fog_unused[6]",
        "structure_bsp.weather_unused[6]", "structure_bsp.sound_unused[6]",
        "structure_bsp.markers", "structure_bsp.diminishing_misc_unused[2]",
    }
    return {member["path"]: member for member in inventory["members"]
            if member["path"] in names}


def make_image(manifest, members):
    bsp = next(definition for definition in manifest["definitions"].values()
               if definition["name"] == "structure_bsp")
    root_size = bsp["size"]
    marker = members["structure_bsp.markers"]
    marker_payload = b"opaque-marker-payload"
    marker_target = (ROOT_OFFSET + root_size + 3) & ~3
    image = bytearray(marker_target + len(marker_payload))
    struct.pack_into("<I", image, 0, SOURCE_BASE + ROOT_OFFSET)
    image[20:24] = b"psbs"
    root = ROOT_OFFSET
    for index, name in enumerate(sorted(members)):
        member = members[name]
        # A distinct nonzero byte pattern catches accidental clearing or edits.
        image[root + member["offset_within_definition"]:
              root + member["offset_within_definition"] + member["size"]] = bytes(
                  ((0x31 + index * 7 + byte_index) & 0xFF)
                  for byte_index in range(member["size"]))
    # The legacy markers block is intentionally not in the schema. Give it a
    # plausible bounded payload address and an opaque definition value.
    struct.pack_into("<iII", image,
                     root + marker["offset_within_definition"],
                     1, SOURCE_BASE + marker_target, 0xDEADBEEF)
    image[marker_target:] = marker_payload
    return bytes(image), bsp, marker_target


class OpenRootBspDispositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCHEMA_ELF.is_file():
            raise unittest.SkipTest("linked compiler schema ELF is required")
        cls.manifest = SchemaManifest(Elf32(SCHEMA_ELF)).build()
        cls.members = omitted_members()
        if len(cls.members) != 12:
            raise AssertionError("inventory must contain all 12 open root members")
        cls.bsp_definition = next(
            definition for definition in cls.manifest["definitions"].values()
            if definition["name"] == "structure_bsp")

    def test_source_backed_scalar_and_opaque_root_bytes_survive_walk(self):
        image, _definition, _target = make_image(self.manifest, self.members)
        result = walk_structure_bsp(self.manifest, image, SOURCE_BASE)
        root = ROOT_OFFSET
        for path, member in self.members.items():
            if path == "structure_bsp.markers":
                continue
            start = root + member["offset_within_definition"]
            end = start + member["size"]
            self.assertEqual(result.image[start:end], image[start:end], path)

    def test_disposition_source_pins_resolve_to_current_exact_lines(self):
        """Keep source associations reviewable without treating them as runtime proof."""
        report = json.loads(DISPOSITIONS.read_text())
        citations = [report["layout_evidence"]]
        for row in report["rows"]:
            citations.extend(row.get("consumer", []))
        for citation in citations:
            path = ROOT / citation["path"]
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), citation["sha256"],
                             citation["path"])
            lines = data.decode(errors="replace").splitlines()
            first, last = (int(value) for value in citation["lines"].split("-"))
            self.assertGreaterEqual(first, 1, citation["path"])
            self.assertLessEqual(last, len(lines), citation["path"])
            self.assertTrue(any(line.strip() for line in lines[first - 1:last]),
                            citation["path"])

    def test_source_backed_root_consumers_are_member_specific(self):
        """Check the cited CE accesses are the declared root fields, not name matches."""
        report = json.loads(DISPOSITIONS.read_text())
        rows = {row["inventory_path"]: row for row in report["rows"]}
        expected_accesses = {
            "structure_bsp.vehicle_floor": ("submodules/halo-ce-universal/source/units/vehicles.c",
                                            "global_structure_bsp_get()->vehicle_floor"),
            "structure_bsp.vehicle_ceiling": ("submodules/halo-ce-universal/source/units/vehicles.c",
                                              "global_structure_bsp_get()->vehicle_ceiling"),
            "structure_bsp.world_bounds": ("submodules/halo-ce-universal/source/structures/structure_visibility.c",
                                           "&structure->world_bounds"),
        }
        for member, (relative_path, expression) in expected_accesses.items():
            row = rows[member]
            self.assertEqual(row["status"], "disposition_resolved_target_behavior_open")
            cited = [item for item in row["consumer"] if item["path"] == relative_path]
            self.assertEqual(len(cited), 1, member)
            first, last = (int(value) for value in cited[0]["lines"].split("-"))
            source_lines = (ROOT / relative_path).read_text().splitlines()
            self.assertIn(expression, "\n".join(source_lines[first - 1:last]), member)
        # The source association is explicit, but target execution remains open.
        self.assertEqual(report["counts"]["consumer_behavior_target_unverified"], 3)

    def test_unused_root_cases_are_preservation_only_with_bounded_search_evidence(self):
        report = json.loads(DISPOSITIONS.read_text())
        rows = [row for row in report["rows"]
                if row["status"] == "open_preserve_only_semantics_unresolved"]
        self.assertEqual(len(rows), 8)
        for row in rows:
            search = row["source_search"]
            self.assertEqual(search["result"], "no explicit .field or ->field source access found",
                             row["inventory_path"])
            self.assertFalse(search["member_access_hits"], row["inventory_path"])
            self.assertIn("does not prove absence", search["limitation"].lower())
            self.assertEqual(row["fixture_scope"].split(";")[0],
                             "Exact compiler-layout byte interval survives schema walk unchanged",
                             row["inventory_path"])
            for hit in search["identifier_hits"]:
                self.assertEqual(hashlib.sha256((ROOT / hit["path"]).read_bytes()).hexdigest(),
                                 hit["sha256"], row["inventory_path"])

    def assert_member_preserved(self, path):
        image, _definition, _target = make_image(self.manifest, self.members)
        result = walk_structure_bsp(self.manifest, image, SOURCE_BASE)
        member = self.members[path]
        start = ROOT_OFFSET + member["offset_within_definition"]
        end = start + member["size"]
        self.assertLessEqual(end, ROOT_OFFSET + self.bsp_definition["size"], path)
        leaf = path.removeprefix("structure_bsp.").split("[")[0]
        self.assertNotIn(leaf, {field["name"] for field in self.bsp_definition["fields"]}, path)
        self.assertEqual(result.image[start:end], image[start:end], path)

    def assert_unused_member_preserved_and_uninterpreted(self, path):
        """Prove exact bytes survive; do not infer the field's game meaning."""
        image, _definition, _target = make_image(self.manifest, self.members)
        result = walk_structure_bsp(self.manifest, image, SOURCE_BASE)
        member = self.members[path]
        start = ROOT_OFFSET + member["offset_within_definition"]
        end = start + member["size"]
        self.assertEqual(result.image[start:end], image[start:end], path)
        # Apart from the containing root span, no schema span or relocation
        # may interpret these compiler-layout bytes as a typed owner/pointer.
        self.assertFalse(any(start <= relocation < end
                             for relocation in result.relocations), path)
        self.assertFalse(any(owner != "structure-BSP root" and
                             span_start < end and start < span_end
                             for span_start, span_end, owner in result.spans), path)

    def test_vehicle_floor_scalar_survives_schema_walk(self):
        self.assert_member_preserved("structure_bsp.vehicle_floor")

    def test_vehicle_ceiling_scalar_survives_schema_walk(self):
        self.assert_member_preserved("structure_bsp.vehicle_ceiling")

    def test_world_bounds_survive_schema_walk(self):
        self.assert_member_preserved("structure_bsp.world_bounds")

    def test_legacy_markers_bytes_are_preserved_without_relocation_claim(self):
        image, definition, marker_target = make_image(self.manifest, self.members)
        result = walk_structure_bsp(self.manifest, image, SOURCE_BASE)
        start = ROOT_OFFSET + self.members["structure_bsp.markers"]["offset_within_definition"]
        self.assertEqual(result.image[start:start + 12], image[start:start + 12])
        self.assertNotIn(start + 4, result.relocations)
        self.assertFalse(any(span[2] == "block structure_bsp.markers" for span in result.spans))
        self.assertEqual(result.image[marker_target:], image[marker_target:])
        schema = definition["fields"]
        self.assertNotIn("markers", {field["name"] for field in schema})

    def test_sad_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.sad_unused[5]")

    def test_lonely_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.lonely_unused")

    def test_render_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.render_unused[3]")

    def test_cluster_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.cluster_unused[3]")

    def test_fog_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.fog_unused[6]")

    def test_weather_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.weather_unused[6]")

    def test_sound_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.sound_unused[6]")

    def test_diminishing_misc_unused_bytes_are_preserved_without_interpretation(self):
        self.assert_unused_member_preserved_and_uninterpreted(
            "structure_bsp.diminishing_misc_unused[2]")


if __name__ == "__main__":
    unittest.main()
