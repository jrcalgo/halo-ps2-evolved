from pathlib import Path
import subprocess


def test_c3_presentation_clock_and_snapshot_endpoint_contract():
	root = Path(__file__).resolve().parents[1]
	executable = root / "build/c3/fps-next/bi1/cadence-contract"
	executable.parent.mkdir(parents=True, exist_ok=True)
	subprocess.run([
		"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
		"-Isrc",
		"-Isubmodules/halo-ce-universal/port/ps2/include",
		"tests/c3_cadence_contract_main.c",
		"src/stream/hcu_snapshot_bank.c", "-o", str(executable),
	], cwd=root, check=True, capture_output=True, text=True)
	result = subprocess.run([str(executable)], cwd=root, check=True,
		capture_output=True, text=True)
	for needle in ("30 fixed ticks", "fractional long-run", "pause and resume",
		"A/B pinned, C published", "safely"):
		assert needle in result.stdout
