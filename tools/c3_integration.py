#!/usr/bin/env python3
"""C3 integration harness: run the 12-case C3 evidence matrix once and score every requirement from those runs.

Cases (all on bloodgulch_mounted_gunner_4p4bot with --c3-workload 4p4bot and HCU_C3_OBJECTS=1):
  render-v1/2/3/4 on the recompiler, render-v4 on the interpreter, render-v4 recompiler with
  --texfence-cap-pages 48, and C3.11 successor runs (beavercreek_mounted_gunner_4p4bot, --render-views 2,
  fault none/preflight/load) in both emulator modes.

Each case is one tools/c2_profile_boot_matrix.py subprocess (it takes the link lock itself; this harness never
uses flock). Completed cases are recorded in <root>/state.json and skipped on rerun. Scoring reads every
completed run's guest log and captures, so a rerun with --score-only or --stamp re-scores without PCSX2.

Usage:
  python3 -I tools/c3_integration.py [--jobs N] [--stamp STAMP] [--dry-run] [--score-only]
Output: build/c3/integration/<stamp>/<case>/ plus report.md and report.json under build/c3/integration/<stamp>/.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "tools/c2_profile_boot_matrix.py"
INTEGRATION_ROOT = ROOT / "build/c3/integration"
ROW = "bloodgulch_mounted_gunner_4p4bot"
SUCC = "beavercreek_mounted_gunner_4p4bot"
FRAMES = 300
CASE_TIMEOUT = 4 * 3600          # host seconds for one matrix subprocess (its own timeouts apply inside)
STATE_NAME = "state.json"
GUEST_LOG = Path("guest/runs/partition-selected/halo_ps2_local.txt")
REQUIREMENTS = ("C3.1", "C3.3", "C3.5", "C3.6", "C3.7", "C3.8", "C3.9", "C3.10", "C3.11", "SNAP")
FIELD = re.compile(r"(?:^|\s)([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)")


def build_cases() -> list[dict]:
    cases = []
    for views in (1, 2, 3, 4):
        cases.append({"name": f"render-v{views}-recompiler", "kind": "render", "views": views,
                      "mode": "recompiler", "cap_pages": 0, "fault": None})
    cases.append({"name": "render-v4-interpreter", "kind": "render", "views": 4,
                  "mode": "interpreter", "cap_pages": 0, "fault": None})
    cases.append({"name": "render-v4-recompiler-cap48", "kind": "render", "views": 4,
                  "mode": "recompiler", "cap_pages": 48, "fault": None})
    for mode in ("recompiler", "interpreter"):
        for fault in ("none", "preflight", "load"):
            cases.append({"name": f"c3-11-{fault}-{mode}", "kind": "successor", "views": 2,
                          "mode": mode, "cap_pages": 0, "fault": fault})
    return cases


def load_matrix():
    """Import tools/c2_profile_boot_matrix.py by path (the harness runs with -I, so the script dir is not on sys.path)."""
    spec = importlib.util.spec_from_file_location("c2m_integration", MATRIX_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_dir(root: Path, case: dict) -> Path:
    return root / case["name"]


def matrix_argv(case: dict, out_dir: Path, package_root: Path) -> list[str]:
    argv = [sys.executable, "-I", str(MATRIX_PATH), "--c3", "--c3-local-players", str(case["views"]), "--rows", ROW,
            "--emu-mode", case["mode"], "--output-root", str(out_dir), "--package-root", str(package_root)]
    if case["kind"] == "render":
        argv += ["--render-views", str(case["views"]), "--render-frames", str(FRAMES)]
    else:
        argv += ["--successor", SUCC, "--successor-fault", case["fault"], "--render-views", str(case["views"]),
                 "--render-frames", str(FRAMES)]
    if case["cap_pages"]:
        argv += ["--texfence-cap-pages", str(case["cap_pages"])]
    return argv


def result_path(c2m, root: Path, case: dict) -> Path:
    """Where the matrix writes this case's result.json (render: <case>/<row>, successor: <case>/<row>/<succ-label>)."""
    base = case_dir(root, case) / ROW
    if case["kind"] == "successor":
        base = base / f"{SUCC}-{c2m.SUCCESSOR_CASES[case['fault']][1]}"
    return base / "result.json"


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def run_is_complete(path: Path) -> bool:
    data = read_json(path)
    return bool(data) and data.get("state") != "running"


