"""Build a bootable C5 guest ELF without editing the shared PS2 closure or link scripts.

Stages (each reads the shared tools and writes only under build/c5-guest/):
  closure  tools/hcu_ps2_closure.py run with the C5 CE defines (HALO_PS2_BOTS, HALO_PS2_SURVIVAL) added to
           its source flags, in its own closure directory (suffix "-c5", never the shared closure).
  rooted   a rooted relocatable link of the closure's layer.o with the C5 roots added (ps2_bots_*, ps2_survival_*,
           actor lifecycle), because the shared rooted link keeps only its own roots.
  platform typed stubs for the remaining undefined symbols (hcu_ps2_link.emit), compiled from the shared link
           script's unit list.
  parent   tools/c5-world.mk (includes tools/ee-world.mk, adds the C5 parent objects) builds the gameplay objects.
  link     the final R5900 ELF, with --wrap hooks for the per-tick session call.

Usage: python3 tools/c5_build.py [--stage all|closure|rooted|platform|parent|link]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from build_toolchain import ROOT, environment  # noqa: E402

import hcu_ps2_closure  # noqa: E402
import hcu_ps2_link  # noqa: E402

C5_CE_DEFINES = ["-DHALO_PS2_BOTS=1", "-DHALO_PS2_SURVIVAL=1"]
# port/ps2/src/ps2_bots.c and ps2_survival.c include the fork's stream headers (hcu_bot.h, hcu_survival.h) bare.
C5_CE_INCLUDES = ["-I" + str(ROOT / "src/stream"), "-I" + str(ROOT / "src")]
C5_SUFFIX = "-c5"
OUT = ROOT / "build/c5-guest"
CLOSURE_DIR = ROOT / ("build/hcu-ps2-closure/all-no-bootstrap-memory" + C5_SUFFIX)

# Roots the shared closure does not keep. Each is a real CE provider the C5 parent side or the debug hook calls.
C5_ROOTS = (
    "ps2_bots_start", "ps2_bots_update_actions", "ps2_bots_player_killed", "ps2_bots_hash",
    "ps2_bots_set_event_sink",
    "ps2_survival_start", "ps2_survival_update", "ps2_survival_stop",
    "actor_place", "actor_set_active", "actor_handle_damage", "actor_kill", "actor_delete", "actors_update",
    # Boot-map request and mount check (hcu_c5_boot.c): CE's menu map-select pair and the map-state queries.
    "main_set_map_name", "main_menu_switch_to_single_player", "game_map_loaded",
    "cache_files_precache_map_loaded", "cache_files_tag_instances", "global_scenario_try_and_get",
    # Multiplayer variant for the sidewinder boot (hcu_c5_boot.c): CE's team-slayer builder, the current-variant setter
    # and the in-progress query.
    "build_game_variant_team_slayer", "game_set_game_variant", "game_in_progress",
)

# Symbols the parent side calls through --wrap. The final link wraps these; the wrappers live in hcu_c5_boot.c.
C5_WRAPS = ("ps2_bots_update_actions",)

# The shared link script's port units and link flags (hcu_ps2_link.main), reproduced because main() keys its
# output directory on the shared profile and would overwrite the shared closure.
PORT_UNITS = ("ps2_main.c", "ps2_abi.c", "ps2_memory.c", "ps2_crt.c", "ps2_edge.c", "ps2_sound_playback_bind.c")


def run(command: list[str], env: dict[str, str], cwd: Path = ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n"
                           f"{result.stdout[-4000:]}{result.stderr[-4000:]}")
    return result.stdout + result.stderr


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_closure(env: dict[str, str]) -> None:
    """Run the shared closure with C5 defines in its own directory. The shared closure stays untouched."""
    hcu_ps2_closure.FLAGS = list(hcu_ps2_closure.FLAGS) + C5_CE_DEFINES + C5_CE_INCLUDES
    hcu_ps2_closure.c3_workload_suffix = lambda: C5_SUFFIX
    saved_argv = sys.argv
    sys.argv = ["hcu_ps2_closure.py", "--layer", "all", "--no-bootstrap-memory"]
    try:
        hcu_ps2_closure.main()
    except SystemExit as error:
        if error.code not in (None, 0):
            raise RuntimeError(f"closure failed: {error.code}") from error
    finally:
        sys.argv = saved_argv
    if not (CLOSURE_DIR / "layer.o").is_file():
        raise RuntimeError(f"closure produced no layer.o in {CLOSURE_DIR}")


def roots_flags() -> list[str]:
    return [arg for name in C5_ROOTS for arg in ("-u", name)]


def closure_objects() -> list[Path]:
    """The closure's compiled units, as listed in its objects.rsp (quoted paths, one per line)."""
    lines = (CLOSURE_DIR / "objects.rsp").read_text().splitlines()
    return [Path(line.strip().strip('"')) for line in lines if line.strip()]


