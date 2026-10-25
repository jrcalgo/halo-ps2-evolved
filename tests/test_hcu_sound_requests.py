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
        self.assertIn("coalesced=", result.stdout)
        self.assertIn("evicted=", result.stdout)

    def test_cache_and_playback_events_are_distinct_and_metadata_is_explicit(self):
        main = (ROOT / "src/stream/hcu_main.c").read_text()
        ce = (ROOT / "submodules/halo-ce-universal/source/sound/sound_manager.c").read_text()
        binder = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_sound_playback_bind.c").read_text()
        self.assertIn("HCU_SOUND_EVENT_PERMUTATION_REQUEST", main)
        self.assertIn("request.metadata_known = 0", main)
        self.assertIn("request.accepted = accepted ? 1u : 0u", main)
        self.assertIn("halo_ps2_sound_playback_bind_sink", binder)
        self.assertIn("sound_definition, captured_owner_kind", main)
        self.assertIn("channel_note_playback_request(sound, definition, &properties, permutation,", ce)
        self.assertIn("sound->track_proc == track_object_impulse_sound", ce)
        self.assertIn("PS2_SOUND_OWNER_LOOPING", ce)
        self.assertIn("sound->source_identifier", ce)
        self.assertIn("channel_note_stop_request", ce)
        self.assertIn("PS2_SOUND_EVENT_STOP", ce)
        self.assertIn("PS2_SOUND_EVENT_FADE", ce)

    def test_ps2_selects_silent_recorder_platform_not_spu2(self):
        # The channel loop runs only when CE's sound manager is initialized, which needs a
        # selected platform. The PS2 build selects the silent recorder (slot 1); it never
        # plays audio, so SPU2 playback stays unqualified and the Xbox backend stays unselected.
        prefs = (ROOT / "submodules/halo-ce-universal/source/sound/sound_preferences.c").read_text()
        ce = (ROOT / "submodules/halo-ce-universal/source/sound/sound_manager.c").read_text()
        self.assertIn("#ifdef HALO_PS2\n\t1,", prefs)
        self.assertIn("&ps2_recorder_platform,", ce)
        self.assertIn(".platform_code = 1,", ce)
        self.assertIn("ps2_recorder_get_channel_state", ce)
        self.assertIn("#define dsound_port_set_channel_stereo_position(...) ((void)0)", ce)
        main = (ROOT / "src/stream/hcu_main.c").read_text()
        self.assertIn("halo_ps2_sound_playback_bind_sink(hcu_c3_sound_playback_sink, NULL)", main)
        recorder = (ROOT / "src/stream/hcu_sound_requests.c").read_text()
        self.assertIn("spu2-playback=not-qualified", recorder)


if __name__ == "__main__":
    unittest.main()
