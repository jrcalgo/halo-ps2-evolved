"""Acquire explicitly selected locked sources; existing trees are never reset."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from locked_source import verify_checkout

ROOT = Path(__file__).resolve().parents[1]


def acquire(item, base, local=None, offline=False):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", item["id"]):
        raise RuntimeError("Invalid source ID")
    if not re.fullmatch(r"[0-9a-f]{40}", item["commit"]):
        raise RuntimeError("Source needs an exact full commit ID")
    base = Path(base).resolve()
    protected = ROOT / "submodules"
    if base == protected or protected in base.parents:
        raise RuntimeError("Acquisition must use a separate staging root")
    destination = base / item["id"]
    if destination.is_symlink():
        raise RuntimeError("Preserving source symlink; staging must own its checkout")
    if destination.exists():
        verify_checkout(destination, item["commit"])
        return destination
    if offline and local is None:
        raise RuntimeError("Offline acquisition needs an explicit local repository")
    if local is not None:
        local = str(Path(local).resolve(strict=True))
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".acquire.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists():
            verify_checkout(destination, item["commit"])
            return destination
        temporary = Path(tempfile.mkdtemp(prefix=".acquire-" + item["id"] + "-", dir=base))
        try:
            def git(*args):
                subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(temporary), *args], check=True)
            git("init", "-q")
            git("remote", "add", "origin", item["url"])
            # Local file transport is enabled only for an explicitly supplied local source.
            if local is not None:
                git("-c", "protocol.file.allow=always", "fetch", "--no-tags", "--depth=1", local, item["commit"])
            else:
                git("fetch", "--no-tags", "--depth=1", "origin", item["commit"])
            git("checkout", "--detach", item["commit"])
            verify_checkout(temporary, item["commit"])
            nested = subprocess.check_output(["git", "-C", str(temporary), "submodule", "status", "--recursive"], text=True)
            if nested.strip():
                raise RuntimeError("Nested source dependencies require an explicit audit and acquisition policy")
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)  # Only our private temporary directory, never existing sources.
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="One source ID from config/toolchain-sources.json")
    parser.add_argument("--from-local", type=Path)
    parser.add_argument("--offline", action="store_true", default=os.environ.get("OFFLINE") == "1")
    args = parser.parse_args()
    items = json.loads((ROOT / "config/toolchain-sources.json").read_text())["sources"]
    matches = [item for item in items if item["id"] == args.id]
    if len(matches) != 1:
        raise RuntimeError("Source ID must uniquely match the lock")
    build = Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build"))
    base = Path(os.environ.get("HALO_TOOLCHAIN_SOURCE_ROOT", build / "toolchain/sources"))
    if args.from_local is None and not args.offline and not (base / args.id).exists():
        existing = base.resolve()
        while not existing.exists():
            existing = existing.parent
        if shutil.disk_usage(existing).free < 20 * 1024 ** 3:
            raise RuntimeError("Remote compiler acquisition needs the conservative 20 GiB staging allowance")
    print(acquire(matches[0], base, args.from_local, args.offline))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Source acquisition failed: {error}")
