#!/usr/bin/env python3
"""Refresh C2 status dependency pins only where regenerated evidence justifies it.

A pin in a requirement's evidence_files goes stale when the pinned file changes.
This tool never re-pins blindly.  For one requirement and one stale pin it
refreshes the sha256 only when ALL of these hold:

* the requirement itself lists the regenerating evidence (the matrix report, or
  a host-fixture result.json) among its evidence_files;
* that evidence run is validated (every row passed, ELF hashes recomputed and
  equal to the recorded ones; or the fixture result says passed);
* the dependency's current content provably existed before the run consumed
  it: the dependency appears in the run's compiler dependency files (.d) with an
  object newer than the file, in the CE closure result.json with an equal
  source_sha256 and an older mtime than the first ELF, or in the fixture
  result.json compile command with the fixture output newer than it;
* for a pin that is itself regenerated output (matrix/fit report, fixture
  result.json and executable) the output is newer than every input.

Everything else stays stale and is listed.  Each refreshed pin gets a
justification record naming the evidence file and run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = Path("docs/reports/m2-c2-status-2026-10-23.json")
CE_ROOT = "submodules/halo-ce-universal"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _sha_or_none(path):
    try:
        return sha(path)
    except OSError:
        return None


def _rel(path, root):
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return str(p)
    return p.as_posix().lstrip("./")


def parse_depfile(text, root):
    """Return (target, set(dependencies relative to root)) from a make .d file."""
    text = text.replace("\\\n", " ")
    target, _, rest = text.partition(":")
    deps = {_rel(tok, root) for tok in rest.split()}
    return target.strip(), deps


class MatrixRun:
    """A validated matrix run: its rows' ELFs and the objects that built them."""

    def __init__(self, root, report_path):
        self.root = Path(root)
        self.report_path = report_path
        report = json.loads((self.root / report_path).read_text())
        self.rows = report.get("rows", [])
        self.problems = []
        if not self.rows or not report.get("exit_met") or not report.get("all_selected_session_rows_passed"):
            self.problems.append("matrix report does not record every row passing")
        if report.get("failing_rows") or report.get("unmeasured_rows"):
            self.problems.append("matrix report has failing or unmeasured rows")
        self.elf_mtimes, self.dep_objects, self.closure_dirs = [], {}, set()
        for row in self.rows:
            prov = row.get("provenance", {})
            if not row.get("pass") or not prov.get("elf_hash_valid") or not prov.get("build_identity_valid"):
                self.problems.append(f"{row.get('row')}: row not passing or identity invalid")
                continue
            elf = Path(prov.get("elf", ""))
            if not elf.is_file() or sha(elf) != prov.get("elf_sha256"):
                self.problems.append(f"{row.get('row')}: ELF missing or hash differs from record")
                continue
            self.elf_mtimes.append(elf.stat().st_mtime)
            link = elf.parent
            for dep in link.rglob("*.d"):
                try:
                    target, deps = parse_depfile(dep.read_text(), self.root)
                except OSError:
                    continue
                obj = dep.with_suffix(".o")
                if not obj.is_file():
                    continue
                for d in deps:
                    self.dep_objects.setdefault(d, {}).setdefault(row["row"], []).append(
                        obj.stat().st_mtime)
            lmap = link / "hcu-parent-link.map"
            if lmap.is_file():
                for m in re.finditer(r"(/[^\s()]+)/[^/\s()]+\.o\b", lmap.read_text(errors="replace")):
                    d = Path(m.group(1))
                    if (d / "result.json").is_file():
                        self.closure_dirs.add(d)
        self.first_elf_mtime = min(self.elf_mtimes) if self.elf_mtimes else None
        self.closure_units = {}
        self.closure_mtime = {}
        for d in sorted(self.closure_dirs):
            try:
                data = json.loads((d / "result.json").read_text())
            except (OSError, ValueError):
                continue
            if isinstance(data.get("units"), dict):
                for key, unit in data["units"].items():
                    self.closure_units[f"{CE_ROOT}/{key}"] = unit
                    self.closure_mtime[f"{CE_ROOT}/{key}"] = (d / "result.json").stat().st_mtime
        self.valid = not self.problems and self.first_elf_mtime is not None
        self.last_result_mtime = max(
            (Path(self.root / r["provenance"]["result_json"]).stat().st_mtime
             for r in self.rows if (self.root / r["provenance"].get("result_json", "x")).is_file()),
            default=None)

    def source_justification(self, dep):
        path = self.root / dep
        if not path.is_file():
            return None
        mtime = path.stat().st_mtime
        built = self.dep_objects.get(dep)
        if built and len(built) == len(self.rows):
            if all(m > mtime for objs in built.values() for m in objs):
                return {"basis": "compiler dependency files (.d) of every matrix row list this file and "
                                 "every object compiled from it is newer than the file",
                        "rows": len(built), "file_mtime": mtime,
                        "oldest_object_mtime": min(m for objs in built.values() for m in objs)}
        unit = self.closure_units.get(dep)
        if unit and unit.get("source_sha256") == sha(path) and mtime < self.first_elf_mtime \
                and self.closure_mtime[dep] > mtime:
            return {"basis": "CE closure result.json records source_sha256 equal to the current content, "
                             "the file is older than the first matrix ELF and than the closure build",
                    "file_mtime": mtime, "closure_unit_object_sha256": unit.get("object_sha256"),
                    "first_elf_mtime": self.first_elf_mtime}
        return None


