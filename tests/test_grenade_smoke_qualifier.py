"""Ensure the grenade smoke cannot qualify a freecam/probe-only trace."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qualify_grenade_smoke import parse_grenade_smoke


def fixture(target="actor", freecam=False):
    rows = [
        "[play] grenade throw frag carried 3 slot 0 mode player eye 0.0 0.0 1.0 aim 1.0 0.0 -0.5",
        f"[play] grenade explosion frag slot 0 target {target} damage 120.00 distance 1.00 shield 0.000 body -0.600 dead 1",
    ]
    if freecam:
        rows.append("[play] freecam on")
    return "\n".join(rows)


class GrenadeSmokeQualifier(unittest.TestCase):
    def test_live_biped_blast_qualifies(self):
        result = parse_grenade_smoke(fixture(), True)
        self.assertEqual(result["throws"], 1)
        self.assertEqual(result["target"], "live scenario biped collision/vitality state")

    def test_probe_fallback_freecam_and_missing_input_are_rejected(self):
        invalid = (
            (fixture(target="probe"), True),
            (fixture(freecam=True), True),
            (fixture(), False),
            (fixture().replace("aim 1.0 0.0 -0.5", "aim 1.0 0.0 0.5"), True),
            (fixture().replace(
                "target actor damage 120.00 distance 1.00 shield 0.000 body -0.600 dead 1",
                "target actor outside 2.70"), True),
        )
        for log, released in invalid:
            with self.subTest(log=log, released=released):
                with self.assertRaises(RuntimeError):
                    parse_grenade_smoke(log, released)


if __name__ == "__main__":
    unittest.main()
