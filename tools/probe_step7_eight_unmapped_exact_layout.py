#!/usr/bin/env python3
"""Compile exact R5900 offsetof/sizeof assertions for the eight BSP gaps.

Unlike the source-name crosswalk, this probe includes the actual schema
translation unit and rejects the run unless every emitted member offset and
extent matches the serialized gap. It proves layout ownership only.
"""
from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_toolchain import environment as toolchain_environment  # noqa: E402

SCHEMA_SOURCE = ROOT / "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c"
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
DEFAULT_OUTPUT = ROOT / "docs/reports/m2-step7-eight-unmapped-exact-layout-2026-10-22.json"

# type spelling, expected size, fields and expected (offset, size)
ASSERTIONS = {
    "detail_object_cell": ("struct detail_object_cell_definition", 32, {
        "cell_x": (0, 2), "cell_y": (2, 2), "cell_z": (4, 2), "offset_z": (6, 2),
        "valid_layers": (8, 4), "start_index": (12, 4), "count_index": (16, 4), "unused14": (20, 12),
    }),
    "detail_object_count": ("word", 2, {}),
    "detail_object_z_reference_vector": ("real_vector4d", 16, {
        "i": (0, 4), "j": (4, 4), "k": (8, 4), "l": (12, 4),
    }),
    # The complete C record also contains the serialized shader reference and
    # points block following this 36-byte schema gap.
    "structure_mirror": ("struct structure_mirror", 64, {"plane": (0, 16), "unused": (16, 20)}),
    "structure_node": ("byte_rectangle3d", 6, {
        "x0": (0, 1), "x1": (1, 1), "y0": (2, 1), "y1": (3, 1), "z0": (4, 1), "z1": (5, 1),
    }),
    # surface_indices is the following 12-byte tag_block, outside this gap.
    "structure_subcluster": ("struct structure_subcluster", 36, {"world_bounds": (0, 24)}),
    "byte": ("byte", 1, {}),
    "long": ("long", 4, {}),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build, prefix, env, _ = toolchain_environment()
    closure = build / "hcu-ps2-closure/all-no-bootstrap-memory"
    result = json.loads((closure / "result.json").read_text())
    hcu = ROOT / "submodules/halo-ce-universal"
    port = json.loads((hcu / "port/ps2/port.json").read_text())
    includes = ["-I" + str(hcu / p) for p in port["include_dirs"]]
    includes += ["-I" + str(prefix / "ps2sdk/common/include"), "-I" + str(prefix / "ps2sdk/ee/include")]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    semantics = closure / "halo_ps2_msvc_semantics.h"
    prelude = hcu / port["prefix"]
    outdir = build / "hcu-step7-step8-c0/eight-exact-layout"
    outdir.mkdir(parents=True, exist_ok=True)
    probe = outdir / "eight_exact_layout.c"
    lines = ['#include "cseries.h"', f'#include "{SCHEMA_SOURCE}"']
    for key, (ctype, expected_size, fields) in ASSERTIONS.items():
        lines.append(f'typedef char size_{key}[(sizeof({ctype}) == {expected_size}) ? 1 : -1];')
        for field, (offset, size) in fields.items():
            lines.append(f'typedef char offset_{key}_{field}[(__builtin_offsetof({ctype}, {field}) == {offset}) ? 1 : -1];')
            lines.append(f'typedef char extent_{key}_{field}[(sizeof((({ctype} *)0)->{field}) == {size}) ? 1 : -1];')
    probe.write_text("\n".join(lines) + "\n")
    obj = probe.with_suffix(".o")
    command = [str(compiler), *result["flags"], *includes, "-include", str(prelude), "-include", str(semantics), "-c", str(probe), "-o", str(obj)]
    run = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    inv = json.loads(INVENTORY.read_text())
    inventory_rows = {r["definition"]: r for r in inv["members"] if r["classification"] == "unclassified"}
    mapped_ranges = []
    for name, (ctype, expected_size, fields) in ASSERTIONS.items():
        row = inventory_rows[name]
        if row["offset_within_definition"] != 0 or row["size"] != expected_size and name not in {"structure_mirror", "structure_subcluster"}:
            raise ValueError(f"inventory extent disagrees for {name}: {row}")
        gap_size = row["size"]
        member_rows = []
        for field, (offset, size) in fields.items():
            if offset >= gap_size or offset + size > gap_size:
                raise ValueError(f"member extent lies outside inventory gap: {name}.{field}")
            member_rows.append({"name": field, "offset": offset, "size": size,
                                "relation": "fully-contained-by-range"})
        if not fields:
            member_rows = [{"name": "value", "offset": 0, "size": expected_size,
                            "relation": "fully-contained-by-range", "kind": "scalar-type-extent"}]
        mapped_ranges.append({"definition": name, "definition_id": row["definition_id"],
                              "inventory_path": row["path"], "schema_range": {"offset": 0, "size": gap_size},
                              "type": ctype, "type_size": expected_size, "members": member_rows,
                              "classification": "compiler_owned_layout", "semantic_disposition": "open_schema_gap"})
    report = {
        "format": "hcu-step7-eight-unmapped-exact-layout-v1",
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha(INVENTORY),
        "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
        "schema_source": SCHEMA_SOURCE.relative_to(ROOT).as_posix(),
        "schema_source_sha256": sha(SCHEMA_SOURCE),
        "schema_source_report_path": "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json",
        "schema_source_report_sha256": sha(ROOT / "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json"),
        "probe_source": probe.relative_to(ROOT).as_posix(),
        "probe_source_sha256": sha(probe),
        "probe_object": obj.relative_to(ROOT).as_posix() if obj.exists() else None,
        "probe_object_sha256": sha(obj) if obj.exists() else None,
        "assertion_sets": {name: {"type": typ, "size": size,
                                  "members": {field: {"offset": pair[0], "size": pair[1]} for field, pair in fields.items()}}
                           for name, (typ, size, fields) in ASSERTIONS.items()},
        "ranges": mapped_ranges,
        "status": "passed" if run.returncode == 0 else "failed",
        "diagnostics": run.stdout + run.stderr,
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if run.returncode == 0:
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
