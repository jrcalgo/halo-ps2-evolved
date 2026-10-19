#!/usr/bin/env python3
"""Build the play ELF, dump one GS frame of the fuel rod, and score it.

The still is the acceptance check against fuelrodingame.jpg. A mesh overlay
is not. The rifle-idle hands stay on the skeleton; a still with no hand in
the lower center is reported as such.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from compare_visibility import framebuffer  # noqa: E402
from render_reference import png  # noqa: E402
from test_emulator import OUTPUT  # noqa: E402

REFERENCE = Path("/home/ai/Pictures/fuelrodingame.jpg")
STILL_FRAME = 70


def _weapon_ref(image):
    width, height = image.size
    pixels = image.load()
    hits = []
    for y in range(height):
        for x in range(0, width, 2):
            red, green, blue = pixels[x, y]
            body = x > width * 0.5 and y > height * 0.22 and red > 80 and green < 55 and blue < 70 and red > green + 40
            meter = green > 180 and red < 140 and green > red + 50 and x > width * 0.6
            if body or meter:
                hits.append((x / width, y / height))
    return hits


def _weapon_still(rgb, width, height):
    hits = []
    green_hits = []
    for y in range(height):
        row = y * width * 3
        for x in range(width):
            red, green, blue = rgb[row + x * 3:row + x * 3 + 3]
            vent = green > 190 and green > red + 25 and green > blue + 30 and x > width * 0.55
            gold = x > width * 0.45 and red > 170 and 140 < green < 240 and blue < 150 and green > blue + 50
            if vent or gold:
                hits.append((x / width, y / height))
            if vent:
                green_hits.append((x / width, y / height))
    return hits, green_hits


def _hand_pixels(rgb, width, height):
    count = 0
    for y in range(int(height * 0.72), height):
        row = y * width * 3
        for x in range(int(width * 0.22), int(width * 0.68)):
            red, green, blue = rgb[row + x * 3:row + x * 3 + 3]
            if max(red, green, blue) < 70 and max(red, green, blue) - min(red, green, blue) < 28:
                count += 1
    return count


def _box(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _iou(reference, still, cells=48):
    def fill(points):
        occupied = set()
        for x, y in points:
            occupied.add((min(cells - 1, int(x * cells)), min(cells - 1, int(y * cells))))
        return occupied
    left, right = fill(reference), fill(still)
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


def _slope(points):
    if len(points) < 8:
        return 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    var = sum((x - mean_x) ** 2 for x in xs) or 1.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var


def score(reference_image, rgb, width, height):
    reference = _weapon_ref(reference_image)
    still, vents = _weapon_still(rgb, width, height)
    hands = _hand_pixels(rgb, width, height)
    if len(reference) < 20 or len(still) < 20:
        return {"iou": 0.0, "still_pixels": len(still), "hands": hands, "error": "weapon mask too small"}
    ref_box = _box(reference)
    still_box = _box(still)
    ref_muzzle = min(reference, key=lambda point: point[0])
    still_muzzle = min(still, key=lambda point: point[0])
    vent_y = sum(point[1] for point in vents) / len(vents) if vents else 1.0
    body_y = sum(point[1] for point in still) / len(still)
    return {
        "iou": round(_iou(reference, still), 4),
        "ref_box": [round(value, 3) for value in ref_box],
        "still_box": [round(value, 3) for value in still_box],
        "ref_muzzle": [round(value, 3) for value in ref_muzzle],
        "still_muzzle": [round(value, 3) for value in still_muzzle],
        "muzzle_dx": round(still_muzzle[0] - ref_muzzle[0], 3),
        "muzzle_dy": round(still_muzzle[1] - ref_muzzle[1], 3),
        "ref_slope": round(_slope(reference), 3),
        "still_slope": round(_slope(still), 3),
        "vents_above_body": vent_y < body_y,
        "vent_pixels": len(vents),
        "still_pixels": len(still),
        "hands": hands,
    }


def decode(run):
    raw = framebuffer((run / "emulog.txt").read_text(errors="replace"), STILL_FRAME)
    rgb = bytearray()
    for index in range(0, len(raw), 2):
        value = raw[index] | (raw[index + 1] << 8)
        rgb.extend(((value & 31) * 255 // 31, ((value >> 5) & 31) * 255 // 31, ((value >> 10) & 31) * 255 // 31))
    return rgb, 512, 448


def main():
    env = os.environ.copy()
    env["WORLD_VARIANT"] = "play"
    subprocess.run([sys.executable, str(ROOT / "tools/build_world.py")], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, str(ROOT / "tools/run_world_viewer.py"), "--fuel-still"], cwd=ROOT, check=True)
    report = json.loads((OUTPUT / "world-latest.json").read_text())
    if report.get("status") != "diagnostic-completed":
        raise SystemExit("Fuel-rod still did not finish: " + report.get("status", "missing"))
    run = Path(report["run_directory"])
    rgb, width, height = decode(run)
    image = run / "fuel-rod.png"
    png(image, width, height, rgb)
    from PIL import Image
    result = score(Image.open(REFERENCE).convert("RGB"), rgb, width, height)
    result["png"] = str(image)
    result["weapon"] = "FUEL ROD" if "FUEL ROD" in (run / "emulog.txt").read_text(errors="replace") else "missing"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
