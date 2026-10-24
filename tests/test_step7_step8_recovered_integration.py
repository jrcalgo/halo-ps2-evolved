"""Recovered identities must preserve the original row's evidence scope."""
import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from integrate_step7_step8_recovered_bindings import integrate


def fixture(tmp_path):
    payload = b"retained executable bytes"
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / "run.elf").write_bytes(payload)
    report = digest.encode()
    (tmp_path / "report.md").write_bytes(report)
    report_hash = hashlib.sha256(report).hexdigest()
    row = {"step": 7, "subcheck": "consumer", "result": "partial",
           "evidence_level": "host execution",
           "evidence_files": [{"path": "report.md", "sha256": report_hash}],
           "fixture_input_hashes": {"executable_hashes": [{"sha256": digest}]}}
    binding = {"step": 7, "subcheck": "consumer", "recorded_result": "partial",
               "evidence_level": "host execution",
               "source_reports": [{"path": "report.md", "sha256": report_hash}],
               "report_artifact_bindings": [{"path": "run.elf", "sha256": digest,
                                              "matches": True}]}
    return {"evidence": [row]}, {"format": "hcu-step7-step8-supplemental-recoverable-bindings-v1",
                                 "bindings": [binding]}


def test_exact_recovery_is_idempotent_and_retains_qualification(tmp_path):
    ledger, bindings = fixture(tmp_path)
    assert integrate(ledger, bindings, tmp_path)["report_artifact_resolutions"] == 1
    item = ledger["evidence"][0]["fixture_input_hashes"]["executable_hashes"][0]
    assert item["local_path"] == "run.elf"
    assert item["recovered_binding"]["origin_path_asserted"] is False
    once = copy.deepcopy(ledger)
    assert integrate(ledger, bindings, tmp_path)["rows_with_added_bindings"] == 0
    assert ledger == once
    assert ledger["evidence"][0]["result"] == "partial"


def test_other_rows_digest_cannot_create_a_new_identity(tmp_path):
    ledger, bindings = fixture(tmp_path)
    ledger["evidence"][0]["fixture_input_hashes"]["executable_hashes"] = []
    before = copy.deepcopy(ledger)
    assert integrate(ledger, bindings, tmp_path)["report_artifact_resolutions"] == 0
    assert ledger == before


def test_changed_artifact_does_not_resolve_historical_pin(tmp_path):
    ledger, bindings = fixture(tmp_path)
    (tmp_path / "run.elf").write_bytes(b"new executable")
    assert integrate(ledger, bindings, tmp_path)["report_artifact_resolutions"] == 0


def test_changed_report_cannot_authorize_binding(tmp_path):
    ledger, bindings = fixture(tmp_path)
    (tmp_path / "report.md").write_bytes(b"changed report")
    with pytest.raises(ValueError, match="no exact linked source report"):
        integrate(ledger, bindings, tmp_path)


def test_map_mention_does_not_expand_fixture_scope(tmp_path):
    ledger, bindings = fixture(tmp_path)
    data = b"map"
    (tmp_path / "map.map").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    ledger["source_maps"] = [{"path": "map.map", "sha256": digest}]
    bindings["bindings"][0]["fixture_bindings"] = [
        {"path": "map.map", "sha256": digest, "matches": True}]
    assert integrate(ledger, bindings, tmp_path)["map_identity_resolutions"] == 0
    assert "fixture_hashes" not in ledger["evidence"][0]["fixture_input_hashes"]


def test_identity_hash_detects_same_length_file_replacement(tmp_path):
    from generate_hcu_step7_step8_closure import sha256
    path = tmp_path / 'artifact'
    path.write_bytes(b'old')
    old = sha256(path)
    path.write_bytes(b'new')
    assert sha256(path) != old
    assert sha256(path) == hashlib.sha256(b'new').hexdigest()
