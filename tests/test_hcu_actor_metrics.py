"""Host test for the C5 actor metrics counters (bots vs retail records kept separate)."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_actor_metrics_host_contract(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        import pytest
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "hcu_actor_metrics_test"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Isrc",
        "tests/hcu_actor_metrics_main.c", "src/stream/hcu_actor_metrics.c", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu_actor_metrics tests passed" in result.stdout
