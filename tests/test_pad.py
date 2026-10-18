"""Dead zone, default look rate, and invert, from the Halo CE control sources."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Pad(unittest.TestCase):
    def test_dead_zone_and_invert(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "pad"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/pad_main.c"),
                 str(ROOT / "src/game/pad.c"),
                 str(ROOT / "src/game/move.c"),
                 str(ROOT / "src/game/pill.c"),
                 str(ROOT / "src/game/collide.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
