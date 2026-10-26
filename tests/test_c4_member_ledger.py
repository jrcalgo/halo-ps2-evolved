"""C4 item 1: the BSP/scenario member ledger covers every inventory member and every C4.1 family."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "audit_c4_member_ledger.py"
LEDGER = ROOT / "docs" / "reports" / "m4-c4-member-ledger-2026-10-26.json"


def _load_checker():
    spec = importlib.util.spec_from_file_location("audit_c4_member_ledger", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checker_passes_on_committed_ledger():
    result = subprocess.run(
        [sys.executable, "-I", str(CHECKER)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_inventory_member_has_one_classified_row():
    checker = _load_checker()
    payload, errors = checker.build_payload()
    assert errors == []
    inventory = json.loads((ROOT / checker.INVENTORY).read_text())
    assert payload["summary"]["row_count"] == len(inventory["members"])
    assert {r["member"] for r in payload["rows"]} == {m["path"] for m in inventory["members"]}
    assert all(r["classification"] in checker.CLASSES for r in payload["rows"])


def test_every_c41_family_has_rows():
    ledger = json.loads(LEDGER.read_text())
    families = {r["family"] for r in ledger["rows"]}
    for family in ledger["families_required"]:
        assert family in families, family


def test_no_consumed_row_without_parity_and_no_relabelled_gaps():
    ledger = json.loads(LEDGER.read_text())
    for row in ledger["rows"]:
        if row["classification"] == "consumed":
            assert row["parity_evidence"], row["member"]
            assert row["parity_scope"] == "member-exact", row["member"]
        if row["classification"] == "blocked":
            assert row["gap_reason"], row["member"]
            assert row["gap_type"], row["member"]


def _synthetic_parity(tmp_path, rows, lane="synthetic"):
    parity_dir = tmp_path / "parity"
    parity_dir.mkdir()
    (parity_dir / "m4-c4-parity-synthetic-2026-10-26.json").write_text(
        json.dumps({"lane": lane, "rows": rows}))
    return parity_dir


def member_name_for(row):
    return row["member"].split(".")[-1].split("[")[0]


def _family_only_member(checker):
    payload, _ = checker.build_payload(parity_dir=checker.ROOT / "docs" / "reports" / "no-such-dir")
    rows = payload["rows"]
    return next(r for r in rows if r["classification"] == "blocked"
                and r["gap_type"] == "consumer-family-parity-only")


def test_valid_member_exact_pass_reclassifies_family_only_row(tmp_path):
    checker = _load_checker()
    target = _family_only_member(checker)
    field = checker.member_name(target["member"])
    test_file = tmp_path / "test_fake_parity.py"
    test_file.write_text(f"# exercises {field}\n")
    parity_dir = _synthetic_parity(tmp_path, [{
        "member": target["member"], "test": str(test_file), "command": "pytest",
        "result": "pass", "scope": "member-exact", "notes": ""}])
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    assert not [e for e in errors if "parity-evidence-invalid" in e], errors
    row = next(r for r in payload["rows"] if r["member"] == target["member"])
    assert row["classification"] == "consumed"
    assert row["gap_type"] is None
    assert row["parity_rows"][0]["lane"] == "synthetic"
    assert str(test_file) in row["parity_evidence"]


def test_invalid_parity_rows_fail_and_are_listed(tmp_path):
    checker = _load_checker()
    target = _family_only_member(checker)
    no_field = tmp_path / "test_unrelated.py"
    no_field.write_text("# nothing relevant\n")
    field_file = tmp_path / "test_field_mention.py"
    field_file.write_text(f"# covers {member_name_for(target)}\n")
    rows = [
        {"member": "structure_bsp.not_a_member", "test": str(no_field), "result": "pass",
         "scope": "member-exact"},
        {"member": target["member"], "test": "", "result": "pass", "scope": "member-exact"},
        {"member": target["member"], "test": str(tmp_path / "missing.py"), "result": "pass",
         "scope": "member-exact"},
        {"member": target["member"], "test": str(no_field), "result": "pass", "scope": "member-exact"},
        {"member": target["member"], "test": str(field_file), "result": "pass", "scope": "family-level"},
    ]
    parity_dir = _synthetic_parity(tmp_path, rows)
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    invalid = [e for e in errors if e.startswith("parity-evidence-invalid")]
    assert any("unknown ledger member" in e for e in invalid)
    assert sum("without an existing test file" in e for e in invalid) == 2
    assert any("does not mention field" in e for e in invalid)
    assert any("only member-exact passes count" in e for e in invalid)
    row = next(r for r in payload["rows"] if r["member"] == target["member"])
    assert row["classification"] == "blocked"


def test_blocked_result_is_tolerated_and_notes_recorded(tmp_path):
    checker = _load_checker()
    target = _family_only_member(checker)
    parity_dir = _synthetic_parity(tmp_path, [{
        "member": target["member"], "test": "", "command": "", "result": "blocked",
        "scope": "family-level", "notes": "no member-exact harness yet"}])
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    assert not [e for e in errors if e.startswith("parity-evidence-invalid")], errors
    row = next(r for r in payload["rows"] if r["member"] == target["member"])
    assert row["classification"] == "blocked"
    assert "no member-exact harness yet" in row["gap_reason"]
    assert row["parity_rows"][0]["result"] == "blocked"


def test_fail_result_is_a_finding_and_strict_exits_nonzero(tmp_path, monkeypatch):
    checker = _load_checker()
    target = _family_only_member(checker)
    test_file = tmp_path / "test_fail_parity.py"
    test_file.write_text("# world_bounds harness\n")
    parity_dir = _synthetic_parity(tmp_path, [{
        "member": target["member"], "test": str(test_file), "command": "pytest",
        "result": "fail", "scope": "member-exact", "notes": "CE mismatch on world_bounds"}])
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    assert not [e for e in errors if e.startswith("parity-evidence-invalid")], errors
    row = next(r for r in payload["rows"] if r["member"] == target["member"])
    assert row["gap_type"] == "parity-failed"
    assert row["classification"] == "blocked"
    assert "CE mismatch" in row["gap_reason"]
    # --strict turns the finding into a non-zero exit; the default run only reports it.
    monkeypatch.setattr(checker, "build_payload", lambda: (payload, []))
    assert checker.main(["--strict"]) == 1


UNCLASSIFIED_CLUSTER = "structure_cluster.<unclassified@0xa>"


def _synthetic_range(tmp_path, rows):
    parity_dir = tmp_path / "parity"
    parity_dir.mkdir(exist_ok=True)
    (parity_dir / "m4-c4-range-dispositions-synthetic-2026-10-26.json").write_text(
        json.dumps({"lane": "synthetic", "rows": rows}))
    return parity_dir


def test_range_disposition_preserved_opaque_sets_classification(tmp_path):
    checker = _load_checker()
    parity_dir = _synthetic_range(tmp_path, [{
        "ledger_member": UNCLASSIFIED_CLUSTER, "disposition": "preserved-opaque",
        "evidence": "declared unusedA span in CE layout", "live_members": [], "needs_fixture": False,
        "notes": ""}])
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    assert not [e for e in errors if "invalid" in e], errors
    row = next(r for r in payload["rows"] if r["member"] == UNCLASSIFIED_CLUSTER)
    assert row["classification"] == "preserved-opaque"
    assert row["gap_type"] is None


def test_range_consumed_stays_blocked_until_member_exact_pass(tmp_path):
    checker = _load_checker()
    parity_dir = _synthetic_range(tmp_path, [{
        "ledger_member": UNCLASSIFIED_CLUSTER, "disposition": "consumed",
        "evidence": "consumer reads the range", "live_members": ["sky_index"], "needs_fixture": True}])
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    row = next(r for r in payload["rows"] if r["member"] == UNCLASSIFIED_CLUSTER)
    assert row["classification"] == "blocked"
    assert row["gap_type"] == "consumed-pending-fixture"
    assert row["range_needs_fixture"] is True


def test_range_schema_gap_and_invalid_rows(tmp_path):
    checker = _load_checker()
    parity_dir = _synthetic_range(tmp_path, [
        {"ledger_member": UNCLASSIFIED_CLUSTER, "disposition": "schema-gap", "evidence": "no schema member"},
        {"ledger_member": "structure_bsp.not_a_range", "disposition": "preserved-opaque", "evidence": "x"},
        {"ledger_member": "structure_cluster.<unclassified@0x0>", "disposition": "preserved-opaque"},
        {"ledger_member": "structure_cluster.<unclassified@0x0>", "disposition": "maybe", "evidence": "x"},
    ])
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    invalid = [e for e in errors if e.startswith("range-disposition-invalid")]
    assert any("unknown ledger member" in e for e in invalid)
    assert any("without evidence" in e for e in invalid)
    assert any("unknown disposition" in e for e in invalid)
    row = next(r for r in payload["rows"] if r["member"] == UNCLASSIFIED_CLUSTER)
    assert row["gap_type"] == "schema-gap"


def test_missing_range_and_parity_files_are_tolerated(tmp_path):
    checker = _load_checker()
    empty = tmp_path / "empty"
    empty.mkdir()
    payload, errors = checker.build_payload(parity_dir=empty)
    assert not errors, errors


def test_breakable_surface_correction_and_collision_row_status():
    checker = _load_checker()
    payload, _ = checker.build_payload(parity_dir=checker.ROOT / "docs" / "reports" / "no-such-dir")
    rows = {r["member"]: r for r in payload["rows"]}
    material = rows["structure_material.breakable_surface_index"]
    assert material["ce_access_sites"] == [
        "submodules/halo-ce-universal/source/structures/structure_render.c:590"]
    assert "path.c:654" in material["ce_correction"]
    # collision_surface.breakable_surface_index has no schema row of its own; it sits inside the
    # unclassified range collision_surface.<unclassified@0x8> (bytes 8..10).
    assert "collision_surface.breakable_surface_index" not in rows
    owner = rows["collision_surface.<unclassified@0x8>"]
    assert owner["classification"] == "blocked"
    assert "breakable_surface_index" in owner["gap_reason"]


def _deferral_member_parity(tmp_path, owner_result, deferring_lane="fog", owner_lane="collision"):
    checker = _load_checker()
    member = "structure_fog_plane.runtime_material_type"
    test_file = tmp_path / "test_runtime_material_type.py"
    test_file.write_text("# runtime_material_type owner pass\n")
    parity_dir = tmp_path / "parity"
    parity_dir.mkdir()
    (parity_dir / "m4-c4-parity-deferring-2026-10-26.json").write_text(json.dumps({"lane": deferring_lane, "rows": [{
        "member": member, "test": "", "result": "blocked", "scope": "family-level",
        "notes": "Owned by the owner lane; deferred."}]}))
    (parity_dir / "m4-c4-parity-owner-2026-10-26.json").write_text(json.dumps({"lane": owner_lane, "rows": [{
        "member": member, "test": str(test_file), "result": owner_result, "scope": "member-exact",
        "notes": ""}]}))
    return checker.build_payload(parity_dir=parity_dir), member


def test_owner_member_exact_pass_supersedes_deferral_row(tmp_path):
    (payload, errors), member = _deferral_member_parity(tmp_path, "pass")
    assert not [e for e in errors if e.startswith("parity-evidence-invalid")], errors
    row = next(r for r in payload["rows"] if r["member"] == member)
    assert row["classification"] == "consumed"
    assert "supersedes fog deferral" in row["gap_reason"]


def test_deferral_without_owner_pass_stays_blocked(tmp_path):
    checker = _load_checker()
    member = "structure_fog_plane.runtime_material_type"
    parity_dir = tmp_path / "parity"
    parity_dir.mkdir()
    (parity_dir / "m4-c4-parity-deferring-2026-10-26.json").write_text(json.dumps({"lane": "fog", "rows": [{
        "member": member, "test": "", "result": "blocked", "scope": "family-level", "notes": "deferred"}]}))
    payload, errors = checker.build_payload(parity_dir=parity_dir)
    row = next(r for r in payload["rows"] if r["member"] == member)
    assert row["classification"] == "blocked"
    assert row["gap_reason"] == "parity lane fog blocked: deferred"


def test_owner_blocked_result_does_not_supersede(tmp_path):
    (payload, errors), member = _deferral_member_parity(tmp_path, "blocked")
    row = next(r for r in payload["rows"] if r["member"] == member)
    assert row["classification"] == "blocked"
    assert row["gap_type"] == "parity-blocked"
