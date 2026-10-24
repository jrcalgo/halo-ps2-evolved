import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_BINDING = ROOT / "docs/reports/m2-step8-local-players-4-identity-bindings-2026-10-22.json"
AVAILABILITY = ROOT / "docs/reports/m2-step8-historical-workload-pin-availability-2026-10-22.json"
CORE_AUDIT = ROOT / "docs/reports/m2-step7-step8-core-ledger-binding-audit-2026-10-22.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HistoricalWorkloadPinAvailabilityTests(unittest.TestCase):
    def test_local_player_manifest_binds_exact_build_reports_and_absence_report(self):
        binding = json.loads(LOCAL_BINDING.read_text())
        available = json.loads(AVAILABILITY.read_text())
        linked = binding["historical_pin_availability_report"]
        self.assertEqual(linked["path"], str(AVAILABILITY.relative_to(ROOT)))
        self.assertEqual(linked["sha256"], digest(AVAILABILITY))
        self.assertEqual(set(linked["pins_checked"]), set(available["pins"]))

        expected_reports = {
            "build/hcu-parent-link-probe/result-step8-mp-workload-4p-tagcache-4477120.json":
                "af1a132a0b9e1e16af3bae84df626fbb7a191e1bc75a18413963d2a8fda5e738",
            "build/hcu-parent-link-probe/result-step8-mp-workload-2p-tagcache-4477120.json":
                "f23210799016b3e4643bf2b22ae9bfe78a1abbc537814713b176822aeb44e8f5",
        }
        actual = {item["path"]: item["sha256"] for item in binding["verified_bindings"]}
        for path, expected in expected_reports.items():
            self.assertEqual(actual[path], expected)
            self.assertEqual(digest(ROOT / path), expected)

    def test_core_auditor_records_verified_absence_without_claiming_recovery(self):
        audit = json.loads(CORE_AUDIT.read_text())
        self.assertEqual(audit["historical_workload_availability_report"],
                         str(AVAILABILITY.relative_to(ROOT)))
        self.assertEqual(audit["historical_workload_availability_report_sha256"], digest(AVAILABILITY))
        rows = {row["core_row_index"]: row for row in audit["rows"]}
        for index in (15, 16, 17):
            row = rows[index]
            self.assertEqual(row["unresolved_identities"], [])
            self.assertTrue(row["documented_artifact_absences"])
            for absence in row["documented_artifact_absences"]:
                self.assertTrue(absence["absence_record_valid"])
                self.assertEqual(absence["source_report"], str(AVAILABILITY.relative_to(ROOT)))
                self.assertEqual(absence["source_report_sha256"], digest(AVAILABILITY))

        unavailable_hashes = {
            absence["expected_sha256"]
            for index in (15, 16, 17)
            for absence in rows[index]["documented_artifact_absences"]
        }
        self.assertTrue(unavailable_hashes)
        self.assertTrue(all(available["availability"] == "not_found"
                            for value in unavailable_hashes
                            for available in [json.loads(AVAILABILITY.read_text())["pins"][value]]))

    def test_all_map_and_target_probe_pins_are_scanned_and_remain_unavailable(self):
        available = json.loads(AVAILABILITY.read_text())
        expected = {
            "beee81293b9059ca2f51c04e6b49897e607e332750fe7f14fa201c2077258bf0":
                "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf",
            "613b3e3bf0f1cf5a45679050df9cb37839973379a5b0b644937af43c809e4c7c":
                "build/hcu-parent-link-probe/result-step8-mp-capacity-tagcache-4477120.json",
            "6544719db660b6be9b277f983a5a270ff9eb83ccf66c2e77d38a164ee6383a85":
                "build/hcu-ps2-closure/emulator-m1-interpreter-c98db8627d234473a8dc263c3288852d/data/PCSX2/inis/PCSX2.ini",
            "29091d26012bf2b9470f2abcdd10b7cca2e8d7ae6e2c6fc2f4134348c52540a2":
                "build/hcu-ps2-closure/emulator-m1-recompiler-5b536c94e7b44a4ca19636cc2cfecacd/data/PCSX2/inis/PCSX2.ini",
        }
        roots = set(available["worktree_search_roots"])
        for pin, expected_path in expected.items():
            record = available["pins"][pin]
            self.assertEqual(record["availability"], "not_found")
            self.assertEqual(record["exact_worktree_matches"], [])
            self.assertEqual(record["exact_git_blob_matches"], [])
            self.assertEqual(record["expected_path"], expected_path)
            self.assertTrue(any(Path(expected_path) == Path(root) or
                                Path(root) in Path(expected_path).parents
                                for root in roots))
            self.assertTrue(all(item["contains_pin"] and item["sha256"]
                                for item in record["report_evidence"]))

        audit = json.loads(CORE_AUDIT.read_text())
        rows = {row["core_row_index"]: row for row in audit["rows"]}
        allmap_pins = list(expected)[:2]
        target_settings = list(expected)[2:]
        for index, pins in {5: allmap_pins, 12: allmap_pins, 24: target_settings}.items():
            absences = {item["expected_sha256"]: item
                        for item in rows[index]["documented_artifact_absences"]}
            for pin in pins:
                self.assertIn(pin, absences)
                self.assertTrue(absences[pin]["absence_record_valid"])
            self.assertTrue(rows[index]["unresolved_identities"])


if __name__ == "__main__":
    unittest.main()
