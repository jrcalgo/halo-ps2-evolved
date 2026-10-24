#!/usr/bin/env python3
"""C2.3 donor-slack checks (tools/c2_budget_donor_slack.py).

The decision must not treat an incomplete or non-multiplayer measurement as a
safe donor, and the budget must stay unchanged while no safe donor covers the
elf_static overflow. Runs under pytest or as a script.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_budget_donor_slack as donors  # noqa: E402

BUDGET = json.loads((ROOT / "config/memory-budget.json").read_text())
ELF_STATIC = next(r["bytes"] for r in BUDGET["regions"] if r["name"] == "elf_static")
OWNERS = ROOT / "build/m2-c2-r5-budget/owners.json"


def _owners(need):
    return {"elf_static_need_bytes": need}


def test_no_incomplete_measurement_is_a_safe_donor():
    result = donors.decide(_owners(ELF_STATIC + 979064), BUDGET)
    assert result["safe_donor_total_bytes"] == 0
    assert all(row["safe_donor_bytes"] == 0 for row in result["donors"])


def test_overflow_is_not_covered_and_budget_is_not_revised():
    result = donors.decide(_owners(ELF_STATIC + 979064), BUDGET)
    assert result["overflow_bytes"] == 979064
    assert result["budget_revision_safe"] is False
    assert result["shortfall_after_safe_donors_bytes"] == 979064


def test_complete_donor_is_counted_after_margin(monkeypatch):
    fake = dict(donors.DONORS)
    fake["streaming"] = dict(fake["streaming"], complete=True)
    monkeypatch.setattr(donors, "DONORS", fake)
    result = donors.decide(_owners(ELF_STATIC + 100000), BUDGET)
    row = next(r for r in result["donors"] if r["region"] == "streaming")
    assert row["safe_donor_bytes"] == 587336 - row["safety_margin_bytes"]
    assert result["budget_revision_safe"] is (row["safe_donor_bytes"] >= 100000)


def test_ungated_diagnostics_are_not_counted_as_donors():
    result = donors.decide(_owners(ELF_STATIC + 979064), BUDGET)
    assert result["ungated_diagnostic_measured_bytes"] == 26220
    assert result["safe_donor_total_bytes"] == 0


def test_live_owner_audit_matches_budget_when_elf_present():
    if not OWNERS.exists():
        return
    owners = json.loads(OWNERS.read_text())
    result = donors.decide(owners, BUDGET)
    assert result["elf_static_reservation_bytes"] == ELF_STATIC
    assert result["overflow_bytes"] == max(0, owners["elf_static_need_bytes"] - ELF_STATIC)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
