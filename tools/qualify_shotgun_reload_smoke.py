#!/usr/bin/env python3
"""Qualify matching PCSX2 integrated shotgun shell-reload runs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "build/emulator/runs"
PREFIX = r"^\[\s*[0-9.]+\]\s+"


def parse_trace(log: str):
    """Return a normalized gameplay trace and the retail reload summary."""
    shots = [tuple(map(int, row)) for row in re.findall(
        r"\[play\] fire SHOTGUN (\d+) pellets (\d+) tick (\d+) loaded (\d+)", log)]
    states = [tuple(map(int, row)) for row in re.findall(
        r"\[play\] shotgun-state tick (\d+) loaded (-?\d+) total (-?\d+) magazine (-?\d+) timer (-?\d+)", log)]
    if not states or states[0][1:3] != (12, 12):
        raise RuntimeError("shotgun did not initialize with the retail 12/12 ammo state")
    if len(shots) != 12 or [row[3] for row in shots] != list(range(11, -1, -1)) or any(row[1] != 15 for row in shots):
        raise RuntimeError("shotgun trace does not contain 12 shots, 15 pellets each, with exact ammo consumption")

    shell_rows = []
    max_loaded = 0
    for row in states:
        if row[1] == max_loaded + 1 and row[1] + row[2] == 12:
            shell_rows.append(row)
            max_loaded = row[1]
    shell_ticks = [row[0] for row in shell_rows]
    if (len(shell_rows) != 12 or [row[1] for row in shell_rows] != list(range(1, 13)) or
            shell_rows[-1][2] != 0 or len(set(b - a for a, b in zip(shell_ticks, shell_ticks[1:]))) != 1):
        raise RuntimeError("reload did not transfer exactly one reserve shell at a stable interval")
    done = re.search(r"\[done\] frames=(\d+) dropped=(\d+)", log)
    if not done or int(done[1]) < 900 or int(done[2]) != 0 or "[err]" in log or " OVERFLOW" in log:
        raise RuntimeError("shotgun emulator run did not complete 900 frames cleanly")

    first_tick = shots[0][2]
    trace = []
    for line in log.splitlines():
        event = re.sub(PREFIX, "", line)
        shot = re.fullmatch(r"\[play\] fire SHOTGUN (\d+) pellets (\d+) tick (\d+) loaded (\d+)", event)
        state = re.fullmatch(r"\[play\] shotgun-state tick (\d+) loaded (-?\d+) total (-?\d+) magazine (-?\d+) timer (-?\d+)", event)
        if shot:
            trace.append(("fire", int(shot[3]) - first_tick, int(shot[1]), int(shot[2]), int(shot[4])))
        elif state:
            trace.append(("state", int(state[1]) - first_tick, *map(int, state.groups()[1:])))
    summary = {
        "frames": int(done[1]), "dropped": int(done[2]), "shots": len(shots),
        "shot_ticks": [row[2] for row in shots], "magazine_after_shots": [row[3] for row in shots],
        "shell_ticks": shell_ticks, "shell_interval_ticks": shell_ticks[1] - shell_ticks[0],
        "loaded_after_each_shell": [row[1] for row in shell_rows], "reserve_after_last_shell": shell_rows[-1][2],
    }
    return summary, trace


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_run(name: str, mode: str, sources: dict[str, str]):
    run = (RUNS / name).resolve()
    if not run.is_relative_to(RUNS.resolve()) or not run.is_dir():
        raise RuntimeError(f"invalid {mode} run directory: {name}")
    record = json.loads((run / "result.json").read_text())
    log = (run / "emulog.txt").read_text(errors="replace")
    if (record.get("status") != "diagnostic-completed" or record.get("scenario") != "bloodgulch-static" or
            record.get("variant") != "play" or record.get("mode") != mode or record.get("dropped") != 0):
        raise RuntimeError(f"{mode} run did not complete the shotgun reload smoke")
    if record.get("source_sha256") != sources:
        raise RuntimeError(f"{mode} source manifest differs from current play build")
    for source, digest in sources.items():
        if sha(ROOT / source) != digest:
            raise RuntimeError(f"source changed after build: {source}")
    if sha(run / "boot/world.elf") != record.get("elf_sha256"):
        raise RuntimeError(f"{mode} copied ELF hash mismatch")
    captures = [Path(path).resolve() for path in record.get("captures", [])]
    for expected in ("visible-start.png", "visible-final.png"):
        capture = next((path for path in captures if path.name == expected), None)
        if capture is None or not capture.is_relative_to(run) or not capture.is_file() or capture.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"{mode} missing valid {expected}")
    summary, trace = parse_trace(log)
    if record.get("shotgun_reload_smoke") != summary:
        # Runner keeps the same measurements, but also records the retail tag and source references.
        smoke = record.get("shotgun_reload_smoke", {})
        if any(smoke.get(key) != value for key, value in summary.items() if key in smoke):
            raise RuntimeError(f"{mode} result metadata disagrees with emulator log")
    return {"run": str(run.relative_to(ROOT)), "mode": mode,
            "elf_sha256": record["elf_sha256"], **summary}, trace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recompiler", required=True)
    parser.add_argument("--interpreter", required=True)
    args = parser.parse_args()
    sources = json.loads((ROOT / "build/world-play-elf/result.json").read_text())["source_sha256"]
    rec, rec_trace = read_run(args.recompiler, "recompiler", sources)
    interp, interp_trace = read_run(args.interpreter, "interpreter", sources)
    if rec["elf_sha256"] != interp["elf_sha256"]:
        raise RuntimeError("CPU modes did not execute the same ELF")
    if rec_trace != interp_trace:
        raise RuntimeError("interpreter and recompiler shotgun reload traces differ")
    digest = hashlib.sha256(("\n".join(map(str, rec_trace)) + "\n").encode()).hexdigest()
    result = {
        "status": "passed", "scenario": "retail shotgun empty -> shell-by-shell reload",
        "trace_sha256": digest, "trace_events": len(rec_trace),
        "modes": {"recompiler": rec, "interpreter": interp},
        "limitations": [
            "This is one retail shotgun profile and does not establish every weapon's reload/eject behavior.",
            "PCSX2 recompiler/interpreter agreement does not establish physical-PS2 CPU/RAM budgets.",
            "The run does not qualify projectile replay across differing rendering schedules.",
        ],
    }
    output = ROOT / "build/emulator/shotgun-reload-smoke-qualification.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"passed: {output.relative_to(ROOT)} trace={digest} events={len(rec_trace)}")


if __name__ == "__main__":
    main()
