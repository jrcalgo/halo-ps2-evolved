#!/usr/bin/env python3
"""Refresh a parent-link JSON report from an already-built, retained ELF.

This is a readelf/nm reporting pass only; it never compiles or links. It exists
so a changed memory budget can be applied to the exact selected ELF without
rebuilding that image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_parent_link_probe as probe  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--memory-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.input = args.input.resolve()
    args.elf = args.elf.resolve()
    args.map = args.map.resolve()
    args.memory_audit = args.memory_audit.resolve()
    args.output = args.output.resolve()

    report = json.loads(args.input.read_text())
    audit = json.loads(args.memory_audit.read_text())
    manifest_path = args.output.parent / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    readelf = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-readelf"
    nm = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-nm"
    headers = subprocess.check_output([str(readelf), "-lW", str(args.elf)], text=True)
    loads = probe.load_segment_intervals(headers)
    file_bytes, memory_bytes = probe.load_segment_sizes(headers)
    symbols = probe.named_symbols(
        subprocess.check_output([str(nm), "-n", str(args.elf)], text=True),
        {"_ftext", "_fbss", "_end", "_stack", "_stack_size", "_heap_size"})
    capacity = probe._budget_region_bytes("elf_static")
    resident = probe._budget_region_bytes("resident_gameplay")
    elf_record = report["hcu_gameplay_machine"]["elf"]
    elf_record.update({
        "path": str(args.elf.relative_to(ROOT)),
        "sha256": sha256(args.elf),
        "load_segment_file_bytes": file_bytes,
        "load_segment_memory_bytes_including_bss": memory_bytes,
        "elf_static_capacity": capacity,
        "elf_static_overage": max(0, file_bytes - capacity),
        "elf_static_margin_bytes": capacity - file_bytes,
        "elf_static_memory_overage_including_bss": max(0, memory_bytes - capacity),
        "bss_bytes": elf_record["sections"].get(".bss", 0),
        "nobits_bytes": memory_bytes - file_bytes,
        "resident_gameplay_capacity_bytes": resident,
        "resident_gameplay_after_nobits_bytes": resident - (memory_bytes - file_bytes),
        "resident_gameplay_nobits_fits": memory_bytes - file_bytes <= resident,
    })
    game = report["hcu_gameplay_machine"]
    game["physical_placement"] = probe.physical_placement(loads, symbols)
    game["memory_ledger"].update({
        "report": str(args.memory_audit.relative_to(ROOT)),
        "report_sha256": sha256(args.memory_audit),
        "elf_sha256": sha256(args.elf),
        "map": str(args.map.relative_to(ROOT)),
        "map_sha256": sha256(args.map),
        "memory_map_sha256": sha256(ROOT / "config/hcu-ps2-memory-map.json"),
        "candidate_allocated_bytes_by_region": audit["candidate_allocated_bytes_by_region"],
        "candidate_regions_over_capacity": audit["candidate_regions_over_capacity"],
        "unassigned_owners": audit["unassigned_owners"],
        "bss_bytes_by_input_object": audit["bss_bytes_by_input_object"],
        "warning": audit["warning"],
    })
    report["source_inputs"]["memory_map_sha256"] = sha256(ROOT / "config/hcu-ps2-memory-map.json")
    report["source_inputs"]["hcu_profile"] = str(args.output.parent.relative_to(ROOT))
    archived_objects = manifest.get("archived_link_objects", {})
    for group, rows in (("parent", report["source_inputs"].get("parent_object_sha256", {})),
                        ("parent", game.get("parent_object_sha256", {})),
                        ("hcu", report["source_inputs"].get("hcu_object_sha256", {}))):
        for original_path, expected_sha in list(rows.items()):
            archived = archived_objects.get(original_path)
            if archived and archived.get("sha256") == expected_sha:
                rows[archived["path"]] = rows.pop(original_path)
    report["source_inputs"]["hcu_rooted_object"] = str(args.output.parent.relative_to(ROOT) / "rooted.o")
    report["hcu_gameplay_machine"]["partition_profile"] = game["partition_profile"]
    # The companion parent-viewer ELF is not the selected runtime image and was
    # not retained. Recompute only its capacity comparison from the exact LOAD
    # counters captured by the original link report; preserve its original hash.
    parent_elf = report["elf"]
    parent_file = int(parent_elf["load_segment_file_bytes"])
    parent_memory = int(parent_elf["load_segment_memory_bytes_including_bss"])
    parent_elf.update({
        "elf_static_capacity": capacity,
        "elf_static_overage": max(0, parent_file - capacity),
        "elf_static_margin_bytes": capacity - parent_file,
        "elf_static_memory_overage_including_bss": max(0, parent_memory - capacity),
        "retained": False,
        "path_at_link": parent_elf.get("path"),
        "path": None,
    })
    report["report_refresh"] = {
        "mode": "readelf-only; no compile or link",
        "input_probe_report_sha256": sha256(args.input),
        "selected_elf_sha256": sha256(args.elf),
        "generator": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": sha256(Path(__file__)),
        "budget_sha256": sha256(ROOT / "config/memory-budget.json"),
        "memory_map_sha256": sha256(ROOT / "config/hcu-ps2-memory-map.json"),
        "unretained_parent_elf_metrics_source": "original probe report counters; selected runtime ELF was freshly parsed from retained bytes",
        "original_manifest_probe_report_sha256": manifest.get("probe_report_sha256"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
