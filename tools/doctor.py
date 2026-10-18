"""Read-only local readiness inventory; never fetches dependencies or repairs Git."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = (
    "halo-64", "halo-ps2", "halo-ce-universal", "ps2dev",
    "ps2toolchain", "ps2sdk", "ps2client", "ps2link",
)


def command(*args):
    try:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                                timeout=10, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return {"ok": result.returncode == 0, "exit_code": result.returncode,
                "detail": (result.stdout + result.stderr).strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "detail": str(error)}


def inventory():
    git = command("git", "rev-parse", "--show-toplevel")
    git["is_workspace_root"] = git["ok"] and Path(git["detail"]).resolve() == ROOT
    git_dir = command("git", "rev-parse", "--absolute-git-dir") if git["ok"] else None
    git["metadata_writable"] = bool(git_dir and git_dir["ok"] and
                                      os.access(git_dir["detail"], os.W_OK))
    names = ("git", "make", "python3", "docker", "node", "pcsx2", "xemu",
             "mips64r5900el-ps2-elf-gcc", "ee-gcc", "dvp-as", "ps2client")
    dependencies = {}
    lock_path = ROOT / "config/dependencies.json"
    locked = {item["name"]: item["commit"] for item in
              json.loads(lock_path.read_text())["dependencies"]} if lock_path.exists() else {}
    for name in dict.fromkeys((*REPOSITORIES, *locked)):
        path = ROOT / "submodules" / name
        head = command("git", "-C", str(path), "rev-parse", "HEAD") if (path / ".git").exists() else {}
        index = command("git", "ls-files", "--stage", "--", "submodules/" + name)
        fields = index.get("detail", "").split()
        pin = locked.get(name)
        verified = pin if (pin and head.get("ok") and head["detail"] == pin and
                           fields[:3] == ["160000", pin, "0"]) else None
        # A directory alone does not establish a registered or initialized submodule.
        dependencies[name] = {"present": path.is_dir(),
                              "git_metadata_present": (path / ".git").exists(),
                              "verified_pin": verified}
    blockers = []
    if not git["is_workspace_root"]:
        blockers.append("Workspace is not a valid parent Git repository.")
    if not git["metadata_writable"]:
        blockers.append("Writable parent Git metadata has not been established.")
    if any(item["verified_pin"] is None for item in dependencies.values()):
        blockers.append("Dependency gitlinks and full commit pins are unverified.")
    return {"workspace": str(ROOT), "git": git,
            "tools": {name: shutil.which(name) for name in names},
            "dependencies": dependencies, "blockers": blockers,
            "network": "Not probed by doctor; no network operations are performed.",
            "limits": "Tool paths do not establish version compatibility, Docker daemon access, emulator configuration, or runtime correctness."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = inventory()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Workspace:", report["workspace"])
        for name, path in report["tools"].items():
            print(f"  {name}: {path or 'missing from PATH'}")
        for blocker in report["blockers"]:
            print("BLOCKED:", blocker)
        print(report["network"])
        print(report["limits"])
    return 1 if report["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
