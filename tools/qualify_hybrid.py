"""Independently recheck retained M08 hybrid logs, identities and CPU configurations."""
import configparser
import json
from pathlib import Path
import sys
from test_emulator import OUTPUT, ROOT, save, sha
from test_hybrid_emulator import host_canonical, observe


def newest(mode, elf_sha):
    found = None
    for path in (OUTPUT / "runs").glob(f"hybrid-{mode}-*/result.json"):
        result = json.loads(path.read_text())
        if result.get("status") != "passed" or result.get("mode") != mode or result.get("elf_sha256") != elf_sha:
            continue
        if found is None or path.stat().st_mtime > found[0].stat().st_mtime:
            found = (path, result)
    if found is None:
        raise RuntimeError("No passing hybrid " + mode + " run matches the current ELF")
    return found[1]


def qualify():
    host = host_canonical()
    elf = ROOT / "build/hybrid-elf/hybrid.elf"
    elf_sha = sha(elf)
    results = [newest(mode, elf_sha) for mode in ("interpreter", "recompiler")]
    runs = []
    observed = []
    for result in results:
        if not result.get("visible"):
            raise RuntimeError("Hybrid run was not visible")
        run = Path(result["run_directory"])
        retained = json.loads((run / "result.json").read_text())
        if retained != result:
            raise RuntimeError("Aggregate and retained hybrid records differ")
        text = Path(result["log"]).read_text(errors="replace")
        checks = observe(text, host)
        if checks != result["observed"]:
            raise RuntimeError("Retained hybrid log no longer agrees with its observations")
        for name, digest in result["source_sha256"].items():
            if sha(ROOT / name) != digest:
                raise RuntimeError("Accepted hybrid source changed: " + name)
        if sha(run / "data/PCSX2/bios/SCPH-30001.bin") != result["bios_sha256"]:
            raise RuntimeError("The isolated BIOS copy changed")
        settings = configparser.ConfigParser(interpolation=None)
        settings.read(run / "data/PCSX2/inis/PCSX2.ini")
        for key in ("EnableEE", "EnableIOP", "EnableVU0", "EnableVU1"):
            if settings.getboolean("EmuCore/CPU/Recompiler", key) != (result["mode"] == "recompiler"):
                raise RuntimeError("Retained CPU configuration differs from the selected mode")
        captures = result.get("captures", [])
        if len(captures) < 3 or any(not Path(path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in captures):
            raise RuntimeError("Visible hybrid PNG evidence is missing")
        observed.append(checks)
        runs.append({"mode": result["mode"], "run_directory": str(run), "elf_sha256": result["elf_sha256"],
                     "log_sha256": sha(result["log"]), "capture_sha256": {Path(path).name: sha(path) for path in captures},
                     "observed": checks, "parent_commit": result["parent_commit"]})
    if observed[0] != observed[1]:
        raise RuntimeError("CPU configurations disagree on the hybrid result")
    report = {"status": "passed", "scenario": "M08-hybrid", "elf_sha256": elf_sha, "host_canonical": host, "runs": runs,
              "validation_runner_sha256": sha(ROOT / "tools/test_hybrid_emulator.py"),
              "qualifier_sha256": sha(Path(__file__)),
              "limits": "Synthetic object driven by original datum and integer point operations. Not a Halo player, weapon, or retail scene. Emulator guest time is not physical-console performance."}
    save(OUTPUT / "hybrid-qualification.json", report)
    print("M08 retained evidence qualification passed")


if __name__ == "__main__":
    try:
        qualify()
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        sys.exit(f"Hybrid qualification failed: {error}")
