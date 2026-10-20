"""Close the logical HCU M0 owner gate for one exact combined machine link.

This gate joins the reviewed rooted-symbol ledger to the parent/HCU ELF and
map-range allocation audit by hashes. It intentionally does not claim physical
EE placement, runtime high-water, PCSX2 boot, or retail-map fit; those belong to
the subsequent M1/M2 gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from build_toolchain import ROOT


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def validate_high_water(records: dict, capacities: dict, link_bytes: int) -> list[str]:
    errors = []
    if set(records) != set(capacities):
        return ["high-water evidence does not cover exactly the budget regions"]
    for name, row in records.items():
        kind, size = row.get("kind"), row.get("bytes")
        if kind == "unknown":
            if size is not None or not row.get("reason"):
                errors.append(f"{name}: unknown high-water needs a reason and null bytes")
        elif kind == "link-measured":
            if name != "elf_static" or size is not None or not row.get("evidence"):
                errors.append(f"{name}: invalid link-measured high-water record")
            elif link_bytes > capacities[name]:
                errors.append(f"{name}: linked static bytes exceed capacity")
        elif kind == "host-fixture":
            if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > capacities[name] or not row.get("evidence"):
                errors.append(f"{name}: invalid host-fixture high-water record")
        elif kind == "reserved":
            if name != "uncommitted_reserve" or size != 0 or not row.get("evidence"):
                errors.append(f"{name}: invalid reserved high-water record")
        else:
            errors.append(f"{name}: unknown high-water evidence kind {kind!r}")
    return errors


def evaluate() -> dict:
    checks: list[str] = []
    errors: list[str] = []
    output = ROOT / "build/hcu-ps2-closure/m0-ownership-gate.json"
    closure_path = ROOT / "build/hcu-ps2-closure/all/result.json"
    rooted_path = ROOT / "build/hcu-ps2-closure/all/rooted.o"
    external_path = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"
    probe_path = ROOT / "build/hcu-parent-link-probe/result.json"
    budget_path = ROOT / "config/memory-budget.json"
    memory_map_path = ROOT / "config/hcu-ps2-memory-map.json"
    allocation_doc = ROOT / "docs/hcu-source-backed-review/m0-allocation-ownership.md"

    paths = (closure_path, rooted_path, external_path, probe_path, budget_path,
             memory_map_path, allocation_doc)
    for path in paths:
        if not path.is_file():
            errors.append(f"missing M0 input: {path.relative_to(ROOT)}")
    if errors:
        return {"gate": "open", "checks": checks, "errors": errors}

    closure = load(closure_path)
    review = load(external_path)
    probe = load(probe_path)
    budget = load(budget_path)
    memory_map = load(memory_map_path)
    source_inputs = probe.get("source_inputs", {})
    for name, path in (("halo_ce_universal_head", ROOT / "submodules/halo-ce-universal"),
                       ("halo_ps2_head", ROOT / "submodules/halo-ps2")):
        if source_inputs.get(name) != git_head(path):
            errors.append(f"combined image was built from a different {name} source pin")
    if not errors:
        checks.append("combined-image submodule pins match the current source commits")
    machine = probe.get("hcu_gameplay_machine", {})
    ledger = machine.get("memory_ledger", {})
    check_path = ROOT / ledger.get("report", "")
    elf_path = ROOT / machine.get("elf", {}).get("path", "")
    map_path = ROOT / ledger.get("map", "")

    for path in (check_path, elf_path, map_path):
        if not path.is_file():
            errors.append(f"missing linked-image audit input: {path}")
    if errors:
        return {"gate": "open", "checks": checks, "errors": errors}
    audit = load(check_path)

    rooted_hash = sha256(rooted_path)
    if review.get("rooted_sha256") != rooted_hash:
        errors.append("external-review ledger is not bound to the current rooted object")
    if probe.get("source_inputs", {}).get("hcu_rooted_sha256") != rooted_hash:
        errors.append("combined machine probe used a different HCU rooted object")
    else:
        checks.append("external ledger and combined machine use the same rooted-object hash")

    if machine.get("elf", {}).get("undefined_symbol_count") != 0:
        errors.append("combined machine ELF has unresolved imports")
    if sha256(elf_path) != machine.get("elf", {}).get("sha256"):
        errors.append("combined machine ELF hash differs from the probe record")
    if sha256(elf_path) != ledger.get("elf_sha256"):
        errors.append("allocation audit is not bound to the combined machine ELF")
    if sha256(map_path) != ledger.get("map_sha256"):
        errors.append("allocation audit is not bound to the current link map")
    if sha256(check_path) != ledger.get("report_sha256"):
        errors.append("allocation-audit hash differs from the probe record")
    memory_map_hash = sha256(memory_map_path)
    if memory_map_hash != ledger.get("memory_map_sha256") or \
            memory_map_hash != probe.get("source_inputs", {}).get("memory_map_sha256"):
        errors.append("combined image and allocation audit use different memory-map inputs")
    if not errors:
        checks.append("machine ELF, linker map, audit, and budget-map hashes agree")

    ranges = sorted(audit.get("bss_input_sections", []), key=lambda row: row["start"])
    for previous, current in zip(ranges, ranges[1:]):
        if previous["end"] > current["start"]:
            errors.append(f"BSS map ranges overlap: {previous['owner']} and {current['owner']}")
            break
    if sum(row["bytes"] for row in ranges) != machine.get("elf", {}).get("bss_bytes"):
        errors.append("link-map input ranges do not account for the complete machine BSS")
    if audit.get("unmapped_symbol_count") != 0:
        errors.append("one or more BSS symbols have no linker-map owner")
    if ledger.get("unassigned_owners"):
        errors.append("the combined machine ledger has unassigned BSS owners")
    if ledger.get("candidate_regions_over_capacity"):
        errors.append("the combined machine ledger exceeds a candidate region")
    if not any("overlap" in error or "complete machine BSS" in error or
               "unassigned" in error or "exceeds a candidate" in error for error in errors):
        checks.append("all BSS map ranges are non-overlapping and fully owned")

    capacities = {row["name"]: row["bytes"] for row in budget["regions"]}
    region_owners = memory_map.get("runtime_region_owners", {})
    if set(region_owners) != set(capacities) or any(not value for value in region_owners.values()):
        errors.append("one or more budget regions lack exactly one named runtime owner")
    else:
        checks.append("every EE budget region has one named owner (including reserved spans)")

    high_water_errors = validate_high_water(
        memory_map.get("high_water_evidence", {}), capacities,
        audit.get("file_backed_allocated_bytes", 0))
    errors.extend(high_water_errors)
    if not high_water_errors:
        checks.append("every budget region has bounded or explicitly unknown high-water evidence")

    profile = memory_map.get("bootstrap_profile", {})
    bss_bytes = int(machine.get("elf", {}).get("bss_bytes", 0))
    game_state_bytes = int(profile.get("game_state_bytes", 0))
    object_pool_bytes = int(profile.get("object_pool_bytes", 0))
    claims_bytes_per_bit = int(profile.get("validator_claim_word_bytes", 0))
    claims_bits_per_word = int(profile.get("validator_claim_bits_per_word", 0))
    tag_bytes = int(machine.get("tag_cache_bytes", 0))
    bsp_capacity = capacities.get(profile.get("structure_bsp_region"), 0)
    bsp_bytes = capacities.get(profile.get("current_bsp_region", "current_bsp"), 0) - tag_bytes
    if not claims_bits_per_word or not claims_bytes_per_bit:
        errors.append("validator claims bitmap word geometry is missing")
        claims_bytes = 0
    else:
        claims_bytes = ((tag_bytes + bsp_bytes + claims_bits_per_word - 1) //
                        claims_bits_per_word) * claims_bytes_per_bit
    resident_used = bss_bytes + game_state_bytes + claims_bytes
    if profile.get("object_pool_nested_within") != "game_state" or object_pool_bytes > game_state_bytes:
        errors.append("nested CE object pool ownership is missing or invalid")
    if resident_used > capacities.get("resident_gameplay", 0):
        errors.append("bootstrap BSS/game-state/claims exceed resident_gameplay")
    if tag_bytes <= 0 or tag_bytes >= bsp_capacity or tag_bytes + bsp_bytes != bsp_capacity:
        errors.append("bootstrap tag cache and BSP spans do not partition current_bsp")
    if not any("resident_gameplay" in error or "current_bsp" in error for error in errors):
        checks.append("bootstrap fixed spans fit once; object pool is nested and tag/BSP are disjoint")

    expected_external = {"gs_edram": 4 * 1024 * 1024,
                         "iop_ram": 2 * 1024 * 1024,
                         "spu2_ram": 2 * 1024 * 1024}
    actual_external = {row.get("name"): row.get("bytes")
                       for row in memory_map.get("external_hardware_stores", [])}
    if actual_external != expected_external:
        errors.append("external GS/IOP/SPU2 stores are not separately and exactly accounted")
    else:
        checks.append("GS, IOP, and SPU2 capacities are separate from EE budget regions")

    if not errors:
        gate = subprocess.run(
            [sys.executable, str(ROOT / "tools/hcu_ps2_external_review.py"), "check"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if gate.returncode:
            errors.append("rooted external semantic gate did not close: " +
                          (gate.stdout + gate.stderr).strip())
        else:
            checks.append("rooted external semantic review passed for the same object")

    return {
        "status": "m0-logical-allocation-ownership",
        "gate": "closed" if not errors else "open",
        "physical_placement_gate": "separate-m1-requirement",
        "runtime_high_water": "recorded where measured; unknown production peaks remain explicit",
        "rooted_sha256": rooted_hash,
        "machine_elf_sha256": sha256(elf_path),
        "machine_map_sha256": sha256(map_path),
        "allocation_audit_sha256": sha256(check_path),
        "memory_map_sha256": memory_map_hash,
        "external_ledger_sha256": sha256(external_path),
        "bss_bytes": bss_bytes,
        "resident_bootstrap_bytes": resident_used,
        "resident_bootstrap_capacity": capacities.get("resident_gameplay"),
        "resident_bootstrap_spare": capacities.get("resident_gameplay", 0) - resident_used,
        "bsp_tag_bytes": tag_bytes,
        "bsp_cache_bytes": bsp_bytes,
        "checks": checks,
        "errors": errors,
        "limits": [
            "A closed M0 owner gate does not prove physical heap-pointer placement or allocator metadata.",
            "Production dynamic, texture, audio, and renderer high-water remain runtime/M1/M2 evidence.",
            "The 2 MiB UI-map bootstrap profile is not a retail gameplay-map capacity claim.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/hcu-ps2-closure/m0-ownership-gate.json")
    args = parser.parse_args()
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"M0 logical ownership gate {result['gate']}: "
          f"{len(result['checks'])} checks, {len(result['errors'])} errors")
    for error in result["errors"]:
        print(f"  {error}")
    if result["gate"] != "closed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
