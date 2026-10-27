from pathlib import Path
import subprocess
import tempfile


def test_local_setup_validator_rejects_before_teardown_and_accepts_qualified_profiles():
	root = Path(__file__).resolve().parents[1]
	with tempfile.TemporaryDirectory(prefix="hcu-local-setup-") as temp:
		executable = Path(temp) / "hcu-local-setup-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-Isrc",
			"tests/hcu_local_setup_main.c",
			"src/stream/hcu_local_setup.c",
			"-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		result = subprocess.run([str(executable)], check=True,
			capture_output=True, text=True)
	for needle in (
		"reject unknown-mode: unknown-mode, state unchanged",
		"reject population-above-qualified",
		"reject bots-above-qualified",
		"reject null-rows",
		"reject team-mismatch: team-mismatch",
		"reject ctf-needs-teams: team-mismatch",
		"reject survival-with-teams: team-mismatch",
		"reject too-many-bots: too-many-bots",
		"teardown-failure: teardown-failed",
		"accept coop: humans=4 bots=4 qualified=8",
		"accept teams: human team 0, bot team 1",
		"accept measure: status=measuring humans=4 bots=12",
		"reject play-unqualified-row: difficulty-not-qualified",
		"reject measure-team-mismatch: team-mismatch, state unchanged",
		"reject measure-too-many-bots: too-many-bots, state unchanged",
		"reject measure-bad-human-mask: bad-human-mask, state unchanged",
		"reject measure-no-humans: no-humans, state unchanged",
		"reject measure-bad-map-name: bad-map-name, state unchanged",
		"reject measure-map-without-row: map-not-qualified, state unchanged",
		"reject measure-unknown-intent: bad-argument, state unchanged",
		"reject measure-unknown-difficulty: unknown-difficulty, state unchanged",
		"rows table: 13 rows, all unqualified",
		"hcu_local_setup tests passed",
	):
		assert needle in result.stdout, needle
