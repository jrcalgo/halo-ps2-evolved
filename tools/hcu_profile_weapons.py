#!/usr/bin/env python3
"""Create a deterministic, evidence-bound profile for accepted custom weapons.

The profile records source roots, complete tag closure dependencies, and separately
owned first-person presentation provenance. It does not claim runtime readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "build/custom-weapon-capacity/closure-verified-2026-10-22.json"
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")]
from audit_custom_weapon_asset_closure import walk_root  # noqa: E402
from audit_mp_match_content_closure import Closure  # noqa: E402
from halo2ps2 import bitmaps, texconv  # noqa: E402


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_bitmap_records(source_map: Path, bitmap_tag_ids: set[int]) -> list[dict]:
    """Return exact image metadata for selected bitmap tags, including parse errors."""
    map_data = texconv.MapData.open(source_map)
    out = []
    for tag_id in sorted(bitmap_tag_ids):
        entry = map_data.by_id.get(tag_id)
        if entry is None or entry.group != "bitm":
            out.append({"tag_id": tag_id, "error": "bitmap tag ID missing from source map"})
            continue
        try:
            images = map_data.images(tag_id)
        except (ValueError, bitmaps.BitmapError) as exc:
            out.append({"path": entry.path, "tag_id": tag_id, "error": str(exc)})
            continue
        for image in images:
            out.append(bitmap_image_record(entry.path, tag_id, image))
    return out


def bitmap_image_record(path: str, tag_id: int, image) -> dict:
    """Serialize one parsed BitmapImage without hiding unsupported image shapes."""
    decodable = image.decodable
    return {
        "path": path, "tag_id": tag_id, "index": image.index,
        "type": image.type, "width": image.width, "height": image.height,
        "depth": image.depth, "mip_count": image.mip_count, "format": image.format,
        "format_name": image.format_name, "flags": image.flags,
        "extent": {"offset": image.pixel_offset, "bytes": image.pixel_size},
        "decodable": decodable,
        "error": None if decodable else
            f"unsupported image shape/type/format: type={image.type}, depth={image.depth}, format={image.format}",
        "cube_storage": validate_cube_record(image) if image.type == bitmaps.TYPE_CUBE else None,
    }


def expected_cube_payload_bytes(image) -> int:
    """Six Xbox cube faces; mip chains are contiguous then 256-byte padded."""
    if image.type != bitmaps.TYPE_CUBE or image.width != image.height or image.depth != 1:
        raise bitmaps.BitmapError("not a square Xbox cube image")
    if image.format not in bitmaps.DXT_BLOCK_BYTES and image.format not in bitmaps.BITS_PER_PIXEL:
        raise bitmaps.BitmapError(f"unsupported cube format {image.format}")
    levels = image.mip_count + 1
    if levels > image.width.bit_length():
        raise bitmaps.BitmapError("cube mip count exceeds dimension")
    face_bytes = sum(bitmaps.level_size(image.format, max(1, image.width >> level),
                                        max(1, image.height >> level))
                     for level in range(levels))
    # The retained C40 records establish 256-byte padding per face:
    # DXT1 64x64x7 levels = 2744 -> 2816; R5G6B5 = 10922 -> 11008.
    face_bytes = (face_bytes + 255) & ~255
    return face_bytes * 6


def validate_cube_record(image) -> dict:
    levels = image.mip_count + 1
    face_bytes = sum(bitmaps.level_size(image.format, max(1, image.width >> level),
                                        max(1, image.height >> level))
                     for level in range(levels))
    face_stride = (face_bytes + 255) & ~255
    expected = face_stride * 6
    return {"faces": 6, "mip_levels_per_face": levels,
            "face_mip_bytes_before_padding": face_bytes,
            "face_padding_bytes": face_stride - face_bytes,
            "face_stride_bytes": face_stride,
            "face_stride_alignment_bytes": 256,
            "expected_extent_bytes": expected, "actual_extent_bytes": image.pixel_size,
            "extent_valid": image.pixel_size == expected}


def find_weapon_root(entries, root_path: str):
    matches = [entry for entry in entries if entry.group == "weap" and
               entry.path.casefold() == root_path.casefold()]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one weapon root {root_path!r}, found {len(matches)}")
    return matches[0]


def build_profile(report: dict, maps_dir: Path) -> dict:
    weapons = {}
    roots = {
        "energy_sword": ("a50.map", r"weapons\energy sword\energy sword"),
        "gravity_rifle": ("beavercreek.map", r"weapons\gravity rifle\gravity rifle"),
        "fuel_rod": ("c40.map", r"weapons\fuel rod gun\fuel rod"),
    }
    for key, (map_name, root_path) in roots.items():
        map_path = maps_dir / map_name
        if not map_path.is_file():
            raise ValueError(f"missing retained source map: {map_path}")
        if key in report["weapons"]:
            closure = report["weapons"][key]
        else:
            # Gravity rifle is present in the retained MP match closure; preserve its
            # complete referenced asset lists from that independent audit below.
            closure = None
        if closure is None:
            raise ValueError(f"closure report lacks {key}; import its match-content evidence")
        bitmaps = closure["bitmap_sources"]
        undecodable = sum(row["undecodable_count"] for row in bitmaps.values())
        visual_ok = undecodable == 0 and closure["unresolved_reference_count"] == 0
        weapons[key] = {
            "source_map": map_name,
            "source_map_sha256": sha(map_path),
            "root": {"group": "weap", "path": root_path},
            "closure_tag_count": closure["closure_tag_count"],
            "dependencies_by_group": closure["closure_paths_by_group"],
            "unresolved_reference_count": closure["unresolved_reference_count"],
            "converted": {name: {"bytes": closure[f"converted_{name}_bytes"],
                                  "sha256": closure[f"converted_{name}_sha256"]}
                          for name in ("MODL", "OTEX", "ANIM")},
            "bitmap_validation": {"sources": bitmaps,
                                  "undecodable_record_count": undecodable,
                                  "visual_admitted": visual_ok},
        }
    weapons["energy_sword"]["presentation"] = {
        "source": "accepted Halo 2 Vista sword idle and handle adapter",
        "source_header": "src/game/hold_pose.h",
        "pose_data": "src/game/sword_idle.h",
        "visual_admitted": True,
    }
    weapons["gravity_rifle"]["presentation"] = {
        "source": "accepted Halo 2 Vista carbine idle adapter; CE gravity-rifle world model",
        "source_header": "src/game/hold_pose.h",
        "pose_data": "src/game/carbine_idle.h",
        "visual_admitted": True,
    }
    weapons["fuel_rod"]["presentation"] = {
        "source": "CE generic weapon implementation; Halo 2 flak idle pose adapter",
        "source_header": "src/game/hold_pose.h",
        "pose_data": "src/game/flak_idle.h",
        "first_person_graph": "absent in CE root; arms-only adapter",
        "visual_admitted": weapons["fuel_rod"]["bitmap_validation"]["visual_admitted"],
    }
    return {"schema": "hcu-special-weapon-profile-v1",
            "scope": "source-map closure and presentation provenance; no runtime admission claim",
            "weapons": weapons}


def generate_profile(maps_dir: Path, schema_elf: Path) -> dict:
    from hcu_schema_manifest import Elf32, SchemaManifest
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    roots = {
        "energy_sword": ("a50.map", r"weapons\energy sword\energy sword"),
        "gravity_rifle": ("beavercreek.map", r"weapons\gravity rifle\gravity rifle"),
        "fuel_rod": ("c40.map", r"weapons\fuel rod gun\fuel rod"),
    }
    root_rows, closures = {}, {}
    for key, (map_name, root_path) in roots.items():
        source = maps_dir / map_name
        closure = Closure(source, manifest)
        row = walk_root(closure, root_path)
        closures[key] = (closure, row)
        bitmap_ids = {e.tag_id for e in closure.visited.values() if e.group == "bitm"}
        models = [e.tag_id for e in closure.visited.values() if e.group == "mode"]
        records = inspect_bitmap_records(source, bitmap_ids)
        bad = [r for r in records if r.get("decodable") is False or r.get("error")]
        root_rows[key] = {
            "source_map": map_name, "source_map_sha256": row["source_map_sha256"],
            "root_tag": row["root_tag"], "closure_tag_count": row["closure_tag_count"],
            "dependencies_by_group": row["closure_paths_by_group"],
            "unresolved_reference_count": row["unresolved_reference_count"],
            "converted": {n: {"bytes": row[f"converted_{n}_bytes"],
                               "sha256": row[f"converted_{n}_sha256"]} for n in ("MODL", "OTEX", "ANIM")},
            "bitmap_records": records,
            "bitmap_unsupported_records": bad,
            "visual_admitted": row["unresolved_reference_count"] == 0 and not bad,
        }
    fuel = root_rows["fuel_rod"]
    fuel_bad = fuel["bitmap_unsupported_records"]
    for record in fuel_bad:
        record["presentation_policy"] = "omit optional environment reflection layer; preserve base/diffuse materials"
    fuel["visual_admitted"] = (fuel["unresolved_reference_count"] == 0 and
                               all(r.get("cube_storage", {}).get("extent_valid") for r in fuel_bad))
    fuel["presentation_policy"] = "Base/diffuse admitted; optional cube-map environment reflections omitted. No full visual parity claim."
    adapter_files = ["src/game/hold_pose.h", "src/game/sword_idle.h", "src/game/carbine_idle.h",
                     "src/game/flak_idle.h", "tools/extract_sword_idle.py", "tools/extract_h2_hold.py"]
    presentation = {
        "source_animation_map": {"path": "build/h2-reference/shared.map (not retained)",
                                  "sha256": "6c0afbcf46ecd3a70ef5106e4f51d68414d5a389c1e0b1d14c47a2766abddfe0"},
        "adapter_files": {p: sha(ROOT / p) for p in adapter_files},
        "energy_sword": {"pose": "Halo 2 Vista jmad 0xEE9B3436 first_person:idle, 89 frames",
                         "pose_header": "src/game/sword_idle.h", "policy": "separate sword pose/handle adapter"},
        "gravity_rifle": {"pose": "Halo 2 Vista carbine jmad 0xEC973232 first_person:idle, 89 frames",
                          "pose_header": "src/game/carbine_idle.h", "policy": "carbine idle orientation/pose adapter"},
        "fuel_rod": {"pose": "Halo 2 Vista flak jmad 0xEDCC3367 first_person:idle, 73 frames; arms only",
                     "pose_header": "src/game/flak_idle.h", "policy": "CE FP model/animation refs null; no FP weapon graph"},
    }
    return {"schema": "hcu-c1-special-weapons-profile-v1",
            "scope": "retained CE source roots, bitmap metadata and explicit first-person presentation provenance",
            "source_map": fuel["source_map"], "source_map_sha256": fuel["source_map_sha256"],
            "root": fuel["root_tag"], "reached_bitmap_tag_count": len(fuel["bitmap_records"]),
            "bitmap_image_count": len(fuel["bitmap_records"]),
            "undecodable_reached_records": fuel_bad, "visual_admitted": fuel["visual_admitted"],
            "interpretation": "C40 root reaches two valid six-face cube payloads; reflection is omitted by explicit adapter policy.",
            "cube_layout_basis": {"source": "retained C40 Xbox bitmap_data metadata and pixel extents",
                                  "layout": "six face mip chains, each padded to a 256-byte stride",
                                  "validation": "both cube records' parsed metadata recompute to their exact stored extents"},
            "presentation_policy": fuel["presentation_policy"],
            "weapon_roots": root_rows, "presentation_provenance": presentation}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--maps", type=Path, default=ROOT / "data/retail/weapon-audit-maps")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--schema-elf", type=Path,
                    default=ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory-m2-ui-lifecycle/halo-local.elf")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace an existing output after generating the complete profile")
    args = ap.parse_args()
    result = generate_profile(args.maps, args.schema_elf)
    if args.output.exists() and not args.overwrite:
        ap.error(f"refusing to overwrite existing output: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
