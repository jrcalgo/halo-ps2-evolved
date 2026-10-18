"""Compile the frozen integer-math closure for R5900 without executing it."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

from build_toolchain import ROOT, dependency, environment, run_stages, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--negative-control", action="store_true")
    args = parser.parse_args()
    selected = os.environ.get("BUILD_ENV", "native")
    if selected not in ("native", "container"):
        raise RuntimeError("BUILD_ENV must be native or container")
    if selected == "container":
        from container_run import run
        run("probe-negative" if args.negative_control else "probe")
        return
    build, prefix, env, _jobs = environment()
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    reader = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    if not compiler.is_file():
        raise RuntimeError("Compiler installation is incomplete; finish make toolchain first")
    item = dependency("halo-64")
    output = build / ("gameplay-ee-negative" if args.negative_control else "gameplay-ee")
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "result.json"
    source = ROOT / "submodules/halo-64/source/math/integer_math.c"
    compiled = source
    if args.negative_control:
        before = "point->x<rectangle->x1"
        text = source.read_text()
        if text.count(before) != 1:
            raise RuntimeError("The frozen negative-control boundary was not found exactly once")
        compiled = output / "integer_math_negative_control.c"
        compiled.write_text(text.replace(before, "point->x<=rectangle->x1"))
    report = run_stages([("compile-ee-probe", ["make", "-f", "tools/ee-probe.mk",
                         f"PROBE_OUTPUT={output}", f"PROBE_SOURCE={compiled}", "all"], ROOT)], env, report_path,
                        {"compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
                         "halo_64_commit": item["commit"],
                         "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    elf = output / "integer-math.elf"
    report["elf_sha256"] = hashlib.sha256(elf.read_bytes()).hexdigest()
    report["elf_header"] = subprocess.check_output([str(reader), "-h", str(elf)], text=True)
    report["status"] = "compiled"
    report["negative_control"] = args.negative_control
    report["compiled_source_sha256"] = hashlib.sha256(compiled.read_bytes()).hexdigest()
    report["source_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                               ("submodules/halo-64/source/math/integer_math.c", "tests/gameplay_host32/integer_math.c",
                                "tests/gameplay_host32/prefix.h", "src/probe/main.c", "tools/ee-probe.mk")}
    report["limits"] = "R5900 compile and link only. The fixture was not executed, so M07 acceptance is not met."
    save(report_path, report)
    print(elf)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"EE probe build failed: {error}")
