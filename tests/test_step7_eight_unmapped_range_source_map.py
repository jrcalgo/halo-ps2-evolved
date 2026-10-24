"""Verify exact source bindings for the eight named BSP schema gaps."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_step7_eight_unmapped_ranges as audit  # noqa: E402


class EightUnmappedRangeSourceMapTest(unittest.TestCase):
    def test_pinned_report_matches_current_inventory_and_sources(self) -> None:
        report_path = ROOT / "docs/reports/m2-step7-eight-unmapped-range-source-map-2026-10-22.json"
        subprocess.run([sys.executable, str(ROOT / "tools/audit_step7_eight_unmapped_ranges.py")],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads(report_path.read_text())
        self.assertEqual(report, audit.build())
        self.assertEqual(report["summary"], {
            "ranges": 8, "member_ranges_mapped": 8, "semantic_dispositions_closed": 0,
        })
        self.assertEqual(len(report["ranges"]), 8)
        for row in report["ranges"]:
            source = ROOT / row["source_path"]
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), row["source_sha256"])
            cursor = 0
            for member in row["members"]:
                self.assertEqual(member["offset"], cursor, row["definition"])
                self.assertGreater(member["size"], 0)
                cursor += member["size"]
            self.assertEqual(cursor, row["inventory_range"]["size"], row["definition"])
            self.assertEqual(row["schema_disposition"],
                             "open; byte retention and consumer semantics remain independently required")

    def test_each_range_binds_to_real_declaration_and_consumer_source(self):
        report_path = ROOT / "docs/reports/m2-step7-eight-unmapped-range-source-map-2026-10-22.json"
        report = json.loads(report_path.read_text())
        declarations = {
            "detail_object_cell": (
                "struct detail_object_cell_definition", "short cell_x;", "short cell_y;",
                "short cell_z;", "short offset_z;", "unsigned long valid_layers;",
                "long start_index;", "long count_index;", "long unused14[3];"),
            "detail_object_count": ("detail_object_count_schema", "TAG_SCHEMA_DEFINITION(detail_object_count, word, empty_fields)"),
            "detail_object_z_reference_vector": ("detail_object_z_reference_vector_schema", "TAG_SCHEMA_DEFINITION(detail_object_z_reference_vector, real_vector4d, empty_fields)"),
            "structure_mirror": ("struct structure_mirror", "real_plane3d plane;", "long unused[5];"),
            "structure_node": ("union byte_rectangle3d", "byte n[6];", "byte x0, x1, y0, y1, z0, z1;"),
            "structure_subcluster": ("struct structure_subcluster", "real_rectangle3d world_bounds;", "struct tag_block surface_indices;"),
            "byte": ("byte_schema", "TAG_SCHEMA_DEFINITION(byte, byte, empty_fields)"),
            "long": ("long_schema", "TAG_SCHEMA_DEFINITION(long, long, empty_fields)"),
        }
        consumer_markers = {
            "detail_object_cell": ("valid_layers", "cell->count_index", "cell->start_index"),
            "detail_object_count": ("detail_object_count_get", "detail_objects.count - first_detail_object_index"),
            "detail_object_z_reference_vector": ("detail_object_z_reference_vector_get", "default_z_reference_vector"),
            "structure_mirror": ("structure_visibility_find_mirror", "&mirror->plane"),
            "structure_node": ("structure_visibility_build_surfaces_traverse_node", "dequantize_byte_to_real_rectangle3d"),
            "structure_subcluster": ("structure_visibility_traverse_subclusters", "&subcluster->world_bounds", "structure->surfaces.count"),
            "byte": ("pathfinding_surfaces", "pathfinding_edges"),
            "long": ("portal_designators", "LONG_MAX", "structure->surfaces.count"),
        }
        for row in report["ranges"]:
            name = row["definition"]
            declaration_text = (ROOT / row["source_path"]).read_text()
            for marker in declarations[name]:
                with self.subTest(range=name, declaration=marker):
                    self.assertIn(marker, declaration_text)
            self.assertIn("consumer_evidence", row)
            self.assertGreaterEqual(len(row["consumer_evidence"]), 1)
            all_consumer_text = []
            for evidence in row["consumer_evidence"]:
                consumer_path = ROOT / evidence["source_path"]
                consumer_bytes = consumer_path.read_bytes()
                self.assertEqual(hashlib.sha256(consumer_bytes).hexdigest(),
                                 evidence["source_sha256"])
                all_consumer_text.append(consumer_bytes.decode("utf-8"))
            joined = "\n".join(all_consumer_text)
            for marker in consumer_markers[name]:
                with self.subTest(range=name, consumer=marker):
                    self.assertIn(marker, joined)
        schema_source = (ROOT / "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c").read_text()
        self.assertIn("TAG_SCHEMA_DEFINITION(structure_node, byte_rectangle3d, empty_fields)", schema_source)


if __name__ == "__main__":
    unittest.main()
