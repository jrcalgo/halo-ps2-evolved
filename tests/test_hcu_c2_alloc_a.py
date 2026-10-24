#!/usr/bin/env python3
"""C2.5 alloc-a host checks: the CE memory pool's counters and bounded reuse.

Compiles source/memory/memory_pool.c unchanged against the host shim, runs
100,000 allocate/reallocate/free cycles, and requires zero growth, zero moves
outside the pool, zero corruption and zero SDK fallbacks. The PS2 compatibility
arena is covered by tools/test_hcu_ps2_malloc_endless.py and
tools/test_hcu_ps2_malloc_diagnostic.py, which are run here too.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def main() -> int:
	compiler = shutil.which("cc")
	if not compiler:
		raise SystemExit("C compiler not found")
	with tempfile.TemporaryDirectory(prefix="hcu-c2-alloc-a-") as temp:
		binary = Path(temp) / "alloc-a"
		command = [
			compiler, "-std=gnu99", "-O2", "-Wall", "-Wextra", "-Werror",
			"-Wno-multichar", "-Wno-unused-parameter",
			"-I" + str(ROOT / "tests/hcu_c2_alloc_a_shim"),
			"-I" + str(HCU / "source/memory"),
			str(HCU / "source/memory/memory_pool.c"),
			str(ROOT / "tests/hcu_c2_alloc_a_main.c"), "-o", str(binary),
		]
		built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
		if built.returncode:
			raise SystemExit("compile failed:\n" + built.stdout + built.stderr)
		run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
		if run.returncode:
			raise SystemExit(f"pool churn failed ({run.returncode}):\n{run.stdout}{run.stderr}")
		line = run.stdout.strip()
		for want in ("cycles=100000", "used_after_drain=0", "growth=0",
				"corruptions=0", "escapes=0", "sdk_fallbacks=0"):
			if want not in line:
				raise SystemExit(f"missing '{want}' in:\n{line}")
		print(line)
	for tool in ("tools/test_hcu_ps2_malloc_endless.py", "tools/test_hcu_ps2_malloc_diagnostic.py"):
		done = subprocess.run([sys.executable, "-I", str(ROOT / tool)], cwd=ROOT, capture_output=True, text=True)
		if done.returncode:
			raise SystemExit(f"{tool} failed:\n{done.stdout}{done.stderr}")
		print(done.stdout, end="")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
