"""Compile original integer_math.c against a narrow ILP32 host boundary."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

from build_toolchain import ROOT, dependency, run_stages, save
from host_abi32 import flags, sysroot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()
    if os.environ.get("BUILD_ENV", "native") != "native":
        raise RuntimeError("The ILP32 gameplay fixture currently supports native host execution only")
    if not (sysroot() / "usr/lib32/ld-linux.so.2").is_file():
        raise RuntimeError("Prepare the workspace-local 32-bit host runtime first")
    item = dependency("halo-64")
    source = ROOT / "submodules/halo-64/source"
    fixture = ROOT / "tests/gameplay_host32"
    output = Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build")).resolve() / "gameplay-host32"
    output.mkdir(parents=True, exist_ok=True)
    binary = output / "integer-math"
    original = source / "math/integer_math.c"
    command = ["gcc", *flags(), "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-fno-strict-aliasing",
               "-include", str(fixture / "prefix.h"), "-I" + str(source / "cseries"), "-I" + str(source / "math"),
               str(original), str(fixture / "integer_math.c"), "-o", str(binary)]
    stages = [("compile-original-integer-math", command, ROOT)]
    if not args.compile_only:
        stages.append(("run-integer-math-ilp32", [str(binary)], ROOT))
        # A generated fault proves the right-edge fixture can reject wrong behavior.
        mutated = output / "integer_math_negative_control.c"
        text = original.read_text()
        before = "point->x<rectangle->x1"
        if text.count(before) != 1:
            raise RuntimeError("Negative control no longer matches the audited source")
        mutated.write_text(text.replace(before, "point->x<=rectangle->x1"))
        negative_binary = output / "integer-math-negative-control"
        negative_command = [str(mutated) if value == str(original) else str(negative_binary) if value == str(binary) else value for value in command]
        stages.append(("compile-negative-control", negative_command, ROOT))
        check = ('import subprocess,sys; r=subprocess.run([sys.argv[1]],capture_output=True,text=True,timeout=10); '
                 'assert r.returncode==1 and "!point2d_in_rectangle2d" in r.stderr, (r.returncode,r.stdout,r.stderr); '
                 'print("Negative control rejected at rectangle boundary check")')
        stages.append(("reject-negative-control", [sys.executable, "-c", check, str(negative_binary)], ROOT))
    report_path = output / "result.json"
    report = run_stages(stages, dict(os.environ), report_path,
                        {"halo_64_commit": item["commit"], "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest()}, timeout=15)
    report["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    report["status"] = "compiled" if args.compile_only else "passed"
    report["limits"] = "Whole original integer math module on an ILP32 Linux host only; no R5900/gameplay integration or M07 acceptance."
    report["negative_control"] = "not executed" if args.compile_only else "inclusive right-edge mutation rejected by the fixture"
    save(report_path, report)
    print(report["status"] + ": " + report["limits"])


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(f"Host gameplay fixture failed: {error}")