def load_state(path: Path) -> dict:
    data = read_json(path)
    return data if isinstance(data, dict) and isinstance(data.get("cases"), dict) else {"cases": {}}


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def pending_cases(c2m, root: Path, cases: list[dict], state: dict, *, retry_failed: bool = False) -> list[dict]:
    """A case is skipped only when state.json marks it done AND its result.json exists and is not still 'running'."""
    todo = []
    for case in cases:
        entry = state["cases"].get(case["name"], {})
        path = result_path(c2m, root, case)
        result = read_json(path) or {}
        if (entry.get("status") == "done" and run_is_complete(path) and
                (not retry_failed or result.get("pass") is True)):
            continue
        todo.append(case)
    return todo


def run_case(c2m, case: dict, root: Path, package_root: Path) -> dict:
    out = case_dir(root, case)
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HCU_C3_OBJECTS": "1"}
    try:
        with (out / "matrix.log").open("w") as log:
            proc = subprocess.run(matrix_argv(case, out, package_root), cwd=ROOT, env=env, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=CASE_TIMEOUT)
            rc: int | str = proc.returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
    except OSError as error:
        rc = f"exception: {error}"
    done = run_is_complete(result_path(c2m, root, case))
    return {"status": "done" if done else "error", "returncode": rc,
            "result": str(result_path(c2m, root, case).relative_to(ROOT))}


# ---------------------------------------------------------------- scoring

def kv(line: str) -> dict[str, str]:
    return dict(FIELD.findall(line))


