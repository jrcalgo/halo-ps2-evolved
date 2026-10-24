#!/usr/bin/env python3
"""Check that HCU ELFs do not retain halo-ps2 viewer simulation helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


FORBIDDEN = (
    "objects_clear",
    "objects_spawn_bsp",
    "objects_spawn_def",
    "objects_tick",
    "objects_pose",
    "objects_pose_model",
    "objects_pose_static",
    "fpview_init",
    "fpview_tick",
    "fpview_place",
    "skel_world",
    "skel_palette_entry",
)
REQUIRED = ("main", "halo_shell_main", "render_frame")
DEFAULT_NM = Path("build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-nm")


def parse_nm_symbols(output: str) -> set[str]:
    symbols: set[str] = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            symbols.add(fields[-1])
    return symbols


def audit(nm_output: str) -> dict[str, list[str] | bool]:
    symbols = parse_nm_symbols(nm_output)
    retained = [name for name in FORBIDDEN if name in symbols]
    missing = [name for name in REQUIRED if name not in symbols]
    return {
        "passed": not retained and not missing,
        "retained_viewer_simulation_symbols": retained,
        "missing_hcu_render_path_symbols": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--nm", type=Path, default=DEFAULT_NM)
    args = parser.parse_args()
    if not args.elf.is_file():
        parser.error(f"ELF does not exist: {args.elf}")
    if not args.nm.is_file():
        parser.error(f"EE nm does not exist: {args.nm}")

    result = subprocess.run(
        [str(args.nm), "-n", str(args.elf)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    disposition = audit(result.stdout)
    report = {
        "elf": str(args.elf),
        "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        **disposition,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if disposition["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
