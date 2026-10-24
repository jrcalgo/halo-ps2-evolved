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

    def test_cache_and_playback_events_are_distinct_and_metadata_is_explicit(self):
        main = (ROOT / "src/stream/hcu_main.c").read_text()
        ce = (ROOT / "submodules/halo-ce-universal/source/sound/sound_manager.c").read_text()
        port = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_sound_cache.c").read_text()
        self.assertIn("HCU_SOUND_EVENT_PERMUTATION_REQUEST", main)
        self.assertIn("request.metadata_known = 0", main)
        self.assertIn("request.accepted = accepted ? 1u : 0u", main)
        self.assertIn("halo_ps2_sound_playback_bind_sink", port)
        self.assertIn("channel_note_playback_request(sound, definition, &properties, permutation,", ce)
        self.assertIn("HCU_SOUND_EVENT_IMPULSE", ce)
        self.assertIn("HCU_SOUND_EVENT_LOOPING_START", ce)


if __name__ == "__main__":
    unittest.main()
