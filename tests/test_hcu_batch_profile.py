import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compiled_batch_profile_accumulator():
	with tempfile.TemporaryDirectory() as td:
		binary = Path(td) / "batch-profile-test"
		subprocess.run([
			"cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
			str(ROOT / "tests/hcu_batch_profile_main.c"), "-o", str(binary),
		], check=True)
		subprocess.run([str(binary)], check=True)
