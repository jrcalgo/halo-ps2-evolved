"""Migrate an exact HCP1 C1 corpus to segmented HCP2 envelopes.

This is an envelope migration utility. It does not requalify C1 source inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_profile_chunks as writer
from hcu_profile_validate import parse_package


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _legacy_chunks(data: bytes, expected_profile_id: int) -> dict:
    """Strictly verify legacy HCP1 wire bytes; migration alone permits large media."""
    if len(data) < writer.HEADER.size:
        raise ValueError("truncated HCP1 header")
    magic, version, hsize, pid, count, directory, dsize, total = writer.HEADER.unpack_from(data)
    if (magic, version, hsize) != (writer.MAGIC_V1, 1, writer.HEADER.size):
        raise ValueError("input package is not HCP1 v1")
    if pid != expected_profile_id or not pid:
        raise ValueError("input profile id mismatch")
    if not 2 <= count <= writer.MAX_CHUNKS or directory != hsize or dsize != count * writer.V1_RECORD.size:
        raise ValueError("invalid HCP1 directory")
    dir_end = directory + dsize
    if total != len(data) or dir_end > total:
        raise ValueError("invalid HCP1 total extent")
    result, end, previous = {}, dir_end, None
    for index in range(count):
        kind, cid, offset, size, digest = writer.V1_RECORD.unpack_from(
            data, directory + index * writer.V1_RECORD.size)
        key = (kind, cid)
        if previous is not None and key <= previous:
            raise ValueError("HCP1 logical rows duplicate or out of order")
        previous = key
        if kind not in (1, 2, 3) or (kind != 2 and cid != 0) or not size:
            raise ValueError("invalid HCP1 logical identity/size")
        canonical = (end + writer.ALIGNMENT - 1) & ~(writer.ALIGNMENT - 1)
        if offset != canonical or offset % writer.ALIGNMENT or offset > total or size > total - offset:
            raise ValueError("HCP1 payload bounds are not canonical")
        if any(data[end:offset]):
            raise ValueError("HCP1 canonical padding is nonzero")
        blob = data[offset:offset + size]
        if hashlib.sha256(blob).digest() != digest:
            raise ValueError("HCP1 logical chunk hash mismatch")
        result[key] = blob
        end = offset + size
    if end != total or (1, 0) not in result or (3, 0) not in result:
        raise ValueError("HCP1 trailing bytes or required root missing")
    return result


def _profile_files(input_dir: Path, selections: list[str] | None):
    packages = sorted(input_dir.glob("*.hcp"))
    if selections:
        wanted = set(selections)
        packages = [p for p in packages if p.stem in wanted]
        missing = wanted - {p.stem for p in packages}
        if missing:
            raise ValueError(f"selected package(s) missing: {', '.join(sorted(missing))}")
    if not packages:
        raise ValueError(f"no package files in {input_dir}")
    return packages


def repack(input_dir: Path, output_dir: Path, selections: list[str] | None = None) -> dict:
    writer_path = Path(writer.__file__).resolve()
    parser_path = Path(__file__).with_name("hcu_profile_validate.py")
    script_path = Path(__file__).resolve()
    writer_sha, parser_sha, script_sha = (_sha(p.read_bytes()) for p in
                                          (writer_path, parser_path, script_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for package_path in _profile_files(input_dir, selections):
        manifest_path = package_path.with_suffix(".json")
        if not manifest_path.is_file():
            raise ValueError(f"manifest missing for {package_path.name}")
        package_data, manifest_data = package_path.read_bytes(), manifest_path.read_bytes()
        manifest = json.loads(manifest_data)
        manifest_sha, source_package_sha = _sha(manifest_data), _sha(package_data)
        package_pin = manifest.get("validation", {}).get("package_sha256")
        profile_id = manifest.get("validation", {}).get("profile_id")
        if package_pin != source_package_sha:
            raise ValueError(f"source package SHA mismatch for {package_path.name}")
        if not isinstance(profile_id, int) or profile_id <= 0:
            raise ValueError(f"invalid manifest profile id for {package_path.name}")
        logical = _legacy_chunks(package_data, profile_id)
        migrated = writer.encode(profile_id, logical, version=2)
        digest = _sha(migrated)
        parsed = parse_package(migrated, expected_package_sha256=digest,
                               expected_profile_id=profile_id)
        logical_hashes = {f"{kind}:{cid}": _sha(blob) for (kind, cid), blob in sorted(logical.items())}
        parsed_hashes = {f"{kind}:{cid}": _sha(blob) for (kind, cid), blob in sorted(parsed["chunks"].items())}
        if logical_hashes != parsed_hashes:
            raise ValueError(f"logical content changed during migration: {package_path.name}")
        if any(segment["size"] > writer.MAX_SEGMENT_BYTES for segment in parsed["segments"]):
            raise ValueError(f"oversized physical segment in {package_path.name}")
        manifest["envelope_provenance"] = {
            "migration": "HCP1-to-HCP2-envelope-only-v1",
            "source_package_sha256": source_package_sha,
            "source_manifest_sha256": manifest_sha,
            "writer_path": writer_path.relative_to(ROOT).as_posix(),
            "writer_sha256": writer_sha,
            "parser_path": parser_path.relative_to(ROOT).as_posix(),
            "parser_sha256": parser_sha,
            "migration_path": script_path.relative_to(ROOT).as_posix(),
            "migration_sha256": script_sha,
            "logical_chunk_count": len(logical),
            "logical_chunk_sha256": logical_hashes,
            "source_producer_pins_preserved": True,
            "c1_clean_source_qualification_claimed": False,
        }
        manifest["validation"]["package_sha256"] = digest
        # The envelope directory and segment records change the container's
        # physical size. Keep the physical-package field coherent while all
        # logical content and C1 producer/source pins remain unchanged.
        memory = manifest.setdefault("memory", {})
        memory["package_file_bytes"] = len(migrated)
        if "package_sha256" in manifest:
            manifest["package_sha256"] = digest
        out_package, out_manifest = output_dir / package_path.name, output_dir / manifest_path.name
        out_package.write_bytes(migrated)
        out_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        rows.append({"name": package_path.stem, "profile_id": profile_id,
                     "source_package_sha256": source_package_sha,
                     "source_manifest_sha256": manifest_sha,
                     "package_sha256": digest,
                     "manifest_sha256": _sha(out_manifest.read_bytes()),
                     "logical_chunk_count": len(logical), "physical_segment_count": len(parsed["segments"]),
                     "logical_chunks_unchanged": True,
                     "max_physical_segment_bytes": max(s["size"] for s in parsed["segments"]),
                     "physical_segments": [{"type": s["type"], "id": s["id"],
                                            "index": s["segment_index"], "size": s["size"],
                                            "sha256": s.get("segment_sha256", s["sha256"])}
                                           for s in parsed["segments"]],
                     "logical_chunk_sha256": logical_hashes})
    report = {"format": "hcu-hcp2-envelope-migration-report-v1",
              "migration_path": script_path.relative_to(ROOT).as_posix(),
              "migration_sha256": script_sha, "writer_sha256": writer_sha, "parser_sha256": parser_sha,
              "profiles": rows}
    (output_dir / "migration-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("profiles", nargs="*", help="optional package stems to migrate")
    args = parser.parse_args()
    report = repack(args.input_dir, args.output_dir, args.profiles or None)
    print(json.dumps({"profiles": len(report["profiles"]), "output": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
