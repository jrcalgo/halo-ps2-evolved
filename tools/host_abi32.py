"""Prepare a private 32-bit libc/compiler support prefix for host fixtures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sysroot():
    return Path(os.environ.get("HALO_HOST_ABI32_ROOT", ROOT / "build/host-abi32/root")).resolve()


def flags():
    root = sysroot()
    return ["-m32", "--sysroot=" + str(root),
            "-B" + str(root / "usr/lib/gcc/x86_64-linux-gnu/12/32") + "/",
            "-B" + str(root / "usr/lib32") + "/",
            "-Wl,--dynamic-linker=" + str(root / "usr/lib32/ld-linux.so.2"),
            "-Wl,-rpath," + str(root / "usr/lib32")]


def prepare():
    root = sysroot()
    base = root.parent
    packages = json.loads((ROOT / "config/host-abi32.json").read_text())["packages"]
    for item in packages:
        path = base / "packages" / item["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"32-bit package checksum differs: {path}")
    root.mkdir(parents=True, exist_ok=True)
    for item in packages:
        subprocess.run(["dpkg-deb", "-x", str(base / "packages" / item["file"]), str(root)], check=True)
    for name in ("lib", "lib32"):
        link = root / name
        if not link.is_symlink() and not link.exists():
            link.symlink_to("usr/" + name)
    loader = root / "usr/lib/ld-linux.so.2"
    if not loader.exists() and not loader.is_symlink():
        loader.symlink_to("../lib32/ld-linux.so.2")
    print(f"32-bit host sysroot prepared at {root}")


if __name__ == "__main__":
    prepare()
