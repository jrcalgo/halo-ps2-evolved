"""Run supported build actions in the locked image with isolated writable output."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = {
    "host-tools": ["python3", "tools/build_toolchain.py", "--host-tools"],
    "toolchain": ["python3", "tools/build_toolchain.py"],
    "smoke-elf": ["python3", "tools/build_smoke.py"],
    "vu-smoke": ["python3", "tools/build_smoke.py", "--vu"],
    "probe": ["python3", "tools/build_probe.py"],
    "platform-elf": ["python3", "tools/build_platform.py"],
    "test-host": ["make", "test-host"],
}


def command(action, image, output):
    if action not in ACTIONS:
        raise RuntimeError("Unsupported container action")
    output = Path(output).resolve()
    if output == ROOT or output in ROOT.parents or output == ROOT / "build":
        raise RuntimeError("Container output must be separate from workspace and native output")
    if ROOT in output.parents and ROOT / "build" not in output.parents:
        raise RuntimeError("Within the workspace, only a build subdirectory may be writable")
    if ROOT / "submodules" == output or ROOT / "submodules" in output.parents:
        raise RuntimeError("Container output cannot be a dependency working tree")
    result = ["run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
              "--mount", f"type=bind,src={ROOT},dst={ROOT},readonly",
              "--mount", f"type=bind,src={output},dst={output}", "--workdir", str(ROOT)]
    settings = {"BUILD_ENV": "native", "HALO_EXECUTION_ENV": "container", "HALO_CONTAINER_IMAGE_ID": image,
                "HALO_BUILD_ROOT": str(output), "HALO_TOOLCHAIN_SOURCE_ROOT": str(output / "toolchain/sources"),
                "HALO_HOST_PREREQUISITE_PREFIX": str(ROOT / "build/host-prerequisites/install"),
                "HALO_BUILD_JOBS": os.environ.get("HALO_BUILD_JOBS", "2"), "HOME": "/tmp"}
    for key, value in settings.items():
        result.extend(["--env", key + "=" + value])
    if action == "toolchain":
        result.extend(["--env", "HALO_CONTAINER_PREPARE_SOURCES=1"])
    return result + [image, *ACTIONS[action]]


def run(action):
    config = json.loads((ROOT / "config/container-environment.json").read_text())
    image = config.get("image_id")
    if not image or not image.startswith("sha256:"):
        raise RuntimeError("Container prerequisite image has not been built and pinned")
    docker = ["docker", "-H", os.environ.get("HALO_DOCKER_HOST", "unix:///var/run/docker.sock")]
    inspected = json.loads(subprocess.check_output(docker + ["image", "inspect", image], text=True))[0]
    if inspected["Id"] != image:
        raise RuntimeError("Container image identity differs from the lock")
    output = Path(os.environ.get("HALO_CONTAINER_BUILD_ROOT", ROOT / "build/container")).resolve()
    arguments = command(action, image, output)
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(docker + arguments, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=ACTIONS)
    args = parser.parse_args()
    try:
        run(args.action)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Container execution failed: {error}")
