"""The integrated reload evidence parser rejects incomplete or irregular reloads."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qualify_shotgun_reload_smoke import parse_trace


def fixture():
    lines = ["[play] shotgun-state tick 1 loaded 12 total 12 magazine 0 timer 0"]
    for index in range(12):
        tick = 10 + index * 30
        loaded = 11 - index
        lines += [f"[play] fire SHOTGUN {loaded} pellets 15 tick {tick} loaded {loaded}",
                  f"[play] shotgun-state tick {tick} loaded {loaded} total 12 magazine 2 timer 0"]
    lines.append("[play] shotgun-state tick 341 loaded 0 total 12 magazine 1 timer 15")
    for index in range(12):
        tick = 355 + index * 11
        loaded = index + 1
        lines.append(f"[play] shotgun-state tick {tick} loaded {loaded} total {12-loaded} magazine {1 if loaded < 12 else 2} timer {12 if loaded < 12 else 0}")
    lines += ["[play] shotgun-state tick 477 loaded 12 total 0 magazine 3 timer 0",
              "[play] shotgun-state tick 478 loaded 12 total 0 magazine 0 timer 0",
              "[done] frames=901 dropped=0"]
    return "\n".join(lines)


class ShotgunReloadQualifier(unittest.TestCase):
    def test_shells_are_counted_by_ammo_transfer_not_chamber_transitions(self):
        summary, trace = parse_trace(fixture())
        self.assertEqual(summary["shots"], 12)
        self.assertEqual(summary["magazine_after_shots"], list(range(11, -1, -1)))
        self.assertEqual(summary["loaded_after_each_shell"], list(range(1, 13)))
        self.assertEqual(summary["shell_ticks"], list(range(355, 477, 11)))
        self.assertEqual(summary["shell_interval_ticks"], 11)
        self.assertEqual(summary["reserve_after_last_shell"], 0)
        self.assertEqual(trace[0], ("state", -9, 12, 12, 0, 0))

    def test_incomplete_or_nonuniform_reload_is_rejected(self):
        text = fixture()
        invalid = (
            text.replace("[done] frames=901 dropped=0", "[done] frames=901 dropped=2"),
            text.replace("[done] frames=901 dropped=0", "[done] frames=899 dropped=0"),
            text.replace("fire SHOTGUN 0 pellets 15 tick 340 loaded 0",
                         "fire SHOTGUN 1 pellets 15 tick 340 loaded 1"),
            text.replace("tick 399 loaded 5 total 7", "tick 400 loaded 5 total 7"),
            text.replace("tick 399 loaded 5 total 7", "tick 399 loaded 5 total 8"),
        )
        for case in invalid:
            with self.subTest(case=case[-80:]):
                with self.assertRaises(RuntimeError):
                    parse_trace(case)


if __name__ == "__main__":
    unittest.main()
