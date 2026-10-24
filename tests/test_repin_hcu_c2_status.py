import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import repin_hcu_c2_status as repin

T0 = 1_700_000_000


def touch(path, t):
    os.utime(path, (t, t))


def build(tmp, rows=2, row_pass=True, include_matrix_in=("C2.1", "C2.2"), obj_t=T0 + 100,
          src_t=T0 + 10, consumed=("src/a.c",)):
    """Synthetic repo: sources, a matrix run whose .d files list `consumed`, a status."""
    for rel, text in (("src/a.c", "int a;"), ("src/b.c", "int b;"), ("tools/c.py", "x=1")):
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        touch(p, src_t)
    matrix_rows = []
    for i in range(rows):
        link = tmp / f"build/m/r{i}/link"
        link.mkdir(parents=True)
        elf = link / "x.elf"
        elf.write_bytes(b"elf%d" % i)
        touch(elf, T0 + 50)
        (link / "stream").mkdir()
        obj = link / "stream/a.o"
        obj.write_bytes(b"o")
        touch(obj, obj_t)
        (link / "stream/a.d").write_text(
            f"{obj}: \\\n " + " \\\n ".join(consumed) + "\n")
        result = tmp / f"build/m/r{i}/result.json"
        result.write_text("{}")
        touch(result, T0 + 60)
        matrix_rows.append({"row": f"r{i}", "pass": row_pass, "provenance": {
            "elf": str(elf), "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
            "elf_hash_valid": True, "build_identity_valid": True,
            "result_json": f"build/m/r{i}/result.json"}})
    docs = tmp / "docs"
    docs.mkdir()
    (docs / "matrix.json").write_text(json.dumps({
        "rows": matrix_rows, "exit_met": row_pass, "all_selected_session_rows_passed": row_pass,
        "failing_rows": [], "unmeasured_rows": []}))
    (docs / "fit.json").write_text("{}")
    touch(docs / "matrix.json", T0 + 70)
    touch(docs / "fit.json", T0 + 70)
    pin = lambda rel, role: {"path": rel, "sha256": "0" * 64, "role": role}
    reqs = []
    for n in (1, 2, 3):
        files = [pin("src/a.c", "source"), pin("src/b.c", "source"), pin("tools/c.py", "source")]
        if f"C2.{n}" in include_matrix_in:
            files += [pin("docs/matrix.json", "report"), pin("docs/fit.json", "report")]
        reqs.append({"id": f"C2.{n}", "evidence_files": files})
    status = {"profile_matrix": {"report": "docs/matrix.json", "fit_ledger": "docs/fit.json"},
              "requirements": reqs}
    (tmp / "status.json").write_text(json.dumps(status))
    return status


def by_req(report, field):
    out = {}
    for item in report[field]:
        out.setdefault(item["requirement"], set()).add(item["path"])
    return out


def test_consumed_source_is_refreshed_with_justification(tmp_path):
    build(tmp_path)
    status, report = repin.repin(tmp_path, Path("status.json"))
    refreshed = by_req(report, "refreshed")
    assert "src/a.c" in refreshed["C2.1"] and "src/a.c" in refreshed["C2.2"]
    entry = next(r for r in report["refreshed"] if r["requirement"] == "C2.1" and r["path"] == "src/a.c")
    assert entry["justification"]["evidence_file"] == "docs/matrix.json"
    assert entry["justification"]["rows"] == 2
    assert entry["new_sha256"] == hashlib.sha256(b"int a;").hexdigest()
    pin = next(p for p in status["requirements"][0]["evidence_files"] if p["path"] == "src/a.c")
    assert pin["sha256"] == entry["new_sha256"]
    assert status["requirements"][0]["repinned_dependencies"][0]["justification"]


def test_stale_without_new_evidence_stays_stale(tmp_path):
    build(tmp_path)
    status, report = repin.repin(tmp_path, Path("status.json"))
    stale = by_req(report, "still_stale")
    # not consumed by the build at all
    assert {"src/b.c", "tools/c.py"} <= stale["C2.1"]
    # C2.3 lists no regenerated evidence, so even the consumed file stays stale
    assert "src/a.c" in stale["C2.3"]
    assert "C2.3" not in by_req(report, "refreshed")
    pin = next(p for p in status["requirements"][2]["evidence_files"] if p["path"] == "src/a.c")
    assert pin["sha256"] == "0" * 64


