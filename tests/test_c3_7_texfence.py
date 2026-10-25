"""C3.7 texture fence: host tests of the real texture cache and the c3_7_texfence_checks log checker.

The real code (submodules/halo-ps2/engine/src/render/texcache.c, with its fence counters) is compiled
with the host compiler and run by engine/tests/test_texcache.c. The checker is exercised on synthetic guest lines; a synthetic log can never
qualify C3.7 without the matching guest lines, and the in-guest proof is the PCSX2 run under build/c3/texfence/runs/.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_profile_boot_matrix as matrix


ENGINE = ROOT / "submodules/halo-ps2/engine"


def build_and_run_model() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "test_texcache"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                        "-I", str(ENGINE / "src"), str(ENGINE / "tests/test_texcache.c"),
                        str(ENGINE / "src/render/texcache.c"), "-o", str(exe)], check=True)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr
        return run.stdout


P = matrix.PREFIX


def texfence(kind, frame, **over):
    base = {"kick-seq": frame, "fence-seq": frame - 1, "claims-published": 40,
            "claims-published-before-queue": 0, "source-released": 1, "source-released-before-fence": 0,
            "reuse-blocked-by-fence": 0, "reuse-after-fence": 0, "reuse-unfenced": 0, "evictions": 0,
            "cap-pages": 0}
    base.update(over)
    body = " ".join(f"{k}={v}" for k, v in base.items())
    return P + f"c3-texfence kind={kind} frame={frame} {body}"


def frame_final(frames, views):
    return P + f"c3-frame kind=final frame={frames} views={views} frames={frames} overflow=0"


def good_log(frames=300, views=4, cap=0, **final_over):
    lines = [texfence("periodic", 30), texfence("final", frames, **final_over), frame_final(frames, views)]
    return lines


def test_texcache_fence_paths():
    out = build_and_run_model()
    assert out.strip() == "ok", out


def test_checker_accepts_clean_uncapped_run():
    res = matrix.c3_7_texfence_checks(good_log(), 4, 300, 0)
    assert res["qualified"], res["reasons"]


def test_checker_rejects_claim_before_queue():
    res = matrix.c3_7_texfence_checks(good_log(**{"claims-published-before-queue": 1}), 4, 300, 0)
    assert not res["qualified"]
    assert "c3-7 check failed: claims_published_before_queue_zero" in res["reasons"]


def test_checker_rejects_source_release_before_fence():
    res = matrix.c3_7_texfence_checks(good_log(**{"source-released-before-fence": 1}), 4, 300, 0)
    assert not res["qualified"]
    assert "c3-7 check failed: source_released_before_fence_zero" in res["reasons"]


def test_checker_rejects_fence_lag():
    res = matrix.c3_7_texfence_checks(good_log(**{"kick-seq": 300, "fence-seq": 290}), 4, 300, 0)
    assert not res["qualified"]
    assert "c3-7 check failed: fence_lag_at_most_one" in res["reasons"]


def test_checker_rejects_unfenced_reuse():
    res = matrix.c3_7_texfence_checks(good_log(**{"reuse-unfenced": 2}), 4, 300, 0)
    assert not res["qualified"]


def test_pressure_run_needs_real_reuse_after_fence():
    no_reuse = matrix.c3_7_texfence_checks(good_log(cap=64, **{"cap-pages": 64, "evictions": 0}), 4, 300, 64)
    assert not no_reuse["qualified"]
    assert "c3-7 check failed: pressure_evictions_seen" in no_reuse["reasons"]
    reused = matrix.c3_7_texfence_checks(
        good_log(**{"cap-pages": 64, "evictions": 120, "reuse-after-fence": 120, "reuse-blocked-by-fence": 7}),
        4, 300, 64)
    assert reused["qualified"], reused["reasons"]


def test_missing_final_line_never_qualifies():
    res = matrix.c3_7_texfence_checks([texfence("periodic", 30), frame_final(300, 4)], 4, 300, 0)
    assert not res["qualified"]


def test_cap_mismatch_rejected():
    res = matrix.c3_7_texfence_checks(good_log(**{"cap-pages": 0}), 4, 300, 64)
    assert not res["qualified"]
    assert "c3-7 check failed: cap_pages_recorded" in res["reasons"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
