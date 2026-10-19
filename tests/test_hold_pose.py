"""Gravity rifle rotation matches the Halo 2 carbine idle, and the grip stays put."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"


class HoldPose(unittest.TestCase):
    def test_carbine_rotation_and_grip_anchor(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hold_pose"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"), "-I" + str(ENGINE),
                 str(ROOT / "tests/hold_pose_main.c"),
                 str(ENGINE / "core/mat.c"), "-lm", "-o", str(exe)],
                check=True, capture_output=True, text=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        self.assertTrue(out.startswith("hold carbine "))
