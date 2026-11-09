"""Menu music bank: every title1 recording, resampled to fit SPU2 RAM."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_hcu_menu_audio as menu_audio  # noqa: E402


class MenuAudioTest(unittest.TestCase):
    def test_music_lists_intro_and_three_loops(self):
        names = [name for _source, group in menu_audio.MUSIC for name in group]
        self.assertEqual(len(names), 4)
        self.assertEqual(len(set(names)), 4)

    def test_fit_rate_fills_but_does_not_exceed_ram(self):
        retail = [(1468000, 44100), (1343000, 44100), (4776000, 44100), (2693000, 44100)]
        rate = menu_audio.fit_rate(retail, 5200)
        total = 5200 + sum(menu_audio.vag_bytes(int(n * rate / src)) for n, src in retail)
        self.assertLessEqual(total, menu_audio.SPU_CAPACITY)
        over = 5200 + sum(menu_audio.vag_bytes(int(n * (rate + menu_audio.RATE_STEP) / src)) for n, src in retail)
        self.assertGreater(over, menu_audio.SPU_CAPACITY)

    def test_small_music_keeps_source_rate(self):
        self.assertEqual(menu_audio.fit_rate([(44100, 44100)], 0), 44100)


if __name__ == "__main__":
    unittest.main()
