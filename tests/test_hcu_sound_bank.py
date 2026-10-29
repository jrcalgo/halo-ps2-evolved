import hashlib
import math
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_sound_bank as sb  # noqa: E402

MAP = ROOT / "build/retail-maps/decompressed/bloodgulch.map"


def snr_db(ref, got):
    noise = sum((a - b) ** 2 for a, b in zip(ref, got)) or 1
    return 10 * math.log10(sum(a * a for a in ref) / noise)


class VagTests(unittest.TestCase):
    def test_round_trip_snr_and_end_flag(self):
        pcm = [int(12000 * math.sin(i * 0.07) + 3000 * math.sin(i * 0.31)) for i in range(28 * 40 + 5)]
        vag = sb.encode_vag(pcm)
        self.assertEqual(len(vag), 16 * 42)
        self.assertEqual(vag[1], 0)
        self.assertEqual(vag[-31], 0)
        self.assertEqual(vag[-15], 7)
        self.assertTrue(all(b == 0 for b in vag[-14:]))
        self.assertGreater(snr_db(pcm, sb.decode_vag(vag)[:len(pcm)]), 25.0)

    def test_silence_encodes_to_zero_nibbles(self):
        vag = sb.encode_vag([0] * 56)
        self.assertEqual(len(vag), 48)
        self.assertTrue(all(b == 0 for b in vag[2:16]))

    def test_name_hash_ignores_separators_and_case(self):
        self.assertEqual(sb.name_hash("Sound\\SFX\\Weapons\\Pistol\\Fire"), sb.name_hash("soundsfxweaponspistolfire"))
        self.assertNotEqual(sb.name_hash("a\\b"), sb.name_hash("a\\c"))

    def test_spu_pitch(self):
        self.assertEqual(sb.spu_pitch(48000), 0x1000)
        self.assertEqual(sb.spu_pitch(22050), 1882)


class XboxAdpcmTests(unittest.TestCase):
    def test_zero_nibbles_hold_predictor_with_decay(self):
        block = struct.pack("<hBB", 1000, 0, 0) + bytes(32)
        out = sb.decode_xbox_adpcm(block)
        self.assertEqual(len(out), 64)
        self.assertEqual(out[0], 1000)
        self.assertTrue(all(abs(v - 1000) < 16 for v in out))

    def test_stereo_downmix_length(self):
        block = struct.pack("<hBB", 100, 0, 0) + bytes(32)
        self.assertEqual(len(sb.decode_xbox_adpcm(block * 2, channels=2)), 64)

    def test_stereo_is_the_interleaved_ima_layout(self):
        # Both channel headers first, then 4-byte nibble groups alternating left, right. Left holds 0x07 nibbles
        # (rising), right 0x0f nibbles (falling): a per-channel block layout would mix their data and blow up.
        left, right = b"\x77" * 4, b"\xff" * 4
        block = struct.pack("<hBB", 0, 20, 0) + struct.pack("<hBB", 0, 20, 0) + (left + right) * 8
        out = sb.decode_xbox_adpcm(block, channels=2)
        mono_l = sb.decode_xbox_adpcm(struct.pack("<hBB", 0, 20, 0) + left * 8)
        mono_r = sb.decode_xbox_adpcm(struct.pack("<hBB", 0, 20, 0) + right * 8)
        self.assertEqual(out, [(l + r) // 2 for l, r in zip(mono_l, mono_r)])
        self.assertGreater(mono_l[-1], 1000)
        self.assertLess(mono_r[-1], -1000)


@unittest.skipUnless(MAP.is_file(), "retail map not present")
class BankTests(unittest.TestCase):
    def test_small_bank_verifies_and_detects_corruption(self):
        blob, entries = sb.build_bank(MAP, budget=60000, max_perms=1)
        info = sb.verify_bank(blob)
        self.assertEqual(info["count"], len(entries))
        self.assertGreater(info["count"], 0)
        self.assertLessEqual(info["spu_bytes"], 60000)
        bad = bytearray(blob)
        bad[len(bad) // 2] ^= 1
        with self.assertRaises(ValueError):
            sb.verify_bank(bytes(bad))


if __name__ == "__main__":
    unittest.main()
