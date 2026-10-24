#!/usr/bin/env python3
"""Reproducibly convert and inventory static BSP/object render assets for stock MP maps.

This is an offline conversion-size inventory, not a runtime high-water or frame-working-set
measurement. It uses halo-ps2's pinned texconv/modelconv pipelines to enumerate the concrete
decoded TEXS, per-BSP LM sections, and scenario-selected object OTEX output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "submodules/halo-ps2/tools"
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
sys.path.insert(0, str(TOOLS))
from halo2ps2 import hp2, modelconv, scenconv, skyconv, texconv  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   text=True).strip()


def audit_one(path: Path) -> dict:
    bsp_result = texconv.convert_map(path, lightmaps=True, lm_gain=1.5)
    bsp_pack = hp2.parse(bsp_result.pack)
    texs_bytes = next(bsp_pack.read(s.tag) for s in bsp_pack.sections if s.tag == "TEXS")
    texs = texconv.parse_texs(texs_bytes)
    bsp_textures = {
        "texture_count": len(texs.textures),
        "binding_count": len(texs.bindings),
        "pixel_bytes": sum(t["pixel_bytes"] for t in texs.textures),
        "clut_bytes": sum(t["clut_entries"] * 4 for t in texs.textures),
        "texs_section_bytes": len(texs_bytes),
        "texs_section_sha256": sha256_bytes(texs_bytes),
        "texture_cache_payload_bytes": len(texs_bytes) - texconv.HEADER_SIZE -
            len(texs.textures) * texconv.TEXTURE_REC - len(texs.bindings) * texconv.BINDING_REC,
        "untextured_bindings": sum(b["texture"] == texconv.NO_TEXTURE for b in texs.bindings),
    }
    lightmaps = []
    for section in bsp_pack.sections:
        if not section.tag.startswith("LM") or not section.tag[2:].isdigit():
            continue
        blob = bsp_pack.read(section.tag)
        parsed = texconv.parse_lmap(blob)
        pages = [p for p in parsed["pages"] if p is not None]
        lightmaps.append({
            "bsp_index": int(section.tag[2:]),
            "section_sha256": sha256_bytes(blob),
            "page_count_dense": len(parsed["pages"]),
            "page_count_used": len(pages),
            "source_resolution_pixel_bytes": sum(p["src_width"] * p["src_height"] * 4 for p in pages),
            "converted_luminance_pixel_bytes": sum(p["pixel_bytes"] for p in pages),
            "lmap_section_bytes_including_tables_clut_alignment": len(blob),
            "extra_shrink": bsp_result.lm_shift.get(int(section.tag[2:]), 0),
        })

    objects = scenconv.collect(path)
    model_tags = set(objects.model_tags)
    sky = skyconv.read_sky(path)
    if sky and sky["model_tag"]:
        model_tags.add(sky["model_tag"])
    obj_result = modelconv.convert_map(path, sorted(model_tags))
    ot = obj_result.otex_result
    return {
        "map": path.stem,
        "source_map_sha256": sha256(path),
        "bsp_count": len(bsp_result.bsps),
        "bsp_referenced_render_textures": bsp_textures,
        "lightmaps": lightmaps,
        "lightmap_converted_bytes_sum": sum(x["converted_luminance_pixel_bytes"] for x in lightmaps),
        "lightmap_lmap_section_bytes_sum": sum(x["lmap_section_bytes_including_tables_clut_alignment"] for x in lightmaps),
        "scenario_object_selection": {
            "model_tag_count_including_sky": len(model_tags),
            "model_count_converted": len(obj_result.models),
            "object_texture_count": len(ot.textures),
            "object_texture_pixel_bytes": sum(t.pixel_bytes for t in ot.textures),
            "object_texture_clut_bytes": sum(len(t.clut) for t in ot.textures),
            "otex_section_bytes": len(obj_result.otex),
            "otex_section_sha256": sha256_bytes(obj_result.otex),
            "object_texture_cache_payload_bytes": len(obj_result.otex) - texconv.HEADER_SIZE -
                len(ot.textures) * texconv.TEXTURE_REC -
                len(ot.shaders) * texconv.BINDING_REC,
            "configured_object_texture_budget_bytes": 6 * 1024 * 1024,
            "effective_max_texture_dimension": ot.max_dim,
            "maximum_texture_dimension_requested": ot.estimate_dim,
            "untextured_shader_count": ot.untextured_shaders,
        },
        "static_bsp_plus_object_texture_section_bytes":
            bsp_textures["texs_section_bytes"] + len(obj_result.otex) +
            sum(x["lmap_section_bytes_including_tables_clut_alignment"] for x in lightmaps),
        "limits": [
            "offline converted-section size only; no simultaneous CPU staging/DMA source lifetime",
            "scenario-selected objects, not match-time spawned bot/vehicle/equipment maxima",
            "no EE cache residency, eviction, render-frame or peak working-set evidence",
            "decoded source-resolution lightmap pixel estimate excludes decode buffers and source tag pages",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("maps", type=Path, help="directory containing decompressed retail MP .map files")
    ap.add_argument("--output", type=Path, help="new JSON destination; refuses overwrite")
    args = ap.parse_args()
    paths = [args.maps / f"{name}.map" for name in MP_MAPS]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        ap.error("missing required MP sources: " + ", ".join(missing))
    reports = []
    for path in paths:
        print(f"auditing {path.name}", file=sys.stderr, flush=True)
        reports.append(audit_one(path))
    output = {
        "schema": "halo-ps2-mp-static-render-asset-bound-v1",
        "scope": "13 stock Halo CE multiplayer maps; campaign excluded",
        "method": "pinned halo-ps2 texconv.convert_map(lm_gain=1.5) plus scenario-selected modelconv.convert_map",
        "halo_ps2_commit": pin(ROOT / "submodules/halo-ps2"),
        "halo_ce_universal_commit": pin(ROOT / "submodules/halo-ce-universal"),
        "tool_sha256": sha256(Path(__file__).resolve()),
        "map_count": len(reports),
        "all_maps_static_texture_section_bytes_sum": sum(r["static_bsp_plus_object_texture_section_bytes"] for r in reports),
        "all_maps_bsp_texs_section_bytes_sum": sum(r["bsp_referenced_render_textures"]["texs_section_bytes"] for r in reports),
        "all_maps_object_otex_section_bytes_sum": sum(r["scenario_object_selection"]["otex_section_bytes"] for r in reports),
        "all_maps_lightmap_lmap_section_bytes_sum": sum(r["lightmap_lmap_section_bytes_sum"] for r in reports),
        "largest_map_static_texture_sections": max(r["static_bsp_plus_object_texture_section_bytes"] for r in reports),
        "maps": reports,
    }
    rendered = json.dumps(output, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            ap.error(f"refusing to overwrite existing output: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