def stage_rooted(env: dict[str, str]) -> Path:
    """Root and gc the closure's unit objects in one link, with the --wrap on the CE tick call.

    The wrap must be applied per unit: ld -r on layer.o already resolves the call inside the layer. Unit objects keep
    the call as an undefined reference, which --wrap renames to __wrap_ps2_bots_update_actions (hcu_c5_boot.c).

    One pass matters: a partial link without --gc-sections first (layer.o) merges the units' function sections, and
    the later gc then keeps about 1.3 MB of unreachable code (measured: 3,195,729 B against 1,848,718 B for the same
    roots applied to the unit objects directly). The defined-symbol set comes from nm over the unit objects.
    """
    prefix = environment()[1]
    linker = prefix / "ee/bin/mips64r5900el-ps2-elf-ld"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    units = closure_objects()
    defined: set[str] = set()
    for line in run([str(nm), "-g", *map(str, units)], env).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-2] in ("T", "t", "W", "w", "b", "B", "D", "d", "R", "r"):
            defined.add(parts[-1])
    # The shared closure's roots (the parent's CE references, e.g. ps2_cache_*, ps2_ctag_*) plus the C5 roots.
    shared = json.loads((CLOSURE_DIR / "result.json").read_text())["rooted_link"]["roots"]
    roots = [name for name in dict.fromkeys([*shared, *C5_ROOTS]) if name in defined]
    missing_roots = sorted(set(C5_ROOTS) - set(roots))
    (OUT / "rooted-c5-roots.txt").write_text("\n".join(f"{name} {'kept' if name in roots else 'absent'}"
                                                       for name in dict.fromkeys([*shared, *C5_ROOTS])) + "\n")
    rooted = OUT / "rooted-c5.o"
    run([str(linker), "-r", "--gc-sections", *[f"--wrap={name}" for name in C5_WRAPS],
         *[arg for name in roots for arg in ("-u", name)], *map(str, units), "-o", str(rooted)], env)
    if missing_roots:
        print("roots absent from the closure:", ", ".join(missing_roots))
    return rooted


