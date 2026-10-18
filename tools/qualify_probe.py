"""Independently recheck retained M07 logs, identities and CPU configurations."""
import configparser
import json
from pathlib import Path
import sys
from test_emulator import OUTPUT, ROOT, save, sha
from test_probe_emulator import datum_result, host_result
from probe_results import validate_probe


REQUIRED = {
    ("probe-negative", "interpreter"), ("probe-negative", "recompiler"),
    ("probe-assert", "interpreter"), ("probe-assert", "recompiler"),
    ("probe", "interpreter"), ("probe", "recompiler"),
    ("datum-negative", "interpreter"), ("datum-negative", "recompiler"),
    ("datum", "interpreter"), ("datum", "recompiler"),
}


def qualify():
    platform = json.loads((OUTPUT / "platform-qualification.json").read_text())
    if platform.get("status") != "passed":
        raise RuntimeError("M06 qualification is not a pass")
    if platform.get("elf_sha256") != sha(ROOT / "build/platform-elf/platform.elf"):
        raise RuntimeError("M06 qualification does not match the current platform ELF")
    aggregate = json.loads((OUTPUT / "gameplay-latest.json").read_text())
    results = aggregate.get("results", [])
    if aggregate.get("status") != "passed" or len(results) != len(REQUIRED):
        raise RuntimeError("M07 requires all ten visible fixture runs")
    if {(result.get("scenario"), result.get("mode")) for result in results} != REQUIRED:
        raise RuntimeError("M07 fixture/CPU coverage is incomplete")
    hosts = {"gameplay": host_result("gameplay"), "datum": host_result("datum")}
    runs = []
    by_case = {}
    for result in results:
        if result.get("status") != "passed" or not result.get("visible"):
            raise RuntimeError("A visible gameplay fixture did not pass")
        run = Path(result["run_directory"])
        retained = json.loads((run / "result.json").read_text())
        if retained != result:
            raise RuntimeError("Aggregate and retained probe records differ")
        kind = "datum" if result["scenario"].startswith("datum") else "gameplay"
        host = hosts[kind]
        if result.get("host_canonical") != host:
            raise RuntimeError("Recorded host canonical result no longer matches the host fixture")
        text = Path(result["log"]).read_text(errors="replace")
        observed = datum_result(text, result["scenario"], host) if kind == "datum" else validate_probe(text, result["scenario"], host)
        if observed != result["observed"]:
            raise RuntimeError("Retained probe log no longer agrees with its observations")
        command = result["command"]
        elf = Path(command[command.index("-elf") + 1])
        if sha(elf) != result["elf_sha256"]:
            raise RuntimeError("Accepted probe ELF identity changed")
        build_report = json.loads((elf.parent / "result.json").read_text())
        if build_report.get("elf_sha256") != result["elf_sha256"]:
            raise RuntimeError("Probe ELF does not match its build report")
        for name, digest in result["source_sha256"].items():
            if sha(ROOT / name) != digest:
                raise RuntimeError("Accepted probe source changed: " + name)
        if sha(run / "data/PCSX2/bios/SCPH-30001.bin") != result["bios_sha256"]:
            raise RuntimeError("The isolated BIOS copy changed")
        ini = run / "data/PCSX2/inis/PCSX2.ini"
        settings = configparser.ConfigParser(interpolation=None)
        settings.read(ini)
        for key in ("EnableEE", "EnableIOP", "EnableVU0", "EnableVU1"):
            if settings.getboolean("EmuCore/CPU/Recompiler", key) != (result["mode"] == "recompiler"):
                raise RuntimeError("Retained CPU configuration differs from the selected mode")
        captures = result.get("captures", [])
        if not captures or any(not Path(path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in captures):
            raise RuntimeError("Visible probe PNG evidence is missing")
        by_case.setdefault(result["scenario"], []).append(result)
        runs.append({"scenario": result["scenario"], "mode": result["mode"], "run_directory": str(run),
                     "elf_sha256": result["elf_sha256"], "log_sha256": sha(result["log"]),
                     "capture_sha256": {Path(path).name: sha(path) for path in captures},
                     "observed": observed, "parent_commit": result["parent_commit"]})
    for scenario, pair in by_case.items():
        if {item["mode"] for item in pair} != {"interpreter", "recompiler"}:
            raise RuntimeError(scenario + " did not run in both CPU configurations")
        if len({item["elf_sha256"] for item in pair}) != 1 or pair[0]["observed"] != pair[1]["observed"]:
            raise RuntimeError(scenario + " disagrees across CPU configurations")
        if len({item["bios_sha256"] for item in pair}) != 1 or len({item["emulator_sha256"] for item in pair}) != 1:
            raise RuntimeError(scenario + " used different BIOS or emulator bytes")
    if len({item["parent_commit"] for item in results}) != 1:
        raise RuntimeError("Probe runs were not all taken from the same parent commit")
    report = {"status": "passed", "scenario": "M07-gameplay-probe", "parent_commit": results[0]["parent_commit"],
              "host_canonical": hosts, "runs": runs,
              "validation_runner_sha256": sha(ROOT / "tools/test_probe_emulator.py"),
              "qualifier_sha256": sha(Path(__file__)),
              "limits": "Integer-math and bounded datum-pool fixtures only. ceiling_log2(1) was not executed. This is not floating-point equivalence, object lifecycle, or gameplay integration."}
    save(OUTPUT / "gameplay-qualification.json", report)
    print("M07 retained evidence qualification passed")


if __name__ == "__main__":
    try:
        qualify()
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        sys.exit(f"Probe qualification failed: {error}")
