"""Isolated native compiler/SDK stages and independently buildable host utilities."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from acquire_sources import acquire
from locked_source import verify_checkout
from toolchain_plan import preflight

ROOT = Path(__file__).resolve().parents[1]


def save(path, report):
    paths = [path]
    if report.get("run_directory"):
        paths.append(Path(report["run_directory"]) / "result.json")
    for destination in paths:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(destination)


def run_stages(stages, env, report_path, identities):
    run = report_path.parent / "runs" / (report_path.stem + "-" + uuid.uuid4().hex)
    report = {"status": "running", "identities": identities, "stages": [], "run_directory": str(run)}
    save(report_path, report)
    for index, (name, command, cwd) in enumerate(stages):
        log = run / "logs" / f"{index:02d}-{name}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        record = {"name": name, "command": command, "cwd": str(cwd), "log": str(log)}
        report["stages"].append(record)
        print(f"Running {name}; log: {log}", flush=True)
        try:
            with log.open("w") as output:
                result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
            record["exit_code"] = result.returncode
            if result.returncode:
                raise RuntimeError(f"Stage {name} failed with exit {result.returncode}; see {log}")
        except (OSError, RuntimeError) as error:
            record["error"] = str(error)
            report["status"] = "failed"
            save(report_path, report)
            raise
        save(report_path, report)
    report["status"] = "stages-passed"
    save(report_path, report)
    return report


def environment():
    build = Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build")).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", str(build)):
        raise RuntimeError("PS2 build paths must not contain whitespace or shell-special characters")
    if build == ROOT or ROOT / "submodules" == build or ROOT / "submodules" in build.parents:
        raise RuntimeError("Build output must be isolated from dependency working trees")
    jobs = int(os.environ.get("HALO_BUILD_JOBS", "2"))
    if not 1 <= jobs <= 64:
        raise RuntimeError("HALO_BUILD_JOBS must be between 1 and 64")
    prefix = build / "toolchain/install"
    env = dict(os.environ)
    for key in ("PS2SDKSRC", "PS2DEV_CONFIG_OVERRIDE", "DESTDIR", "MAKEFLAGS", "MFLAGS",
                "CC", "CXX", "CPP", "AR", "AS", "LD", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS"):
        env.pop(key, None)
    env.update(PS2DEV=str(prefix), PS2SDK=str(prefix / "ps2sdk"), HALO_BUILD_JOBS=str(jobs),
               HALO_LOCKED_SOURCE_HELPER=str(ROOT / "tools/locked_source.py"),
               HALO_TOOLCHAIN_SOURCE_ROOT=str(Path(os.environ.get("HALO_TOOLCHAIN_SOURCE_ROOT", build / "toolchain/sources")).resolve()))
    env["PATH"] = os.pathsep.join(str(prefix / suffix) for suffix in
                                 ("bin", "ee/bin", "iop/bin", "dvp/bin", "ps2sdk/bin")) + os.pathsep + env.get("PATH", "")
    return build, prefix, env, jobs


def dependency(name):
    entries = json.loads((ROOT / "config/dependencies.json").read_text())["dependencies"]
    item = next(entry for entry in entries if entry["name"] == name)
    verify_checkout(ROOT / item["path"], item["commit"])
    return item


def stage_dependency(name, build):
    item = dependency(name)
    path = acquire({"id": name, "url": item["upstream"], "commit": item["commit"]},
                   build / "toolchain/staging", local=ROOT / item["path"], offline=True)
    return path, item


def host_tools(build, prefix, env, jobs):
    for tool in ("cc", "make", "strip"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"Missing host build tool: {tool}")
    source, item = stage_dependency("ps2client", build)
    report_path = build / "toolchain/host-tools.json"
    stages = [("host-build", ["make", f"-j{jobs}", "CC=cc", "all"], source),
              ("host-install", ["make", f"PREFIX={prefix}", "install"], source)]
    report = run_stages(stages, env, report_path, {"ps2client": item["commit"]})
    report["artifacts"] = {}
    for name in ("ps2client", "fsclient"):
        path = prefix / "bin" / name
        if not path.is_file():
            report["status"] = "failed"
            save(report_path, report)
            raise RuntimeError(f"Build did not produce {path}")
        report["artifacts"][name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    report["compiler"] = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    report["limits"] = "Host utilities compiled; no connection to a console or emulator was made."
    report["status"] = "passed"
    save(report_path, report)
    print(f"Host tools installed at {prefix / 'bin'}")


def compiler_and_sdk(build, prefix, env, jobs):
    readiness = preflight()
    if readiness["blockers"]:
        raise RuntimeError("Toolchain prerequisites unavailable:\n" + "\n".join(readiness["blockers"]))
    profile = json.loads((ROOT / "config/toolchain-profile.json").read_text())
    identities = {}
    for name in ("ps2toolchain-ee", "ps2toolchain-iop", "ps2toolchain-dvp", "ps2sdk"):
        identities[name] = dependency(name)["commit"]
    sdk, _ = stage_dependency("ps2sdk", build)
    stages = []
    for index, script in enumerate(profile["compiler_scripts"]):
        path = (ROOT / script).resolve()
        if ROOT / "submodules" not in path.parents or not path.is_file():
            raise RuntimeError(f"Invalid compiler stage: {script}")
        stages.append((f"compiler-{index:02d}", ["bash", str(path)], build / "toolchain"))
    stages.extend([("sdk-build", ["make", f"-j{jobs}"], sdk),
                   ("sdk-install", ["make", f"-j{jobs}", "install"], sdk)])
    report_path = build / "toolchain/compiler-sdk.json"
    report = run_stages(stages, env, report_path, identities)
    library_dir = prefix / "ee/mips64r5900el-ps2-elf/lib"
    for name in ("libcglue.a", "libpthreadglue.a", "libprofglue.a", "libkernel.a", "libcdvd.a"):
        target = prefix / "ps2sdk/ee/lib" / name
        link = library_dir / name
        if not target.is_file():
            report["status"] = "failed"
            save(report_path, report)
            raise RuntimeError(f"SDK glue library missing: {target}")
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if link.exists() or link.is_symlink():
            raise RuntimeError(f"Preserving unexpected installed library: {link}")
        link.symlink_to(os.path.relpath(target, library_dir))
    report["limits"] = "Compiler/SDK stages only; ELF parity, emulator and hardware gates remain separate."
    report["status"] = "passed"
    save(report_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-tools", action="store_true", help="Build only the small native ps2client utilities")
    args = parser.parse_args()
    if os.environ.get("BUILD_ENV", "native") != "native":
        raise RuntimeError("Container build execution is pending a pinned image/package environment")
    build, prefix, env, jobs = environment()
    if args.host_tools:
        host_tools(build, prefix, env, jobs)
    else:
        compiler_and_sdk(build, prefix, env, jobs)
        host_tools(build, prefix, env, jobs)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Build failed: {error}")
