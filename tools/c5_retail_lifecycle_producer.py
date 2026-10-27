#!/usr/bin/env python3
"""C5 retail lifecycle producer: drives real CE actor code for C1 retail recipes on the host.

For each eligible recipe of the C1 roster (docs/reports/m2-c1-actor-roster-2026-10-23.json) the
recipe's actor variant is passed to the real CE actor_place (source/ai/actors.c), which is the
call encounter_place_actor makes for a squad's actor palette entry (source/ai/encounters.c:3230).
actors.c, memory/data.c and src/stream/hcu_actor_metrics.c are compiled unchanged (ILP32, clang
-m32, the same prelude as tests/test_c4_live_pathfinding_real.py). Every other symbol the closure
needs is generated as a stub that prints "C5 blocked symbol=<name>" and exits 3, so the first
unavailable dependency on the path is recorded, not papered over.

Output: c5-retail-lifecycle-evidence-v1 JSON, consumed by tools/c5_retail_actor_lifecycle.py
(--evidence). Stage kind is "retail" only where the real CE code ran on the recipe's retail
data. A stage that could not run is "blocked" with its exact blocker. Recipes with any blocked
stage are recorded with record kind "blocked", which the ledger ignores (it gates on record kind).
Spartan bot counters are never sampled here: bots are reported as not-measured.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c5_retail_actor_lifecycle as c5  # noqa: E402

ROOT = c5.ROOT
HCU = ROOT / "submodules/halo-ce-universal"
SOURCE = HCU / "source"
PORT_HEADERS = (HCU / "port",)
HARNESS = ROOT / "tests/c5_retail_lifecycle_main.c"
HOST = ROOT / "tests/c5_retail_lifecycle_host.c"
METRICS = ROOT / "src/stream/hcu_actor_metrics.c"
PREFIX = ROOT / "tests/c5_lifecycle_prefix.h"
# The CE units the harness compiles whole. objects/widgets/flags.c and the others listed in
# CLOSURE_UNITS_FILE were each added because the harness reached a stub defined in them.
REAL_UNITS_BASE = (SOURCE / "ai/actors.c", SOURCE / "memory/data.c", SOURCE / "objects/objects.c",
                   SOURCE / "objects/damage.c", SOURCE / "objects/widgets/widgets.c",
                   SOURCE / "objects/object_types.c", SOURCE / "objects/object_lights.c",
                   SOURCE / "saved games/game_state.c", SOURCE / "memory/crc.c",
                   SOURCE / "game/game_time.c", METRICS)
CLOSURE_UNITS_FILE = ROOT / "tests/c5_closure_units.txt"


def closure_units() -> tuple[Path, ...]:
    lines = CLOSURE_UNITS_FILE.read_text().split() if CLOSURE_UNITS_FILE.is_file() else []
    return tuple(HCU / line for line in lines if line.strip())


REAL_UNITS = REAL_UNITS_BASE + closure_units()


# saved games/game_state_xbox.c is not compiled whole on the host (its file-system half needs the
# Win32 file API, which the PS2 build provides and the host does not): game_state_allocate_buffer
# and its globals are extracted verbatim instead (write_game_state_closure), compiled with HALO_PS2,
# the define the PS2 build gives this file: its buffer is the physical_memory arena, with no Xbox
# virtual mapping and no XPhysicalProtect.
PRELUDE = ["-std=gnu99", "-m32", "-fms-extensions", "-fshort-wchar", "-fwrapv",
           "-fno-strict-aliasing", "-w", "-include", str(ROOT / "tests/soundreq_host_prefix.h"),
           "-include", str(ROOT / "tests/c5_lifecycle_prefix.h")]
# the struct tag list is written per run by struct_tag_header() and added by build_harness()
EVIDENCE_FORMAT = c5.EVIDENCE_FORMAT
NONE = -1  # cseries.h
STRUCT_TAGS: Path | None = None
DEFAULT_OUT = ROOT / "docs/reports/c5-retail-lifecycle-evidence-2026-10-26.json"
# Stages the harness can observe today. activation, update and combat have no driver in the closure:
# actor_update is static (actors.c:4247) and runs only inside the game tick, and the damage path
# (actor_handle_damage, actors.c:1275) reads units through unit_get, which is not in the closure.
# attachment is reached inside actor_place (actor_create_for_unit -> actor_attach_unit, actors.c:2709).
UNDRIVEN_REASONS = {
    "activation": "not driven yet: the harness has no activation step; actor_set_active (actors.c:3599) is public and runs after placement",
    "update": "not driven yet: the harness has no update step; actors_update (actors.c:4290) is the public tick that calls the static actor_update (actors.c:4247)",
    "combat": "not driven yet: the harness has no damage step; actor_handle_damage (actors.c:1275) runs after placement and attachment",
}
TRACE = [
    "C1 roster unique_recipes[i]: variant (actv) -> actor (actr), unit (bipd), ranged_weapon (weap); source_map_sha256 pins the map.",
    "scenario tag: squad_definition.actor_palette_index selects scenario.ai_actor_palette; starting_location.actor_variant_index overrides it (source/ai/encounters.c:3149-3208, encounter_place_actor at :3128).",
    "encounter_place_actor: actor_palette_entry->index is the actor variant; major_upgrade_reference is checked; then actor_place(actor_palette_entry->index, encounter, squad, starting_location, upgrade_major, initial_variant) at encounters.c:3230.",
    "actor_place (source/ai/actors.c:2720): network_game_distributed_client() check; actor_variant_definition_get (tag_get, ACTOR_VARIANT_DEFINITION_TAG); object_placement_data_new + object_new places the bipd unit (actors.c ~2750-2766).",
    "actor_place: actor_customize_unit (actors.c:2818) then actor_create_for_unit (actors.c:2851) which calls actor_new (actors.c:2623).",
    "actor_new (actors.c:2251): actor_variant_definition_get and actor_definition_get (both tag_get), type check, datum_new(actor_data) (memory/data.c:305).",
    "actor_create_for_unit: actor_attach_unit (actors.c:2709) binds the actor datum to the unit. Attachment is not driven by the harness.",
    "Death: actor_kill(index, silent, delayed) (actors.c:3265). Cleanup: actor_delete(index, died) (actors.c:3129).",
]


def stderr_tail(text: str, lines: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def clang_path() -> str:
    cc = shutil.which("clang")
    if cc is None:
        raise c5.LifecycleError("clang -m32 is required for the host closure")
    return cc


def compile_obj(cc: str, source: Path, out: Path, includes: list[str], prelude: bool = True,
                extra: list[str] | None = None) -> None:
    flags = PRELUDE if prelude else ["-m32", "-w"]
    if prelude and STRUCT_TAGS is not None:
        flags = [*flags[:-2], "-include", str(STRUCT_TAGS), *flags[-2:]]
    flags = [*flags, *(extra or [])]
    result = subprocess.run([cc, *flags, *includes, "-c", str(source), "-o", str(out)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise c5.LifecycleError(f"compile {source.name} failed: {stderr_tail(result.stderr)}")


def struct_tag_header(work: Path) -> Path:
    """Forward declarations of every struct tag the closure's headers define (see c5_lifecycle_prefix.h)."""
    tags = set()
    for header in SOURCE.rglob("*.h"):
        for m in re.finditer(r"^struct\s+(\w+)\s*\n?\s*\{", header.read_text(errors="replace"), re.M):
            tags.add(m.group(1))
    out = work / "c5_struct_tags.h"
    out.write_text("".join(f"struct {tag};\n" for tag in sorted(tags)))
    return out


