"""Build the unchanged datum module and bounded ILP32 host or EE fixtures."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from build_toolchain import ROOT, dependency, environment, run_stages, save
from host_abi32 import flags

SOURCES = ["submodules/halo-64/source/memory/data.c", "submodules/halo-64/source/memory/data.h",
           "submodules/halo-64/source/tag_files/tag_files.h", "tests/gameplay_host32/prefix.h",
           "tests/gameplay_host32/datum_prefix.h", "tests/gameplay_host32/datum.c", "src/probe/datum_main.c", "tools/ee-datum.mk"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="store_true")
    parser.add_argument("--negative-control", action="store_true")
    args = parser.parse_args()
    selected = os.environ.get("BUILD_ENV", "native")
    if selected == "container" and not args.host:
        from container_run import run
        run("datum-negative" if args.negative_control else "datum-probe")
        return
    if selected != "native":
        raise RuntimeError("Unsupported build environment for this fixture")
    dependency("halo-64")
    original = ROOT / "submodules/halo-64/source/memory/data.c"
    compiled = original
    if args.negative_control:
        build_root = Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build")).resolve()
        generated = build_root / "datum-negative-source"
        generated.mkdir(parents=True, exist_ok=True)
        compiled = generated / "data.c"
        before = "identifier && header->identifier!=identifier"
        text = original.read_text()
        if text.count(before) != 1:
            raise RuntimeError("The audited stale-handle negative-control boundary changed")
        compiled.write_text(text.replace(before, "FALSE"))
    if args.host:
        output = ROOT / ("build/datum-host32-negative" if args.negative_control else "build/datum-host32")
        output.mkdir(parents=True, exist_ok=True)
        binary = output / "datum"
        source = ROOT / "submodules/halo-64/source"
        command = ["gcc", *flags(), "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-multichar", "-fno-strict-aliasing",
                   "-include", str(ROOT / "tests/gameplay_host32/datum_prefix.h"),
                   *[f"-I{source / name}" for name in ("cseries", "memory", "tag_files")],
                   str(compiled), str(ROOT / "tests/gameplay_host32/datum.c"), "-o", str(binary)]
        stages = [("compile-datum-host", command, ROOT)]
        if args.negative_control:
            check = ('import subprocess,sys; r=subprocess.run([sys.argv[1]],capture_output=True,text=True,timeout=10); '
                     'assert r.returncode==1 and "datum_try_and_get(pool, stale) == NULL" in r.stderr, (r.returncode,r.stdout,r.stderr); '
                     'print("Negative control rejected: stale identifier")')
            stages.append(("reject-datum-negative", [sys.executable, "-c", check, str(binary)], ROOT))
        else:
            stages.append(("execute-datum-host", [str(binary)], ROOT))
        report = run_stages(stages,
                            dict(os.environ), output / "result.json", {}, timeout=15)
        report["status"] = "passed"
    else:
        build, prefix, env, _jobs = environment()
        output = build / ("datum-ee-negative" if args.negative_control else "datum-ee")
        binary = output / "datum.elf"
        report = run_stages([("compile-datum-ee", ["make", "-f", "tools/ee-datum.mk", f"PROBE_OUTPUT={output}", f"PROBE_SOURCE={compiled}", "all"], ROOT)],
                            env, output / "result.json", {})
        report["status"] = "compiled"
    report["elf_sha256" if not args.host else "binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    report["source_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    report["negative_control"] = args.negative_control
    report["compiled_source_sha256"] = hashlib.sha256(compiled.read_bytes()).hexdigest()
    report["limits"] = "Bounded datum-pool fixture. This is not the complete object system or gameplay integration."
    save(output / "result.json", report)
    print(binary)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(f"Datum fixture failed: {error}")
