"""C3 integration harness host tests: the case plan, the resume state, the C3.8 and snapshot/exit scorers, and
checker-error handling, all on synthetic guest lines. No PCSX2 run is involved."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ci = _load("c3_integration", "tools/c3_integration.py")
c2m = _load("c2m_for_integration_test", "tools/c2_profile_boot_matrix.py")


def sound_line(phase="periodic", rejected=0, drained=5, playback="not-qualified"):
    return (f"HALO_PS2_LOCAL sound-requests phase={phase} submitted=9 accepted=9 rejected={rejected} "
            f"drained={drained} pending=0 high=3 dropped-full=0 resets=0 coalesced=0 evicted=0 capacity=64 "
            f"spu2-playback={playback}")


def snapshot_lines(seqs, views=2, biped=4):
    out = []
    for i, seq in enumerate(seqs):
        out.append(f"HALO_PS2_LOCAL c3-snapshot frame={30 * (i + 1)} map-gen=1 seq={seq} views={views} "
                   f"active-views={views} objects=12 biped={biped} weapon=4 vehicle=1 other=0")
    return out


def exit_lines(periodic=2, tex_hits=40, lm=3, pose=5, emit=0, dropped=0):
    lines = snapshot_lines(list(range(1, periodic + 1)))
    lines += [f"HALO_PS2_LOCAL c3-frame kind=periodic frame={30 * (i + 1)} views=2" for i in range(periodic)]
    lines.append(f"HALO_PS2_LOCAL c3-frame kind=final frame=300 views=2 emit-failures={emit} tex-hits={tex_hits}")
    lines.append(f"HALO_PS2_LOCAL c3-render-ready map=bloodgulch views=2 frames=300 lm={lm}")
    lines.append(f"HALO_PS2_LOCAL c3-pose frame=30 pose-changes={pose} pose-static=1")
    lines.append(f"HALO_PS2_LOCAL c3-bitmap tick=1 begin-calls=1 begin=1 set-view=2 requests=3 queue-end=1 end=1 "
                 f"bitmap-frames-dropped={dropped}")
    return lines


GOOD_CAPTURE = {"error": None, "nonblack_fraction": 0.5, "scene_color_buckets": 200,
                "scene_nonflat_fraction": 0.4, "file": "/x/held.png", "marker": "c3-render-held "}
BLACK_CAPTURE = {"error": None, "nonblack_fraction": 0.0, "scene_color_buckets": 1,
                 "scene_nonflat_fraction": 0.0, "file": "/x/black.png", "marker": "c3-render-held "}


def test_case_plan_has_twelve_unique_cases_with_expected_shape():
    cases = ci.build_cases()
    assert len(cases) == 12
    assert len({c["name"] for c in cases}) == 12
    renders = [c for c in cases if c["kind"] == "render"]
    successors = [c for c in cases if c["kind"] == "successor"]
    assert len(renders) == 6 and len(successors) == 6
    assert sorted((c["views"], c["mode"]) for c in renders if not c["cap_pages"]) == [
        (1, "recompiler"), (2, "recompiler"), (3, "recompiler"), (4, "interpreter"), (4, "recompiler")]
    assert [c["cap_pages"] for c in renders if c["cap_pages"]] == [48]
    assert sorted({c["fault"] for c in successors}) == ["load", "none", "preflight"]
    assert {c["mode"] for c in successors} == {"recompiler", "interpreter"}


def test_matrix_argv_flags_and_no_flock(tmp_path):
    cases = {c["name"]: c for c in ci.build_cases()}
    argv = ci.matrix_argv(cases["render-v4-recompiler-cap48"], tmp_path, Path("/pkg"))
    assert argv[argv.index("--render-views") + 1] == "4"
    assert argv[argv.index("--texfence-cap-pages") + 1] == "48"
    assert argv[argv.index("--emu-mode") + 1] == "recompiler"
    assert argv[argv.index("--c3-local-players") + 1] == "4"
    assert "flock" not in " ".join(argv)
    succ = ci.matrix_argv(cases["c3-11-load-interpreter"], tmp_path, Path("/pkg"))
    assert succ[succ.index("--successor") + 1] == ci.SUCC
    assert succ[succ.index("--successor-fault") + 1] == "load"
    assert succ[succ.index("--render-views") + 1] == "2"
    assert "--texfence-cap-pages" not in succ
    assert succ[succ.index("--c3-local-players") + 1] == "2"


def test_c3_workload_selects_stock_slayer_before_ce_local_map_start():
    ce = ROOT / "submodules/halo-ce-universal/source"
    main = (ce / "main/main.c").read_text()
    game = (ce / "game/game.c").read_text()
    engine = (ce / "game/game_engine.c").read_text()
    setup = main[main.index("void main_loop("):]
    assert "#if defined(HALO_PS2_C3_FRAME_SNAPSHOT) && defined(HCU_C3_WORKLOAD_LOCAL_PLAYERS)" in setup
    initialize = setup.index("game_initialize();")
    select = setup.index("build_game_variant_slayer(&c3_variant);")
    apply = setup.index("game_set_game_variant(&c3_variant);")
    start = setup.index("main_setup_connection();")
    status = setup.index("c3-workload-mode engine=slayer selected=1 game-engine-running=%d")
    assert initialize < select < apply < start < status
    assert "game_engine_initialize(&game_variant_global);" in game
    assert "game_initial_pulse();" in main[main.rindex("static void main_new_map("):]
    assert "result.game_engine_index = game_engine_slayer;" in engine
    # Successor map attempts reuse game_variant_global; they don't reset it.
    successor = main[main.index("static boolean hcu_c2_successor_attempt("):
                     main.index("void main_loop(")]
    assert "game_set_game_variant(NULL)" not in successor


def test_resume_skips_only_completed_runs(tmp_path):
    cases = ci.build_cases()
    state = {"cases": {}}
    for case in cases:
        path = ci.result_path(c2m, tmp_path, case)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"state": "done", "pass": True}))
    assert ci.pending_cases(c2m, tmp_path, cases, state) == cases  # no state entry: nothing is skipped yet
    state["cases"][cases[0]["name"]] = {"status": "done"}
    state["cases"][cases[1]["name"]] = {"status": "error"}
    state["cases"][cases[2]["name"]] = {"status": "done"}
    ci.result_path(c2m, tmp_path, cases[2]).write_text(json.dumps({"state": "running"}))
    todo = [c["name"] for c in ci.pending_cases(c2m, tmp_path, cases, state)]
    assert cases[0]["name"] not in todo          # done and complete: skipped
    assert cases[1]["name"] in todo              # recorded as error: rerun
    assert cases[2]["name"] in todo              # done in state but result still 'running': rerun


def test_retry_failed_preserves_successful_independent_cases(tmp_path):
    cases = ci.build_cases()[:2]
    state = {"cases": {c["name"]: {"status": "done"} for c in cases}}
    for case, passed in zip(cases, (True, False)):
        path = ci.result_path(c2m, tmp_path, case)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"pass": passed}))
    assert ci.pending_cases(c2m, tmp_path, cases, state) == []
    assert ci.pending_cases(c2m, tmp_path, cases, state, retry_failed=True) == cases[1:]


def test_state_round_trip_and_bad_state_is_empty(tmp_path):
    path = tmp_path / ci.STATE_NAME
    assert ci.load_state(path) == {"cases": {}}
    path.write_text("not json")
    assert ci.load_state(path) == {"cases": {}}
    ci.save_state(path, {"cases": {"a": {"status": "done"}}})
    assert ci.load_state(path)["cases"]["a"]["status"] == "done"


def test_sound_check_passes_on_synthetic_lines():
    lines = [sound_line(), sound_line(drained=7), "HALO_PS2_LOCAL c3-frame kind=periodic frame=30",
             "HALO_PS2_LOCAL c3-frame kind=periodic frame=60"]
    out = ci.c3_8_sound_checks(lines)
    assert all(out["checks"].values()), out["checks"]


def test_sound_check_fails_on_missing_periodic_line_and_qualified_playback():
    lines = [sound_line(), sound_line(playback="qualified"),
             "HALO_PS2_LOCAL c3-frame kind=periodic frame=30", "HALO_PS2_LOCAL c3-frame kind=periodic frame=60"]
    checks = ci.c3_8_sound_checks(lines)["checks"]
    assert checks["spu2_playback_not_qualified"] is False
    assert checks["sound_line_per_periodic_frame"] is True
    short = ci.c3_8_sound_checks(lines[:1] + lines[2:])["checks"]
    assert short["sound_line_per_periodic_frame"] is False


def test_sound_check_fails_when_nothing_drained_or_rejected():
    lines = [sound_line(rejected=2, drained=0)]
    checks = ci.c3_8_sound_checks(lines, frames_periodic=1)["checks"]
    assert checks["sound_rejected_zero"] is False
    assert checks["sound_drained_positive"] is False
    # Replacement may reset a queue; a clean final map cannot erase earlier loss.
    assert not ci.c3_8_sound_checks([sound_line(rejected=2), sound_line()])["checks"]["sound_rejected_zero"]


def test_snapshot_exit_passes_on_good_run():
    out = ci.snapshot_exit_checks(exit_lines(), 2, [GOOD_CAPTURE], True, c2m.capture_has_scene_variation)
    assert all(out["checks"].values()), out["checks"]


def test_snapshot_seq_must_advance_each_periodic_frame():
    lines = exit_lines(periodic=2)
    stuck = [l.replace("seq=2", "seq=1") for l in lines]
    checks = ci.snapshot_exit_checks(stuck, 2, [GOOD_CAPTURE], True, c2m.capture_has_scene_variation)["checks"]
    assert checks["snap_seq_advances_per_periodic_frame"] is False


def test_snapshot_black_capture_and_no_textures_fail():
    lines = exit_lines(tex_hits=0, lm=0, pose=0)
    checks = ci.snapshot_exit_checks(lines, 2, [BLACK_CAPTURE], True, c2m.capture_has_scene_variation)["checks"]
    assert checks["captures_scene_not_sky_only"] is False
    assert checks["tex_hits_positive"] is False
    assert checks["lightmaps_present"] is False
    assert checks["animated_pose_changes_positive"] is False


def test_bitmap_drop_does_not_excuse_geometry_emit_failures():
    no_drop = ci.snapshot_exit_checks(exit_lines(emit=3, dropped=0), 2, [GOOD_CAPTURE], True,
                                      c2m.capture_has_scene_variation)["checks"]
    counted = ci.snapshot_exit_checks(exit_lines(emit=3, dropped=2), 2, [GOOD_CAPTURE], True,
                                      c2m.capture_has_scene_variation)["checks"]
    assert no_drop["emit_failures_zero"] is False
    assert counted["emit_failures_zero"] is False


def test_scoring_rejects_a_previous_guest_after_failed_relink(tmp_path):
    case = ci.build_cases()[0]
    result = ci.result_path(c2m, tmp_path, case)
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps({"pass": False, "started_unix": 10,
                                  "reasons": ["link failed"]}))
    log = result.parent / ci.GUEST_LOG
    log.parent.mkdir(parents=True)
    log.write_text("\n".join(exit_lines()))
    scored = ci.score_case(c2m, tmp_path, case)
    assert not scored["evidence_valid"]
    assert scored["evidence_error"]
    assert all(v["status"] == "not-run" for v in scored["requirements"].values())


def test_missing_log_is_not_run_not_a_crash():
    verdicts = ci.score_lines(c2m, None, views=1, frames=300, cap_pages=0, captures=[], successor=None,
                              emu_mode_verified=False)
    assert all(v["status"] == "not-run" for v in verdicts.values())
    assert ci.requirement_cell(verdicts["C3.3"]) == "not-run"


def test_checker_error_is_reported_not_raised(monkeypatch):
    def broken(*_args, **_kwargs):
        raise KeyError("layout moved")
    fake = SimpleNamespace(**{name: getattr(c2m, name) for name in dir(c2m) if not name.startswith("__")})
    fake.c3_5_layout_checks = broken
    verdicts = ci.score_lines(fake, ["HALO_PS2_LOCAL c3-frame kind=final frame=1"], views=1, frames=300,
                              cap_pages=0, captures=[], successor=None, emu_mode_verified=False)
    assert verdicts["C3.5"]["status"] == "checker error"
    assert "KeyError" in verdicts["C3.5"]["error"]
    assert ci.requirement_cell(verdicts["C3.5"]).startswith("checker error")


def test_verdict_names_first_failing_field():
    v = ci._verdict(lambda: {"checks": {"a": True, "b": False, "c": False}})
    assert v == {"status": "fail", "first_failing": "b", "error": None}
    ok = ci._verdict(lambda: {"checks": {"a": True}})
    assert ok["status"] == "pass"


def test_successor_verdict_uses_rendered_successor_checks_with_mode(tmp_path):
    calls = {}

    def fake_rendered(lines, old, new, mode, views, captures):
        calls.update(old=old, new=new, mode=mode, views=views)
        return {"checks": {"rendered_maps": True}}

    fake = SimpleNamespace(**{name: getattr(c2m, name) for name in dir(c2m) if not name.startswith("__")})
    fake.rendered_successor_checks = fake_rendered
    verdicts = ci.score_lines(fake, ["x"], views=2, frames=300, cap_pages=0, captures=[],
                              successor={"old": "a", "new": "b", "mode": 3}, emu_mode_verified=True)
    assert calls == {"old": "a", "new": "b", "mode": 3, "views": 2}
    assert verdicts["C3.11"]["status"] == "pass"
