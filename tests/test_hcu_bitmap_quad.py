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
    for mode in ("valid", "overflow", "bad_uv", "add", "opaque", "multitexture", "premultiplied", "raw_add", "premultiplied_overflow", "meter_fill", "meter_empty", "meter_bad_ref"):
        args = [str(exe)] if mode == "valid" else [str(exe), mode]
        subprocess.run(args, check=True, capture_output=True, text=True)


def test_screen_flash_passes_match_the_retail_formulas(tmp_path):
    exe = tmp_path / "hcu_bitmap_flash_test"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ENGINE / "src"), "-I", str(ROOT / "src"),
        str(ROOT / "tests/hcu_bitmap_flash_main.c"),
        str(ROOT / "src/stream/hcu_bitmap_quad.c"),
        str(ENGINE / "src/render/chain.c"), str(ENGINE / "src/world/tex.c"),
        "-lm", "-o", str(exe),
    ], check=True, capture_output=True, text=True)
    modes = (
        "lighten_damage", "lighten_fade", "lighten_full", "lighten_white", "lighten_zero", "darken_camo", "darken_full",
        "max", "max_noop", "min", "invert_overshield", "invert_half", "invert_noframe", "tint_health",
        "tint_teleporter", "tint_teleporter_noframe", "overflow", "bad_rect", "bad_type", "pane_2p", "pane_4p", "pane_full",
    )
    for mode in modes:
        result = subprocess.run([str(exe), mode], capture_output=True, text=True)
        assert result.returncode == 0, f"{mode}: rc={result.returncode} {result.stdout}"


def test_button_glyphs_are_bounded_vector_packets(tmp_path):
    exe = tmp_path / "hcu_bitmap_glyph_test"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ENGINE / "src"), "-I", str(ROOT / "src"),
        str(ROOT / "tests/hcu_bitmap_glyph_main.c"),
        str(ROOT / "src/stream/hcu_bitmap_quad.c"),
        str(ENGINE / "src/render/chain.c"), str(ENGINE / "src/world/tex.c"),
        "-lm", "-o", str(exe),
    ], check=True, capture_output=True, text=True)
    subprocess.run([str(exe)], check=True, capture_output=True, text=True)
