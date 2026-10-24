"""Keep the 46-range consumer audit complete and explicitly non-semantic."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/reports/m2-step7-gap-consumer-evidence-2026-10-22.json"
GENERATOR = ROOT / "tools/audit_step7_gap_consumer_evidence.py"


class Step7GapConsumerEvidenceTest(unittest.TestCase):
    def test_report_reproduces_and_keeps_all_semantics_open(self):
        check = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"], cwd=ROOT,
            text=True, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        report = json.loads(REPORT.read_text())
        summary = report["summary"]
        self.assertEqual(summary["compiled_member_overlap_ranges"], 46)
        self.assertEqual(len(report["rows"]), 46)
        self.assertEqual(summary["semantic_qualifications_closed"], 0)
        self.assertEqual(summary["ranges_with_target_consumer_execution"], 0)
        self.assertTrue(all(row["semantic_qualification"] == "open"
                            for row in report["rows"]))
        self.assertTrue(all(row["limitation"] for row in report["rows"]))
        self.assertTrue(all(row["compiled_member_overlaps"] for row in report["rows"]))
        direct = [claim for row in report["rows"]
                  for claim in row["direct_member_fixture_claims"]]
        self.assertEqual(len(direct), 1)
        self.assertEqual(direct[0]["member"], "resource_index")
        self.assertEqual(direct[0]["test"],
                         "tests/test_hcu_mp_predicted_resource_member.py")
        self.assertTrue(all(member["access_search_limit"]
                            for row in report["rows"]
                            for member in row["compiled_member_overlaps"]))


if __name__ == "__main__":
    unittest.main()
