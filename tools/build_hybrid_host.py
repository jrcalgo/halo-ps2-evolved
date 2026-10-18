"""Prepare M08's bounded synthetic replay on the ILP32 host; no EE acceptance."""
import hashlib
import json
import os
from pathlib import Path
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
            "-include", str(ROOT / "src/hybrid/boundary.h"), f"-I{ROOT}/src",
            *[f"-I{source / name}" for name in ("cseries", "memory", "tag_files", "math")]]
    binary = output / "hybrid"
    stages = [("compile-host-hybrid", [*base, str(source / "memory/data.c"), str(source / "math/integer_math.c"),
                                      "src/hybrid/boundary.c", "src/hybrid/core.c", "src/hybrid/replay.c",
                                      "tests/gameplay_host32/hybrid.c", "-o", str(binary)], ROOT),
              ("execute-replays", [str(binary)], ROOT)]
    report = run_stages(stages, dict(os.environ), output / "result.json", {}, timeout=15)
    log = Path(report["stages"][-1]["log"]).read_text()
    canonical = json.loads(next(line for line in log.splitlines() if line.startswith('{"fixture":')))
    if canonical.get("event_hash") != 1235839601 or not canonical.get("presentation_independent"):
        raise RuntimeError("Host hybrid replay no longer matches the recorded canonical hash")
    sources = ["src/hybrid/protocol.h", "src/hybrid/boundary.h", "src/hybrid/boundary.c", "src/hybrid/core.c",
               "src/hybrid/replay.h", "src/hybrid/replay.c", "tests/gameplay_host32/hybrid.c",
               "submodules/halo-64/source/memory/data.c", "submodules/halo-64/source/math/integer_math.c"]
    report.update(status="passed", binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  canonical=canonical,
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
                  limits="Host synthetic replay using the project boundary and original datum/point operations. EE rendering is a separate gate.")
    save(output / "result.json", report)
    print(binary)


if __name__ == "__main__":
    try: main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error: sys.exit(f"Hybrid host preparation failed: {error}")
