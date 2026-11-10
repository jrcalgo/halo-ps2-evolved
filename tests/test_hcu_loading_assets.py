"""The retail loading screen is read out of default.xbe at build time (tools/build_hcu_loading_assets.py).

The fixtures are synthetic: they follow the layout the retail loader uses and contain no retail bytes."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_hcu_loading_assets as loading  # noqa: E402


def rle(levels):
    out = bytearray()
    run = 0
    for value in levels:
        if run and (value != previous or run == 15):
            out.append(run << 4 | previous)
            run = 0
        previous = value
        run += 1
    out.append(run << 4 | previous)
    return bytes(out)


def synthetic_xbe(pad=4, bad_chant=False):
    total = loading.PICTURE_W * loading.PICTURE_H
    levels = [(i // 640) % 16 for i in range(total)]
    chant = bytearray()
    for block in range(loading.CHANT_BYTES // 36):
        chant += struct.pack("<hBB", block * 7 - 1000, block % 89 if not bad_chant else 200, 0) + bytes([0x5A]) * 32
    xbe = bytes(range(251)) * 9 + loading.HEADER + rle(levels) + bytes(pad) + bytes(chant) + b"tail"
    return xbe, levels, bytes(chant)


class LoadingAssetsTest(unittest.TestCase):
    def test_locates_picture_and_chant(self):
        for pad in (0, 4, 8):
            xbe, levels, chant = synthetic_xbe(pad)
            got_levels, got_chant = loading.locate(xbe)
            self.assertEqual(got_levels, [v << 4 for v in levels])
            self.assertEqual(got_chant, chant)

    def test_rejects_a_chant_with_bad_block_headers(self):
        xbe, _levels, _chant = synthetic_xbe(bad_chant=True)
        with self.assertRaises(loading.RetailLoadingError):
            loading.locate(xbe)

    def test_rejects_an_xbe_without_the_picture(self):
        with self.assertRaises(loading.RetailLoadingError):
            loading.locate(bytes(100000))

    def test_run_total_must_be_exact(self):
        with self.assertRaises(loading.RetailLoadingError):
            loading.decode_picture(bytes([0xF3]) * 10)

    def test_picture_is_blue_as_the_retail_loader_expands_it(self):
        image = loading.picture_image([0xF0] + [0] * (loading.PICTURE_W * loading.PICTURE_H - 1))
        self.assertEqual(image.getpixel((0, 0)), (0xF0 >> 2, 0xF0 >> 1, 0xF0))
        self.assertEqual(image.getpixel((1, 0)), (0, 0, 0))

    def test_stamp_marks_a_generated_package(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "load.rgb"
            package.write_bytes(b"x")
            self.assertFalse(loading.current(package))  # an older invented backplate has no stamp
            loading.stamp_for(package).write_text(f"loading-assets v{loading.VERSION} sha256 00\n")
            self.assertTrue(loading.current(package))
            loading.stamp_for(package).write_text("loading-assets v0 sha256 00\n")
            self.assertFalse(loading.current(package))

    def test_build_makes_a_ps2_field(self):
        xbe, _levels, _chant = synthetic_xbe()
        packed, stamp, pcm, native = loading.build(xbe)
        self.assertEqual(len(packed), 512 * 448 * 2)
        self.assertEqual(native.size, (320, 240))
        self.assertEqual(len(pcm), loading.CHANT_BYTES // 36 * 64)
        self.assertTrue(stamp.startswith(b"loading-assets v"))


if __name__ == "__main__":
    unittest.main()
