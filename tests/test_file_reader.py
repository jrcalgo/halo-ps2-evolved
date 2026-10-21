"""Host regression for allocation-free descriptor reads and CRNG map sources."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class FileReaderTests(unittest.TestCase):
    def test_bounded_persistent_reader_and_map_source(self):
        root = Path(__file__).resolve().parents[1]
        payload = bytes((i * 13 + 7) & 0xFF for i in range(2048))
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source.bin"
            source.write_bytes(payload)
            executable = directory / "file-reader-test"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Isrc", "-I" + str(root / "submodules/halo-ps2/engine/src"),
                str(root / "tests/file_reader_main.c"),
                str(root / "src/stream/ctag_map_source.c"),
                str(root / "src/stream/sha256.c"),
                str(root / "src/stream/hmap.c"),
                str(root / "src/stream/ctag_mount.c"),
                str(root / "src/stream/cbsp_catalog.c"),
                str(root / "src/stream/ctag_resource_index.c"),
                str(root / "submodules/halo-ps2/engine/src/stream/file.c"),
                str(root / "submodules/halo-ps2/engine/src/stream/hp2.c"),
                str(root / "submodules/halo-ps2/engine/src/core/mem.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable), str(source), str(directory) + "/"],
                           check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
