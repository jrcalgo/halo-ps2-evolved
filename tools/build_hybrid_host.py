"""Prepare M08's bounded synthetic replay on the ILP32 host; no EE acceptance."""
import hashlib
import os
import subprocess
import sys
from build_toolchain import ROOT, dependency, run_stages, save
from host_abi32 import flags


def main():
    dependency("halo-64")
    output = ROOT / "build/hybrid-host32"
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "submodules/halo-64/source"
    base = ["gcc", *flags(), "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-multichar", "-fno-strict-aliasing",
            "-include", str(ROOT / "tests/gameplay_host32/datum_prefix.h"), f"-I{ROOT}/src",
            *[f"-I{source / name}" for name in ("cseries", "memory", "tag_files", "math")]]
    binary = output / "hybrid"
    stages = [("compile-probe-boundary", [*base, "-Dmain=unused_datum_fixture", "-c", "tests/gameplay_host32/datum.c", "-o", str(output / "boundary.o")], ROOT),
              ("compile-host-hybrid", [*base, str(source / "memory/data.c"), str(source / "math/integer_math.c"), "src/hybrid/core.c",
                                      "tests/gameplay_host32/hybrid.c", str(output / "boundary.o"), "-o", str(binary)], ROOT),
              ("execute-replays", [str(binary)], ROOT)]
    report = run_stages(stages, dict(os.environ), output / "result.json", {}, timeout=15)
    sources = ["src/hybrid/protocol.h", "src/hybrid/core.c", "tests/gameplay_host32/hybrid.c", "tests/gameplay_host32/datum.c",
               "tests/gameplay_host32/datum_prefix.h", "tests/gameplay_host32/prefix.h",
               "submodules/halo-64/source/memory/data.c", "submodules/halo-64/source/math/integer_math.c"]
    report.update(status="passed", binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
                  limits="Host-only synthetic replay using original datum/point operations. Probe boundary is temporarily reused; no EE rendering, scheduler timing or M08 completion.")
    save(output / "result.json", report)
    print(binary)


if __name__ == "__main__":
    try: main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error: sys.exit(f"Hybrid host preparation failed: {error}")