def include_dirs() -> list[str]:
    dirs = sorted(p for p in SOURCE.rglob("*") if p.is_dir())
    flags = [f"-I{ROOT / 'tests/c5_shim'}", f"-I{ROOT / 'tests/c4_shim'}", f"-I{HCU / 'port/ps2/include'}", f"-I{HCU / 'port/linux/game'}",
             f"-I{HCU / 'port/include'}", f"-I{HCU / 'port/include/xdk'}",
             f"-I{ROOT / 'submodules/halo-ps2/engine/src'}", f"-I{ROOT / 'src'}", f"-I{ROOT / 'tests'}"]
    return flags + [f"-I{d}" for d in dirs] + [f"-I{SOURCE}"]


def nm_undefined(path: Path) -> set[str]:
    out = subprocess.run(["nm", "-u", str(path)], capture_output=True, text=True).stdout
    return {line.split()[-1] for line in out.splitlines() if line.strip()}


def nm_defined(path: Path) -> set[str]:
    # external definitions only: a header's static inline function (real_math.h __inline) is local
    # to every unit that includes it, and cannot satisfy another unit's external reference
    out = subprocess.run(["nm", "--extern-only", "--defined-only", str(path)], capture_output=True,
                         text=True).stdout
    return {line.split()[-1] for line in out.splitlines() if line.strip()}


