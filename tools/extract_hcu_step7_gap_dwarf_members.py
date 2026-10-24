#!/usr/bin/env python3
"""Extract exact compiler member layout for BSP schema gaps via GCC DWARF.

The input declarations are compiled with the pinned R5900 toolchain and exact
closure flags. This tool reports physical member ranges and their overlap with
schema-unrepresented intervals only. It does not assign consumer meaning or
retention/removal dispositions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_toolchain import environment as toolchain_environment  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_readelf(text: str) -> dict[int, dict]:
    """Parse the stable DIE/attribute subset emitted by GNU readelf."""
    dies: dict[int, dict] = {}
    stack: list[int] = []
    die_re = re.compile(r"^\s*<([0-9]+)><([0-9a-f]+)>: Abbrev Number: [0-9]+ \((DW_TAG_[^)]+)\)")
    attr_re = re.compile(r"^\s*<[0-9a-f]+>\s+(DW_AT_[A-Za-z0-9_]+)\s*:\s*(.*)$")
    for line in text.splitlines():
        m = die_re.match(line)
        if m:
            depth, off, tag = int(m.group(1)), int(m.group(2), 16), m.group(3)
            while len(stack) > depth:
                stack.pop()
            parent = stack[-1] if stack else None
            dies[off] = {"offset": off, "depth": depth, "tag": tag, "parent": parent, "attrs": {}, "children": []}
            if parent is not None:
                dies[parent]["children"].append(off)
            stack.append(off)
            continue
        m = attr_re.match(line)
        if m and stack:
            dies[stack[-1]]["attrs"][m.group(1)] = m.group(2).strip()
    return dies


def attr_number(value: str | None) -> int | None:
    if value is None:
        return None
    # readelf renders constants as e.g. ``(data1) 12`` and DWARF refs as
    # ``(ref4) <0x123>``. For locations/bit offsets, use the terminal integer.
    m = re.search(r"(?:^|\s)(0x[0-9a-fA-F]+|[0-9]+)\s*$", value)
    if not m:
        return None
    return int(m.group(1), 0)


def attr_ref(value: str | None) -> int | None:
    if value is None:
        return None
    m = re.search(r"<0x([0-9a-fA-F]+)>", value)
    return int(m.group(1), 16) if m else None


def attr_string(value: str | None) -> str | None:
    if value is None:
        return None
    # The final colon separates GNU readelf's form/offset prefix from a string.
    if "): " in value:
        return value.rsplit(": ", 1)[1]
    m = re.match(r"^\([^)]*\)\s*(.*)$", value)
    return m.group(1) if m else value


def type_size(dies: dict[int, dict], ref: int | None, seen: set[int] | None = None) -> int | None:
    if ref is None or ref not in dies:
        return None
    seen = set() if seen is None else seen
    if ref in seen:
        return None
    seen.add(ref)
    die = dies[ref]
    size = attr_number(die["attrs"].get("DW_AT_byte_size"))
    if size is not None:
        return size
    if die["tag"] in {"DW_TAG_typedef", "DW_TAG_const_type", "DW_TAG_volatile_type", "DW_TAG_restrict_type", "DW_TAG_atomic_type"}:
        return type_size(dies, attr_ref(die["attrs"].get("DW_AT_type")), seen)
    if die["tag"] == "DW_TAG_array_type":
        elem = type_size(dies, attr_ref(die["attrs"].get("DW_AT_type")), seen)
        count = 1
        for child in die["children"]:
            c = dies[child]
            if c["tag"] == "DW_TAG_subrange_type":
                n = attr_number(c["attrs"].get("DW_AT_count"))
                if n is None:
                    upper = attr_number(c["attrs"].get("DW_AT_upper_bound"))
                    lower = attr_number(c["attrs"].get("DW_AT_lower_bound")) or 0
                    n = upper - lower + 1 if upper is not None else None
                if n is None:
                    return None
                count *= n
        return elem * count if elem is not None else None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", type=Path, default=ROOT / "docs/reports/m2-step7-schema-gap-source-discovery-2026-10-22.json")
    ap.add_argument("--layout", type=Path, default=ROOT / "docs/reports/m2-step7-schema-gap-layout-2026-10-22.json")
    ap.add_argument("--output", type=Path, default=ROOT / "docs/reports/m2-step7-schema-gap-dwarf-members-2026-10-22.json")
    args = ap.parse_args()
    discovery, layout = json.loads(args.discovery.read_text()), json.loads(args.layout.read_text())
    build, prefix, env, _ = toolchain_environment()
    closure = build / "hcu-ps2-closure/all-no-bootstrap-memory"
    exact_result = json.loads((closure / "result.json").read_text())
    hcu = ROOT / "submodules/halo-ce-universal"
    port = json.loads((hcu / "port/ps2/port.json").read_text())
    includes = ["-I" + str(hcu / x) for x in port["include_dirs"]]
    includes += ["-I" + str(prefix / "ps2sdk/common/include"), "-I" + str(prefix / "ps2sdk/ee/include")]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    readelf = "readelf"
    semantics = closure / "halo_ps2_msvc_semantics.h"
    prefix_header = hcu / port["prefix"]

    # Build one debug object per existing sizeof-probe group. Explicit global
    # instances retain each named aggregate in DWARF, even under -Os.
    groups: dict[str, list[str]] = {}
    for name, item in layout["type_size_results"].items():
        if item["status"] == "passed":
            groups.setdefault(item["probe"], []).append(name)
    decls = {g["definition"]: g for g in discovery["gaps"]}
    out_dir = build / "hcu-step7-step8-c0/schema-gap-dwarf-members"
    out_dir.mkdir(parents=True, exist_ok=True)
    type_results = {}
    for i, (probe_rel, names) in enumerate(sorted(groups.items())):
        original = ROOT / probe_rel
        src = out_dir / f"members_{i:02d}.c"
        obj = src.with_suffix(".o")
        lines = [original.read_text()]
        for j, name in enumerate(sorted(names)):
            kind = layout["type_size_results"][name]["tag_kind"]
            lines.append(f"{kind} {name} hcu_dwarf_force_{j};")
        src.write_text("\n".join(lines) + "\n")
        command = [str(compiler), *exact_result["flags"], "-g", "-gdwarf-4", "-fno-eliminate-unused-debug-types",
                   *includes, "-include", str(prefix_header), "-include", str(semantics), "-c", str(src), "-o", str(obj)]
        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(f"DWARF probe failed ({src}):\n{run.stdout}{run.stderr}")
        dumped = subprocess.run([readelf, "--debug-dump=info", "--wide", str(obj)], capture_output=True, text=True, check=True)
        dies = parse_readelf(dumped.stdout)
        die_types = {}
        for d in dies.values():
            name = attr_string(d["attrs"].get("DW_AT_name"))
            size = attr_number(d["attrs"].get("DW_AT_byte_size"))
            if d["tag"] in {"DW_TAG_structure_type", "DW_TAG_union_type"} and name and size is not None:
                die_types.setdefault(name, []).append(d)
        for name in names:
            expected = layout["type_size_results"][name]["expected_schema_size"]
            candidates = [d for d in die_types.get(name, []) if attr_number(d["attrs"].get("DW_AT_byte_size")) == expected]
            if not candidates:
                type_results[name] = {"status": "dwarf_type_not_found", "expected_schema_size": expected,
                                      "probe_source": str(src.relative_to(ROOT)), "probe_source_sha256": sha256(src),
                                      "object": str(obj.relative_to(ROOT)), "object_sha256": sha256(obj)}
                continue
            # Prefer a complete type with concrete members, and retain all
            # candidates' offsets to surface ambiguous duplicate declarations.
            d = max(candidates, key=lambda x: sum(dies[c]["tag"] == "DW_TAG_member" for c in x["children"]))
            members = []
            for child in d["children"]:
                m = dies[child]
                if m["tag"] != "DW_TAG_member":
                    continue
                attrs = m["attrs"]
                offset = attr_number(attrs.get("DW_AT_data_member_location"))
                # C union members all begin at byte zero; DWARF commonly omits
                # their redundant DW_AT_data_member_location attribute.
                if offset is None and d["tag"] == "DW_TAG_union_type":
                    offset = 0
                bits = attr_number(attrs.get("DW_AT_bit_size"))
                bit_offset = attr_number(attrs.get("DW_AT_bit_offset"))
                ref = attr_ref(attrs.get("DW_AT_type"))
                size = type_size(dies, ref)
                members.append({"name": attr_string(attrs.get("DW_AT_name")), "offset": offset,
                                "size": size, "bit_size": bits, "bit_offset": bit_offset,
                                "type_die": ref, "member_range": {"offset": offset, "size": size} if offset is not None and size is not None else None})
            type_results[name] = {"status": "extracted", "sizeof": expected,
                                  "declaration": layout["type_size_results"][name]["declaration"],
                                  "probe_source": str(src.relative_to(ROOT)), "probe_source_sha256": sha256(src),
                                  "probe_object": str(obj.relative_to(ROOT)), "probe_object_sha256": sha256(obj),
                                  "members": members}

    # Map member physical intervals against schema ranges. Overlaps are purely
    # geometric evidence; they do not classify or release any bytes.
    mapped = []
    for gap in discovery["gaps"]:
        result = type_results.get(gap["definition"], {"status": "no_matching_size_type"})
        start, end = gap["schema_range"]["offset"], gap["schema_range"]["offset"] + gap["schema_range"]["size"]
        overlaps = []
        for member in result.get("members", []):
            r = member.get("member_range")
            if not r:
                continue
            a, b = r["offset"], r["offset"] + r["size"]
            lo, hi = max(start, a), min(end, b)
            if lo < hi:
                overlaps.append({"member": member["name"], "member_range": r,
                                 "schema_gap_overlap": {"offset": lo, "size": hi - lo}})
        mapped.append({**gap, "dwarf_layout": result, "member_overlap_evidence": overlaps,
                       "classification": "unclassified", "semantic_consumer_disposition": "unresolved"})

    report = {"format": "hcu-step7-schema-gap-dwarf-members-v1", "discovery": str(args.discovery.relative_to(ROOT)),
              "discovery_sha256": sha256(args.discovery), "layout": str(args.layout.relative_to(ROOT)),
              "layout_sha256": sha256(args.layout), "schema_elf_sha256": discovery["schema_elf_sha256"],
              "exact_source_build_result_sha256": sha256(closure / "result.json"),
              "prefix_header": str(prefix_header.relative_to(ROOT)), "prefix_header_sha256": sha256(prefix_header),
              "msvc_semantics_header": str(semantics.relative_to(ROOT)), "msvc_semantics_header_sha256": sha256(semantics),
              "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
              "compiler_flags": exact_result["flags"] + ["-g", "-gdwarf-4", "-fno-eliminate-unused-debug-types"],
              "include_dirs": [str(Path(p).relative_to(ROOT)) if Path(p).is_relative_to(ROOT) else str(p)
                               for p in [*(hcu / x for x in port["include_dirs"]),
                                         prefix / "ps2sdk/common/include", prefix / "ps2sdk/ee/include"]],
              "types": type_results, "ranges": mapped,
              "summary": {"schema_ranges": len(mapped), "matched_source_types": len(type_results),
                          "types_with_member_layout": sum(x.get("status") == "extracted" for x in type_results.values()),
                          "sizeof_matched_ranges": sum(r.get("dwarf_layout", {}).get("status") == "extracted" for r in mapped),
                          "ranges_without_matching_dwarf_type": sum(r.get("dwarf_layout", {}).get("status") != "extracted" for r in mapped),
                          "all_ranges_unclassified": True,
                          "note": "DWARF member offsets and extents are exact compiler-layout evidence for these declarations. Geometric overlap with schema gaps is not a semantic disposition and does not authorize normalization or removal."}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
