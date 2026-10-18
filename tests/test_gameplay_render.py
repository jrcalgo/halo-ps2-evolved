"""Rendered Blood Gulch bouts: walk, jump, crouch, and turn, each from the player eye."""
from pathlib import Path
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def rows(text):
    return [tuple(map(float, line.split())) for line in text.splitlines() if line.strip()]


class RenderedMovement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MAP.is_file():
            raise unittest.SkipTest("decompressed Blood Gulch is not in the tree")
        sys.path.insert(0, str(ROOT / "tools"))
        from convert_collision import build_pack
        cls.temp = tempfile.TemporaryDirectory()
        cls.pack = Path(cls.temp.name) / "collision.hp2"
        cls.pack.write_bytes(build_pack(MAP))
        cls.exe = Path(cls.temp.name) / "gameplay_path"
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
             str(ROOT / "tests/gameplay_path.c"),
             str(ROOT / "src/game/collpack.c"), str(ROOT / "src/game/move.c"),
             str(ROOT / "src/game/pill.c"), str(ROOT / "src/game/collide.c"),
             str(ROOT / "src/game/pad.c"), "-lm", "-o", str(cls.exe)],
            check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def path_for(self, mode):
        out = subprocess.run([str(self.exe), str(self.pack), mode], check=True, capture_output=True, text=True)
        got = rows(out.stdout)
        self.assertGreaterEqual(len(got), 4)
        self.assertEqual(got[0][0], 0.0)
        return got, out.stdout

    def render(self, mode, text):
        motion = Path(self.temp.name) / (mode + ".path")
        motion.write_text(text)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools/run_world_viewer.py"),
             "--variant", "portal", "--mode", "recompiler", "--objects",
             "--frames", "80", "--motion", str(motion),
             "--camera", "98.4934", "-157.6390", "2.3235", "76.1049", "0"],
            check=True, cwd=ROOT, capture_output=True, text=True)
        found = re.search(r"evidence: (\S+)", proc.stdout)
        self.assertIsNotNone(found, proc.stdout + proc.stderr)
        run = Path(found.group(1))
        log = (run / "emulog.txt").read_text(errors="replace")
        self.assertIn("scripted path:", log)
        done = re.search(r"\[done\] frames=(\d+) dropped=(\d+)", log)
        self.assertIsNotNone(done)
        self.assertEqual(int(done.group(2)), 0)
        shots = sorted(run.glob("gameplay-*.png")) + [run / "visible-final.png"]
        shots = [shot for shot in shots if shot.is_file()]
        self.assertGreaterEqual(len(shots), 2)
        hashes = {hashlib.sha256(shot.read_bytes()).hexdigest() for shot in shots}
        self.assertGreater(len(hashes), 1, mode)
        return run

    def test_walk_renders(self):
        got, text = self.path_for("walk")
        moved = ((got[-1][1] - got[0][1]) ** 2 + (got[-1][2] - got[0][2]) ** 2) ** 0.5
        self.assertGreater(moved, 1.0)
        self.render("walk", text)

    def test_jump_renders(self):
        got, text = self.path_for("jump")
        peak = max(row[3] for row in got)
        self.assertGreater(peak, got[0][3] + 0.4)
        self.assertLess(got[-1][3], peak - 0.2)
        self.render("jump", text)

    def test_crouch_renders(self):
        got, text = self.path_for("crouch")
        self.assertLess(min(row[3] for row in got), got[0][3] - 0.2)
        self.render("crouch", text)

    def test_turn_renders(self):
        got, text = self.path_for("turn")
        self.assertGreater(abs(got[-1][4] - got[0][4]), 60.0)
        moved = ((got[-1][1] - got[0][1]) ** 2 + (got[-1][2] - got[0][2]) ** 2) ** 0.5
        self.assertLess(moved, 0.3)
        self.render("turn", text)


if __name__ == "__main__":
    unittest.main()
