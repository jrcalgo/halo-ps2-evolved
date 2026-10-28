"""Host test of the SPU2 playback core (bank parse, voice allocation, pitch/volume).

Uses a recording fake for the SPU2 register operations; the libsd/sdrdrv glue is
exercised only by the PS2 guest run."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/c3/spu-playback"


class HcuSpuPlaybackTest(unittest.TestCase):
    def test_playback_core(self):
        OUT.mkdir(parents=True, exist_ok=True)
        exe = OUT / "hcu_spu_playback_main"
        subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
             "-o", str(exe), str(ROOT / "tests/hcu_spu_playback_main.c"),
             str(ROOT / "src/stream/hcu_spu_playback.c"), "-lm"],
            check=True)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("spu-playback-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
