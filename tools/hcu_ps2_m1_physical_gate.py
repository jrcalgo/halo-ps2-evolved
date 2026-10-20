"""Join exact HCU link placement with interpreter/recompiler guest evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_toolchain import ROOT
from test_hcu_boot import linked_physical_evidence, physical_memory_evidence, sha


def evaluate(probe_path: Path, run_paths: list[Path]) -> dict:
    probe = json.loads(probe_path.read_text())
    machine = probe["hcu_gameplay_machine"]
    elf = ROOT / machine["elf"]["path"]
    errors = []
    if sha(elf) != machine["elf"]["sha256"]:
        errors.append("linked machine ELF hash differs from probe")
    if machine["elf"]["undefined_symbol_count"] != 0:
        errors.append("linked machine has unresolved imports")
    if not machine["physical_placement"]["necessary_conditions_pass"]:
        errors.append("static physical placement lower bound fails")
    modes = set()
    runs = []
    for path in run_paths:
        run = json.loads(path.read_text())
        mode = run.get("mode")
        if mode in modes:
            errors.append(f"duplicate guest mode {mode}")
        modes.add(mode)
        if run.get("status") != "passed" or run.get("stage") != "m3-memory-ready":
            errors.append(f"{mode}: guarded memory-ready boundary did not pass")
        if run.get("elf_sha256") != machine["elf"]["sha256"]:
            errors.append(f"{mode}: guest ran a different ELF")
        log_path = Path(run["log"])
        log = log_path.read_text(errors="replace")
        if "HALO_PS2_LOCAL memory-ready canaries=10" not in log:
            errors.append(f"{mode}: required canary-checked marker absent")
        physical = physical_memory_evidence(log)
        if physical is None or physical != run.get("physical_memory"):
            errors.append(f"{mode}: recorded physical intervals differ from guest log")
            continue
        linked = linked_physical_evidence(physical, elf, probe_path)
        if not linked["passed"]:
            errors.append(f"{mode}: linked ELF and guest intervals disagree")
        runs.append({"mode": mode, "result": str(path),
                     "guest_log": str(log_path),
                     "boot_start": physical["boot_start"],
                     "boot_end": physical["boot_end"],
                     "allocator_gap_bytes": physical["allocator_gap_bytes"],
                     "headroom_before_reserve_bytes": physical["headroom_bytes"],
                     "stack": physical["kernel_stack"],
                     "arena_high_water": {
                         row["name"]: row["high"] for row in physical["arenas"]},
                     "linked_checks": linked["checks"]})
    if modes != {"interpreter", "recompiler"}:
        errors.append("both interpreter and recompiler evidence are required")
    return {"gate": "closed" if not errors else "open",
            "machine_elf_sha256": machine["elf"]["sha256"],
            "probe": str(probe_path), "runs": runs, "errors": errors,
            "limits": ["PCSX2 proves this boot image's placement, not physical-console OPL storage.",
                       "Memory-ready precedes map loading, rendering, and CE gameplay startup."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path,
                        default=ROOT / "build/hcu-parent-link-probe/result.json")
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/hcu-ps2-closure/m1-physical-placement-gate.json")
    args = parser.parse_args()
    result = evaluate(args.probe, args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"M1 physical placement gate {result['gate']}: "
          f"{len(result['runs'])} guest runs, {len(result['errors'])} errors")
    for error in result["errors"]:
        print("  " + error)
    if result["gate"] != "closed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
