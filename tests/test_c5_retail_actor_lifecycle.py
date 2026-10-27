"""Host tests for the C5 retail-actor lifecycle ledger (tools/c5_retail_actor_lifecycle.py)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c5_retail_actor_lifecycle as c5  # noqa: E402

ROSTER = ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json"
FIXTURE = ROOT / "tests/c5_empty_roster_fixture.json"


def _tiny_roster(tmp_path, recipes):
    path = tmp_path / "roster.json"
    path.write_text(json.dumps({"format": "hcu-actor-roster-v1", "source_roots": [],
                                "unique_recipes": recipes}))
    return path


def _recipe(name):
    return {"actor": {"path": f"characters\\{name}\\{name}"},
            "unit": {"group": "bipd", "path": f"characters\\{name}\\{name}"},
            "ranged_weapon": {"path": "weapons\\needler\\needler"},
            "variant": {"path": f"characters\\{name}_ingame\\{name}_ingame"},
            "source_aliases": [], "source_map_sha256": "0" * 64}


def test_real_roster_has_eligible_recipes_and_seven_stages():
    roster = json.loads(ROSTER.read_text())
    recipes = c5.eligible_recipes(roster)
    assert len(recipes) > 0
    result = c5.build(ROSTER, ROOT / "build/retail-maps/decompressed", None, limit=2)
    assert result["stages_required"] == 2 * len(c5.STAGES) == 14
    assert result["stages_passed"] == 0
    assert result["status"] == "incomplete"
    assert result["retail_actor_records"] is None and result["spartan_bots"] is None


def test_zero_recipes_is_refused():
    with pytest.raises(c5.LifecycleError, match="no eligible"):
        c5.build(FIXTURE, ROOT / "build/retail-maps/decompressed", None, None)


def test_synthetic_evidence_never_completes_a_stage(tmp_path):
    roster = _tiny_roster(tmp_path, [_recipe("elite")])
    ledger = c5.new_ledger(c5.eligible_recipes(json.loads(roster.read_text())))
    evidence = {"format": c5.EVIDENCE_FORMAT, "roster_sha256": c5.sha256_file(roster),
                "records": [{"variant": ledger[0]["variant"], "kind": "synthetic",
                             "stages": {s: {"status": "passed"} for s in c5.STAGES}}]}
    info = c5.apply_evidence(ledger, evidence, c5.sha256_file(roster))
    assert info == {"stages_applied": 0, "synthetic_stages_ignored": 7}
    assert all(v["status"] == "not-executed" for v in ledger[0]["stages"].values())


def test_retail_evidence_completes_and_failure_is_reported(tmp_path):
    roster = _tiny_roster(tmp_path, [_recipe("elite"), _recipe("grunt")])
    recipes = c5.eligible_recipes(json.loads(roster.read_text()))
    ledger = c5.new_ledger(recipes)
    sha = c5.sha256_file(roster)
    ok = {s: {"status": "passed", "source": "pcsx2-run-1"} for s in c5.STAGES}
    bad = dict(ok, death={"status": "failed"})
    evidence = {"format": c5.EVIDENCE_FORMAT, "roster_sha256": sha,
                "records": [{"variant": ledger[0]["variant"], "kind": "retail", "stages": ok},
                            {"variant": ledger[1]["variant"], "kind": "retail", "stages": bad}]}
    c5.apply_evidence(ledger, evidence, sha)
    summary = c5.summarize(ledger, roster, tmp_path)
    assert summary["stages_passed"] == 13 and summary["stages_failed"] == 1
    assert summary["status"] == "failed"


def test_full_pass_is_complete(tmp_path):
    roster = _tiny_roster(tmp_path, [_recipe("elite")])
    ledger = c5.new_ledger(c5.eligible_recipes(json.loads(roster.read_text())))
    sha = c5.sha256_file(roster)
    evidence = {"format": c5.EVIDENCE_FORMAT, "roster_sha256": sha,
                "records": [{"variant": ledger[0]["variant"], "kind": "retail",
                             "stages": {s: {"status": "passed"} for s in c5.STAGES}}]}
    c5.apply_evidence(ledger, evidence, sha)
    assert c5.summarize(ledger, roster, tmp_path)["status"] == "complete"


def test_evidence_from_other_roster_is_refused(tmp_path):
    roster = _tiny_roster(tmp_path, [_recipe("elite")])
    ledger = c5.new_ledger(c5.eligible_recipes(json.loads(roster.read_text())))
    evidence = {"format": c5.EVIDENCE_FORMAT, "roster_sha256": "f" * 64, "records": []}
    with pytest.raises(c5.LifecycleError, match="not produced from this roster"):
        c5.apply_evidence(ledger, evidence, c5.sha256_file(roster))


def test_cli_refuses_with_nonzero_exit():
    result = subprocess.run([sys.executable, "-I", str(ROOT / "tools/c5_retail_actor_lifecycle.py"),
                             "--roster", str(FIXTURE)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "no eligible" in result.stderr
