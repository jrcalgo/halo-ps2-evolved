import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "identity_freshness", ROOT / "tools/audit_step7_step8_identity_freshness.py")
freshness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freshness)


class IdentityFreshnessTests(unittest.TestCase):
    def test_changed_package_marks_dependent_row_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "build/map.hp2"
            report = root / "docs/independent.json"
            package.parent.mkdir(parents=True)
            report.parent.mkdir(parents=True)
            package.write_bytes(b"original package")
            report.write_bytes(b"independent evidence")
            package_hash = freshness.sha(package)
            report_hash = freshness.sha(report)
            ledger = {
                "generated_packages": [{"path": "build/map.hp2", "sha256": package_hash}],
                "evidence": [
                    {"step": 7, "subcheck": "uses-package", "result": "qualified",
                     "fixture_input_hashes": {"input_hashes": [
                         {"path": "build/map.hp2", "sha256": package_hash}]}},
                    {"step": 8, "subcheck": "independent", "result": "partial",
                     "evidence_files": [{"path": "docs/independent.json",
                                         "sha256": report_hash}]},
                ],
            }
            package.write_bytes(b"mutated package")
            result = freshness.audit_freshness(ledger, root)

        self.assertEqual(result["summary"]["rows_marked_stale"], 1)
        self.assertEqual(result["rows"][0]["effective_result"], "stale")
        self.assertEqual(result["rows"][1]["effective_result"], "partial")
        self.assertEqual(result["summary"]["independent_rows_preserved"], 1)

    def test_changed_report_bytes_mark_report_consumer_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "docs/run.json"
            report.parent.mkdir(parents=True)
            report.write_bytes(b"run report")
            expected = freshness.sha(report)
            ledger = {"evidence": [{"step": 7, "subcheck": "report-consumer",
                                    "result": "partial",
                                    "evidence_files": [{"path": "docs/run.json",
                                                        "sha256": expected}]}]}
            report.write_bytes(b"changed run report")
            result = freshness.audit_freshness(ledger, root)
        self.assertEqual(result["rows"][0]["effective_result"], "stale")


if __name__ == "__main__":
    unittest.main()
