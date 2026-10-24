#!/usr/bin/env python3
"""Emit the C2 production profile image header for one partition row.

The header is included by src/stream/hcu_main.c when the EE build defines
HALO_HCU_PROFILE_IMAGE_HEADER (tools/ee-world.mk does so for WORLD_HCU_PARTITION_PROFILE).
It pins, for one selected package row:

- the package file: asset-root-relative path, exact byte size and SHA-256
  (checked against the manifest's package_sha256 before anything is written);
- the HCM1 runtime metadata blob (tools/build_hcu_runtime_metadata.py build()),
  as a const byte array, with its SHA-256 and the storage bytes its decode needs;
- the source maps the package reads, each with an asset-root-relative path, size
  and SHA-256 (checked against the manifest's source_maps entries);
- the output_datum -> source map table, built from the manifest's chunk bindings.
  Every datum must map to exactly one source map or the generator fails.

Nothing here is read by the EE at runtime except the header itself. The package
and source maps stay in the asset root and are read through hcu_file_bridge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_hcu_runtime_metadata as metadata_tool  # noqa: E402

DEFAULT_PACKAGE_ROOT = ROOT / "build/m2-c2-r3-selected-packages/pkg"
HCM_HEADER_BYTES = 32
HCM_BITMAP_BYTES = 56
HCM_CBSP_BYTES = 76
HCM_RANGE_BYTES = 12


class HeaderError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise HeaderError(f"{path} is outside the asset root {root}") from exc


def metadata_storage_bytes(blob: bytes) -> int:
    """Caller storage for decode: the three tables, i.e. everything after the header."""
    bitmap_count = struct.unpack_from("<I", blob, 16)[0]
    cbsp_count = struct.unpack_from("<I", blob, 20)[0]
    range_count = struct.unpack_from("<I", blob, 24)[0]
    needed = (bitmap_count * HCM_BITMAP_BYTES + cbsp_count * HCM_CBSP_BYTES +
              range_count * HCM_RANGE_BYTES)
    if HCM_HEADER_BYTES + needed != len(blob):
        raise HeaderError("metadata table sizes do not cover the blob")
    return needed


def byte_array(data: bytes, indent: str = "\t") -> str:
    lines = []
    for start in range(0, len(data), 16):
        chunk = data[start:start + 16]
        lines.append(indent + ", ".join(f"0x{b:02x}" for b in chunk) + ",")
    return "\n".join(lines)


def sha_array(hex_digest: str) -> str:
    raw = bytes.fromhex(hex_digest)
    return "{ " + ", ".join(f"0x{b:02x}" for b in raw) + " }"


def build_header(row: str, package_root: Path, asset_root: Path) -> str:
    package_dir = package_root / row
    manifest_path = package_dir / f"{row}.json"
    package_path = package_dir / f"{row}.hcp"
    if not manifest_path.is_file() or not package_path.is_file():
        raise HeaderError(f"package row {row} is missing its manifest or HCP under {package_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile = manifest.get("profile", {})
    if profile.get("name") != row:
        raise HeaderError(f"manifest names {profile.get('name')!r}, expected {row!r}")
    profile_id = int(profile["id"])
    map_name = profile["map"]

    package_sha = sha256_file(package_path)
    if package_sha != manifest["package_sha256"]:
        raise HeaderError(f"HCP sha256 {package_sha} differs from the manifest pin")
    package_bytes = package_path.stat().st_size
    if package_bytes != manifest["memory"]["package_file_bytes"]:
        raise HeaderError("HCP size differs from the manifest's package_file_bytes")

    blob = metadata_tool.build(manifest_path, package_path)
    metadata_sha = hashlib.sha256(blob).hexdigest()
    storage_bytes = metadata_storage_bytes(blob)

    source_keys = sorted({b["owner"]["source_key"] for b in manifest["chunk_bindings"]})
    source_keys = sorted(set(source_keys) | {r["source"] for r in manifest["resources"]})
    sources = []
    for key in source_keys:
        entry = manifest["source_maps"].get(key)
        if entry is None:
            raise HeaderError(f"source map {key} has no manifest entry")
        source_path = asset_root / entry["path"]
        if not source_path.is_file():
            raise HeaderError(f"source map {source_path} is missing")
        if sha256_file(source_path) != entry["sha256"]:
            raise HeaderError(f"source map {source_path} differs from its manifest sha256")
        sources.append({
            "key": key,
            "path": entry["path"],
            "bytes": source_path.stat().st_size,
            "sha256": entry["sha256"],
        })
    index_of = {s["key"]: i for i, s in enumerate(sources)}

    datum_source: dict[int, str] = {}
    for binding in manifest["chunk_bindings"]:
        owner = binding["owner"]
        datum = int(owner["output_datum"])
        key = owner["source_key"]
        if datum_source.setdefault(datum, key) != key:
            raise HeaderError(f"output datum {datum} maps to two source maps")
    relocation_bytes = (int(manifest["memory"]["ctag_relocation_table_bytes"]) + 3) & ~3

    package_rel = relative_to_root(package_path, asset_root)
    out = []
    out.append("/* Generated by tools/c2_profile_image_header.py. Do not edit. */")
    out.append(f"/* Row {row}: profile {profile_id} on map {map_name}. */")
    out.append(f"#ifndef HCU_C2_PROFILE_IMAGE_{row.upper()}_H")
    out.append(f"#define HCU_C2_PROFILE_IMAGE_{row.upper()}_H")
    out.append("")
    out.append(f'#define HCU_C2_IMAGE_ROW "{row}"')
    out.append(f'#define HCU_C2_IMAGE_MAP "{map_name}"')
    out.append(f"#define HCU_C2_IMAGE_PROFILE_ID {profile_id}u")
    out.append(f'#define HCU_C2_IMAGE_PACKAGE_PATH "{package_rel}"')
    out.append(f"#define HCU_C2_IMAGE_PACKAGE_BYTES {package_bytes}u")
    out.append(f"static const uint8_t HCU_C2_IMAGE_PACKAGE_SHA256[32] = {sha_array(package_sha)};")
    out.append(f"#define HCU_C2_IMAGE_METADATA_BYTES {len(blob)}u")
    out.append(f"#define HCU_C2_IMAGE_METADATA_STORAGE_BYTES {storage_bytes}u")
    out.append(f"static const uint8_t HCU_C2_IMAGE_METADATA_SHA256[32] = {sha_array(metadata_sha)};")
    out.append(f"#define HCU_C2_IMAGE_RELOCATION_BYTES {relocation_bytes}u")
    out.append("static const uint8_t HCU_C2_IMAGE_METADATA[HCU_C2_IMAGE_METADATA_BYTES] = {")
    out.append(byte_array(blob))
    out.append("};")
    out.append("")
    out.append(f"#define HCU_C2_IMAGE_SOURCE_COUNT {len(sources)}u")
    out.append("typedef struct { const char *key; const char *path; uint32_t bytes; uint8_t sha256[32]; } hcu_c2_image_source;")
    out.append("static const hcu_c2_image_source HCU_C2_IMAGE_SOURCES[HCU_C2_IMAGE_SOURCE_COUNT] = {")
    for s in sources:
        out.append(f'\t{{ "{s["key"]}", "{s["path"]}", {s["bytes"]}u, {sha_array(s["sha256"])} }},')
    out.append("};")
    out.append("")
    out.append(f"#define HCU_C2_IMAGE_DATUM_COUNT {len(datum_source)}u")
    out.append("typedef struct { uint32_t output_datum; uint8_t source; } hcu_c2_image_datum;")
    out.append("static const hcu_c2_image_datum HCU_C2_IMAGE_DATUMS[HCU_C2_IMAGE_DATUM_COUNT] = {")
    for datum in sorted(datum_source):
        out.append(f"\t{{ {datum}u, {index_of[datum_source[datum]]} }},")
    out.append("};")
    out.append("")
    out.append("#endif")
    out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--row", required=True, help="partition row name, e.g. sidewinder_marine_shotgun_4p4bot")
    parser.add_argument("--package-root", type=Path, default=DEFAULT_PACKAGE_ROOT,
                        help="directory holding one <row>/ package folder per row")
    parser.add_argument("--asset-root", type=Path, default=ROOT,
                        help="directory the EE host: root maps to; paths in the header are relative to it")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        text = build_header(args.row, args.package_root, args.asset_root)
    except HeaderError as exc:
        print(f"c2_profile_image_header: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(json.dumps({"row": args.row, "output": str(args.output), "bytes": len(text)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
