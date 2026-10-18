"""Compile unchanged Halo combat source for R5900; object-only feasibility probe.

The generated prefix uses N64 capacity macros solely to satisfy header
declarations. These are *not* PS2 runtime limits. No object is linked into the
PS2 viewer, and successful compilation does not establish behavior parity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from build_toolchain import ROOT, environment, save

SOURCE = ROOT / "submodules/halo-64"
UNITS = {
    "weapons": "source/items/weapons.c",
    "projectiles": "source/items/projectiles.c",
    "damage": "source/objects/damage.c",
}
PREFIX = r"""#include <string.h>
#include <stdlib.h>
#define HALO_LINUX 1
#define _X86_ 1
#define _STDCALL_SUPPORTED 1
#define _INTEGRAL_MAX_BITS 64
#define _USE_MATH_DEFINES 1
#define __export
#define __cdecl
#define __stdcall
#define __fastcall
#define _cdecl
#define _stdcall
#define _fastcall
#define __declspec(x)
#define __int8 char
#define __int16 short
#define __int32 int
#define __int64 long long
#define __unaligned
#define __w64
#define __ptr32
#define __inline __inline__
#define _inline __inline__
#define __forceinline __inline__ __attribute__((always_inline))
#define __NO_INLINE__ 1
#define DECLSPEC_SELECTANY __attribute__((weak))
#define __try if (1)
#define __except(filter) else if (0)
#define __finally
#define __leave
#define strnlen halo_strnlen
#define random halo_random
#include "halo_n64_limits.h"
"""


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    build, prefix, env, _ = environment()
    output = build / "combat-source-probe"
    output.mkdir(parents=True, exist_ok=True)
    header = output / "halo_ps2_probe_prefix.h"
    header.write_text(PREFIX)
    config = json.loads((SOURCE / "config/config.json").read_text())
    include_dirs = [SOURCE / name for name in config["projects"][0]["options"]["include_dirs"]
                    if name != "xbox/include"]
    include_dirs += [SOURCE / "port/linux/include", SOURCE / "port/include",
                    SOURCE / "port/include/xdk", SOURCE / "port/n64/include"]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    flags = ["-std=gnu89", "-fms-extensions", "-fshort-wchar", "-fcommon",
             "-fno-strict-aliasing", "-fwrapv", "-G0", "-w", "-D_EE",
             *["-I" + str(item) for item in include_dirs], "-include", str(header), "-c"]
    report = {"status": "objects-only", "compiler": subprocess.check_output(
        [str(compiler), "--version"], text=True).splitlines()[0],
        "prefix_sha256": digest(header), "units": {},
        "limits": "N64 capacity macros are compile-only placeholders; no PS2 runtime, link, or parity claim."}
    for name, relative in UNITS.items():
        source = SOURCE / relative
        obj = output / (name + ".o")
        run = subprocess.run([str(compiler), *flags, str(source), "-o", str(obj)],
                             cwd=ROOT, env=env, text=True, capture_output=True)
        (output / (name + ".log")).write_text(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError(f"{relative} failed; see {output / (name + '.log')}")
        symbols = subprocess.check_output([str(nm), "-u", str(obj)], text=True)
        (output / (name + "-undefined.txt")).write_text(symbols)
        report["units"][relative] = {"source_sha256": digest(source),
                                     "object_sha256": digest(obj),
                                     "undefined_symbols": sum(bool(line.strip()) for line in symbols.splitlines())}
    save(output / "result.json", report)
    print(output / "result.json")


if __name__ == "__main__":
    main()
