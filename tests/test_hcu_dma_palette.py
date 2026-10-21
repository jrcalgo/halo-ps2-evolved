from pathlib import Path
import subprocess
import tempfile


def test_parent_vu1_palette_dma_payload_is_qword_aligned():
    root = Path(__file__).resolve().parents[1]
    engine = root / "submodules/halo-ps2/engine/src"
    with tempfile.TemporaryDirectory(prefix="hcu-dma-palette-") as temp:
        executable = Path(temp) / "hcu-dma-palette-test"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I" + str(engine),
            str(root / "tests/hcu_dma_palette_main.c"),
            str(engine / "render/chain.c"),
            str(engine / "sim/skeleton.c"),
            str(engine / "core/mat.c"), "-lm", "-o", str(executable),
        ], check=True, capture_output=True, text=True)
        subprocess.run([str(executable)], check=True, capture_output=True,
                       text=True)
