#!/usr/bin/env python3
"""Qualify matching PCSX2 live-biped retail-pistol smoke runs."""
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
    if (record.get("status") != "diagnostic-completed" or
            record.get("scenario") != "bloodgulch-static" or
            record.get("variant") != "play" or record.get("mode") != mode):
        raise RuntimeError(f"{mode} run did not complete the live-biped pistol smoke")
    if record.get("frames", 0) < 300 or record.get("dropped") != 0:
        raise RuntimeError(f"{mode} run has insufficient frames or dropped frames")
    if record.get("source_sha256") != sources:
        raise RuntimeError(f"{mode} source manifest differs from the current play build")
    for source, digest in sources.items():
        if sha(ROOT / source) != digest:
            raise RuntimeError(f"source changed after the play ELF was built: {source}")
    if sha(run / "boot/world.elf") != record.get("elf_sha256"):
        raise RuntimeError(f"{mode} copied ELF hash mismatch")
    captures = [Path(path).resolve() for path in record.get("captures", [])]
    for name in ("visible-start.png", "visible-final.png"):
        capture = next((item for item in captures if item.name == name), None)
        if (capture is None or not capture.is_relative_to(run) or not capture.is_file() or
                capture.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"{mode} visible capture is missing or invalid: {name}")
    if " OVERFLOW" in log or "[err]" in log or "[done] frames=301 dropped=0" not in log:
        raise RuntimeError(f"{mode} emulator log has an error or incomplete frame run")

    smoke = record.get("actor_pistol_smoke", {})
    actor = smoke.get("live_actor", {})
    if (smoke.get("weapon") != "PISTOL" or smoke.get("target_dead") is not True or
            smoke.get("fire_events", 0) < 5 or smoke.get("actor_damage_events", 0) < 5 or
            actor.get("node_count") != 19 or actor.get("model_tag") != 0xE20B0097):
        raise RuntimeError(f"{mode} run did not kill the compatible live biped with pistol damage")
    prefix = r"^\[\s*[0-9.]+\]\s+"
    events = []
    for line in log.splitlines():
        event = re.sub(prefix, "", line)
        if event.startswith(("[play] live-actor ", "[play] fire PISTOL ",
                             "[play] actor damage ", "[play] hit 1 ")):
            events.append(event)
    damage = [event for event in events if event.startswith("[play] actor damage ")]
    if (len(damage) != smoke["actor_damage_events"] or
            not re.search(r"\[play\] actor damage .* region 0 .* resistance 0 .* dead 1", log)):
        raise RuntimeError(f"{mode} pistol actor trace is inconsistent with its manifest")
    return {
        "run": str(run.relative_to(ROOT)), "mode": mode,
        "frames": record["frames"], "dropped": record["dropped"],
        "elf_sha256": record["elf_sha256"], "live_actor": actor,
        "fire_events": smoke["fire_events"], "damage_events": len(damage),
        "last_actor_hit": smoke["last_actor_hit"], "captures": [str(p.relative_to(ROOT)) for p in captures],
    }, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recompiler", required=True)
    parser.add_argument("--interpreter", required=True)
    args = parser.parse_args()
    build = json.loads((ROOT / "build/world-play-elf/result.json").read_text())
    sources = build["source_sha256"]
    rec, rec_events = read_run(args.recompiler, "recompiler", sources)
    interp, interp_events = read_run(args.interpreter, "interpreter", sources)
    if rec["elf_sha256"] != interp["elf_sha256"]:
        raise RuntimeError("CPU modes did not execute the same ELF")
    if rec_events != interp_events:
        raise RuntimeError("interpreter and recompiler live-pistol traces differ")
    trace = ("\n".join(rec_events) + "\n").encode()
    result = {
        "status": "passed",
        "scenario": "retail pistol -> live spawned player-biped ACOL pose -> cyborg-tagged vitality",
        "trace_sha256": hashlib.sha256(trace).hexdigest(),
        "trace_events": len(rec_events),
        "modes": {"recompiler": rec, "interpreter": interp},
        "limitations": [
            "The target is one diagnostic chiefcam-spawned player biped, not an AI encounter or general actor registry.",
            "This smoke does not establish actor effects/audio, render-schedule replay, or physical-PS2 CPU and RAM budgets.",
        ],
    }
    destination = ROOT / "build/emulator/actor-pistol-smoke-qualification.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(f"passed: {destination.relative_to(ROOT)} trace={result['trace_sha256']} events={len(rec_events)}")


if __name__ == "__main__":
    main()
