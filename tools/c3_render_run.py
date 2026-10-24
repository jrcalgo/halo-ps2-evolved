#!/usr/bin/env python3
"""C3 render runner: boot one HCU ELF in PCSX2 and capture the framebuffer.

Captures the X root window of an Xvfb display (no window manager, so no wmctrl) with
`xwd -root` at timed intervals and converts each capture to PNG with ffmpeg. The emulator
log is kept verbatim; HALO_PS2_LOCAL lines are parsed into key=value counters and written to
summary.json together with the capture list and the PCSX2/ELF hashes.

It starts its own Xvfb only when the display is not already answering, and kills only that
process. The PCSX2 process is started in its own session and stopped on timeout or exit.

Usage:
    python3 -I tools/c3_render_run.py --elf PATH [--run NAME] [--timeout S] [--capture-every S]
        [--display :99]

Output: build/c3/render/<run>/ (emu.txt, halo_ps2_local.txt, launcher.log, capture-*.png,
capture-*.xwd, summary.json).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PCSX2 = Path(os.environ.get("PCSX2_BIN", "/home/ai/.local/bin/pcsx2"))
PROFILE_TEMPLATE = ROOT / ("build/hcu-ps2-closure/"
                           "emulator-m1-interpreter-0139052a7cf940829aa1384ca8c0152f/data")
FFMPEG = shutil.which("ffmpeg") or "/home/ai/miniconda3/envs/dl/bin/ffmpeg"
KV = re.compile(r"([A-Za-z0-9_\-]+)=(\S+)")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def display_alive(display: str) -> bool:
    return subprocess.run(["xdpyinfo", "-display", display], capture_output=True).returncode == 0


def ensure_display(display: str):
    """Return the Xvfb process we started, or None when the display already answers."""
    if display_alive(display):
        return None
    server = subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=True)
    for _ in range(50):
        if display_alive(display):
            return server
        if server.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError(f"Xvfb did not become ready on {display}")


def stop(process, grace: float) -> str:
    if process is None or process.poll() is not None:
        return "already-exited"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return "already-exited"
    try:
        process.wait(timeout=grace)
        return "terminated"
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        return "killed"


def capture(display: str, out_base: Path) -> dict:
    xwd = out_base.with_suffix(".xwd")
    png = out_base.with_suffix(".png")
    env = {**os.environ, "DISPLAY": display}
    r = subprocess.run(["xwd", "-root", "-silent", "-out", str(xwd)], env=env, capture_output=True)
    if r.returncode != 0:
        return {"file": None, "error": r.stderr.decode(errors="replace").strip()}
    c = subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", str(xwd), str(png)],
                       capture_output=True)
    if c.returncode != 0:
        return {"file": str(xwd), "error": "ffmpeg: " + c.stderr.decode(errors="replace").strip()}
    return {"file": str(png), "xwd": str(xwd), "bytes": png.stat().st_size}


def parse_counters(lines):
    """Group HALO_PS2_LOCAL lines by their first token and keep each line's key=value fields."""
    groups = {}
    for line in lines:
        body = line.split("HALO_PS2_LOCAL ", 1)[1] if "HALO_PS2_LOCAL " in line else ""
        parts = body.split()
        if not parts:
            continue
        tag = parts[0]
        fields = {}
        for k, v in KV.findall(" ".join(parts[1:])):
            fields[k] = v
        groups.setdefault(tag, []).append(fields)
    return groups


def halo_lines(text: str):
    return [ln for ln in text.splitlines() if "HALO_PS2_LOCAL" in ln]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--elf", type=Path, required=True)
    ap.add_argument("--run", default=None, help="output name under build/c3/render/")
    ap.add_argument("--display", default=os.environ.get("C3_RENDER_DISPLAY", ":99"))
    ap.add_argument("--timeout", type=int, default=120, help="seconds before PCSX2 is stopped")
    ap.add_argument("--capture-every", type=float, default=15.0)
    ap.add_argument("--first-capture", type=float, default=10.0)
    args = ap.parse_args()

    elf = args.elf.resolve()
    if not elf.is_file():
        ap.error(f"ELF not found: {elf}")
    run = args.run or elf.stem
    out = ROOT / "build/c3/render" / run
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    data = out / "data"
    shutil.copytree(PROFILE_TEMPLATE, data)
    guest = out / elf.name
    shutil.copy2(elf, guest)

    xvfb = ensure_display(args.display)
    env = {**os.environ, "DISPLAY": args.display, "APPIMAGE_EXTRACT_AND_RUN": "1",
           "QT_QPA_PLATFORM": "xcb"}
    log = out / "emu.txt"
    command = [str(PCSX2), "-batch", "-nogui", "-datapath", str(data),
               "-logfile", str(log), "-elf", str(guest)]
    captures = []
    status = "not-run"
    start = time.monotonic()
    try:
        with (out / "launcher.log").open("w") as launcher:
            process = subprocess.Popen(command, cwd=out, env=env, stdout=launcher,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            due = args.first_capture
            n = 0
            while True:
                elapsed = time.monotonic() - start
                if process.poll() is not None:
                    status = f"host-exited-{process.returncode}"
                    break
                if elapsed >= args.timeout:
                    status = f"bounded-timeout-{args.timeout}s"
                    break
                if elapsed >= due:
                    n += 1
                    captures.append(capture(args.display, out / f"capture-{n:02d}-{int(elapsed)}s"))
                    due += args.capture_every
                time.sleep(0.2)
            if captures:
                captures.append(capture(args.display, out / f"capture-final-{int(time.monotonic() - start)}s"))
            stopped = stop(process, grace=10.0)
    finally:
        if xvfb is not None:
            stop(xvfb, grace=3.0)

    text = log.read_text(errors="replace") if log.exists() else ""
    lines = halo_lines(text)
    (out / "halo_ps2_local.txt").write_text("\n".join(lines) + "\n")
    summary = {
        "run": run,
        "elf": str(elf),
        "elf_sha256": sha256(elf),
        "pcsx2": str(PCSX2),
        "pcsx2_sha256": sha256(PCSX2),
        "display": args.display,
        "status": status,
        "pcsx2_stop": stopped if captures or status else None,
        "elapsed_s": round(time.monotonic() - start, 1),
        "captures": captures,
        "counters": parse_counters(lines),
        "halo_lines": len(lines),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"run": run, "status": status, "captures": [c.get("file") for c in captures],
                      "halo_lines": len(lines)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
