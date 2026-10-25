from pathlib import Path
import subprocess
import tempfile


def test_pinned_bank_is_never_overwritten_or_evicted_and_dedupe_is_cross_view():
	root = Path(__file__).resolve().parents[1]
	with tempfile.TemporaryDirectory(prefix="hcu-scenes-bank-") as temp:
		executable = Path(temp) / "hcu-scenes-bank-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-Isrc",
			"-I" + str(root / "submodules/halo-ce-universal/port/ps2/include"),
			"tests/hcu_scenes_bank_main.c",
			"src/stream/hcu_snapshot_bank.c",
			"-lm", "-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		result = subprocess.run([str(executable)], check=True,
			capture_output=True, text=True)
	for needle in ("pinned-writer: ok", "refused-writes=8", "eviction-refusals=8",
		"pinned-bytes: ok", "cross-view-dedupe: ok", "hcu_scenes_bank tests passed"):
		assert needle in result.stdout, needle
