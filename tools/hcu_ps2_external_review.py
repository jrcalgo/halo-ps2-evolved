"""Create and check the source-backed M0 review of rooted HCU externals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from build_toolchain import ROOT

REPORT = ROOT / "build/hcu-ps2-closure/all/result.json"
ROOTED = ROOT / "build/hcu-ps2-closure/all/rooted.o"
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"
GENERATED = ROOT / "build/hcu-ps2-closure/all/ps2_platform.c"
APPROVED = {"implemented", "state-adapter", "excluded-proven"}
REAL_BODY = {"implemented", "state-adapter"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_rows(report: dict) -> dict[str, dict]:
    units = report["units"]
    rows = {}
    for row in report["rooted_link"]["live_externals"]:
        symbol = row["symbol"]
        sources = row["caller_source_candidates"]
        if not sources:
            raise ValueError(f"no source attribution for {symbol}")
        if symbol in rows:
            raise ValueError(f"duplicate rooted symbol {symbol}")
        rows[symbol] = {
            "classification": row["classification"],
            "caller_sections": row["caller_sections"],
            "caller_sources": {source: units[source]["source_sha256"]
                               for source in sources},
        }
    return rows


def initialize(report: dict) -> None:
    if LEDGER.exists():
        raise ValueError(f"review already exists; will not overwrite {LEDGER}")
    rows = current_rows(report)
    ledger = {
        "version": 1,
        "rooted_sha256": sha256(ROOTED),
        "note": "Pending rows are an audit queue, not approved platform stubs.",
        "symbols": {
            name: {**row, "disposition": "pending", "owner": "",
                   "reason": "", "evidence": "", "test": ""}
            for name, row in sorted(rows.items())
        },
    }
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")
    print(f"created {LEDGER}: {len(rows)} pending rooted externals")


def refresh(report: dict) -> None:
    """Carry matching reviews forward; invalidate any changed caller/source row."""
    ledger = json.loads(LEDGER.read_text())
    current = current_rows(report)
    previous = ledger["symbols"]
    refreshed = {}
    invalidated = 0
    for name, identity in sorted(current.items()):
        old = previous.get(name, {})
        if all(old.get(key) == value for key, value in identity.items()):
            refreshed[name] = old
        else:
            invalidated += 1
            refreshed[name] = {**identity, "disposition": "pending", "owner": "",
                               "reason": "", "evidence": "", "test": ""}
    ledger["rooted_sha256"] = sha256(ROOTED)
    ledger["symbols"] = refreshed
    ledger["note"] = ("Pending rows are an audit queue, not approved platform stubs. "
                      "Refresh invalidates any changed caller/source row.")
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")
    print(f"refreshed {LEDGER}: {len(refreshed)} rooted externals; "
          f"{invalidated} new or changed rows invalidated")


def generated_symbols(path: Path) -> set[str]:
    """Names defined by the typed-zero generator, not by a reviewed owner."""
    if not path.is_file():
        return set()
    names = set()
    for line in path.read_text().splitlines():
        if not line or line.startswith(("/*", "#", " ")):
            continue
        if "(" in line:
            names.add(line.split("(", 1)[0].split()[-1].lstrip("*"))
        elif line.endswith(";"):
            token = line[:-1].split()[-1]
            names.add(token.split("[", 1)[0].lstrip("*"))
    return names


def check(report: dict) -> None:
    ledger = json.loads(LEDGER.read_text())
    current = current_rows(report)
    reviewed = ledger["symbols"]
    errors = []
    if ledger.get("rooted_sha256") != sha256(ROOTED):
        errors.append("rooted object hash changed; refresh the review")
    if set(reviewed) != set(current):
        errors.append(f"symbol set mismatch: missing={sorted(set(current)-set(reviewed))}, "
                      f"stale={sorted(set(reviewed)-set(current))}")
    for name in sorted(set(current) & set(reviewed)):
        row = reviewed[name]
        if any(row.get(key) != current[name][key] for key in
               ("classification", "caller_sections", "caller_sources")):
            errors.append(f"{name}: caller/class/source identity changed")
        if row.get("disposition") not in APPROVED:
            errors.append(f"{name}: pending semantic review")
        elif not all(row.get(key) for key in ("owner", "reason", "evidence", "test")):
            errors.append(f"{name}: incomplete source-backed disposition")
    notes = sorted(name for name in reviewed if name.startswith("network_coop_note_"))
    if len(notes) != 15 or any(reviewed[name].get("disposition") not in APPROVED for name in notes):
        errors.append("the 15 network_coop_note_* local-mode proofs must stay approved")
    generated = generated_symbols(GENERATED)
    for name in sorted(generated & set(reviewed)):
        if reviewed[name].get("disposition") in REAL_BODY:
            errors.append(f"{name}: newly generated required symbol; a real body must own it")
    if errors:
        print(f"M0 external-review gate open: {len(errors)} issues")
        for error in errors[:20]:
            print(error)
        raise SystemExit(1)
    print(f"M0 external-review gate closed: {len(current)} approved externals")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "refresh", "check"))
    args = parser.parse_args()
    report = json.loads(REPORT.read_text())
    if args.action == "init":
        initialize(report)
    elif args.action == "refresh":
        refresh(report)
    else:
        check(report)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError) as error:
        sys.exit(str(error))