def stage_platform(env: dict[str, str], rooted: Path) -> list[Path]:
    prefix = environment()[1]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    undefined = sorted({line.split()[-1] for line in run([str(nm), "-u", str(rooted)], env).splitlines()
                        if line.strip()})
    generated, missing = hcu_ps2_link.emit(undefined, set())
    platform_c = OUT / "ps2_platform_c5.c"
    platform_c.write_text(generated)
    (OUT / "ps2_platform_c5_missing.txt").write_text("\n".join(missing) + ("\n" if missing else ""))
    hcu = ROOT / "submodules/halo-ce-universal"
    # The include list of hcu_ps2_link.main (its flags), which the port units need (tag_files.h and friends).
    flags = [
        "-std=gnu89", "-Os", "-mabi=n32", "-G0", "-fms-extensions", "-fshort-wchar",
        "-fcommon", "-ffp-contract=off", "-fsigned-char", "-fwrapv", "-D_EE",
        "-D__STRICT_ANSI__", "-w", "-I" + str(hcu / "port/ps2/include"),
        "-I" + str(hcu / "source"), "-I" + str(hcu / "source/cseries"),
        "-I" + str(hcu / "source/cache"), "-I" + str(hcu / "source/tag_files"),
        "-I" + str(hcu / "source/memory"), "-I" + str(hcu / "source/math"),
        "-I" + str(hcu / "source/rasterizer"), "-I" + str(hcu / "source/render"),
        "-I" + str(hcu / "source/game"), "-I" + str(hcu / "source/sound"),
        "-I" + str(hcu / "port/include"), "-I" + str(hcu / "port/include/xdk"),
        "-I" + str(prefix / "ps2sdk/common/include"), "-I" + str(prefix / "ps2sdk/ee/include"),
        "-include", str(hcu / "port/ps2/include/halo_ps2_prefix.h"),
        "-include", str(CLOSURE_DIR / "halo_ps2_msvc_semantics.h"),
    ]
    objects = []
    for name in PORT_UNITS:
        source = hcu / "port/ps2/src" / name
        obj = OUT / (Path(name).stem + ".o")
        extra = ["-DHALO_PS2_NO_BOOTSTRAP_MEMORY"] if name == "ps2_memory.c" else []
        run([str(compiler), *flags, *extra, "-c", str(source), "-o", str(obj)], env)
        objects.append(obj)
    obj = OUT / "ps2_platform_c5.o"
    run([str(compiler), *flags, "-c", str(platform_c), "-o", str(obj)], env)
    objects.append(obj)
    return objects


GAMEPLAY_MAKE_VARS = [
    "WORLD_VIS_SOURCE=src/world/visibility.c", "WORLD_STREAM_DIAGNOSTIC=0", "WORLD_PLAY=0",
    "WORLD_HCU_LINK_PROBE=1", "WORLD_HCU_GAMEPLAY=1", "WORLD_HCU_ASSET_PROFILE=host",
    "WORLD_HCU_RENDER_CLEAR_TEST=0", "WORLD_HCU_ANIMATION_TRACE_TEST=0", "WORLD_HCU_M2_UI_LIFECYCLE_TEST=0",
    "WORLD_HCU_STEP8_MP_CAPACITY_DIAGNOSTIC=0", "WORLD_HCU_STEP8_MP_WORKLOAD_PLAYERS=2",
    "WORLD_HCU_TAG_CACHE_BYTES=2097152", "WORLD_HCU_PARTITION_PROFILE=",
    "WORLD_HCU_PROFILE_PACKAGE_ROOT=" + str(ROOT / "build/m2-c2-r3-selected-packages/pkg"),
    "WORLD_HCU_HEADLESS_RUNTIME_GUEST=0", "EE_OPTFLAGS=-Oz",
]
PARENT_OUT = OUT / "parent"
GUEST_ELF = OUT / "hcu-c5-guest.elf"
# The map the shell loads when HALO_PS2_C2_PRODUCTION_RUNTIME_GUEST is not defined: CE's solo map (source/main/main.c).
C5_BOOT_MAP = "b30"
# CE scenario path per boot map. b30 is CE's solo level (source/main/main.c scenario_paths); sidewinder is the
# multiplayer test path used by ps2_m2_ui_lifecycle_test.c. Selected by --boot-map.
BOOT_SCENARIO_PATHS = {
    "b30": "levels\\b30\\b30",
    "sidewinder": "levels\\test\\sidewinder\\sidewinder",
}
ROSTER = ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json"


