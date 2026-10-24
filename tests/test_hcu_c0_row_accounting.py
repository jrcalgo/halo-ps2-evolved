import hashlib
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools/audit_hcu_c0_row_accounting.py"
spec = importlib.util.spec_from_file_location("c0_accounting", MODULE_PATH)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def fixture_row(path, digest):
    return {"step": 7, "subcheck": "test", "behavior_or_member": "member", "owner": "team",
            "fixture_input_hashes": {"input_hashes": [{"local_path": path, "sha256": digest}]},
            "evidence_level": "host", "result": "partial", "measurements": {},
            "remaining_limitation": "open", "acceptance_requirement": "qualify", "evidence_files": []}


def test_exact_and_unclassified_identity_are_accounted(tmp_path):
    artifact = tmp_path / "data.bin"
    artifact.write_bytes(b"fixture")
    row = fixture_row("data.bin", hashlib.sha256(b"fixture").hexdigest())
    row["fixture_input_hashes"]["input_hashes"].append({"reported_label": "old artifact"})
    result = audit_module.audit({"evidence": [row]}, tmp_path)
    assert result["totals"]["exact_path_hash_bindings"] == 1
    assert result["totals"]["unclassified_identity_count"] == 1
    assert result["rows"][0]["result_preserved"] == "partial"


def test_missing_and_stale_files_fail_accounting(tmp_path):
    row = fixture_row("gone.bin", "0" * 64)
    row["fixture_input_hashes"]["input_hashes"].append({"local_path": "stale.bin", "sha256": "0" * 64})
    (tmp_path / "stale.bin").write_bytes(b"different")
    result = audit_module.audit({"evidence": [row]}, tmp_path)
    assert result["totals"]["missing_current_files"] == 1
    assert result["totals"]["stale_hashes"] == 1


def test_explicit_unavailable_disposition_is_counted_not_qualified(tmp_path):
    row = fixture_row("unused.bin", "0" * 64)
    row["fixture_input_hashes"]["input_hashes"] = [{"reported_label": "historical", "sha256": "0" * 64, "disposition": "unavailable"}]
    row["result"] = "partial"
    result = audit_module.audit({"evidence": [row]}, tmp_path)
    assert result["totals"]["explicit_dispositions"] == 1
    assert result["totals"]["unclassified_identity_count"] == 0
    assert result["rows"][0]["identity_counts"]["unresolved_digest_only"] == 0
    assert result["rows"][0]["result_preserved"] == "partial"


def test_missing_and_digest_only_are_classified_historical_evidence(tmp_path):
    row = fixture_row("gone.bin", "a" * 64)
    row["fixture_input_hashes"]["input_hashes"].append({"sha256": "b" * 64})
    states = [x["state"] for x in audit_module.classify_identities(row, tmp_path)]
    assert states == ["historical_path_missing", "unresolved_digest_only"]


def test_qualified_row_with_missing_identity_is_rejected_by_audit(tmp_path):
    row = fixture_row("gone.bin", "a" * 64)
    row["result"] = "passed"
    result = audit_module.audit({"evidence": [row]}, tmp_path)
    assert result["rows"][0]["qualified_row_has_unbacked_identities"] is True


def test_attach_accounting_preserves_identity_bytes(tmp_path):
    row = fixture_row("gone.bin", "a" * 64)
    original = row["fixture_input_hashes"]["input_hashes"][0].copy()
    ledger = audit_module.attach_accounting({"evidence": [row]}, tmp_path)
    assert ledger["evidence"][0]["fixture_input_hashes"]["input_hashes"][0] == original
    assert ledger["evidence"][0]["identity_accounting"][0]["state"] == "historical_path_missing"


def test_fabricated_recipe_cannot_back_a_qualified_row(tmp_path):
    row = fixture_row("unused", "a" * 64)
    row['result'] = 'qualified'
    row['fixture_input_hashes'] = {'fixture_hashes': [{'sha256': 'a' * 64, 'recipe': 'invented'}]}
    result = audit_module.audit({'evidence': [row]}, tmp_path)
    assert result['rows'][0]['qualified_row_has_unbacked_identities']
    assert result['rows'][0]['identities'][0]['state'] == 'invalid_synthetic_fixture'
