#!/usr/bin/env python3
"""Enumerate allocation API callsites in the current HCU PS2 source closure.

This is a source inventory, not a dynamic trace or a proof that each site is
reachable after map load. It follows the PS2 port manifest's source selection,
then adds the parent HCU stream integration and the PS2 arena implementation.
The emitted records preserve literal callsite path/line/API so a reviewer can
classify the site against exact production behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MANIFEST = HCU / "port/ps2/port.json"
BASELINE = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory"
CALL = re.compile(
    r"\b(" + "|".join(map(re.escape, (
        "match_malloc", "match_realloc", "match_free",
        "debug_malloc", "debug_realloc", "debug_free",
        "game_state_malloc", "game_state_realloc", "game_state_free",
        "game_state_memory_pool_new", "memory_pool_new", "memory_pool_delete",
        "memory_pool_block_allocate", "memory_pool_block_reallocate", "memory_pool_block_free",
        "stack_memory_pool_allocate", "stack_memory_pool_free",
        "malloc", "calloc", "realloc", "free",
        "GlobalAlloc", "GlobalReAlloc", "GlobalFree",
        "system_malloc", "system_calloc", "system_realloc", "system_free",
        "arena_alloc", "arena_sub", "arena_release", "arena_reset",
    ))) + r")\s*\("
)


def mask_noncode(text: str) -> str:
    """Blank comments and literals while preserving offsets/newlines."""
    out = list(text)
    i = 0
    state = "code"
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "line"
                continue
            if ch == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                i += 2
                state = "block"
                continue
            if ch == '"':
                out[i] = " "
                state = "string"
            elif ch == "'":
                out[i] = " "
                state = "char"
        elif state == "line":
            if ch == "\n":
                state = "code"
            else:
                out[i] = " "
        elif state == "block":
            if ch == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "code"
                continue
            if ch != "\n":
                out[i] = " "
        else:
            if ch == "\\" and i + 1 < len(text):
                out[i] = " "
                if text[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if (state == "string" and ch == '"') or (state == "char" and ch == "'"):
                out[i] = " "
                state = "code"
            elif ch != "\n":
                out[i] = " "
        i += 1
    return "".join(out)


def source_set() -> list[Path]:
    manifest = json.loads(MANIFEST.read_text())
    exclude_dirs = tuple(manifest["exclude_dirs"])
    excluded = set(manifest["exclude_sources"])
    chosen = []
    for path in sorted((HCU / "source").rglob("*.c")):
        rel = path.relative_to(HCU).as_posix()
        if rel not in excluded and not rel.startswith(exclude_dirs):
            chosen.append(path)
    for rel in manifest["port_sources"]:
        path = HCU / rel
        if path.exists():
            chosen.append(path)
    for rel in manifest["extra_game_sources"]:
        path = HCU / rel
        if path.exists():
            chosen.append(path)
    # Parent integration and its generic fixed-arena implementation.
    chosen.extend((ROOT / "src/stream").glob("*.c"))
    chosen.append(ROOT / "submodules/halo-ps2/engine/src/core/mem.c")
    # Match CE's source selection (not just its live link sections). This test
    # helper is an opt-in probe object and is explicitly not production code.
    chosen = [p for p in chosen if p.name != "ps2_m2_ui_lifecycle_test.c"]
    return sorted(set(p for p in chosen if p.is_file()))


def owner(api: str) -> str:
    if api.startswith("arena_"):
        return "parent fixed arena"
    if api in {"memory_pool_new", "game_state_memory_pool_new", "memory_pool_delete",
               "memory_pool_block_allocate", "memory_pool_block_reallocate", "memory_pool_block_free"}:
        return "CE object/game-state pool"
    if api.startswith("game_state_"):
        return "CE game-state CPU region"
    if api.startswith("stack_memory_pool_"):
        return "CE stack memory pool"
    if api.startswith("system_") or api in {"malloc", "calloc", "realloc", "free",
                                              "GlobalAlloc", "GlobalReAlloc", "GlobalFree"}:
        return "PS2 compatibility heap / CE system wrapper"
    if api.startswith("debug_") or api.startswith("match_"):
        return "CE debug heap (routes to system wrapper)"
    return "unclassified"


def free_semantics(api: str) -> str:
    if api in {"free", "system_free", "debug_free", "match_free", "GlobalFree",
               "game_state_free", "memory_pool_delete", "memory_pool_block_free",
               "stack_memory_pool_free", "arena_release", "arena_reset"}:
        return "release/rewind API; exact owner lifetime depends on caller"
    if api in {"realloc", "system_realloc", "debug_realloc", "match_realloc",
               "GlobalReAlloc", "memory_pool_block_reallocate"}:
        return "resize; success/failure and old-block semantics are API-specific"
    if api in {"arena_alloc", "arena_sub", "game_state_malloc", "game_state_memory_pool_new",
               "memory_pool_new", "stack_memory_pool_allocate"}:
        return "bulk owner teardown/rewind or paired pool release; callsite pairing unresolved"
    return "allocation/free pair unresolved from this call expression"


PHASE_LOAD = re.compile(
    r"(init|load|mount|bind|startup|setup|create|build|open|preflight|boot|new$|_new|reset|layout|"
    r"scenario|map_|dispose|unload|tag_load|construct|prepare|allocate_|reserve)", re.I)
PHASE_RECURRENT = re.compile(
    r"(update|tick|frame|render|draw|spawn|wave|bot|mode|step|process|simulate|sample|AI|ai_|effect|"
    r"decal|projectile|hud|interface|sound|object|unit|weapon|player|cache|lru|hash|search|locate|add|"
    r"remove|event)", re.I)
FUNC_DEF = re.compile(r"^[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\([^;]*$")
NOT_FUNCTIONS = {"if", "for", "while", "switch", "return", "sizeof"}
_LINE_CACHE: dict[str, list[str]] = {}


def enclosing_function(path: str, line: int) -> str | None:
    """Name of the function whose brace depth encloses `line` (heuristic)."""
    if path not in _LINE_CACHE:
        _LINE_CACHE[path] = mask_noncode((ROOT / path).read_text(errors="replace")).splitlines()
    name, depth = None, 0
    for text in _LINE_CACHE[path][:line]:
        match = FUNC_DEF.match(text)
        candidate = match.group(1) if match and match.group(1) not in NOT_FUNCTIONS and not text.rstrip().endswith(";") else None
        if depth == 0 and candidate:
            name = candidate
        depth += text.count("{") - text.count("}")
    return name if depth > 0 else None


def classify_phase(function: str | None, path: str) -> tuple[str, str]:
    """Label a site from its enclosing function name. Source-only, not a trace."""
    if function and PHASE_LOAD.search(function):
        return "load-or-init", "static-name-heuristic (enclosing function name)"
    if (function and PHASE_RECURRENT.search(function)) or PHASE_RECURRENT.search(path):
        return "post-load-candidate", "static-name-heuristic (enclosing function and path)"
    return "unknown", "no name heuristic matched"


# Verdicts for the post-load-candidate and unknown sites, keyed by (path, enclosing
# function, API). Keys are function-level so a source edit that moves a line does not
# unmatch a verdict; every callsite of the same function and API shares the verdict.
# Each basis cites the caller chain or symbol evidence used. Verdict vocabulary:
#   load-only                  startup, map-start or save-load boundary chain proven from source
#   unreachable-selected-build no caller in the selected source tree, or no symbol in the baseline link map
#   recurrent-open             reachable from gameplay, console or cheat paths; not yet moved to scoped storage
#   cross-lane-open            file outside the lane; verdict recorded from read-only analysis
#   unknown-open               caller chain not fully traced
#   bounded-after-binding      bounded once the PS2 compatibility arena is bound (C2.5 r6/alloc-a)
#   bounded-in-pool           bounded by a fixed pool (C2.5 r6/alloc-a)
#   unverified                 no verdict recorded (the default for any unmatched site)
# A bounded-* verdict closes a site only when its basis cites a counter-backed bound
# (COUNTER_BASIS): a bound argued from the code alone stays open. Every other verdict
# other than load-only and unreachable-selected-build is open.
# Verdicts from docs/reports/m2-c2-r6-alloc-a-verdicts.json (another lane) are merged on top.
CLOSED_VERDICTS = ("load-only", "unreachable-selected-build")
BOUNDED_VERDICTS = ("bounded-after-binding", "bounded-in-pool")
OPEN_VERDICTS = ("recurrent-open", "unknown-open", "cross-lane-open", "bounded-after-binding",
                 "bounded-in-pool", "unverified-open", "unverified")
COUNTER_BASIS = re.compile(
    r"\b(counters?|sdk_\w+|refused_\w+|used_after_drain|\w+_fallbacks?|\w+_failures?|\w+_counter)\b")
ALLOC_A_VERDICTS = ROOT / "docs/reports/m2-c2-r6-alloc-a-verdicts.json"
OBJ_PATH = "submodules/halo-ce-universal/source/objects/objects.c"
# Shared basis texts. A bounded basis closes a site only when it cites a counter (COUNTER_BASIS).
OBJECT_POOL_BASIS = (
    "object_memory_pool is a fixed memory_pool (game_state_memory_pool_new in objects_initialize, "
    "OBJECT_MEMORY_POOL_SIZE) that never calls the SDK heap: exhaustion returns FALSE. Each header "
    "change is followed by object_pool_counters_note (objects.c), which pushes the pool's used, "
    "high-water, allocation-failure and reset counters to halo_ps2_owner_counters as "
    "HALO_PS2_OWNER_OBJECT_POOL. Refused reallocates are the pool's reallocation_failures counter, "
    "which that push does not forward yet (cross-lane: objects.c object_pool_counters_note)")
REVERT_BASIS = (
    "game_state_read_from_file (game_state_xbox.c) refuses on PS2 whenever game_engine_running() "
    "(game_state_port_revert_refusals, game_state_port_revert_refusal_count) before the malloc; the "
    "image is freed before return. Its only caller is game_state_revert (game_state.c:391), reached from "
    "checkpoint revert (main.c:2070, :2090), cinematic skip (main.c:2113), the lost-map respawn (main.c:2266, "
    "armed only without a game engine, players.c:5136) and save-and-quit (game_state.c:421). The read runs "
    "only with no game engine, "
    "which is the campaign; the C2 selected profiles are UI, multiplayer bot and survival profiles. "
    "Residual: the survival variant's game engine index is not traced in this lane, so a survival game "
    "whose engine index is 0 would reach the read")
CS_WRAPPER_BASIS = {
    "GlobalAlloc": (
        "CE system allocator wrapper (cseries_windows.c, in the PS2 closure). GlobalAlloc (ps2_memory.c:479) "
        "-> __wrap_malloc (ps2_memory.c:481): the fixed compat arena after binding, with no SDK heap. "
        "Counters: refused_unbound, sdk_malloc_preactivation (physical_memory_get_malloc_fallback_counters) "
        "and malloc_high_water (physical_memory_get_malloc_diagnostics)"),
    "GlobalReAlloc": (
        "CE system allocator wrapper (cseries_windows.c, in the PS2 closure). GlobalReAlloc (ps2_memory.c:696) "
        "copies only the live extent into the fixed compat arena and refuses rather than using the SDK heap. "
        "Counters: refused_unbound, sdk_realloc (physical_memory_get_malloc_fallback_counters) and "
        "malloc_high_water (physical_memory_get_malloc_diagnostics)"),
}

VERDICTS = {
    ("src/stream/hcu_main.c", "main", "arena_alloc"): (
        "load-only",
        "main() (src/stream/hcu_main.c:554) runs once at boot. Its arena_alloc sites at :657/:660 (opt-in M2 animation trace, resident gameplay) and :751-758 (snapshot, renderer workspace and DMA spans) run before halo_shell_main() (:881), and no loop in main() repeats them; the shell and frame loop start only inside halo_shell_main"),
    ("src/stream/hcu_main.c", "hcu_register_selected_runtime", "arena_alloc"): (
        "load-only",
        "hcu_register_selected_runtime (src/stream/hcu_main.c:329) is called once from main() (:1012), before halo_shell_main() (:1073). Its arena_alloc sites (:356-358, the generated image header path) allocate the image metadata, relocation and stream scratch spans at boot, and the function returns nothing to a loop"),
    ("src/stream/hcu_map_service.c", "feed_ctag_first_pass", "arena_alloc"): (
        "load-only",
        "map-load preflight, rewound before return: hcu_map_service_preflight (hcu_map_service.c:908) -> preflight_ctag_stream (:232) -> visit_section -> feed_ctag_first_pass (:171; relocation buffer at :195). preflight_ctag_stream rewinds its owner at :266 and hcu_map_service_preflight rewinds map_arena at :1062. Reached only from map_preflight (:772, the CE map preflight hook) and the map loader (:600, :716)"),
    ("src/stream/hcu_map_service.c", "verify_source_hash", "arena_alloc"): (
        "load-only",
        "hcu_map_service_preflight (hcu_map_service.c:825) -> verify_source_hash (hcu_map_service.c:965)"),
    ("src/stream/hcu_map_service.c", "verify_source_hash", "arena_release"): (
        "load-only",
        "hcu_map_service_preflight (hcu_map_service.c:825) -> verify_source_hash (hcu_map_service.c:965)"),
    ("submodules/halo-ce-universal/source/cseries/cseries_windows.c", "system_calloc", "GlobalAlloc"): (
        "bounded-after-binding",
        CS_WRAPPER_BASIS["GlobalAlloc"]),
    ("submodules/halo-ce-universal/source/cseries/cseries_windows.c", "system_malloc", "GlobalAlloc"): (
        "bounded-after-binding",
        CS_WRAPPER_BASIS["GlobalAlloc"]),
    ("submodules/halo-ce-universal/source/cseries/cseries_windows.c", "system_realloc", "GlobalAlloc"): (
        "bounded-after-binding",
        CS_WRAPPER_BASIS["GlobalAlloc"]),
    ("submodules/halo-ce-universal/source/cseries/cseries_windows.c", "system_realloc", "GlobalReAlloc"): (
        "bounded-after-binding",
        CS_WRAPPER_BASIS["GlobalReAlloc"]),
    ("submodules/halo-ce-universal/source/cseries/debug_memory.c", "debug_free", "system_free"): (
        "recurrent-open",
        "CE debug heap wrapper: system_free -> PS2 __wrap_free (ps2_memory.c:503), compat arena; debug_free callers not traced; not moved"),
    ("submodules/halo-ce-universal/source/cseries/debug_memory.c", "debug_malloc", "system_malloc"): (
        "recurrent-open",
        "CE debug heap wrapper: system_malloc (cseries_windows.c:179) -> PS2 __wrap_malloc (ps2_memory.c:373), which refuses rather than using the SDK heap once bound; SDK heap only before binding (sdk_malloc_preactivation_calls); debug_malloc callers not traced; not moved"),
    ("submodules/halo-ce-universal/source/cseries/debug_memory.c", "debug_realloc", "system_realloc"): (
        "recurrent-open",
        "CE debug heap wrapper: system_realloc -> PS2 __wrap_realloc (ps2_memory.c:605), compat arena with copy; sdk_realloc_fallbacks counts pre-binding blocks; debug_realloc callers not traced; not moved"),
    ("submodules/halo-ce-universal/source/hs/hs_compile.c", "hs_compile_add_source", "match_malloc"): (
        "unreachable-selected-build",
        "hs_compile_add_source (hs_compile.c) <- hs_compile <- hs_compile_and_evaluate (hs.c). Its callers: console_process_command (console.c:239), reached only from console_update, which opens on the backquote key read from keystrokes; keystrokes come only from keyboard_handle (input_xbox.c), which PS2 never opens (port/ps2/src/ps2_input.c valid_device_type refuses the keyboard); console_startup (console.c:425) reads lines into a 200-byte buffer, below the 0x400 scratch limit; cheats.c calls are compiled out on PS2 (CHEATS_DEBUG_STUB); telnet_console.c is excluded (port/ps2/port.json exclude_dirs source/networking). Scenario compiles are load-only (hs_compile_initialize(TRUE))"),
    ("submodules/halo-ce-universal/source/hs/hs_compile.c", "hs_compile_add_source", "match_realloc"): (
        "unreachable-selected-build",
        "hs_compile_add_source (hs_compile.c); same caller chain as the match_malloc row (console keyboard gate, 200-byte startup buffer, cheats compiled out on PS2, telnet excluded); scenario compiles load-only"),
    ("submodules/halo-ce-universal/source/math/geometry.c", "subdivide_triangle", "match_free"): (
        "load-only",
        "shell_initialize (source/shell/shell.c:54) -> real_math_initialize -> random_math_initialize (source/math/random_math.c:170) -> geosphere_new -> geosphere_new (geometry.c:316) -> subdivide_triangle"),
    ("submodules/halo-ce-universal/source/math/geometry.c", "subdivide_triangle", "match_malloc"): (
        "load-only",
        "shell_initialize (source/shell/shell.c:54) -> real_math_initialize -> random_math_initialize (source/math/random_math.c:170) -> geosphere_new -> geosphere_new (geometry.c:316) -> subdivide_triangle"),
    ("submodules/halo-ce-universal/source/memory/array.c", "dynamic_array_add_element", "debug_realloc"): (
        "unreachable-selected-build",
        "dynamic_array_add_element callers: math/vector_tree.c:89 and tool/connected_geometry.c (excluded); vector_tree_new/insert have no caller outside vector_tree.c in the selected tree"),
    ("submodules/halo-ce-universal/source/memory/array.c", "dynamic_array_delete", "debug_realloc"): (
        "unreachable-selected-build",
        "dynamic_array_delete only callers are hashtable.c:129/308; hashtable_put has no caller in the selected tree"),
    ("submodules/halo-ce-universal/source/memory/array.c", "dynamic_array_delete_element", "debug_realloc"): (
        "unreachable-selected-build",
        "dynamic_array_delete_element has no caller in the selected tree (definition only)"),
    ("submodules/halo-ce-universal/source/memory/array.c", "dynamic_array_resize", "debug_realloc"): (
        "unreachable-selected-build",
        "dynamic_array_resize only caller is hashtable_grow (hashtable.c:281); hashtable_put has no caller in the selected tree"),
    ("submodules/halo-ce-universal/source/memory/circular_queue.c", "circular_queue_delete", "match_free"): (
        "unreachable-selected-build",
        "circular_queue_delete callers are only in source/networking (excluded by port.json exclude_dirs)"),
    ("submodules/halo-ce-universal/source/memory/data.c", "data_compact", "match_free"): (
        "unreachable-selected-build",
        "data_compact has no caller in the selected tree (definition only); data.c outside C2.5 ownership"),
    ("submodules/halo-ce-universal/source/memory/data.c", "data_compact", "match_malloc"): (
        "unreachable-selected-build",
        "data_compact has no caller in the selected tree (definition only); data.c outside C2.5 ownership"),
    ("submodules/halo-ce-universal/source/memory/hashtable.c", "hashtable_delete", "match_free"): (
        "unreachable-selected-build",
        "hashtable_new/hashtable_put have no caller outside hashtable.c/.h in the selected tree"),
    ("submodules/halo-ce-universal/source/memory/hashtable.c", "hashtable_grow", "match_free"): (
        "unreachable-selected-build",
        "hashtable_grow reached only from hashtable_put, which has no caller in the selected tree"),
    ("submodules/halo-ce-universal/source/memory/hashtable.c", "hashtable_grow", "match_malloc"): (
        "unreachable-selected-build",
        "hashtable_grow reached only from hashtable_put, which has no caller in the selected tree"),
    ("submodules/halo-ce-universal/source/memory/lruv_cache.c", "lruv_delete", "match_free"): (
        "unreachable-selected-build",
        "lruv_delete has no caller in source/ (only a typedef and member name); unreachable in the selected tree"),
    ("submodules/halo-ce-universal/source/memory/memory_pool.c", "memory_pool_block_reallocate", "memory_pool_block_allocate"): (
        "recurrent-open",
        "memory_pool_block_reallocate <- object_header_block_allocate (objects.c:806) <- object_new (objects.c:3711, gameplay object spawn); bounded: block grows inside the pool (memory_pool.c:251-292) and returns FALSE on exhaustion, no SDK heap"),
    ("submodules/halo-ce-universal/source/memory/memory_pool.c", "memory_pool_block_reallocate", "memory_pool_block_free"): (
        "recurrent-open",
        "memory_pool_block_reallocate <- object_header_block_allocate (objects.c:806) <- object_new (objects.c:3711, gameplay object spawn); bounded: block grows inside the pool (memory_pool.c:251-292) and returns FALSE on exhaustion, no SDK heap"),
    ("submodules/halo-ce-universal/source/memory/memory_pool.c", "memory_pool_delete", "match_free"): (
        "unreachable-selected-build",
        "memory_pool_delete has no caller outside memory_pool.c/.h; symbol absent from baseline map"),
    ("submodules/halo-ce-universal/source/memory/stack_memory_pool.c", "stack_memory_pool_resize_block", "stack_memory_pool_allocate"): (
        "bounded-in-pool",
        "UI widget pool only: pool_resize_pointer (stack_memory_pool.c:549) from ui_widget.c:1924, :5120 and :5244. The pool is widget_memory_pool (ui_widget.c:1504), a fixed WIDGET_MEMORY_POOL_SIZE block (ui_widget.c:689, 0x40000 bytes) allocated once by ui_widgets_initialize (ui_widget.c:2170) and reset by stack_memory_pool_reset. Exhaustion returns NULL with no SDK heap; the high-water counters maximum_bytes_used and maximum_block_count_used are kept in the pool (stack_memory_pool.c:402-410, counter updates)"),
    ("submodules/halo-ce-universal/source/memory/texture_page.c", "texture_page_delete", "match_free"): (
        "unreachable-selected-build",
        "texture_page_delete only caller bitmaps/bitmap_extract.c, excluded by port.json exclude_sources; symbol absent from baseline map"),
    ("submodules/halo-ce-universal/source/memory/zlib/gzio.c", "", "free"): (
        "unreachable-selected-build",
        "gzclose symbol absent from the stale baseline link map"),
    ("submodules/halo-ce-universal/source/memory/zlib/zutil.c", "zcalloc", "debug_malloc"): (
        "unreachable-selected-build",
        "zcalloc symbol absent from the stale baseline link map"),
    ("submodules/halo-ce-universal/source/memory/zlib/zutil.c", "zcfree", "debug_free"): (
        "unreachable-selected-build",
        "zcfree symbol absent from the stale baseline link map"),
    ("submodules/halo-ce-universal/source/objects/objects.c", "object_header_block_allocate", "memory_pool_block_reallocate"): (
        "bounded-in-pool",
        OBJECT_POOL_BASIS),
    ("submodules/halo-ce-universal/source/objects/objects.c", "object_header_delete", "memory_pool_block_free"): (
        "bounded-in-pool",
        OBJECT_POOL_BASIS),
    ("submodules/halo-ce-universal/source/objects/objects.c", "object_name_list_allocate", "game_state_malloc"): (
        "load-only",
        "objects_initialize (objects.c:1113) -> object_name_list_allocate (objects.c:1146) <- game_initialize (game.c:299, startup)"),
    ("submodules/halo-ce-universal/source/saved games/game_state_xbox.c", "game_state_read_core", "free"): (
        "unreachable-selected-build",
        "game_state_read_core (game_state_xbox.c:421) <- game_state_load_core (game_state.c:1086) <- main_load_core_private (main.c:2287). The flag setters are the core_load* built-ins, refused and counted on PS2 (hs.c hs_port_core_load_refusals); the core files live on the d: drive, which PS2 does not have"),
    ("submodules/halo-ce-universal/source/saved games/game_state_xbox.c", "game_state_read_core", "malloc"): (
        "unreachable-selected-build",
        "game_state_read_core (game_state_xbox.c:421) <- game_state_load_core (game_state.c:1086) <- main_load_core_private (main.c:2287, on main_globals.load_core). That flag is set only by main_load_core, _at_startup, _name and _name_at_startup (main.c:1042-1072), whose only callers are the core_load* script built-ins (hs.c main_load_core_*_evaluate). On PS2 those built-ins are refused and counted (hs.c hs_port_core_load_refusals), so no core image is read in the selected build"),
    ("submodules/halo-ce-universal/source/saved games/game_state_xbox.c", "game_state_read_from_file", "free"): (
        "unreachable-selected-build",
        REVERT_BASIS),
    ("submodules/halo-ce-universal/source/saved games/game_state_xbox.c", "game_state_read_from_file", "malloc"): (
        "unreachable-selected-build",
        REVERT_BASIS),
    ("submodules/halo-ce-universal/source/saved games/game_state_xbox.c", "game_state_read_from_persistent_storage", "free"): (
        "load-only",
        "game_state_read_from_persistent_storage (game_state_xbox.c:681) <- game_state_try_and_load_from_persistent_storage (game_state.c:1057) <- main_new_map (main.c:1480, call at :1518): runs at map start, freed before return"),
    ("submodules/halo-ce-universal/source/saved games/game_state_xbox.c", "game_state_read_from_persistent_storage", "malloc"): (
        "load-only",
        "game_state_read_from_persistent_storage (game_state_xbox.c:681) <- game_state_try_and_load_from_persistent_storage (game_state.c:1057) <- main_new_map (main.c:1480, call at :1518): runs at map start, freed before return"),
    ("submodules/halo-ce-universal/source/tag_files/files.c", "datastore_read", "match_free"): (
        "unreachable-selected-build",
        "datastore_read (files.c:313) has no caller in the selected tree (hs/hs.c has no datastore call)"),
    ("submodules/halo-ce-universal/source/tag_files/files.c", "datastore_write", "match_free"): (
        "unreachable-selected-build",
        "datastore_write (files.c:381) has no caller in the selected tree"),
    ("submodules/halo-ce-universal/source/tag_files/files.c", "datastore_write", "match_malloc"): (
        "unreachable-selected-build",
        "datastore_write (files.c:381) has no caller in the selected tree"),
    ("submodules/halo-ce-universal/source/tag_files/files.c", "file_read_into_memory", "match_free"): (
        "unreachable-selected-build",
        "file_read_into_memory (files.c:70) <- hs_rebuild_source_file (hs.c) <- hs_rebuild_source; setters refused on PS2 (see the match_malloc row: script_recompile counted in hs_port_recompile_refusals; hs_recompile and hs_hack have no callers)"),
    ("submodules/halo-ce-universal/source/tag_files/files.c", "file_read_into_memory", "match_malloc"): (
        "unreachable-selected-build",
        "file_read_into_memory (files.c:70) <- hs_rebuild_source_file (hs.c) <- hs_rebuild_source, which runs only when hs_recompile_pending is set (hs.c hs_compile_and_evaluate_command, after hs_recompile_evaluate). Setters: script_recompile (hs_recompile_evaluate, refused and counted on PS2 by hs_port_recompile_refusals), hs_recompile() (no callers in source/ or port/ps2) and hs_hack (no callers). Unreachable in the selected build"),
    ("submodules/halo-ps2/engine/src/core/mem.c", "arena_sub_aligned", "arena_alloc"): (
        "unreachable-selected-build",
        "arena_sub_aligned's only caller is arena_sub (mem.c), and arena_sub has no caller in the selected tree: its other references are the declaration in mem.h, and no file in src/, the halo-ps2 engine sources or the CE source and port trees calls it"),
}

# The alloc-final lane's verdicts. They are applied after the alloc-a file, and replace every row of their
# function (any api), because the alloc-a rows for these functions carry no counter or caller evidence.
FINAL_VERDICTS = {
    (OBJ_PATH, "object_header_delete", "memory_pool_block_free"): (
        "bounded-in-pool", OBJECT_POOL_BASIS),
    (OBJ_PATH, "object_header_block_allocate", "memory_pool_block_reallocate"): (
        "bounded-in-pool", OBJECT_POOL_BASIS),
    (OBJ_PATH, "object_name_list_allocate", "game_state_malloc"): (
        "load-only",
        "object_name_list_allocate <- objects_initialize (objects.c:1139, call at :1169) <- game_initialize "
        "(game.c:281, call at :299) <- main_loop (main.c:3477, call at :3501). main_loop calls game_initialize "
        "once before its frame loop, and shell_xbox.c:122 calls main_loop once from main. game_state_malloc "
        "allocates from the fixed game-state region"),
}

def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def merge_verdicts(alloc_a_path: Path):
    """Built-in verdicts, with the other lane's verdict file (if present) merged on top.

    The file is docs/reports/m2-c2-r6-alloc-a-verdicts.json: {"verdicts": [...]} where each
    row names a file and a function, with an optional api (no api matches every allocator
    call of that function). Rows take "path" or "file" and "basis" or "evidence". A verdict
    outside CLOSED_VERDICTS counts as open.

    A row replaces the built-in rows of its file and function. Returns
    ({(path, function, api or None): (verdict, basis, source)}, stats).
    """
    verdicts = {key: (verdict, basis, "built-in") for key, (verdict, basis) in VERDICTS.items()}
    stats = {"alloc_a_file": display_path(alloc_a_path),
             "alloc_a_present": alloc_a_path.exists(), "alloc_a_entries": 0,
             "alloc_a_overrides": 0, "final_entries": 0}
    if not alloc_a_path.exists():
        return apply_final_verdicts(verdicts, stats), stats
    try:
        document = json.loads(alloc_a_path.read_text())
    except json.JSONDecodeError as error:
        raise SystemExit(f"{stats['alloc_a_file']}: not JSON: {error}")
    rows = document.get("verdicts") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        raise SystemExit(f"{stats['alloc_a_file']}: expected an object with a \"verdicts\" list")
    for row in rows:
        try:
            # "file" rows are relative to submodules/halo-ce-universal; "path" rows are repo-relative
            path = row["path"] if "path" in row else "submodules/halo-ce-universal/" + row["file"]
            key = (path, row["function"], row.get("api"))
            verdict = row["verdict"]
            basis = row["basis"] if "basis" in row else row["evidence"]
        except (KeyError, TypeError, AttributeError):
            raise SystemExit(f"{stats['alloc_a_file']}: row needs file/path, function, verdict and basis/evidence: {row!r}")
        stats["alloc_a_entries"] += 1
        # A row names file and function: it replaces every built-in row of that function.
        for built_in in [k for k in verdicts if k[0] == key[0] and k[1] == key[1] and verdicts[k][2] == "built-in"]:
            if verdicts[built_in][:2] != (verdict, basis):
                stats["alloc_a_overrides"] += 1
            del verdicts[built_in]
        verdicts[key] = (verdict, basis, "alloc-a")
    return apply_final_verdicts(verdicts, stats), stats


def apply_final_verdicts(verdicts, stats):
    """Overlay FINAL_VERDICTS: each row replaces every row of its file and function, whatever its source."""
    for key, (verdict, basis) in FINAL_VERDICTS.items():
        for other in [k for k in verdicts if k[0] == key[0] and k[1] == key[1]]:
            del verdicts[other]
        verdicts[key] = (verdict, basis, "alloc-final")
        stats["final_entries"] += 1
    return verdicts


def lookup_verdict(verdicts, path, function, api):
    """The exact (function, api) row first, then the function's rows for every api."""
    return verdicts.get((path, function, api)) or verdicts.get((path, function, None))


