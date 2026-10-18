"""Compile the M08 hybrid ELF. Compilation does not pass the visible acceptance gate."""
import hashlib
import os
import subprocess
import sys

from build_toolchain import ROOT, dependency, environment, run_stages, save


def main():
    selected = os.environ.get("BUILD_ENV", "native")
    if selected not in ("native", "container"):
        raise RuntimeError("BUILD_ENV must be native or container")
    if selected == "container":
        from container_run import run
        run("hybrid-elf")
        return
    dependency("halo-64")
    build, prefix, env, _jobs = environment()
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    reader = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    if not compiler.is_file():
        raise RuntimeError("Compiler installation is incomplete; finish make toolchain first")
    output = build / "hybrid-elf"
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "result.json"
    report = run_stages([("compile-hybrid-elf", ["make", "-f", "tools/ee-hybrid.mk",
                         f"HYBRID_OUTPUT={output}", "all"], ROOT)], env, report_path,
                        {"compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
                         "halo_64_commit": dependency("halo-64")["commit"]})
    elf = output / "hybrid.elf"
    sources = ["src/hybrid/boundary.h", "src/hybrid/boundary.c", "src/hybrid/protocol.h", "src/hybrid/core.c",
               "src/hybrid/replay.h", "src/hybrid/replay.c", "src/hybrid/ee_main.c", "src/platform/triangle.vsm",
               "tools/ee-hybrid.mk", "submodules/halo-64/source/memory/data.c",
               "submodules/halo-64/source/math/integer_math.c",
               "submodules/halo-ps2/engine/src/platform/video.c",
               "submodules/halo-ps2/engine/src/render/chain.c",
               "submodules/halo-ps2/engine/src/render/upload.c"]
    report.update(status="compiled", elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
                  elf_header=subprocess.check_output([str(reader), "-h", str(elf)], text=True),
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
                  limits="Compiled the hybrid ELF. Visible EE acceptance is separate and is not established by this build.")
    save(report_path, report)
    print(elf)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Hybrid ELF build failed: {error}")
