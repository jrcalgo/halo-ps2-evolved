"""Guarded split-v2 carve, overflow detection, exhaustion, and reinit."""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def test_guarded_v2_layout_on_host():
    with tempfile.TemporaryDirectory() as temporary:
        binary = Path(temporary) / "hcu-v2-guard"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "submodules/halo-ps2/engine/src"),
            str(ROOT / "tests/hcu_v2_guard_main.c"),
            str(ROOT / "submodules/halo-ps2/engine/src/core/mem.c"),
            "-o", str(binary),
        ], check=True, capture_output=True, text=True)
        subprocess.run([str(binary)], check=True, capture_output=True, text=True)
