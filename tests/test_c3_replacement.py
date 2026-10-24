"""The rendered successor diagnostic cannot promote absent or misordered proof."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_profile_boot_matrix as matrix


def transaction_lines():
    p = matrix.PREFIX
    return [p + "c3-render-ready map=bloodgulch views=4",
            p + "map-replacement phase=candidate-validated old=bloodgulch new=beavercreek readers=1",
            p + "map-replacement phase=quiesce-begin old=bloodgulch new=beavercreek readers=1",
            p + "map-replacement phase=quiesce-end old=bloodgulch new=beavercreek readers=0 drained=1",
            p + "production-ce-successor-step step=dispose result=1",
            p + "c3-render-ready map=beavercreek views=4"]


def check(lines, mode=1, captures=None):
    return matrix.rendered_successor_checks(
        lines, "bloodgulch", "beavercreek", mode, 4,
        captures if captures is not None else [{"nonblack_fraction": 0.7}] * 2)


def test_rendered_successor_requires_validated_drain_before_ce_dispose():
    good = check(transaction_lines())
    assert all(good["checks"].values())
    assert good["c3_11_qualified"] is False
    for left, right in [(1, 2), (3, 4)]:
        reordered = transaction_lines()
        reordered[left], reordered[right] = reordered[right], reordered[left]
        assert not check(reordered)["checks"]["candidate_before_quiesce_before_dispose"]
    assert not check(transaction_lines(), captures=[{"nonblack_fraction": 0}] * 2)["checks"]["replacement_captures_visible"]


def test_failed_preflight_must_keep_old_renderer_and_skip_quiesce():
    lines = [transaction_lines()[0]]
    assert all(check(lines, mode=2)["checks"].values())
    assert not check(lines + [transaction_lines()[2]], mode=2)["checks"]["failed_preflight_preserves_renderer"]


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
