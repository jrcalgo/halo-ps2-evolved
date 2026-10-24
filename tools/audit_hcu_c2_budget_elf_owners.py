#!/usr/bin/env python3
"""C2.3 ELF owner attribution for linked HCU probe ELFs.

Budget v3 accounting: elf_static is charged the file-backed LOAD bytes (no
NOBITS); ELF NOBITS is reported separately as charged to resident_gameplay.
The per-symbol classification below is informational attribution.

Every static symbol of the probe's .bss and .data is classified once for
owner attribution. NOBITS is charged to resident_gameplay regardless of symbol
classification; diagnostic-only content is a subset of those NOBITS bytes.
File-backed LOAD bytes are charged to elf_static. The result reports both
accounting bases, so no byte is counted twice.

Classification is by symbol name, from the CE and port sources that define the
symbol (see OWNER_RULES). A symbol not listed is unowned static state.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NM = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-nm"
ADDR2LINE = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-addr2line"
READELF = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-readelf"
DEFAULT_ELF = ROOT / "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-tagcache-4477120.elf"

ELF_STATIC = "elf_static"
DIAGNOSTIC = "diagnostic_in_elf_static"

# name -> (owner region, class, source that defines it).
# class "owned" = counted in the named region; "diagnostic" = linked into the
# production image but used only for debugging, stays in elf_static.
OWNER_RULES = {
    "widget_walk": ("streaming", "owned", "port/linux/game/tag_schema_effects.c: validator graph walk, map-load scratch"),
    "tag_validate_bootstrap_claims": ("streaming", "owned", "port/linux/game/tag_validate.c: validator claims before the resident owner"),
    "tag_empty_data_bytes": ("streaming", "owned", "source/tag_files/tag_groups.c: empty tag data for map-load tag reads"),
    "object_bounds": ("dynamic_simulation", "owned", "port/ps2/game/ps2_local.c: per-object bounds pool"),
    "lights_port": ("dynamic_simulation", "owned", "source/objects/object_lights.c: light pool"),
    "decal_geometry": ("dynamic_simulation", "owned", "source/effects/decals.c: decal pool"),
    "s_decal_bytes": ("dynamic_simulation", "owned", "port/ps2/src/ps2_rasterizer.c: decal vertex bytes"),
    "s_dynamic_vertex_bytes": ("frame_scratch", "owned", "port/ps2/src/ps2_rasterizer.c: per-frame dynamic vertices"),
    "s_dynamic_triangle_shorts": ("frame_scratch", "owned", "port/ps2/src/ps2_rasterizer.c: per-frame dynamic indices"),
    "s_dynamic_triangles": ("frame_scratch", "owned", "port/ps2/src/ps2_rasterizer.c: per-frame dynamic triangles"),
    "game_state_allocations": ("resident_gameplay", "owned", "source/saved games/game_state.c: game-state allocation records"),
    "sound_channels": ("audio", "owned", "source/sound/sound_manager.c: voice channels"),
    "dsound_globals": ("audio", "owned", "port/linux/src/halo_linker_common.c: DirectSound state"),
    "stack": ("system_kernel", "owned", "SDK/runtime stack"),
    "stack.1": ("system_kernel", "owned", "SDK/runtime stack"),
    "__intr_data": ("system_kernel", "owned", "SDK interrupt data"),
    "__sbuff": ("system_kernel", "owned", "SDK stdio buffer"),
    "_fio_recv_data": ("system_kernel", "owned", "SDK file I/O receive buffer"),
    "sCmdRecvBuff": ("system_kernel", "owned", "SDK command receive buffer"),
    "sCmdSendBuff": ("system_kernel", "owned", "SDK command send buffer"),
    "__threadInfo": ("system_kernel", "owned", "SDK thread state"),
    "_rd_intr_data": ("system_kernel", "owned", "SDK interrupt data"),
    "__descriptor_data_pool": ("system_kernel", "owned", "SDK descriptor pool"),
    "__descriptormap": ("system_kernel", "owned", "SDK descriptor map"),
    "__cwd": ("system_kernel", "owned", "SDK working directory"),
    "tocBuff": ("system_kernel", "owned", "SDK table of contents buffer"),
    "g_AlarmBuf": ("system_kernel", "owned", "SDK alarm buffer"),
    "topArg": ("system_kernel", "owned", "SDK argument buffer"),
    "profilestring": ("system_kernel", "owned", "SDK profile string buffer"),
    # Diagnostic-only: linked into the production image, read only by debug paths.
    "ai_debug": (ELF_STATIC, DIAGNOSTIC, "source/ai/ai_debug.c: AI debug recorder; on PS2 its line-of-sight buffers are one entry each unless HCU_AI_DEBUG_DIAGNOSTICS is defined (source/ai/ai_debug.h), and its 512 actor records stay full size"),
    "g_CounterBuf": (ELF_STATIC, DIAGNOSTIC, "profile counters"),
    "ai_profile": (ELF_STATIC, DIAGNOSTIC, "AI profiler state"),
    "debug_path": (ELF_STATIC, DIAGNOSTIC, "AI debug path draw state"),
    "debug_obstacles": (ELF_STATIC, DIAGNOSTIC, "AI debug obstacle draw state"),
    "cheat_strings": (ELF_STATIC, DIAGNOSTIC, "development cheat strings"),
    "console_globals": (ELF_STATIC, DIAGNOSTIC, "development console state"),
    "profile_graph_values": (ELF_STATIC, DIAGNOSTIC, "profiler graph samples (.data)"),
}

BSS_TYPES = ("b", "B")
DATA_TYPES = ("d", "D")
TEXT_TYPES = ("t", "T", "w", "W")
CODE_SECTIONS = (".text", ".rodata", ".data", ".sdata", ".MIPS.abiflags")


def section_sizes(elf):
    out = subprocess.run([str(READELF), "-SW", str(elf)], capture_output=True, text=True, check=True).stdout
    sizes = {}
    for line in out.splitlines():
        parts = line.replace("[", " ").replace("]", " ").split()
        # "1 .text PROGBITS addr off size ..."
        if len(parts) >= 6 and parts[1].startswith("."):
            try:
                sizes[parts[1]] = int(parts[5], 16)
            except ValueError:
                pass
    return sizes


def load_segments(elf):
    """PT_LOAD rows: (vaddr, filesz, memsz). filesz is file-backed, memsz-filesz is NOBITS."""
    out = subprocess.run([str(READELF), "-lW", str(elf)], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        p = line.split()
        if p and p[0] == "LOAD":
            rows.append({"vaddr": int(p[2], 16), "filesz": int(p[4], 16), "memsz": int(p[5], 16)})
    return rows


def alloc_section_bytes(elf):
    """Allocated section bytes split by NOBITS vs file-backed (SHF_ALLOC only)."""
    out = subprocess.run([str(READELF), "-SW", str(elf)], capture_output=True, text=True, check=True).stdout
    file_backed = nobits = 0
    for line in out.splitlines():
        parts = line.replace("[", " ").replace("]", " ").split()
        # nr name type addr off size es [flags] lk inf al
        if len(parts) < 7 or not parts[1].startswith("."):
            continue
        flags = parts[7] if len(parts) >= 11 else ""
        if "A" not in flags:
            continue
        size = int(parts[5], 16)
        if parts[2] == "NOBITS":
            nobits += size
        else:
            file_backed += size
    return file_backed, nobits


def symbols(elf):
    out = subprocess.run([str(NM), "-S", "-t", "d", str(elf)], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        p = line.split()
        if len(p) == 4 and p[2] in BSS_TYPES + DATA_TYPES + TEXT_TYPES:
            rows.append({"addr": int(p[0]), "size": int(p[1], 10), "type": p[2], "name": p[3]})
    return rows


def budget_region_bytes(name):
    # Capacities are the budget's, read from config/memory-budget.json; the
    # audit never carries its own copy of a number.
    budget = json.loads((ROOT / "config/memory-budget.json").read_text())
    for region in budget["regions"]:
        if region["name"] == name:
            return region["bytes"]
    raise KeyError(f"config/memory-budget.json has no {name} region")


def elf_static_reservation():
    return budget_region_bytes(ELF_STATIC)


def source_lines(elf, addresses):
    # addr2line -f prints a function name and file:line per address. Only the
    # symbols listed in a top table get this lookup, so one call stays small.
    if not addresses:
        return []
    out = subprocess.run([str(ADDR2LINE), "-f", "-e", str(elf)] + [hex(a) for a in addresses],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return [out[i + 1] if i + 1 < len(out) else "??:0" for i in range(0, len(out), 2)]


def top_symbols(elf, syms, types, count):
    picked = sorted((s for s in syms if s["type"] in types), key=lambda s: -s["size"])[:count]
    where = source_lines(elf, [s["addr"] for s in picked])
    return [{"name": s["name"], "bytes": s["size"], "source": w.replace(str(ROOT) + "/", "")}
            for s, w in zip(picked, where)]


def attribute(elf, top=30):
    sec = section_sizes(elf)
    syms = symbols(elf)
    code_bytes = sum(sec.get(s, 0) for s in CODE_SECTIONS)
    bss_bytes = sec.get(".bss", 0)
    owned = {}
    diagnostic = []
    unowned_named = []
    owned_rows = []
    for s in syms:
        if s["type"] not in BSS_TYPES:
            continue
        rule = OWNER_RULES.get(s["name"])
        if rule is None:
            continue
        owner, cls, why = rule
        if cls == "owned":
            owned[owner] = owned.get(owner, 0) + s["size"]
            owned_rows.append({"symbol": s["name"], "bytes": s["size"], "owner": owner, "source": why})
        else:
            diagnostic.append({"symbol": s["name"], "bytes": s["size"], "source": why})
    owned_total = sum(owned.values())
    diag_total = sum(d["bytes"] for d in diagnostic)
    # Data symbols (.data) are inside code_bytes already; only .bss is re-owned.
    # unowned_bss is every .bss byte that no named region counts, so it includes
    # the diagnostic bytes (diag_total is a subset of it, not an addition to it).
    unowned_bss = bss_bytes - owned_total
    # Budget v3: elf_static holds the file-backed LOAD bytes (PROGBITS/alloc,
    # no NOBITS). ELF NOBITS (memsz - filesz) is charged to resident_gameplay at
    # boot (src/stream/hcu_main.c). The owned/unowned .bss split above is
    # informational attribution; it no longer decides elf_static.
    loads = load_segments(elf)
    file_backed = sum(l["filesz"] for l in loads)
    nobits = sum(l["memsz"] - l["filesz"] for l in loads)
    sec_file_backed, sec_nobits = alloc_section_bytes(elf)
    elf_static_need = file_backed
    reservation = elf_static_reservation()
    resident_cap = budget_region_bytes("resident_gameplay")
    return {
        "elf": str(elf),
        "sections": {k: sec.get(k, 0) for k in CODE_SECTIONS + (".bss",)},
        "code_and_constant_bytes": code_bytes,
        "text_bytes": sec.get(".text", 0),
        "rodata_bytes": sec.get(".rodata", 0),
        "data_bytes": sec.get(".data", 0) + sec.get(".sdata", 0) + sec.get(".MIPS.abiflags", 0),
        "bss_bytes": bss_bytes,
        "bss_symbol_bytes": sum(s["size"] for s in syms if s["type"] in BSS_TYPES),
        "bss_section_padding_bytes": bss_bytes - sum(s["size"] for s in syms if s["type"] in BSS_TYPES),
        "owned_bss_by_region": owned,
        "owned_bss_total": owned_total,
        "owned_rows": sorted(owned_rows, key=lambda r: -r["bytes"]),
        "diagnostic_in_elf_static": sorted(diagnostic, key=lambda d: -d["bytes"]),
        "diagnostic_in_elf_static_total": diag_total,
        "unowned_bss_bytes": unowned_bss,
        "unowned_non_diagnostic_bss_bytes": unowned_bss - diag_total,
        "load_segments": loads,
        "file_backed_load_bytes": file_backed,
        "alloc_section_file_backed_bytes": sec_file_backed,
        "alloc_section_nobits_bytes": sec_nobits,
        "nobits_bytes": nobits,
        "nobits_charged_to": "resident_gameplay",
        "resident_gameplay_capacity_bytes": resident_cap,
        "resident_gameplay_after_nobits_bytes": resident_cap - nobits,
        "resident_gameplay_nobits_fits": nobits <= resident_cap,
        "elf_static_need_bytes": elf_static_need,
        "elf_static_margin_bytes": reservation - elf_static_need,
        "elf_static_reservation_bytes": reservation,
        "elf_static_fits": elf_static_need <= reservation,
        "elf_static_excess_bytes": max(0, elf_static_need - reservation),
        "largest_unowned_bss_symbols": [
            {"name": s["name"], "bytes": s["size"]} for s in sorted(
                (s for s in syms if s["type"] in BSS_TYPES and s["name"] not in OWNER_RULES),
                key=lambda s: -s["size"])[:12]],
        "top_bss_symbols": top_symbols(elf, syms, BSS_TYPES, top),
        "top_data_symbols": top_symbols(elf, syms, DATA_TYPES, top),
        "top_text_symbols": top_symbols(elf, syms, TEXT_TYPES, top),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--elf", default=str(DEFAULT_ELF))
    ap.add_argument("--json", default="")
    ap.add_argument("--top", type=int, default=30, help="symbols per top table")
    args = ap.parse_args(argv)
    result = attribute(Path(args.elf), args.top)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in (
        "text_bytes", "rodata_bytes", "data_bytes", "code_and_constant_bytes", "bss_bytes",
        "owned_bss_total", "owned_bss_by_region", "diagnostic_in_elf_static_total",
        "unowned_non_diagnostic_bss_bytes", "unowned_bss_bytes", "file_backed_load_bytes",
        "elf_static_need_bytes", "elf_static_reservation_bytes", "elf_static_fits",
        "elf_static_excess_bytes", "elf_static_margin_bytes", "nobits_bytes",
        "resident_gameplay_capacity_bytes", "resident_gameplay_after_nobits_bytes",
        "resident_gameplay_nobits_fits")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
