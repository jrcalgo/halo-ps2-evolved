#!/usr/bin/env python3
"""Fail if decals.c or objects.c prints HALO_PS2_LOCAL outside the verbose gate."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ROOT / "submodules/halo-ce-universal/source/effects/decals.c",
    ROOT / "submodules/halo-ce-universal/source/objects/objects.c",
)
VERBOSE = "defined(HALO_PS2_C3_VERBOSE_PROFILING)"
PRINTF = re.compile(r"(?<![\w])printf\s*\(")


def directive(line):
    text = line.strip()
    if not text.startswith("#"):
        return ""
    return text[1:].lstrip()


def ungated_printfs(text):
    stack = []
    verbose = 0
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        body = directive(line)
        if body.startswith(("if", "ifdef", "ifndef")):
            opens = VERBOSE in body
            stack.append(opens)
            if opens:
                verbose += 1
        elif body.startswith("endif") and stack:
            if stack.pop() and verbose:
                verbose -= 1
        if verbose == 0 and "HALO_PS2_LOCAL" in line and PRINTF.search(line):
            found.append(number)
    return found


def main():
    failed = False
    for path in FILES:
        for number in ungated_printfs(path.read_text(encoding="utf-8", errors="replace")):
            print(f"{path}:{number}: ungated HALO_PS2_LOCAL printf", file=sys.stderr)
            failed = True
    if not failed:
        print("ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
