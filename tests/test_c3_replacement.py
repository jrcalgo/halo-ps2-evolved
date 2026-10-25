"""Rendered successor checks: every ordered marker must hold, and absent proof never qualifies."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_profile_boot_matrix as matrix

OLD, NEW = "bloodgulch", "beavercreek"
P = matrix.PREFIX
VISIBLE = {"nonblack_fraction": 0.7, "scene_color_buckets": 100, "scene_nonflat_fraction": 0.3}


def captures(first="c3-render-held ", second="production-ce-successor-usable result=1 "):
    return [dict(VISIBLE, marker=first), dict(VISIBLE, marker=second)]


def ready(map_name):
    return P + f"c3-render-ready map={map_name} views=4"


def frame(n=30):
    return P + f"c3-frame kind=periodic frame={n} views=4"


def step(name, **fields):
    body = " ".join(f"{k}={v}" for k, v in fields.items())
    return P + f"production-ce-successor-step step={name} {body}"


def begin():
    return P + f"production-ce-successor-begin mode=1 old={OLD} new={NEW} old-tag-bytes=1000 old-bsp-bytes=2000 ticks=30"


def released():
    return P + "m2-cycle-boundary phase=map-released cycle=1"


def quiesce_ok():
    return [P + "c3-render-quiesce result=1 readers=0 kick-seq=5 fence=1 frame-active=0 bitmap-attachments=0"]


def boundary(phase, drained=False):
    return (P + f"c3-replacement-boundary phase={phase} frame=30 map-generation=1 kick-seq=5 "
            f"fence={1 if drained else 0} inflight={0 if drained else 1} "
            f"service-readers={0 if drained else 1} world-bound=1 media-loaded=1 "
            f"object-pin-live={0 if drained else 1} bitmap-leases={0 if drained else 4}")


def replace_lines():
    """Mode 1 (foreign replacement) in the order the guest must print it."""
    return ([begin(), ready(OLD), frame(30), boundary("before-preflight"),
             P + f"map-replacement phase=candidate-validated old={OLD} new={NEW} readers=1",
             P + f"map-replacement phase=quiesce-begin old={OLD} new={NEW} readers=1 callback=1"]
            + [boundary("after-drain", True)] + quiesce_ok() +
            [P + f"map-replacement phase=quiesce-end old={OLD} new={NEW} readers=0 drained=1",
             step("dispose", result=1, old=OLD, **{"old-mounted": 1}, new=NEW, **{"new-mounted": 0},
                  **{"tag-bytes": 1000, "bsp-bytes": 2000}),
             released(),
             step("unload", result=1, old=OLD, **{"old-mounted": 0}, new=NEW, **{"new-mounted": 0},
                  **{"tag-bytes": 0, "bsp-bytes": 0}),
             step("load", result=1, old=OLD, **{"old-mounted": 0}, new=NEW, **{"new-mounted": 1}),
             ready(NEW), frame(30), frame(300),
             P + f"production-ce-successor-usable result=1 old={OLD} ticks=30 local-players=4"])


def preflight_lines():
    return [begin(), ready(OLD), frame(30), boundary("before-preflight"), boundary("after-preflight-rejected"),
            step("after-failed-preflight", result=1, old=OLD, **{"old-mounted": 1}, new=NEW, **{"new-mounted": 0},
                 **{"tag-bytes": 1000, "bsp-bytes": 2000}),
            frame(60), P + "c3-render-held views=4 frames=300",
            P + f"production-ce-successor-usable result=1 old={OLD} ticks=30 local-players=4"]


def load_lines():
    lines = [begin(), ready(OLD), frame(30), boundary("before-preflight"),
             P + f"map-replacement phase=candidate-validated old={OLD} new={NEW} readers=1",
             P + f"map-replacement phase=quiesce-begin old={OLD} new={NEW} readers=1 callback=1"]
    lines += [boundary("after-drain", True)] + quiesce_ok()
    lines += [P + f"map-replacement phase=quiesce-end old={OLD} new={NEW} readers=0 drained=1",
              step("dispose", result=1, old=OLD, **{"old-mounted": 1}, new=NEW, **{"new-mounted": 0},
                   **{"tag-bytes": 1000, "bsp-bytes": 2000}),
              released(),
              step("unload", result=1, old=OLD, **{"old-mounted": 0}, new=NEW, **{"new-mounted": 0},
                   **{"tag-bytes": 0, "bsp-bytes": 0}),
              step("load", result=0, old=OLD, **{"old-mounted": 0}, new=NEW, **{"new-mounted": 0}),
              step("after-failed-load", result=1, old=OLD, **{"old-mounted": 0}, new=NEW, **{"new-mounted": 0},
                   **{"tag-bytes": 0, "bsp-bytes": 0}),
              P + f"production-ce-successor-retry old={OLD} new={NEW}",
              step("load", result=1, old=OLD, **{"old-mounted": 0}, new=NEW, **{"new-mounted": 1}),
              ready(NEW), frame(30), frame(300),
              P + f"production-ce-successor-usable result=1 old={OLD} ticks=30 local-players=4 new={NEW}"]
    return lines


def check(lines, mode=1, caps=None):
    return matrix.rendered_successor_checks(lines, OLD, NEW, mode, 4,
                                            caps if caps is not None else captures())


def failing(result):
    return {name for name, ok in result["checks"].items() if not ok}


def test_replacement_passes_every_ordered_check():
    good = check(replace_lines())
    assert failing(good) == set(), good
    assert good["c3_11_qualified"] is False


def test_replacement_rejects_each_missing_or_misordered_link():
    base = replace_lines()
    # candidate validation after quiesce begins
    lines = list(base)
    v = next(i for i, l in enumerate(lines) if "candidate-validated" in l)
    b = next(i for i, l in enumerate(lines) if "quiesce-begin" in l)
    lines[v], lines[b] = lines[b], lines[v]
    assert "candidate_before_quiesce" in failing(check(lines))
    # no renderer reader held
    lines = [l.replace("readers=1 callback=1", "readers=0 callback=1") for l in base]
    assert "readers_held_while_drawing" in failing(check(lines))
    # fence not observed at drain
    lines = [l.replace("fence=1", "fence=-1") for l in base]
    assert "drain_readers_zero_fence_observed" in failing(check(lines))
    # CE disposes with old tags already released
    lines = [l.replace("step=dispose result=1 old=bloodgulch old-mounted=1",
                       "step=dispose result=1 old=bloodgulch old-mounted=0") for l in base]
    assert "ce_dispose_with_old_tags_live" in failing(check(lines))
    # successor load before the old owner is released
    lines = list(base)
    u = next(i for i, l in enumerate(lines) if "step=unload" in l)
    l_ = next(i for i, l in enumerate(lines) if "step=load" in l)
    lines[u], lines[l_] = lines[l_], lines[u]
    assert "release_before_successor_load" in failing(check(lines))
    # successor never draws a frame
    after = base.index(ready(NEW))
    lines = base[:after] + [l for l in base[after:] if not l.startswith(P + "c3-frame")]
    assert "successor_frames_render" in failing(check(lines))
    # captures not visible
    assert "replacement_captures_visible" in failing(check(base, caps=[{"nonblack_fraction": 0}] * 2))
    # captures in the wrong order
    assert "capture_order_map_a_then_map_b" in failing(check(base, caps=captures("production-ce-successor-usable result=1 ", "c3-render-held ")))


def test_preflight_keeps_old_renderer_and_skips_quiesce():
    good = check(preflight_lines(), mode=2, caps=captures())
    assert failing(good) == set(), good
    # quiesce or candidate markers after a failed preflight is a violation
    bad = preflight_lines() + [P + f"map-replacement phase=quiesce-begin old={OLD} new={NEW} readers=1"]
    assert "failed_preflight_preserves_renderer" in failing(check(bad, mode=2))
    assert "failed_preflight_no_quiesce_or_dispose" in failing(check(bad, mode=2))


def test_late_failure_reaches_empty_then_retries_and_renders():
    good = check(load_lines(), mode=3)
    assert failing(good) == set(), good
    # no retry load after the failure
    lines = [l for l in load_lines() if "step=load result=1" not in l]
    assert "late_failure_empty_then_retry" in failing(check(lines, mode=3))


def test_empty_renderer_never_qualifies():
    assert "rendered_maps" in failing(check([], mode=1, caps=[]))
    assert check([], mode=1, caps=[])["c3_11_qualified"] is False


def test_c3_successor_cli_forwards_render_inputs(monkeypatch, tmp_path):
    row = "bloodgulch_mounted_gunner_4p4bot"
    successor = "beavercreek_mounted_gunner_4p4bot"
    calls = []
    monkeypatch.setenv("HCU_C3", "0")
    monkeypatch.setattr(matrix, "run_successor", lambda *a, **k:
                        calls.append((a, k)) or {"pass": True, "case": "replace", "reasons": []})
    assert matrix.main(["--rows", row, "--successor", successor, "--c3",
                        "--render-views", "4", "--c3-workload", "4p4bot",
                        "--package-root", str(tmp_path), "--emu-mode", "recompiler"]) == 0
    args, kwargs = calls[0]
    assert args[:2] == (row, successor)
    assert kwargs == {"package_root_override": tmp_path, "render_views": 4,
                      "render_frames": 300, "workload_players": 4}


def test_guest_fault_lines_report_the_real_cause(tmp_path):
    log = tmp_path / "halo_ps2_local.txt"
    log.write_text("HALO_PS2_LOCAL machine entry\n[err] ELF/boot backing exceeds EE fixed budget\nok line\n")
    assert matrix.guest_fault_lines(log) == ["[err] ELF/boot backing exceeds EE fixed budget"]
    assert matrix.guest_fault_lines(tmp_path / "missing.txt") == []


def test_preflight_failure_must_leave_owner_bytes_and_old_map_usable():
    base = preflight_lines()
    # owner bytes changed by the rejected candidate
    lines = [l.replace("tag-bytes=1000", "tag-bytes=0") if "step=after-failed-preflight" in l else l for l in base]
    assert "failed_preflight_owner_unchanged" in failing(check(lines, mode=2))
    # the old map is never reported usable after the rejection
    lines = [l for l in base if "production-ce-successor-usable" not in l]
    assert "failed_preflight_old_map_usable" in failing(check(lines, mode=2))
    # a rejected candidate that still reports the new map as mounted
    lines = [l.replace("new-mounted=0", "new-mounted=1") if "step=after-failed-preflight" in l else l for l in base]
    assert "failed_preflight_owner_unchanged" in failing(check(lines, mode=2))


def test_owner_release_must_follow_dispose_and_zero_the_bytes():
    base = replace_lines()
    # the parent never reports map-released between dispose and unload
    lines = [l for l in base if "phase=map-released" not in l]
    assert "parent_release_between_dispose_and_unload" in failing(check(lines))
    # the unload step still holds tag bytes: the unpublish did not happen
    lines = [l.replace("step=unload result=1 old=bloodgulch old-mounted=0 new=beavercreek new-mounted=0 "
                       "tag-bytes=0 bsp-bytes=0",
                       "step=unload result=1 old=bloodgulch old-mounted=0 new=beavercreek new-mounted=0 "
                       "tag-bytes=1000 bsp-bytes=2000") for l in base]
    assert "old_owner_unpublished_zero_bytes" in failing(check(lines))
    # the owner release is reported before CE dispose instead of after it
    lines = list(base)
    r = next(i for i, l in enumerate(lines) if "phase=map-released" in l)
    d = next(i for i, l in enumerate(lines) if "step=dispose" in l)
    lines[r], lines[d] = lines[d], lines[r]
    assert "parent_release_between_dispose_and_unload" in failing(check(lines))


def test_late_failure_must_reach_empty_state_then_retry_without_rendering():
    base = load_lines()
    assert failing(check(base, mode=3)) == set()
    # the failed load leaves bytes behind instead of an empty state
    lines = [l.replace("step=after-failed-load result=1 old=bloodgulch old-mounted=0 new=beavercreek "
                       "new-mounted=0 tag-bytes=0 bsp-bytes=0",
                       "step=after-failed-load result=1 old=bloodgulch old-mounted=0 new=beavercreek "
                       "new-mounted=0 tag-bytes=1000 bsp-bytes=2000") for l in base]
    assert "late_failure_empty_state" in failing(check(lines, mode=3))
    # no retry marker: the successful load is not a retry
    lines = [l for l in base if "production-ce-successor-retry" not in l]
    assert "late_failure_retry_marker_then_load" in failing(check(lines, mode=3))
    # a frame published while the state is empty
    idx = next(i for i, l in enumerate(base) if "production-ce-successor-retry" in l)
    lines = base[:idx] + [frame(31)] + base[idx:]
    assert "late_failure_no_render_while_empty" in failing(check(lines, mode=3))
    # the new map is drawn from a ready line emitted before the retry load
    lines = base[:idx] + [ready(NEW)] + base[idx:]
    assert "late_failure_no_render_while_empty" in failing(check(lines, mode=3))


def test_late_failure_retry_does_not_dispose_or_unload_an_empty_state():
    # The guarded retry (CE hcu_c2_successor_attempt) skips dispose/unload once the old map is no longer mounted:
    # the log holds one release pair from the first attempt, and every ordered mode-3 check still holds.
    lines = load_lines()
    assert sum("step=dispose" in l for l in lines) == 1
    assert sum("step=unload" in l for l in lines) == 1
    assert not failing(check(lines, mode=3))
