from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_chain_variant_round_trip(tmp_path):
    binary = tmp_path / "hcu-chain-variant"
    build = subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            "submodules/halo-ce-universal/source/game",
            "tests/hcu_chain_variant_main.c",
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "chain-variant-ok" in run.stdout