def libc_symbols(cc: str) -> set[str]:
    lib = subprocess.run([cc, "-m32", "-print-file-name=libc.so.6"], capture_output=True, text=True).stdout.strip()
    libm = subprocess.run([cc, "-m32", "-print-file-name=libm.so.6"], capture_output=True, text=True).stdout.strip()
    names: set[str] = set()
    for lib_path in (lib, libm):
        if Path(lib_path).is_file():
            out = subprocess.run(["nm", "-D", "--defined-only", lib_path], capture_output=True, text=True).stdout
            names |= {line.split()[-1].split("@")[0] for line in out.splitlines() if line.strip()}
    return names


def data_symbols(names: set[str]) -> set[str]:
    """Names declared as objects (extern T name; with no parameter list) in the submodule's headers."""
    text = "\n".join(p.read_text(errors="replace") for root in (SOURCE, *PORT_HEADERS)
                     for p in root.rglob("*.h"))
    found = set()
    for name in names:
        if re.search(r"extern\s+[^();]*\b" + re.escape(name) + r"\s*(\[[^\]]*\])?\s*;", text):
            found.add(name)
    return found


CACHE_SOURCE = SOURCE / "cache/cache_files.c"
CACHE_STRUCTS = ("cache_file_tag_instance", "cache_file_tag_header", "cache_file_header", "cache_file_globals")
CACHE_FUNCTIONS = ("cache_get_tag_instance", "cache_empty_tag_instance", "tag_get", "tag_get_group_tag",
                   "tag_iterator_new", "tag_iterator_next")
CACHE_GLOBALS = ("static struct cache_file_globals cache_file_globals = { 0 };",
                 "static long global_tag_count;",
                 "extern struct cache_file_tag_instance *global_tag_instances;",
                 "static struct cache_file_tag_instance *cache_get_tag_instance(long tag_index);",
                 "static struct cache_file_tag_instance *cache_empty_tag_instance(long tag_index);")
# The attach function is the one place this closure is written by hand: it does what cache_files.c
# does once a map's tag header is read (cache_files.c:1242), and nothing else. The map's header and
# tag region are read by tests/c5_retail_lifecycle_host.c at the Xbox tag base.
CACHE_ATTACH = """
struct cache_file_tag_instance *global_tag_instances;

void c5_cache_tags_attach(void *tag_header_address, long tag_count)
{
	cache_file_globals.tag_header = (struct cache_file_tag_header *)tag_header_address;
	global_tag_instances = cache_file_globals.tag_header->tag_instances;
	global_tag_count = tag_count;
	cache_file_globals.tags_loaded = TRUE;
}
"""


