#!/usr/bin/env python3
"""Inventory existing Halo CE source-map closures for requested MP custom weapons.

This is an offline asset provenance/conversion audit, not a runtime residency test.
It walks references from explicit tag roots with the current HCU compiler-derived
schemas, then runs the pinned halo-ps2 MODL/OTEX and ANIM converters over reached
model/animation tags. No retail tag or payload is copied into the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")]
from audit_mp_match_content_closure import Closure, sha256_file  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402
from halo2ps2 import animconv, modelconv  # noqa: E402


def git_pin(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   text=True).strip()


def walk_root(closure: Closure, root_path: str) -> dict:
    roots = [entry for entry in closure.index.entries
             if entry.group == "weap" and entry.path.casefold() == root_path.casefold()]
    if len(roots) != 1:
        raise ValueError(f"expected exactly one tag root {root_path!r}, found {len(roots)}")
    root = roots[0]
    pending = [root.tag_id]
    seen: set[int] = set()
    while pending:
        tag_id = pending.pop()
        if tag_id in seen:
            continue
        entry = closure.by_id.get(tag_id)
        if entry is None:
            continue
        seen.add(tag_id)
        closure.visited[tag_id] = entry
        definition = closure.schema_by_group.get(entry.group or "")
        if entry.group == "sbsp" or not definition:
            closure.opaque_groups[entry.group or "?"] += 1
            continue
        closure.walk_definition(entry, int(definition), entry.data_address - closure.base)
        for edge in closure.edges:
            if edge["from"] == tag_id and edge["target_id"] not in seen and edge["target_path"]:
                pending.append(edge["target_id"])

    summary = closure.summary()
    model_ids = sorted({entry.tag_id for entry in closure.visited.values()
                        if entry.group == "mode"})
    anim_ids = sorted({entry.tag_id for entry in closure.visited.values()
                       if entry.group == "antr"})
    model_output = modelconv.convert_map(closure.path, model_ids)
    anim_output = animconv.build_section(closure.path, anim_ids)
    summary.update({
        "root_tag": {"path": root.path, "group": root.group, "tag_id": root.tag_id},
        "source_map": str(closure.path),
        "source_map_sha256": sha256_file(closure.path),
        "closure_model_tag_count": len(model_ids),
        "closure_animation_graph_tag_count": len(anim_ids),
        "converted_MODL_bytes": len(model_output.modl),
        "converted_OTEX_bytes": len(model_output.otex),
        "converted_ANIM_bytes": len(anim_output),
        "converted_MODL_sha256": hashlib.sha256(model_output.modl).hexdigest(),
        "converted_OTEX_sha256": hashlib.sha256(model_output.otex).hexdigest(),
        "converted_ANIM_sha256": hashlib.sha256(anim_output).hexdigest(),
        "converted_OTEX_pixel_bytes": sum(t.pixel_bytes for t in model_output.otex_result.textures),
        "converted_OTEX_clut_bytes": sum(len(t.clut) for t in model_output.otex_result.textures),
        "untextured_shader_count": model_output.otex_result.untextured_shaders,
        "reference_edges": closure.edges,
    })
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--maps", type=Path, required=True,
                    help="directory of extracted/decompressed Halo CE source maps")
    ap.add_argument("--schema-elf", type=Path, required=True,
                    help="HCU PS2 ELF whose compiler-derived schemas define this walk")
    ap.add_argument("--output", type=Path, required=True,
                    help="new JSON path; existing output is never overwritten")
    args = ap.parse_args()
    sources = {
        "energy_sword": ("a50", "weapons\\energy sword\\energy sword"),
        "fuel_rod": ("c40", "weapons\\fuel rod gun\\fuel rod"),
        "gravity_rifle": ("beavercreek", "weapons\\gravity rifle\\gravity rifle"),
    }
    manifest = SchemaManifest(Elf32(args.schema_elf)).build()
    if manifest["elf_sha256"] != sha256_file(args.schema_elf):
        raise RuntimeError("schema ELF hash mismatch")
    rows = {}
    for key, (map_name, root) in sources.items():
        path = args.maps / f"{map_name}.map"
        if not path.is_file():
            ap.error(f"missing source map: {path}")
        closure = Closure(path, manifest)
        rows[key] = walk_root(closure, root)
    output = {
        "schema": "hcu-custom-weapon-source-closure-v1",
        "scope": "source provenance and offline converted-content inventory only; no runtime or EE residency claim",
        "source_selection": "retail CE map copies already present under data/retail/weapon-audit-maps; sword root from a50, handheld fuel rod root from c40",
        "schema_elf": str(args.schema_elf),
        "schema_elf_sha256": sha256_file(args.schema_elf),
        "halo_ce_universal_commit": git_pin(ROOT / "submodules/halo-ce-universal"),
        "halo_ps2_commit": git_pin(ROOT / "submodules/halo-ps2"),
        "audit_tool_sha256": sha256_file(Path(__file__).resolve()),
        "weapons": rows,
        "limits": [
            "Only compiler-schema-walked references present in each selected map are closed; external/missing references are reported unresolved.",
            "MODL, OTEX, ANIM lengths are independent offline converter outputs and must not be summed as concurrent residency.",
            "No audio conversion, runtime texture/model pinning, first-person switch overlap, arena high-water, EE timing, or target-sized fit is measured.",
            "The available sources are campaign-map tag images, not a provisioned custom multiplayer asset pack. Required CE map root/dependency metadata and external bitmap/sound payload availability must be carried into the proposed MP asset source.",
        ],
    }
    if args.output.exists():
        ap.error(f"refusing to overwrite existing output: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    print(f"audited {len(rows)} special-weapon roots -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
