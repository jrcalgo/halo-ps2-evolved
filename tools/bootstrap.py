"""Restore locked local forks without moving dirty or mismatched worktrees."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=ROOT if cwd is None else cwd, text=True).strip()


def bootstrap():
    entries = json.loads((ROOT / "config/dependencies.json").read_text())["dependencies"]
    # Check every existing worktree and bundle before any checkout operation.
    for item in entries:
        path = ROOT / item["path"]
        staged = git("ls-files", "--stage", "--", item["path"]).split()
        if len(staged) < 3 or staged[:3] != ["160000", item["commit"], "0"]:
            raise RuntimeError(f"Gitlink differs from lock: {item['path']}")
        bundle = ROOT / ".local/bundles" / (item["name"] + ".bundle")
        if not bundle.is_file() or hashlib.sha256(bundle.read_bytes()).hexdigest() != item["bundle_sha256"]:
            raise RuntimeError(f"Missing or changed private bundle: {bundle}")
        if (path / ".git").exists():
            if git("status", "--porcelain", cwd=path):
                raise RuntimeError(f"Preserving dirty worktree: {path}")
            if git("rev-parse", "HEAD", cwd=path) != item["commit"]:
                raise RuntimeError(f"Preserving mismatched checkout: {path}")
    git("submodule", "init")
    for item in entries:
        fork = ROOT / ".local/forks" / (item["name"] + ".git")
        bundle = ROOT / ".local/bundles" / (item["name"] + ".bundle")
        git("bundle", "verify", str(bundle))
        if not fork.exists():
            fork.parent.mkdir(parents=True, exist_ok=True)
            git("clone", "--bare", str(bundle), str(fork))
        git("--git-dir", str(fork), "cat-file", "-e", item["commit"] + "^{commit}")
        git("config", f"submodule.{item['name']}.url", str(fork))
        # File transport permission is scoped to this invocation only.
        git("-c", "protocol.file.allow=always", "submodule", "update", "--init",
            "--recursive", "--checkout", "--no-fetch", "--", item["path"])
        path = ROOT / item["path"]
        remotes = git("remote", cwd=path).splitlines()
        git("remote", "set-url" if "upstream" in remotes else "add",
            "upstream", item["upstream"], cwd=path)
        git("remote", "set-url", "origin", str(fork), cwd=path)
        if git("rev-parse", "HEAD", cwd=path) != item["commit"]:
            raise RuntimeError(f"Checkout did not match lock: {path}")
    status = git("submodule", "status", "--recursive")
    if any(line.startswith(("-", "+", "U")) for line in status.splitlines()):
        raise RuntimeError("Recursive submodule status is inconsistent")
    print(status)
    print("Locked dependencies restored without network fetches.")


if __name__ == "__main__":
    try:
        bootstrap()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Bootstrap failed: {error}", file=sys.stderr)
        sys.exit(1)
