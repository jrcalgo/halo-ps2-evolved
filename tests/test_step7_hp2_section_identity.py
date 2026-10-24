import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/reports/m2-step7-step8-core-ledger-binding-audit-2026-10-22.json"


class Step7Hp2SectionIdentityTests(unittest.TestCase):
    def test_cbsp_digest_binds_to_exact_hp2_b000_section(self):
        report = json.loads(AUDIT.read_text())
        row = next(item for item in report["rows"]
                   if item["subcheck"] == "relocation-materialization")
        digest = "0fc221a36e097285e472e6fc4227a6bf07f20b063d285d4b464303c7d7a0715d"
        self.assertNotIn(digest, {item["sha256"] for item in row["unresolved_identities"]})
        matches = [binding for category in row["identity_categories"].values()
                   for binding in category.get("verified_fixture_bindings", [])
                   if binding.get("section") == "B000" and
                   binding.get("package_sha256") ==
                   "ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["section_bytes"], 1_303_092)
        self.assertGreater(matches[0]["section_offset"], 0)
        self.assertIn("CRC were validated", matches[0]["basis"])


if __name__ == "__main__":
    unittest.main()
