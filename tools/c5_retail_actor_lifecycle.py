#!/usr/bin/env python3
"""C5 step 3: retail-actor lifecycle ledger driven from C1 actor recipes.

Reads the C1 actor roster (hcu-actor-roster-v1), keeps recipes that resolve a
retail actor, a bipd unit and a ranged weapon, verifies each recipe's pinned
source map hash, and produces one ledger row per recipe with seven lifecycle
stages: placement, attachment, activation, update, combat, death, cleanup.

A stage counts as passed only from evidence with kind "retail" (real CE
placement/update executed by a harness). Records with kind "synthetic" are kept
for context and never complete a stage. Without evidence every stage is
"not-executed", and the ledger reports incomplete. Spartan bot counts are not
produced here; they are null and belong to the metrics module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROSTER = ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json"
DEFAULT_MAPS = ROOT / "build/retail-maps/decompressed"
FORMAT = "c5-retail-actor-lifecycle-v1"
EVIDENCE_FORMAT = "c5-retail-lifecycle-evidence-v1"
STAGES = ("placement", "attachment", "activation", "update", "combat", "death", "cleanup")


class LifecycleError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def eligible_recipes(roster: dict) -> list[dict]:
    """Recipes that can drive a full retail lifecycle: actor, bipd unit, ranged weapon."""
    out = []
    for r in roster.get("unique_recipes", []):
        unit = r.get("unit") or {}
        if not (r.get("actor") and r["actor"].get("path")):
            continue
        if unit.get("group") != "bipd" or not unit.get("path"):
            continue
        weapon = r.get("ranged_weapon") or {}
        if not weapon.get("path"):
            continue
        out.append(r)
    return out


def check_pins(roster: dict, recipes: list[dict], maps_dir: Path) -> list[str]:
    """Return pin mismatch messages for recipes whose source map is present on disk."""
    pins = {s["map"]: s["sha256"] for s in roster.get("source_roots", [])}
    problems = []
    for r in recipes:
        digest = r.get("source_map_sha256")
        for alias in r.get("source_aliases", []):
            path = maps_dir / f"{alias}.map"
            if path.is_file() and sha256_file(path) != pins.get(alias):
                problems.append(f"{alias}.map differs from roster pin")
        if digest and r.get("source_aliases") and digest not in pins.values():
            problems.append(f"recipe {r['variant']['path']} pins unknown source hash")
    return sorted(set(problems))


def new_ledger(recipes: list[dict]) -> list[dict]:
    rows = []
    for r in recipes:
        rows.append({
            "variant": r["variant"]["path"],
            "actor": r["actor"]["path"],
            "unit": r["unit"]["path"],
            "ranged_weapon": r["ranged_weapon"]["path"],
            "source_aliases": r.get("source_aliases", []),
            "stages": {s: {"status": "not-executed"} for s in STAGES},
        })
    return rows


def apply_evidence(ledger: list[dict], evidence: dict, roster_sha: str) -> dict:
    if evidence.get("format") != EVIDENCE_FORMAT:
        raise LifecycleError("evidence format mismatch")
    if evidence.get("roster_sha256") != roster_sha:
        raise LifecycleError("evidence was not produced from this roster")
    index = {row["variant"]: row for row in ledger}
    applied = ignored_synthetic = 0
    for rec in evidence.get("records", []):
        row = index.get(rec.get("variant"))
        if row is None:
            raise LifecycleError(f"evidence names a recipe outside the roster: {rec.get('variant')}")
        real = rec.get("kind") == "retail"
        for stage, result in rec.get("stages", {}).items():
            if stage not in STAGES:
                raise LifecycleError(f"unknown stage {stage}")
            if not real:
                ignored_synthetic += 1
                continue
            if result.get("status") not in ("passed", "failed"):
                raise LifecycleError(f"invalid status for {stage}")
            row["stages"][stage] = {"status": result["status"], "source": result.get("source", "")}
            applied += 1
    return {"stages_applied": applied, "synthetic_stages_ignored": ignored_synthetic}


def summarize(ledger: list[dict], roster_path: Path, maps_dir: Path) -> dict:
    total = len(ledger) * len(STAGES)
    passed = sum(1 for row in ledger for s in row["stages"].values() if s["status"] == "passed")
    failed = sum(1 for row in ledger for s in row["stages"].values() if s["status"] == "failed")
    complete = total > 0 and passed == total
    return {
        "format": FORMAT,
        "roster": str(roster_path.relative_to(ROOT)) if roster_path.is_relative_to(ROOT) else str(roster_path),
        "roster_sha256": sha256_file(roster_path),
        "maps_dir_present": maps_dir.is_dir(),
        "recipes": len(ledger),
        "stages_required": total,
        "stages_passed": passed,
        "stages_failed": failed,
        "status": "complete" if complete else ("failed" if failed else "incomplete"),
        "retail_actor_records": None,
        "spartan_bots": None,
        "note": "Spartan bot and retail record counts come from src/stream/hcu_actor_metrics.c, not this ledger.",
        "ledger": ledger,
    }


def build(roster_path: Path, maps_dir: Path, evidence_path: Path | None, limit: int | None) -> dict:
    roster = json.loads(roster_path.read_text())
    recipes = eligible_recipes(roster)
    if limit is not None:
        recipes = recipes[:limit]
    if not recipes:
        raise LifecycleError("no eligible retail actor recipes in roster")
    problems = check_pins(roster, recipes, maps_dir)
    if problems:
        raise LifecycleError("; ".join(problems))
    ledger = new_ledger(recipes)
    roster_sha = sha256_file(roster_path)
    if evidence_path is not None:
        apply_evidence(ledger, json.loads(evidence_path.read_text()), roster_sha)
    return summarize(ledger, roster_path, maps_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    ap.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS)
    ap.add_argument("--evidence", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        result = build(args.roster, args.maps_dir, args.evidence, args.limit)
    except (LifecycleError, OSError, json.JSONDecodeError) as exc:
        print(f"c5 lifecycle refused: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
