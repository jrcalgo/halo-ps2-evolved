"""Preserve or restore the exact private build image without a registry push."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--save", action="store_true")
    action.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    config_path = ROOT / "config/container-environment.json"
    config = json.loads(config_path.read_text())
    image = config["image_id"]
    docker = ["docker", "-H", os.environ.get("HALO_DOCKER_HOST", "unix:///var/run/docker.sock")]
    archive = Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build")) / "container-environment.tar"
    if args.save:
        inspected = json.loads(subprocess.check_output(docker + ["image", "inspect", image], text=True))[0]
        if inspected["Id"] != image:
            raise RuntimeError("Build image differs from the recorded identity")
        archive.parent.mkdir(parents=True, exist_ok=True)
        temporary = archive.with_suffix(".tar.tmp")
        subprocess.run(docker + ["image", "save", "--output", str(temporary), image], check=True)
        checksum = digest(temporary)
        temporary.replace(archive)
        config["archive_file"] = archive.name
        config["archive_sha256"] = checksum
        config_path.write_text(json.dumps(config, indent=2) + "\n")
        print(f"Saved {image} to {archive}; SHA-256 {checksum}")
    else:
        if not config.get("archive_sha256") or digest(archive) != config["archive_sha256"]:
            raise RuntimeError("Private build image archive is missing or has a different checksum")
        subprocess.run(docker + ["image", "load", "--input", str(archive)], check=True)
        inspected = json.loads(subprocess.check_output(docker + ["image", "inspect", image], text=True))[0]
        if inspected["Id"] != image:
            raise RuntimeError("Restored image does not match the lock")
        print(f"Restored exact build image {image}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Container image preservation failed: {error}")