def eligible_variants(map_name: str) -> list[dict]:
    """C1 roster actv variants of the map that the C5 lifecycle can drive: a combat variant with an actor, a bipd
    unit and no unresolved dependency, sorted by tag path."""
    roster = json.loads(ROSTER.read_text())
    eligible = [v for v in roster["variants"]
                if v.get("map") == map_name and v.get("group") == "actv" and v.get("disposition") == "combat"
                and v.get("actor") and (v.get("unit") or {}).get("group") == "bipd" and not v.get("unresolved")]
    return sorted(eligible, key=lambda v: v["path"])


def lifecycle_variant(map_name: str) -> tuple[str, int, str]:
    """The first eligible C1 roster actv variant for the map: (tag path, roster datum, roster path).

    Only the tag path is passed to the guest; the guest resolves the tag index at runtime with tag_loaded('actv', path)
    on the map that is loaded. The datum is recorded for the build log only. A map with no eligible variant gives an
    empty path: the guest then reports the lifecycle stages as variant-not-loaded instead of failing the build.
    """
    eligible = eligible_variants(map_name)
    if not eligible:
        return "", -1, ""
    first = eligible[0]
    return first["path"], first["datum"], first["path"]


def c_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_lifecycle_header(path: str) -> Path:
    """c5_lifecycle_variant.h, included by hcu_c5_boot.c: the lifecycle tag path, the boot map's path table for the
    map-load report (every eligible actv path and its bipd unit path), and the map's canonical scenario path."""
    directory = OUT / "variant"
    directory.mkdir(parents=True, exist_ok=True)
    eligible = eligible_variants(C5_BOOT_MAP)
    actv_paths = [v["path"] for v in eligible]
    unit_paths = sorted({v["unit"]["path"] for v in eligible})
    header = directory / "c5_lifecycle_variant.h"
    lines = ["/* generated by tools/c5_build.py from docs/reports/m2-c1-actor-roster-2026-10-23.json */",
             f'#define HCU_C5_BOOT_MAP "{C5_BOOT_MAP}"',
             f"#define HCU_C5_BOOT_MAP_PATH {c_string(BOOT_SCENARIO_PATHS[C5_BOOT_MAP])}",
             f'#define HCU_C5_LIFECYCLE_VARIANT_MAP "{C5_BOOT_MAP}"',
             f"#define HCU_C5_LIFECYCLE_VARIANT_PATH {c_string(path)}",
             f"#define HCU_C5_BOOT_SCENARIO_PATH {c_string(BOOT_SCENARIO_PATHS[C5_BOOT_MAP])}",
             "static const char *const hcu_c5_boot_actv_paths[] = {"]
    lines += [f"\t{c_string(p)}," for p in actv_paths]
    lines += ["\tNULL,", f"}};", f"#define HCU_C5_BOOT_ACTV_COUNT {len(actv_paths)}u",
              "static const char *const hcu_c5_boot_unit_paths[] = {"]
    lines += [f"\t{c_string(p)}," for p in unit_paths]
    lines += ["\tNULL,", f"}};", f"#define HCU_C5_BOOT_UNIT_COUNT {len(unit_paths)}u"]
    header.write_text("\n".join(lines) + "\n")
    return directory


def stage_parent(env: dict[str, str], map_capacity_diagnostic: bool = False) -> list[Path]:
    """Build the gameplay-variant parent objects (ee-world's gameplay set plus the C5 objects).

    map_capacity_diagnostic: measurement only. Applies HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC to hcu_map_service.o in
    this C5 build (tools/c5-world.mk). Off by default, so a C5 build without the flag keeps the normal admit list.
    """
    if PARENT_OUT.exists():
        for stale in PARENT_OUT.rglob("*.o"):
            stale.unlink()
    path, datum, _roster_path = lifecycle_variant(C5_BOOT_MAP)
    variant_dir = write_lifecycle_header(path)
    print(f"lifecycle variant: map={C5_BOOT_MAP} roster datum={datum} path={path or '(none eligible)'} "
          f"header={variant_dir}")
    boot_defines = f"C5_BOOT_DEFINES=-DHALO_PS2_SURVIVAL=1 -I{variant_dir}"
    diagnostic = ["C5_MAP_CAPACITY_DIAGNOSTIC=1"] if map_capacity_diagnostic else []
    print(f"map capacity diagnostic (measurement only): {bool(map_capacity_diagnostic)}")
    run(["make", "-B", "-f", "tools/c5-world.mk", f"WORLD_OUTPUT={PARENT_OUT}", *GAMEPLAY_MAKE_VARS,
         boot_defines, *diagnostic, "parent-objects"], env)
    objects = sorted(PARENT_OUT.rglob("*.o"))
    if not any(p.name == "hcu_c5_boot.o" for p in objects):
        raise RuntimeError("parent build produced no hcu_c5_boot.o")
    return objects


