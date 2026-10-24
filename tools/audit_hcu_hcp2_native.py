#!/usr/bin/env python3
"""Run the bounded file-backed C HCP2 preflight across an exact package corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def identity(path):
    path = Path(path).resolve()
    return {"path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def audit(profiles, output):
    compiler = shutil.which("cc")
    if not compiler:
        raise RuntimeError("C compiler unavailable")
    output.mkdir(parents=True, exist_ok=True)
    executable = output / "hcp2-file-preflight"
    sources = [ROOT / "tests/hcu_asset_profile_corpus_main.c",
               ROOT / "src/stream/hcu_asset_profile.c", ROOT / "src/stream/sha256.c"]
    command = [compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
               "-I" + str(ROOT / "src"), *map(str, sources), "-o", str(executable)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    rows = []
    for package in sorted(profiles.glob("*.hcp")):
        manifest = package.with_suffix(".json")
        metadata = json.loads(manifest.read_text())
        package_id = identity(package)
        if package_id["sha256"] != metadata["package_sha256"]:
            raise ValueError("manifest package mismatch: " + package.name)
        profile_id = metadata["profile"]["id"]
        run_command = [str(executable), str(package), str(profile_id)]
        run = subprocess.run(run_command, capture_output=True, text=True)
        fields = run.stdout.split()
        accepted = run.returncode == 0 and len(fields) == 6 and fields[0] == "OK"
        row = {"profile": package.stem, "package": package_id,
               "manifest": identity(manifest), "command": run_command,
               "returncode": run.returncode, "stdout": run.stdout,
               "stderr": run.stderr, "result": "passed" if accepted else "failed"}
        if accepted:
            row.update(profile_id=int(fields[1]), physical_segments=int(fields[2]),
                       ce_logical_bytes=int(fields[3]), largest_read_request_bytes=int(fields[4]),
                       source_read_calls=int(fields[5]))
        rows.append(row)
    report = {"format": "hcu-c2-hcp2-native-corpus-v1", "evidence_level": "host execution",
              "scope": "File-backed C segment/hash preflight and cross-segment CE range read; no package-sized guest allocation",
              "limitation": "Host execution does not prove EE placement, runtime timing, CE live-set capacity, or complete rendered consumption.",
              "producer": identity(__file__), "compile_command": command,
              "executable": identity(executable),
              "source_pins": [identity(path) for path in sources +
                              [ROOT / "src/stream/hcu_asset_profile.h"]],
              "profiles": rows, "passed": sum(r["result"] == "passed" for r in rows),
              "failed": sum(r["result"] != "passed" for r in rows)}
    path = output / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=ROOT / "build/m2-c2-hcp2-primary")
    parser.add_argument("--output", type=Path, default=ROOT / "build/m2-c2-hcp2-native")
    parser.add_argument("--expect-count", type=int, default=27,
                        help="require this many package manifests (default: complete 27-profile corpus)")
    args = parser.parse_args()
    result = audit(args.profiles.resolve(), args.output.resolve())
    print(f'HCP2 native corpus: {result["passed"]} passed, {result["failed"]} failed')
    raise SystemExit(0 if result["passed"] == args.expect_count and result["failed"] == 0 else 1)
