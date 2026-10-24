"""C3 matrix evidence must come from the current successful guest launch."""
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_profile_boot_matrix as matrix  # noqa: E402


def test_failed_guest_launch_cannot_reuse_previous_render_evidence(tmp_path, monkeypatch):
    row = "bloodgulch_mounted_gunner_4p4bot"
    out_root = tmp_path / "runs"
    out = out_root / row
    old_guest = out / "guest/runs/partition-selected"
    old_guest.mkdir(parents=True)
    (out / "guest/manifest.json").write_text(json.dumps({"runs": [{
        "run": "partition-selected", "pcsx2_config": {"emu_mode_verified": True},
        "captures": [{"marker": "c3-render-held ", "nonblack_fraction": 0.9}],
    }]}))
    (old_guest / "halo_ps2_local.txt").write_text(
        "HALO_PS2_LOCAL c3-render-ready views=1\n")
    stale_capture = out / "captures/c3-render-held.png"
    stale_capture.parent.mkdir()
    stale_capture.write_bytes(b"old visible frame")

    monkeypatch.setattr(matrix, "OUTPUT_ROOT", out_root)
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    monkeypatch.setattr(matrix, "RESULT_ROOT", tmp_path / "results")
    monkeypatch.setattr(matrix, "stage_plan", lambda *_: {
        "map": "bloodgulch", "profile_id": 16, "package_root": tmp_path / "pkg",
        "scenario": "levels\\test\\bloodgulch\\bloodgulch",
        "package_tree": tmp_path / "tree", "guest_package_root": "build/c3/render-tree",
        "stage_paths": [],
    })
    elf = out / "link/current.elf"
    elf.parent.mkdir(parents=True)
    elf.write_bytes(b"linked current ELF")
    monkeypatch.setattr(matrix, "link_row", lambda *a, **k: (elf, ""))
    monkeypatch.setattr(matrix.subprocess, "run", lambda args, **kwargs:
                        CompletedProcess(args, 0, stdout="", stderr=""))

    def failed_runner(command, *, log, timeout, env=None):
        assert not (out / "guest/manifest.json").exists()
        assert not stale_capture.exists()
        log.write_text("Xvfb failed before PCSX2 launch\n")
        return 1, False

    monkeypatch.setattr(matrix, "run_group", failed_runner)
    result = matrix.run_row(row, package_root_override=tmp_path / "pkg",
                            render_views=1, workload_players=4)

    assert result["pass"] is False
    assert "guest runner exited 1" in result["reasons"][0]
    assert "guest_line_count" not in result
    assert "render" not in result
    assert result.get("captures") is None


def test_guest_provenance_requires_mode_and_current_launch(tmp_path):
    out = tmp_path / "attempt"
    run_dir = out / "guest/runs/partition-selected"
    captures_dir = out / "captures"
    run_dir.mkdir(parents=True)
    captures_dir.mkdir()
    launch_start = __import__("time").time_ns() - 1_000_000_000
    launch_id = "launch-current"
    invocation_id = "invocation-current"
    log = run_dir / "emu.txt"
    local = run_dir / "halo_ps2_local.txt"
    capture = captures_dir / "held.png"
    log.write_bytes(b"PCSX2 current launch")
    local.write_bytes(b"HALO_PS2_LOCAL current\n")
    capture.write_bytes(b"current visible pixels")
    import hashlib

    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    record = {
        "run": "partition-selected", "invocation_id": invocation_id,
        "launch_id": launch_id, "launch_started_unix_ns": launch_start,
        "launch_completed_unix_ns": __import__("time").time_ns(),
        "log": str(log), "log_sha256": digest(log),
        "halo_lines_saved": str(local), "halo_lines_sha256": digest(local),
        "pcsx2_config": {"emu_mode": "recompiler", "emu_mode_verified": True},
        "captures": [{"file": str(capture), "launch_id": launch_id,
                      "captured_unix_ns": __import__("time").time_ns(),
                      "sha256": digest(capture), "marker": "c3-render-held ",
                      "nonblack_fraction": 0.5}],
    }
    (out / "guest/manifest.json").write_text(json.dumps({
        "invocation_id": invocation_id, "runs": [record]}))

    accepted, reason = matrix.validate_guest_provenance(out, launch_start - 1,
                                                         "recompiler", expected_captures=1)
    assert reason == ""
    assert accepted["launch_id"] == launch_id

    record["pcsx2_config"]["emu_mode_verified"] = False
    (out / "guest/manifest.json").write_text(json.dumps({
        "invocation_id": invocation_id, "runs": [record]}))
    accepted, reason = matrix.validate_guest_provenance(out, launch_start - 1,
                                                         "recompiler", expected_captures=1)
    assert accepted is None
    assert "settings were not verified" in reason
