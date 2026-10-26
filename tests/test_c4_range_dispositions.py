"""C4 item 1 (ranges lane): every unclassified DWARF range in the member ledger has an honest disposition."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "audit_c4_range_dispositions.py"
LEDGER_TOOL = ROOT / "tools" / "audit_c4_member_ledger.py"
OUT = ROOT / "docs" / "reports" / "m4-c4-range-dispositions-2026-10-26.json"
LEDGER = ROOT / "docs" / "reports" / "m4-c4-member-ledger-2026-10-26.json"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load(TOOL, "audit_c4_range_dispositions")


@pytest.fixture(scope="module")
def built(tool):
    payload, errors = tool.build()
    assert errors == []
    return payload


def _targets():
    rows = json.loads(LEDGER.read_text())["rows"]
    return [r for r in rows if r["inventory_classification"] == "unclassified"
            and (r.get("gap_type") == "unclassified-dwarf-range" or r.get("range_source"))]


def test_checker_passes_on_committed_outputs():
    result = subprocess.run([sys.executable, "-I", str(TOOL)], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_committed_json_equals_regeneration(built):
    assert json.loads(OUT.read_text()) == json.loads(json.dumps(built))


def test_every_unclassified_range_has_exactly_one_disposition(built):
    targets = {r["member"] for r in _targets()}
    assert len(targets) == 43
    rows = built["rows"]
    assert [r["ledger_member"] for r in rows].count(rows[0]["ledger_member"]) == 1
    assert {r["ledger_member"] for r in rows} == targets
    assert built["summary"]["unresolved"] == 0


def test_vocabulary_and_required_fields(tool, built):
    counts = {d: 0 for d in tool.DISPOSITIONS}
    for r in built["rows"]:
        assert r["disposition"] in tool.DISPOSITIONS
        counts[r["disposition"]] += 1
        assert r["evidence"].strip()
        assert r["live_members"], r["ledger_member"]
        if r["disposition"] in ("consumed", "schema-gap"):
            assert r["needs_fixture"] is True
        else:
            assert r["needs_fixture"] is False
        if r["disposition"] == "schema-gap":
            assert r["schema_addition"]
        if r["disposition"] == "blocked":
            assert r["notes"]
        for c in r["citations"]:
            assert c["line"] > 0
    assert counts == built["summary"]["counts"]
    assert sorted(built["needs_fixture"]) == sorted(r["ledger_member"] for r in built["rows"] if r["needs_fixture"])


def test_every_live_member_has_declaration_or_is_type_level(built):
    for r in built["rows"]:
        def walk(members):
            for m in members:
                if "children" in m:
                    yield from walk(m["children"])
                else:
                    yield m
        for m in walk(r["live_members"]):
            if r["type_level"] or r["struct"] in ("byte", "long", "structure_node"):
                continue
            assert m.get("declaration"), (r["ledger_member"], m["name"])


def test_preserved_opaque_members_have_no_runtime_access(built):
    for r in built["rows"]:
        def walk(members):
            for m in members:
                if "children" in m:
                    yield from walk(m["children"])
                else:
                    yield m
        for m in walk(r["live_members"]):
            if m["disposition"] == "preserved-opaque":
                assert m["reads_runtime_count"] == 0 and m["writes_runtime_count"] == 0, (r["ledger_member"], m["name"])


def test_known_gap_is_reported_not_hidden(built):
    row = next(r for r in built["rows"] if r["ledger_member"] == "structure_material.<unclassified@0xae>")
    assert row["disposition"] == "schema-gap"
    assert "TAG_SCHEMA_RESET" in row["schema_addition"]
    names = {c["name"]: c["disposition"] for m in row["live_members"] for c in m.get("children", [])}
    assert names["vertices.hardware_format"] == "schema-gap"
    assert names["lightmap_vertices.base_address"] == "schema-gap"


def test_ledger_ingestion_accepts_the_file_and_clears_the_gap_type():
    ledger_mod = _load(LEDGER_TOOL, "audit_c4_member_ledger_for_ranges")
    rows = copy.deepcopy(json.loads(LEDGER.read_text())["rows"])
    doc = json.loads(OUT.read_text())
    errors = ledger_mod.apply_range_dispositions(rows, [("docs/reports/" + OUT.name, doc)])
    assert errors == []
    assert not [r for r in rows if r.get("gap_type") == "unclassified-dwarf-range"]
    assert all(r["classification"] != "unclassified" for r in rows)


# ---- the checker must fail, not pass, when evidence and claims disagree --------------------------------

def test_missing_disposition_is_an_unresolved_error(tool, monkeypatch):
    spec = copy.deepcopy(tool.SPEC)
    spec.pop("bsp3d_node.<unclassified@0x4>")
    monkeypatch.setattr(tool, "SPEC", spec)
    _, errors = tool.build()
    assert any("unresolved range: bsp3d_node.<unclassified@0x4>" in e for e in errors)


def test_consumed_member_cannot_be_relabelled_preserved_opaque(tool, monkeypatch):
    spec = copy.deepcopy(tool.SPEC)
    key = "collision_surface.<unclassified@0x0>"
    spec[key]["members"][0]["sub"] = "preserved-opaque"
    spec[key]["disposition"] = "preserved-opaque"
    spec[key]["needs_fixture"] = False
    monkeypatch.setattr(tool, "SPEC", spec)
    _, errors = tool.build()
    assert any("declared preserved-opaque but has runtime accesses" in e for e in errors)


def test_unread_member_cannot_be_called_consumed(tool, monkeypatch):
    spec = copy.deepcopy(tool.SPEC)
    key = "structure_weather_palette_entry.<unclassified@0x30>"
    spec[key]["members"][1]["sub"] = "consumed"
    spec[key]["disposition"] = "consumed"
    spec[key]["needs_fixture"] = True
    monkeypatch.setattr(tool, "SPEC", spec)
    _, errors = tool.build()
    assert any("declared consumed but has no runtime read" in e for e in errors)


def test_runtime_normalized_requires_a_load_write(tool, monkeypatch):
    spec = copy.deepcopy(tool.SPEC)
    key = "structure_weather_palette_entry.<unclassified@0x30>"
    spec[key]["members"][1]["sub"] = "runtime-normalized"
    spec[key]["disposition"] = "runtime-normalized"
    monkeypatch.setattr(tool, "SPEC", spec)
    _, errors = tool.build()
    assert any("runtime-normalized without a load/validator write" in e for e in errors)


def test_blocked_requires_a_reason_and_schema_gap_requires_an_addition(tool, monkeypatch):
    spec = copy.deepcopy(tool.SPEC)
    key = "structure_material.<unclassified@0xae>"
    spec[key]["schema_addition"] = None
    monkeypatch.setattr(tool, "SPEC", spec)
    _, errors = tool.build()
    assert any("schema-gap without a stated schema addition" in e for e in errors)


def test_stale_citation_is_an_error(tool, monkeypatch):
    spec = copy.deepcopy(tool.SPEC)
    key = "predicted_resource.<unclassified@0x2>"
    path, _ = spec[key]["cites"][0]
    spec[key]["cites"][0] = (path, "this text does not occur in the file")
    monkeypatch.setattr(tool, "SPEC", spec)
    _, errors = tool.build()
    assert any("cite not found" in e for e in errors)


def test_new_reader_of_a_debug_only_range_is_caught(tool, monkeypatch):
    spec = copy.deepcopy(tool.SPEC)
    key = "leaf_portal.<unclassified@0x0>"
    spec[key]["assert_no_refs"] = [(r"\bdebug_leaf_portals\b", ("structures/structure_render.h",))]
    monkeypatch.setattr(tool, "SPEC", spec)
    _, errors = tool.build()
    assert any("unexpected reference" in e for e in errors)
