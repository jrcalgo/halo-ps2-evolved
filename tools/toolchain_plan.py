"""Read-only toolchain build preflight; no downloads, builds, or package installs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from lock_toolchain import declarations
from locked_source import source_path
from host_prerequisites import native_environment, prefix as host_prefix

ROOT = Path(__file__).resolve().parents[1]
# Conservative staging allowance, not a measured requirement or a correctness gate.
MIN_FREE_BYTES = 20 * 1024 ** 3
HOST_TOOLS = ("gcc", "g++", "make", "cmake", "git", "patch", "makeinfo", "flex", "bison", "gawk")


def preflight():
    path = ROOT / "config/toolchain-sources.json"
    lock = json.loads(path.read_text()) if path.exists() else {"sources": []}
    sources = {source["id"]: source for source in lock["sources"]}
    profile = json.loads((ROOT / "config/toolchain-profile.json").read_text())
    build_root = Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build")).resolve()
    source_root = Path(os.environ.get("HALO_TOOLCHAIN_SOURCE_ROOT", build_root / "toolchain/sources")).resolve()
    blockers = []
    for source in declarations():
        if source["id"] not in profile["required_sources"]:
            continue
        pin = sources.get(source["id"])
        if not pin or any(pin.get(key) != source[key] for key in ("url", "ref", "declared_by")):
            blockers.append("Missing or stale source identity: " + source["id"])
        else:
            try:
                source_path(source["url"], source["ref"], source_root)
            except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
                blockers.append(f"Source not acquired/verified: {source['id']}: {error}")
    host_env = native_environment()
    tools = {name: shutil.which(name, path=host_env["PATH"]) for name in HOST_TOOLS}
    missing = [name for name, executable in tools.items() if executable is None]
    if missing:
        blockers.append("Missing native tools: " + ", ".join(missing))
    existing_parent = build_root
    while not existing_parent.exists():
        existing_parent = existing_parent.parent
    free = shutil.disk_usage(existing_parent).free
    if free < MIN_FREE_BYTES:
        blockers.append("Less than the conservative 20 GiB free-space allowance for source staging and builds")
    development = {}
    if tools["gcc"]:
        include = ["-I" + str(host_prefix() / "include")] if host_prefix().is_dir() else []
        headers = subprocess.run([tools["gcc"], *include, "-x", "c", "-fsyntax-only", "-"],
                                 input="#include <gmp.h>\n#include <mpfr.h>\n#include <mpc.h>\n#include <zlib.h>\n",
                                 capture_output=True, text=True)
        development["headers_ok"] = headers.returncode == 0
        development["header_diagnostics"] = headers.stderr.strip()
        libraries = {}
        for name in ("libgmp.so", "libmpfr.so", "libmpc.so", "libz.so"):
            local = host_prefix() / "lib" / name.replace(".so", ".a")
            if local.is_file():
                libraries[name] = str(local)
                continue
            resolved = subprocess.check_output([tools["gcc"], "-print-file-name=" + name], text=True).strip()
            libraries[name] = resolved if resolved != name and Path(resolved).is_file() else None
        development["libraries"] = libraries
        if not development["headers_ok"] or not all(libraries.values()):
            blockers.append("Native GMP/MPFR/MPC/zlib development headers or linker libraries are missing")
    return {"source_identities": len(sources), "required_sources": profile["required_sources"],
            "optional_sources": profile["optional_sources"], "compiler_scripts": profile["compiler_scripts"],
            "build_root": str(build_root), "source_root": str(source_root), "host_tools": tools,
            "native_development": development,
            "disk_free_bytes": free, "staging_allowance_bytes": MIN_FREE_BYTES,
            "blockers": blockers, "build_executed": False,
            "validation_pending": ["Full compiler/SDK stage execution", "Pinned container base/packages and native/container ELF parity"],
            "steps": ["Acquire locked compiler/SDK source objects and verify provenance",
                      "Adapt acquisition in dedicated forks to refuse implicit fetching",
                      "Build DVP binutils; IOP binutils and GCC",
                      "Build EE binutils, GCC stage 1, newlib, pthread support, GCC stage 2",
                      "Build SDK and host utilities with locked external libraries",
                      "Repeat with digest-pinned container environment and compare minimal EE ELF"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = preflight()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Resolved source identities: {report['source_identities']}")
        print(f"Free workspace storage: {report['disk_free_bytes'] / 1024**3:.2f} GiB")
        for blocker in report["blockers"]:
            print("BLOCKED:", blocker)
        print("No toolchain build executed.")
    sys.exit(1 if report["blockers"] else 0)
