"""Run project ELFs visibly with isolated PCSX2 settings and retained evidence."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

from emulator_window import Input, capture, focus, windows

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build/emulator"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, result):
    path.write_text(json.dumps(result, indent=2) + "\n")


def prepare(config, run, mode):
    original = Path(config["bios"])
    if not original.is_file() or original.stat().st_size != 4 * 1024 * 1024:
        raise RuntimeError("The configured PS2 ROM0 is missing or has an unexpected size")
    data = run / "data/PCSX2"
    bios = data / "bios"
    bios.mkdir(parents=True)
    shutil.copy2(original, bios / "SCPH-30001.bin")
    for extension in (".nvm", ".mec", ".rom1", ".rom2"):
        source = original.with_suffix(extension)
        if source.is_file():
            shutil.copy2(source, bios / ("SCPH-30001" + extension))
    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    template = Path(config["profile"]) / "PCSX2/inis/PCSX2.ini"
    if not settings.read(template):
        raise RuntimeError("Initialize the project PCSX2 profile before running acceptance")
    for section in ("UI", "Filenames", "Folders", "Logging", "EmuCore", "EmuCore/CPU/Recompiler", "EmuCore/Speedhacks", "Pad1"):
        if not settings.has_section(section):
            settings.add_section(section)
    settings["UI"].update(SetupWizardIncomplete="false", ConfirmShutdown="false", StartPaused="false",
                          PauseOnFocusLoss="false", StartFullscreen="false", RenderToSeparateWindow="false")
    settings["Filenames"]["BIOS"] = "SCPH-30001.bin"
    settings["Folders"]["Bios"] = str(bios)
    settings["EmuCore"]["HostFs"] = "true"
    settings["Logging"].update(EnableFileLogging="true", EnableEEConsole="true", EnableIOPConsole="true")
    for key in ("EnableEE", "EnableIOP", "EnableVU0", "EnableVU1"):
        settings["EmuCore/CPU/Recompiler"][key] = "true" if mode == "recompiler" else "false"
    settings["EmuCore/Speedhacks"].update(vuThread="false", vu1Instant="false", EECycleRate="0", EECycleSkip="0")
    settings["Pad1"].update(Type="DualShock2", Start="Keyboard/Return", Cross="Keyboard/K")
    ini = data / "inis/PCSX2.ini"
    ini.parent.mkdir(parents=True)
    with ini.open("w") as handle:
        settings.write(handle)
    return ini


def stop_previous():
    active = OUTPUT / "active.json"
    if active.exists():
        record = json.loads(active.read_text())
        pid = record["pid"]
        # Only terminate a still-existing process group launched by this runner.
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"pcsx2" in cmdline and str(OUTPUT).encode() in cmdline:
                os.killpg(pid, signal.SIGTERM)
                time.sleep(0.3)
        except (ProcessLookupError, FileNotFoundError):
            pass


def validate_platform(text, seconds):
    if "HALO_PS2_FAIL" in text:
        raise RuntimeError("The guest reported a platform failure")
    if "pad_ready=1" not in text:
        raise RuntimeError("The guest did not initialize its virtual controller")
    frames = re.findall(r"HALO_PS2_FRAME frame=(\d+) elapsed_ms=(\d+) heap=(\d+) chain_high=(\d+) guards=ok", text)
    done = re.search(r"HALO_PS2_DONE duration=(\d+) frames=(\d+) pad_events=(\d+) heap=(\d+) guards=ok", text)
    if not done or int(done[1]) != seconds or len(frames) < 2:
        raise RuntimeError("Guest completion or frame progression is missing")
    if int(frames[-1][1]) < seconds * 1000 - 1100 or int(done[2]) < int(frames[-1][0]):
        raise RuntimeError("Guest completion was reported before the requested duration")
    if any(int(b[0]) <= int(a[0]) or int(b[1]) < int(a[1]) for a, b in zip(frames, frames[1:])):
        raise RuntimeError("Guest frame/time counters did not progress monotonically")
    heaps = {int(frame[2]) for frame in frames}
    heaps.add(int(done[4]))
    if len(heaps) != 1 or max(int(frame[3]) for frame in frames) > 64:
        raise RuntimeError("Guest memory or chain capacity changed unexpectedly")
    edges = [int(value) for value in re.findall(r"HALO_PS2_PAD frame=\d+ edges=(\d+)", text)]
    if not any(edge & 8 for edge in edges) or not any(edge & 0x4000 for edge in edges):
        raise RuntimeError("The scripted Start/Cross controller input was not observed")
    return {"duration": seconds, "frames": int(done[2]), "heap": next(iter(heaps)),
            "chain_high": max(int(frame[3]) for frame in frames), "pad_edges": edges, "guards": "ok"}


def run_once(config, scenario, mode, seconds, timeout):
    stop_previous()
    run = OUTPUT / "runs" / f"{scenario}-{mode}-{uuid.uuid4().hex}"
    run.mkdir(parents=True)
    ini = prepare(config, run, mode)
    elf = ROOT / ("build/platform-elf/platform.elf" if scenario == "platform" else "build/gameplay-ee/integer-math.elf")
    if not elf.is_file():
        raise RuntimeError("Build the selected ELF before launching the emulator")
    build_report = json.loads((elf.parent / "result.json").read_text())
    if build_report.get("elf_sha256") != sha(elf):
        raise RuntimeError("ELF bytes differ from the build report")
    for name, digest in build_report.get("source_sha256", {}).items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Rebuild the ELF after changing " + name)
    log = run / "emulog.txt"
    command = [config["binary"], "-datapath", str(run / "data"), "-nofullscreen", "-logfile", str(log), "-elf", str(elf)]
    if scenario == "platform":
        command += ["-gameargs", str(seconds)]
    env = {**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1", "QT_QPA_PLATFORM": "xcb", "DISPLAY": config["display"]}
    result = {"status": "running", "scenario": scenario, "mode": mode, "visible": True, "command": command,
              "parent_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "elf_sha256": sha(elf), "bios_sha256": sha(config["bios"]), "emulator_sha256": sha(Path(config["binary"]).resolve()),
              "settings_sha256": sha(ini), "run_directory": str(run), "log": str(log), "captures": []}
    result["source_sha256"] = build_report.get("source_sha256", {})
    path = run / "result.json"
    save(path, result)
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=(run / "launcher.log").open("w"),
                               stderr=subprocess.STDOUT, start_new_session=True)
    save(OUTPUT / "active.json", {"pid": process.pid, "run_directory": str(run)})
    print(f"Visible {scenario} {mode} process {process.pid}; evidence: {run}", flush=True)
    start = last_progress = time.monotonic()
    previous_size = 0
    window = None
    keyboard = Input()
    held = None
    sent = []
    last_input_attempt = start
    try:
        while time.monotonic() - start < timeout:
            if process.poll() is not None:
                raise RuntimeError(f"Emulator exited before guest completion: {process.returncode}")
            text = log.read_text(errors="replace") if log.exists() else ""
            if len(text) != previous_size:
                last_progress, previous_size = time.monotonic(), len(text)
            if "HALO_PS2_FAIL" in text:
                raise RuntimeError("Guest failure; inspect the retained log")
            if window is None:
                candidates = windows(process.pid)
                if candidates:
                    window = candidates[0][0]
                    subprocess.run(["wmctrl", "-ir", window, "-e", "0,80,80,1024,768"], check=True)
                    focus(window)
            frames = re.findall(r"HALO_PS2_FRAME frame=(\d+)", text)
            frame = int(frames[-1]) if frames else 0
            if scenario == "platform" and window:
                edges = [int(value) for value in re.findall(r"HALO_PS2_PAD frame=\d+ edges=(\d+)", text)]
                if held and any(edge & held[1] for edge in edges):
                    keyboard.key(held[0], False)
                    sent.append(held[0])
                    held = None
                if held is None and frame >= 120 and "Return" not in sent:
                    focus(window); keyboard.key("Return", True); held = ("Return", 8); last_input_attempt = time.monotonic()
                elif held is None and frame >= 240 and "K" not in sent:
                    focus(window); keyboard.key("K", True); held = ("K", 0x4000); last_input_attempt = time.monotonic()
                if held and time.monotonic() - last_input_attempt > 2:
                    # Desktop focus can change between scheduled button events.
                    # Release/repress after focusing only our owned emulator window.
                    focus(window)
                    keyboard.key(held[0], False)
                    time.sleep(.05)
                    keyboard.key(held[0], True)
                    last_input_attempt = time.monotonic()
                if time.monotonic() - start > 30 and len(sent) < 2:
                    raise RuntimeError("Controlled pad input was not acknowledged within 30 seconds")
                if frame >= 60 and not result["captures"]:
                    capture(window, run / "visible-start.png")
                    result["captures"].append(str(run / "visible-start.png"))
                    save(path, result)
            complete = "HALO_PS2_DONE" in text if scenario == "platform" else bool(re.search(r'\{"fixture":"integer_math".*"status":"passed"\}', text))
            if complete:
                if held:
                    keyboard.key(held[0], False); held = None
                if scenario == "platform":
                    if window is None or not result["captures"]:
                        raise RuntimeError("Visible platform capture is missing")
                    result["observed"] = validate_platform(text, seconds)
                    result["status"] = "passed" if seconds == 600 else "short-smoke-passed"
                else:
                    result["observed"] = {"fixture": "integer_math", "abi": "ILP32", "status": "passed"}
                    result["status"] = "executed"
                if window:
                    capture(window, run / "visible-final.png")
                    result["captures"].append(str(run / "visible-final.png"))
                result["wall_seconds"] = time.monotonic() - start
                save(path, result)
                print(f"{scenario} {mode}: {result['status']}", flush=True)
                return result
            if time.monotonic() - last_progress > 90:
                raise RuntimeError("Emulator log progress stopped for 90 seconds")
            time.sleep(0.25)
        raise RuntimeError("Emulator run exceeded the wall-time limit")
    except Exception as error:
        result["status"], result["error"] = "failed", str(error)
        save(path, result)
        raise
    finally:
        if held:
            keyboard.key(held[0], False)
        keyboard.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("platform", "probe"), default=os.environ.get("SCENARIO") or "platform")
    parser.add_argument("--mode", choices=("interpreter", "recompiler", "both"), default=os.environ.get("EMULATOR_MODE") or "both")
    parser.add_argument("--seconds", type=int, default=int(os.environ.get("SMOKE_SECONDS") or "600"))
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 600:
        raise RuntimeError("Smoke duration must be between 5 and 600 guest seconds")
    config = json.loads((ROOT / ".local/emulator.json").read_text())
    modes = ("interpreter", "recompiler") if args.mode == "both" else (args.mode,)
    results = [run_once(config, args.scenario, mode, args.seconds, args.timeout) for mode in modes]
    comparison = None
    if len(results) == 2 and args.scenario == "platform":
        a, b = [result["observed"] for result in results]
        comparison = {"same_heap": a["heap"] == b["heap"], "same_chain_high": a["chain_high"] == b["chain_high"],
                      "same_guards": a["guards"] == b["guards"], "controlled_buttons_observed": True}
        if not all(comparison.values()):
            raise RuntimeError("Interpreter/recompiler platform state differs")
    save(OUTPUT / f"{args.scenario}-latest.json", {"scenario": args.scenario, "results": results, "comparison": comparison})


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(f"Emulator validation failed: {error}")
