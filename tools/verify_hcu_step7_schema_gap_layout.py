#!/usr/bin/env python3
"""Compile source-layout checks for CE types represented in the BSP schema.

This verifies only whole-type sizeof values. It intentionally does not assign
member names to schema gaps or infer that any bytes may be discarded.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json")
    parser.add_argument("--discovery", type=Path, default=ROOT / "docs/reports/m2-step7-schema-gap-source-discovery-2026-10-22.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/reports/m2-step7-schema-gap-layout-2026-10-22.json")
    args = parser.parse_args()
    inv = json.loads(args.inventory.read_text())
    discovery = json.loads(args.discovery.read_text())
    build, prefix, env, _jobs = toolchain_environment()
    closure_dir = build / "hcu-ps2-closure/all-no-bootstrap-memory"
    result = json.loads((closure_dir / "result.json").read_text())
    hcu_root = ROOT / "submodules/halo-ce-universal"
    port = json.loads((hcu_root / "port/ps2/port.json").read_text())
    include_dirs = ["-I" + str(hcu_root / x) for x in port["include_dirs"]]
    include_dirs += ["-I" + str(prefix / "ps2sdk/common/include"), "-I" + str(prefix / "ps2sdk/ee/include")]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    semantics = closure_dir / "halo_ps2_msvc_semantics.h"
    prefix_header = hcu_root / port["prefix"]
    units = result["units"]

    declaration_by_type = {}
    for gap in discovery["gaps"]:
        choices = []
        for declaration in gap["source_declarations"]:
            absolute = hcu_root / declaration["path"].removeprefix("submodules/halo-ce-universal/") if declaration["path"].startswith("submodules/halo-ce-universal/") else ROOT / declaration["path"]
            rel = absolute.relative_to(hcu_root).as_posix()
            unit_key = "source/" + rel
            active = absolute.suffix == ".h" or (unit_key in units and units[unit_key]["status"] == "compiled")
            choices.append((0 if absolute.suffix == ".h" else 1, 0 if active else 1, absolute, declaration, unit_key, active))
        choices.sort(key=lambda item: (item[1], item[0], str(item[2])))
        if choices:
            declaration_by_type[gap["definition"]] = choices[0]

    # Each original translation unit is included in a small probe TU, allowing
    # its private file-scope declarations to remain visible to sizeof checks.
    groups = {}
    types_without_source = []
    for definition in sorted({g["definition"] for g in discovery["gaps"]}):
        choice = declaration_by_type.get(definition)
        if not choice:
            types_without_source.append(definition)
            continue
        _pa, _active, source, declaration, unit_key, active = choice
        if source.suffix == ".c":
            groups.setdefault(("source", source), []).append((definition, declaration, unit_key, active))
        else:
            groups.setdefault(("header", source), []).append((definition, declaration, unit_key, active))

    probe_root = build / "hcu-step7-step8-c0/schema-gap-layout"
    probe_root.mkdir(parents=True, exist_ok=True)
    type_results = {}
    group_results = []
    for index, ((kind, source_path), members) in enumerate(sorted(groups.items(), key=lambda x: str(x[0][1]))):
        probe = probe_root / f"layout_{index:02d}.c"
        lines = ['#include "cseries.h"']
        lines.append(f'#include "{source_path.as_posix()}"')
        for i, (name, _declaration, _unit, _active) in enumerate(members):
            expected = next(d["serialized_size"] for d in inv["definitions"] if d["name"] == name)
            tag = _declaration.get("tag_kind", "struct")
            lines.append(f'typedef char hcu_sizeof_{i}[(sizeof({tag} {name}) == {expected}) ? 1 : -1];')
        probe.write_text("\n".join(lines) + "\n")
        obj = probe.with_suffix(".o")
        command = [str(compiler), *result["flags"], *include_dirs,
                   "-include", str(prefix_header), "-include", str(semantics),
                   "-c", str(probe), "-o", str(obj)]
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        group_status = "passed" if completed.returncode == 0 else "failed"
        group_results.append({"translation_unit_kind": kind, "source": str(source_path.relative_to(ROOT)),
                              "probe_source": str(probe.relative_to(ROOT)), "probe_source_sha256": sha256(probe),
                              "object": str(obj.relative_to(ROOT)) if obj.exists() else None,
                              "object_sha256": sha256(obj) if obj.exists() else None,
                              "command": command, "status": group_status,
                              "diagnostics": completed.stdout + completed.stderr})
        for i, (name, declaration, unit_key, active) in enumerate(members):
            expected = next(d["serialized_size"] for d in inv["definitions"] if d["name"] == name)
            type_results[name] = {"status": group_status, "expected_schema_size": expected,
                                  "tag_kind": declaration.get("tag_kind", "struct"),
                                  "declaration": declaration, "source_unit_in_closure": unit_key if unit_key in units else None,
                                  "source_unit_status": units.get(unit_key, {}).get("status") if unit_key else None,
                                  "probe": str(probe.relative_to(ROOT)), "probe_object": str(obj.relative_to(ROOT)) if obj.exists() else None}

    range_rows = []
    for gap in discovery["gaps"]:
        layout = type_results.get(gap["definition"])
        range_rows.append({**gap, "sizeof_status": layout["status"] if layout else "no-source-declaration-found",
                           "sizeof_evidence": layout,
                           "byte_range_classification": "unclassified",
                           "semantic_consumer_disposition": "unresolved"})
    output = {"format": "hcu-step7-schema-gap-layout-v1", "inventory": str(args.inventory.relative_to(ROOT)),
              "inventory_sha256": sha256(args.inventory), "source_discovery": str(args.discovery.relative_to(ROOT)),
              "source_discovery_sha256": sha256(args.discovery), "schema_elf_sha256": inv["schema_elf_sha256"],
              "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
              "exact_source_rebuild": {"status": result["status"], "compiled_units": result["compiled_count"],
                                       "failed_units": result["failed_count"]},
              "type_size_results": type_results, "probe_groups": group_results,
              "ranges": range_rows,
              "summary": {"range_count": len(range_rows),
                          "sizeof_passed_ranges": sum(r["sizeof_status"] == "passed" for r in range_rows),
                          "sizeof_failed_ranges": sum(r["sizeof_status"] == "failed" for r in range_rows),
                          "ranges_unclassified": len(range_rows),
                          "note": "Whole-type sizeof agreement does not identify individual bytes, prove preservation, or establish safe removal. Member-offset assertions and consumer dispositions remain required."}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
