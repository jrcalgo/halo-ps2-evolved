#!/usr/bin/env python3
"""Host test for opt-in telemetry on the HCU PS2 compatibility allocator."""
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
	with tempfile.TemporaryDirectory(prefix="hcu-ps2-malloc-diagnostic-") as temp:
		binary = Path(temp) / "malloc-diagnostic"
		command = [
			compiler, "-std=gnu99", "-O2", "-Wall", "-Wextra", "-Werror",
			"-DHALO_PS2", "-DHALO_PS2_STEP8_MEMORY_DIAGNOSTIC=1",
			"-DHALO_PS2_NO_BOOTSTRAP_MEMORY", "-I" + str(HCU / "source"),
			"-I" + str(ROOT / "tests/hcu_ps2_memory_shim"),
			"-I" + str(HCU / "port/ps2/include"), "-Wno-sign-compare",
			str(HCU / "port/ps2/src/ps2_memory.c"),
			str(ROOT / "tests/hcu_ps2_malloc_diagnostic_main.c"), "-o", str(binary),
		]
		built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
		if built.returncode:
			raise SystemExit("compile failed:\n" + built.stdout + built.stderr)
		run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
		if run.returncode:
			raise SystemExit(f"host allocator diagnostic failed ({run.returncode}):\n{run.stdout}{run.stderr}")
		expected = "ps2-malloc-diagnostic preboot-realloc=preserved align=16 high_water=224 failures=3 free=coalesced-reuse rebind_reset=passed"
		if expected not in run.stdout:
			raise SystemExit("expected diagnostic marker missing:\n" + run.stdout)
		print(run.stdout, end="")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
