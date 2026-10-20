"""The M1 placement gate must bind two guest logs to one exact machine ELF."""
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hcu_ps2_m1_physical_gate import evaluate  # noqa: E402


RUNS = [
    ROOT / "build/hcu-ps2-closure/emulator-m1-recompiler-43f894e003384917b1d2b58687ce15a2/result.json",
    ROOT / "build/hcu-ps2-closure/emulator-m1-interpreter-cf28668ca6084700ad30d91e0f66d246/result.json",
]
PROBE = ROOT / "build/hcu-parent-link-probe/result.json"


def test_current_guarded_image_passes_both_guest_modes(tmp_path):
    if not PROBE.is_file() or any(not path.is_file() for path in RUNS):
        pytest.skip("build the combined ELF and run PCSX2 in both modes first")
    result = evaluate(PROBE, RUNS)
    assert result["gate"] == "closed", result["errors"]
    assert min(run["headroom_before_reserve_bytes"] for run in result["runs"]) > 0

    wrong = json.loads(RUNS[0].read_text())
    wrong["elf_sha256"] = "0" * 64
    tampered = tmp_path / "wrong-hash.json"
    tampered.write_text(json.dumps(wrong))
    rejected = evaluate(PROBE, [tampered, RUNS[1]])
    assert rejected["gate"] == "open"
    assert any("different ELF" in error for error in rejected["errors"])
