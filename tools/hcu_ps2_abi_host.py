"""Check the PS2 port's shared record assertions with a host ILP32 compiler.

The PS2 link separately compiles the same translation unit with the R5900
toolchain. This host check uses the toolchain's freestanding headers so it
does not require host multilib libc development packages.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from build_toolchain import ROOT, environment

HCU = ROOT / "submodules/halo-ce-universal"


def main() -> None:
    _build, prefix, _env, _jobs = environment()
    host_cc = shutil.which(os.environ.get("HOST_CC", "cc"))
    target_cc = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    if not host_cc or not target_cc.is_file():
        raise RuntimeError("host cc and the installed R5900 compiler are required")

    target_sysroot = prefix / "ee/mips64r5900el-ps2-elf"
    target_internal = Path(subprocess.check_output(
        [str(target_cc), "-print-file-name=include"], text=True).strip())
    host_internal = Path(subprocess.check_output(
        [host_cc, "-print-file-name=include"], text=True).strip())
    source = HCU / "port/ps2/src/ps2_abi.c"
    include_dirs = [
        HCU / "port/ps2/include", HCU / "source", HCU / "source/cseries",
        HCU / "source/cache", HCU / "source/tag_files", HCU / "source/memory",
        HCU / "source/math", HCU / "source/rasterizer", HCU / "source/render",
        HCU / "source/game", HCU / "source/sound", HCU / "port/include",
        HCU / "port/include/xdk",
    ]
    command = [host_cc, "-m32", "-fshort-wchar", "-malign-double", "-fms-extensions",
               "-fcommon", "-D__mips__", "-D__MIPSEL__", "-D_EE", "-D__STRICT_ANSI__",
               "-nostdinc", "-isystem", str(host_internal), "-isystem",
               str(target_sysroot / "include"), "-isystem", str(target_internal)]
    for directory in include_dirs:
        command.extend(("-I", str(directory)))
    command.extend(("-include", str(HCU / "port/ps2/include/halo_ps2_prefix.h"),
                    "-fsyntax-only", str(source)))
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("host ILP32 ABI compile failed:\n" +
                           (result.stderr or result.stdout))
    target_command = [str(target_cc), "-std=gnu89", "-mabi=n32", "-fshort-wchar",
                      "-fms-extensions", "-fcommon", "-D_EE", "-D__STRICT_ANSI__",
                      "-nostdinc", "-isystem", str(target_sysroot / "include"),
                      "-isystem", str(target_internal)]
    for directory in include_dirs:
        target_command.extend(("-I", str(directory)))
    target_command.extend(("-include", str(HCU / "port/ps2/include/halo_ps2_prefix.h"),
                           "-fsyntax-only", str(source)))
    target_result = subprocess.run(target_command, cwd=ROOT, text=True,
                                   capture_output=True)
    if target_result.returncode:
        raise RuntimeError("R5900 ABI compile failed:\n" +
                           (target_result.stderr or target_result.stdout))

    # Keep a code-generation guard in addition to syntax/layout checks. A
    # non-volatile local write/read smoke can be optimized to `return 1`,
    # which compiles cleanly but proves nothing about the EE's datum accesses.
    objdump = prefix / "ee/bin/mips64r5900el-ps2-elf-objdump"
    if not objdump.is_file():
        raise RuntimeError("R5900 objdump is required to inspect ABI smoke codegen")
    compile_command = [arg for arg in target_command if arg != "-fsyntax-only"]
    with tempfile.TemporaryDirectory(prefix="hcu-ps2-abi-codegen-") as temp:
        object_file = Path(temp) / "ps2_abi.o"
        compile_command.extend(("-O2", "-c", "-o", str(object_file)))
        compile_result = subprocess.run(compile_command, cwd=ROOT, text=True,
                                        capture_output=True)
        if compile_result.returncode:
            raise RuntimeError("R5900 ABI object compile failed:\n" +
                               (compile_result.stderr or compile_result.stdout))
        disassembly = subprocess.run(
            [str(objdump), "-d", "--no-show-raw-insn", str(object_file)],
            cwd=ROOT, text=True, capture_output=True, check=True).stdout
        function = re.search(
            r"<ps2_abi_check>:(.*?)(?=\n[0-9a-fA-F]+ <[^>]+>:|\Z)",
            disassembly, re.S)
        if not function:
            raise RuntimeError("R5900 ABI smoke symbol missing from target object")
        body = function.group(1)
        required = {"sw": r"\bsw\s", "lwc1": r"\blwc1\s",
                    "comparison": r"\bbne\s|\bbc1[tf]\s"}
        missing = [name for name, pattern in required.items()
                   if not re.search(pattern, body)]
        if missing:
            raise RuntimeError("R5900 ABI smoke optimized away required accesses: " +
                               ", ".join(missing))
    print("host ILP32/R5900 ABI layouts pass; R5900 ABI smoke emits stores, "
          "loads, and comparisons")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        sys.exit(f"HCU host ABI check failed: {error}")
