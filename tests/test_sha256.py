from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class Sha256Tests(unittest.TestCase):
    def test_nist_abc_vector_with_incremental_updates(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "sha256-test"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Isrc", str(root / "tests/sha256_main.c"),
                str(root / "src/stream/sha256.c"), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
