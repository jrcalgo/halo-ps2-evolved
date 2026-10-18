"""Truncated retail-map inputs fail before any pack is written."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "submodules/halo-ps2/tools"))
from halo2ps2 import mapinfo


class ConvertInputs(unittest.TestCase):
    def test_truncated_header_fails(self):
        with self.assertRaisesRegex(ValueError, "shorter than a cache header"):
            mapinfo.MapHeader.parse(b"head")

    def test_bad_magic_fails(self):
        buffer = bytearray(mapinfo.HEADER_SIZE)
        struct.pack_into("<I", buffer, 0, 1)
        with self.assertRaisesRegex(ValueError, "bad head/foot magic"):
            mapinfo.MapHeader.parse(bytes(buffer))


if __name__ == "__main__":
    unittest.main()
