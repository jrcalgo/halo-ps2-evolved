#!/usr/bin/env python3
"""Dry-run the C3 object working set of a profile package (read-only).

The residency pool copies each mode model's MODL chunk and its OTEX chunk at 64-byte
alignment. This prints that sum, the sum with scenery counted at LOD2, and both against
the pool. Scenery LOD2 uses the LOD2 plan from tools/hcu_c3_object_classes.py when the
manifest records a byte size for each stored LOD. A manifest without those sizes has no
per-LOD split, so the scenery line is the full-chunk total. Nothing is written.

Usage:
  python3 -I tools/hcu_c3_working_set.py --package-dir build/c3/bloodgulch/pkg/bloodgulch_mounted_gunner_4p4bot
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_c3_objects_measure as measure  # noqa: E402
import hcu_c3_objects_table as table  # noqa: E402

# Above the packaged manifests (about 7 MB). A larger file is not loaded whole.
_MANIFEST_LOAD_MAX = 64 * 1024 * 1024
_LOD_KEYS = ("lod_bytes", "per_lod_bytes")


def is_scenery(path: str) -> bool:
    """True for a model whose tag path is in the scenery tree."""
    return path.replace("/", "\\").lower().startswith("scenery\\")


def _lod_list(obj: dict) -> list[int] | None:
    for key in _LOD_KEYS:
        raw = obj.get(key)
        if not isinstance(raw, list) or not raw:
            continue
        if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in raw):
            return [int(n) for n in raw]
    return None


def lod_bytes_by_path(manifest: dict) -> dict[str, list[int]]:
    """Stored-LOD byte lists keyed by model path, when the manifest records them."""
    by_sha: dict[str, list[int]] = {}
    for chunk in (manifest.get("media") or {}).get("chunks") or []:
        if chunk.get("kind") != "MODL":
            continue
        raw = _lod_list(chunk)
        sha = chunk.get("sha256")
        if raw is not None and sha:
            by_sha[sha] = raw
    found: dict[str, list[int]] = {}
    for binding in manifest.get("chunk_bindings") or []:
        if binding.get("kind") != "MODL":
            continue
        path = (binding.get("owner") or {}).get("path")
        if not path:
            continue
        raw = _lod_list(binding)
        if raw is None:
            raw = by_sha.get(binding.get("sha256"))
        if raw is None:
            continue
        previous = found.get(path)
        if previous is not None and previous != raw:
            raise SystemExit(f"{path}: manifest per-LOD sizes disagree")
        found[path] = raw
    return found


def media_sha_sizes(manifest: dict) -> dict[str, int]:
    """sha256 -> logical chunk bytes for MODL and OTEX rows in the manifest media summary."""
    sizes: dict[str, int] = {}
    for chunk in (manifest.get("media") or {}).get("chunks") or []:
        if chunk.get("kind") not in ("MODL", "OTEX") or "bytes" not in chunk:
            continue
        sha = chunk.get("sha256")
        if not sha:
            continue
        size = int(chunk["bytes"])
        previous = sizes.get(sha)
        if previous is not None and previous != size:
            raise SystemExit(f"manifest disagrees on the size of {sha}")
        sizes[sha] = size
    return sizes


def directory_logical_sizes(path: Path) -> dict[int, int]:
    """Media chunk id -> logical size, from the HCP2 directory. Payloads are not read."""
    record = measure.HCP_RECORD.size
    with path.open("rb") as fh:
        raw = fh.read(measure.HCP_HEADER.size)
        if len(raw) < measure.HCP_HEADER.size:
            raise SystemExit(f"short HCP header: {path}")
        magic, version, _hs, _pid, count, dir_off, dsize, _total = measure.HCP_HEADER.unpack(raw)
        if magic != b"HCP2" or version != 2:
            raise SystemExit(f"not an HCP2 pack: {path}")
        nbytes = count * record
        if count < 1 or nbytes != dsize or nbytes > 65536 * record:
            raise SystemExit(f"HCP2 directory is not usable: {path}")
        fh.seek(dir_off)
        blob = fh.read(nbytes)
    if len(blob) != nbytes:
        raise SystemExit(f"short HCP2 directory: {path}")
    sizes: dict[int, int] = {}
    for i in range(count):
        kind, cid, _off, _size, _loff, logical, index, _n, _seg, _whole = measure.HCP_RECORD.unpack_from(blob, i * record)
        if kind == 2 and index == 0:
            sizes[cid] = logical
    return sizes


def resolve_sizes(manifest: dict, rows: list[dict], package_dir: Path, row_name: str) -> dict[str, int]:
    """Logical sizes for the selected chunks. The media summary is enough when it carries bytes."""
    by_sha = media_sha_sizes(manifest)

    def missing(row: dict) -> bool:
        if row["model_sha256"] not in by_sha:
            return True
        return bool(row["texture_chunk"]) and row["texture_sha256"] not in by_sha

    if any(missing(row) for row in rows):
        hcp = package_dir / f"{row_name}.hcp"
        if not hcp.is_file():
            raise SystemExit(f"manifest is missing MODL/OTEX sizes and {hcp.name} is absent")
        by_id = directory_logical_sizes(hcp)
        for row in rows:
            if row["model_sha256"] not in by_sha:
                if row["model_chunk"] not in by_id:
                    raise SystemExit(f"{row['path']}: MODL size is not in the manifest or the HCP directory")
                by_sha[row["model_sha256"]] = by_id[row["model_chunk"]]
            if row["texture_chunk"] and row["texture_sha256"] not in by_sha:
                if row["texture_chunk"] not in by_id:
                    raise SystemExit(f"{row['path']}: OTEX size is not in the manifest or the HCP directory")
                by_sha[row["texture_sha256"]] = by_id[row["texture_chunk"]]
    return by_sha


def aligned_entry(row: dict, sizes: dict[str, int], model_bytes: int | None = None) -> int:
    """Pool bytes of one table entry: aligned MODL plus aligned OTEX. model_bytes overrides the chunk."""
    model = sizes[row["model_sha256"]] if model_bytes is None else model_bytes
    total = measure.align(model)
    if row["texture_chunk"]:
        total += measure.align(sizes[row["texture_sha256"]])
    return total


def lod2_slots() -> set[int]:
    """Stored LOD indices the class search's LOD2 plan keeps (one geometry when every slot agrees)."""
    import hcu_c3_object_classes as classes

    for label, slots in classes.lod_plans():
        if label == "LOD2":
            return set(slots)
    raise SystemExit("hcu_c3_object_classes has no LOD2 plan")