def extract_struct(source: str, name: str) -> str:
    """The verbatim 'struct NAME { ... };' definition (braces balanced)."""
    m = re.search(r"^struct " + re.escape(name) + r"\s*\n\{", source, re.M)
    if not m:
        raise c5.LifecycleError(f"struct {name} not found in cache_files.c")
    depth = 0
    for i in range(source.index("{", m.start()), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                end = source.index(";", i) + 1
                return source[m.start():end]
    raise c5.LifecycleError(f"struct {name} unterminated")


def extract_function(source: str, name: str) -> str:
    """The verbatim definition of a function (one match, braces balanced)."""
    # a definition starts at the first column (the prefix): calls inside bodies are indented
    pattern = re.compile(r"^[A-Za-z_][^;{}\n]*\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", re.M)
    found = list(pattern.finditer(source))
    if len(found) != 1:
        raise c5.LifecycleError(f"expected one definition of {name}, found {len(found)}")
    start = found[0].start()
    depth = 0
    for i in range(source.index("{", found[0].start()), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise c5.LifecycleError(f"{name} unterminated")


def write_cache_closure(work: Path) -> Path:
    """Verbatim CE tag accessors (cache/cache_files.c) for the loaded map's tag table."""
    text = CACHE_SOURCE.read_text(errors="replace")
    parts = ['/* generated by tools/c5_retail_lifecycle_producer.py from cache/cache_files.c: the tag',
             ' * accessors and their structures, verbatim. Only c5_cache_tags_attach is written here. */',
             '#include "cseries/cseries.h"', '#include "cseries/errors.h"', '#include "tag_files/tag_groups.h"',
             '#include "cache/cache_files.h"', '#include <stdio.h>', '']
    for name in CACHE_STRUCTS:
        parts.append(extract_struct(text, name) + "\n")
    parts.extend(CACHE_GLOBALS)
    for name in CACHE_FUNCTIONS:
        parts.append(extract_function(text, name) + "\n")
    parts.append(CACHE_ATTACH)
    out = work / "c5_cache_tag_closure.c"
    out.write_text("\n".join(parts))
    return out


GAME_STATE_SOURCE = SOURCE / "saved games/game_state_xbox.c"
GAME_STATE_GLOBALS = "static struct xbox_game_state_globals_prefix xbox_game_state_globals = { 0 };"


def write_game_state_closure(work: Path) -> Path:
    """game_state_allocate_buffer, game_state_create_or_open_file (game_state_xbox.c:155, :84) and the
    enum, structure and globals they use, verbatim. The Win32 file calls they make are declared
    here with their public Win32 values; the host definitions of those calls are in
    tests/c5_retail_lifecycle_host.c (the PS2 behaviour: no persistent image, see the source)."""
    text = GAME_STATE_SOURCE.read_text(errors="replace")
    if GAME_STATE_GLOBALS not in text:
        raise c5.LifecycleError("game_state_xbox.c globals changed: update the closure")
    enum = re.search(r"^enum\n\{\n\tCPU_PAGE_SIZE.*?\n\};", text, re.M | re.S)
    if enum is None:
        raise c5.LifecycleError("game_state_xbox.c enum not found")
    parts = ['/* generated by tools/c5_retail_lifecycle_producer.py from saved games/game_state_xbox.c:',
             ' * game_state_allocate_buffer and game_state_create_or_open_file, their enum, structure and',
             ' * globals, verbatim. The Win32 names are the public values; the calls are host definitions. */',
             '#include "cseries/cseries.h"', '#include "cseries/errors.h"', '#include "saved games/game_state.h"',
             '#include "cache/physical_memory_map.h"', '#include <stddef.h>', '',
             'typedef void *HANDLE;',
             '#define GENERIC_READ 0x80000000u', '#define GENERIC_WRITE 0x40000000u',
             '#define OPEN_ALWAYS 4', '#define FILE_FLAG_NO_BUFFERING 0x20000000u',
             '#define FILE_FLAG_SEQUENTIAL_SCAN 0x08000000u', '#define FILE_BEGIN 0',
             '#define INVALID_HANDLE_VALUE ((HANDLE)-1)', '#define INVALID_SET_FILE_POINTER 0xFFFFFFFFu',
             'HANDLE CreateFileA(const char *name, unsigned long access, unsigned long share, void *security,',
             '\tunsigned long disposition, unsigned long flags, HANDLE template_file);',
             'long SetFilePointer(HANDLE file, long distance, long *high, unsigned long method);',
             'long SetEndOfFile(HANDLE file);', 'long CloseHandle(HANDLE file);', 'unsigned long GetLastError(void);',
             '', enum.group(0), "", extract_struct(text, "xbox_game_state_globals_prefix"), "", GAME_STATE_GLOBALS, "",
             extract_function(text, "game_state_allocate_buffer"), "",
             extract_function(text, "game_state_create_or_open_file"), ""]
    out = work / "c5_game_state_closure.c"
    out.write_text("\n".join(parts))
    return out


CSERIES_SOURCE = SOURCE / "cseries/cseries.c"


def write_cseries_colour_closure(work: Path) -> Path:
    """The colour table and the global_real_argb_* / global_real_rgb_* pointers, verbatim from
    cseries/cseries.c (lines 170-227). cseries.c as a whole does not compile under this prelude (see
    host.c); these pointers are read by the object code (objects.c, object_placement_data_new reads
    *global_real_rgb_white), so a placeholder would make them null."""
    text = CSERIES_SOURCE.read_text(errors="replace")
    start = text.index("static const real_argb_color global_real_argb_color_table[17] =")
    end_marker = "const real_rgb_color *global_real_rgb_violet"
    end = text.index(end_marker)
    end = text.index("\n", end) + 1
    body = text[start:end]
    if body.count("global_real_rgb_white") != 1 or body.count("global_real_argb_violet") != 1:
        raise c5.LifecycleError("cseries.c colour globals changed: update the closure")
    head = ['/* generated by tools/c5_retail_lifecycle_producer.py from cseries/cseries.c lines 170-227:',
            ' * the colour table and its pointers, verbatim. */',
            '#include "cseries/cseries.h"', '#include "math/real_math.h"', '']
    out = work / "c5_cseries_colour_closure.c"
    out.write_text("\n".join(head) + "char temporary[256];\n" + body)
    return out


GAME_ENGINE_SOURCE = SOURCE / "game/game_engine.c"


def write_game_engine_closure(work: Path) -> Path:
    """game_engine_running (game/game_engine.c:4133) verbatim, with the game_engine global it reads.
    The global is declared here with its initial value from game_engine.c:920 (NULL: no game type is
    running). The rest of game_engine.c needs the whole game engine (halo UI, scoreboard), which this
    host closure does not compile; a placeholder would make the pointer non-null."""
    text = GAME_ENGINE_SOURCE.read_text(errors="replace")
    initial = "struct game_engine *game_engine = NULL;"
    if initial not in text:
        raise c5.LifecycleError("game_engine.c global changed: update the closure")
    parts = ['/* generated by tools/c5_retail_lifecycle_producer.py from game/game_engine.c:',
             ' * game_engine_running, verbatim, and the game_engine global (its initial value). */',
             '#include "cseries/cseries.h"', '#include "game/game_engine.h"', '',
             initial, "", extract_function(text, "game_engine_running"), ""]
    out = work / "c5_game_engine_closure.c"
    out.write_text("\n".join(parts))
    return out


PS2_TEXTURE_SOURCE = HCU / "port/ps2/src/ps2_sound_cache.c"


def write_port_answer_closure(work: Path) -> Path:
    """Port functions the closure calls, taken verbatim from the PS2 port (the answer the PS2 build
    gives on a machine without its texture hardware). _texture_cache_bitmap_get_hardware_format
    (port/ps2/src/ps2_sound_cache.c:77) returns the bitmap; the CE texture cache it replaces needs the
    Xbox Direct3D headers, which the host closure does not have."""
    text = PS2_TEXTURE_SOURCE.read_text(errors="replace")
    parts = ['/* generated by tools/c5_retail_lifecycle_producer.py from port/ps2/src/ps2_sound_cache.c:',
             ' * the PS2 port\'s answers for the texture cache query, verbatim. */',
             '#include "cseries/cseries.h"', '#include "cache/texture_cache.h"', '',
             extract_function(text, "_texture_cache_bitmap_get_hardware_format"), ""]
    out = work / "c5_port_answer_closure.c"
    out.write_text("\n".join(parts))
    return out


def build_harness(work: Path) -> tuple[Path, dict]:
    global STRUCT_TAGS
    cc = clang_path()
    STRUCT_TAGS = struct_tag_header(work)
    includes = include_dirs()
    objects = []
    for source in REAL_UNITS:
        obj = work / (source.stem + ".o")
        compile_obj(cc, source, obj, includes)
        objects.append(obj)
    cache_obj = work / "c5_cache_tag_closure.o"
    compile_obj(cc, write_cache_closure(work), cache_obj, includes)
    objects.append(cache_obj)
    port_obj = work / "c5_port_answer_closure.o"
    compile_obj(cc, write_port_answer_closure(work), port_obj, includes)
    objects.append(port_obj)
    engine_obj = work / "c5_game_engine_closure.o"
    compile_obj(cc, write_game_engine_closure(work), engine_obj, includes)
    objects.append(engine_obj)
    colour_obj = work / "c5_cseries_colour_closure.o"
    compile_obj(cc, write_cseries_colour_closure(work), colour_obj, includes)
    objects.append(colour_obj)
    game_state_obj = work / "c5_game_state_closure.o"
    compile_obj(cc, write_game_state_closure(work), game_state_obj, includes, extra=["-DHALO_PS2"])
    objects.append(game_state_obj)
    for source, name in ((HARNESS, "harness"), (HOST, "host")):
        obj = work / f"{name}.o"
        compile_obj(cc, source, obj, includes)
        objects.append(obj)

    defined = set().union(*(nm_defined(o) for o in objects))
    undefined = set().union(*(nm_undefined(o) for o in objects)) - defined
    libc = libc_symbols(cc)
    needed = sorted(s for s in undefined if s not in libc and not s.startswith("_GLOBAL") and s != "_GLOBAL_OFFSET_TABLE_")
    data = data_symbols(set(needed))
    functions = [s for s in needed if s not in data]

    stub_lines = [
        "/* generated by tools/c5_retail_lifecycle_producer.py: each stub is a blocker record */\n"
        "int printf(const char *format, ...);\nint fflush(void *stream);\nvoid exit(int code);\n",
        'static void c5_blocked(const char *name)\n{\n'
        '\tprintf("C5 blocked symbol=%s\\n", name);\n\tfflush(0);\n\texit(3);\n}\n',
    ]
    for name in functions:
        stub_lines.append(f'void {name}(void)\n{{\n\tc5_blocked("{name}");\n}}\n')
    for name in sorted(data):
        # Zero-filled placeholder of the object's extent, which the header does not give to the
        # host. A run that reads one is not evidence: placement is blocked before any use.
        stub_lines.append(f"unsigned char {name}[4096] __attribute__((aligned(16)));\n")
    stubs = work / "c5_blocked_stubs.c"
    stubs.write_text("\n".join(stub_lines))
    stub_obj = work / "c5_blocked_stubs.o"
    compile_obj(cc, stubs, stub_obj, [], prelude=False)
    exe = work / "c5_retail_lifecycle"
    link = subprocess.run([cc, "-m32", "-o", str(exe), *map(str, objects), str(stub_obj), "-lm"],
                          capture_output=True, text=True)
    if link.returncode != 0:
        raise c5.LifecycleError(f"link failed: {stderr_tail(link.stderr, 12)}")
    host = {
        "compiler": subprocess.run([cc, "--version"], capture_output=True, text=True).stdout.splitlines()[0],
        "real_units": [str(p.relative_to(ROOT)) for p in REAL_UNITS],
        "host_units": [str(HARNESS.relative_to(ROOT)), str(HOST.relative_to(ROOT))],
        "generated_from": [str(CACHE_SOURCE.relative_to(ROOT)) + " (CE tag_get, cache_get_tag_instance, cache_empty_tag_instance and their structures, verbatim)"],
        "blocked_function_stubs": len(functions),
        "placeholder_data_stubs": len(data),
        "host_defined_symbols": sorted(nm_defined(objects[-1])),
    }
    return exe, host


def run_recipe(exe: Path, variant_datum: int, map_path: Path) -> dict:
    index = variant_datum & 0xFFFF  # DATUM_INDEX_TO_ABSOLUTE_INDEX (cseries.h)
    try:
        run = subprocess.run([str(exe), str(index), str(map_path)], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"exit": None, "timeout": True, "lines": [], "stderr": ""}
    return {"exit": run.returncode, "timeout": False, "lines": run.stdout.splitlines(), "stderr": run.stderr}


def parse_run(run: dict) -> dict:
    """Stage results from the harness output. Blocked means the last opened stage never closed."""
    stages: dict[str, dict] = {}
    checks: dict[str, dict] = {}
    open_stage = None
    blocker = None
    metrics = None
    for line in run["lines"]:
        m = re.match(r"C5 begin stage=(\w+)", line)
        if m:
            open_stage = m.group(1)
            continue
        m = re.match(r"C5 end stage=(\w+) result=(-?\d+)", line)
        if m:
            name, result = m.group(1), int(m.group(2))
            stages[name] = {"executed": True, "result": result}
            open_stage = None
            continue
        m = re.match(r"C5 check stage=(\w+) ok=([01]) detail=(.*)", line)
        if m:
            checks[m.group(1)] = {"ok": m.group(2) == "1", "detail": m.group(3)}
            continue
        m = re.match(r"C5 blocked symbol=(\S+)", line)
        if m:
            blocker = m.group(1)
            continue
        m = re.match(r"C5 assert file=\S+ line=(\d+) expr=(.*)", line)
        if m:
            blocker = f"CE assertion failed at line {m.group(1)}: {m.group(2)}"
            continue
        m = re.match(r"C5 metrics retail_samples=(\d+) retail_peak=(\d+) retail_failures=(\d+) bot_samples=(\d+)", line)
        if m:
            metrics = {"retail_samples": int(m.group(1)), "retail_peak": int(m.group(2)),
                       "retail_failures": int(m.group(3)), "bot_samples": int(m.group(4))}
    return {"stages": stages, "checks": checks, "open_stage": open_stage, "blocker": blocker,
            "metrics": metrics}


def stage_rows(parsed: dict, run: dict) -> tuple[dict, str]:
    """One evidence entry per lifecycle stage. A stage is passed or failed only when the harness ran
    the CE call and printed an observable-state check for it (kind "retail"); otherwise it is blocked
    with the exact reason. The record kind is "retail" when at least one stage ran on retail data."""
    stages: dict[str, dict] = {}
    placement = parsed["stages"].get("placement")
    placed = placement is not None and placement["result"] != NONE
    for name in c5.STAGES:
        check = parsed["checks"].get(name)
        if name == "placement" and check is not None:
            ok = check["ok"]
            stages[name] = {"status": "passed" if ok else "failed", "kind": "retail",
                            "source": "actor_place (actors.c:2720): " + check["detail"]}
            if not ok:
                stages[name]["detail"] = check["detail"]
        elif name in ("death", "cleanup") and check is not None:
            ok = check["ok"]
            stages[name] = {"status": "passed" if ok else "failed", "kind": "retail",
                            "source": f"{name} call returned; {check['detail']}"}
        elif name == "attachment" and placed:
            stages[name] = blocked(name, parsed, run,
                                   reason="not checked: attachment runs inside actor_place (actors.c:2709) "
                                          "and the harness has no observable check of the unit link yet")
        elif name in parsed["stages"] and name in ("death", "cleanup"):
            stages[name] = blocked(name, parsed, run,
                                   reason=f"{name} call ran but no observable-state check is implemented")
        elif name in UNDRIVEN_REASONS:
            # an earlier stop is the reason the stage did not run; an undriven stage of a run that got
            # through setup and placement is recorded with its missing driver
            stages[name] = blocked(name, parsed, run,
                                   reason=None if parsed["blocker"] else UNDRIVEN_REASONS[name])
        else:
            reason = "not reached: placement did not produce an actor" if placement is not None and not placed else None
            stages[name] = blocked(name, parsed, run, reason=reason)
    kind = "retail" if any(s.get("kind") == "retail" for s in stages.values()) else "blocked"
    return stages, kind


def blocked(name: str, parsed: dict, run: dict, reason: str | None = None) -> dict:
    if reason is None:
        if parsed["blocker"] and parsed["open_stage"] == name:
            reason = f"stub reached: {parsed['blocker']} during the {name} stage"
        elif parsed["blocker"] and parsed["open_stage"]:
            reason = (f"not reached: the harness stopped at {parsed['blocker']} in the "
                      f"{parsed['open_stage']} stage before the {name} stage")
        elif parsed["blocker"]:
            reason = f"stub reached: {parsed['blocker']} before the {name} stage"
        elif run.get("no_map"):
            reason = "no source map on disk for this recipe"
        elif run["timeout"]:
            reason = "harness timed out"
        else:
            reason = f"harness exited {run['exit']} without a blocker record"
    return {"status": "blocked", "kind": "blocked", "source": "", "blocker": reason}


def source_map(recipe: dict, maps_dir: Path) -> Path | None:
    """The first of the recipe's source maps that is on disk (the roster's pinned alias)."""
    for alias in recipe.get("source_aliases", []):
        path = maps_dir / f"{alias}.map"
        if path.is_file():
            return path
    return None


def build_evidence(roster_path: Path, maps_dir: Path, out: Path | None, limit: int | None,
                   work: Path) -> dict:
    roster = json.loads(roster_path.read_text())
    recipes = c5.eligible_recipes(roster)
    if limit is not None:
        recipes = recipes[:limit]
    if not recipes:
        raise c5.LifecycleError("no eligible retail actor recipes in roster")
    problems = c5.check_pins(roster, recipes, maps_dir)
    if problems:
        raise c5.LifecycleError("; ".join(problems))
    roster_sha = c5.sha256_file(roster_path)
    exe, host = build_harness(work)

    records = []
    metric_totals = {"retail_samples": 0, "retail_peak": 0, "retail_failures": 0, "recipes_placed": 0}
    blockers: dict[str, int] = {}
    for recipe in recipes:
        variant = recipe["variant"]
        map_path = source_map(recipe, maps_dir)
        if map_path is None:
            run = {"exit": None, "timeout": False, "lines": [], "stderr": "",
                   "no_map": True}
        else:
            run = run_recipe(exe, variant["datum"], map_path)
        parsed = parse_run(run)
        stages, kind = stage_rows(parsed, run)
        for stage in stages.values():
            if stage["status"] == "blocked":
                blockers[stage["blocker"]] = blockers.get(stage["blocker"], 0) + 1
        if parsed["metrics"]:
            metric_totals["retail_samples"] += parsed["metrics"]["retail_samples"]
            metric_totals["retail_peak"] = max(metric_totals["retail_peak"], parsed["metrics"]["retail_peak"])
            metric_totals["retail_failures"] += parsed["metrics"]["retail_failures"]
        if stages["placement"]["status"] == "passed":
            metric_totals["recipes_placed"] += 1
        records.append({
            "variant": variant["path"],
            "variant_datum": variant["datum"],
            "absolute_index": variant["datum"] & 0xFFFF,
            "actor": recipe["actor"]["path"],
            "unit": recipe["unit"]["path"],
            "ranged_weapon": recipe["ranged_weapon"]["path"],
            "source_aliases": recipe.get("source_aliases", []),
            "kind": kind,
            "harness_exit": run["exit"],
            "stages": stages,
        })

    evidence = {
        "format": EVIDENCE_FORMAT,
        "producer": str(Path(__file__).resolve().relative_to(ROOT)),
        "generated": datetime.date.today().isoformat(),
        "roster": str(roster_path.relative_to(ROOT)) if roster_path.is_relative_to(ROOT) else str(roster_path),
        "roster_sha256": roster_sha,
        "host": host,
        "trace": TRACE,
        "records": records,
        "metrics": {
            "retail_actors": {
                "measured_by": "hcu_actor_metrics_sample_retail over actor_data->actual_count after actor_place",
                **metric_totals,
            },
            "spartan_bots": {
                "status": "not-measured",
                "reason": "the host harness drives no bot players; bot counters are never sampled here",
                "samples": 0,
            },
        },
        "blockers": dict(sorted(blockers.items(), key=lambda kv: (-kv[1], kv[0]))),
        "summary": {
            "recipes": len(records),
            "records_kind_retail": sum(1 for r in records if r["kind"] == "retail"),
            "records_kind_blocked": sum(1 for r in records if r["kind"] == "blocked"),
            "stages_passed": sum(1 for r in records for s in r["stages"].values() if s["status"] == "passed"),
            "stages_failed": sum(1 for r in records for s in r["stages"].values() if s["status"] == "failed"),
            "stages_blocked": sum(1 for r in records for s in r["stages"].values() if s["status"] == "blocked"),
        },
    }
    return evidence


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--roster", type=Path, default=c5.DEFAULT_ROSTER)
    ap.add_argument("--maps-dir", type=Path, default=c5.DEFAULT_MAPS)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--work", type=Path, default=None, help="build directory (default: a temporary one)")
    args = ap.parse_args(argv)
    try:
        if args.work is None:
            with tempfile.TemporaryDirectory(prefix="c5-lifecycle-") as tmp:
                evidence = build_evidence(args.roster, args.maps_dir, args.output, args.limit, Path(tmp))
        else:
            args.work.mkdir(parents=True, exist_ok=True)
            evidence = build_evidence(args.roster, args.maps_dir, args.output, args.limit, args.work)
    except (c5.LifecycleError, OSError, json.JSONDecodeError) as exc:
        print(f"c5 lifecycle producer refused: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
