import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fixed_tick_scheduler(tmp_path):
    compiler = shutil.which("cc")
    assert compiler, "A host C compiler is required"
    executable = tmp_path / "scheduler"
    subprocess.run(
        [compiler, "-std=gnu89", "-Wall", "-Wextra", "-Werror", "-O2",
         "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
         str(ROOT / "tests/hcu_c3_scheduler_main.c"), "-o", str(executable)],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    assert "scheduler-ok" in result.stdout
