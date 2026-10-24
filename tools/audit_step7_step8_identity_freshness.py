#!/usr/bin/env python3
"""Diagnose freshness of C0 ledger identities without modifying evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"


def sha(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def _git(repo: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(repo), *args],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _repository_drift(record: dict, root: Path) -> list[dict]:
    repo = (root / record.get("path", ".")).resolve()
    drift = []
    head = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    tracked = None
    try:
        tracked_bytes = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary", "HEAD"],
                                                stderr=subprocess.DEVNULL)
        tracked = hashlib.sha256(tracked_bytes).hexdigest()
    except (OSError, subprocess.CalledProcessError):
        pass
    if head != record.get("head"):
        drift.append({"kind": "repository_head", "path": record.get("path"),
                      "expected": record.get("head"), "actual": head})
    if status is None or hashlib.sha256(status.encode()).hexdigest() != record.get("status_porcelain_sha256"):
        drift.append({"kind": "repository_worktree_status", "path": record.get("path"),
                      "expected_sha256": record.get("status_porcelain_sha256"),
                      "actual_sha256": hashlib.sha256(status.encode()).hexdigest() if status is not None else None})
    if tracked != record.get("tracked_diff_sha256"):
        drift.append({"kind": "repository_tracked_diff", "path": record.get("path"),
                      "expected_sha256": record.get("tracked_diff_sha256"),
                      "actual_sha256": tracked})
    for item in record.get("changed_file_sha256", []):
        full = repo / item["path"]
        actual = sha(full)
        if actual != item.get("sha256"):
            drift.append({"kind": "repository_changed_file", "path": str(full.relative_to(root)),
                          "expected_sha256": item.get("sha256"), "actual_sha256": actual})
    return drift


def _row_refs(value) -> tuple[set[str], set[str]]:
    paths: set[str] = set()
    digests: set[str] = set()
    if isinstance(value, dict):
        for key, val in value.items():
            if key in ("path", "local_path", "source_artifact", "build_report_path",
                       "compiler_path", "profile_path", "budget_path", "schema_elf") and isinstance(val, str):
                paths.add(val.replace("\\", "/").lstrip("./"))
            if key in ("sha256", "local_sha256", "source_artifact_sha256") and isinstance(val, str):
                digests.add(val)
            elif key.endswith("_sha256") and isinstance(val, str):
                digests.add(val)
            else:
                p, d = _row_refs(val)
                paths.update(p)
                digests.update(d)
    elif isinstance(value, list):
        for item in value:
            p, d = _row_refs(item)
            paths.update(p)
            digests.update(d)
    return paths, digests


def audit_freshness(ledger: dict, root: Path = ROOT) -> dict:
    """Compare ledger pins with current bytes and identify only dependent rows.

    Global repository-state drift is reported even when there is no row-level
    path to attribute it to. A row is marked stale only when one of its exact
    declared paths/digests intersects a stale identity; independent rows keep
    their recorded result.
    """
    stale_identities: list[dict] = []

    def check_file(path: str | None, expected: str | None, kind: str) -> None:
        if not path or not expected:
            return
        full = Path(path)
        if not full.is_absolute():
            full = root / full
        actual = sha(full)
        if actual != expected:
            try:
                rel = full.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = str(full)
            stale_identities.append({"kind": kind, "path": rel,
                                     "expected_sha256": expected, "actual_sha256": actual})

    for group in ("repository_identities", "dependency_identities"):
        for record in ledger.get(group, []):
            stale_identities.extend(_repository_drift(record, root))
            for item in record.get("changed_file_sha256", []):
                check_file(f"{record.get('path','.')}/{item.get('path','')}",
                           item.get("sha256"), f"{group}_changed_source")
    for item in ledger.get("source_maps", []):
        check_file(item.get("path"), item.get("sha256"), "source_map")
    for item in ledger.get("generated_packages", []):
        check_file(item.get("path"), item.get("sha256"), "generated_package")
    for item in ledger.get("generated_inputs", []):
        check_file(item.get("path"), item.get("sha256"), "generated_input")

    pins = ledger.get("additional_pins", {})
    for name, record in pins.items():
        if isinstance(record, dict):
            check_file(record.get("path"), record.get("sha256"), f"additional_pin:{name}")
        elif name.endswith("_path") and isinstance(record, str):
            digest = pins.get(name[:-5] + "_sha256")
            check_file(record, digest if isinstance(digest, str) else None,
                       f"additional_pin:{name[:-5]}")
    check_file(pins.get("schema_elf"), pins.get("schema_elf_sha256"), "schema_elf")
    check_file(pins.get("bsp_inventory_path"), pins.get("bsp_inventory_sha256"), "bsp_inventory")
    toolchain = pins.get("toolchain", {})
    for key in ("compiler", "profile", "build_report"):
        check_file(toolchain.get(f"{key}_path"), toolchain.get(f"{key}_sha256"),
                   f"toolchain:{key}")
    build = ledger.get("schema_build_units", {})
    for item in build.get("source_identity", {}).get("units", []):
        check_file(f"submodules/halo-ce-universal/{item.get('path','')}",
                   item.get("built_source_sha256"), "schema_build_source")

    # Include bindings in the standalone report sidecar if the ledger has one.
    provenance = ledger.get("package_provenance", {})
    check_file(provenance.get("path"), provenance.get("sha256"), "package_provenance_report")

    # Reports and inputs are the direct evidence dependencies. Recheck all
    # row-local path/digest pairs independently of the top-level inventory.
    for row in ledger.get("evidence", []):
        for item in row.get("evidence_files", []):
            check_file(item.get("path"), item.get("sha256"), "evidence_report")
        fixture = row.get("fixture_input_hashes", {})
        for category in ("fixture_hashes", "input_hashes", "source_hashes",
                         "harness_hashes", "executable_hashes", "log_hashes",
                         "reported_hash_pins"):
            for item in fixture.get(category, []):
                path = item.get("local_path") or item.get("path")
                digest = item.get("local_sha256") or item.get("sha256")
                # Path-like pins only. Labels such as "PCSX2 BIOS" remain
                # unresolved historical identities rather than filesystem paths.
                if path and ("/" in path or "\\" in path or Path(path).suffix):
                    check_file(path, digest, f"row_input:{category}")
        for item in row.get("measurements", {}).get("values", []):
            if isinstance(item, dict):
                check_file(item.get("source_artifact"), item.get("source_artifact_sha256"),
                           "measurement_source")

    stale_identities = list({(x.get("kind"), x.get("path"), x.get("expected_sha256"),
                              x.get("actual_sha256"), x.get("expected"), x.get("actual")):
                             x for x in stale_identities}.values())
    stale_paths = {x.get("path", "").replace("\\", "/").lstrip("./")
                   for x in stale_identities if x.get("path")}
    stale_digests = {x.get("expected_sha256") for x in stale_identities
                     if x.get("expected_sha256")}
    row_results = []
    for index, row in enumerate(ledger.get("evidence", [])):
        paths, digests = _row_refs(row)
        hits = []
        for stale in stale_identities:
            p = stale.get("path", "").replace("\\", "/").lstrip("./")
            expected = stale.get("expected_sha256")
            path_match = bool(p and any(ref == p or ref.endswith("/" + p) for ref in paths))
            digest_match = bool(expected and expected in digests)
            if path_match or digest_match:
                hits.append(stale)
        source_hash = row.get("source_map_sha256")
        if source_hash in stale_digests and not any(h.get("expected_sha256") == source_hash for h in hits):
            hits.extend(x for x in stale_identities if x.get("expected_sha256") == source_hash)
        row_results.append({"evidence_index": index, "step": row.get("step"),
                            "subcheck": row.get("subcheck"),
                            "recorded_result": row.get("result"),
                            "effective_result": "stale" if hits else row.get("result"),
                            "stale_identity_count": len(hits), "stale_identities": hits})
    return {
        "format": "hcu-m2-step7-step8-identity-freshness-v1",
        "policy": "Diagnostic overlay: exact path/digest dependencies become stale; unrelated evidence keeps its recorded result. Global repository drift without an attributable row reference is reported separately.",
        "summary": {
            "stale_identity_count": len(stale_identities),
            "rows_checked": len(row_results),
            "rows_marked_stale": sum(x["effective_result"] == "stale" for x in row_results),
            "independent_rows_preserved": sum(x["effective_result"] != "stale" for x in row_results),
            "repository_state_drift_count": sum(
                x["kind"].startswith("repository_") for x in stale_identities),
        },
        "stale_identities": stale_identities,
        "rows": row_results,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--output")
    args = ap.parse_args()
    ledger_path = ROOT / args.ledger
    report = audit_freshness(json.loads(ledger_path.read_text()), ROOT)
    report["ledger_path"] = args.ledger
    report["ledger_sha256"] = sha(ledger_path)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
