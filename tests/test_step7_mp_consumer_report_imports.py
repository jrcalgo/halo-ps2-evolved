import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
COVERAGE = ROOT / "docs/reports/m2-step7-step8-ledger-coverage-audit-2026-10-22.json"
GENERATOR = ROOT / "tools/generate_hcu_step7_step8_closure.py"
SPEC = importlib.util.spec_from_file_location("step7_closure_generator", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Step7MpConsumerReportImportTests(unittest.TestCase):
    def test_generated_ledger_and_coverage_audit_preserve_import_counts(self):
        ledger = json.loads(LEDGER.read_text())
        coverage = json.loads(COVERAGE.read_text())
        self.assertEqual(len(ledger["evidence"]), 75)
        self.assertTrue(all(ledger["step_status"][key]["status"] == "open"
                            for key in ("step7", "step8")))
        imported = [row for row in ledger["evidence"] if row["subcheck"].startswith("mp-")]
        self.assertEqual(len(imported), 11)
        self.assertEqual(sum(len(row["fixture_scope"]["imported_reports"]) for row in imported), 15)
        reserve = next(row for row in ledger["evidence"] if row["subcheck"] == "reserve")
        self.assertEqual(reserve["result"], "partial")
        findings = {row["requirement"]: row["finding"] for row in coverage["coverage_findings"]}
        self.assertIn("15 distinct Step 7 MP consumer reports", findings["Import prior evidence at original scope"])

    def test_successful_mp_consumer_slices_are_imported_at_source_scope(self):
        rows = MODULE.step7_mp_consumer_rows()
        self.assertEqual(len(rows), 11)
        self.assertEqual(len({row["subcheck"] for row in rows}), 11)
        for row in rows:
            with self.subTest(row=row["subcheck"]):
                self.assertEqual(row["step"], 7)
                self.assertEqual(row["result"], "partial")
                self.assertEqual(row["evidence_level"], "host execution")
                self.assertTrue(row["remaining_limitation"])
                self.assertTrue(row["fixture_scope"]["imported_reports"])
                self.assertGreaterEqual(len(row["evidence_files"]), 2)
                for item in row["evidence_files"]:
                    path = ROOT / item["path"]
                    self.assertTrue(path.is_file())
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
                for imported in row["fixture_scope"]["imported_reports"]:
                    report = ROOT / imported["report_path"]
                    self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(),
                                     imported["report_sha256"])
                for category in ("fixture_hashes", "input_hashes", "source_hashes", "harness_hashes"):
                    for pin in row["fixture_input_hashes"].get(category, []):
                        local = pin.get("local_path")
                        if local:
                            path = ROOT / local
                            self.assertTrue(path.is_file())
                            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                             pin["local_sha256"])

    def test_imported_reports_and_stock_map_fixtures_are_path_bound(self):
        """The importer must bind each claim to the report and map it actually used."""
        rows = MODULE.step7_mp_consumer_rows()
        ledger = json.loads(LEDGER.read_text())
        ledger_rows = {row["subcheck"]: row for row in ledger["evidence"]}
        report_count = 0
        map_count = 0
        for row in rows:
            by_report = {}
            for imported in row["fixture_scope"]["imported_reports"]:
                report_count += 1
                report_path = ROOT / imported["report_path"]
                self.assertTrue(report_path.is_file())
                digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
                self.assertEqual(imported["report_sha256"], digest)
                excerpt = " ".join(line.strip() for line in report_path.read_text(errors="replace").splitlines()[:20]
                                   if line.strip())[:1200]
                self.assertEqual(imported["scope_excerpt"], excerpt)
                by_report[imported["report_path"]] = imported

            scoped_maps = row["fixture_input_hashes"]["fixture_hashes"]
            self.assertTrue(scoped_maps)
            canonical = ledger_rows[row["subcheck"]]
            self.assertEqual(canonical["fixture_scope"]["imported_reports"],
                             row["fixture_scope"]["imported_reports"])
            self.assertEqual(canonical["fixture_input_hashes"]["fixture_hashes"], scoped_maps)
            for fixture in scoped_maps:
                map_count += 1
                fixture_path = ROOT / fixture["path"]
                self.assertTrue(fixture_path.is_file())
                self.assertEqual(fixture_path.stat().st_size, fixture["bytes"])
                self.assertEqual(hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                                 fixture["sha256"])
                self.assertEqual(fixture["role"], "fixture")
                self.assertIn(fixture["scope_report"], by_report)
                self.assertIn(fixture["map"], by_report[fixture["scope_report"]]["fixture_maps"])

            # The map fixture set for a report is an exact projection of that
            # report's declared fixture scope; lifecycle/query behavior scope
            # remains separately represented in maps_named_in_report.
            for path, imported in by_report.items():
                actual = {item["map"] for item in scoped_maps if item["scope_report"] == path}
                self.assertEqual(actual, set(imported["fixture_maps"]))

        self.assertEqual(report_count, 15)
        self.assertEqual(map_count, 99)


if __name__ == "__main__":
    unittest.main()