def _int(value, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _verdict(fn, *args, **kwargs) -> dict:
    """Run one existing checker and reduce its checks dict to pass/fail with the first failing field."""
    try:
        out = fn(*args, **kwargs)
    except Exception as error:  # a checker mid-edit by another lane must not stop the matrix scoring
        return {"status": "checker error", "first_failing": None, "error": f"{type(error).__name__}: {error}"}
    checks = out.get("checks") or {}
    failing = [name for name, ok in checks.items() if not ok]
    if not checks:
        reasons = out.get("reasons") or ["no checks returned"]
        return {"status": "fail", "first_failing": reasons[0], "error": None}
    if failing:
        return {"status": "fail", "first_failing": failing[0], "error": None}
    return {"status": "pass", "first_failing": None, "error": None}


def c3_8_sound_checks(lines: list[str], frames_periodic: int | None = None) -> dict:
    """C3.8 sound-request adapter evidence from the guest log.

    'rejected' is read as the queue's rejected counter on every sound-requests line (no request refused).
    Every sound-requests line must say spu2-playback=not-qualified, because SPU2 playback is not qualified.
    The sound-coverage lines (one per sound-requests line) carry the field-preservation counters. The final
    coverage line must show nonzero playback events with owner, position, priority, gain and pitch covered,
    and its drain checksum must equal its record checksum on every line.
    """
    sound = [kv(l) for l in lines if "sound-requests phase=" in l]
    coverage = [kv(l) for l in lines if "sound-coverage phase=" in l]
    periodic = [l for l in lines if "c3-frame kind=periodic " in l]
    if frames_periodic is None:
        frames_periodic = len(periodic)
    last = sound[-1] if sound else {}
    cov = coverage[-1] if coverage else {}
    playback = _int(cov.get("playback"), 0) or 0
    checks = {
        "sound_lines_present": bool(sound),
        "sound_line_per_periodic_frame": frames_periodic > 0 and len(sound) >= frames_periodic,
        "sound_rejected_zero": bool(sound) and all(s.get("rejected") == "0" for s in sound),
        "sound_drained_positive": (_int(last.get("drained"), 0) or 0) > 0,
        "spu2_playback_not_qualified": bool(sound) and all(s.get("spu2-playback") == "not-qualified" for s in sound),
        "sound_coverage_line_per_sound_line": bool(coverage) and len(coverage) == len(sound),
        "playback_events_nonzero": playback > 0,
        "playback_owner_covered": (_int(cov.get("owner"), 0) or 0) > 0,
        "playback_position_covered": (_int(cov.get("position"), 0) or 0) > 0,
        "playback_priority_covered": (_int(cov.get("priority"), 0) or 0) > 0,
        "playback_gain_covered": (_int(cov.get("gain"), 0) or 0) > 0,
        "playback_pitch_covered": (_int(cov.get("pitch"), 0) or 0) > 0,
        "drain_checksum_equals_record": bool(coverage) and all(
            c.get("drain-checksum") is not None and c.get("drain-checksum") == c.get("record-checksum")
            for c in coverage),
    }
    return {"checks": checks, "sound_lines": len(sound), "periodic_frames": frames_periodic,
            "coverage": {k: cov.get(k) for k in ("playback", "owner", "position", "priority", "gain", "pitch",
                                                  "prio-min", "prio-max", "drain-checksum", "record-checksum")},
            "reasons": [f"c3.8 sound check failed: {k}" for k, v in checks.items() if not v]}


def snapshot_exit_checks(lines: list[str], views: int, captures: list[dict], emu_mode_verified: bool,
                         capture_ok) -> dict:
    """Snapshot, renderer and exit evidence for one run: snapshot seq advancing per periodic frame, the active view
    count, biped presence, emit failures (zero or counted as bitmap drops), non-black/non-sky captures, textured and
    lightmapped counters, and animated objects (c3-pose changes)."""
    snaps = [kv(l) for l in lines if "c3-snapshot " in l and " seq=" in l]
    periodic = [l for l in lines if "c3-frame kind=periodic " in l]
    frames = [kv(l) for l in lines if "c3-frame " in l]
    final = frames[-1] if frames else {}
    ready = [kv(l) for l in lines if "c3-render-ready " in l]
    poses = [kv(l) for l in lines if "c3-pose " in l]
    seqs = [_int(s.get("seq")) for s in snaps]
    last_snap = snaps[-1] if snaps else {}
    checks = {
        "snap_seq_present": bool(snaps),
        "snap_seq_advances_per_periodic_frame": bool(periodic) and len(snaps) >= len(periodic) and
            all(a is not None and b is not None and b > a for a, b in zip(seqs, seqs[1:])),
        "snap_active_views_match": last_snap.get("active-views") == str(views),
        "snap_biped_positive": (_int(last_snap.get("biped"), 0) or 0) > 0,
        # A bitmap drop cannot explain an unrelated object/chain emission failure.
        "emit_failures_zero": _int(final.get("emit-failures")) == 0,
        "captures_present": bool(captures),
        "captures_scene_not_sky_only": bool(captures) and all(capture_ok(c) for c in captures),
        "tex_hits_positive": (_int(final.get("tex-hits"), 0) or 0) > 0,
        "lightmaps_present": bool(ready) and (_int(ready[-1].get("lm"), 0) or 0) > 0,
        "animated_pose_changes_positive": any((_int(p.get("pose-changes"), 0) or 0) > 0 for p in poses),
        "emu_mode_verified": bool(emu_mode_verified),
    }
    return {"checks": checks, "reasons": [f"snapshot/exit check failed: {k}" for k, v in checks.items() if not v]}


def snapshot_payload_checks(lines: list[str]) -> dict:
    """Runtime payload observations supplement the source/host snapshot layout tests."""
    snapshots = [kv(l) for l in lines if "c3-snapshot " in l and " seq=" in l]
    checks = {
        "snapshot_payload_observed": bool(snapshots),
        "generation_and_resources_present": bool(snapshots) and all(
            (_int(s.get("map-gen")) or 0) > 0 and (_int(s.get("palette")) or 0) > 0 and
            (_int(s.get("resources")) or 0) > 0 for s in snapshots),
        "bounded_fx_payload": bool(snapshots) and all(
            0 <= (_int(s.get("effects"), -1)) + (_int(s.get("decals"), -1)) <= 64 and
            s.get("fx-dropped") == "0" for s in snapshots),
        "attachments_observed": any((_int(s.get("attachments")) or 0) > 0 for s in snapshots),
    }
    return {"checks": checks}


def content_checks(lines: list[str], views: int) -> dict:
    """Count real submitted first-person geometry and effect packets, never selection alone."""
    fp = [kv(l) for l in lines if "c3-fp " in l]
    effects = [kv(l) for l in lines if "c3-fx " in l]
    checks = {
        "weapon_geometry_in_each_view": all(any(
            f.get("view") == str(view) and (_int(f.get("fp-weapon-draws")) or 0) > 0 for f in fp)
            for view in range(views)),
        "hands_geometry_in_each_view": all(any(
            f.get("view") == str(view) and (_int(f.get("fp-hands-draws")) or 0) > 0 for f in fp)
            for view in range(views)),
        "representative_effect_geometry": any((_int(f.get("fx-drawn")) or 0) > 0 for f in effects),
    }
    return {"checks": checks}


def _hash_nonzero(value) -> bool:
    try:
        return int(str(value), 16) != 0
    except (TypeError, ValueError):
        return False


def c3_6_content_checks(lines: list[str], views: int) -> dict:
    """C3.6 content evidence for one run: textured world and lightmapped pages, animated objects with pose
    changes, first-person weapon and hands geometry in every active view, submitted fx geometry, and world and
    object parity lines with nonzero identity hashes. Each check reads a real counter the guest prints."""
    frames = [kv(l) for l in lines if "c3-frame " in l]
    final = frames[-1] if frames else {}
    ready = [kv(l) for l in lines if "c3-render-ready " in l]
    poses = [kv(l) for l in lines if "c3-pose " in l]
    fp = [kv(l) for l in lines if "c3-fp " in l]
    effects = [kv(l) for l in lines if "c3-fx " in l]
    parity = [kv(l) for l in lines if "c3-parity " in l]
    world = [p for p in parity if p.get("kind") == "world"]
    objects = [p for p in parity if p.get("kind") == "object"]
    checks = {
        "world_tex_hits_positive": (_int(final.get("tex-hits"), 0) or 0) > 0,
        "world_lightmaps_present": bool(ready) and (_int(ready[-1].get("lm"), 0) or 0) > 0,
        "objects_pose_changes_positive": any((_int(p.get("pose-changes"), 0) or 0) > 0 for p in poses),
        "fp_weapon_draws_each_view": all(any(
            f.get("view") == str(view) and (_int(f.get("fp-weapon-draws")) or 0) > 0 for f in fp)
            for view in range(views)),
        "fp_hands_draws_each_view": all(any(
            f.get("view") == str(view) and (_int(f.get("fp-hands-draws")) or 0) > 0 for f in fp)
            for view in range(views)),
        "fx_drawn_positive": any((_int(f.get("fx-drawn"), 0) or 0) > 0 for f in effects),
        # C3.6(c) textured fx is required: at least one effect quad drawn with a resident texture. Counted
        # reasons (fx-no-binding, fx-budget-deferred, fx-cache-full) are diagnostics and never pass the check.
        "fx_textured_positive": any((_int(f.get("fx-textured"), 0) or 0) > 0 for f in effects),
        "world_parity_present": bool(world) and (_int(world[-1].get("materials"), 0) or 0) > 0,
        "world_parity_hash_nonzero": bool(world) and _hash_nonzero(world[-1].get("hash")),
        "object_parity_present": bool(objects),
        "object_parity_hash_nonzero": bool(objects) and _hash_nonzero(objects[-1].get("hash")),
    }
    return {"checks": checks, "reasons": [f"c3.6 content check failed: {k}" for k, v in checks.items() if not v]}


def score_lines(c2m, lines: list[str] | None, *, views: int, frames: int, cap_pages: int, captures: list[dict],
                successor: dict | None, emu_mode_verified: bool) -> dict:
    """Every requirement verdict for one run. successor is {'old', 'new', 'mode'} for C3.11 runs, else None."""
    if lines is None:
        return {req: {"status": "not-run", "first_failing": "guest log missing", "error": None}
                for req in REQUIREMENTS}
    if successor:
        # Replacement logs contain two map lifetimes with separate frame counts,
        # bindings and releases. Per-map render proofs come from the render cases;
        # applying their single-map totals to this combined log is invalid.
        verdicts = {req: {"status": "n/a", "first_failing": "covered by render cases", "error": None}
                    for req in REQUIREMENTS}
        verdicts["C3.8"] = _verdict(c3_8_sound_checks, lines)
        verdicts["C3.11"] = _verdict(c2m.rendered_successor_checks, lines, successor["old"], successor["new"],
                                    successor["mode"], views, captures)
        return verdicts
    held = [c.get("file") for c in captures if "c3-render-held" in str(c.get("marker", "")) and c.get("file")]
    verdicts = {
        "C3.1": _verdict(snapshot_payload_checks, lines),
        "C3.3": (_verdict(c2m.c3_3_scene_checks, lines, views, views) if views > 1 else
                 {"status": "n/a", "first_failing": "opposing-player scene is exercised by multiplayer cases", "error": None}),
        "C3.5": _verdict(c2m.c3_5_layout_checks, views, held),
        "C3.6": _verdict(c3_6_content_checks, lines, views),
        "C3.7": _verdict(c2m.c3_7_texfence_checks, lines, views, frames, cap_pages),
        "C3.8": _verdict(c3_8_sound_checks, lines),
        "C3.9": _verdict(c2m.c3_9_bitmap_checks, lines, views),
        "C3.10": _verdict(c2m.c3_10_dma_checks, lines, views, frames),
        "SNAP": _verdict(snapshot_exit_checks, lines, views, captures, emu_mode_verified,
                         c2m.capture_has_scene_variation),
    }
    if successor:
        verdicts["C3.11"] = _verdict(c2m.rendered_successor_checks, lines, successor["old"], successor["new"],
                                     successor["mode"], views, captures)
    else:
        verdicts["C3.11"] = {"status": "n/a", "first_failing": None, "error": None}
    return verdicts


def score_case(c2m, root: Path, case: dict) -> dict:
    res_file = result_path(c2m, root, case)
    result = read_json(res_file) or {}
    entry = {"case": case["name"], "kind": case["kind"], "views": case["views"], "mode": case["mode"],
             "cap_pages": case["cap_pages"], "fault": case["fault"], "result_json": str(res_file),
             "matrix_pass": result.get("pass") is True, "reasons": result.get("reasons", [])[:3]}
    log = res_file.parent / GUEST_LOG
    # Revalidate saved evidence when scoring. A failed relink may leave an older
    # log next to result.json; its presence never establishes a current launch.
    run, provenance_error = c2m.validate_guest_provenance(
        res_file.parent, (_int(result.get("started_unix"), 0) or 0) * 1_000_000_000,
        case["mode"], expected_captures=2)
    if run is not None and run.get("launch_id") != result.get("guest_launch_id"):
        run, provenance_error = None, "result does not identify this guest launch"
    entry["evidence_valid"] = run is not None
    entry["evidence_error"] = provenance_error or None
    lines = log.read_text(errors="replace").splitlines() if run is not None and log.is_file() else None
    captures = run.get("captures", []) if run is not None else []
    successor = None
    if case["kind"] == "successor":
        successor = {"old": result.get("map"), "new": result.get("successor_map"), "mode": c2m.SUCCESSOR_CASES[case["fault"]][0]}
    entry["guest_log"] = str(log) if lines is not None else None
    entry["captures"] = [c.get("file") for c in captures if c.get("file")]
    entry["requirements"] = score_lines(
        c2m, lines, views=case["views"], frames=FRAMES, cap_pages=case["cap_pages"], captures=captures,
        successor=successor, emu_mode_verified=bool(run and run.get("pcsx2_config", {}).get("emu_mode_verified")))
    return entry


def requirement_cell(verdict: dict) -> str:
    if verdict["status"] == "pass":
        return "PASS"
    if verdict["status"] == "checker error":
        return f"checker error ({verdict.get('error')})"
    if verdict["status"] in ("n/a", "not-run"):
        return verdict["status"]
    return f"FAIL: {verdict.get('first_failing')}"


def write_report(root: Path, stamp: str, scored: list[dict], state: dict) -> dict:
    summary = {}
    for req in REQUIREMENTS:
        statuses = [e["requirements"][req]["status"] for e in scored]
        summary[req] = {s: statuses.count(s) for s in sorted(set(statuses))}
    passed = all(e["matrix_pass"] and e.get("evidence_valid", False) and all(
        v["status"] in ("pass", "n/a") for k, v in e["requirements"].items()
        if k != "C3.11" or e["kind"] == "successor") for e in scored)
    data = {"stamp": stamp, "root": str(root), "matrix_qualified": passed,
            "requirements": list(REQUIREMENTS), "summary": summary,
            "runs": scored, "state": state}
    (root / "report.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    names = [e["case"] for e in scored]
    lines = [f"# C3 integration report {stamp}", "",
             "Cell = verdict and first failing field. Matrix pass is the matrix's own result.json verdict.", "",
             "| requirement | " + " | ".join(names) + " |",
             "|---|" + "---|" * len(names),
             "| matrix pass | " + " | ".join("yes" if e["matrix_pass"] else "no" for e in scored) + " |"]
    for req in REQUIREMENTS:
        cells = [requirement_cell(e["requirements"][req]).replace("|", "/") for e in scored]
        lines.append(f"| {req} | " + " | ".join(cells) + " |")
    lines += ["", "## Evidence", ""]
    for e in scored:
        lines.append(f"- {e['case']}: result {e['result_json']}")
        lines.append(f"  - guest log: {e['guest_log'] or 'missing'}")
        for cap in e["captures"]:
            lines.append(f"  - capture: {cap}")
    (root / "report.md").write_text("\n".join(lines) + "\n")
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--jobs", type=int, default=3, help="matrix subprocesses in flight (default %(default)s)")
    parser.add_argument("--stamp", help="output stamp; pass an existing one to resume (default: now)")
    parser.add_argument("--dry-run", action="store_true", help="print the 12 matrix commands and exit")
    parser.add_argument("--score-only", action="store_true", help="do not run anything; score existing runs")
    parser.add_argument("--retry-failed", action="store_true", help="rerun completed cases whose matrix result failed")
    parser.add_argument("--cases", nargs="+", help="run only these case names; the report still shows the full matrix")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    c2m = load_matrix()
    cases = build_cases()
    selected = cases
    if args.cases:
        unknown = sorted(set(args.cases) - {c["name"] for c in cases})
        if unknown:
            parser.error("unknown cases: " + ", ".join(unknown))
        selected = [c for c in cases if c["name"] in args.cases]
    stamp = args.stamp or time.strftime("%Y%m%dT%H%M%S")
    root = INTEGRATION_ROOT / stamp
    if args.dry_run:
        for case in selected:
            print(" ".join(matrix_argv(case, case_dir(root, case), ROOT / "build/c3/render-tree/pkg")))
        return 0
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / STATE_NAME
    state = load_state(state_path)
    if not args.score_only:
        todo = pending_cases(c2m, root, selected, state, retry_failed=args.retry_failed)
        print(f"stamp {stamp}: {len(selected) - len(todo)} done, {len(todo)} to run, jobs {args.jobs}", flush=True)
        if todo:
            package_root = c2m.prepare_render_tree()  # once here, so concurrent matrix runs do not race on it
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                futures = {pool.submit(run_case, c2m, case, root, package_root): case for case in todo}
                for future in as_completed(futures):
                    case = futures[future]
                    try:
                        entry = future.result()
                    except Exception as error:
                        entry = {"status": "error", "returncode": f"exception: {error}", "result": None}
                    state["cases"][case["name"]] = entry
                    save_state(state_path, state)
                    print(f"{case['name']}: {entry['status']} rc={entry['returncode']}", flush=True)
    scored = [score_case(c2m, root, case) for case in cases]
    data = write_report(root, stamp, scored, state)
    print(f"report: {root / 'report.md'}", flush=True)
    return 0 if data["matrix_qualified"] else 1


if __name__ == "__main__":
    sys.exit(main())
