"""Visibly run the M08 hybrid proof for the full 18,000-tick smoke in both CPU modes."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from test_emulator import OUTPUT, ROOT, prepare, save, sha, stop_previous
from emulator_window import capture, focus, windows


def host_canonical():
    report = json.loads((ROOT / "build/hybrid-host32/result.json").read_text())
    if report.get("status") != "passed":
        raise RuntimeError("The host hybrid replay has not passed")
    for name, digest in report["source_sha256"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Rerun the host hybrid replay after changing " + name)
    canonical = report["canonical"]
    if canonical.get("event_hash") != 1235839601 or canonical.get("ticks") != 18000 or not canonical.get("presentation_independent"):
        raise RuntimeError("Host hybrid canonical result is not the expected replay")
    return canonical


def require_probe():
    qualification = json.loads((OUTPUT / "gameplay-qualification.json").read_text())
    if qualification.get("status") != "passed":
        raise RuntimeError("M07 qualification has not passed")


def observe(text, host):
    if "HALO_PS2_FAIL" in text:
        raise RuntimeError("Hybrid guest reported failure")
    schedules = dict(re.findall(r"HALO_PS2_HYBRID schedule=([a-z]+) event_hash=(\d+) ticks=18000 created=30 destroyed=30 rejected=30", text))
    if set(schedules) != {"suppressed", "delayed", "normal"}:
        raise RuntimeError("Three presentation schedules did not complete")
    if len(set(schedules.values())) != 1 or int(schedules["normal"]) != host["event_hash"]:
        raise RuntimeError("EE schedules disagree with each other or with the host hash")
    done = re.search(r"HALO_PS2_HYBRID outcome=passed elapsed_ms=(\d+) heap=(\d+) chain_high=(\d+) guards=ok", text)
    fixture = re.search(r'\{"fixture":"hybrid","ticks":18000,"created":30,"destroyed":30,"stale_rejected":30,"event_hash":(\d+),"presentation_independent":true,"elapsed_ms":(\d+),"status":"passed"\}', text)
    if not done or not fixture or int(done[1]) < 600000 or int(fixture[1]) != host["event_hash"] or int(fixture[2]) != int(done[1]):
        raise RuntimeError("Hybrid smoke duration or canonical fixture is missing")
    frames = [(int(tick), int(x)) for tick, x in re.findall(r"HALO_PS2_HYBRID_FRAME tick=(\d+) x=(-?\d+)", text)]
    if len(frames) < 2 or frames[0][0] > 1 or frames[-1][0] < 18000 or frames[0][1] == frames[min(10, len(frames) - 1)][1]:
        raise RuntimeError("Visible object motion was not recorded")
    return {"event_hash": int(schedules["normal"]), "elapsed_ms": int(done[1]), "heap": int(done[2]),
            "chain_high": int(done[3]), "frames": len(frames), "host_equal": True, "presentation_independent": True}


def run_case(config, mode, host):
    stop_previous()
    elf = ROOT / "build/hybrid-elf/hybrid.elf"
    build_report = json.loads((elf.parent / "result.json").read_text())
    if sha(elf) != build_report["elf_sha256"] or build_report.get("status") != "compiled":
        raise RuntimeError("Rebuild the hybrid ELF before executing it")
    for name, digest in build_report["source_sha256"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Rebuild the hybrid ELF after changing " + name)
    run = OUTPUT / "runs" / f"hybrid-{mode}-{uuid.uuid4().hex}"
    run.mkdir(parents=True)
    ini = prepare(config, run, mode)
    log = run / "emulog.txt"
    command = [config["binary"], "-datapath", str(run / "data"), "-nofullscreen", "-logfile", str(log), "-elf", str(elf)]
    result = {"status": "running", "scenario": "hybrid", "mode": mode, "visible": True, "command": command,
              "elf_sha256": sha(elf), "source_sha256": build_report["source_sha256"], "settings_sha256": sha(ini),
              "bios_sha256": sha(config["bios"]), "emulator_sha256": sha(Path(config["binary"]).resolve()),
              "parent_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "run_directory": str(run), "log": str(log), "host_canonical": host, "captures": []}
    path = run / "result.json"
    save(path, result)
    env = {**os.environ, "DISPLAY": config["display"], "QT_QPA_PLATFORM": "xcb", "APPIMAGE_EXTRACT_AND_RUN": "1"}
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=(run / "launcher.log").open("w"), stderr=subprocess.STDOUT, start_new_session=True)
    save(OUTPUT / "active.json", {"pid": process.pid, "run_directory": str(run)})
    print(f"Visible hybrid {mode}; evidence: {run}", flush=True)
    start = progress = time.monotonic()
    size = 0
    window = None
    try:
        while time.monotonic() - start < 1800:
            text = log.read_text(errors="replace") if log.exists() else ""
            if len(text) != size:
                size = len(text)
                progress = time.monotonic()
            if "HALO_PS2_FAIL" in text or "hybrid check failed" in text:
                raise RuntimeError("Guest hybrid proof failed; inspect retained log")
            if window is None:
                owned = windows(process.pid)
                if owned:
                    window = owned[0][0]
                    subprocess.run(["wmctrl", "-ir", window, "-e", "0,80,80,1024,768"], check=True)
                    focus(window)
            if window and "HALO_PS2_HYBRID_FRAME" in text and not result["captures"]:
                time.sleep(0.3)
                capture(window, run / "visible-start.png")
                result["captures"].append(str(run / "visible-start.png"))
                save(path, result)
            if window and re.search(r"HALO_PS2_HYBRID_FRAME tick=300 ", text) and len(result["captures"]) == 1:
                capture(window, run / "visible-motion.png")
                result["captures"].append(str(run / "visible-motion.png"))
                save(path, result)
            if window and "HALO_PS2_HYBRID outcome=passed" in text:
                time.sleep(0.5)
                text = log.read_text(errors="replace")
                observed = observe(text, host)
                capture(window, run / "visible-final.png")
                result["captures"].append(str(run / "visible-final.png"))
                result.update(status="passed", observed=observed, wall_seconds=time.monotonic() - start)
                save(path, result)
                print(f"hybrid {mode}: passed", flush=True)
                return result
            if process.poll() is not None:
                raise RuntimeError("Emulator exited before the hybrid proof completed")
            if time.monotonic() - progress > 180:
                raise RuntimeError("Hybrid log progress stopped")
            time.sleep(0.25)
        raise RuntimeError("Hybrid proof exceeded its wall-time limit")
    except Exception as error:
        result.update(status="failed", error=str(error))
        save(path, result)
        raise


def execute(mode="both"):
    if mode not in ("both", "interpreter", "recompiler"):
        raise RuntimeError("Unknown hybrid CPU mode")
    require_probe()
    host = host_canonical()
    config = json.loads((ROOT / ".local/emulator.json").read_text())
    modes = ("interpreter", "recompiler") if mode == "both" else (mode,)
    results = [run_case(config, selected, host) for selected in modes]
    if len(results) == 2 and results[0]["observed"] != results[1]["observed"]:
        raise RuntimeError("Interpreter and recompiler hybrid observations differ")
    save(OUTPUT / "hybrid-latest.json", {"status": "passed", "results": results})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("both", "interpreter", "recompiler"), default="both")
    args = parser.parse_args()
    execute(args.mode)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyError) as error:
        sys.exit(f"Hybrid emulator validation failed: {error}")
