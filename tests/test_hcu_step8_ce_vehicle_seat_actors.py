#!/usr/bin/env python3
"""Pin the stock-MP actor spawn set and CE's unwired vehicle-seat place path."""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_mp_vehicle_seat_actors as audit  # noqa: E402

CE_UNITS = ROOT / "submodules/halo-ce-universal/source/units/units.c"
CE_AI = ROOT / "submodules/halo-ce-universal/source/ai/ai.c"


class VehicleSeatActorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = audit.run()

    def test_census_and_fixture_pass(self):
        self.assertEqual(self.payload["status"], "PASS")
        self.assertEqual(self.payload["issues"], [])
        self.assertEqual(self.payload["offsets"]["step8_unit_seat"], 284)
        self.assertEqual(self.payload["offsets"]["step8_unit_seat_built_in"], 248)
        self.assertEqual(self.payload["offsets"]["step8_unit_seats"], 740)
        self.assertEqual(self.payload["offsets"]["step8_scnr_encounters"], 1068)
        self.assertEqual(self.payload["hashes"]["units_c"], hashlib.sha256(CE_UNITS.read_bytes()).hexdigest())
        self.assertEqual(self.payload["hashes"]["ai_c"], hashlib.sha256(CE_AI.read_bytes()).hexdigest())
        units = CE_UNITS.read_text()
        ai = CE_AI.read_text()
        self.assertIn("if (seat->built_in_actor_reference.index!=NONE)", units)
        self.assertIn("ai_create_mounted_weapons_for_unit(unit_index);", units)
        self.assertIn("if (seat->built_in_actor_reference.index != NONE)", ai)
        self.assertIn("actor_index = actor_place(", ai)
        harness = (audit.OUT / "seat_fixture.c").read_text()
        self.assertIn("static void ai_place_pending_mounted_weapons(", harness)
        self.assertIn("void ai_create_mounted_weapons_for_unit(", harness)
        self.assertIn("fixture_actor_place_calls++", harness)
        report = (audit.OUT / "report.md").read_text()
        self.assertIn("hollow `actv` stubs", report)
        self.assertIn("never enter `actor_place`", report)
        self.assertIn("Do not fill those references synthetically", report)

    def test_map_matrix(self):
        self.assertEqual([row["map"] for row in self.payload["maps"]], list(audit.MP_MAPS))
        for row in self.payload["maps"]:
            with self.subTest(map=row["map"]):
                map_path = audit.SOURCE_DIR / f"{row['map']}.map"
                self.assertEqual(hashlib.sha256(map_path.read_bytes()).hexdigest(), audit.MAP_SHA256[row["map"]])
                self.assertEqual(row["source_sha256"], audit.MAP_SHA256[row["map"]])
                self.assertEqual(row["actr"], 0)
                self.assertEqual(row["encounters"], 0)
                self.assertEqual(row["wired_seats"], 0)
                self.assertEqual(sorted(tag["path"] for tag in row["actv"]), sorted(audit.EXPECTED_ACTV))
                self.assertEqual(sorted(vehicle["path"] for vehicle in row["vehicles"]), sorted(audit.EXPECTED_VEHI))
                for tag in row["actv"]:
                    self.assertEqual(tag["actor"]["index"], -1)
                    self.assertEqual(tag["unit"]["index"], -1)
                    self.assertEqual(tag["ranged"]["index"], -1)
                    self.assertEqual(tag["actor"]["name_ptr"], 0)
                    self.assertEqual(tag["unit"]["name_ptr"], 0)
                for vehicle in row["vehicles"]:
                    self.assertEqual(vehicle["spawned"]["index"], -1)
                    self.assertGreater(len(vehicle["seats"]), 0)
                    for seat in vehicle["seats"]:
                        self.assertEqual(seat["builtin"]["index"], -1)
                for slot in row["palette"]:
                    self.assertEqual(slot["index"], -1)
                self.assertEqual(row["issues"], [])
        self.assertEqual(self.payload["fixture"]["actor_place"], "call-count-probe-not-entered")
        self.assertEqual(self.payload["fixture"]["returncode"], -5)
        self.assertEqual(self.payload["fixture"]["game_state_high_water"], 489384)
        self.assertEqual(self.payload["fixture"]["actor_record_bytes"], 1828)


if __name__ == "__main__":
    unittest.main()