def fixture_runs(root, requirement):
    """Passed host-fixture result.json pins of a requirement with their sources."""
    runs = {}
    for pin in requirement["evidence_files"]:
        path = root / pin["path"]
        if not pin["path"].endswith("result.json") or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except ValueError:
            continue
        command = data.get("compile_command")
        if data.get("result") != "passed" or not isinstance(command, list):
            continue
        sources = {_rel(tok, root) for tok in command
                   if isinstance(tok, str) and tok.endswith((".c", ".h"))}
        sources = {s for s in sources if (root / s).is_file()}
        runs[pin["path"]] = {"result": path, "sources": sources, "data": data,
                             "executable": [p["path"] for p in requirement["evidence_files"]
                                            if p.get("role") == "executable"
                                            and Path(p["path"]).parent == Path(pin["path"]).parent]}
    return runs


def repin(root=ROOT, status_path=STATUS):
    root = Path(root)
    status = json.loads((root / status_path).read_text())
    matrix_path = status["profile_matrix"]["report"]
    fit_path = status["profile_matrix"]["fit_ledger"]
    matrix = MatrixRun(root, matrix_path) if (root / matrix_path).is_file() else None
    report = {"refreshed": [], "still_stale": []}
    for req in status["requirements"]:
        pins = req["evidence_files"]
        listed = {p["path"] for p in pins}
        fixtures = fixture_runs(root, req)
        refreshed, remaining = [], []
        for pin in pins:
            path = root / pin["path"]
            actual = _sha_or_none(path)
            if actual == pin["sha256"]:
                continue
            why = None
            if actual is None:
                remaining.append({"path": pin["path"], "reason": "missing"})
                continue
            # 1. regenerated matrix/fit reports: the regenerating evidence itself.
            if pin["path"] in (matrix_path, fit_path) and matrix and matrix.valid \
                    and matrix_path in listed and fit_path in listed:
                newest_input = matrix.last_result_mtime
                if newest_input is not None and path.stat().st_mtime >= newest_input:
                    why = {"evidence_file": matrix_path,
                           "run": f"matrix rerun, {len(matrix.rows)} rows passing, ELFs "
                                  f"{matrix.first_elf_mtime:.0f}..{max(matrix.elf_mtimes):.0f} (epoch), "
                                  "report written after the last row result",
                           "basis": "pinned file is the regenerated output of the validated run"}
            # 2. sources consumed by the matrix build.
            elif matrix and matrix.valid and matrix_path in listed and pin.get("role") == "source":
                j = matrix.source_justification(pin["path"])
                if j:
                    why = {"evidence_file": matrix_path,
                           "run": f"matrix rerun, {len(matrix.rows)} rows, first ELF mtime "
                                  f"{matrix.first_elf_mtime:.0f}", **j}
            # 3. host-fixture outputs and sources regenerated together.
            if why is None:
                for result_path, run in fixtures.items():
                    rm = run["result"].stat().st_mtime
                    exe = [root / e for e in run["executable"]]
                    inputs_old = all((root / s).stat().st_mtime < rm for s in run["sources"]) \
                        and all(e.stat().st_mtime >= max((root / s).stat().st_mtime for s in run["sources"])
                                for e in exe if e.is_file())
                    if not inputs_old:
                        continue
                    if pin["path"] == result_path or pin["path"] in run["executable"] \
                            or pin["path"] in run["sources"]:
                        why = {"evidence_file": result_path,
                               "run": f"host fixture result {run['data'].get('passing_checks')} passing "
                                      f"checks, result mtime {rm:.0f}",
                               "basis": "fixture output/executable written after every source in its "
                                        "compile command; the pinned file is that output, the executable "
                                        "or one of those sources"}
                        break
            if why is None:
                remaining.append({"path": pin["path"], "reason":
                                  "no regenerated evidence for this requirement consumed the current content"})
                continue
            refreshed.append({"path": pin["path"], "old_sha256": pin["sha256"],
                              "new_sha256": actual, "justification": why})
            pin["sha256"] = actual
        # Keep earlier justifications while the pin still holds the content they
        # justified, so a second run never erases the record of a refresh.
        kept = [r for r in req.get("repinned_dependencies", [])
                if any(p["path"] == r["path"] and p["sha256"] == r["new_sha256"] for p in pins)
                and r["path"] not in {x["path"] for x in refreshed}]
        refreshed_all = kept + refreshed
        req["repinned_dependencies"] = refreshed_all
        req["stale_dependencies_remaining"] = remaining
        report["refreshed"] += [{"requirement": req["id"], **r} for r in refreshed]
        report["still_stale"] += [{"requirement": req["id"], **r} for r in remaining]
    # The top-level validation pins of the two reports follow only when the
    # same report pin was refreshed with a justification above.
    done = {r["path"] for r in report["refreshed"]}
    for key, rel in (("profile_matrix", matrix_path), ("guarded_fit_ledger", fit_path)):
        entry = status.get("validation", {}).get(key)
        if entry and entry.get("path") == rel and rel in done:
            entry["sha256"] = sha(root / rel)
    return status, report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status", type=Path, default=STATUS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    status, report = repin(ROOT, args.status)
    if not args.dry_run:
        (ROOT / args.status).write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps({"refreshed": len(report["refreshed"]), "still_stale": len(report["still_stale"]),
                      "still_stale_detail": report["still_stale"]}, indent=1))


if __name__ == "__main__":
    main()
