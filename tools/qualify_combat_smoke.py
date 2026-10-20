#!/usr/bin/env python3
"""Independently qualify the retained PCSX2 M13 diagnostic combat runs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build/emulator"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_event(event: str) -> str:
    """Ignore sub-decimeter float-print noise in a diagnostic hit position."""
    hit = re.fullmatch(r"\[play\] hit 1 (-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+)", event)
    if hit:
        position = tuple(f"{float(value):.1f}" for value in hit.groups())
        return "[play] hit 1 " + " ".join(position)
    return event


def run_record(name: str, expected_mode: str, sources: dict[str, str]) -> tuple[dict, list[str]]:
    run = (OUTPUT / "runs" / name).resolve()
    if not run.is_relative_to((OUTPUT / "runs").resolve()) or not run.is_dir():
        raise RuntimeError(f"invalid {expected_mode} run directory: {name}")
    result_path = run / "result.json"
    log_path = run / "emulog.txt"
    record = json.loads(result_path.read_text())
    log = log_path.read_text(errors="replace")
    if (record.get("status") != "diagnostic-completed" or
            record.get("scenario") != "bloodgulch-static" or
            record.get("variant") != "play" or record.get("mode") != expected_mode):
        raise RuntimeError(f"{expected_mode} run did not complete the play combat smoke")
    if record.get("frames", 0) < 300 or record.get("dropped") != 0:
        raise RuntimeError(f"{expected_mode} run has insufficient frames or dropped frames")
    if record.get("source_sha256") != sources:
        raise RuntimeError(f"{expected_mode} source manifest differs from the current play build")
    for source, digest in sources.items():
        if sha(ROOT / source) != digest:
            raise RuntimeError(f"source changed after the play ELF was built: {source}")
    elf = run / "boot/world.elf"
    if sha(elf) != record.get("elf_sha256"):
        raise RuntimeError(f"{expected_mode} copied ELF hash mismatch")
    bios = run / "data/PCSX2/bios/SCPH-30001.bin"
    if sha(bios) != record.get("bios_sha256"):
        raise RuntimeError(f"{expected_mode} BIOS copy hash mismatch")
    captures = [Path(path).resolve() for path in record.get("captures", [])]
    if not any(path.name == "visible-start.png" for path in captures) or not any(
            path.name == "visible-final.png" for path in captures):
        raise RuntimeError(f"{expected_mode} visible start/final captures are missing")
    for capture in captures:
        if not capture.is_relative_to(run) or not capture.is_file() or capture.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"{expected_mode} capture is missing or invalid: {capture}")
    if " OVERFLOW" in log or "[err]" in log:
        raise RuntimeError(f"{expected_mode} emulator log contains an error or overflow")
    prefix = r"^\[\s*[0-9.]+\]\s+\[play\] "
    fire = re.findall(prefix + r"fire PISTOL (\d+) pellets 1$", log, re.M)
    damage = re.findall(prefix + r"probe damage ([0-9.]+) shield ([0-9.]+) body (-?[0-9.]+) dead (\d+)$", log, re.M)
    hits = re.findall(prefix + r"hit 1 (-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+)$", log, re.M)
    if len(fire) != 6 or len(damage) != 6 or len(hits) != 6 or damage[-1][3] != "1":
        raise RuntimeError(f"{expected_mode} guest trace did not show six shots, six hits and probe death")
    if "[done] frames=301 dropped=0" not in log:
        raise RuntimeError(f"{expected_mode} guest did not report the expected bounded run completion")
    trace = []
    for line in log.splitlines():
        event = re.sub(r"^\[\s*[0-9.]+\]\s+", "", line)
        if event.startswith(("[play] fire PISTOL ", "[play] probe damage ", "[play] hit 1 ")):
            trace.append(canonical_event(event))
    evidence = {
        "run": str(run.relative_to(ROOT)), "mode": expected_mode,
        "frames": record["frames"], "dropped": record["dropped"],
        "elf_sha256": record["elf_sha256"], "bios_sha256": record["bios_sha256"],
        "settings_sha256": record["settings_sha256"],
        "combat": {"fire_events": len(fire), "hit_events": len(hits),
                   "target_damage_events": len(damage), "target_dead": True,
                   "last_shield": float(damage[-1][1]), "last_body": float(damage[-1][2]),
                   "target": "fixed diagnostic sphere, not a retail actor"},
        "captures": [str(path.relative_to(ROOT)) for path in captures],
    }
    return evidence, trace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recompiler", required=True, help="run directory name under build/emulator/runs")
    parser.add_argument("--interpreter", required=True, help="run directory name under build/emulator/runs")
    args = parser.parse_args()
    build = json.loads((ROOT / "build/world-play-elf/result.json").read_text())
    sources = build["source_sha256"]
    recompiler, recompiler_trace = run_record(args.recompiler, "recompiler", sources)
    interpreter, interpreter_trace = run_record(args.interpreter, "interpreter", sources)
    if recompiler["elf_sha256"] != interpreter["elf_sha256"]:
        raise RuntimeError("interpreter and recompiler did not execute the same ELF")
    if recompiler_trace != interpreter_trace:
        raise RuntimeError("interpreter and recompiler combat event traces differ")
    trace_bytes = ("\n".join(recompiler_trace) + "\n").encode()
    result = {
        "status": "passed",
        "scenario": "integrated EE pistol -> projectile/BSP -> diagnostic vitality target",
        "trace_sha256": hashlib.sha256(trace_bytes).hexdigest(),
        "trace_events": len(recompiler_trace),
        "modes": {"recompiler": recompiler, "interpreter": interpreter},
        "limitations": [
            "The target is a fixed diagnostic sphere, not a retail Halo actor.",
            "The target is intentionally placed before nearby BSP geometry to avoid occlusion.",
            "This does not establish all-weapon/source-parity damage or PS2 hardware performance.",
        ],
    }
    destination = OUTPUT / "combat-smoke-qualification.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(f"passed: {destination.relative_to(ROOT)} trace={result['trace_sha256']} events={len(recompiler_trace)}")


if __name__ == "__main__":
    main()
