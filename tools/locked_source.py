"""Return an already acquired, exact compiler source tree; never fetch or reset it."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def source_path(url, ref, source_root):
    lock = json.loads((ROOT / "config/toolchain-sources.json").read_text())
    matches = [item for item in lock["sources"] if item["url"] == url and item["ref"] == ref]
    if len(matches) != 1:
        raise RuntimeError("Requested source URL/ref does not uniquely match the lock")
    item = matches[0]
    base = Path(source_root).resolve()
    path = (base / item["id"]).resolve()
    submodules = ROOT / "submodules"
    if path == submodules or submodules in path.parents:
        raise RuntimeError("Compiler builds must use separate staging trees, not dependency submodules")
    if path.parent != base:
        raise RuntimeError("Source ID escapes the staging root")
    verify_checkout(path, item["commit"])
    return path


def verify_checkout(path, commit):
    path = Path(path).resolve()
    if not (path / ".git").exists():
        raise RuntimeError(f"Locked staging checkout is missing: {path}")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], text=True,
                                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).strip()

    if Path(git("rev-parse", "--show-toplevel")).resolve() != path:
        raise RuntimeError("Staging path is not an independent source checkout")
    if git("rev-parse", "HEAD") != commit:
        raise RuntimeError(f"Locked staging checkout has a different commit: {path}")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError(f"Preserving modified compiler source: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--ref", required=True)
    args = parser.parse_args()
    try:
        base = os.environ.get("HALO_TOOLCHAIN_SOURCE_ROOT")
        if not base:
            raise RuntimeError("HALO_TOOLCHAIN_SOURCE_ROOT must select acquired staging checkouts")
        print(source_path(args.url, args.ref, base))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Locked source unavailable: {error}", file=sys.stderr)
        sys.exit(1)
