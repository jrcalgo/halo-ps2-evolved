"""The C5 local-setup rows can qualify only from recorded guest evidence (tools/c5_local_setup_rows.py).

Each test builds a fixture repository root (the C2 inputs copied from the real tree, plus whatever guest evidence the
test writes), so the committed files are never touched. The guest runner's own evaluation (tools/c5_guest_qualification.py)
produces the evidence records, so the chain from a PCSX2 log to a qualified row is the one that ships.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROWS_TOOL = ROOT / "tools/c5_local_setup_rows.py"
GUEST_TOOL = ROOT / "tools/c5_guest_qualification.py"
C2_INPUTS = (
    "src/stream/hcu_memory_profile.c",
    "docs/reports/m2-c2-profile-guarded-fit-2026-10-24.json",
    "docs/reports/m2-c2-profile-matrix-2026-10-24.json",
)
SHA = "a" * 64


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rows_tool = load(ROWS_TOOL, "c5_local_setup_rows_under_test")
guest_tool = load(GUEST_TOOL, "c5_guest_qualification_under_test")


def fixture_root(tmp_path: Path) -> Path:
    """A root with the C2 inputs and no guest evidence."""
    root = tmp_path / "repo"
    for rel in C2_INPUTS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    (root / "docs/reports").mkdir(parents=True, exist_ok=True)
    return root


def write_evidence(root: Path, name: str, record) -> Path:
    path = root / "docs/reports" / f"c5-guest-{name}.json"
    path.write_text(json.dumps(record, indent=2) + "\n" if not isinstance(record, str) else record)
    return path


def good_record(**overrides):
    """A record a qualified stock-coop run writes (team-slayer, bloodgulch, normal, 4 humans, no bots)."""
    record = {
        "format": "hcu-c5-guest-evidence-v1",
        "run": "good",
        "elf_sha256": SHA,
        "log_sha256": SHA,
        "terminated_ok": True,
        "returncode": 0,
        "boot_line": True,
        "session_hash": "0123456789abcdef",
        "session": {"mode": "coop", "coop": 1, "humans": 4, "bots": 0, "map": "bloodgulch",
                    "difficulty": "normal", "status": "qualified"},
        "rows": {"coop-team-slayer": {"status": "claimed"}},
    }
    record.update(overrides)
    return record


def bot_record(**overrides):
    bot_rows = {name: {"status": "claimed"} for name in guest_tool.ROW_NAMES[:5]}
    record = good_record(rows={"coop-team-slayer": {"status": "claimed"}, **bot_rows},
                         session={"mode": "coop", "coop": 1, "humans": 1, "bots": 4, "map": "bloodgulch",
                                  "difficulty": "normal", "status": "qualified"})
    record.update(overrides)
    return record


def row_for(inc_text: str, map_name: str) -> str:
    for line in inc_text.splitlines():
        if line.startswith('\t{ "%s",' % map_name):
            return line
    raise AssertionError(map_name)


def qualified_maps(report: dict) -> set:
    return {row["map"] for row in report["setup_rows"] if row["qualified"]}


def test_no_evidence_means_no_qualified_row(tmp_path):
    inc, report = rows_tool.build(fixture_root(tmp_path))
    assert report["qualified_row_count"] == 0
    assert qualified_maps(report) == set()
    for name in rows_tool.MAPS:
        assert row_for(inc, name).startswith('\t{ "%s", HCU_LOCAL_MODE_STOCK_COOP, 0x0u, 0u, 0u }' % name)
    assert not any("qualified=1" in line for line in inc.splitlines() if line.startswith("\t{"))


def test_committed_table_matches_the_generator():
    result = subprocess.run([sys.executable, str(ROWS_TOOL), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "qualified rows: 0 of 13" in result.stdout


def test_a_qualified_record_qualifies_its_map(tmp_path):
    root = fixture_root(tmp_path)
    write_evidence(root, "good", good_record())
    inc, report = rows_tool.build(root)
    assert qualified_maps(report) == {"bloodgulch"}
    assert row_for(inc, "bloodgulch").startswith('\t{ "bloodgulch", HCU_LOCAL_MODE_STOCK_COOP, 0x4u, 4u, 0u }')
    assert row_for(inc, "carousel").startswith('\t{ "carousel", HCU_LOCAL_MODE_STOCK_COOP, 0x0u, 0u, 0u }')


@pytest.mark.parametrize("label,record", [
    ("measuring session", good_record(session={"mode": "coop", "coop": 1, "humans": 4, "bots": 0,
                                               "map": "bloodgulch", "difficulty": "normal",
                                               "status": "measuring"})),
    ("no status", good_record(session={"mode": "coop", "coop": 1, "humans": 4, "bots": 0,
                                       "map": "bloodgulch", "difficulty": "normal"})),
    ("nonzero exit", good_record(returncode=1, terminated_ok=False)),
    ("not terminated", good_record(terminated_ok=False)),
    ("no boot line", good_record(boot_line=False)),
    ("no session hash", good_record(session_hash=None)),
    ("coop row not claimed", good_record(rows={"coop-team-slayer": {"status": "refused"}})),
    ("survival run", good_record(session={"mode": "survival", "coop": -1, "humans": 1, "bots": 0,
                                          "map": "bloodgulch", "difficulty": "normal", "status": "qualified"})),
    ("unknown map", good_record(session={"mode": "coop", "coop": 1, "humans": 4, "bots": 0,
                                         "map": "a30", "difficulty": "normal", "status": "qualified"})),
    ("bots without bot rows", bot_record(rows={"coop-team-slayer": {"status": "claimed"}})),
    ("wrong format", good_record(format="other")),
    ("bad elf sha", good_record(elf_sha256="not-a-sha")),
])
def test_a_record_that_does_not_support_a_claim_qualifies_nothing(tmp_path, label, record):
    root = fixture_root(tmp_path)
    write_evidence(root, "case", record)
    _, report = rows_tool.build(root)
    assert qualified_maps(report) == set(), label
    assert report["qualified_row_count"] == 0, label


def test_bots_qualify_only_with_every_bot_row_claimed(tmp_path):
    root = fixture_root(tmp_path)
    write_evidence(root, "bots", bot_record())
    _, report = rows_tool.build(root)
    assert qualified_maps(report) == {"bloodgulch"}
    inc, _ = rows_tool.build(root)
    assert row_for(inc, "bloodgulch").startswith('\t{ "bloodgulch", HCU_LOCAL_MODE_STOCK_COOP, 0x4u, 1u, 4u }')


def test_row_population_is_the_smallest_qualified_difficulty(tmp_path):
    root = fixture_root(tmp_path)
    write_evidence(root, "normal", good_record(run="normal"))
    write_evidence(root, "heroic", good_record(run="heroic", session={
        "mode": "coop", "coop": 1, "humans": 2, "bots": 0, "map": "bloodgulch", "difficulty": "heroic",
        "status": "qualified"}))
    inc, report = rows_tool.build(root)
    # difficulties normal (bit 2) and heroic (bit 3); population is the smaller maximum (2 humans)
    assert row_for(inc, "bloodgulch").startswith('\t{ "bloodgulch", HCU_LOCAL_MODE_STOCK_COOP, 0xcu, 2u, 0u }')
    assert report["qualified_row_count"] == 1


def test_a_measuring_run_never_qualifies_even_beside_good_evidence(tmp_path):
    root = fixture_root(tmp_path)
    measuring = good_record(run="measure", session={"mode": "coop", "coop": 1, "humans": 4, "bots": 0,
                                                    "map": "carousel", "difficulty": "normal",
                                                    "status": "measuring"})
    write_evidence(root, "measure", measuring)
    _, report = rows_tool.build(root)
    assert qualified_maps(report) == set()
    entry = [e for e in report["evidence"] if e["file"].endswith("c5-guest-measure.json")][0]
    assert entry["decision"] == "no-claim"


def test_unreadable_evidence_is_reported_not_ignored(tmp_path):
    root = fixture_root(tmp_path)
    write_evidence(root, "broken", "{not json")
    _, report = rows_tool.build(root)
    assert report["qualified_row_count"] == 0
    assert report["evidence"][0]["decision"] == "rejected"


def test_the_guest_runner_cannot_claim_from_a_measuring_log(tmp_path):
    text = ("HALO_PS2_LOCAL boot\n"
            "HALO_PS2_C5 session-start mode=coop coop=1 humans=4 bots=0 qualified=8 map=bloodgulch "
            "difficulty=normal status=measuring\n"
            "HALO_PS2_C5 session-hash tick=9 hash=0123456789abcdef\n")
    rows = guest_tool.evaluate_log(text, terminated_ok=True)
    assert all(rows[name]["status"] == "refused" for name in guest_tool.ROW_NAMES)


def test_the_full_chain_from_a_qualified_log_to_a_qualified_row(tmp_path):
    text = ("HALO_PS2_LOCAL boot\n"
            "HALO_PS2_C5 session-start mode=coop coop=1 humans=4 bots=0 qualified=8 map=bloodgulch "
            "difficulty=normal status=qualified\n"
            "HALO_PS2_C5 session-hash tick=9 hash=0123456789abcdef\n")
    rows = guest_tool.evaluate_log(text, terminated_ok=True)
    assert rows["coop-team-slayer"]["status"] == "claimed"
    record = guest_tool.evidence_record("chain", SHA, SHA, text, True, 0, rows)
    root = fixture_root(tmp_path)
    write_evidence(root, "chain", record)
    inc, report = rows_tool.build(root)
    assert qualified_maps(report) == {"bloodgulch"}
    assert row_for(inc, "bloodgulch").startswith('\t{ "bloodgulch", HCU_LOCAL_MODE_STOCK_COOP, 0x4u, 4u, 0u }')


def test_the_full_chain_from_a_measuring_log_qualifies_nothing(tmp_path):
    text = ("HALO_PS2_LOCAL boot\n"
            "HALO_PS2_C5 session-start mode=coop coop=1 humans=4 bots=0 qualified=8 map=bloodgulch "
            "difficulty=normal status=measuring\n"
            "HALO_PS2_C5 session-hash tick=9 hash=0123456789abcdef\n")
    rows = guest_tool.evaluate_log(text, terminated_ok=True)
    record = guest_tool.evidence_record("chain-measure", SHA, SHA, text, True, 0, rows)
    root = fixture_root(tmp_path)
    write_evidence(root, "chain-measure", record)
    _, report = rows_tool.build(root)
    assert report["qualified_row_count"] == 0
