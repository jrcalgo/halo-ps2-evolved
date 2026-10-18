"""Host biped step: walk, jump, crouch, and collision without a renderer."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Move(unittest.TestCase):
    def test_traces(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "move"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/move.c"), str(ROOT / "src/game/move.c"),
                 str(ROOT / "src/game/pill.c"), str(ROOT / "src/game/collide.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
