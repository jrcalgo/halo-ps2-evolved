#!/usr/bin/env python3
"""Audit identity accounting in the C0–C7 evidence ledger; never qualifies rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from functools import lru_cache
import sys

DEFAULT_LEDGER = "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
DEFAULT_OUTPUT = "docs/reports/m2-c0-row-accounting-2026-10-23.json"
FIELDS = ("step", "subcheck", "behavior_or_member", "owner", "fixture_input_hashes",
          "evidence_level", "result", "measurements", "remaining_limitation",
          "acceptance_requirement", "evidence_files")
HASH_KEYS = ("fixture_hashes", "input_hashes", "harness_hashes", "executable_hashes",
             "source_hashes", "log_hashes", "reported_hash_pins")
DISPOSITIONS = {"missing", "unavailable", "unrun", "not_applicable", "unresolved", "historical_unavailable"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=4)
def _synthetic_inputs(root_path, schema_path, schema_hash, inventory_hash):
    root = Path(root_path)
    sys.path.insert(0, str(root)) if str(root) not in sys.path else None
    from tools.hcu_schema_manifest import Elf32, SchemaManifest
    manifest = SchemaManifest(Elf32(root / schema_path)).build()
    inventory = json.loads((root / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json").read_text())
    return manifest, {r['path']: r for r in inventory['members']}


def verified_synthetic_fixture(row, value, root):
    """Reconstruct the fixture; a recipe string alone is never evidence."""
    if not all(k in value for k in ('field', 'sha256', 'bytes', 'recipe')):
        return False
    inputs = row.get('fixture_input_hashes', {}).get('input_hashes', [])
    schema = next((r for r in inputs if str(r.get('path', '')).endswith('.elf')), None)
    if not schema or any(not r.get('path') or not (root / r['path']).is_file()
                         or sha256(root / r['path']) != r.get('sha256') for r in inputs):
        return False
    inventory = root / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
    manifest, members = _synthetic_inputs(str(root), schema['path'], schema['sha256'], sha256(inventory))
    member = members.get(value['field'])
    if not member:
        return False
    from tools.audit_step7_empty_bsp_fields import make_synthetic_block
    image, _location, _payload, recipe = make_synthetic_block(manifest, member)
    return (hashlib.sha256(image).hexdigest() == value['sha256']
            and len(image) == value['bytes'] and recipe == value['recipe'])


def classify_identities(row: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Classify every supplied digest as availability evidence, never as acceptance."""
    records = []
    hashes = row.get("fixture_input_hashes") or {}
    if not isinstance(hashes, dict):
        return [{"category": "fixture_input_hashes", "index": None, "sha256": None,
                 "reported_path": None, "resolved_path": None, "observed_hash": None,
                 "state": "invalid_missing_digest", "limitation": "fixture_input_hashes is not an object"}]
    for category in HASH_KEYS:
        values = hashes.get(category, [])
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                value = {}
            expected = value.get("sha256") or value.get("digest")
            reported_path = value.get("local_path") or value.get("path")
            resolved_path = None
            observed = None
            recipe = value.get("recipe") or value.get("synthetic_recipe")
            disposition = str(value.get("disposition", value.get("status", ""))).lower().replace("-", "_")
            if recipe and (value.get("reproducible_synthetic_fixture") or value.get("synthetic") or "fixture" in category):
                state = ("reproducible_synthetic_fixture(recipe present)" if verified_synthetic_fixture(row, value, root)
                         else "invalid_synthetic_fixture")
            elif reported_path:
                resolved_path = (root / reported_path).resolve()
                if not resolved_path.is_file():
                    state = "historical_path_missing"
                else:
                    observed = sha256(resolved_path)
                    state = "exact_current_bytes" if expected and observed == expected else "historical_path_hash_mismatch"
            elif expected:
                state = "unresolved_digest_only"
            else:
                state = "invalid_missing_digest"
            records.append({"category": category, "index": index, "sha256": expected,
                            "reported_path": reported_path,
                            "resolved_path": str(resolved_path) if resolved_path else None,
                            "observed_hash": observed, "state": state,
                            "explicit_disposition": disposition or None,
                            "limitation": None if state in ("exact_current_bytes", "reproducible_synthetic_fixture(recipe present)")
                            else "Identity is accounted for but its bytes or reproducible workload are unavailable; this is missing evidence."})
    # evidence_files are path/digest pins too; retain their separate category.
    for index, value in enumerate(row.get("evidence_files", []) if isinstance(row.get("evidence_files", []), list) else []):
        if not isinstance(value, dict): value = {}
        path = value.get("path") or value.get("local_path")
        digest = value.get("sha256") or value.get("digest")
        target = (root / path).resolve() if path else None
        observed = sha256(target) if target and target.is_file() else None
        if not digest: state = "invalid_missing_digest"
        elif not target: state = "unresolved_digest_only"
        elif not target.is_file(): state = "historical_path_missing"
        elif observed != digest: state = "historical_path_hash_mismatch"
        else: state = "exact_current_bytes"
        records.append({"category": "evidence_files", "index": index, "sha256": digest,
                        "reported_path": path, "resolved_path": str(target) if target else None,
                        "observed_hash": observed, "state": state,
                        "limitation": None if state == "exact_current_bytes" else "Evidence file unavailable or changed; this is missing evidence."})
    return records


