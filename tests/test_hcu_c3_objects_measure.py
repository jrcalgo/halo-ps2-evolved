"""Host tests for tools/hcu_c3_objects_measure.py (C3.6c footprint measurement).

The synthetic cases check the HCP2 reassembly, the TEXS texture sizing and the alignment without any package.
The Blood Gulch case reads the real 4-player package when it is staged under build/m2-c2-r3-selected-packages
and skips otherwise. Its totals are pinned so a change in the package or in the reader shows up here.
"""
import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
spec = importlib.util.spec_from_file_location("hcu_c3_objects_measure", ROOT / "tools/hcu_c3_objects_measure.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)
from hcu_profile_chunks import encode  # noqa: E402

PACKAGE_DIR = ROOT / "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot"


def texs_blob(textures, binds):
    """A minimal TEXS: header, texture records, binding records, then data (CLUT and pixels are zero bytes)."""
    toff = 64
    boff = toff + 32 * len(textures)
    data = bytearray(boff + 32 * len(binds))
    struct.pack_into("<4sHHIIIIII", data, 0, b"TEXS", 1, 0, len(textures), len(binds), toff, boff, 0, 0)
    for i, (w, h, ents, pix) in enumerate(textures):
        struct.pack_into("<HH", data, toff + 32 * i + 4, w, h)
        struct.pack_into("<I", data, toff + 32 * i + 0x14, pix)
        struct.pack_into("<H", data, toff + 32 * i + 0x18, ents)
    for i, (sid, tix) in enumerate(binds):
        struct.pack_into("<IH", data, boff + 32 * i, sid, tix)
    return bytes(data)


class ChunkReadTest(unittest.TestCase):
    def test_segmented_media_chunk_is_reassembled(self):
        big = bytes(range(256)) * 300            # 76,800 B: two 64 KiB segments
        small = b"\x01\x02\x03"
        pack = encode(7, {"ce": b"c" * 16, "media": {5: big, 9: small}, "sound_meta": b"s" * 16})
        chunks = measure.read_chunks(pack)
        self.assertEqual(chunks[5], big)
        self.assertEqual(chunks[9], small)

    def test_rejects_other_magic(self):
        with self.assertRaises(SystemExit):
            measure.read_chunks(b"NOPE" + b"\0" * 60)


class TexsSizeTest(unittest.TestCase):
    def test_binding_and_texture_bytes(self):
        blob = texs_blob([(64, 64, 256, 4096), (32, 32, 16, 512)], [(0x1234, 1), (0x5678, 0), (0x9999, 0xFFFF)])
        binds, sizes = measure.texs_sizes(blob)
        self.assertEqual(binds, {0x1234: 1, 0x5678: 0, 0x9999: 0xFFFF})
        self.assertEqual(sizes, [4096 + 4 * 256, 512 + 4 * 16])

    def test_alignment_is_64_bytes(self):
        self.assertEqual(measure.align(1), 64)
        self.assertEqual(measure.align(64), 64)
        self.assertEqual(measure.align(65), 128)


class BloodGulchPackageTest(unittest.TestCase):
    @unittest.skipUnless((PACKAGE_DIR / "bloodgulch_mounted_gunner_4p4bot.hcp").is_file(),
                         "Blood Gulch 4p package not staged")
    def test_pinned_totals(self):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = measure.main(["--package-dir", str(PACKAGE_DIR)])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("69 MODL entries, model 4932064 B, textures 4480224 B", text)
        self.assertIn("scen_lod2_only", text)
        self.assertIn("loaded as today (all LODs, all textures, 64 B aligned): 6907264 B fits=False", text)


if __name__ == "__main__":
    unittest.main()
