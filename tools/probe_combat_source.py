"""Compile unchanged Halo combat source for R5900 and inspect a partial link.

The generated prefix uses N64 capacity macros solely to satisfy header
declarations. These are *not* PS2 runtime limits. The partial link retains only
three update/damage roots; it is not a PS2 executable or evidence of parity.
"""
from __future__ import annotations

import argparse
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
FOUNDATION_UNITS = {
    "data": "source/memory/data.c",
    "game_time": "source/game/game_time.c",
}
LEAF_SUPPORT_UNITS = {
    "real_math": "source/math/real_math.c",
    "random_math": "source/math/random_math.c",
    "periodic_functions": "source/math/periodic_functions.c",
    "tag_groups": "source/tag_files/tag_groups.c",
}
ROOT_SYMBOLS = ("weapon_update", "projectile_update", "object_cause_damage")
LIFECYCLE_ROOTS = (
    "weapon_new", "weapon_delete", "weapon_owner_update",
    "weapon_handle_potential_inventory_item", "weapon_place", "weapon_ready",
    "weapon_put_away", "weapon_melee_attack", "projectile_new",
    "projectile_delete", "object_damage_update", "object_initialize_vitality",
    "area_of_effect_cause_damage", "damage_data_new",
)
TOOLCHAIN_RUNTIME_SYMBOLS = {"floor", "fmod", "rint", "scalbn", "sqrt", "strrchr"}
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
#pragma weak halo_random
"""


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def undefined_symbols(nm: Path, obj: Path) -> set[str]:
    output = subprocess.check_output([str(nm), "-u", str(obj)], text=True)
    return {line.split()[-1] for line in output.splitlines() if line.strip()}


def live_external_symbols(nm: Path, objdump: Path, obj: Path) -> list[str]:
    """Filter undefined symbol-table entries to surviving relocations."""
    undefined = undefined_symbols(nm, obj)
    relocations = subprocess.check_output([str(objdump), "-r", str(obj)], text=True)
    referenced = {line.split()[-1].split("+")[0] for line in relocations.splitlines()
                  if "R_MIPS_" in line}
    return sorted(undefined & referenced)


def is_toolchain_runtime(symbol: str) -> bool:
    return symbol.startswith("__") or symbol in TOOLCHAIN_RUNTIME_SYMBOLS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundations", action="store_true",
                        help="also compile and partially link the original datum and tick services")
    parser.add_argument("--lifecycle", action="store_true",
                        help="retain combat creation, ownership, inventory, melee and damage roots")
    parser.add_argument("--leaf-support", action="store_true",
                        help="add original vector, random, transition and tag-block implementations")
    parser.add_argument("--deterministic-math", action="store_true",
                        help="link the pinned cross-platform musl math implementation")
    args = parser.parse_args()
    build, prefix, env, _ = environment()
    output_name = "combat-source-foundations" if args.foundations else "combat-source-probe"
    suffix = (("-lifecycle" if args.lifecycle else "") +
              ("-leaf" if args.leaf_support else "") +
              ("-math" if args.deterministic_math else ""))
    output = build / (output_name + suffix)
    output.mkdir(parents=True, exist_ok=True)
    header = output / "halo_ps2_probe_prefix.h"
    header.write_text(PREFIX)
    semantics = output / "halo_msvc_semantics.h"
    subprocess.run(["python3", str(SOURCE / "tools/linux_msvc_semantics.py"),
                    "--output", str(semantics), "--all-inlines", "--exclude-static",
                    "--tags", str(SOURCE / "source"),
                    "--inlines", str(SOURCE / "source"),
                    "--inlines", str(SOURCE / "port/include/xdk")],
                   cwd=ROOT, env=env, check=True)
    config = json.loads((SOURCE / "config/config.json").read_text())
    include_dirs = [SOURCE / name for name in config["projects"][0]["options"]["include_dirs"]
                    if name != "xbox/include"]
    include_dirs += [SOURCE / "port/linux/include", SOURCE / "port/include",
                    SOURCE / "port/include/xdk", SOURCE / "port/n64/include"]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    objdump = prefix / "ee/bin/mips64r5900el-ps2-elf-objdump"
    linker = prefix / "ee/bin/mips64r5900el-ps2-elf-ld"
    flags = ["-std=gnu89", "-fms-extensions", "-fshort-wchar", "-fcommon",
             "-fno-strict-aliasing", "-fno-delete-null-pointer-checks",
             "-ffp-contract=off", "-fsigned-char", "-fwrapv", "-ffunction-sections",
             "-fdata-sections", "-G0", "-w", "-D_EE",
             *["-I" + str(item) for item in include_dirs], "-include", str(header),
             "-include", str(semantics), "-c"]
    report = {"status": "partial-relocatable-link", "compiler": subprocess.check_output(
        [str(compiler), "--version"], text=True).splitlines()[0],
        "prefix_sha256": digest(header), "semantics_sha256": digest(semantics), "units": {},
        "limits": "N64 capacity macros are compile-only placeholders; no PS2 executable, runtime, or parity claim."}
    objects = []
    units = (UNITS | (FOUNDATION_UNITS if args.foundations else {}) |
             (LEAF_SUPPORT_UNITS if args.leaf_support else {}))
    for name, relative in units.items():
        source = SOURCE / relative
        obj = output / (name + ".o")
        run = subprocess.run([str(compiler), *flags, str(source), "-o", str(obj)],
                             cwd=ROOT, env=env, text=True, capture_output=True)
        (output / (name + ".log")).write_text(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError(f"{relative} failed; see {output / (name + '.log')}")
        objects.append(obj)
        symbols = subprocess.check_output([str(nm), "-u", str(obj)], text=True)
        (output / (name + "-undefined.txt")).write_text(symbols)
        report["units"][relative] = {"source_sha256": digest(source),
                                     "object_sha256": digest(obj),
                                     "undefined_symbols": sum(bool(line.strip()) for line in symbols.splitlines())}
    if args.deterministic_math:
        musl = SOURCE / "port/third_party/musl-math"
        musl_flags = ["-std=gnu11", "-O2", "-ffp-contract=off", "-fno-math-errno",
                      "-ffunction-sections", "-fdata-sections", "-G0", "-w", "-D_EE",
                      "-I" + str(musl / "include"), "-include", str(musl / "include/libm.h"), "-c"]
        for source in sorted((musl / "src").glob("*.c")):
            obj = output / ("musl-" + source.stem + ".o")
            run = subprocess.run([str(compiler), *musl_flags, str(source), "-o", str(obj)],
                                 cwd=ROOT, env=env, text=True, capture_output=True)
            (output / ("musl-" + source.stem + ".log")).write_text(run.stdout + run.stderr)
            if run.returncode:
                raise RuntimeError(f"{source.relative_to(SOURCE)} failed; see {output / ('musl-' + source.stem + '.log')}")
            objects.append(obj)
        report["deterministic_math"] = {
            "source": "port/third_party/musl-math", "object_count": len(list((musl / "src").glob("*.c"))),
            "readme_sha256": digest(musl / "README.md"),
        }
    combined = output / "combat-core.o"
    roots = ROOT_SYMBOLS + (LIFECYCLE_ROOTS if args.lifecycle else ())
    link = subprocess.run([str(linker), "-r", "--gc-sections",
                           *[arg for symbol in roots for arg in ("-u", symbol)],
                           *map(str, objects), "-o", str(combined)],
                          cwd=ROOT, env=env, text=True, capture_output=True)
    (output / "partial-link.log").write_text(link.stdout + link.stderr)
    if link.returncode:
        raise RuntimeError(f"Combat partial link failed; see {output / 'partial-link.log'}")
    live = live_external_symbols(nm, objdump, combined)
    runtime = [symbol for symbol in live if is_toolchain_runtime(symbol)]
    game_platform = [symbol for symbol in live if not is_toolchain_runtime(symbol)]
    (output / "live-externals.txt").write_text("\n".join(live) + "\n")
    report["partial_link"] = {
        "roots": list(roots), "object_sha256": digest(combined),
        "undefined_symbol_table_count": len(undefined_symbols(nm, combined)),
        "live_external_count": len(live), "live_d3d_count": sum(name.startswith("D3D") for name in live),
        "live_external_symbols": live,
        "toolchain_runtime_external_count": len(runtime),
        "toolchain_runtime_external_symbols": runtime,
        "game_platform_external_count": len(game_platform),
        "game_platform_external_symbols": game_platform,
    }
    save(output / "result.json", report)
    print(output / "result.json")


if __name__ == "__main__":
    main()
