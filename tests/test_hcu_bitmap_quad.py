import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"


def test_real_chain_and_gs_tex_readers_validate_quad(tmp_path):
    exe = tmp_path / "hcu_bitmap_quad_test"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ENGINE / "src"), "-I", str(ROOT / "src"),
        str(ROOT / "tests/hcu_bitmap_quad_main.c"),
        str(ROOT / "src/stream/hcu_bitmap_quad.c"),
        str(ENGINE / "src/render/chain.c"), str(ENGINE / "src/world/tex.c"),
        "-lm", "-o", str(exe),
    ], check=True, capture_output=True, text=True)
    for mode in ("valid", "overflow", "bad_uv", "add", "opaque", "multitexture", "premultiplied", "raw_add", "premultiplied_overflow"):
        args = [str(exe)] if mode == "valid" else [str(exe), mode]
        subprocess.run(args, check=True, capture_output=True, text=True)
