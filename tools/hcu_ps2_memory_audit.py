"""Emit a symbol-level inventory of the linked HCU PS2 BSS.

The link-map input-section ranges are authoritative byte totals. ``nm`` names
the symbols within them; symbol sizes can overlap (for example, aliases), so
the tool deliberately reports both views and never adds symbol sizes to the
section total. This report is an audit queue, not proof that a candidate region
is physically backing the storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from build_toolchain import ROOT, environment

OUT = ROOT / "build/hcu-ps2-closure/all"
SECTION = re.compile(
    r"^\s*(\.bss(?:\.[^\s]+)?|COMMON)\s+"
    r"(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(.+?)\s*$"
)
SECTION_HEADER = re.compile(r"^\s*(\.bss(?:\.[^\s]+)?|COMMON)\s*$")
ADDRESS_ROW = re.compile(r"^\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(.+?)\s*$")
FILL_ROW = re.compile(r"^\s*\*fill\*\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*$")
BSS_OUTPUT = re.compile(r"^\.bss\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*$")
ALLOC_SECTION = re.compile(
    r"^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+"
    r"[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+\S+\s+(\S+)"
)


def parse_map(text: str) -> list[dict[str, object]]:
    ranges = []
    pending_section = None
    bss_bounds = None
    for line in text.splitlines():
        match = BSS_OUTPUT.match(line)
        if match:
            start, size = (int(value, 16) for value in match.groups())
            bss_bounds = (start, start + size)
            break

    def add(section: str, address: str, size: str, input_object: str) -> None:
        if "/" not in input_object and ".a(" not in input_object:
            # Ignore output-section totals and linker-script synthetic rows.
            return
        start, length = int(address, 16), int(size, 16)
        if length and (not bss_bounds or bss_bounds[0] <= start and start + length <= bss_bounds[1]):
            ranges.append({
                "section": section,
                "start": start,
                "end": start + length,
                "bytes": length,
                "input_object": input_object,
                "owner": Path(input_object).name,
            })

    for line in text.splitlines():
        fill = FILL_ROW.match(line)
        if fill:
            address, size = fill.groups()
            start, length = int(address, 16), int(size, 16)
            if length and bss_bounds and bss_bounds[0] <= start and start + length <= bss_bounds[1]:
                ranges.append({
                    "section": "*fill*",
                    "start": start,
                    "end": start + length,
                    "bytes": length,
                    "input_object": "linker alignment padding",
                    "owner": "linker-fill",
                })
            pending_section = None
            continue
        match = SECTION.match(line)
        if not match:
            header = SECTION_HEADER.match(line)
            if header:
                pending_section = header.group(1)
                continue
            if pending_section:
                row = ADDRESS_ROW.match(line)
                if row:
                    address, size, input_object = row.groups()
                    add(pending_section, address, size, input_object)
                    pending_section = None
            continue
        section, address, size, input_object = match.groups()
        pending_section = None
        add(section, address, size, input_object)
    return ranges


def parse_nm(text: str) -> list[dict[str, object]]:
    symbols = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[2] not in {"B", "b", "C", "c"}:
            continue
        try:
            address, size = int(fields[0], 16), int(fields[1], 16)
        except ValueError:
            continue
        symbols.append({"address": address, "bytes": size, "type": fields[2], "name": fields[3]})
    return symbols


def attach_owners(symbols: list[dict[str, object]], ranges: list[dict[str, object]]) -> None:
    for symbol in symbols:
        address = int(symbol["address"])
        candidates = [r for r in ranges if int(r["start"]) <= address < int(r["end"])]
        # Specific symbol sections and COMMON blocks are narrower than the
        # aggregate .bss output section; prefer the narrowest matching range.
        owner = min(candidates, key=lambda r: int(r["bytes"])) if candidates else None
        symbol["input_object"] = owner["input_object"] if owner else None
        symbol["owner"] = owner["owner"] if owner else None
        symbol["owner_section"] = owner["section"] if owner else None
        symbol["review"] = "required"


def parse_file_backed_allocated_bytes(text: str) -> tuple[int, list[dict[str, object]]]:
    sections = []
    total = 0
    for line in text.splitlines():
        match = ALLOC_SECTION.match(line)
        if not match:
            continue
        name, section_type, size_hex, flags = match.groups()
        if "A" not in flags or section_type == "NOBITS":
            continue
        size = int(size_hex, 16)
        total += size
        sections.append({"name": name, "type": section_type, "flags": flags, "bytes": size})
    return total, sections


def apply_region_candidates(
    ranges: list[dict[str, object]],
    symbols: list[dict[str, object]],
    memory_map: dict[str, object],
) -> dict[str, object]:
    owner_regions = memory_map["owner_regions"]
    symbol_regions = memory_map["symbol_regions"]
    unassigned = str(memory_map.get("unassigned_region", "unassigned"))
    system_owner_fragments = memory_map.get("system_runtime_owner_contains", [])

    def owner_region(owner: str) -> str:
        if owner in owner_regions:
            return str(owner_regions[owner])
        if any(fragment in owner for fragment in system_owner_fragments):
            return str(owner_regions["system_runtime"])
        return unassigned

    for symbol in symbols:
        owner = str(symbol.get("owner") or "")
        region = str(symbol_regions.get(symbol["name"], "")) if owner == "ps2_memory.o" else ""
        if not region:
            region = owner_region(owner)
        symbol["candidate_region"] = region or unassigned

    totals: dict[str, int] = {}
    missing_owners = set()
    preceding_region = None
    ps2_memory_ranges = [r for r in ranges if r["owner"] == "ps2_memory.o"]
    ps2_memory_symbols = sorted(
        (s for s in symbols if s["owner"] == "ps2_memory.o"),
        key=lambda s: int(s["address"]),
    )
    special_bss_bytes = 0

    def add(region: str, size: int) -> None:
        totals[region] = totals.get(region, 0) + size

    for item in sorted(ranges, key=lambda r: int(r["start"])):
        owner = str(item["owner"])
        size = int(item["bytes"])
        if owner == "linker-fill":
            region = preceding_region or unassigned
            item["candidate_region"] = region
            add(region, size)
            continue
        if owner == "ps2_memory.o":
            if item["section"] != ".bss":
                # A symbol-specific PS2 memory map currently covers one BSS
                # input section; fail closed if the object adds another.
                missing_owners.add(f"unexpected {item['section']} in ps2_memory.o")
                item["candidate_region"] = unassigned
                add(unassigned, size)
                continue
            start, end = int(item["start"]), int(item["end"])
            inside = [s for s in ps2_memory_symbols if start <= int(s["address"]) < end]
            cursor = start
            previous_region = None
            assigned = 0
            for symbol in inside:
                symbol_start = int(symbol["address"])
                symbol_end = symbol_start + int(symbol["bytes"])
                if symbol_start < cursor:
                    # Aliases overlap. Do not add their byte-size twice.
                    symbol["candidate_region"] = str(symbol.get("candidate_region") or unassigned)
                    continue
                region = str(symbol["candidate_region"])
                if symbol_start > cursor:
                    gap_region = previous_region or region
                    add(gap_region, symbol_start - cursor)
                    assigned += symbol_start - cursor
                add(region, int(symbol["bytes"]))
                assigned += int(symbol["bytes"])
                cursor = symbol_end
                previous_region = region
            if cursor < end:
                tail_region = previous_region or unassigned
                add(tail_region, end - cursor)
                assigned += end - cursor
            if assigned != size:
                missing_owners.add(f"ps2_memory.o section accounted {assigned} of {size} bytes")
            item["candidate_region"] = "split-by-symbol"
            special_bss_bytes += size
            preceding_region = previous_region or unassigned
            continue
        region = owner_region(owner)
        item["candidate_region"] = region
        add(region, size)
        if region == unassigned:
            missing_owners.add(owner)
        preceding_region = region

    return {
        "candidate_bss_bytes_by_region": dict(sorted(totals.items())),
        "symbol_specific_ps2_memory_bytes": special_bss_bytes,
        "unassigned_owners": sorted(missing_owners),
    }


def build_report(
    elf: Path,
    map_path: Path,
    nm_text: str,
    readelf_text: str,
    budget: dict[str, object],
    memory_map: dict[str, object],
) -> dict[str, object]:
    ranges = parse_map(map_path.read_text(encoding="utf-8", errors="replace"))
    symbols = parse_nm(nm_text)
    attach_owners(symbols, ranges)
    owner_totals: dict[str, int] = {}
    for item in ranges:
        owner = str(item["owner"])
        owner_totals[owner] = owner_totals.get(owner, 0) + int(item["bytes"])
    file_backed_bytes, alloc_sections = parse_file_backed_allocated_bytes(readelf_text)
    candidates = apply_region_candidates(ranges, symbols, memory_map)
    candidate_totals = dict(candidates["candidate_bss_bytes_by_region"])
    file_backed_region = str(memory_map["file_backed_region"])
    candidate_totals[file_backed_region] = candidate_totals.get(file_backed_region, 0) + file_backed_bytes
    capacities = {entry["name"]: int(entry["bytes"]) for entry in budget["regions"]}
    over_capacity = {
        region: {"used": used, "capacity": capacities[region]}
        for region, used in candidate_totals.items()
        if region in capacities and used > capacities[region]
    }
    symbols.sort(key=lambda item: (item["owner"] or "", item["address"], item["name"]))
    return {
        "elf": str(elf),
        "map": str(map_path),
        "warning": "Region totals are provisional logical assignments, not proof of physical linker/loader or parent-arena placement. Symbol sizes may alias; map input sections are the authoritative totals.",
        "file_backed_allocated_bytes": file_backed_bytes,
        "file_backed_sections": alloc_sections,
        "bss_input_sections": ranges,
        "bss_bytes_by_input_object": dict(sorted(owner_totals.items())),
        **candidates,
        "candidate_allocated_bytes_by_region": dict(sorted(candidate_totals.items())),
        "budget_capacities": capacities,
        "candidate_regions_over_capacity": over_capacity,
        "symbols": symbols,
        "unmapped_symbol_count": sum(item["owner"] is None for item in symbols),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, default=OUT / "halo-local.elf")
    parser.add_argument("--map", dest="map_path", type=Path, default=OUT / "halo-local.map")
    parser.add_argument("--output", type=Path, default=OUT / "memory-symbols.json")
    parser.add_argument("--budget", type=Path, default=ROOT / "config/memory-budget.json")
    parser.add_argument("--memory-map", type=Path, default=ROOT / "config/hcu-ps2-memory-map.json")
    args = parser.parse_args()
    if not args.elf.is_file() or not args.map_path.is_file():
        raise RuntimeError("build the HCU PS2 ELF first with tools/hcu_ps2_link.py")
    _build, prefix, _env, _jobs = environment()
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    readelf = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    output = subprocess.check_output([str(nm), "-S", "--defined-only", str(args.elf)], text=True)
    sections = subprocess.check_output([str(readelf), "-W", "-S", str(args.elf)], text=True)
    report = build_report(
        args.elf, args.map_path, output, sections,
        json.loads(args.budget.read_text(encoding="utf-8")),
        json.loads(args.memory_map.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print("BSS input-section bytes by owner:")
    for owner, size in report["bss_bytes_by_input_object"].items():
        print(f"  {size:>9}  {owner}")
    print(f"Named BSS symbols: {len(report['symbols'])}; unmapped: {report['unmapped_symbol_count']}")
    print("Provisional region totals:")
    for region, size in report["candidate_allocated_bytes_by_region"].items():
        cap = report["budget_capacities"].get(region)
        suffix = f" / {cap}" if cap is not None else " (unassigned)"
        print(f"  {size:>9}  {region}{suffix}")
    print("Unassigned owners:", report["unassigned_owners"])


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        sys.exit(f"HCU PS2 memory audit failed: {error}")
