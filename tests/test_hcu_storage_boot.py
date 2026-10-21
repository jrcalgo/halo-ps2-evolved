from pathlib import Path
import subprocess
import tempfile
import unittest


class HcuStorageBootTests(unittest.TestCase):
    def test_reuses_or_loads_filexio_without_iop_reset(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "hcu-storage-boot-test"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-DHALO_FILE_USE_FILEXIO",
                "-I" + str(root / "tests/hcu_storage_boot_shim"),
                "-I" + str(root / "src"),
                "-I" + str(root / "submodules/halo-ps2/engine/src"),
                str(root / "tests/hcu_storage_boot_main.c"),
                str(root / "src/stream/hcu_storage_boot.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True, capture_output=True,
                           text=True)


if __name__ == "__main__":
    unittest.main()
