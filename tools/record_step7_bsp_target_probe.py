#!/usr/bin/env python3
"""Verify and summarize paired PCSX2 runs of the 13-map CE BSP probe.

The runner consumes guest logs/result records produced by
tools/test_hcu_step7_path_guest.py. It does not synthesize target evidence:
every accepted row must be present in the retained PCSX2 log for both backends.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_hcu_mp_capacity import MP_PACKAGE_SHA256, MP_SOURCE_SHA256  # noqa: E402
MAPS = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
        "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
        "sidewinder", "wizard")
QUERY = re.compile(
    r"HALO_PS2_LOCAL step8-mp-capacity-query map=(\w+) clusters=(\d+) "
    r"pvs_rows=(\d+) collision_called=(\d+) collision_hit=(\d+) "
    r"collision_surface=(-?\d+) collision_material_type=(-?\d+)")
UNLOADED = re.compile(r"HALO_PS2_LOCAL step8-mp-capacity-unloaded map=(\w+) guards=ok")
PATH = re.compile(
    r"HALO_PS2_LOCAL step8-mp-path map=(\w+) start=(-?\d+) goal=(-?\d+) "
    r"explored=(\d+) chain_nodes=(\d+) root=(-?\d+) reached=(\d+)")
COMPLETE = "HALO_PS2_LOCAL step8-mp-capacity-complete maps=13 query_only=1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_run(run_dir: Path, mode: str) -> dict:
    result_path = run_dir / "result.json"
    log_path = run_dir / "emulog.txt"
    validation_path = run_dir / "step7-path-validation.json"
    if not result_path.is_file() or not log_path.is_file() or not validation_path.is_file():
        raise ValueError(f"{run_dir}: missing result, guest log, or path-validation record")
    result = json.loads(result_path.read_text())
    log = log_path.read_text(errors="replace")
    path_validation = json.loads(validation_path.read_text())
    if result.get("status") != "passed" or result.get("mode") != mode:
        raise ValueError(f"{run_dir}: result status/mode is not passed/{mode}")
    if result.get("required_success_marker") != COMPLETE or COMPLETE not in log:
        raise ValueError(f"{run_dir}: missing all-map completion marker")
    if "HALO_PS2_FAIL" in log or result.get("host_assets_unchanged") is not True:
        raise ValueError(f"{run_dir}: guest failure or changed host assets")
    elf_sha = result.get("elf_sha256")
    if not elf_sha or path_validation.get("elf_sha256") != elf_sha:
        raise ValueError(f"{run_dir}: ELF identity differs across retained records")
    queries = QUERY.findall(log)
    unloaded = UNLOADED.findall(log)
    routes = PATH.findall(log)
    if len(queries) != len(MAPS) or len(unloaded) != len(MAPS) or len(routes) != len(MAPS):
        raise ValueError(f"{run_dir}: expected 13 query/unload/path rows; got "
                         f"{len(queries)}/{len(unloaded)}/{len(routes)}")
    if [r[0] for r in queries] != list(MAPS) or unloaded != list(MAPS) or \
       [r[0] for r in routes] != list(MAPS):
        raise ValueError(f"{run_dir}: duplicate, missing, or unordered map rows")
    oracle_path = ROOT / "build/mp-collision-shared-edge-source-oracle.json"
    oracle = json.loads(oracle_path.read_text())
    if set(oracle) != set(MAPS):
        raise ValueError("source collision oracle does not cover the exact 13 stock maps")
    query_rows = []
    for row in queries:
        name, clusters, pvs_rows, collision_called, collision_hit, surface, material = row
        expected = oracle[name]["bsps"][0]["qualified"][0]
        if int(surface) != expected["selected"] or int(material) != expected["material_type"]:
            raise ValueError(f"{run_dir}: collision hit differs from independent source oracle for {name}")
        if int(clusters) <= 0 or int(pvs_rows) != int(clusters) or \
           collision_called != "1" or collision_hit != "1":
            raise ValueError(f"{run_dir}: failed PVS/collision result for {name}: {row}")
        query_rows.append({"map": name, "cluster_count": int(clusters),
                           "pvs_rows_queried": int(pvs_rows),
                           "collision_called": True, "collision_hit": True,
                           "collision_surface": int(surface),
                           "collision_material_type": int(material)})
    if len(path_validation.get("ce_astar_routes", [])) != len(MAPS):
        raise ValueError(f"{run_dir}: path validator does not report 13 routes")
    map_inputs = []
    for name in MAPS:
        source_map = ROOT / f"build/retail-maps/decompressed/{name}.map"
        package = ROOT / f"build/hcu-parent-link-probe/maps/{name}.hp2"
        source_hash, package_hash = sha(source_map), sha(package)
        if source_hash != MP_SOURCE_SHA256[name] or package_hash != MP_PACKAGE_SHA256[name]:
            raise ValueError(f"{run_dir}: stock source/package pin changed for {name}")
        map_inputs.append({
            "map": name,
            "source_map_path": source_map.relative_to(ROOT).as_posix(),
            "source_map_sha256": source_hash,
            "package_path": package.relative_to(ROOT).as_posix(),
            "package_sha256": package_hash,
        })
    return {
        "mode": mode,
        "status": "passed",
        "run_directory": run_dir.relative_to(ROOT).as_posix(),
        "elf_path": result["elf_path"],
        "elf_sha256": elf_sha,
        "result_sha256": sha(result_path),
        "guest_log_path": log_path.relative_to(ROOT).as_posix(),
        "guest_log_sha256": sha(log_path),
        "path_validation_path": validation_path.relative_to(ROOT).as_posix(),
        "path_validation_sha256": sha(validation_path),
        "emulator_sha256": result.get("emulator_sha256"),
        "bios_sha256": result.get("bios_sha256"),
        "settings_sha256": result.get("settings_sha256"),
        "host_assets_unchanged": result["host_assets_unchanged"],
        "query_rows": query_rows,
        "unload_guard_rows": len(unloaded),
        "path_rows": len(routes),
        "completion_marker": COMPLETE,
        "collision_oracle_path": oracle_path.relative_to(ROOT).as_posix(),
        "collision_oracle_sha256": sha(oracle_path),
        "map_inputs": map_inputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interpreter-run", type=Path, required=True)
    parser.add_argument("--recompiler-run", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json")
    args = parser.parse_args()
    runs = [inspect_run(args.interpreter_run.resolve(), "interpreter"),
            inspect_run(args.recompiler_run.resolve(), "recompiler")]
    if runs[0]["elf_sha256"] != runs[1]["elf_sha256"]:
        raise ValueError("interpreter/recompiler runs must use the same exact ELF")
    report = {
        "schema": "hcu-m2-step7-bsp-current-target-probe-v1",
        "status": "passed-paired-pcsx2-diagnostic",
        "scope": "13 stock multiplayer map CBSPs, one deterministic CE collision hit and every cluster PVS row per map, one CE path route per map; no campaign, rendering, bots, or hardware claim",
        "elf_sha256": runs[0]["elf_sha256"],
        "build_report_path": "build/hcu-parent-link-probe/result-step8-mp-capacity-tagcache-4477120.json",
        "build_report_sha256": sha(ROOT / "build/hcu-parent-link-probe/result-step8-mp-capacity-tagcache-4477120.json"),
        "recorder_path": "tools/record_step7_bsp_target_probe.py",
        "recorder_sha256": sha(Path(__file__).resolve()),
        "probe_source_path": "submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c",
        "probe_source_sha256": sha(ROOT / "submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c"),
        "code_inputs": [{
            "path": path,
            "sha256": sha(ROOT / path),
        } for path in (
            "submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c",
            "submodules/halo-ce-universal/source/physics/collisions.c",
            "submodules/halo-ce-universal/source/physics/collision_bsp.c",
            "submodules/halo-ce-universal/source/ai/path.c",
            "submodules/halo-ce-universal/source/ai/path_structure_bsp.c",
            "tools/test_hcu_step7_path_guest.py",
            "tests/test_hcu_mp_capacity.py",
        )],
        "map_order": list(MAPS),
        "runs": runs,
        "consumer_members_invoked": [
            {"member": "structure_bsp.clusters", "consumer": "structure_bsp_get_cluster_pvs; loop bound and cluster indices", "source": "submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c"},
            {"member": "structure_bsp.cluster_data", "consumer": "structure_bsp_get_cluster_pvs; cluster visibility bitvectors", "source": "submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c"},
            {"member": "structure_bsp.collision_bsp", "consumer": "collision_test_vector -> collision_bsp_test_vector", "source": "submodules/halo-ce-universal/source/physics/collisions.c"},
            {"member": "collision_bsp.bsp3d.nodes", "consumer": "3D collision tree traversal", "source": "submodules/halo-ce-universal/source/physics/collision_bsp.c"},
            {"member": "collision_bsp.bsp3d.planes", "consumer": "collision plane lookup during 3D tree traversal", "source": "submodules/halo-ce-universal/source/physics/collision_bsp.c"},
            {"member": "collision_bsp.leaves", "consumer": "collision leaf lookup in vector collision traversal", "source": "submodules/halo-ce-universal/source/physics/collision_bsp.c"},
            {"member": "collision_bsp.bsp2d_references", "consumer": "2D collision routing from leaves", "source": "submodules/halo-ce-universal/source/physics/collision_bsp.c"},
            {"member": "collision_bsp.bsp2d.nodes", "consumer": "2D collision tree traversal", "source": "submodules/halo-ce-universal/source/physics/collision_bsp.c"},
            {"member": "collision_bsp.surfaces", "consumer": "vector collision surface selection", "source": "submodules/halo-ce-universal/source/physics/collision_bsp.c"},
            {"member": "structure_bsp.collision_materials", "consumer": "collision_structure_material_type; returned material checked against source oracle", "source": "submodules/halo-ce-universal/source/physics/collisions.c"},
            {"member": "structure_bsp.pathfinding_surfaces", "consumer": "CE A* path search over retained retail routes", "source": "submodules/halo-ce-universal/source/ai/path.c; submodules/halo-ce-universal/source/ai/path_structure_bsp.c"},
            {"member": "structure_bsp.pathfinding_edges", "consumer": "CE A* route adjacency traversal", "source": "submodules/halo-ce-universal/source/ai/path.c; submodules/halo-ce-universal/source/ai/path_structure_bsp.c"}
        ],
        "limits": [
            "The query executes real CE consumers after scenario_load publishes each retail CBSP. One deterministic hit per map does not visit every collision record or prove malformed-data handling for every member.",
            "The PVS loop invokes CE for every cluster index and requires every returned row to be non-null. It does not establish visual submission or pixel correctness.",
            "A* uses one predetermined successful route per map; it is not an AI actor steering workload.",
            "The diagnostic ELF uses the opt-in MP capacity path and does not qualify ordinary production admission, renderer residency, 5,767,168-byte reserve, or physical hardware behavior.",
            "This report covers only the explicitly listed members and tested call paths. Other BSP consumers, opaque ranges, and open dispositions remain governed by the current generated crosswalk and inventory; no whole-inventory closure is claimed."
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown = args.output.with_suffix(".md")
    markdown_lines = [
        "# M2 Step 7 current target BSP consumer probe",
        "",
        "## Result",
        "",
        "PCSX2 interpreter passed and PCSX2 recompiler passed the deterministic 13-map CE BSP query on the same exact ELF. Each map emitted one positive CE collision hit with the expected retail surface/material, queried every cluster PVS row, completed its retained A* route, unloaded its scenario, and passed guard checks. These are diagnostic runs using the opt-in MP capacity profile.",
        "",
        f"ELF SHA-256: `{report['elf_sha256']}`. The machine-readable evidence with run, emulator, BIOS, settings, result, guest-log, and validator hashes is `{markdown.with_suffix('.json').relative_to(ROOT).as_posix()}`.",
        "",
        "| Backend | Result SHA-256 | Guest log SHA-256 | Query rows | Unload/guard rows | Path rows |",
        "|---|---|---|---:|---:|---:|",
    ]
    for run in runs:
        markdown_lines.append(
            f"| PCSX2 {run['mode']} passed | `{run['result_sha256']}` | `{run['guest_log_sha256']}` | {len(run['query_rows'])}/13 | {run['unload_guard_rows']}/13 | {run['path_rows']}/13 |")
    markdown_lines += [
        "",
        "## Exact BSP members exercised",
        "",
        "The loaded retail CBSP is published by `scenario_load()` before these real CE calls execute. `structure_bsp_get_cluster_pvs()` reads `structure_bsp.clusters` and `structure_bsp.cluster_data` for every cluster index. `collision_test_vector()` calls `collision_bsp_test_vector()` and checks the selected `structure_bsp.collision_materials` result against the source oracle. The positive hit executes the 3D BSP traversal and selected 2D/surface route.",
        "",
        "| Exact inventory member | Executed consumer / evidence |",
        "|---|---|",
    ]
    for item in report["consumer_members_invoked"]:
        markdown_lines.append(f"| `{item['member']}` | `{item['consumer']}`; `{item['source']}` |")
    markdown_lines += [
        "",
        "## Limits",
        "",
        *[f"- {limit}" for limit in report["limits"]],
        "",
        "The original test ELF source prints `step8-mp-capacity-query`, `step8-mp-capacity-unloaded`, and the completion marker only after its assertions. The capture and acceptance parser are `tools/test_hcu_step7_path_guest.py`; this summary validator is `tools/record_step7_bsp_target_probe.py`.",
        "",
    ]
    markdown.write_text("\n".join(markdown_lines))
    print(json.dumps({"status": report["status"], "elf_sha256": report["elf_sha256"],
                      "runs": [{"mode": r["mode"], "log_sha256": r["guest_log_sha256"],
                                "query_rows": len(r["query_rows"])} for r in runs],
                      "report": str(args.output.relative_to(ROOT)),
                      "report_sha256": sha(args.output),
                      "markdown": str(markdown.relative_to(ROOT)),
                      "markdown_sha256": sha(markdown)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"step7 BSP target probe record failed: {error}", file=sys.stderr)
        raise SystemExit(1)
