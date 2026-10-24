"""Pin production HP2 header/table rejection behavior used by the L1 loader."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class Hp2Section(ctypes.Structure):
    _fields_ = [
        ("tag", ctypes.c_char * 5),
        ("offset", ctypes.c_uint32),
        ("stored_size", ctypes.c_uint32),
        ("raw_size", ctypes.c_uint32),
        ("codec", ctypes.c_uint32),
        ("crc32", ctypes.c_uint32),
        ("align", ctypes.c_uint32),
    ]


class Hp2Pack(ctypes.Structure):
    _fields_ = [
        ("image", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
        ("name", ctypes.c_char * 17),
        ("count", ctypes.c_uint32),
        ("sections", Hp2Section * 64),
    ]


def _pack(rows):
    data = bytearray(64 + 32 * len(rows))
    data[:4] = b"HP2P"
    data[4:6] = (1).to_bytes(2, "little")
    data[6:8] = len(rows).to_bytes(2, "little")
    file_size = 4096
    data[8:12] = file_size.to_bytes(4, "little")
    for index, row in enumerate(rows):
        tag, offset, stored, raw, codec, align = row
        base = 64 + index * 32
        data[base:base + 4] = tag
        for field, value in ((4, offset), (8, stored), (12, raw),
                             (16, codec), (24, align)):
            data[base + field:base + field + 4] = value.to_bytes(4, "little")
    return bytes(data), file_size


class Hp2HeaderFaultMatrixTests(unittest.TestCase):
    def test_structural_table_faults_are_rejected_by_production_parser(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="hp2-header-matrix-") as temp:
            library_path = Path(temp) / "libhp2.so"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-shared", "-fPIC",
                "-I" + str(root / "submodules/halo-ps2/engine/src"),
                str(root / "submodules/halo-ps2/engine/src/stream/hp2.c"),
                "-o", str(library_path),
            ], check=True, capture_output=True, text=True)
            hp2 = ctypes.CDLL(str(library_path))
            open_header = hp2.hp2_open_header
            open_header.argtypes = [ctypes.POINTER(Hp2Pack), ctypes.c_void_p,
                                    ctypes.c_size_t, ctypes.c_size_t]
            open_header.restype = ctypes.c_int

            valid = (b"HMAP", 2048, 4, 4, 0, 16)
            overlap = (b"CRNG", 2048, 4, 4, 0, 16)
            cases = [
                ("truncated_table", _pack([valid, overlap])[0][:64], 4096, 1),
                ("reserved_entry_word", _pack([valid])[0][:96], 4096, 3,
                 (64 + 28, 1)),
                ("duplicate_tag", _pack([valid, (b"HMAP", 3072, 4, 4, 0, 16)])[0], 4096, 3),
                ("overlapping_extents", _pack([valid, overlap])[0], 4096, 3),
                ("unknown_codec", _pack([(b"HMAP", 2048, 4, 4, 2, 16)])[0], 4096, 3),
                ("extent_past_file", _pack([(b"HMAP", 4096, 4, 4, 0, 16)])[0], 4096, 1),
            ]
            for case in cases:
                name, header, file_size, expected = case[:4]
                if len(case) == 5:
                    offset, value = case[4]
                    header = bytearray(header)
                    header[offset:offset + 4] = value.to_bytes(4, "little")
                    header = bytes(header)
                with self.subTest(case=name):
                    pack = Hp2Pack()
                    header_buffer = ctypes.create_string_buffer(header)
                    status = open_header(ctypes.byref(pack), header_buffer,
                                         len(header), file_size)
                    self.assertEqual(status, expected)


if __name__ == "__main__":
    unittest.main()
