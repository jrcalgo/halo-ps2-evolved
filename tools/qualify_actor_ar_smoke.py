#!/usr/bin/env python3
"""Qualify matching PCSX2 sustained assault-rifle live-biped runs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "build/emulator/runs"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_run(name: str, mode: str, sources: dict[str, str]):
    run = (RUNS / name).resolve()
    if not run.is_relative_to(RUNS.resolve()) or not run.is_dir():
        raise RuntimeError(f"invalid {mode} run directory: {name}")
    record = json.loads((run / "result.json").read_text())
    log = (run / "emulog.txt").read_text(errors="replace")
    if (record.get("status") != "diagnostic-completed" or record.get("scenario") != "bloodgulch-static" or
            record.get("variant") != "play" or record.get("mode") != mode or
            record.get("frames", 0) < 300 or record.get("dropped") != 0):
        raise RuntimeError(f"{mode} run did not complete 300 frames without drops")
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
        if (capture is None or not capture.is_relative_to(run) or not capture.is_file() or
                capture.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"{mode} missing valid {expected}")
    if " OVERFLOW" in log or "[err]" in log or "[done] frames=301 dropped=0" not in log:
        raise RuntimeError(f"{mode} emulator log has an error or incomplete frame count")

    smoke = record.get("actor_ar_smoke", {})
    ticks = smoke.get("simulation_ticks", [])
    ammo = smoke.get("magazine_loaded_after_each_shot", [])
    actor = smoke.get("live_actor", {})
    if (smoke.get("weapon") != "ASSAULT RIFLE" or smoke.get("target_dead") is not True or
            len(ticks) < 45 or len(ammo) != len(ticks) or ticks[-1] - ticks[0] < 90 or
            any(b - a != 2 for a, b in zip(ticks, ticks[1:])) or
            any(b != a - 1 for a, b in zip(ammo, ammo[1:])) or
            actor.get("model_tag") != 0xE20B0097 or actor.get("node_count") != 19):
        raise RuntimeError(f"{mode} did not meet cadence/ammo/live-target requirements")
    prefix = r"^\[\s*[0-9.]+\]\s+"
    events = []
    for line in log.splitlines():
        event = re.sub(prefix, "", line)
        if event.startswith(("[play] live-actor ", "[play] fire ASSAULT RIFLE ",
                             "[play] actor damage ", "[play] hit 1 ")):
            events.append(event)
    fire_events = [event for event in events if event.startswith("[play] fire ASSAULT RIFLE ")]
    damage_events = [event for event in events if event.startswith("[play] actor damage ")]
    if (len(fire_events) != len(ticks) or
            not re.search(r"\[play\] actor damage .* region 0 .* resistance 1 .* dead 1", log)):
        raise RuntimeError(f"{mode} logged trace disagrees with run manifest or did not kill target")
    # Desktop key-up is asynchronous to the EE tick. Compare the exact common
    # 96-tick held-input interval and exclude only a trailing shot observed
    # after that release threshold; keep its existence/count in the run record.
    normalized_events = []
    first_tick = ticks[0]
    for event in events:
        if event.startswith("[play] fire ASSAULT RIFLE "):
            match = re.search(r" tick (\d+)", event)
            relative_tick = int(match.group(1)) - first_tick
            if relative_tick > 96:
                break
            event = re.sub(r" tick \d+", f" tick {relative_tick}", event)
        normalized_events.append(event)
    return {
        "run": str(run.relative_to(ROOT)), "mode": mode,
        "frames": record["frames"], "dropped": record["dropped"],
        "elf_sha256": record["elf_sha256"], "live_actor": actor,
        "projectiles": len(fire_events), "first_tick": ticks[0], "last_tick": ticks[-1],
        "magazine_start": ammo[0], "magazine_end": ammo[-1],
        "damage_events": len(damage_events), "qualified_trace_events": len(normalized_events),
        "last_actor_hit": smoke["last_actor_hit"],
        "captures": [str(path.relative_to(ROOT)) for path in captures],
    }, normalized_events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recompiler", required=True)
    parser.add_argument("--interpreter", required=True)
    args = parser.parse_args()
    sources = json.loads((ROOT / "build/world-play-elf/result.json").read_text())["source_sha256"]
    rec, rec_events = read_run(args.recompiler, "recompiler", sources)
    interp, interp_events = read_run(args.interpreter, "interpreter", sources)
    if rec["elf_sha256"] != interp["elf_sha256"]:
        raise RuntimeError("CPU modes did not execute the same ELF")
    if rec_events != interp_events:
        raise RuntimeError("interpreter and recompiler assault-rifle traces differ")
    digest = hashlib.sha256(("\n".join(rec_events) + "\n").encode()).hexdigest()
    result = {
        "status": "passed",
        "scenario": "sustained retail assault rifle -> live biped ACOL collision -> cyborg-tagged vitality",
        "trace_sha256": digest, "trace_events": len(rec_events),
        "modes": {"recompiler": rec, "interpreter": interp},
        "limitations": [
            "The target is one chiefcam-spawned diagnostic player biped, not an AI encounter or general actor registry.",
            "Desktop-trigger release is asynchronous; cross-mode comparison normalizes to the common first 96 held-input ticks and excludes only any trailing post-threshold shot.",
            "This does not establish reload behavior, effects/audio, render-schedule replay, or physical-PS2 resource budgets.",
        ],
    }
    output = ROOT / "build/emulator/actor-ar-smoke-qualification.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"passed: {output.relative_to(ROOT)} trace={digest} events={len(rec_events)}")


if __name__ == "__main__":
    main()
