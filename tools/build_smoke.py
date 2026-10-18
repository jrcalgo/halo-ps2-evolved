"""Compile a minimal EE ELF and record tool/layout identities, without executing it."""
import hashlib
import os
import argparse
from pathlib import Path
import subprocess
import sys

from build_toolchain import ROOT, environment, run_stages, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vu", action="store_true", help="Assemble the existing VU1 renderer program only")
    args = parser.parse_args()
    selected = os.environ.get("BUILD_ENV", "native")
    if selected not in ("native", "container"):
        raise RuntimeError("BUILD_ENV must be native or container")
    if selected == "container":
        from container_run import run
        run("vu-smoke" if args.vu else "smoke-elf")
        return
    build, prefix, env, jobs = environment()
    if args.vu:
        assembler = prefix / "dvp/bin/dvp-as"
        if not assembler.is_file():
            raise RuntimeError("DVP assembler is unavailable")
        output = build / "vu-smoke"
        output.mkdir(parents=True, exist_ok=True)
        obj = output / "world.o"
        report_path = output / "result.json"
        report = run_stages([("assemble-vu1", [str(assembler), "src/vu1/world.vsm", "-o", str(obj)],
                             ROOT / "submodules/halo-ps2/engine")], env, report_path,
                            {"assembler": subprocess.check_output([str(assembler), "--version"], text=True).splitlines()[0]})
        report["object_sha256"] = hashlib.sha256(obj.read_bytes()).hexdigest()
        report["layout"] = subprocess.check_output([str(assembler.with_name("dvp-objdump")), "-f", str(obj)], text=True)
        report["status"] = "passed"
        report["limits"] = "VU1 assembly only; no EE integration or runtime execution observed."
        save(report_path, report)
        print(obj)
        return
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    reader = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    if not compiler.is_file() or not (prefix / "ps2sdk/samples/Makefile.eeglobal").is_file():
        raise RuntimeError("Compiler/SDK installation is incomplete; finish make toolchain first")
    output = build / "platform-smoke"
    report_path = output / "result.json"
    report = run_stages([("compile-ee-smoke", ["make", "-f", "tools/ee-smoke.mk",
                         f"SMOKE_OUTPUT={output}", "all"], ROOT)], env, report_path,
                        {"compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0]})
    elf = output / "halo-smoke.elf"
    report["elf_sha256"] = hashlib.sha256(elf.read_bytes()).hexdigest()
    report["elf_header"] = subprocess.check_output([str(reader), "-h", str(elf)], text=True)
    report["status"] = "passed"
    report["limits"] = "Compiled and inspected only; no emulator or hardware execution observed."
    save(report_path, report)
    print(elf)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"EE smoke build failed: {error}")
