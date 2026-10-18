"""Execute bounded gameplay fixtures and specific negative controls visibly."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from test_emulator import ROOT, OUTPUT, prepare, stop_previous, sha, save
from emulator_window import windows, focus, capture
from probe_results import validate_probe

CASES = {
    "probe-negative": ("gameplay-ee-negative/integer-math.elf", "negative"),
    "probe-assert": ("gameplay-ee/integer-math.elf", "assert"),
    "probe": ("gameplay-ee/integer-math.elf", None),
    "datum-negative": ("datum-ee-negative/datum.elf", "negative"),
    "datum": ("datum-ee/datum.elf", None),
}


def host_result(kind):
    report = json.loads((ROOT / f"build/{kind}-host32/result.json").read_text())
    if report.get("status") != "passed":
        raise RuntimeError("The matching host fixture has not passed")
    for name, digest in report.get("source_sha256", {}).items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Rerun the host fixture after changing " + name)
    binary = ROOT / ("build/gameplay-host32/integer-math" if kind == "gameplay" else "build/datum-host32/datum")
    if sha(binary) != report["binary_sha256"]:
        raise RuntimeError("Host fixture binary changed after its report")
    stages = [stage for stage in report["stages"] if stage["name"] in ("run-integer-math-ilp32", "execute-datum-host")]
    if len(stages) != 1 or stages[0].get("exit_code") != 0:
        raise RuntimeError("Host execution evidence is missing")
    text = Path(stages[0]["log"]).read_text()
    return json.loads(next(line for line in text.splitlines() if line.startswith('{"fixture":')))


def require_platform():
    qualification_path = OUTPUT / "platform-qualification.json"
    if not qualification_path.is_file():
        raise RuntimeError("M06 retained-evidence qualification has not passed")
    qualification = json.loads(qualification_path.read_text())
    if qualification.get("status") != "passed" or qualification.get("elf_sha256") != sha(ROOT / "build/platform-elf/platform.elf"):
        raise RuntimeError("M06 qualification does not match the current platform ELF")
    report = json.loads((OUTPUT / "platform-latest.json").read_text())
    results = report.get("results", [])
    if {r.get("mode") for r in results} != {"interpreter", "recompiler"} or len(results) != 2:
        raise RuntimeError("M06 requires both CPU configurations")
    if any(r.get("status") != "passed" or r.get("observed", {}).get("duration") != 600 for r in results):
        raise RuntimeError("M06 full-duration runtime gate is still open")
    if not report.get("comparison") or not all(report["comparison"].values()):
        raise RuntimeError("M06 platform state comparison has not passed")


def datum_result(text, case, host):
    if "HALO_PS2_FAIL" in text:
        raise RuntimeError("Datum guest reported failure")
    if case == "datum-negative":
        if '"status":"passed"' in text or "HALO_PS2_DATUM outcome=passed" in text:
            raise RuntimeError("Datum mutation escaped rejection")
        if "datum check failed: datum_try_and_get(pool, stale) == NULL" not in text or "HALO_PS2_DATUM negative_control=rejected" not in text:
            raise RuntimeError("Expected stale-identifier rejection is missing")
        return {"negative_control": "rejected"}
    expected = {"fixture": "datum", "abi": "ILP32", "slots": 4, "status": "passed"}
    fixtures = [json.loads(line) for line in re.findall(r'\{"fixture":"datum"[^\n]*?\}', text)]
    if fixtures != [expected] or host != expected or "HALO_PS2_DATUM outcome=passed" not in text:
        raise RuntimeError("Datum host/EE comparison or wrapper completion failed")
    return {"canonical": expected, "host_equal": True}


def run_case(config, case, mode, host):
    stop_previous()
    elf_name, argument = CASES[case]
    elf = ROOT / "build" / elf_name
    build_report = json.loads((elf.parent / "result.json").read_text())
    if sha(elf) != build_report["elf_sha256"]:
        raise RuntimeError("EE fixture changed after build")
    for name, digest in build_report["source_sha256"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Rebuild the EE fixture after changing " + name)
    run = OUTPUT / "runs" / f"{case}-{mode}-{uuid.uuid4().hex}"
    run.mkdir(parents=True)
    ini = prepare(config, run, mode)
    log = run / "emulog.txt"
    command = [config["binary"], "-datapath", str(run / "data"), "-nofullscreen", "-logfile", str(log), "-elf", str(elf)]
    if argument:
        command += ["-gameargs", argument]
    result = {"status": "running", "scenario": case, "mode": mode, "visible": True, "command": command,
              "elf_sha256": sha(elf), "source_sha256": build_report["source_sha256"], "settings_sha256": sha(ini),
              "bios_sha256": sha(config["bios"]), "emulator_sha256": sha(Path(config["binary"]).resolve()),
              "parent_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "run_directory": str(run), "log": str(log), "host_canonical": host}
    path = run / "result.json"
    save(path, result)
    env = {**os.environ, "DISPLAY": config["display"], "QT_QPA_PLATFORM": "xcb", "APPIMAGE_EXTRACT_AND_RUN": "1"}
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=(run / "launcher.log").open("w"), stderr=subprocess.STDOUT, start_new_session=True)
    save(OUTPUT / "active.json", {"pid": process.pid, "run_directory": str(run)})
    print(f"Visible {case} {mode}; evidence: {run}", flush=True)
    start = time.monotonic()
    window = None
    try:
        while time.monotonic() - start < 120:
            text = log.read_text(errors="replace") if log.exists() else ""
            if "HALO_PS2_FAIL" in text:
                raise RuntimeError("Guest fixture failed; inspect retained log")
            if window is None:
                owned = windows(process.pid)
                if owned:
                    window = owned[0][0]
                    subprocess.run(["wmctrl", "-ir", window, "-e", "0,80,80,1024,768"], check=True)
                    focus(window)
            marker = ("HALO_PS2_DATUM" if case.startswith("datum") else
                      "assertion: 0" if case == "probe-assert" else "HALO_PS2_PROBE")
            if window and marker in text:
                time.sleep(.5)
                text = log.read_text(errors="replace")
                observed = datum_result(text, case, host) if case.startswith("datum") else validate_probe(text, case, host)
                capture(window, run / "visible-final.png")
                result.update(status="passed", observed=observed, captures=[str(run / "visible-final.png")], wall_seconds=time.monotonic()-start)
                save(path, result)
                print(f"{case} {mode}: passed", flush=True)
                return result
            if process.poll() is not None:
                raise RuntimeError("Emulator exited before classified fixture completion")
            time.sleep(.25)
        raise RuntimeError("Fixture exceeded its bounded execution time")
    except Exception as error:
        result.update(status="failed", error=str(error)); save(path, result); raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["all", *CASES], default="all")
    parser.add_argument("--mode", choices=("both", "interpreter", "recompiler"), default="both")
    args = parser.parse_args()
    require_platform()
    config = json.loads((ROOT / ".local/emulator.json").read_text())
    modes = ("interpreter", "recompiler") if args.mode == "both" else (args.mode,)
    hosts = {"gameplay": host_result("gameplay"), "datum": host_result("datum")}
    results = [run_case(config, case, mode, hosts["datum" if case.startswith("datum") else "gameplay"])
               for case in (CASES if args.case == "all" else [args.case]) for mode in modes]
    save(OUTPUT / "gameplay-latest.json", {"status": "passed", "results": results})


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(f"Gameplay emulator validation failed: {error}")
