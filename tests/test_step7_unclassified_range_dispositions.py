import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/reports/m2-step7-unclassified-range-dispositions-2026-10-22.json"


class UnclassifiedRangeDispositionTests(unittest.TestCase):
    def test_compiler_ownership_classification_is_complete_and_nonsemantic(self):
        report = json.loads(REPORT.read_text())
        self.assertEqual(report["summary"], {
            "compiler_exact_member_ownership": 8,
            "compiler_named_member_ownership": 44,
            "compiler_owned_layout_ranges": 54,
            "complete_compiler_byte_coverage_ranges": 54,
            "incomplete_compiler_byte_coverage_ranges": 0,
            "open_schema_gaps": 54,
            "partial_compiler_member_overlap": 2,
            "ranges_with_boundary_crossing_members": 2,
            "ranges": 54,
            "retained_byte_dispositions": 54,
            "semantic_dispositions_open": 54,
            "source_layout_unresolved": 0,
        })
        inventory = ROOT / report["inventory_path"]
        layout = ROOT / report["layout_report_path"]
        exact_layout = ROOT / report["exact_layout_report_path"]
        self.assertEqual(hashlib.sha256(inventory.read_bytes()).hexdigest(), report["inventory_sha256"])
        self.assertEqual(hashlib.sha256(layout.read_bytes()).hexdigest(), report["layout_report_sha256"])
        self.assertEqual(hashlib.sha256(exact_layout.read_bytes()).hexdigest(), report["exact_layout_report_sha256"])
        self.assertEqual({row["disposition"] for row in report["ranges"]}, {"open_schema_gap"})
        self.assertTrue(all("consumer" not in row["classification"] for row in report["ranges"]))
        self.assertEqual({r["classification"] for r in report["ranges"]}, {
            "compiler_named_member_ownership", "compiler_exact_member_ownership", "partial_compiler_member_overlap"})
        self.assertEqual(report["summary"]["retained_byte_dispositions"], 54)
        retention = ROOT / "tests/test_step7_unmapped_bsp_range_retention.py"
        retention_sha = hashlib.sha256(retention.read_bytes()).hexdigest()
        self.assertEqual(report["summary"]["semantic_dispositions_open"], 54)
        for row in report["ranges"]:
            self.assertEqual(row["byte_disposition"],
                             "retained_bytes_verified_semantics_open")
            self.assertEqual(row["retained_byte_evidence"]["path"],
                             "tests/test_step7_unmapped_bsp_range_retention.py")
            self.assertEqual(row["retained_byte_evidence"]["sha256"], retention_sha)
            self.assertIn("not runtime member semantics",
                          row["retained_byte_evidence"]["scope"])
        self.assertEqual(sum(bool(r["candidate_members"]) for r in report["ranges"]), 54)
        self.assertTrue(all(r["compiler_byte_interval_coverage"]["status"] == "complete" for r in report["ranges"]))
        self.assertTrue(all(not r["compiler_byte_interval_coverage"]["uncovered_intervals"] for r in report["ranges"]))

    def test_eight_exact_rows_bind_inventory_member_extents_and_keep_disposition_open(self):
        report = json.loads(REPORT.read_text())
        exact = [r for r in report["ranges"] if r["classification"] == "compiler_exact_member_ownership"]
        self.assertEqual(len(exact), 8)
        inventory = json.loads((ROOT / report["inventory_path"]).read_text())
        inventory_by_path = {r["path"]: r for r in inventory["members"]}
        for row in exact:
            source = inventory_by_path[row["inventory_path"]]
            self.assertEqual(row["schema_range"], {"offset": source["offset_within_definition"], "size": source["size"]})
            self.assertTrue(row["candidate_members"])
            for member in row["candidate_members"]:
                self.assertGreater(member["size"], 0)
                self.assertGreaterEqual(member["offset"], row["schema_range"]["offset"])
                self.assertLessEqual(member["offset"] + member["size"],
                                     row["schema_range"]["offset"] + row["schema_range"]["size"])
            self.assertEqual(row["disposition"], "open_schema_gap")

    def test_partial_overlaps_remain_distinct(self):
        report = json.loads(REPORT.read_text())
        partial = [r for r in report["ranges"] if r["classification"] == "partial_compiler_member_overlap"]
        self.assertEqual(len(partial), 2)
        self.assertTrue(all(any(m["relation"] == "partially-overlaps-range" for m in r["candidate_members"])
                            for r in partial))
        self.assertTrue(all(r["compiler_byte_interval_coverage"]["status"] == "complete" for r in partial))
        self.assertTrue(all(r["compiler_byte_interval_coverage"]["boundary_crossing_members"] for r in partial))


if __name__ == "__main__":
    unittest.main()
