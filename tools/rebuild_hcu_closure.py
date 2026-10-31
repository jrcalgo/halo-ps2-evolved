#!/usr/bin/env python3
"""Rebuild the CE closure the ISO seed link leaves stale.

tools/build_halo_ps2_iso.py --seed-link copies a finished probe tree. It does
not recompile CE units (decals.c, objects.c, ps2_render.c, main.c, and the
rest of the closure). tools/hcu_ps2_closure.py compiles those units and
relinks rooted.o with --gc-sections and the production, chain-load, and C3
roots it already owns. That tool has no incremental mode, so this runs its
full entry point with the ISO guest flags (--layer all --no-bootstrap-memory
--production-runtime-guest) and the ISO C3 environment. It does not pack an
ISO and it does not pass --full-seed.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_halo_ps2_iso as iso  # noqa: E402

TMP = Path("/home/ai/.cache/hbtmp")
LOCK = Path("/tmp/hb/build.lock")


def closure_argv() -> list[str]:
    return [
        sys.executable,
        "tools/hcu_ps2_closure.py",
        "--layer", "all",
        "--no-bootstrap-memory",
        "--production-runtime-guest",
    ]


def closure_overrides() -> dict[str, str]:
    """ISO C3 flags plus the include path that selects the shared closure directory.

    C_INCLUDE_PATH is the same for every map (build_halo_ps2_iso.base_env).
    The quiet preset's remaining C3 flags are applied inside the closure tool.
    HCU_C3_OBJECTS_GEN is a parent-object input and is not passed through.
    """
    iso_env = iso.base_env(None)
    ordered = {"TMPDIR": str(TMP)}
    for key, value in iso.C3_ENV.items():
        if key == "TMPDIR":
            continue
        ordered[key] = value
    ordered["C_INCLUDE_PATH"] = iso_env["C_INCLUDE_PATH"]
    return ordered


def format_command(overrides: dict[str, str], argv: list[str]) -> str:
    assignments = [f"{key}={value}" for key, value in overrides.items()]
    return shlex.join(["cd", str(ROOT)]) + " && " + shlex.join(["env", *assignments, *argv])


def _process_ancestors() -> set[str]:
    """This process and its parents. flock(1) keeps the lock in the parent."""
    pids: set[str] = set()
    pid = str(os.getpid())
    while pid and pid != "0" and pid not in pids:
        pids.add(pid)
        try:
            status = Path(f"/proc/{pid}/status").read_text()
        except OSError:
            break
        parent = ""
        for line in status.splitlines():
            if line.startswith("PPid:"):
                parent = line.split()[1]
                break
        pid = parent
    return pids


def _lock_held_by_this_process(path: Path) -> bool:
    """True when this process or an ancestor already holds an flock on path."""
    try:
        inode = str(path.stat().st_ino)
        text = Path("/proc/locks").read_text()
    except OSError:
        return False
    holders = _process_ancestors()
    for line in text.splitlines():
        if "->" in line:
            continue
        parts = line.split()
        # "N: FLOCK ADVISORY WRITE <pid> <major>:<minor>:<inode> ..."
        if len(parts) < 6 or parts[1] != "FLOCK" or parts[2] != "ADVISORY":
            continue
        if parts[4] not in holders:
            continue
        if parts[5].rsplit(":", 1)[-1] == inode:
            return True
    return False


def run_closure(overrides: dict[str, str], argv: list[str]) -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(overrides)
    if _lock_held_by_this_process(LOCK):
        completed = subprocess.run(argv, cwd=ROOT, env=env)
        return completed.returncode
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        completed = subprocess.run(argv, cwd=ROOT, env=env)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="print the closure command and exit (default)")
    mode.add_argument("--run", action="store_true",
                      help="rebuild the CE closure under the ISO C3 environment")
    args = parser.parse_args()
    overrides = closure_overrides()
    argv = closure_argv()
    print(format_command(overrides, argv), flush=True)
    if not args.run:
        return 0
    return run_closure(overrides, argv)


if __name__ == "__main__":
    raise SystemExit(main())
