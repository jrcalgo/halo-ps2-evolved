"""Host test for tools/c2_profile_boot_matrix.c3_5_layout_checks on synthetic framebuffers."""
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


def frame(views, clear_quadrant=True):
    img = Image.new("RGB", (640, 448), (0, 0, 0))
    px = img.load()
    rects = {
        1: [(0, 0, 640, 448)],
        2: [(0, 0, 640, 224), (0, 224, 640, 224)],
        3: [(0, 0, 320, 224), (320, 0, 320, 224), (0, 224, 320, 224)],
        4: [(0, 0, 320, 224), (320, 0, 320, 224), (0, 224, 320, 224), (320, 224, 320, 224)],
    }[views]
    for x0, y0, w, h in rects:
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                px[x, y] = SCENE if (x + y) % 3 else (30, 30, 30)
    if views == 3:
        for y in range(224, 448):
            for x in range(320, 640):
                px[x, y] = CLEAR if clear_quadrant else SCENE
    return img


def main():
    fails = 0
    for views in (1, 2, 4):
        r = m.c3_5_layout_checks(views, [])
        fails += r["checks"].get("layout_capture_present") is not False
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.png")
            frame(views).save(p)
            r = m.c3_5_layout_checks(views, [p])
            if not all(r["checks"].values()):
                print("FAIL views", views, r["reasons"]); fails += 1
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.png")
        frame(3).save(p)
        r = m.c3_5_layout_checks(3, [p])
        if not all(r["checks"].values()):
            print("FAIL 3-view clean", r["reasons"]); fails += 1
        frame(3, clear_quadrant=False).save(p)
        r = m.c3_5_layout_checks(3, [p])
        if r["checks"].get("layout_unused_quadrant_cleared") is not False:
            print("FAIL 3-view uncleared quadrant not caught"); fails += 1
    r = m.c3_5_layout_checks(2, [])
    if r["checks"].get("layout_capture_present") is not False:
        print("FAIL missing capture not caught"); fails += 1
    print("c3_5_layout_checks: " + ("all passed" if not fails else f"{fails} failure(s)"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
