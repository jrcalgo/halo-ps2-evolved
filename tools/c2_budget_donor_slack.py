#!/usr/bin/env python3
"""C2.3 donor-slack decision for the elf_static overflow.

Reads the owner audit JSON (tools/audit_hcu_c2_budget_elf_owners.py --json) and
the committed budget, then decides whether any region's measured worst-case
slack can cover the elf_static overflow. A donor counts only when its high-water
comes from a multiplayer workload that is recorded with a source file and
complete for that region. Anything else is shown as a bound, not as a safe
donor. The tool never edits config/memory-budget.json; it only reports.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "config/memory-budget.json"

# Measured high-water records. "peak" is the largest observed use of the
# region's bytes; "complete" means every byte the region owns was accounted in
# that run. Sources are repository paths.
DONORS = {
    "resident_gameplay": {
        "reserved": 6815744,
        "peak": 3107656,
        "complete": False,
        "source": "docs/reports/m2-step8-ce-four-local-player-workload-2026-10-22.md (game-state peak only; one 4-player Sidewinder run)",
        "note": "game-state peak excludes claims, UI and nested owners not in that run; 54,456 B below the 3,162,112 B CPU backing",
    },
    "streaming": {
        "reserved": 1572864,
        "peak": 1572864 - 587336,
        "complete": False,
        "source": "docs/reports/m2-c2-r3-elf-budget-2026-10-23.md (587,336 B slack, workload not recorded)",
        "note": "slack is a single measurement without a multiplayer worst case",
    },
    "dynamic_simulation": {
        "reserved": 2621440,
        "peak": None,
        "complete": False,
        "source": "docs/reports/mp-step8-dynamic-pool-pressure-2026-10-22.md (no high-water exists)",
        "note": "no executable per-owner peak counter was run",
    },
}

# Diagnostic bytes that a gate in CE source would remove from elf_static. These
# are not applied by this tool; they are listed as the only code-side donor.
UNGATED_DIAGNOSTIC_BYTES = {
    "g_CounterBuf": 8192,
    "debug_path": 5428,
    "ai_profile": 3820,
    "cheat_strings": 3200,
    "debug_obstacles": 3080,
    "console_globals": 2500,
    "profile_graph_values": None,  # size not measured in the owner audit
}
UNGATED_MEASURED_TOTAL = sum(v for v in UNGATED_DIAGNOSTIC_BYTES.values() if v is not None)


def decide(owners, budget, margin_fraction=0.1, margin_min=65536):
    elf_static = next(r["bytes"] for r in budget["regions"] if r["name"] == "elf_static")
    need = owners["elf_static_need_bytes"]
    excess = max(0, need - elf_static)
    rows = []
    safe_total = 0
    bound_total = 0
    for name, d in DONORS.items():
        reserved = d["reserved"]
        if d["peak"] is None:
            slack = None
        else:
            slack = reserved - d["peak"]
        margin = max(margin_min, int(reserved * margin_fraction))
        safe = 0
        if slack is not None and d["complete"]:
            safe = max(0, slack - margin)
        if slack is not None:
            bound_total += max(0, slack)
        safe_total += safe
        rows.append({
            "region": name,
            "reserved_bytes": reserved,
            "measured_peak_bytes": d["peak"],
            "measured_slack_bytes": slack,
            "safety_margin_bytes": margin,
            "safe_donor_bytes": safe,
            "complete_multiplayer_measurement": d["complete"],
            "source": d["source"],
            "note": d["note"],
        })
    shortfall_after_safe = max(0, excess - safe_total)
    return {
        "elf_static_reservation_bytes": elf_static,
        "elf_static_need_bytes": need,
        "overflow_bytes": excess,
        "donors": rows,
        "safe_donor_total_bytes": safe_total,
        "uncapped_measured_slack_bound_bytes": bound_total,
        "ungated_diagnostic_measured_bytes": UNGATED_MEASURED_TOTAL,
        "shortfall_after_safe_donors_bytes": shortfall_after_safe,
        "budget_revision_safe": shortfall_after_safe == 0,
        "verdict": "revise budget" if shortfall_after_safe == 0 else "no safe revision; budget unchanged",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--owners", required=True, help="JSON from audit_hcu_c2_budget_elf_owners.py --json")
    ap.add_argument("--budget", default=str(BUDGET))
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)
    owners = json.loads(Path(args.owners).read_text())
    budget = json.loads(Path(args.budget).read_text())
    result = decide(owners, budget)
    text = json.dumps(result, indent=2)
    if args.json:
        Path(args.json).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
