"""Compile the M06 NTSC startup ELF without executing it."""
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
        run("platform-elf")
        return
    build, prefix, env, _jobs = environment()
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    reader = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    if not compiler.is_file():
        raise RuntimeError("Compiler installation is incomplete; finish make toolchain first")
    output = build / "platform-elf"
    report_path = output / "result.json"
    report = run_stages([("compile-platform-elf", ["make", "-f", "tools/ee-platform.mk",
                         f"PLATFORM_OUTPUT={output}", "all"], ROOT)], env, report_path,
                        {"compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0]})
    elf = output / "platform.elf"
    report["elf_sha256"] = hashlib.sha256(elf.read_bytes()).hexdigest()
    report["elf_header"] = subprocess.check_output([str(reader), "-h", str(elf)], text=True)
    report["status"] = "compiled"
    report["limits"] = "Compiled the NTSC startup, pad poll, GIF/VIF DMA setup, VU1 upload, and synthetic texture self-test. No PCSX2 or hardware run was observed, so M06 acceptance is not met."
    save(report_path, report)
    print(elf)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Platform ELF build failed: {error}")
