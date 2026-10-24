"""Audit schema-aware CTAG compaction across the supplied retail map corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

try:
    from .convert_retail_ctag import convert_retail_map
    from .hcu_schema_manifest import Elf32, SchemaManifest
except ImportError:
    from convert_retail_ctag import convert_retail_map
    from hcu_schema_manifest import Elf32, SchemaManifest


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(maps_dir: Path, schema_elf: Path) -> dict:
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    rows = []
    failures = []
    paths = sorted(maps_dir.glob("*.map"))
    for index, path in enumerate(paths, 1):
        try:
            payload, summary = convert_retail_map(path, manifest=manifest)
            rows.append({
                **summary,
                "source_sha256": sha256(path),
                "ctag_sha256": hashlib.sha256(payload).hexdigest(),
            })
            print(f"[{index}/{len(paths)}] {path.name}: ok ({summary['image_size']} bytes)",
                  file=sys.stderr, flush=True)
        except (OSError, ValueError) as error:
            failures.append({"map": path.name, "error": str(error)})
            print(f"[{index}/{len(paths)}] {path.name}: FAILED ({error})",
                  file=sys.stderr, flush=True)
    if not rows and not failures:
        raise ValueError(f"no retail maps found in {maps_dir}")
    return {
        "format": "retail-ctag-compaction-audit-v1",
        "schema_elf": str(schema_elf),
        "schema_elf_sha256": sha256(schema_elf),
        "map_count": len(rows) + len(failures),
        "successful_map_count": len(rows),
        "failure_count": len(failures),
        "maps": rows,
        "failures": failures,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", type=Path, help="decompressed retail Xbox map directory")
    parser.add_argument("schema_elf", type=Path, help="linked HCU ELF")
    parser.add_argument("--output", type=Path, help="new JSON output path; stdout when omitted")
    args = parser.parse_args(argv)
    try:
        result = audit(args.maps, args.schema_elf)
        rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            if args.output.exists():
                parser.error(f"refusing to overwrite existing output: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered)
        else:
            print(rendered, end="")
    except (OSError, ValueError) as error:
        parser.exit(2, f"retail CTAG audit failed: {error}\n")
    return 0 if result["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
