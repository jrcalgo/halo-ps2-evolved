from pathlib import Path
import subprocess
import tempfile


def test_survival_host_contract():
	root = Path(__file__).resolve().parents[1]
	with tempfile.TemporaryDirectory(prefix="hcu-survival-") as temp:
		executable = Path(temp) / "hcu-survival-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-Isrc",
			"tests/hcu_survival_main.c",
			"src/stream/hcu_survival.c",
			"-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		result = subprocess.run([str(executable)], check=True,
			capture_output=True, text=True)
	for needle in ("validation: ok", "repeated mixed waves: ok", "storage reuse: ok",
		"same-tick elimination: ok", "no active-wave respawn: ok", "intermission length: ok",
		"expansion reservation: ok", "swarm bound: ok", "budgets: ok", "refusal: ok",
		"hcu_survival tests passed"):
		assert needle in result.stdout, needle
