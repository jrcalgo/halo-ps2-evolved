#!/usr/bin/env python3
"""Audit bitmap and sound ownership against the currently wired PS2 consumers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")]
from audit_custom_weapon_asset_closure import walk_root  # noqa: E402
from audit_mp_match_content_closure import Closure, MP_MAPS, sha256_file  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402
from halo2ps2 import modelconv  # noqa: E402


CONSUMERS = {
    "mode_otex": ROOT / "submodules/halo-ps2/engine/src/world/world.c",
    "bitmap_texs": ROOT / "submodules/halo-ps2/engine/src/world/world.c",
    "animation": ROOT / "submodules/halo-ps2/engine/src/world/anim.c",
}


def digest(path: Path) -> str:
    return sha256_file(path)


def classify_bitmap(entry, owners: list[dict], otex_ids: set[int]) -> dict:
    if entry.tag_id in otex_ids:
        status, consumer = "covered_by_model_OTEX", "submodules/halo-ps2/engine/src/world/world.c:world_load_objects/src_binding"
    elif any(o["group"] in {"font", "wphi", "unhi", "grhi", "hudg", "hud#"}
             or o["group"].startswith("ui_") for o in owners):
        status, consumer = "unsupported_UI_texture", None
    elif any(o["group"] in {"effe", "part", "pctl", "deca", "cont", "lens", "glw!"} for o in owners):
        status, consumer = "unsupported_effect_sprite_texture", None
    else:
        status, consumer = "unsupported_unbound_bitmap", None
    return {"status": status, "consumer": consumer}


def audit_closure(closure: Closure, scope: str) -> dict:
    summary = closure.run()
    mode_ids = sorted(e.tag_id for e in closure.visited.values() if e.group == "mode")
    converted = modelconv.convert_map(closure.map, mode_ids) if mode_ids else None
    otex_ids = {t.source_id for t in converted.otex_result.textures} if converted else set()
    bitmap_rows = []
    for entry in sorted((e for e in closure.visited.values() if e.group == "bitm"), key=lambda e: e.tag_id):
        owners = [{"tag_id": edge["from"], "path": edge["from_path"], "group": closure.by_id[edge["from"]].group,
                   "field": edge["field"]}
                  for edge in closure.edges if edge["target_id"] == entry.tag_id and edge["target_path"]]
        bitmap_rows.append({"tag_id": entry.tag_id, "path": entry.path,
                            "source_map": closure.path.name, "owners": owners,
                            **classify_bitmap(entry, owners, otex_ids)})
    sounds = [{"tag_id": e.tag_id, "path": e.path, "source_map": closure.path.name,
               "metadata_only": True, "playback_consumer": None}
              for e in sorted(closure.visited.values(), key=lambda e: e.tag_id) if e.group == "snd!"]
    return {"scope": scope, "source_map": closure.path.name,
            "source_map_sha256": digest(closure.path), "closure_tag_count": len(closure.visited),
            "bitmap_count": len(bitmap_rows), "bitmap_owners": bitmap_rows,
            "sound_count": len(sounds), "sounds": sounds,
            "model_OTEX": {"model_tag_count": len(mode_ids), "bitmap_source_ids": sorted(otex_ids),
                           "chunk_bytes": len(converted.otex) if converted else 0,
                           "chunk_sha256": hashlib.sha256(converted.otex).hexdigest() if converted else None},
            "unresolved_reference_count": summary["unresolved_reference_count"]}


def build_report(maps_dir: Path, schema_elf: Path) -> dict:
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    rows = []
    for name in ("ui", *MP_MAPS):
        path = maps_dir / f"{name}.map"
        if not path.is_file():
            raise ValueError(f"missing selected map {path}")
        rows.append(audit_closure(Closure(path, manifest), "ui" if name == "ui" else "multiplayer"))
    roots = [
        ("energy_sword", "a50", r"weapons\energy sword\energy sword"),
        ("gravity_rifle", "beavercreek", r"weapons\gravity rifle\gravity rifle"),
        ("fuel_rod", "c40", r"weapons\fuel rod gun\fuel rod"),
    ]
    special = []
    for key, map_name, root_path in roots:
        c = Closure(maps_dir / f"{map_name}.map", manifest)
        row = walk_root(c, root_path)
        # Convert only the modes reached from this exact special root.
        modes = sorted(e.tag_id for e in c.visited.values() if e.group == "mode")
        result = modelconv.convert_map(c.map, modes) if modes else None
        ids = {t.source_id for t in result.otex_result.textures} if result else set()
        entries = []
        for e in sorted((x for x in c.visited.values() if x.group == "bitm"), key=lambda x: x.tag_id):
            owners = [{"tag_id": x["from"], "path": x["from_path"], "group": c.by_id[x["from"]].group,
                       "field": x["field"]} for x in c.edges if x["target_id"] == e.tag_id and x["target_path"]]
            entries.append({"tag_id": e.tag_id, "path": e.path, "owners": owners, **classify_bitmap(e, owners, ids)})
        special.append({"weapon": key, "root": root_path, "source_map": f"{map_name}.map",
                         "source_map_sha256": digest(c.path), "closure_tag_count": row["closure_tag_count"],
                         "bitmap_count": len(entries), "bitmap_owners": entries,
                         "unresolved_reference_count": row["unresolved_reference_count"],
                         "model_OTEX_bytes": len(result.otex) if result else 0,
                         "model_OTEX_sha256": hashlib.sha256(result.otex).hexdigest() if result else None})
    counts = {}
    unsupported_by_owner_group = {}
    for map_row in rows:
        for b in map_row["bitmap_owners"]:
            counts[b["status"]] = counts.get(b["status"], 0) + 1
            if b["status"] not in {"covered_by_model_OTEX"}:
                for owner in b["owners"]:
                    group_counts = unsupported_by_owner_group.setdefault(owner["group"], {})
                    group_counts[b["status"]] = group_counts.get(b["status"], 0) + 1
    return {"schema": "hcu-c1-media-coverage-v2", "scope": "retained UI map, all 13 selected stock MP maps, and three custom weapon roots",
            "schema_elf_sha256": digest(schema_elf), "consumer_source_hashes": {k: digest(v) for k, v in CONSUMERS.items()},
            "maps": rows, "special_weapons": special, "map_bitmap_status_counts": dict(sorted(counts.items())),
            "unsupported_bitmap_owner_group_counts": {k: dict(sorted(v.items()))
                                                       for k, v in sorted(unsupported_by_owner_group.items())},
            "admission": {"ui_bitmap_profile": "blocked: no UI bitmap consumer", "effect_bitmap_profile": "blocked: no effect/sprite texture consumer",
                          "model_OTEX": "admitted for bitmaps referenced by converted models", "sound_playback": "blocked: identities only; SPU2 sample playback separate"}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--maps", type=Path, default=ROOT / "data/retail/weapon-audit-maps")
    ap.add_argument("--schema-elf", type=Path, default=ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory-m2-ui-lifecycle/halo-local.elf")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--overwrite", action="store_true",
                    help="replace an existing report after the full audit succeeds")
    args = ap.parse_args()
    if args.output.exists() and not args.overwrite:
        ap.error(f"refusing to overwrite existing output: {args.output}")
    result = build_report(args.maps, args.schema_elf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
