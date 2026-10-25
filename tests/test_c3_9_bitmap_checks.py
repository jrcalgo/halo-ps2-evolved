"""C3.9 bitmap checks: registration, one queue end per CE frame, and release with no leaked leases."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_profile_boot_matrix as matrix  # noqa: E402

P = matrix.PREFIX


def tick(n, begin=1, views=4, requests=2, queue_end=None, end=None, in_frame=0, status=0, leases=0, drain=0):
    qe = begin if queue_end is None else queue_end
    en = begin if end is None else end
    return (P + f"c3-bitmap tick={n} windows={views} begin-calls={begin} begin={begin} set-view={begin * views} "
            f"requests={requests * begin} queue-end={qe} end={en} end-failed-total=0 in-frame={in_frame} "
            f"drain-pending={drain} gpu-pending=0 leases={leases} last-status={status} bitmap-frames-dropped=0")


def release(requests=0, begins=0, queue_ends=0, leases=0, readers=0, in_frame=0):
    return (P + f"c3-bitmap map-released leases={leases} readers={readers} requests-total={requests} "
            f"begins-total={begins} queue-end-total={queue_ends} in-frame={in_frame}")


GOOD_BOUND = P + "c3-bitmap-bound generation=1 bindings=587 producer=0x1"


def run(lines, views=4):
    return matrix.c3_9_bitmap_checks(lines, views)


def test_clean_run_qualifies():
    lines = [GOOD_BOUND, tick(1, begin=0, requests=0), tick(2, begin=1, leases=3), tick(3, begin=1, leases=0),
             release(requests=4, begins=2, queue_ends=2)]
    out = run(lines)
    assert out["c3_9_qualified"], out["reasons"]
    assert out["totals"]["requests"] == 4 and out["totals"]["begin"] == 2


def test_unregistered_or_no_frames_never_qualifies():
    lines = [release()]
    out = run(lines)
    assert not out["c3_9_qualified"]
    assert not out["checks"]["bitmap_registered"]
    assert not out["checks"]["bitmap_frames_seen"]


def test_queue_end_across_frames_fails():
    # A frame whose queue end is missing leaves the frame open at the tick boundary.
    lines = [GOOD_BOUND, tick(1, begin=1, queue_end=0, end=1, in_frame=1),
             release(requests=2, begins=1, queue_ends=0)]
    out = run(lines)
    assert not out["checks"]["bitmap_queue_end_once_per_frame"]
    assert not out["checks"]["bitmap_no_frame_open_at_tick"]
    assert not out["c3_9_qualified"]


def test_set_view_must_match_view_count():
    lines = [GOOD_BOUND, tick(1, begin=1, views=2), release(requests=2, begins=1, queue_ends=1)]
    out = run(lines, views=4)
    assert not out["checks"]["bitmap_set_view_per_view"]


def test_bootstrap_window_is_accounted_before_all_player_windows_are_ready():
    lines = [GOOD_BOUND, tick(1, views=1), tick(2, views=4),
             release(requests=4, begins=2, queue_ends=2)]
    assert run(lines)["c3_9_qualified"]
    lines[1] = lines[1].replace("set-view=1", "set-view=2")
    assert not run(lines)["checks"]["bitmap_set_view_per_view"]


def test_leaked_lease_on_release_fails():
    lines = [GOOD_BOUND, tick(1, begin=1), release(requests=2, begins=1, queue_ends=1, leases=2)]
    out = run(lines)
    assert not out["checks"]["bitmap_released_no_leases"]
    assert not out["c3_9_qualified"]


def test_failure_line_or_total_mismatch_fails():
    lines = [GOOD_BOUND, P + "HALO_PS2_FAIL c3-bitmap frame-guard frame=3", tick(1, begin=1),
             release(requests=9, begins=1, queue_ends=1)]
    out = run(lines)
    assert not out["checks"]["bitmap_no_failure"]
    assert not out["checks"]["bitmap_release_totals_match"]
    assert not out["c3_9_qualified"]


def test_all_frames_dropped_never_qualifies():
    # Every frame begins, but each sealed batch is dropped whole (cause 0x2 = unsupported capture).
    dropped = [tick(n, begin=1) .replace("bitmap-frames-dropped=0", f"bitmap-frames-dropped={n}")
               for n in (1, 2, 3)]
    lines = [GOOD_BOUND] + dropped + [release(requests=6, begins=3, queue_ends=3)]
    out = run(lines)
    assert not out["checks"]["bitmap_accepted_frames_nonzero"]
    assert not out["checks"]["bitmap_no_dropped_batches"]
    assert not out["c3_9_qualified"]


def test_accepted_frames_require_nonzero_count():
    # One accepted frame and one drop is still incomplete evidence, and the accepted count must be positive.
    lines = [GOOD_BOUND, tick(1, begin=1, views=4),
             tick(2, begin=1).replace("bitmap-frames-dropped=0", "bitmap-frames-dropped=1"),
             release(requests=4, begins=2, queue_ends=2)]
    out = run(lines)
    assert out["checks"]["bitmap_accepted_frames_nonzero"]
    assert not out["checks"]["bitmap_no_dropped_batches"]
    assert not out["c3_9_qualified"]


def test_release_totals_must_balance_with_ticks():
    lines = [GOOD_BOUND, tick(1, begin=1), tick(2, begin=1), release(requests=2, begins=2, queue_ends=2)]
    out = run(lines)
    assert not out["checks"]["bitmap_release_totals_match"]
    assert not out["c3_9_qualified"]

