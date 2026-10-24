#!/usr/bin/env python3
"""Merge only exact, row-pinned recovered paths into the C0 closure ledger.

The supplemental manifest is a discovery artifact; this tool resolves a
canonical ledger identity only when that row already contains the exact digest
and the report declaring it is itself an exact, linked evidence file. Map
scope is never inferred from report prose: a map binding can resolve only an
existing pathless fixture_hashes entry whose digest is in the ledger's
source_maps inventory.

The canonical ledger does not pin this supplemental manifest, so its
ledger_sha256 snapshot is deliberately not copied into the ledger. That keeps
the dependency one-way and avoids a circular file-hash identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
DEFAULT_BINDINGS = "docs/reports/m2-step7-step8-supplemental-bindings-2026-10-23.json"
DEFAULT_AUDIT = "docs/reports/m2-step7-step8-ledger-coverage-audit-2026-10-22.json"
PIN_CATEGORIES = ("fixture_hashes", "input_hashes", "source_hashes",
                  "harness_hashes", "executable_hashes", "log_hashes",
                  "reported_hash_pins")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rooted_path(raw: str, root: Path = ROOT) -> Path:
    path = Path(raw)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {raw}") from exc
    return resolved


def _linked_reports(row: dict[str, Any], binding: dict[str, Any],
                    root: Path = ROOT) -> list[dict[str, str]]:
    """Return report inputs which are both ledger-linked and currently exact."""
    evidence = {item.get("path"): item.get("sha256")
                for item in row.get("evidence_files", [])}
    linked: list[dict[str, str]] = []
    for report in binding.get("source_reports", []):
        path, digest = report.get("path"), report.get("sha256")
        if not path or evidence.get(path) != digest:
            continue
        report_path = rooted_path(path, root)
        if report_path.is_file() and sha(report_path) == digest:
            linked.append({"path": path, "sha256": digest})
    return linked


def _identity_items(row: dict[str, Any]):
    hashes = row.setdefault("fixture_input_hashes", {})
    for category in PIN_CATEGORIES:
        values = hashes.get(category, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                yield category, item


def _bind(item: dict[str, Any], path: str, digest: str, *, basis: str,
          source_reports: list[dict[str, str]]) -> bool:
    """Resolve a digest-only pin; never overwrite an existing path binding."""
    existing_path = item.get("local_path") or item.get("path")
    existing_digest = item.get("local_sha256") or item.get("sha256")
    if existing_path:
        # Already-integrated identical entries are a no-op, so repeated runs
        # report zero additions and leave serialized bytes unchanged.
        return False
    if item.get("sha256") != digest:
        return False
    item["local_path"] = path
    item["local_sha256"] = digest
    item["matches_current_file"] = True
    item["recovered_binding"] = {
        "basis": basis,
        "source_reports": source_reports,
        "origin_path_asserted": False,
    }
    return True


def integrate(ledger: dict[str, Any], manifest: dict[str, Any], root: Path = ROOT) -> dict[str, int]:
    """Apply exact recoveries, retaining row result/evidence scope unchanged."""
    if manifest.get("format") != "hcu-step7-step8-supplemental-recoverable-bindings-v1":
        raise ValueError("unexpected supplemental binding format")
    ledger_rows = ledger.get("evidence", [])
    by_key = {(r.get("step"), r.get("subcheck")): r for r in ledger_rows}
    if len(by_key) != len(ledger_rows):
        raise ValueError("canonical ledger row keys are not unique")
    manifest_rows = manifest.get("bindings", [])
    manifest_keys = [(r.get("step"), r.get("subcheck")) for r in manifest_rows]
    if len(manifest_keys) != len(set(manifest_keys)):
        raise ValueError("supplemental row keys are not unique")

    source_maps = {item.get("sha256"): item for item in ledger.get("source_maps", [])}
    changed = set()
    map_resolutions = artifact_resolutions = 0
    for binding in manifest_rows:
        key = (binding.get("step"), binding.get("subcheck"))
        row = by_key.get(key)
        if row is None:
            raise ValueError(f"supplemental row does not exist in ledger: {key}")
        if binding.get("recorded_result") != row.get("result"):
            raise ValueError(f"result mismatch for row {key}")
        if binding.get("evidence_level") != row.get("evidence_level"):
            raise ValueError(f"evidence-level mismatch for row {key}")
        linked_reports = _linked_reports(row, binding, root)
        if binding.get("source_reports") and not linked_reports:
            raise ValueError(f"no exact linked source report for row {key}")
        row_changed = False

        # Resolve a map only when this exact map digest is already present as a
        # row-level fixture pin. This does not infer or broaden behavior scope.
        for fixture in binding.get("fixture_bindings", []):
            digest = fixture.get("sha256")
            unresolved = [item for category, item in _identity_items(row)
                          if category == "fixture_hashes" and item.get("sha256") == digest
                          and not (item.get("path") or item.get("local_path"))]
            if not unresolved:
                continue
            inventory = source_maps.get(digest)
            if (not inventory or inventory.get("path") != fixture.get("path") or
                    fixture.get("matches") is not True):
                continue
            map_path = rooted_path(inventory["path"], root)
            if not map_path.is_file() or sha(map_path) != digest:
                continue
            for item in unresolved:
                if _bind(item, inventory["path"], digest,
                         basis="existing row fixture digest matched exact ledger source_maps entry",
                         source_reports=[]):
                    row_changed = True
                    map_resolutions += 1

        # For report artifacts, require (a) the digest was already pinned in
        # this row, (b) a linked source report contains that digest, and (c) a
        # candidate file has those exact bytes. We record content equivalence,
        # not the original producer path.
        for artifact in binding.get("report_artifact_bindings", []):
            digest, relpath = artifact.get("sha256"), artifact.get("path")
            unresolved = [item for _category, item in _identity_items(row)
                          if item.get("sha256") == digest
                          and not (item.get("path") or item.get("local_path"))]
            if not unresolved:
                continue
            if not digest or not relpath or artifact.get("matches") is not True:
                continue
            candidate = rooted_path(relpath, root)
            if not candidate.is_file() or sha(candidate) != digest:
                continue
            reports_with_digest = []
            for report in linked_reports:
                report_path = rooted_path(report["path"], root)
                if digest.encode("ascii") in report_path.read_bytes().lower():
                    reports_with_digest.append(report)
            if not reports_with_digest:
                continue
            for item in unresolved:
                if _bind(item, relpath, digest,
                         basis="row-pinned digest matched retained file bytes and linked report pin",
                         source_reports=reports_with_digest):
                    row_changed = True
                    artifact_resolutions += 1
        if row_changed:
            changed.add(key)

    # Status, evidence level, and result are outside the write set by design.
    return {"rows_with_added_bindings": len(changed),
            "map_identity_resolutions": map_resolutions,
            "report_artifact_resolutions": artifact_resolutions,
            "rows_checked": len(manifest_rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--bindings", default=DEFAULT_BINDINGS)
    ap.add_argument("--audit", default=DEFAULT_AUDIT)
    ap.add_argument("--check", action="store_true", help="validate and report without writing")
    args = ap.parse_args()
    ledger_path, manifest_path = rooted_path(args.ledger), rooted_path(args.bindings)
    ledger = json.loads(ledger_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    before = [(r.get("step"), r.get("subcheck"), r.get("result"), r.get("evidence_level"))
              for r in ledger.get("evidence", [])]
    counts = integrate(ledger, manifest)
    after = [(r.get("step"), r.get("subcheck"), r.get("result"), r.get("evidence_level"))
             for r in ledger.get("evidence", [])]
    if before != after:
        raise ValueError("integration changed row result or evidence level")
    if not args.check:
        ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
        # This is a one-way pointer from the diagnostic to the canonical file;
        # the canonical ledger does not include or hash the diagnostic.
        manifest["ledger_sha256"] = sha(ledger_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        if args.audit:
            from generate_hcu_step7_step8_closure import coverage_audit, write_json
            audit_path = rooted_path(args.audit)
            write_json(audit_path, coverage_audit(ledger, ledger_path))
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
