"""Coverage for the allocation-free streamed CTAG validator."""
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import ctag


STATUS_OK = 0
STATUS_FORMAT = 2
STATUS_BOUNDS = 3
STATUS_CHECKSUM = 4
STATUS_SPACE = 5
STATUS_IO = 8


def synthetic_image():
    image = bytearray(76)
    struct.pack_into("<9I", image, 0,
                     36, 0x00010000, 0x12345678, 1, 0, 0, 0, 0,
                     ctag.TAG_SIGNATURE)
    struct.pack_into("<I", image, 52, 68)
    struct.pack_into("<I", image, 56, 72)
    image[68:70] = b"x\0"
    image[72:76] = b"root"
    return bytes(image)


class StreamedCtagValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.port = cls.root / "submodules/halo-ce-universal/port/ps2"
        cls.temp = tempfile.TemporaryDirectory(prefix="hcu-ctag-stream-")
        cls.temp_path = Path(cls.temp.name)
        cls.executable = cls.temp_path / "ctag-stream-validate"
        subprocess.run([
            "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
            "-I" + str(cls.port / "include"),
            str(cls.root / "tests/hcu_ctag_stream_validate_main.c"),
            str(cls.port / "src/ps2_ctag.c"), "-o", str(cls.executable),
        ], check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name, payload, expected, scratch=20,
                 fail_offset=-1, maximum_relocations=100,
                 push_expected=None):
        path = self.temp_path / (name + ".ctag")
        path.write_bytes(payload)
        if push_expected is None:
            push_expected = expected
        result = subprocess.run([
            str(self.executable), str(path), str(expected), str(push_expected),
            str(scratch),
            str(fail_offset), str(maximum_relocations),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         f"{name}: stdout={result.stdout!r}, stderr={result.stderr!r}")

    def test_accepts_valid_payload_and_matches_legacy_parser_metadata(self):
        payload = ctag.encode(synthetic_image(), [0, 20, 28, 52, 56],
                              scenario_tag_index=0x00010000)
        self.run_case("valid", payload, STATUS_OK)

    def test_rejects_inner_image_crc_mismatch(self):
        payload = bytearray(ctag.encode(
            synthetic_image(), [0, 20, 28, 52, 56],
            scenario_tag_index=0x00010000))
        payload[ctag.HEADER_SIZE + 68] ^= 1
        self.run_case("bad-image-crc", bytes(payload), STATUS_CHECKSUM)

    def test_rejects_relocation_order_and_missing_required_field(self):
        encoded = ctag.encode(synthetic_image(), [0, 20, 28, 52, 56],
                              scenario_tag_index=0x00010000)
        image_size = len(synthetic_image())
        reloc_offset = ctag.HEADER_SIZE + image_size

        unordered = bytearray(encoded)
        first_last = struct.unpack_from("<I", unordered, reloc_offset + 12)[0]
        last = struct.unpack_from("<I", unordered, reloc_offset + 16)[0]
        struct.pack_into("<II", unordered, reloc_offset + 12, last, first_last)
        self.run_case("unordered-relocations", bytes(unordered), STATUS_BOUNDS)

        missing = bytearray(encoded)
        # Replace required field 28 with a sorted, otherwise in-range offset.
        struct.pack_into("<I", missing, reloc_offset + 8, 48)
        self.run_case("missing-required-relocation", bytes(missing), STATUS_FORMAT)

    def test_rejects_count_over_limit_and_scratch_exhaustion(self):
        encoded = ctag.encode(synthetic_image(), [0, 20, 28, 52, 56],
                              scenario_tag_index=0x00010000)
        too_many = bytearray(encoded)
        struct.pack_into("<I", too_many, 16, 101)
        self.run_case("relocation-count-over-limit", bytes(too_many),
                      STATUS_BOUNDS, maximum_relocations=100)
        self.run_case("scratch-too-small", encoded, STATUS_SPACE, scratch=19)

    def test_rejects_out_of_image_relocation_target(self):
        payload = bytearray(ctag.encode(
            synthetic_image(), [0, 20, 28, 52, 56],
            scenario_tag_index=0x00010000))
        struct.pack_into("<I", payload, ctag.HEADER_SIZE + 56, 0xFFFFFFFF)
        image = payload[ctag.HEADER_SIZE:ctag.HEADER_SIZE + len(synthetic_image())]
        struct.pack_into("<I", payload, 32, zlib.crc32(image) & 0xFFFFFFFF)
        self.run_case("out-of-image-target", bytes(payload), STATUS_BOUNDS,
                      push_expected=STATUS_OK)

    def test_reports_exact_read_failure_and_clears_output(self):
        payload = ctag.encode(synthetic_image(), [0, 20, 28, 52, 56],
                              scenario_tag_index=0x00010000)
        self.run_case("read-failure", payload, STATUS_IO,
                      fail_offset=ctag.HEADER_SIZE + 4)


if __name__ == "__main__":
    unittest.main()
