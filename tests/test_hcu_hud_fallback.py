import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def _function_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?m)^struct bitmap_data const \*{re.escape(name)}\s*\([^;{{]*\)\s*\{{",
        source,
    )
    assert match, f"missing {name} implementation"
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():index + 1]
    raise AssertionError(f"unclosed {name} body")


def test_ps2_hud_sprite_fallback_returns_the_authored_bitmap():
    compiler = shutil.which("cc")
    if not compiler:
        import pytest

        pytest.skip("host C compiler unavailable")

    source = (HCU / "port/ps2/src/ps2_interface.c").read_text()
    body = _function_body(source, "hud_hires_sprite_bitmap")
    manifest = json.loads((HCU / "port/ps2/port.json").read_text())
    assert "port/ps2/src/ps2_interface.c" in manifest["port_sources"]

    harness = f"""
struct bitmap_data;
{body}
int main(void)
{{
    struct bitmap_data const *sheet = (struct bitmap_data const *)0x1000;
    return hud_hires_sprite_bitmap(sheet, 7) == sheet &&
        hud_hires_sprite_bitmap((struct bitmap_data const *)0, 7) == 0 ? 0 : 1;
}}
"""
    with tempfile.TemporaryDirectory(prefix="hcu-hud-fallback-") as temporary:
        c_file = Path(temporary) / "hud_fallback.c"
        executable = Path(temporary) / "hud_fallback"
        c_file.write_text(harness)
        subprocess.run(
            [compiler, "-std=c89", "-Wall", "-Wextra", "-Werror",
             str(c_file), "-o", str(executable)],
            check=True, capture_output=True, text=True,
        )
        subprocess.run([str(executable)], check=True)


def test_stock_hud_caller_never_receives_null_for_a_valid_source_bitmap():
    source = (HCU / "source/interface/hud_messaging.c").read_text()
    start = source.rindex("static void render_state_bitmap(")
    body = source[start:source.index("\nstatic ", start + 1)]
    assert "if (bitmap && _texture_cache_bitmap_get_hardware_format(" in body
    assert "bitmap = hud_hires_sprite_bitmap(bitmap, icon->sequence_index);" in body
    assert "bitmap->width" in body
    assert "return bitmap;" in _function_body(
        (HCU / "port/ps2/src/ps2_interface.c").read_text(),
        "hud_hires_sprite_bitmap",
    )
