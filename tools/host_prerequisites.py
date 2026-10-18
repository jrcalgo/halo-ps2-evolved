"""Verify and extract pinned native packages into a workspace-owned prefix."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def prefix():
    if os.environ.get("HALO_HOST_PREREQUISITE_PREFIX"):
        return Path(os.environ["HALO_HOST_PREREQUISITE_PREFIX"]).resolve()
    return Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build")).resolve() / "host-prerequisites/install"


def configure_flags():
    location = prefix()
    return [f"--with-{name}={location}" for name in ("gmp", "mpfr", "mpc")] if location.is_dir() else []


def native_environment(env=None):
    result = dict(os.environ if env is None else env)
    location = prefix()
    if location.is_dir():
        result["PATH"] = str(location / "bin") + os.pathsep + result.get("PATH", "")
        result["HALO_HOST_CONFIGURE_FLAGS"] = " ".join(configure_flags())
    return result


def prepare():
    base = prefix().parent
    packages = json.loads((ROOT / "config/native-prerequisites.json").read_text())["packages"]
    for item in packages:
        path = base / "packages" / item["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Prerequisite package checksum differs: {path}")
    root = base / "root"
    root.mkdir(parents=True, exist_ok=True)
    for item in packages:
        subprocess.run(["dpkg-deb", "-x", str(base / "packages" / item["file"]), str(root)], check=True)
    location = prefix()
    for directory in ("bin", "include", "lib"):
        (location / directory).mkdir(parents=True, exist_ok=True)
    for header in ("gmp.h", "mpfr.h", "mpc.h"):
        source = root / "usr/include" / header
        if not source.exists():
            source = root / "usr/include/x86_64-linux-gnu" / header
        shutil.copyfile(source, location / "include" / header)
    for library in ("libgmp.a", "libmpfr.a", "libmpc.a"):
        shutil.copyfile(root / "usr/lib/x86_64-linux-gnu" / library, location / "lib" / library)
    settings = {"LD_LIBRARY_PATH": str(root / "usr/lib/x86_64-linux-gnu"),
                "PERL5LIB": ":".join(str(root / "usr" / part) for part in
                                     ("share/texinfo", "share/perl5", "lib/x86_64-linux-gnu/perl5/5.38", "lib/texinfo")),
                "BISON_PKGDATADIR": str(root / "usr/share/bison")}
    for name in ("makeinfo", "flex", "bison", "gawk"):
        wrapper = location / "bin" / name
        lines = ["#!/bin/sh"]
        for key, value in settings.items():
            suffix = '${' + key + ':+:$' + key + '}' if key != "BISON_PKGDATADIR" else ""
            lines.append(f"export {key}={shlex.quote(value)}{suffix}")
        lines.append("exec " + shlex.quote(str(root / "usr/bin" / name)) + ' "$@"')
        wrapper.write_text("\n".join(lines) + "\n")
        wrapper.chmod(0o755)
        subprocess.run([str(wrapper), "--version"], check=True, stdout=subprocess.DEVNULL)
    print(f"Verified native prerequisites prepared at {location}")


if __name__ == "__main__":
    prepare()
