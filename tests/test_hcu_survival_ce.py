from pathlib import Path
import subprocess
import tempfile


def test_survival_ce_host_contract():
	root = Path(__file__).resolve().parents[1]
	with tempfile.TemporaryDirectory(prefix="hcu-survival-ce-") as temp:
		executable = Path(temp) / "hcu-survival-ce-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-Isrc/stream",
			"tests/hcu_survival_ce_main.c",
			"src/stream/hcu_survival_ce.c",
			"src/stream/hcu_survival.c",
			"-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		result = subprocess.run([str(executable)], check=True,
			capture_output=True, text=True)
	for needle in ("recipes: ok", "bounds: ok", "pool: ok", "deaths and gate: ok", "slots: ok",
		"human for slot: ok", "next reserve matches admission: ok", "raise secondary: ok",
		"hcu_survival_ce tests passed"):
		assert needle in result.stdout, needle