def site_closed(verdict, basis):
    """A site is closed by a closed verdict, or by a bounded verdict whose basis cites a counter."""
    if verdict in CLOSED_VERDICTS:
        return True
    return verdict in BOUNDED_VERDICTS and COUNTER_BASIS.search(basis or "") is not None


def open_records(records):
    """Callsites with a verdict that does not close them, in source order."""
    return [r for r in records if "verdict" in r and not site_closed(r["verdict"], r.get("verdict_basis"))]


def verdict_summary(records, merge_stats):
    counts = Counter(r["verdict"] for r in records if "verdict" in r)
    still_open = open_records(records)
    open_counts = Counter(r["verdict"] for r in still_open)
    # every open verdict is listed, even at zero, so a closed-out row is visible
    for verdict in OPEN_VERDICTS:
        open_counts.setdefault(verdict, 0)
    return {
        "verdict_counts": dict(sorted(counts.items())),
        "open_counts": dict(sorted(open_counts.items())),
        "open_total": len(still_open),
        "closed_by_counter": sum(1 for r in records if "verdict" in r
                                 and r["verdict"] in BOUNDED_VERDICTS
                                 and site_closed(r["verdict"], r.get("verdict_basis"))),
        "open_sites": [f'{r.get("path", "?")}:{r.get("line", "?")} {r.get("enclosing_function") or "?"} '
                       f'{r.get("api", "?")} [{r["verdict"]}]' for r in still_open],
        "alloc_a": merge_stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = []
    for path in source_set():
        try:
            source = path.read_text(errors="replace")
        except OSError:
            continue
        code = mask_noncode(source)
        depths = [0] * len(code)
        depth = 0
        for index, char in enumerate(code):
            depths[index] = depth
            if char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
        for match in CALL.finditer(code):
            # At top-level these tokens are declarations/definitions, not
            # executed allocator expressions. C initializers cannot call them.
            if depths[match.start()] == 0:
                continue
            api = match.group(1)
            records.append({
                "path": path.relative_to(ROOT).as_posix(),
                "line": code.count("\n", 0, match.start()) + 1,
                "api": api,
                "owner_family": owner(api),
                "phase": "unresolved-source-only",
                "release_or_resize": free_semantics(api),
                "evidence": "PS2 port manifest-selected C source expression; runtime invocation/reachability not observed",
            })
    for record in records:
        function = enclosing_function(record["path"], record["line"])
        phase, basis = classify_phase(function, record["path"])
        record["enclosing_function"] = function
        record["phase_classification"] = phase
        record["phase_basis"] = basis
    verdicts, merge_stats = merge_verdicts(ALLOC_A_VERDICTS)
    for record in records:
        if record["phase_classification"] != "load-or-init":
            found = lookup_verdict(verdicts, record["path"], record["enclosing_function"] or "", record["api"])
            verdict, verdict_basis, source = found or ("unverified", "no verdict recorded", "none")
            record["verdict"] = verdict
            record["verdict_basis"] = verdict_basis
            record["verdict_source"] = source
    baseline_result_path = BASELINE / "result.json"
    baseline = json.loads(baseline_result_path.read_text()) if baseline_result_path.exists() else {}
    tu_identities = {}
    for rel, identity in baseline.get("units", {}).items():
        src = HCU / rel
        if src.exists():
            current_hash = hashlib.sha256(src.read_bytes()).hexdigest()
            if current_hash != identity.get("source_sha256"):
                tu_identities[rel] = {
                    "baseline_source_sha256": identity.get("source_sha256"),
                    "current_source_sha256": current_hash,
                    "baseline_object_sha256": identity.get("object_sha256"),
                    "baseline_status": identity.get("status"),
                    "matches_baseline": False,
                }
    def file_hash(path: Path) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    result = {
        "schema": "hcu-postload-allocation-source-inventory-v1",
        "date": "2026-10-23",
        "status": "source-only-inventory-not-workload-trace",
        "scope": {
            "port_manifest": "submodules/halo-ce-universal/port/ps2/port.json",
            "parent_sources": "src/stream/*.c and submodules/halo-ps2/engine/src/core/mem.c",
            "callsite_count": len(records),
            "phase_counts": dict(sorted(Counter(r["phase_classification"] for r in records).items())),
            "verdict_counts": verdict_summary(records, merge_stats)["verdict_counts"],
            "open_counts": verdict_summary(records, merge_stats)["open_counts"],
            "open_total": verdict_summary(records, merge_stats)["open_total"],
            "open_sites": verdict_summary(records, merge_stats)["open_sites"],
            "verdict_sources": dict(sorted(Counter(r.get("verdict_source") for r in records if "verdict" in r).items())),
            "alloc_a": merge_stats,
            "files_with_callsite_count": len({r["path"] for r in records}),
            "api_counts": dict(sorted(Counter(r["api"] for r in records).items())),
        },
        "closure_artifacts": {
            "classification": "stale-compile-baseline; source callsites are current, reachability is not",
            "baseline_elf": "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf",
            "baseline_elf_sha256": file_hash(BASELINE / "halo-local.elf"),
            "baseline_map": "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.map",
            "baseline_map_sha256": file_hash(BASELINE / "halo-local.map"),
            "baseline_result": "build/hcu-ps2-closure/all-no-bootstrap-memory/result.json",
            "baseline_result_sha256": file_hash(baseline_result_path),
            "baseline_hcu_commit": baseline.get("hcu_commit"),
            "baseline_selected_source_count": baseline.get("selected_source_count"),
            "baseline_stale_translation_units": tu_identities,
            "note": "Only mismatching baseline translation units are listed. Matching source hashes do not establish live function reachability or runtime invocation.",
        },
        "limitations": [
            "The manifest describes compiled source selection, not the final live function/call graph; dead or phase-exclusive functions can appear.",
            "Line-level source matches do not resolve macro expansion, conditional compilation, inlining, indirect calls, or allocator implementations hidden in libraries.",
            "Phase, dynamic owner instance, allocation size, success/failure, and free/realloc pairing require runtime callsite observations; no workload invocation is inferred.",
            "This does not inventory EE SDK, IOP, GS, DMA, SPU2, or library-internal allocations unless their source call expression is in this manifest-selected set.",
        ],
        "callsites": records,
    }
    rendered = json.dumps(result, indent=2) + "\n"
    summary = verdict_summary(records, merge_stats)
    lines = ["verdict totals (callsites with a phase other than load-or-init):"]
    lines += [f"  {verdict}: {count}" for verdict, count in summary["verdict_counts"].items()]
    lines.append("bounded verdicts closed by a counter-backed basis: %d" % summary["closed_by_counter"])
    lines.append("open callsites remaining: %d" % summary["open_total"])
    lines += [f"  {verdict}: {count}" for verdict, count in summary["open_counts"].items()]
    lines.append("open callsites (path:line function api [verdict]):")
    lines += [f"  {site}" for site in summary["open_sites"]]
    lines.append("alloc-a verdict file: %s (present=%s, entries=%d, overrides=%d)" % (
        merge_stats["alloc_a_file"], merge_stats["alloc_a_present"],
        merge_stats["alloc_a_entries"], merge_stats["alloc_a_overrides"]))
    lines.append("alloc-final verdict rows applied: %d" % merge_stats["final_entries"])
    if args.output:
        args.output.write_text(rendered)
        print("\n".join(lines))
    else:
        print(rendered, end="")
        print("\n".join(lines), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
