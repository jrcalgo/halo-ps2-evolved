"""Bounded host combat regression; fixture values are synthetic, not retail data."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Combat(unittest.TestCase):
    def test_combat_transitions_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "combat"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/combat_main.c"),
                 str(ROOT / "src/game/combat.c"), "-lm", "-o", str(exe)],
                check=True, capture_output=True, text=True,
            )
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
        self.assertIn("pistol shield=0 body=85", result.stdout)
        self.assertIn("grenade target_alive=0 pistol_loaded=12", result.stdout)
        self.assertIn("replay_ticks=101 equal=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
