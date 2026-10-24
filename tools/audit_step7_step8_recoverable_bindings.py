#!/usr/bin/env python3
"""Emit digest-verified supplemental bindings for three reproducible C0 slices.

This diagnostic never edits the canonical closure ledger or promotes results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
MP_MAPS = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
           "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
           "sidewinder", "wizard")
HEX64 = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
PATH_TOKEN = re.compile(r"(?:[A-Za-z0-9_.+-]+/)+[A-Za-z0-9_.+-]+")


def digest_kind(context: str) -> str:
    """Classify what the report says a digest identifies, without guessing bytes."""
    text = context.lower()
    if any(k in text for k in ("source_map", "fixture", "scenario", "map_sha", "map hash")):
        return "map fixture"
    if any(k in text for k in ("source_sha", "source_hash", "probe_source", "harness_sha", "compiler_source")):
        return "source"
    if any(k in text for k in ("package_sha", "package_hash", ".hp2", "generated_package")):
        return "package"
    if any(k in text for k in ("elf_sha", "object_sha", "binary_sha", "executable", "log_sha", "artifact_sha", "build/")):
        return "build artifact"
    if any(k in text for k in ("report pin", "report_sha", "report hash", "report_digest", "sha256")):
        return "report pin"
    return "unknown"


def nearby_paths(text: str, start: int, end: int) -> list[str]:
    # JSON and Markdown reports commonly put a path next to its digest. Keep
    # the window narrow so unrelated paths are not accidentally bound.
    window = text[max(0, start - 240):min(len(text), end + 240)]
    return sorted(set(PATH_TOKEN.findall(window)))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, help="write diagnostic JSON here")
    ap.add_argument("--ledger", default=str(LEDGER), help="canonical ledger to inspect")
    args = ap.parse_args()
    ledger_path = Path(args.ledger)
    if not ledger_path.is_absolute():
        ledger_path = ROOT / ledger_path
    ledger = json.loads(ledger_path.read_text())
    maps = {Path(x["path"]).stem: x for x in ledger["source_maps"]}
    # Read each map once for this immutable input snapshot, rather than once
    # for every row which refers to it. A new invocation always rehashes it.
    map_actuals = {name: sha(ROOT / item['path']) if (ROOT / item['path']).is_file() else None
                   for name, item in maps.items() if name in MP_MAPS}
    rows = ledger["evidence"]
    digest_index: dict[str, list[str]] = {}
    scan_roots = (ROOT / "build/m2-step7-late-b000-failure-atomicity-20261022",
                  ROOT / "build/mp-render-cache-stress", ROOT / "build/hcu-parent-link-probe",
                  ROOT / "tests", ROOT / "tools")
    for base in scan_roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file():
                if p.suffix.lower() == ".hp2" or "assets" in p.parts:
                    continue
                try:
                    digest_index.setdefault(sha(p), []).append(str(p.relative_to(ROOT)))
                except OSError:
                    pass
    bindings = []

    # Source-map hashes are independently pinned in the ledger inventory.
    for row in rows:
        subcheck = row["subcheck"]
        report_files = [x["path"] for x in row.get("evidence_files", [])
                        if x.get("path", "").endswith((".md", ".json", ".txt"))]
        report_text = []
        report_hashes: dict[str, dict[str, set[str]]] = {}
        for report_path in report_files:
            p = ROOT / report_path
            if not p.is_file():
                continue
            content = p.read_text(errors="replace")
            report_text.append((report_path, content))
            for match in HEX64.finditer(content):
                digest = match.group(0).lower()
                context = content[max(0, match.start() - 240):min(len(content), match.end() + 240)]
                info = report_hashes.setdefault(digest, {"reports": set(), "kinds": set(), "paths": set()})
                info["reports"].add(report_path)
                info["kinds"].add(digest_kind(context))
                info["paths"].update(nearby_paths(content, match.start(), match.end()))
        joined = "\n".join(text for _path, text in report_text)
        joined_lower = joined.lower()
        names = set()
        existing = row.get("fixture_input_hashes", {})
        for category in ("fixture_hashes", "input_hashes", "source_hashes", "harness_hashes",
                         "executable_hashes", "log_hashes", "reported_hash_pins"):
            for item in existing.get(category, []) if isinstance(existing, dict) else []:
                name = item.get("map")
                path = item.get("path") or item.get("local_path")
                if name in MP_MAPS:
                    names.add(name)
                if path:
                    stem = Path(path).stem.lower()
                    if stem in MP_MAPS:
                        names.add(stem)
        for name in MP_MAPS:
            if re.search(rf"\b{re.escape(name)}\b", joined_lower):
                names.add(name)
        if re.search(r"\b(?:all\s*)?13\s+(?:stock\s+)?(?:multiplayer\s+)?maps\b", joined_lower):
            names.update(MP_MAPS)
        if "all13" in joined_lower or "all-13" in joined_lower or "all 13" in joined_lower:
            names.update(MP_MAPS)
        maps_in_scope = []
        for name in names:
            entry = maps.get(name)
            if not entry:
                continue
            p = ROOT / entry["path"]
            actual = map_actuals.get(name)
            maps_in_scope.append({"path": entry["path"], "sha256": entry["sha256"],
                                  "actual_sha256": actual, "matches": actual == entry["sha256"],
                                  "role": "fixture", "basis": "ledger source_maps inventory; current bytes rehashed"})

        artifact_pins = []
        classified = []
        for digest in sorted(report_hashes):
            info = report_hashes[digest]
            # Follow exact paths declared beside a digest before scanning the
            # bounded retained roots. No filename or semantic substitution.
            candidates = set(digest_index.get(digest, []))
            for raw_path in info["paths"]:
                p = ROOT / raw_path
                if p.is_file():
                    try:
                        if sha(p) == digest:
                            candidates.add(str(p.relative_to(ROOT)))
                    except OSError:
                        pass
            for path in sorted(set(digest_index.get(digest, []))):
                p = ROOT / path
                artifact_pins.append({"path": path, "sha256": digest, "actual_sha256": sha(p),
                                      "matches": True, "basis": "report-pinned digest equals current file bytes"})
            # Include path-discovered exact matches too, preserving de-duplication.
            already = {x["path"] for x in artifact_pins if x["sha256"] == digest}
            for path in sorted(candidates - already):
                p = ROOT / path
                artifact_pins.append({"path": path, "sha256": digest, "actual_sha256": sha(p),
                                      "matches": True, "basis": "report-adjacent path and digest equal current file bytes"})
            existing_paths = [p for p in info["paths"] if (ROOT / p).is_file()]
            wrong_paths = []
            for raw_path in existing_paths:
                try:
                    if sha(ROOT / raw_path) != digest:
                        wrong_paths.append(raw_path)
                except OSError:
                    wrong_paths.append(raw_path)
            status = ("path-bound" if candidates else
                      "reported-path-bytes-mismatch" if wrong_paths else
                      "reported-path-missing" if info["paths"] else
                      "digest-only-unresolved")
            classified.append({"sha256": digest, "category": sorted(info["kinds"])[0] if len(info["kinds"]) == 1 else "unknown",
                               "reported_categories": sorted(info["kinds"]),
                               "reported_paths": sorted(info["paths"]),
                               "source_reports": sorted(info["reports"]),
                               "resolved_paths": sorted(candidates),
                               "status": status})
        bindings.append({"step": row["step"], "subcheck": subcheck, "recorded_result": row["result"],
                         "evidence_level": row["evidence_level"], "source_reports": [
                             {"path": p, "sha256": sha(ROOT / p)} for p, _ in report_text],
                         "fixture_bindings": maps_in_scope,
                         "report_artifact_bindings": artifact_pins,
                         "report_digest_classifications": classified,
                         "unresolved_report_digests": sorted(set(report_hashes) -
                             {x["sha256"] for x in artifact_pins}),
                         "scope_limitation": row.get("remaining_limitation")})
    categories = {}
    statuses = {}
    for row in bindings:
        for item in row["report_digest_classifications"]:
            categories[item["category"]] = categories.get(item["category"], 0) + 1
            statuses[item["status"]] = statuses.get(item["status"], 0) + 1
    out = {"format": "hcu-step7-step8-supplemental-recoverable-bindings-v1",
           "ledger_sha256": sha(ledger_path), "bindings": bindings,
           "digest_audit": {"references": sum(statuses.values()),
                            "path_bound": statuses.get("path-bound", 0),
                            "unresolved": sum(v for k, v in statuses.items() if k != "path-bound"),
                            "categories": categories, "statuses": statuses},
           "policy": "Diagnostic only; exact current bytes and ledger-pinned maps only; row results remain unchanged."}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"rows": len(bindings), "rows_with_fixture_bindings": sum(bool(r['fixture_bindings']) for r in bindings),
                      "rows_with_report_artifacts": sum(bool(r['report_artifact_bindings']) for r in bindings),
                      "verified_fixture_bindings": sum(sum(x['matches'] for x in r['fixture_bindings']) for r in bindings),
                      "verified_report_artifacts": sum(len(r['report_artifact_bindings']) for r in bindings),
                      "unresolved_report_digests": sum(len(r['unresolved_report_digests']) for r in bindings),
                      "report_digest_categories": categories}, sort_keys=True))


if __name__ == "__main__":
    main()
