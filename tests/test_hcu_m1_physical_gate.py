"""The M1 placement gate must bind two guest logs to one exact machine ELF."""
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hcu_ps2_m1_physical_gate import evaluate  # noqa: E402


PROBE = ROOT / "build/hcu-parent-link-probe/result.json"


def current_runs():
    """Select current-hash evidence, not a previously hard-coded ELF run."""
    if not PROBE.is_file():
        return []
    probe = json.loads(PROBE.read_text())
    elf_hash = probe["hcu_gameplay_machine"]["elf"]["sha256"]
    candidates = []
    for path in (ROOT / "build/hcu-ps2-closure").glob("emulator-m1-*/result.json"):
        try:
            result = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if result.get("elf_sha256") == elf_hash:
            candidates.append((path.stat().st_mtime_ns, result.get("mode"), path))
    selected = {}
    for _, mode, path in sorted(candidates):
        if mode in {"interpreter", "recompiler"}:
            selected[mode] = path
    return [selected["recompiler"], selected["interpreter"]] if len(selected) == 2 else []


def test_current_guarded_image_passes_both_guest_modes(tmp_path):
    runs = current_runs()
    if not runs:
        pytest.skip("build the combined ELF and run PCSX2 in both modes first")
    result = evaluate(PROBE, runs)
    assert result["gate"] == "closed", result["errors"]
    assert min(run["headroom_before_reserve_bytes"] for run in result["runs"]) > 0

    wrong = json.loads(runs[0].read_text())
    wrong["elf_sha256"] = "0" * 64
    tampered = tmp_path / "wrong-hash.json"
    tampered.write_text(json.dumps(wrong))
    rejected = evaluate(PROBE, [tampered, runs[1]])
    assert rejected["gate"] == "open"
    assert any("different ELF" in error for error in rejected["errors"])
