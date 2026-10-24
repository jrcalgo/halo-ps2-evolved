#!/usr/bin/env python3
"""Derive a source-pinned CE bitmap-index to final HCP BITM chunk table."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hcu_profile_validate import parse_package


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(manifest_path: Path, package_path: Path, *, cache_key_base: int = 0) -> dict:
    manifest_path, package_path = Path(manifest_path), Path(package_path)
    manifest = json.loads(manifest_path.read_text())
    package = package_path.read_bytes()
    package_sha = hashlib.sha256(package).hexdigest()
    if manifest.get("package_sha256") != package_sha:
        raise ValueError("manifest package SHA-256 does not match final HCP bytes")
    profile_id = int(manifest["profile"]["id"])
    parsed = parse_package(package, expected_package_sha256=package_sha,
                           expected_profile_id=profile_id)
    rows = []
    for binding in manifest.get("chunk_bindings", []):
        if binding.get("kind") != "BITM":
            continue
        owner = binding.get("owner", {})
        if owner.get("group") != "bitm":
            raise ValueError("BITM chunk binding has non-BITM owner")
        chunk_id = int(binding["chunk_id"])
        image = int(binding.get("source_image_index", owner.get("source_image_index", -1)))
        output_datum = int(owner["output_datum"])
        # The currently registered CE capture identifies bitmap-group element
        # index; serializer emits one image per independently addressed chunk.
        if image < 0 or image > 0xFFFF or output_datum < 0 or output_datum > 0xFFFFFFFF:
            raise ValueError("BITM identity outside dispatcher range")
        if (2, chunk_id) not in parsed["chunks"]:
            raise ValueError(f"final HCP lacks media chunk {chunk_id}")
        if hashlib.sha256(parsed["chunks"][(2, chunk_id)]).hexdigest() != binding["sha256"]:
            raise ValueError(f"final HCP BITM chunk {chunk_id} does not match manifest pin")
        cache_key = cache_key_base + chunk_id
        if not 0 <= cache_key < 4096:
            raise ValueError("cache key base plus media chunk id exceeds tc_t namespace")
        rows.append({"bitmap_output_datum": output_datum, "bitmap_index": image,
                     "image_index": 0, "chunk_id": chunk_id,
                     "cache_key": cache_key, "source_datum": int(owner["source_datum"]),
                     "expected_profile_id": profile_id,
                     "expected_chunk_sha256_bytes": list(bytes.fromhex(binding["sha256"])),
                     "path": owner["path"], "source_image_index": image,
                     "chunk_sha256": binding["sha256"], "runtime_admitted": False})
    rows.sort(key=lambda r: (r["bitmap_output_datum"], r["bitmap_index"], r["chunk_id"]))
    identities = [(r["bitmap_output_datum"], r["bitmap_index"]) for r in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("ambiguous CE bitmap identity in final manifest")
    return {"format": "hcu-c1-bitmap-bindings-v1", "runtime_admitted": False,
            "profile": manifest["profile"], "package": {"path": str(package_path),
                "sha256": package_sha, "bytes": len(package)},
            "manifest": {"path": str(manifest_path), "sha256": sha(manifest_path)},
            "schema_elf_sha256": manifest.get("schema_elf_sha256"),
            "cache_key_base": cache_key_base, "binding_count": len(rows), "bindings": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache-key-base", type=int, default=0)
    args = parser.parse_args(argv)
    result = build(args.manifest, args.package, cache_key_base=args.cache_key_base)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"binding_count": result["binding_count"],
                      "package_sha256": result["package"]["sha256"],
                      "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