def scenery_lod2_total(rows: list[dict], sizes: dict[str, int], lod_of: dict[str, list[int]]) -> int | None:
    """Full-chunk bytes, with scenery models reduced to the LOD2 plan. None when a scenery model has no split."""
    scenery = [row for row in rows if is_scenery(row["path"])]
    if not scenery or any(row["path"] not in lod_of for row in scenery):
        return None
    keep = sorted(lod2_slots())
    total = 0
    for row in rows:
        if is_scenery(row["path"]):
            parts = lod_of[row["path"]]
            if any(index >= len(parts) for index in keep):
                return None
            total += aligned_entry(row, sizes, sum(parts[index] for index in keep))
        else:
            total += aligned_entry(row, sizes)
    return total


def load_manifest(path: Path) -> dict:
    size = path.stat().st_size
    if size > _MANIFEST_LOAD_MAX:
        raise SystemExit(f"{path} is {size} B; refusing to load it (chunk sizes only, and this file is past the cap)")
    return json.loads(path.read_text())


def report(row: str, aligned: int, lod: int | None, pool: int) -> None:
    print(f"{row}: aligned MODL+OTEX {aligned} B")
    if lod is None:
        print("manifest has no per-LOD sizes")
        print(f"scenery LOD2 full-chunk total {aligned} B")
        lod = aligned
    else:
        print(f"scenery LOD2 {lod} B")
    print(f"pool {pool} B  aligned fits={aligned <= pool}  scenery-lod2 fits={lod <= pool}")
    print(f"aligned minus pool {aligned - pool} B  scenery-lod2 minus pool {lod - pool} B")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package-dir", type=Path, required=True)
    ap.add_argument("--row", help="package row name (default: the directory name)")
    ap.add_argument("--pool-bytes", type=int, default=measure.POOL_BYTES_DEFAULT)
    args = ap.parse_args(argv)
    row = args.row or args.package_dir.name
    manifest_path = args.package_dir / f"{row}.json"
    if not manifest_path.is_file():
        raise SystemExit(f"manifest missing: {manifest_path}")
    manifest = load_manifest(manifest_path)
    rows = table.select(manifest)
    sizes = resolve_sizes(manifest, rows, args.package_dir, row)
    aligned = sum(aligned_entry(row_entry, sizes) for row_entry in rows)
    lod = scenery_lod2_total(rows, sizes, lod_bytes_by_path(manifest))
    report(row, aligned, lod, args.pool_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
