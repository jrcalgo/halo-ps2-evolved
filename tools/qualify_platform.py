"""Independently recheck retained M06 logs, identities and CPU configurations."""
import configparser
import json
from pathlib import Path
import sys
from test_emulator import ROOT, OUTPUT, sha, save, validate_platform


def qualify():
    aggregate = json.loads((OUTPUT / "platform-latest.json").read_text())
    results = aggregate.get("results", [])
    if len(results) != 2 or {r.get("mode") for r in results} != {"interpreter", "recompiler"}:
        raise RuntimeError("Both full CPU configurations are required")
    observed = []
    runs = []
    for result in results:
        if result.get("status") != "passed" or not result.get("visible"):
            raise RuntimeError("A full visible run did not pass")
        run = Path(result["run_directory"])
        retained = json.loads((run / "result.json").read_text())
        if retained != result:
            raise RuntimeError("Aggregate and retained run records differ")
        log = Path(result["log"])
        checks = validate_platform(log.read_text(), 600)
        if checks != result["observed"]:
            raise RuntimeError("Retained log no longer agrees with its observations")
        elf = ROOT / "build/platform-elf/platform.elf"
        if sha(elf) != result["elf_sha256"]:
            raise RuntimeError("Accepted platform ELF identity changed")
        for name, digest in result["source_sha256"].items():
            if sha(ROOT / name) != digest:
                raise RuntimeError("Accepted platform source changed: " + name)
        if sha(run / "data/PCSX2/bios/SCPH-30001.bin") != result["bios_sha256"]:
            raise RuntimeError("The isolated BIOS copy changed")
        ini = run / "data/PCSX2/inis/PCSX2.ini"
        # PCSX2 can persist harmless UI changes on shutdown. Check execution flags
        # rather than assuming its entire writable INI is immutable after launch.
        settings = configparser.ConfigParser(interpolation=None)
        settings.read(ini)
        for key in ("EnableEE", "EnableIOP", "EnableVU0", "EnableVU1"):
            if settings.getboolean("EmuCore/CPU/Recompiler", key) != (result["mode"] == "recompiler"):
                raise RuntimeError("Retained CPU configuration differs from the selected mode")
        captures = result.get("captures", [])
        if len(captures) < 2 or any(not Path(p).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for p in captures):
            raise RuntimeError("Visible start/final PNG evidence is missing")
        observed.append(checks)
        runs.append({"mode":result["mode"],"run_directory":str(run),"log_sha256":sha(log),
                     "result_sha256":sha(run/"result.json"),"capture_sha256":{Path(p).name:sha(p) for p in captures},
                     "settings_sha256_at_launch":result["settings_sha256"],"settings_sha256_now":sha(ini),
                     "observed":checks})
    for key in ("heap", "chain_high", "guards"):
        if observed[0][key] != observed[1][key]:
            raise RuntimeError("CPU configurations disagree on " + key)
    for key in ("bios_sha256", "emulator_sha256"):
        if len({r[key] for r in results}) != 1:
            raise RuntimeError("CPU configurations used different " + key)
    elf_hashes = {r["elf_sha256"] for r in results}
    if len(elf_hashes) != 1:
        raise RuntimeError("CPU configurations executed different ELFs")
    report = {"status":"passed","scenario":"M06-platform","elf_sha256":next(iter(elf_hashes)),"runs":runs,
              "validation_runner_sha256":sha(ROOT/"tools/test_emulator.py"),
              "qualifier_sha256":sha(Path(__file__)),
              "limits":"Emulator platform fixture only. Visual inspection is separate; physical PS2 and Halo gameplay acceptance remain open."}
    save(OUTPUT/"platform-qualification.json",report)
    print("M06 retained evidence qualification passed")


if __name__ == "__main__":
    try: qualify()
    except (OSError, RuntimeError, ValueError) as error: sys.exit(f"Platform qualification failed: {error}")
