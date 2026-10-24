#!/usr/bin/env python3
"""Map anonymous schema ranges to exact CE C fields with R5900 offsetof probes.

This reports declaration/layout ownership only. It never converts an
unclassified schema byte range into a safe-to-remove or normalized field.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_toolchain import environment as toolchain_environment  # noqa: E402

INV = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
LAYOUT = ROOT / "docs/reports/m2-step7-schema-gap-layout-2026-10-22.json"
DISCOVERY = ROOT / "docs/reports/m2-step7-schema-gap-source-discovery-2026-10-22.json"
OUT = ROOT / "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fields_from_declaration(source: str, name: str, tag_kind: str, line: int) -> list[str]:
    pattern = re.compile(r"\b" + re.escape(tag_kind) + r"\s+" + re.escape(name) + r"\s*\{(.*?)\}\s*;", re.S)
    matches = list(pattern.finditer(source))
    if not matches:
        return []
    # There may be a forward declaration or duplicate spelling in one TU;
    # choose the body nearest the declaration selected by the existing audit.
    m = min(matches, key=lambda x: abs(source.count("\n", 0, x.start()) + 1 - line))
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", m.group(1), flags=re.S)
    found = []
    for decl in body.split(";"):
        decl = " ".join(decl.split())
        if not decl:
            continue
        # Current BSP records use one declarator per statement. Skip function
        # members/bitfields rather than guessing their record contribution.
        if "(" in decl or ":" in decl:
            continue
        dm = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*$", decl)
        if dm:
            found.append(dm.group(1))
    return list(dict.fromkeys(found))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=OUT)
    args = ap.parse_args()
    inv = json.loads(INV.read_text())
    layout = json.loads(LAYOUT.read_text())
    discovery = json.loads(DISCOVERY.read_text())
    build, prefix, env, _jobs = toolchain_environment()
    closure_dir = build / "hcu-ps2-closure/all-no-bootstrap-memory"
    build_result = json.loads((closure_dir / "result.json").read_text())
    hcu = ROOT / "submodules/halo-ce-universal"
    port = json.loads((hcu / "port/ps2/port.json").read_text())
    include_dirs = ["-I" + str(hcu / x) for x in port["include_dirs"]]
    include_dirs += ["-I" + str(prefix / "ps2sdk/common/include"), "-I" + str(prefix / "ps2sdk/ee/include")]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    readelf = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    semantics = closure_dir / "halo_ps2_msvc_semantics.h"
    prefix_header = hcu / port["prefix"]
    probe_root = build / "hcu-step7-step8-c0/range-member-probes"
    probe_root.mkdir(parents=True, exist_ok=True)

    gap_defs = {g["definition"] for g in discovery["gaps"]}
    type_results = layout["type_size_results"]
    probes = {}
    fields_by_def = {}
    for name in sorted(gap_defs):
        tr = type_results.get(name)
        if not tr or tr.get("status") != "passed":
            fields_by_def[name] = []
            probes[name] = {"status": "no compiler-selected source declaration", "fields": []}
            continue
        decl = tr["declaration"]
        rel = decl["path"]
        srcpath = ROOT / rel
        source = srcpath.read_text(errors="replace")
        fields = fields_from_declaration(source, name, decl.get("tag_kind", "struct"), decl["line"])
        fields_by_def[name] = fields
        if not fields:
            probes[name] = {"status": "source declaration has no parseable direct fields", "declaration": decl, "fields": []}
            continue
        probe = probe_root / (re.sub(r"[^A-Za-z0-9_]", "_", name) + ".c")
        obj = probe.with_suffix(".o")
        lines = ['#include "cseries.h"', f'#include "{srcpath}"', '__attribute__((used,section(".hcu_membermap"))) const unsigned int hcu_membermap[] = {']
        for field in fields:
            lines.append(f"__builtin_offsetof({decl.get('tag_kind','struct')} {name}, {field}), sizeof((({decl.get('tag_kind','struct')} {name} *)0)->{field}),")
        lines.append("};")
        probe.write_text("\n".join(lines) + "\n")
        command = [str(compiler), *build_result["flags"], *include_dirs,
                   "-include", str(prefix_header), "-include", str(semantics),
                   "-c", str(probe), "-o", str(obj)]
        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        if run.returncode != 0 or not obj.exists():
            probes[name] = {"status": "failed", "declaration": decl, "fields": fields,
                            "probe": probe.relative_to(ROOT).as_posix(), "probe_sha256": sha(probe),
                            "diagnostics": (run.stdout + run.stderr)[-5000:]}
            continue
        dump = subprocess.run([str(readelf), "-x", ".hcu_membermap", str(obj)], capture_output=True, text=True)
        words = []
        for line in dump.stdout.splitlines():
            if not re.match(r"\s*0x[0-9a-fA-F]+", line):
                continue
            # readelf prints 32-bit words in the hex columns before ASCII.
            words.extend(int(token, 16) for token in re.findall(r"\b[0-9a-fA-F]{8}\b", line.split("  ", 1)[1].split("  ", 1)[0]))
        # The target is little endian; each displayed hex word is the bytewise
        # representation of one uint32 constant, hence reverse its bytes.
        values = []
        for w in words:
            values.append(int.from_bytes(w.to_bytes(4, "big"), "little"))
        if len(values) != len(fields) * 2:
            probes[name] = {"status": "could not decode compiler offset section", "declaration": decl,
                            "fields": fields, "probe": probe.relative_to(ROOT).as_posix(),
                            "probe_sha256": sha(probe), "object_sha256": sha(obj), "readelf": dump.stdout}
            continue
        field_rows = [{"name": fields[i], "offset": values[2*i], "size": values[2*i+1]} for i in range(len(fields))]
        probes[name] = {"status": "passed", "declaration": decl, "declaration_sha256": sha(srcpath),
                        "probe": probe.relative_to(ROOT).as_posix(), "probe_sha256": sha(probe),
                        "object": obj.relative_to(ROOT).as_posix(), "object_sha256": sha(obj),
                        "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
                        "fields": field_rows}

    range_rows = []
    for m in inv["members"]:
        if m["classification"] != "unclassified":
            continue
        start, end = m["offset_within_definition"], m["offset_within_definition"] + m["size"]
        pr = probes.get(m["definition"], {})
        candidates = []
        for f in pr.get("fields", []):
            if not isinstance(f, dict):
                continue
            fs, fe = f["offset"], f["offset"] + f["size"]
            if fs < end and start < fe:
                candidates.append({**f, "relation": "fully-contained-by-range" if start <= fs and fe <= end else "partially-overlaps-range"})
        gap = next((g for g in discovery["gaps"] if g["definition_id"] == m["definition_id"] and g["schema_range"]["offset"] == start and g["schema_range"]["size"] == m["size"]), None)
        range_rows.append({
            "inventory_path": m["path"], "definition": m["definition"], "definition_id": m["definition_id"],
            "schema_range": {"offset": start, "size": m["size"]},
            "classification_remains": "unclassified",
            "compiler_source_type_probe_status": pr.get("status", "not probed"),
            "source_declaration": pr.get("declaration"),
            "source_declaration_sha256": pr.get("declaration_sha256"),
            "candidate_c_members": candidates,
            "source_discovery_note": gap.get("note") if gap else "No source-discovery row matched this definition/range.",
            "interpretation": "C-layout overlap identifies source member ownership only; it does not close schema byte preservation, consumer, normalization, or safety disposition.",
        })

    output = {
        "format": "hcu-step7-bsp-range-member-layout-v1",
        "generated_by": "tools/probe_step7_bsp_range_members.py",
        "inventory_path": INV.relative_to(ROOT).as_posix(), "inventory_sha256": sha(INV),
        "layout_report_path": LAYOUT.relative_to(ROOT).as_posix(), "layout_report_sha256": sha(LAYOUT),
        "source_discovery_path": DISCOVERY.relative_to(ROOT).as_posix(), "source_discovery_sha256": sha(DISCOVERY),
        "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
        "schema_elf_sha256": inv["schema_elf_sha256"],
        "interpretation": "Exact field offsets/sizes are emitted only when a compiler-selected source declaration compiled and its constants decoded from the R5900 object. Schema classifications are intentionally unchanged; no byte range is deemed safe or removable.",
        "summary": {
            "unclassified_ranges": len(range_rows),
            "ranges_with_compiler_mapped_member": sum(bool(r["candidate_c_members"]) for r in range_rows),
            "ranges_without_mapped_member": sum(not r["candidate_c_members"] for r in range_rows),
            "ranges_with_partial_member_overlap": sum(any(c["relation"] == "partially-overlaps-range" for c in r["candidate_c_members"]) for r in range_rows),
            "definitions_with_compiled_field_offsets": sum(p.get("status") == "passed" for p in probes.values()),
            "definitions_without_compiled_field_offsets": [n for n,p in probes.items() if p.get("status") != "passed"],
        },
        "type_probes": probes,
        "ranges": range_rows,
    }
    out = args.output if args.output.is_absolute() else ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
