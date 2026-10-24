#!/usr/bin/env python3
"""Import scoped C2 evidence into the canonical Step 7/8 closure ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = Path("docs/reports/m2-c2-status-2026-10-23.json")
LEDGER = Path("docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update(root=ROOT, status_path=STATUS, ledger_path=LEDGER):
    status = json.loads((root / status_path).read_text())
    if status.get("format") != "hcu-m2-c2-status-v2" or {
            row.get("id") for row in status.get("requirements", [])} != {
            f"C2.{i}" for i in range(1, 9)} or len(status["requirements"]) != 8:
        raise ValueError("C2 status must account for all eight requirements")
    ledger = json.loads((root / ledger_path).read_text())
    retained = [row for row in ledger["evidence"]
                if not row.get("subcheck", "").startswith("c2-")]
    report_pin = {"path": str(status_path), "sha256": sha(root / status_path),
                  "role": "phase status report"}
    added = []
    for requirement in status["requirements"]:
        pins = [dict(report_pin), *requirement.get("evidence_files", [])]
        stale, executables = [], []
        for pin in pins:
            if not pin.get("path") or not pin.get("sha256"):
                raise ValueError("C2 evidence identity lacks path or hash")
            path = root / pin["path"]
            pin["exists"] = path.is_file()
            if not pin["exists"] or sha(path) != pin["sha256"]:
                stale.append(pin["path"])
            elif pin.get("role") == "executable":
                executables.append(dict(pin))
        result = requirement["result"]
        if result == "passed" and (not pins[1:] or not requirement.get("acceptance_verified")):
            raise ValueError("A C2 requirement cannot pass without verified acceptance evidence")
        if stale:
            result = "stale"
        levels = sorted({pin.get("evidence_level", "source inspection") for pin in pins[1:]})
        row = {"step": 8, "subcheck": "c2-" + requirement["id"].split(".")[1],
               "behavior_or_member": requirement["behavior"], "owner": requirement["owner"],
               "acceptance_requirement": requirement["acceptance_requirement"],
               "evidence": str(status_path), "evidence_files": pins,
               "evidence_level": requirement["evidence_level"],
               "execution_results": [{"mode": level, "result": result,
                                      "scope": requirement["scope"],
                                      "evidence_files": [pin for pin in pins[1:]
                                                         if pin.get("evidence_level", "source inspection") == level]}
                                     for level in levels],
               "fixture_input_hashes": {"status": "partial" if stale else "complete",
                                        "executable_hashes": executables,
                                        "fixture_hashes": [report_pin],
                                        "harness_hashes": [], "input_hashes": pins[1:]},
               "measurements": requirement.get("measurements", {}), "result": result,
               "remaining_limitation": requirement["remaining_limitation"],
               "source_report_hashes": {pin["path"]: pin["sha256"] for pin in pins}}
        # A user-approved carry-over changes proof ownership, not its result.
        # Preserve the destination and unresolved acceptance text explicitly;
        # importing it must never manufacture a target execution or a pass.
        if requirement.get("deferred_to"):
            row["deferred_to"] = requirement["deferred_to"]
            row["deferred_acceptance_requirements"] = requirement.get(
                "deferred_acceptance_requirements", [])
            row["scope_amendment"] = requirement.get("scope_amendment")
        # Narrower-scope outcomes are recorded for reference only; they never
        # replace the row result, which stays the full-acceptance verdict.
        for key in ("c2_retained_scope_result", "c2_retained_scope_basis",
                    "matrix_evidence"):
            if requirement.get(key) is not None:
                row[key] = requirement[key]
        if stale:
            row["stale_dependencies"] = stale
        added.append(row)
    ledger["evidence"] = retained + added
    ledger.setdefault("additional_pins", {})["c2_evidence_updater"] = {
        "path": "tools/update_hcu_c2_evidence.py", "sha256": sha(Path(__file__))}
    for step in (7, 8):
        rows = [row for row in ledger["evidence"] if row["step"] == step]
        target = ledger["step_status"][f"step{step}"]
        target.update(status="open", partial_rows=sum(row["result"] in ("partial", "stale") for row in rows),
                      qualified_rows=sum(row["result"] in ("pass", "passed", "qualified") for row in rows),
                      unrun_rows=sum(row["result"] in ("not_run", "blocked", "missing") for row in rows))
    (root / ledger_path).write_text(json.dumps(ledger, indent=2) + "\n")
    return ledger


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=STATUS)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()
    update(status_path=args.status, ledger_path=args.ledger)