def test_source_changed_after_the_build_stays_stale(tmp_path):
    build(tmp_path, obj_t=T0 + 5, src_t=T0 + 10)
    _, report = repin.repin(tmp_path, Path("status.json"))
    assert "src/a.c" in by_req(report, "still_stale")["C2.1"]
    assert "src/a.c" not in by_req(report, "refreshed").get("C2.1", set())


def test_failing_matrix_refreshes_nothing(tmp_path):
    build(tmp_path, row_pass=False)
    _, report = repin.repin(tmp_path, Path("status.json"))
    assert report["refreshed"] == []


def test_edited_elf_invalidates_the_run(tmp_path):
    build(tmp_path)
    (tmp_path / "build/m/r0/link/x.elf").write_bytes(b"tampered")
    _, report = repin.repin(tmp_path, Path("status.json"))
    assert report["refreshed"] == []


def test_matched_pins_are_untouched(tmp_path):
    status = build(tmp_path)
    good = hashlib.sha256(b"int a;").hexdigest()
    status["requirements"][0]["evidence_files"][0]["sha256"] = good
    (tmp_path / "status.json").write_text(json.dumps(status))
    out, report = repin.repin(tmp_path, Path("status.json"))
    assert "src/a.c" not in by_req(report, "refreshed").get("C2.1", set())
    assert out["requirements"][0]["evidence_files"][0]["sha256"] == good


def fixture_repo(tmp, result_t, source_t):
    (tmp / "src").mkdir()
    (tmp / "src/s.c").write_text("int s;")
    touch(tmp / "src/s.c", source_t)
    out = tmp / "build/f"
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps({
        "result": "passed", "passing_checks": 3, "compile_command": ["gcc", str(tmp / "src/s.c")]}))
    (out / "fx").write_bytes(b"exe")
    touch(out / "result.json", result_t)
    touch(out / "fx", result_t)
    pins = [{"path": "build/f/result.json", "sha256": "0" * 64, "role": "report"},
            {"path": "build/f/fx", "sha256": "0" * 64, "role": "executable"},
            {"path": "src/s.c", "sha256": "0" * 64, "role": "source"}]
    (tmp / "docs").mkdir()
    status = {"profile_matrix": {"report": "docs/none.json", "fit_ledger": "docs/none2.json"},
              "requirements": [{"id": "C2.8", "evidence_files": pins}]}
    (tmp / "status.json").write_text(json.dumps(status))


def test_fixture_outputs_newer_than_sources_are_refreshed(tmp_path):
    fixture_repo(tmp_path, T0 + 100, T0 + 10)
    _, report = repin.repin(tmp_path, Path("status.json"))
    assert {r["path"] for r in report["refreshed"]} == {"build/f/result.json", "build/f/fx", "src/s.c"}
    assert all(r["justification"]["evidence_file"] == "build/f/result.json" for r in report["refreshed"])


def test_fixture_older_than_its_sources_stays_stale(tmp_path):
    fixture_repo(tmp_path, T0 + 10, T0 + 100)
    _, report = repin.repin(tmp_path, Path("status.json"))
    assert report["refreshed"] == []
    assert len(report["still_stale"]) == 3


def test_depfile_parser_handles_continuations(tmp_path):
    target, deps = repin.parse_depfile(f"{tmp_path}/x.o: \\\n src/a.c \\\n {tmp_path}/src/b.h\n", tmp_path)
    assert deps == {"src/a.c", "src/b.h"}


def test_second_run_keeps_the_justification_records(tmp_path):
    build(tmp_path)
    status, first = repin.repin(tmp_path, Path("status.json"))
    (tmp_path / "status.json").write_text(json.dumps(status))
    again, second = repin.repin(tmp_path, Path("status.json"))
    assert second["refreshed"] == []
    assert again["requirements"][0]["repinned_dependencies"] == status["requirements"][0]["repinned_dependencies"]
    assert again["requirements"][0]["repinned_dependencies"]
