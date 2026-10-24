#!/usr/bin/env python3
"""Endless-play churn test for the PS2 compatibility allocator (host build)."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def main() -> int:
	compiler = shutil.which("cc")
	if not compiler:
		raise SystemExit("C compiler not found")
	with tempfile.TemporaryDirectory(prefix="hcu-ps2-malloc-endless-") as temp:
		binary = Path(temp) / "malloc-endless"
		command = [
			compiler, "-std=gnu99", "-O2", "-Wall", "-Wextra", "-Werror",
			"-DHALO_PS2", "-DHALO_PS2_STEP8_MEMORY_DIAGNOSTIC=1",
			"-DHALO_PS2_NO_BOOTSTRAP_MEMORY", "-I" + str(HCU / "source"),
			"-I" + str(ROOT / "tests/hcu_ps2_memory_shim"),
			"-I" + str(HCU / "port/ps2/include"), "-Wno-sign-compare",
			str(HCU / "port/ps2/src/ps2_memory.c"),
			str(ROOT / "tests/hcu_ps2_malloc_endless_main.c"), "-o", str(binary),
		]
		built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
		if built.returncode:
			raise SystemExit("compile failed:\n" + built.stdout + built.stderr)
		run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
		if run.returncode:
			raise SystemExit(f"endless allocator churn failed ({run.returncode}):\n{run.stdout}{run.stderr}")
		if "failures=0 fragmentation_failures=0" not in run.stdout or "sdk_fallbacks=0" not in run.stdout:
			raise SystemExit("unexpected churn result:\n" + run.stdout)
		print(run.stdout, end="")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
