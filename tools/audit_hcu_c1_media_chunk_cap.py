"""Audit checked-in primary C1 HCP packages against the current MEDIA cap."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hcu_profile_chunks import (HEADER, V1_RECORD, V2_RECORD, MAX_MEDIA_CHUNK_BYTES,
                                MAX_SEGMENT_BYTES)  # noqa: E402
from hcu_profile_validate import parse_package  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(profiles: Path, qualification: Path) -> dict:
    qualification_data = json.loads(qualification.read_text())
    packages = []
    for manifest_path in sorted(profiles.glob("*.json")):
        if manifest_path.name == "specs.json":
            continue
        manifest = json.loads(manifest_path.read_text())
        manifest_package_sha = manifest.get("validation", {}).get(
            "package_sha256", manifest.get("package_sha256"))
        manifest_profile_id = manifest.get("validation", {}).get(
            "profile_id", manifest.get("profile", {}).get("id"))
        package_path = manifest_path.with_suffix(".hcp")
        if not package_path.is_file():
            continue
        package_bytes = package_path.read_bytes()
        package_sha = hashlib.sha256(package_bytes).hexdigest()
        try:
            if len(package_bytes) < HEADER.size:
                raise ValueError("truncated HCP header")
            magic, version, hsize, profile_id, count, directory, dsize, total = HEADER.unpack_from(package_bytes)
            if (magic, version) not in ((b"HCP1", 1), (b"HCP2", 2)) or hsize != HEADER.size:
                raise ValueError("unsupported HCP header while inventorying rows")
            record = V1_RECORD if version == 1 else V2_RECORD
            if directory != HEADER.size or dsize != count * record.size or total != len(package_bytes):
                raise ValueError("invalid HCP directory while inventorying MEDIA rows")
            media_sizes, physical_sizes = [], []
            for index in range(count):
                fields = record.unpack_from(package_bytes, directory + index * record.size)
                if version == 1:
                    kind, chunk_id, offset, size, digest = fields
                    logical_size, segment_index = size, 0
                    segment_sha = digest
                else:
                    (kind, chunk_id, offset, size, logical_offset, logical_size,
                     segment_index, segment_count, segment_sha, logical_sha) = fields
                physical_sizes.append({"type": kind, "chunk_id": chunk_id,
                                       "segment_index": segment_index, "size_bytes": size,
                                       "segment_sha256": segment_sha.hex()})
                if kind == 2 and (version == 1 or segment_index == 0):
                    media_sizes.append({"chunk_id": chunk_id, "size_bytes": logical_size,
                                        "logical_sha256": (digest.hex() if version == 1 else logical_sha.hex())})
            strict_result = {"accepted": True, "error": None}
            try:
                parsed = parse_package(
                    package_bytes, expected_package_sha256=manifest.get("validation", {}).get(
                        "package_sha256", manifest.get("package_sha256")),
                    expected_profile_id=manifest.get("validation", {}).get(
                        "profile_id", manifest.get("profile", {}).get("id")))
                strict_result["parsed_media_chunks"] = sum(
                    row["type"] == 2 for row in parsed["directory"])
            except Exception as error:  # Record the validator's fail-closed result verbatim.
                strict_result = {"accepted": False,
                                 "error_type": type(error).__name__, "error": str(error)}
            max_entry = max(media_sizes, key=lambda row: row["size_bytes"], default=None)
            packages.append({
                "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
                "manifest_sha256": sha256(manifest_path),
                "package_path": package_path.relative_to(ROOT).as_posix(),
                "package_sha256": package_sha,
                "manifest_package_sha256": manifest_package_sha,
                "package_sha_matches_manifest": package_sha == manifest_package_sha,
                "profile_id": manifest_profile_id,
                "media_entry_count": len(media_sizes),
                "over_cap_media_entry_count": sum(
                    row["size_bytes"] > MAX_MEDIA_CHUNK_BYTES for row in media_sizes),
                "physical_segment_count": len(physical_sizes),
                "over_cap_physical_segment_count": sum(
                    row["size_bytes"] > MAX_SEGMENT_BYTES for row in physical_sizes),
                "max_physical_segment_bytes": max((row["size_bytes"] for row in physical_sizes), default=0),
                "physical_segments": physical_sizes,
                "max_media_entry": max_entry,
                "strict_validator": strict_result,
            })
        except Exception as error:
            packages.append({
                "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
                "manifest_sha256": sha256(manifest_path),
                "package_path": package_path.relative_to(ROOT).as_posix(),
                "package_sha256": package_sha,
                "strict_validator": {"accepted": False,
                                     "error_type": type(error).__name__, "error": str(error)},
                "inventory_error": True,
            })

    writer = ROOT / "tools/hcu_profile_chunks.py"
    parser = ROOT / "tools/hcu_profile_validate.py"
    return {
        "schema": "hcu-c1-media-chunk-cap-audit-v1",
        "cap_bytes": MAX_MEDIA_CHUNK_BYTES,
        "profiles_directory": profiles.relative_to(ROOT).as_posix(),
        "qualification": {
            "path": qualification.relative_to(ROOT).as_posix(),
            "sha256": sha256(qualification),
            "format": qualification_data.get("format"),
            "status": qualification_data.get("status"),
            "qualified": qualification_data.get("qualified"),
            "summary": qualification_data.get("summary"),
        },
        "current_writer": {"path": writer.relative_to(ROOT).as_posix(),
                           "sha256": sha256(writer)},
        "current_strict_parser": {"path": parser.relative_to(ROOT).as_posix(),
                                  "sha256": sha256(parser)},
        "package_count": len(packages),
        "strict_validator_pass_count": sum(
            row.get("strict_validator", {}).get("accepted") is True for row in packages),
        "strict_validator_fail_count": sum(
            row.get("strict_validator", {}).get("accepted") is not True for row in packages),
        "packages": packages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path,
                        default=ROOT / "build/m2-c1-corpus-primary-v3")
    parser.add_argument("--qualification", type=Path,
                        default=ROOT / "docs/reports/m2-c1-qualification-2026-10-23.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/reports/m2-c1-media-chunk-cap-audit-2026-10-23.json")
    args = parser.parse_args()
    report = audit(args.profiles.resolve(), args.qualification.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "schema", "package_count", "strict_validator_pass_count",
        "strict_validator_fail_count", "current_writer", "current_strict_parser",
        "qualification")}, sort_keys=True, indent=2))
    return 0 if report["package_count"] and report["strict_validator_fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
