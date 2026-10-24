from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


class HcuReaderFaultMatrixTests(unittest.TestCase):
    def test_production_c_metadata_and_cbsp_readers_reject_malformed_inputs(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        engine = root / "submodules/halo-ps2/engine/src"
        ps2_include = root / "submodules/halo-ce-universal/port/ps2/include"
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "hcu-reader-fault-matrix"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                "-Isrc", "-I" + str(engine), "-I" + str(ps2_include),
                str(root / "tests/hcu_reader_fault_matrix_main.c"),
                str(root / "src/stream/hmap.c"),
                str(root / "src/stream/cbsp_catalog.c"),
                str(root / "src/stream/ctag_resource_index.c"),
                str(engine / "stream/hp2.c"),
                str(root / "submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([str(executable)], check=True,
                                    capture_output=True, text=True,
                                    env={**os.environ,
                                         "ASAN_OPTIONS": "detect_leaks=0"})
            self.assertIn(
                "reader-fault-matrix hmap=11 crng=15 cbix=16 cbsp=21",
                result.stdout)


if __name__ == "__main__":
    unittest.main()
