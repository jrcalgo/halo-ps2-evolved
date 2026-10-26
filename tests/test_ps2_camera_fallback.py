import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ps2_camera_fallback_tracks_native_first_person_forward(tmp_path):
    executable = tmp_path / "ps2_camera_fallback_test"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
            str(ROOT / "tests/ps2_camera_fallback_main.c"),
            "-lm",
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable)], check=True)
