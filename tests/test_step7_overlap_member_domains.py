"""C0 overlap member source/domain assessment remains conservative."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/reports/m2-step7-overlap-member-domain-audit-2026-10-22.json"
GENERATOR = ROOT / "tools/audit_step7_overlap_member_domains.py"


class Step7OverlapMemberDomainsTest(unittest.TestCase):
    def test_generated_audit_is_pinned_and_does_not_overstate_closure(self):
        run = subprocess.run([sys.executable, str(GENERATOR), "--check"], cwd=ROOT,
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        data = json.loads(REPORT.read_text())
        summary = data["summary"]
        self.assertEqual(summary["overlap_range_count"], 46)
        self.assertEqual(summary["semantic_dispositions_closed"], 0)
        self.assertEqual(summary["member_specific_host_fixtures"], 1)
        self.assertEqual(len(data["rows"]), 46)
        for row in data["rows"]:
            self.assertTrue(row["members"])
            for member in row["members"]:
                self.assertIn(member["source_access_classification"], {
                    "anonymous_member_no_source_name",
                    "exact_member_spelling_found_type_association_unverified",
                    "no_exact_member_spelling_found_family_type_association_only",
                })
                self.assertEqual(member["semantic_disposition"], "open")
                self.assertIn("status", member["domain_assessment"])
        self.assertTrue(any(m["member"] == "resource_index"
                            and m["fixture_disposition"] == "existing_direct_member_fixture"
                            for r in data["rows"] for m in r["members"]))


if __name__ == "__main__":
    unittest.main()
