#!/usr/bin/env python3
"""Independently qualify matching PCSX2 live-biped actor-ray smoke runs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "build/emulator/runs"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_record(name: str, expected_mode: str, sources: dict[str, str]):
    run = (RUNS / name).resolve()
    if not run.is_relative_to(RUNS.resolve()) or not run.is_dir():
        raise RuntimeError(f"invalid {expected_mode} run directory: {name}")
    record = json.loads((run / "result.json").read_text())
    log = (run / "emulog.txt").read_text(errors="replace")
    if (record.get("status") != "diagnostic-completed" or
            record.get("scenario") != "bloodgulch-static" or
            record.get("variant") != "play" or record.get("mode") != expected_mode):
        raise RuntimeError(f"{expected_mode} run did not complete the live-biped play smoke")
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
    captures = [Path(path).resolve() for path in record.get("captures", [])]
    if not all(any(path.name == expected for path in captures)
               for expected in ("visible-start.png", "visible-final.png")):
        raise RuntimeError(f"{expected_mode} visible start/final captures are missing")
    for capture in captures:
        if not capture.is_relative_to(run) or not capture.is_file() or capture.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"{expected_mode} capture is missing or invalid: {capture}")
    if " OVERFLOW" in log or "[err]" in log or "[done] frames=301 dropped=0" not in log:
        raise RuntimeError(f"{expected_mode} emulator log has an error or incomplete frame run")

    actor = record.get("actor_ray_smoke", {})
    if actor.get("pellets") != 15 or actor.get("actor_damage_events", 0) <= 0:
        raise RuntimeError(f"{expected_mode} actor-ray smoke did not damage its live biped")
    outcomes = actor.get("pellet_outcomes", {})
    if (outcomes.get("calls") != 15 or outcomes.get("resolved") != 15 or
            outcomes.get("still_flying") != 0 or
            outcomes.get("actor_damage_hits", 0) + outcomes.get("bsp_surface_hits", 0) != 15 or
            outcomes.get("actor_damage_hits") != actor.get("actor_damage_events")):
        raise RuntimeError(f"{expected_mode} did not account for all 15 pellet collision/damage outcomes")
    identity = actor.get("live_actor", {})
    if identity.get("node_count") != 19 or identity.get("model_tag") != 0xE20B0097:
        raise RuntimeError(f"{expected_mode} live target is not the compatible cyborg biped")
    costs = [row for row in actor.get("shot_tick_cost_windows", []) if row.get("samples")]
    if not costs or max(row.get("max_calls_per_tick", 0) for row in costs) < 15:
        raise RuntimeError(f"{expected_mode} run did not exercise 15 pellets in one tick")

    prefix = r"^\[\s*[0-9.]+\]\s+"
    events = []
    first_fire_tick = None
    for line in log.splitlines():
        event = re.sub(prefix, "", line)
        if event.startswith(("[play] live-actor ", "[play] fire SHOTGUN ",
                             "[play] actor damage ", "[play] pellet-result ", "[play] hit 15 ")):
            if event.startswith("[play] fire SHOTGUN "):
                match = re.search(r" tick (\d+)", event)
                if first_fire_tick is None:
                    first_fire_tick = int(match.group(1))
                event = re.sub(r" tick (\d+)",
                    f" tick {int(match.group(1)) - first_fire_tick}", event)
            elif event.startswith("[play] pellet-result "):
                match = re.search(r"tick (\d+)", event)
                relative = int(match.group(1)) - first_fire_tick
                event = re.sub(r"tick \d+", f"tick {relative}", event)
            events.append(event)
    damage_events = [event for event in events if event.startswith("[play] actor damage ")]
    if len(damage_events) != actor["actor_damage_events"]:
        raise RuntimeError(f"{expected_mode} damage event count does not match its result manifest")
    evidence = {
        "run": str(run.relative_to(ROOT)), "mode": expected_mode,
        "frames": record["frames"], "dropped": record["dropped"],
        "elf_sha256": record["elf_sha256"], "bios_sha256": record.get("bios_sha256"),
        "settings_sha256": record.get("settings_sha256"),
        "live_actor": identity, "pellets": actor["pellets"], "pellet_outcomes": outcomes,
        "damage_events": len(damage_events), "last_actor_hit": actor.get("last_actor_hit"),
        "shot_tick_cost_windows": costs,
        "captures": [str(path.relative_to(ROOT)) for path in captures],
    }
    return evidence, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recompiler", required=True, help="run directory name under build/emulator/runs")
    parser.add_argument("--interpreter", required=True, help="run directory name under build/emulator/runs")
    args = parser.parse_args()
    build = json.loads((ROOT / "build/world-play-elf/result.json").read_text())
    sources = build["source_sha256"]
    recompiler, recompiler_events = run_record(args.recompiler, "recompiler", sources)
    interpreter, interpreter_events = run_record(args.interpreter, "interpreter", sources)
    if recompiler["elf_sha256"] != interpreter["elf_sha256"]:
        raise RuntimeError("interpreter and recompiler did not execute the same ELF")
    if recompiler_events != interpreter_events:
        raise RuntimeError("interpreter and recompiler live-actor damage traces differ")
    trace = ("\n".join(recompiler_events) + "\n").encode()
    result = {
        "status": "passed",
        "scenario": "EE shotgun -> all 15 live-biped/BSP collision outcomes -> tag-profiled vitality",
        "trace_sha256": hashlib.sha256(trace).hexdigest(),
        "trace_events": len(recompiler_events),
        "modes": {"recompiler": recompiler, "interpreter": interpreter},
        "limitations": [
            "The test target is a diagnostic chiefcam-spawned player biped, not an AI or ordinary placed encounter actor.",
            "Only one cyborg-compatible actor is enumerated; actor selection, ownership, moving-target replay and multiplayer remain incomplete.",
            "PCSX2 cycle timing is not a physical PS2 performance measurement.",
        ],
    }
    destination = ROOT / "build/emulator/actor-ray-smoke-qualification.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(f"passed: {destination.relative_to(ROOT)} trace={result['trace_sha256']} events={len(recompiler_events)}")


if __name__ == "__main__":
    main()
