"""Host test of the SPU2 music stream player (ring refill, loop flags, piece order) on a simulated SPU2."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/c3/spu-stream"


class HcuSpuStreamTest(unittest.TestCase):
    def test_stream(self):
        OUT.mkdir(parents=True, exist_ok=True)
        exe = OUT / "hcu_spu_stream_main"
        subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-I" + str(ROOT / "src"),
             "-o", str(exe), str(ROOT / "tests/hcu_spu_stream_main.c"), str(ROOT / "src/stream/hcu_spu_stream.c"),
             str(ROOT / "src/stream/hcu_spu_playback.c"), "-lm"],
            check=True)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("spu-stream-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
