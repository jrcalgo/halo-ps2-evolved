import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_profile_chunks as writer
from hcu_profile_validate import ProfileValidationError, parse_package
import repack_hcu_profiles_hcp2


def parse(data):
    return parse_package(data, expected_package_sha256=hashlib.sha256(data).hexdigest(),
                         expected_profile_id=7)


def test_hcp2_segments_every_type_and_reconstructs_logical_chunks():
    payload = bytes(range(256)) * 300
    chunks = {(1, 0): payload, (3, 0): b"sound", (2, 4): b"texture"}
    data = writer.encode(7, chunks)
    parsed = parse(data)
    assert parsed["format"] == "HCP2" and parsed["version"] == 2
    assert parsed["chunks"] == chunks
    rows = parsed["segments"]
    assert len(rows) == 4
    assert [(r["type"], r["segment_index"]) for r in rows] == [(1, 0), (1, 1), (2, 0), (3, 0)]


def test_hcp1_compatibility_and_explicit_encoder():
    logical = {(1, 0): b"ce", (2, 1): b"media", (3, 0): b"sound"}
    package = writer.encode(7, logical, version=1)
    parsed = parse(package)
    assert parsed["format"] == "HCP1" and parsed["chunks"] == logical
    assert len(parsed["segments"]) == 3


def test_default_hcp2_segments_oversize_media_logical_chunks():
    media = b"m" * 200_000
    package = writer.encode(7, {(1, 0): b"ce", (2, 9): media, (3, 0): b"sound"})
    parsed = parse(package)
    assert parsed["chunks"][(2, 9)] == media
    media_rows = [row for row in parsed["segments"] if row["type"] == 2]
    assert [row["size"] for row in media_rows] == [65536, 65536, 65536, 3392]
    with pytest.raises(writer.ProfileError):
        writer.encode(7, {(1, 0): b"ce", (2, 9): media, (3, 0): b"sound"}, version=1)


@pytest.mark.parametrize("field,value", [(24, 2), (28, 0), (32, 1), (36, 0)])
def test_hcp2_rejects_bad_segment_metadata(field, value):
    package = bytearray(writer.encode(7, {(1, 0): b"c" * 70000, (3, 0): b"s"}))
    struct.pack_into("<I", package, writer.HEADER.size + field, value)
    with pytest.raises(ProfileValidationError):
        parse(bytes(package))


def test_hcp2_rejects_segment_hash_logical_hash_and_truncation():
    package = writer.encode(7, {(1, 0): b"c" * 70000, (3, 0): b"s"})
    parsed = parse(package)
    first = parsed["segments"][0]
    damaged = bytearray(package); damaged[first["offset"]] ^= 1
    with pytest.raises(ProfileValidationError):
        parse(bytes(damaged))
    header = writer.HEADER.unpack_from(package)
    row_at = header[5]
    damaged = bytearray(package)
    # Keep each segment digest valid, but make the whole logical digest incorrect.
    damaged[row_at + 64] ^= 1
    with pytest.raises(ProfileValidationError):
        parse(bytes(damaged))
    with pytest.raises(ProfileValidationError):
        parse(package[:-1])


def test_hcp1_envelope_migration_updates_physical_package_size(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    logical = {(1, 0): b"ce" * 80, (2, 1): b"media" * 800,
               (3, 0): b"sound"}
    source = writer.encode(13, logical, version=1)
    (input_dir / "bots-sidewinder.hcp").write_bytes(source)
    manifest = {"profile": {"name": "bots-sidewinder", "id": 13},
                "validation": {"profile_id": 13,
                               "package_sha256": hashlib.sha256(source).hexdigest()},
                "package_sha256": hashlib.sha256(source).hexdigest(),
                "memory": {"package_file_bytes": len(source)}}
    (input_dir / "bots-sidewinder.json").write_text(json.dumps(manifest))

    report = repack_hcu_profiles_hcp2.repack(input_dir, output_dir,
                                              ["bots-sidewinder"])
    migrated = output_dir / "bots-sidewinder.hcp"
    result_manifest = json.loads((output_dir / "bots-sidewinder.json").read_text())
    parsed = parse_package(migrated.read_bytes(),
                           expected_package_sha256=hashlib.sha256(migrated.read_bytes()).hexdigest(),
                           expected_profile_id=13)
    assert result_manifest["memory"]["package_file_bytes"] == migrated.stat().st_size
    assert result_manifest["memory"]["package_file_bytes"] != len(source)
    assert parsed["chunks"] == logical
    assert report["profiles"][0]["logical_chunks_unchanged"]
    assert report["profiles"][0]["max_physical_segment_bytes"] <= 65536