def stage_link(env: dict[str, str], parent_objects: list[Path]) -> Path:
    """Final R5900 link: parent objects, closure units (HCU's ps2 units and the C5 rooted object), gc, wrap."""
    prefix = environment()[1]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    linkfile = prefix / "ps2sdk/ee/startup/linkfile"
    # ps2_main.o is not linked: its main() would clash with the parent's hcu_main.o (as in hcu_parent_link_probe.py).
    closure_units = [OUT / f"{name}.o" for name in ("ps2_abi", "ps2_memory", "ps2_crt", "ps2_edge",
                                                  "ps2_sound_playback_bind")]
    closure_units += [OUT / "ps2_platform_c5.o", OUT / "rooted-c5.o"]
    missing = [str(p) for p in closure_units if not p.is_file()]
    if missing:
        raise RuntimeError("missing link inputs: " + ", ".join(missing))
    map_file = OUT / "hcu-c5-guest.map"
    run([str(compiler), "-mabi=n32", "-G0", "-T", str(linkfile),
         "-Wl,--gc-sections", "-Wl,--wrap,malloc", "-Wl,--wrap,free", "-Wl,--wrap,calloc", "-Wl,--wrap,realloc",
         "-Wl,--wrap,ps2_bots_update_actions", "-Wl,-u,halo_shell_main",
         "-Wl,-Map," + str(map_file), "-Wl,-zmax-page-size=128",
         "-L" + str(prefix / "ps2sdk/ee/lib"), "-o", str(GUEST_ELF),
         *map(str, parent_objects), *map(str, closure_units),
         "-ldraw", "-lgraph", "-lpacket2", "-ldma", "-ldebug", "-lpad", "-lmtap", "-lfileXio", "-lpatches", "-lm"],
        env)
    return GUEST_ELF


def main() -> None:
    global C5_BOOT_MAP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=("all", "closure", "rooted", "platform", "parent", "link"))
    parser.add_argument("--boot-map", default="b30", choices=sorted(BOOT_SCENARIO_PATHS),
                        help="map the C5 guest requests at boot (must match the staged --level of the runner)")
    parser.add_argument("--map-capacity-diagnostic", action="store_true",
                        help="measurement only: admit the HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC map list "
                             "in hcu_map_service.o for this build; never a qualification")
    args = parser.parse_args()
    C5_BOOT_MAP = args.boot_map
    OUT.mkdir(parents=True, exist_ok=True)
    _build, prefix, env, _jobs = environment()
    stages = ["closure", "rooted", "platform", "parent", "link"] if args.stage == "all" else [args.stage]
    print("stages:", stages, "closure dir:", CLOSURE_DIR)
    if "closure" in stages:
        stage_closure(env)
    rooted = OUT / "rooted-c5.o"
    if "rooted" in stages:
        rooted = stage_rooted(env)
    if "platform" in stages:
        stage_platform(env, rooted)
    if "parent" in stages:
        stage_parent(env, args.map_capacity_diagnostic)
    if "link" in stages:
        elf = stage_link(env, sorted(PARENT_OUT.rglob("*.o")))
        print("elf", elf, "sha256", sha256(elf))
    print("ok", stages)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"C5 build failed: {error}")