def attach_accounting(ledger: dict[str, Any], root: Path) -> dict[str, Any]:
    """Return a ledger copy with per-row, non-qualifying identity accounting."""
    for row in ledger.get("evidence", []):
        row["identity_accounting"] = classify_identities(row, root)
        row["identity_accounting_policy"] = (
            "Availability accounting only. Unresolved digests, historical missing paths, "
            "and mismatches remain missing acceptance evidence; no replacement bytes are inferred.")
        if "execution_results" not in row:
            level = row.get("evidence_level", "")
            modes = (["interpreter", "recompiler"] if "interpreter and recompiler" in level
                     else ["interpreter"] if "interpreter" in level
                     else ["recompiler"] if "recompiler" in level
                     else ["host", "PCSX2 mode unspecified"] if "host/PCSX2" in level
                     else [level])
            row["execution_results"] = [
                {"mode": mode, "result": row["result"],
                 "scope": ("Aggregate report retained; this entry does not infer a separately qualified execution."
                           if len(modes) > 1 else "Row's original stated evidence scope."),
                 "evidence_files": row.get("evidence_files", [])}
                for mode in modes]
    return ledger


def audit(ledger: dict[str, Any], root: Path) -> dict[str, Any]:
    rows = ledger.get("evidence", [])
    audited = []
    total_exact = total_missing = total_stale = total_unavailable = unclassified = 0
    required_missing = []
    for index, row in enumerate(rows):
        absent_fields = [key for key in FIELDS if key not in row]
        if absent_fields:
            required_missing.append({"row": index, "fields": absent_fields})
        identities = classify_identities(row, root)
        state_names = {"exact_current_bytes": "exact", "historical_path_missing": "missing",
                       "historical_path_hash_mismatch": "stale", "unresolved_digest_only": "unresolved_digest_only",
                       "invalid_missing_digest": "unclassified"}
        identity_counts = {"exact": 0, "missing": 0, "stale": 0, "explicit_disposition": 0, "unclassified": 0, "synthetic_recipe": 0, "unresolved_digest_only": 0}
        for identity in identities:
            state = identity["state"]
            if state == "reproducible_synthetic_fixture(recipe present)": identity_counts["synthetic_recipe"] += 1
            elif state == "unresolved_digest_only" and identity.get("explicit_disposition") in DISPOSITIONS:
                # A declared unavailable digest is unresolved evidence, not a
                # malformed identity.
                identity_counts["explicit_disposition"] += 1
            else: identity_counts[state_names.get(state, "unclassified")] += 1
        unclassified += identity_counts["unclassified"]
        total_exact += identity_counts["exact"]; total_missing += identity_counts["missing"]
        total_stale += identity_counts["stale"]; total_unavailable += identity_counts["explicit_disposition"]
        audited.append({"row_index": index, "step": row.get("step"), "subcheck": row.get("subcheck"),
                        "behavior_or_member": row.get("behavior_or_member"), "required_fields_missing": absent_fields,
                        "identity_counts": identity_counts, "identities": identities,
                        "result_preserved": row.get("result"), "evidence_level_preserved": row.get("evidence_level"),
                        "measurements_preserved": row.get("measurements"), "limitation_preserved": row.get("remaining_limitation")})
        qualified = str(row.get("result", "")).lower() in {"pass", "passed", "accepted", "qualified"}
        unbacked = [item for item in identities if item["state"] not in ("exact_current_bytes", "reproducible_synthetic_fixture(recipe present)")]
        audited[-1]["qualified_row_has_unbacked_identities"] = bool(qualified and unbacked)
    return {"format": "hcu-c0-row-accounting-v2", "purpose": "identity accounting only; does not establish acceptance of C1-C7 or any row",
            "ledger_rows": len(rows), "required_fields": list(FIELDS), "rows_missing_required_fields": required_missing,
            "totals": {"exact_path_hash_bindings": total_exact, "missing_current_files": total_missing,
                       "stale_hashes": total_stale, "explicit_dispositions": total_unavailable,
                       "unclassified_identity_count": unclassified}, "rows": audited}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    root = Path.cwd()
    ledger = json.loads((root / args.ledger).read_text())
    result = audit(ledger, root)
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": args.output, "ledger_rows": result["ledger_rows"], **result["totals"]}, sort_keys=True))
    return 1 if result["rows_missing_required_fields"] or any(r.get("qualified_row_has_unbacked_identities") for r in result["rows"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
