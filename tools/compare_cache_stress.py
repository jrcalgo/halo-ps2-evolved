"""Compare a full-cache and constrained-cache GS image after the same view sweep."""
import hashlib
import json
from pathlib import Path
import re
import sys

from compare_visibility import framebuffer
from render_reference import png
from test_emulator import ROOT, sha, save


def verify(baseline_path, stress_path, complete=False):
    baseline_path = Path(baseline_path).resolve()
    stress_path = Path(stress_path).resolve()
    a, b = json.loads(baseline_path.read_text()), json.loads(stress_path.read_text())
    fields = ("mode", "elf_sha256", "pack_sha256", "camera", "framebuffer_frame", "framebuffer_frames")
    if any(a.get(key) != b.get(key) for key in fields):
        raise RuntimeError("Paired runs differ in mode, ELF, packs, initial camera, or capture frames")
    if a.get("status") != "diagnostic-completed" or b.get("status") != "diagnostic-completed":
        raise RuntimeError("Both visible diagnostics must complete")
    if not a.get("cache_route") or not b.get("cache_route") or a.get("cache_pages") != 0 or not b.get("cache_pages"):
        raise RuntimeError("Expected an uncapped baseline and a capped cache-route run")
    frames = [int(frame) for frame in (a.get("framebuffer_frames") or [a["framebuffer_frame"]])]
    run_a, run_b = Path(a["run_directory"]), Path(b["run_directory"])
    cfg_a = (run_a / "boot/halo.cfg").read_text().splitlines()
    cfg_b = (run_b / "boot/halo.cfg").read_text().splitlines()
    cfg_a = [line for line in cfg_a if not line.startswith("cache_pages ")]
    cfg_b = [line for line in cfg_b if not line.startswith("cache_pages ")]
    if cfg_a != cfg_b or "cache_route 1" not in cfg_a or "overlay 0" not in cfg_a or any(f"fbdump {frame}" not in cfg_a for frame in frames):
        raise RuntimeError("Paired run configurations differ beyond the cache cap")
    if complete:
        churn = b.get("streaming", {}).get("texture_churn", {})
        if churn.get("failed") or churn.get("deferred"):
            raise RuntimeError("Constrained sweep dropped or deferred texture requests")
    raw_by_frame = []
    for is_stress, r, run in ((False, a, run_a), (True, b, run_b)):
        if not r.get("visible") or sha(run / "boot/world.elf") != r["elf_sha256"]:
            raise RuntimeError("A staged ELF is missing or changed")
        for name, digest in r["source_sha256"].items():
            if sha(Path(__file__).resolve().parents[1] / name) != digest:
                raise RuntimeError("Viewer source changed after run: " + name)
        if r["runner_sha256"] != sha(ROOT / "tools/run_world_viewer.py"):
            raise RuntimeError("Runner source changed after run")
        log = Path(r["log"]).read_text(errors="replace")
        if "[err]" in log or " OVERFLOW" in log or "[done]" not in log:
            raise RuntimeError("A viewer reported an error or did not finish")
        if is_stress and r.get("streaming", {}).get("texture_churn", {}).get("evictions", 0) < 1:
            raise RuntimeError("Capped run did not record a rendered eviction")
        decoded = []
        for frame in frames:
            marker = f"[fb] begin frame={frame}"
            before_capture = log.split(marker, 1)[0]
            profiles = re.findall(r"\[prof\] frames=(\d+).*?defer=(\d+) fail=(\d+)", before_capture)
            if not profiles or int(profiles[-1][0]) != frame or int(profiles[-1][1]) or int(profiles[-1][2]):
                raise RuntimeError(f"Frame {frame} lacks a clean texture-defer/failure profiler sample")
            raw = framebuffer(log, frame)
            (run / f"framebuffer-{frame}.rgb16").write_bytes(raw)
            rgb = bytearray()
            for i in range(0, len(raw), 2):
                v = raw[i] | raw[i + 1] << 8
                rgb.extend(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31))
            png(run / f"framebuffer-{frame}.png", 512, 448, rgb)
            decoded.append(raw)
        raw_by_frame.append(decoded)
    pixel_sha = []
    for frame, raw_a, raw_b in zip(frames, raw_by_frame[0], raw_by_frame[1]):
        if raw_a != raw_b:
            differing = sum(raw_a[i:i+2] != raw_b[i:i+2] for i in range(0, len(raw_a), 2))
            raise RuntimeError(f"Constrained-cache frame {frame} differs at {differing} pixels")
        pixel_sha.append(hashlib.sha256(raw_a).hexdigest())
    report = {"status": "passed", "mode": a["mode"], "frames": frames,
              "baseline_run": str(run_a), "stress_run": str(run_b),
              "cache_pages": b["cache_pages"],
              "evictions": b["streaming"]["texture_churn"]["evictions"],
              "failures": b["streaming"]["texture_churn"]["failed"],
              "deferred": b["streaming"]["texture_churn"]["deferred"],
              "pixel_sha256": pixel_sha,
              "different_pixels": 0,
              "limits": "Sampled raw GS views after a fixed-camera sweep; not a full-route or physical-PS2 guarantee."}
    out = Path("build/streaming-ee") / f"cache-stress-{b['cache_pages']}-{a['mode']}.json"
    save(out, report)
    print(f"Cache churn framebuffer matches: {a['mode']}, {report['evictions']} evictions, frames {frames}")


if __name__ == "__main__":
    complete = "--complete" in sys.argv[1:]
    args = [item for item in sys.argv[1:] if item != "--complete"]
    if len(args) != 2:
        sys.exit("usage: python3 tools/compare_cache_stress.py [--complete] BASELINE_RESULT STRESS_RESULT")
    try:
        verify(args[0], args[1], complete)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        sys.exit("Cache-stress comparison failed: " + str(exc))
