"""Compile the frozen integer-math closure for R5900 without executing it."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

from build_toolchain import ROOT, environment, run_stages, save


def main():
    selected = os.environ.get("BUILD_ENV", "native")
    if selected not in ("native", "container"):
        raise RuntimeError("BUILD_ENV must be native or container")
    if selected == "container":
        from container_run import run
        run("probe")
        return
    build, prefix, env, _jobs = environment()
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    reader = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    if not compiler.is_file():
        raise RuntimeError("Compiler installation is incomplete; finish make toolchain first")
    output = build / "gameplay-ee"
    report_path = output / "result.json"
    source = ROOT / "submodules/halo-64/source/math/integer_math.c"
    report = run_stages([("compile-ee-probe", ["make", "-f", "tools/ee-probe.mk",
                         f"PROBE_OUTPUT={output}", "all"], ROOT)], env, report_path,
                        {"compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
                         "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    elf = output / "integer-math.elf"
    report["elf_sha256"] = hashlib.sha256(elf.read_bytes()).hexdigest()
    report["elf_header"] = subprocess.check_output([str(reader), "-h", str(elf)], text=True)
    report["status"] = "compiled"
    report["limits"] = "R5900 compile and link only. The fixture was not executed, so M07 acceptance is not met."
    save(report_path, report)
    print(elf)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"EE probe build failed: {error}")
