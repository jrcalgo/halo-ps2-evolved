import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import update_hcu_c2_evidence as updater


def fixture(tmp_path):
    requirements = []
    for index in range(1, 9):
        path = tmp_path / f"proof{index}.json"
        path.write_text('{}')
        requirements.append({"id": f"C2.{index}", "behavior": "fixture", "owner": "fixture",
                             "acceptance_requirement": "fixture acceptance", "scope": "host fixture",
                             "remaining_limitation": "actual target workload remains open",
                             "evidence_level": "host execution", "result": "partial",
                             "evidence_files": [{"path": path.name, "sha256": updater.sha(path),
                                                  "evidence_level": "host execution"}]})
    status = {"format": "hcu-m2-c2-status-v2", "requirements": requirements}
    (tmp_path / "status.json").write_text(json.dumps(status))
    independent = {"step": 7, "subcheck": "retained-consumer", "result": "partial"}
    ledger = {"evidence": [independent], "step_status": {"step7": {}, "step8": {}}}
    (tmp_path / "ledger.json").write_text(json.dumps(ledger))
    return status, independent


def test_changed_proof_invalidates_only_its_requirement(tmp_path):
    status, independent = fixture(tmp_path)
    (tmp_path / "proof4.json").write_text('{"corrupt":true}')
    ledger = updater.update(tmp_path, Path("status.json"), Path("ledger.json"))
    assert ledger["evidence"][0] == independent
    assert [row["subcheck"] for row in ledger["evidence"] if row["result"] == "stale"] == ["c2-4"]
    assert ledger["step_status"]["step8"]["qualified_rows"] == 0


def test_missing_requirement_and_unverified_pass_are_rejected(tmp_path):
    status, _ = fixture(tmp_path)
    missing = copy.deepcopy(status)
    missing["requirements"].pop()
    (tmp_path / "status.json").write_text(json.dumps(missing))
    with pytest.raises(ValueError):
        updater.update(tmp_path, Path("status.json"), Path("ledger.json"))
    status["requirements"][0]["result"] = "passed"
    (tmp_path / "status.json").write_text(json.dumps(status))
    with pytest.raises(ValueError):
        updater.update(tmp_path, Path("status.json"), Path("ledger.json"))
