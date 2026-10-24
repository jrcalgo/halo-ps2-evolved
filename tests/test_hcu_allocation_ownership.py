"""Check the combined-image memory ledger is exact and non-overlapping."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hcu_ps2_m0_gate import validate_high_water
RESULT = ROOT / "build/m2-c2-resume-budget-v3/result-partition-sidewinder_marine_shotgun_4p4bot.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HcuAllocationOwnershipTests(unittest.TestCase):
    def test_high_water_evidence_rejects_missing_and_false_claims(self):
        memory_map = json.loads((ROOT / "config/hcu-ps2-memory-map.json").read_text())
        budget = json.loads((ROOT / "config/memory-budget.json").read_text())
        capacities = {entry["name"]: entry["bytes"] for entry in budget["regions"]}
        records = memory_map["high_water_evidence"]
        self.assertEqual(validate_high_water(records, capacities, 2066232), [])
        missing = dict(records)
        missing.pop("audio")
        self.assertTrue(validate_high_water(missing, capacities, 2066232))
        false_peak = dict(records)
        false_peak["audio"] = {"kind": "host-fixture", "bytes": capacities["audio"] + 1,
                               "evidence": "fabricated"}
        self.assertTrue(validate_high_water(false_peak, capacities, 2066232))

    def test_current_machine_map_has_exact_bss_owners(self):
        if not RESULT.is_file():
            self.skipTest("generate the combined HCU parent link probe first")
        result = json.loads(RESULT.read_text())
        machine = result["hcu_gameplay_machine"]
        ledger = machine["memory_ledger"]
        audit_path = ROOT / ledger["report"]
        elf_path = ROOT / machine["elf"]["path"]
        map_path = ROOT / ledger["map"]
        audit = json.loads(audit_path.read_text())
        external_ledger = json.loads(
            (ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text()
        )

        self.assertEqual(sha256(elf_path), machine["elf"]["sha256"])
        self.assertEqual(sha256(elf_path), ledger["elf_sha256"])
        self.assertEqual(sha256(audit_path), ledger["report_sha256"])
        self.assertEqual(sha256(map_path), ledger["map_sha256"])
        self.assertEqual(ledger["memory_map_sha256"],
                         result["source_inputs"]["memory_map_sha256"])
        self.assertEqual(result["source_inputs"]["memory_map_sha256"],
                         sha256(ROOT / "config/hcu-ps2-memory-map.json"))
        self.assertEqual(external_ledger["rooted_sha256"],
                         result["source_inputs"]["hcu_rooted_sha256"])
        self.assertEqual(external_ledger["rooted_sha256"],
                         sha256(ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/rooted.o"))
        # The combined machine link is built from the no-bootstrap closure.
        # The standalone `all/` profile intentionally has different roots and
        # must not be used as a second, conflicting identity check here.
        self.assertTrue(map_path.is_file())
        self.assertEqual(Path(audit["elf"]).resolve(), elf_path.resolve())
        self.assertEqual(Path(audit["map"]).resolve(), map_path.resolve())

        ranges = sorted(audit["bss_input_sections"], key=lambda row: row["start"])
        for previous, current in zip(ranges, ranges[1:]):
            with self.subTest(previous=previous["owner"], current=current["owner"]):
                self.assertLessEqual(previous["end"], current["start"])
        self.assertEqual(sum(row["bytes"] for row in ranges),
                         machine["elf"]["bss_bytes"])
        self.assertEqual(audit["unmapped_symbol_count"], 0)
        self.assertEqual(machine["memory_ledger"]["unassigned_owners"], [])
        candidate = machine["memory_ledger"]["candidate_allocated_bytes_by_region"]
        self.assertEqual(candidate["elf_static"], audit["elf_load_accounting"]["file_backed_load_bytes"])
        self.assertEqual(candidate["resident_gameplay"], audit["elf_load_accounting"]["nobits_load_bytes"])
        self.assertLessEqual(candidate["elf_static"], 2490368)
        gate = subprocess.run(
            [sys.executable, str(ROOT / "tools/hcu_ps2_m0_gate.py")],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        self.assertIn("M0 logical ownership gate closed", gate.stdout)
        gate_report = json.loads(
            (ROOT / "build/hcu-ps2-closure/m0-ownership-gate.json").read_text()
        )
        self.assertEqual(gate_report["rooted_sha256"], external_ledger["rooted_sha256"])
        self.assertEqual(gate_report["gate"], "closed")

    def test_fixed_bootstrap_allocations_are_not_double_counted(self):
        memory_map = json.loads((ROOT / "config/hcu-ps2-memory-map.json").read_text())
        budget = json.loads((ROOT / "config/memory-budget.json").read_text())
        self.assertEqual(memory_map["owner_regions"]["ps2_crt.o"], "resident_gameplay")
        capacities = {entry["name"]: entry["bytes"] for entry in budget["regions"]}
        bss = 2114532
        game_state = 0x305000 + 0x40000
        claims = (2 * 1024 * 1024 + 4 * 1024 * 1024) // 32 * 4
        self.assertEqual(game_state, 3428352)
        self.assertEqual(claims, 786432)
        self.assertLessEqual(bss + game_state + claims,
                             capacities["resident_gameplay"])
        self.assertEqual(capacities["resident_gameplay"] - bss - game_state - claims,
                         486428)
        self.assertEqual(capacities["current_bsp"], 2 * 1024 * 1024 + 4 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
