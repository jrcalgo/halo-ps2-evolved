"""Check the retail-tag weapon audit when the user's map is available."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"
sys.path.insert(0, str(ROOT / "tools"))
from audit_weapons import audit_map, _read  # noqa: E402


class WeaponAudit(unittest.TestCase):
    def test_out_of_region_read_fails(self):
        with self.assertRaises(ValueError):
            _read(b"abc", 0x1000, 0x1002, 2)

    def test_blood_gulch_families(self):
        if not MAP.is_file():
            self.skipTest("user-owned decompressed Blood Gulch map unavailable")
        by_name = {row["path"].split("\\")[-1]: row for row in audit_map(MAP)["weapons"]}
        self.assertEqual(len(by_name), 15)
        self.assertEqual(by_name["pistol"]["magazines"][0]["rounds_loaded_max"], 12)
        self.assertEqual(by_name["assault rifle"]["magazines"][0]["rounds_loaded_max"], 60)
        self.assertEqual(by_name["shotgun"]["triggers"][0]["projectiles_per_shot"], 15)
        self.assertEqual(len(by_name["plasma pistol"]["triggers"]), 2)
        self.assertEqual(len(by_name["scorpion cannon"]["triggers"]), 2)
        self.assertEqual(by_name["flag"]["triggers"], [])
        self.assertEqual(by_name["needler"]["triggers"][0]["projectile"],
                         "weapons\\needler\\needle")
        report = audit_map(MAP)
        self.assertEqual(len(report["grenade_equipment"]), 2)
        self.assertEqual(len(report["grenade_projectiles"]), 2)


if __name__ == "__main__":
    unittest.main()
