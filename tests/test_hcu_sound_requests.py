"""Host test for the bounded CE sound-request recorder (C3.8).

Compiles tests/hcu_sound_requests_main.c against src/stream/hcu_sound_requests.c
and checks the ring, ordering, validation and counters. SPU2 playback is not
exercised: the recorder reports spu2-playback=not-qualified by design."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/c3/sound-replace"


class HcuSoundRequestsTest(unittest.TestCase):
    def test_recorder_fixture(self):
        OUT.mkdir(parents=True, exist_ok=True)
        exe = OUT / "hcu_sound_requests_main"
        subprocess.run(
            ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
             "-o", str(exe), str(ROOT / "tests/hcu_sound_requests_main.c"),
             str(ROOT / "src/stream/hcu_sound_requests.c")],
            check=True)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS sound request recorder", result.stdout)
        self.assertIn("spu2-playback=not-qualified", result.stdout)


if __name__ == "__main__":
    unittest.main()
