"""Compile the pinned PS2-native static-world viewer, without runtime claims."""
import hashlib
import os
import subprocess
import sys
from build_toolchain import ROOT, dependency, environment, run_stages, save


def main():
    selected = os.environ.get("BUILD_ENV", "native")
    if selected == "container":
        from container_run import run
        run("world-elf")
        return
    if selected != "native":
        raise RuntimeError("BUILD_ENV must be native or container")
    dependency("halo-ps2")
    build, prefix, env, _jobs = environment()
    output = build / "world-elf"
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    report = run_stages([("compile-world-viewer", ["make", "-f", "tools/ee-world.mk", f"WORLD_OUTPUT={output}", "all"], ROOT)], env,
                        output / "result.json", {"compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0]})
    elf = output / "world.elf"
    report["status"] = "compiled"
    report["elf_sha256"] = hashlib.sha256(elf.read_bytes()).hexdigest()
    sources = [ROOT / "tools/ee-world.mk", ROOT / "src/world/visibility.c", *sorted((ROOT / "submodules/halo-ps2/engine/src").rglob("*.c")),
               *sorted((ROOT / "submodules/halo-ps2/engine/src").rglob("*.h")),
               *sorted((ROOT / "submodules/halo-ps2/engine/src").rglob("*.vsm"))]
    report["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report["limits"] = "Static-world viewer compilation only. No retail data or gameplay is linked into this ELF. M10 runtime gates remain unmet."
    save(output / "result.json", report)
    print(elf)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"World build failed: {error}")
