"""Exercise the allocation-free direct FileXio reader path with SDK API fakes."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class FileReaderFileXioTests(unittest.TestCase):
    def test_direct_filexio_path_requires_service_and_bounds_reads(self):
        root = Path(__file__).resolve().parents[1]
        ps2sdk = root / "submodules/ps2sdk"
        engine = root / "submodules/halo-ps2/engine/src"
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "file-reader-filexio-test"
            subprocess.run([
                "cc", "-std=gnu11", "-D_EE", "-DHALO_FILE_USE_FILEXIO",
                "-Wall", "-Wextra", "-Werror", "-Wno-int-to-pointer-cast",
                "-I" + str(root / "src"), "-I" + str(engine),
                "-I" + str(ps2sdk / "common/include"),
                "-I" + str(ps2sdk / "ee/include"),
                "-I" + str(ps2sdk / "ee/rpc/filexio/include"),
                str(root / "tests/file_reader_filexio_main.c"),
                str(engine / "stream/file.c"),
                str(engine / "core/mem.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True, capture_output=True,
                           text=True)


if __name__ == "__main__":
    unittest.main()
