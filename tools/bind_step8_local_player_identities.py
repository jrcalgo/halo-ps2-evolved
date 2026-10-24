#!/usr/bin/env python3
"""Rebuild exact-byte bindings for the Step 8 four-local-player ledger row."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = Path("docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json")
OUTPUT = Path("docs/reports/m2-step8-local-players-4-identity-bindings-2026-10-22.json")
AVAILABILITY_REPORT = Path("docs/reports/m2-step8-historical-workload-pin-availability-2026-10-22.json")
ROW_KEY = "local-players-4"

# These are candidate locations only. A path is included in the output only if
# its current bytes reproduce a digest declared by the selected ledger row.
CANDIDATE_CATEGORIES = {
    "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-4p-tagcache-4477120.elf": ("executable_hashes", "reported_hash_pins"),
    "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-2p-tagcache-4477120.elf": ("input_hashes", "source_hashes", "reported_hash_pins"),
    # The report SHA-256s pin these machine-readable link reports, rather than
    # the 2P/4P ELFs. Keep the path association explicit so the auditor can
    # verify those report artifacts independently.
    "build/hcu-parent-link-probe/result-step8-mp-workload-4p-tagcache-4477120.json": ("reported_hash_pins",),
    "build/hcu-parent-link-probe/result-step8-mp-workload-2p-tagcache-4477120.json": ("reported_hash_pins",),
    "tools/hcu_parent_link_probe.py": ("input_hashes", "source_hashes", "reported_hash_pins"),
    "tools/ee-world.mk": ("input_hashes", "source_hashes", "reported_hash_pins"),
    "tools/test_hcu_step8_mp_workload.py": ("input_hashes", "source_hashes", "reported_hash_pins"),
    "tests/test_hcu_step8_mp_workload_source.py": ("input_hashes", "source_hashes", "reported_hash_pins", "harness_hashes"),
    "tests/test_hcu_step8_mp_workload_runner.py": ("input_hashes", "source_hashes", "reported_hash_pins", "harness_hashes"),
    "build/hcu-ps2-closure/emulator-m1-recompiler-3a78e285374b453f9cb18b6e2ae61fdf/result.json": ("input_hashes", "source_hashes", "reported_hash_pins"),
    "build/hcu-ps2-closure/emulator-m1-recompiler-3a78e285374b453f9cb18b6e2ae61fdf/emulog.txt": ("input_hashes", "source_hashes", "reported_hash_pins"),
    "build/hcu-ps2-closure/emulator-m1-interpreter-15c010c1a47041618f6c159e1c41621e/result.json": ("input_hashes", "source_hashes", "reported_hash_pins", "log_hashes"),
    "build/hcu-ps2-closure/emulator-m1-interpreter-15c010c1a47041618f6c159e1c41621e/emulog.txt": ("input_hashes", "source_hashes", "reported_hash_pins"),
    # Exact result/log artifacts for the separately pinned four-player guest
    # follow-up; the 2P historical outputs above remain independent.
    "build/hcu-ps2-closure/emulator-m1-recompiler-3a78e285374b453f9cb18b6e2ae61fdf/result.json": ("executable_hashes", "reported_hash_pins"),
    "build/hcu-ps2-closure/emulator-m1-recompiler-3a78e285374b453f9cb18b6e2ae61fdf/emulog.txt": ("log_hashes", "reported_hash_pins"),
    "build/hcu-ps2-closure/emulator-m1-interpreter-15c010c1a47041618f6c159e1c41621e/result.json": ("executable_hashes", "reported_hash_pins"),
    "build/hcu-ps2-closure/emulator-m1-interpreter-15c010c1a47041618f6c159e1c41621e/emulog.txt": ("log_hashes", "reported_hash_pins"),
    "build/hcu-step8-mp-workload/interpreter-result.json": ("input_hashes", "source_hashes", "reported_hash_pins"),
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    ledger_path = args.ledger if args.ledger.is_absolute() else ROOT / args.ledger
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    ledger = json.loads(ledger_path.read_text())
    row_index, row = next((i, row) for i, row in enumerate(ledger["evidence"]) if row.get("subcheck") == ROW_KEY)
    identities = row["fixture_input_hashes"]
    bindings = []
    matched: set[str] = set()
    for rel, categories in CANDIDATE_CATEGORIES.items():
        path = ROOT / rel
        if not path.is_file():
            continue
        actual = digest(path)
        bound_categories = [cat for cat in categories if any(
            isinstance(item, dict) and item.get("sha256") == actual
            for item in identities.get(cat, [])
        )]
        if bound_categories:
            matched.add(actual)
            bindings.append({
                "core_row_index": row_index,
                "path": rel,
                "sha256": actual,
                "categories_bound": bound_categories,
                "basis": "SHA-256 of current file bytes equals the report-pinned identity",
            })

    # The final follow-up paragraph prints both mode-specific result and log
    # hashes. Its text labels are not enough to infer the artifact category, so
    # bind each exact current file under the category independently verified by
    # its report path and bytes.
    explicit_mode_outputs = [
        ("build/hcu-ps2-closure/emulator-m1-recompiler-3a78e285374b453f9cb18b6e2ae61fdf/result.json", "f1134c273bce827da8884c8dae80170845fdc8a701436a9fe0a7135076571c72", ("executable_hashes",)),
        ("build/hcu-ps2-closure/emulator-m1-recompiler-3a78e285374b453f9cb18b6e2ae61fdf/emulog.txt", "968869907e432bbf81a9c9aef8507298bd3019a3bdccff1f436556b2fc6398f7", ("log_hashes",)),
        ("build/hcu-ps2-closure/emulator-m1-interpreter-15c010c1a47041618f6c159e1c41621e/result.json", "706c973eb040696c35c13e9ab813b80005f3650fce15bf8671284b5c6471c529", ("log_hashes", "reported_hash_pins")),
        ("build/hcu-ps2-closure/emulator-m1-interpreter-15c010c1a47041618f6c159e1c41621e/emulog.txt", "96298193eb2eb8d6db250288e221df2f4f37e080ae20de4c55d9f0a334c076ce", ("log_hashes",)),
    ]
    for rel, expected, categories in explicit_mode_outputs:
        path = ROOT / rel
        if not path.is_file() or digest(path) != expected:
            continue
        categories = tuple(cat for cat in categories
                           if expected in {item.get("sha256") for item in identities.get(cat, [])})
        if not categories:
            continue
        matched.add(expected)
        bindings.append({"core_row_index": row_index, "path": rel, "sha256": expected,
                         "categories_bound": list(categories),
                         "basis": "mode-specific guest report gives exact output path and current bytes reproduce digest"})

    unbound = []
    for category, values in identities.items():
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            expected = item.get("sha256")
            if not expected or expected in matched:
                continue
            if item.get("local_path") and item.get("local_sha256") == expected:
                local = ROOT / item["local_path"]
                if local.is_file() and digest(local) == expected:
                    continue
            unbound.append({
                "category": category,
                "sha256": expected,
                "reported_label": item.get("reported_label", ""),
            })

    result = {
        "format": "hcu-step8-local-player-4-identity-bindings-v1",
        "ledger_path": str(ledger_path.relative_to(ROOT)),
        "ledger_sha256": digest(ledger_path),
        "core_row_index": row_index,
        "policy": "Bindings count only when SHA-256 of current file bytes equals the exact digest in the ledger row. Missing historical generated files remain unresolved; no result qualification is changed.",
        "historical_pin_availability_report": {
            "path": AVAILABILITY_REPORT.as_posix(),
            "sha256": digest(ROOT / AVAILABILITY_REPORT),
            "pins_checked": sorted(json.loads((ROOT / AVAILABILITY_REPORT).read_text())["pins"]),
        } if (ROOT / AVAILABILITY_REPORT).is_file() else None,
        "verified_bindings": bindings,
        "unbound_identities": unbound,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"core_row_index": row_index, "verified_bindings": len(bindings), "unbound_identities": len(unbound), "ledger_sha256": result["ledger_sha256"], "output": str(output_path.relative_to(ROOT))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
