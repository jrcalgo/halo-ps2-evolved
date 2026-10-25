"""C3.5 host tests: per-view state checks on synthetic guest lines, the combined C3.5 verdict with a synthetic
framebuffer, and the PS2 config default that gates CE's first-person snapshot. No PCSX2 run is involved."""
import importlib.util
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ci = _load("c3_integration_c35", "tools/c3_integration.py")
c2m = _load("c2m_c35", "tools/c2_profile_boot_matrix.py")

VIEWPORTS = ci.C3_5_VIEWPORTS


def good_lines(views, *, fp_nodes=2, fp_drawn=1, frame=30):
    out = []
    for v in range(views):
        x, y, w, h = VIEWPORTS[views][v]
        out.append(
            f"HALO_PS2_LOCAL c3-views frame={frame} view={v} camera=snapshot pos_x100=0,0,0 fov_h_x100=100 "
            f"pitch_x100=0 active=1 viewport={x},{y},{w},{h} hud=3 fp-nodes={fp_nodes} fp-drawn={fp_drawn} "
            f"fp-placeholder=0 bank-views={views} bank-seq={frame} pins=0")
    return out


@pytest.mark.parametrize("views", [1, 2, 3, 4])
def test_view_state_passes_for_every_layout(views):
    result = ci.c3_5_view_checks(good_lines(views), views)
    assert all(result["checks"].values()), result["reasons"]


def test_baseline_zero_first_person_fails():
    # The failed baseline: CE published no first-person nodes and the object pass drew none.
    result = ci.c3_5_view_checks(good_lines(4, fp_nodes=0, fp_drawn=0), 4)
    assert result["checks"]["view0_fp_nodes_published"] is False
    assert result["checks"]["view3_fp_drawn"] is False
    assert any("fp_drawn" in r for r in result["reasons"])


def test_missing_view_line_fails():
    lines = good_lines(4)[:-1]
    result = ci.c3_5_view_checks(lines, 4)
    assert result["checks"]["views_state_present"] is False
    assert result["checks"]["view3_active"] is False


def test_fixed_camera_and_wrong_viewport_fail():
    lines = good_lines(2)
    lines[1] = lines[1].replace("camera=snapshot", "camera=fixed").replace("viewport=0,224,512,224",
                                                                         "viewport=0,224,512,200")
    result = ci.c3_5_view_checks(lines, 2)
    assert result["checks"]["view1_camera_snapshot"] is False
    assert result["checks"]["view1_viewport_layout"] is False
    assert result["checks"]["view0_viewport_layout"] is True


def test_last_line_per_view_wins():
    # An early frame may be inactive; the verdict reads the newest line of each view.
    lines = good_lines(2, frame=0)
    lines[0] = lines[0].replace("active=1", "active=0")
    lines += good_lines(2, frame=30)
    result = ci.c3_5_view_checks(lines, 2)
    assert all(result["checks"].values()), result["reasons"]


def test_combined_verdict_uses_pixels_and_state(tmp_path):
    from PIL import Image

    def frame(views):
        img = Image.new("RGB", (512, 448), (0, 0, 0))
        px = img.load()
        for x0, y0, w, h in VIEWPORTS[views]:
            for y in range(y0, y0 + h):
                for x in range(x0, x0 + w):
                    px[x, y] = (120, 200, 80) if (x + y) % 3 else (30, 30, 30)
        if views == 3:
            for y in range(224, 448):
                for x in range(256, 512):
                    px[x, y] = (16, 16, 24)
        # The capture is the 1280x1024 root with the game in the top-left 640x480 area.
        root = Image.new("RGB", (1280, 1024), (0, 0, 0))
        root.paste(img.resize((640, 480), Image.NEAREST), (0, 0))
        return root

    capture = tmp_path / "held.png"
    frame(3).save(capture)
    held = [str(capture)]
    ok = ci.c3_5_checks(c2m, good_lines(3), 3, held)
    assert all(ok["checks"].values()), ok["reasons"]
    verdict = ci._verdict(ci.c3_5_checks, c2m, good_lines(3, fp_drawn=0), 3, held)
    assert verdict["status"] == "fail"
    assert verdict["first_failing"] == "view0_fp_drawn"


def test_score_lines_wires_c35_to_the_combined_checker():
    text = (ROOT / "tools/c3_integration.py").read_text()
    assert '"C3.5": _verdict(c3_5_checks, c2m, lines, views, held)' in text


def test_layout_rectangles_match_the_parent_layout_code():
    # hcu_render_layout_compute on 512x448: halves are 256 x 224; the 3-view clear is the bottom-right quadrant.
    frame_h = (ROOT / "src/stream/hcu_render_frame.c").read_text()
    assert "half_w = screen_w / 2;" in frame_h and "half_h = screen_h / 2;" in frame_h
    assert VIEWPORTS[3][1] == (256, 0, 256, 224)
    assert VIEWPORTS[4][3] == (256, 224, 256, 224)
    assert c2m.C3_5_CLEAR_RGB == (16, 16, 24)


def _config_boolean_under_test(define: bool) -> Path:
    """Compile the real config_boolean and ascii_nicmp of port/ps2/src/ps2_config.c on the host."""
    source = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_config.c").read_text()

    def function(signature):
        start = source.index(signature)
        depth = 0
        for i in range(source.index("{", start), len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    return source[start:i + 1]
        raise AssertionError("unterminated " + signature)

    body = "\n".join([
        "#include <stddef.h>",
        function("static int ascii_nicmp("),
        function("int config_boolean("),
    ])
    harness = body + r'''
#include <stdio.h>
int main(void) {
	const char *names[] = { "display.viewmodel_visible", "display.viewmodel_visible2",
		"display.viewmodel_visibl", "game.enhanced_animations", "display.viewmodel_hidden", NULL };
	int i;
	for (i = 0; names[i]; i++)
		printf("%s=%d\n", names[i], config_boolean(names[i]));
	return 0;
}
'''
    temp = Path(tempfile.mkdtemp(prefix="c35-config-"))
    src = temp / "config.c"
    src.write_text(harness)
    exe = temp / ("config-on" if define else "config-off")
    cmd = ["cc", "-std=c11", "-Wall", "-Werror", "-Wno-unused-function"]
    if define:
        cmd.append("-DHALO_PS2_C3_FRAME_SNAPSHOT")
    cmd += [str(src), "-o", str(exe)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return exe


def _run_config(exe: Path) -> dict:
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
    return {k: int(v) for k, v in (line.split("=") for line in out.split())}


def test_config_default_for_viewmodel_is_on_only_in_the_c3_snapshot_build():
    on = _run_config(_config_boolean_under_test(define=True))
    off = _run_config(_config_boolean_under_test(define=False))
    # The C3 snapshot build reads display.viewmodel_visible as true (the Linux default); the exact name only.
    assert on["display.viewmodel_visible"] == 1
    assert on["display.viewmodel_visible2"] == 0
    assert on["display.viewmodel_visibl"] == 0
    assert on["display.viewmodel_hidden"] == 0
    assert on["game.enhanced_animations"] == 1
    # C2 behaviour is unchanged without the flag.
    assert off["display.viewmodel_visible"] == 0
    assert off["game.enhanced_animations"] == 1


def test_config_edit_is_guarded_and_documented():
    source = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_config.c").read_text()
    assert re.search(r"#if defined\(HALO_PS2_C3_FRAME_SNAPSHOT\)\s*\n[^#]*display\.viewmodel_visible", source)
