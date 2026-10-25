"""Host test for tools/c2_profile_boot_matrix.c3_5_layout_checks on synthetic and real framebuffers.

Captures are full root windows (1280x1024) with the game in the top-left 640x480 area; the 512x448 layout
rectangles are mapped into that area, not into the whole capture.
"""
import importlib.util
import os
import sys
import tempfile

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("m", os.path.join(ROOT, "tools", "c2_profile_boot_matrix.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CLEAR = (16, 16, 24)
SCENE = (120, 200, 80)
ROOT_SIZE = (1280, 1024)
GAME_SIZE = (640, 480)
REAL_CAPTURE = os.path.join(ROOT, "build", "c3", "integration", "c3-pkg-r1", "render-v4-recompiler",
                            "bloodgulch_mounted_gunner_4p4bot", "captures", "capture-02-c3-render-held.png")
RECTS = {
    1: [(0, 0, 512, 448)],
    2: [(0, 0, 512, 224), (0, 224, 512, 224)],
    3: [(0, 0, 256, 224), (256, 0, 256, 224), (0, 224, 256, 224)],
    4: [(0, 0, 256, 224), (256, 0, 256, 224), (0, 224, 256, 224), (256, 224, 256, 224)],
}


def layout_image(views, clear_quadrant=True, black=()):
    """512x448 layout content, with the views listed in `black` left black, placed as the game area of a
    1280x1024 root (scaled NEAREST to 640x480 at the top-left)."""
    img = Image.new("RGB", (512, 448), (0, 0, 0))
    px = img.load()
    for i, (x0, y0, w, h) in enumerate(RECTS[views]):
        if i in black:
            continue
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                px[x, y] = SCENE if (x + y) % 3 else (30, 30, 30)
    if views == 3 and clear_quadrant:
        for y in range(224, 448):
            for x in range(256, 512):
                px[x, y] = CLEAR
    game = img.resize(GAME_SIZE, Image.NEAREST)
    root = Image.new("RGB", ROOT_SIZE, (0, 0, 0))
    root.paste(game, (0, 0))
    return root


def run_layout(views, img, **kw):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.png")
        img.save(p)
        return m.c3_5_layout_checks(views, [p], **kw)


def main():
    fails = 0

    def expect(cond, msg):
        nonlocal fails
        if not cond:
            print("FAIL", msg)
            fails += 1

    for views in (1, 2, 4):
        r = m.c3_5_layout_checks(views, [])
        expect(r["checks"].get("layout_capture_present") is False, f"missing capture not caught ({views})")
        r = run_layout(views, layout_image(views))
        expect(all(r["checks"].values()), f"clean {views}-view should pass: {r['reasons']}")
        expect(r["game_rect"]["source"] == "pcsx2-default", "default game rect source")

    r = run_layout(3, layout_image(3))
    expect(all(r["checks"].values()), f"clean 3-view should pass: {r['reasons']}")
    r = run_layout(3, layout_image(3, clear_quadrant=False))
    expect(r["checks"].get("layout_unused_quadrant_cleared") is False, "3-view uncleared quadrant not caught")

    # One black view must fail that view's nonblack check and no other view's.
    for views in (2, 3, 4):
        for k in range(views):
            r = run_layout(views, layout_image(views, black=(k,)))
            expect(r["checks"].get(f"layout_view{k}_nonblack") is False,
                   f"{views}-view with view{k} black passed view{k}_nonblack")
            others = [v for v in range(views) if v != k]
            expect(all(r["checks"].get(f"layout_view{v}_nonblack") for v in others),
                   f"{views}-view with view{k} black failed another view")

    # The explicit game size works too: a window-sized capture is the game area itself.
    r = run_layout(4, layout_image(4).crop((0, 0) + GAME_SIZE), game_size=GAME_SIZE)
    expect(all(r["checks"].values()), f"window-sized capture should pass: {r['reasons']}")
    expect(r["game_rect"]["source"] == "window", "window game rect source")
    # A 512x448 canvas (the old mapping's input) no longer contains the 640x480 game area.
    small = Image.new("RGB", (512, 448), (0, 0, 0))
    r = run_layout(4, small)
    expect(r["checks"].get("layout_game_rect_in_capture") is False, "game rect outside small capture not caught")

    game_from_captures = m.c3_5_game_size([{"window": "0x1", "window_size": "640x480"}])
    expect(game_from_captures == (640, 480), "window size read from capture entry")
    expect(m.c3_5_game_size([{"window": "root", "window_size": None}]) is None, "root capture has no game size")

    if os.path.isfile(REAL_CAPTURE):
        r = m.c3_5_layout_checks(4, [REAL_CAPTURE])
        expect(all(r["checks"].values()), f"real c3-pkg-r1 4-view capture: {r['reasons']}")
    else:
        print("skip real capture (not present)")

    print("c3_5_layout_checks: " + ("all passed" if not fails else f"{fails} failure(s)"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
