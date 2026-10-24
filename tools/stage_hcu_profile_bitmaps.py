#!/usr/bin/env python3
"""Stage independently-addressable serialized bitmaps from a pinned profile diagnostic.

This writes bitmap chunks and a deterministic staging catalog. It never marks
the assets as admitted to a live UI, effect, or sprite renderer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from hcu_profile_bitmap import serialize_bitmap  # noqa: E402
from halo2ps2 import texconv  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402


FORMAT = "hcu-profile-bitmap-staging-v1"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _expected_ctag_path(diagnostic_path: Path, diagnostic: dict) -> Path:
    profile = str(diagnostic.get("profile", ""))
    if not profile or Path(profile).name != profile or profile in (".", ".."):
        raise ValueError("diagnostic has no safe profile name for its sibling CTAG")
    return diagnostic_path.parent / f"{profile}.unadmitted.ctag"


def _identity(row: dict) -> dict:
    return {
        "source_key": str(row.get("source", "")),
        "group": str(row.get("group", "")),
        "path": str(row.get("path", "")),
        "source_datum": int(row.get("source_datum", -1)),
    }


def _error_row(owner: dict, error: Exception) -> dict:
    match = re.search(r"\[(\d+)\]", str(error))
    return {
        **owner,
        "status": "failed",
        "failure": str(error),
        "image_index": int(match.group(1)) if match else None,
        "runtime_admitted": False,
    }


def stage_profile_bitmaps(diagnostic_path: Path, schema_elf_path: Path,
                          output_path: Path, ctag_path: Path | None = None) -> int:
    diagnostic_path = diagnostic_path.resolve()
    schema_elf_path = schema_elf_path.resolve()
    output_path = output_path.resolve()
    diagnostic_bytes = diagnostic_path.read_bytes()
    diagnostic_hash = _sha_bytes(diagnostic_bytes)
    diagnostic = json.loads(diagnostic_bytes)
    ctag_path = (ctag_path or _expected_ctag_path(diagnostic_path, diagnostic)).resolve()

    # Replace any earlier status immediately. A failed pin check can therefore
    # never leave a stale staged/complete catalog at this requested destination.
    catalog = {
        "format": FORMAT,
        "status": "incomplete",
        "runtime_admitted": False,
        "diagnostic_path": diagnostic_path.relative_to(ROOT).as_posix()
            if diagnostic_path.is_relative_to(ROOT) else str(diagnostic_path),
        "diagnostic_sha256": diagnostic_hash,
        "schema_elf_path": schema_elf_path.relative_to(ROOT).as_posix()
            if schema_elf_path.is_relative_to(ROOT) else str(schema_elf_path),
        "schema_elf_sha256": None,
        "ctag_path": ctag_path.relative_to(ROOT).as_posix()
            if ctag_path.is_relative_to(ROOT) else str(ctag_path),
        "ctag_sha256": None,
        "profile": diagnostic.get("profile"),
        "diagnostic_failure_stage": diagnostic.get("failure_stage"),
        "diagnostic_error": diagnostic.get("error"),
        "diagnostic_tag_count": diagnostic.get("tag_count"),
        "source_maps": {},
        "roots": diagnostic.get("roots", []),
        "assets": [],
        "chunks": [],
        "failures": [],
        "storage": {"unique_chunk_bytes": 0, "unique_chunk_count": 0,
                    "max_selected_decoded_bytes": 0,
                    "max_selected_serialized_chunk_bytes": 0,
                    "decoded_byte_basis": "largest selected base image width × height × 4 RGBA8"},
    }
    output_path.mkdir(parents=True, exist_ok=True)
    _canonical_write(output_path / "catalog.json", catalog)

    def fail(message: str) -> int:
        catalog["status"] = "incomplete"
        catalog["failures"].append({"stage": "preflight", "failure": message})
        _canonical_write(output_path / "catalog.json", catalog)
        return 2

    if diagnostic.get("format") != "hcu-profile-diagnostic-v1":
        return fail("unsupported profile diagnostic format")
    if not schema_elf_path.is_file():
        return fail(f"schema ELF is missing: {schema_elf_path}")
    schema_hash = _sha_file(schema_elf_path)
    catalog["schema_elf_sha256"] = schema_hash
    if schema_hash != diagnostic.get("schema_elf_sha256"):
        return fail("schema ELF SHA-256 does not match the diagnostic pin")
    if not ctag_path.is_file():
        return fail(f"diagnostic CTAG is missing: {ctag_path}")
    ctag_hash = _sha_file(ctag_path)
    catalog["ctag_sha256"] = ctag_hash
    if ctag_hash != diagnostic.get("unadmitted_ctag_sha256"):
        return fail("CTAG SHA-256 does not match the diagnostic pin")

    source_rows = diagnostic.get("source_maps")
    if not isinstance(source_rows, dict) or not source_rows:
        return fail("diagnostic has no pinned source maps")
    source_paths: dict[str, Path] = {}
    # Validate every input source before opening maps or calling the serializer.
    for source_key in sorted(source_rows):
        row = source_rows[source_key]
        source_path = _repo_path(str(row.get("path", ""))).resolve()
        expected_hash = str(row.get("sha256", ""))
        if not source_path.is_file():
            return fail(f"source map {source_key} is missing: {row.get('path')}")
        actual_hash = _sha_file(source_path)
        catalog["source_maps"][source_key] = {
            "path": source_path.relative_to(ROOT).as_posix()
                if source_path.is_relative_to(ROOT) else str(source_path),
            "sha256": actual_hash,
        }
        source_paths[source_key] = source_path
        if not expected_hash or actual_hash != expected_hash:
            return fail(f"source map {source_key} SHA-256 does not match the diagnostic pin")

    try:
        schema = SchemaManifest(Elf32(schema_elf_path)).build()
    except Exception as error:  # preserve exact compiler-schema failure
        return fail(f"cannot build compiler schema manifest: {error}")
    if schema.get("elf_sha256") != schema_hash:
        return fail("generated compiler schema manifest ELF hash disagrees with input ELF")

    dependencies = diagnostic.get("dependencies", [])
    owners_by_identity: dict[tuple[str, int], dict] = {}
    for row in dependencies:
        if row.get("group") != "bitm":
            continue
        owner = _identity(row)
        key = (owner["source_key"], owner["source_datum"])
        if owner["source_key"] not in source_rows:
            return fail(f"bitmap dependency names unpinned source {owner['source_key']}")
        expected = source_rows[owner["source_key"]].get("sha256")
        if row.get("source_sha256") != expected:
            return fail(f"bitmap dependency source hash disagrees with pinned map for {owner['path']}")
        previous = owners_by_identity.get(key)
        if previous and previous != owner:
            return fail(f"bitmap datum has conflicting diagnostic identities: {key}")
        owners_by_identity[key] = owner
    owners = sorted(owners_by_identity.values(),
                    key=lambda x: (x["source_key"], x["path"], x["source_datum"]))

    try:
        sources = {key: texconv.MapData.open(path) for key, path in source_paths.items()}
    except Exception as error:
        return fail(f"cannot open pinned retail source map: {error}")

    chunks_by_hash: dict[str, dict] = {}
    output_path.joinpath("chunks").mkdir(parents=True, exist_ok=True)
    for owner in owners:
        source_map = sources.get(owner["source_key"])
        if source_map is None:
            catalog["failures"].append(_error_row(owner, ValueError("source map was not opened")))
            continue
        try:
            asset = serialize_bitmap(sources, owner, schema)
            asset_chunks = []
            decoded_bytes = 0
            unique_asset_hashes = set()
            unique_asset_bytes = 0
            for chunk in asset["chunks"]:
                payload = chunk["data"]
                digest = _sha_bytes(payload)
                if digest != chunk["sha256"]:
                    raise ValueError("serializer payload digest does not match its chunk record")
                chunk_path = output_path / "chunks" / f"{digest}.bitm"
                if digest not in chunks_by_hash:
                    if chunk_path.exists() and _sha_file(chunk_path) != digest:
                        chunk_path.unlink()
                    if not chunk_path.exists():
                        chunk_path.write_bytes(payload)
                    chunks_by_hash[digest] = {
                        "key": f"BITM:{digest}", "kind": "BITM", "path": f"chunks/{digest}.bitm",
                        "bytes": len(payload), "sha256": digest,
                    }
                    if digest not in unique_asset_hashes:
                        unique_asset_bytes += len(payload)
                elif chunk_path.read_bytes() != payload:
                    raise ValueError("same chunk hash resolved to different serialized bytes")
                if digest not in unique_asset_hashes:
                    unique_asset_hashes.add(digest)
                asset_chunks.append({k: chunk[k] for k in (
                    "key", "kind", "bytes", "sha256", "texture_source_id", "width", "height",
                    "psm", "image_format", "source_pixel_offset", "source_pixel_bytes",
                    "source_pixel_sha256")})
                decoded_bytes = max(decoded_bytes, int(chunk["width"]) * int(chunk["height"]) * 4)
            asset_row = {
                **owner,
                "status": "staged",
                "runtime_admitted": False,
                "decision": asset["decision"],
                "source_sha256": asset["source_sha256"],
                "asset_format": asset["format"],
                "sequences": asset["sequences"],
                "images": asset_chunks,
                "dispositions": asset["dispositions"],
                "logical_serialized_bytes": sum(c["bytes"] for c in asset_chunks),
                "unique_serialized_bytes": unique_asset_bytes,
                "max_selected_decoded_bytes": decoded_bytes,
            }
            catalog["assets"].append(asset_row)
            catalog["storage"]["max_selected_decoded_bytes"] = max(
                catalog["storage"]["max_selected_decoded_bytes"], decoded_bytes)
            catalog["storage"]["max_selected_serialized_chunk_bytes"] = max(
                catalog["storage"]["max_selected_serialized_chunk_bytes"],
                max((c["bytes"] for c in asset_chunks), default=0))
            catalog["storage"]["unique_chunk_bytes"] = sum(x["bytes"] for x in chunks_by_hash.values())
            catalog["storage"]["unique_chunk_count"] = len(chunks_by_hash)
        except Exception as error:
            catalog["failures"].append(_error_row(owner, error))
        _canonical_write(output_path / "catalog.json", catalog)

    catalog["chunks"] = sorted(chunks_by_hash.values(), key=lambda x: x["sha256"])
    catalog["producer"] = {
        "serializer_path": "tools/hcu_profile_bitmap.py",
        "serializer_sha256": _sha_file(ROOT / "tools/hcu_profile_bitmap.py"),
        "stager_path": "tools/stage_hcu_profile_bitmaps.py",
        "stager_sha256": _sha_file(Path(__file__).resolve()),
    }
    catalog["status"] = "incomplete" if catalog["failures"] else "staged"
    catalog["runtime_admitted"] = False
    _canonical_write(output_path / "catalog.json", catalog)
    return 2 if catalog["failures"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--schema-elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ctag", type=Path,
                        help="pinned CTAG (default: <profile>.unadmitted.ctag beside diagnostic)")
    args = parser.parse_args()
    result = stage_profile_bitmaps(args.diagnostic, args.schema_elf, args.output, args.ctag)
    catalog_path = args.output / "catalog.json"
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text())
        print(json.dumps({"status": catalog.get("status"), "assets": len(catalog.get("assets", [])),
                          "chunks": len(catalog.get("chunks", [])),
                          "failures": catalog.get("failures", []),
                          "catalog": str(catalog_path)}, indent=2))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
