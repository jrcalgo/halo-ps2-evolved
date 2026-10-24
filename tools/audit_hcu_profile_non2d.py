#!/usr/bin/env python3
"""Classify staged non-2D UI bitmaps against proven PS2 consumers.

The audit intentionally recognizes only source-backed owners. Unknown owners,
asset paths, or changed evidence pins fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
if str(ROOT / "submodules/halo-ps2/tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
CATALOG = Path("build/m2-c1-profiles-ui/bitmap-stage-ui-2026-10-23/catalog.json")
MEDIA = Path("docs/reports/m2-c1-media-coverage-2026-10-23.json")
PLAN = Path("plans/7.hcu-remake-m2-m4.md")
MODEL_POLICY = Path("submodules/halo-ps2/docs/11-model-section.md")
XBOX_MODEL = Path("submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_models.c")
XBOX_RASTERIZER = Path("submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox.c")
XBOX_ENVIRONMENT = Path("submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_environment.c")
XBOX_CAMO = Path("submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_active_camouflage.c")
GLOBALS = Path("submodules/halo-ce-universal/source/game/game_globals.h")
CINEMATICS = Path("submodules/halo-ce-universal/source/cutscene/cinematics.c")
PS2_OBJTEX = Path("submodules/halo-ps2/tools/halo2ps2/objtex.py")
PS2_TEXCONV = Path("submodules/halo-ps2/tools/halo2ps2/texconv.py")
PS2_SCEN_H = Path("submodules/halo-ps2/engine/src/world/scen.h")
PS2_ARCH = Path("submodules/halo-ps2/docs/03-engine-architecture.md")
XBOX_PLASMA = Path("submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_plasma_energy.c")
XBOX_LIGHTS = Path("submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_environment.c")
XBOX_WATER = Path("submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_water.c")

# Expected tag-owner field is deliberately exact. Changing schemas or adding a
# new caller requires a reviewed rule here; default is "unknown / do not omit".
RULES = {
    "characters\\cyborg\\bitmaps\\cyborg reflection armor": ("cube", "soso", "reflection_cube_map", "model_reflection"),
    "scenery\\halo\\bitmaps\\cubemap halo": ("cube", "soso", "reflection_cube_map", "model_reflection"),
    "weapons\\assault rifle\\fp\\bitmaps\\diffuse gunmetal": ("cube", "soso", "reflection_cube_map", "model_reflection"),
    "weapons\\plasma rifle\\bitmaps\\cubemap plasma rifle": ("cube", "soso", "reflection_cube_map", "model_reflection"),
    "rasterizer\\active camouflage distortion": ("cube", "matg", "active_camouflage_distortion", "xbox_helper"),
    "rasterizer\\distance attenuation": ("3d", "matg", "distance_attenuation", "xbox_helper"),
    "rasterizer\\vector normalization": ("cube", "matg", "vector_normalization", "xbox_helper"),
    "rasterizer\\default 3d": ("3d", "matg", "default_textures", "xbox_default"),
    "rasterizer\\default cube map": ("cube", "matg", "default_textures", "xbox_default"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def classify(path: str, image_type: str, owners: list[dict[str, Any]]) -> dict[str, Any]:
    rule = RULES.get(path.lower())
    if not rule:
        return {"classification": "unknown_fail_closed", "payload_disposition": "retain_or_block_profile", "reason": "no exact reviewed owner rule"}
    expected_type, group, field, kind = rule
    actual = {(o.get("group"), o.get("field")) for o in owners}
    if image_type.lower() != expected_type or not actual or any(g != group or f != field for g, f in actual):
        return {"classification": "unknown_fail_closed", "payload_disposition": "retain_or_block_profile", "reason": "image type or owner schema differs from reviewed rule"}
    if kind == "model_reflection":
        return {
            "classification": "ce_model_reflection_cube",
            "payload_disposition": "exclude_from_current_ps2_visual_profile_under_explicit_feature_gate",
            "feature_gate": "ps2_model_reflection_cube_consumer_absent",
            "consumer_evidence": "CE Xbox model shader reads reflection_cube_map; PS2 OTEX binds only soso.base_map and documents reflection maps dropped.",
            "replacement_if_enabled": "Implement cube-face decoding plus a real sphere/environment-map render pass; six 2D face chunks alone do not qualify visual parity.",
        }
    if kind == "xbox_helper":
        return {
            "classification": "ce_rasterizer_helper_payload",
            "payload_disposition": "exclude_from_current_ps2_visual_profile_under_explicit_feature_gate",
            "feature_gate": "xbox_rasterizer_helper_consumers_not_present_in_ps2_model_pipeline",
            "consumer_evidence": "CE fields are consumed by Xbox rasterizer shader/effect paths; PS2 model OTEX has no consumer for matg helper textures.",
            "replacement_if_enabled": "Provide a PS2 implementation of the corresponding shader/effect path and its native volume/cube sampling before admitting payload.",
        }
    return {
        "classification": "ce_xbox_default_texture",
        "payload_disposition": "exclude_from_current_ps2_visual_profile_under_explicit_feature_gate",
        "feature_gate": "xbox_default_hardware_texture_lookup_not_in_ps2_profile",
        "consumer_evidence": "Xbox rasterizer default-hardware-format lookup reads default_textures[type]; PS2 OTEX uses base_map only. Cinematics uses default_textures[0] (2D default), not these 3D/cube records.",
        "replacement_if_enabled": "Add a PS2 caller-specific fallback consumer and native 3D/cube sampling; keep CE tag references and source metadata in the profile.",
    }


FIELD_RULES = {
    ("soso", "reflection_cube_map"): ("ce_model_reflection_cube", "ps2_model_reflection_cube_consumer_absent", "CE Xbox model shaders read this reflection input; PS2 OTEX converts only `soso.base_map` and explicitly drops reflection maps."),
    ("senv", "reflection_cube_map"): ("ce_environment_reflection_cube", "ps2_environment_reflection_consumer_absent", "CE environment shader reflection input; PS2 `resolve_shader` binds base/self-illumination input and does not read the reflection field."),
    ("sgla", "reflection_map"): ("ce_glass_reflection_input", "ps2_glass_reflection_consumer_absent", "CE glass shader reflection input; PS2 `resolve_shader` binds its base map only."),
    ("swat", "reflection_map"): ("ce_water_reflection_cube", "ps2_water_reflection_consumer_absent", "CE rasterizer_xbox_water.c binds water->reflection_map.index for its reflection pass; PS2 texconv.resolve_shader(swat) binds only SWAT_MAP (the base map at +0x4c), with no reflection pass."),
    ("spla", "primary_noise_map"): ("ce_plasma_primary_noise_volume", "ps2_plasma_shader_consumer_absent", "CE Xbox plasma-energy renderer samples the primary noise map; PS2 `objtex` explicitly classifies `spla` as untextured."),
    ("spla", "secondary_noise_map"): ("ce_plasma_secondary_noise_volume", "ps2_plasma_shader_consumer_absent", "CE Xbox plasma-energy renderer samples the secondary noise map; PS2 `objtex` explicitly classifies `spla` as untextured."),
    ("ligh", "gel_map"): ("ce_projected_light_gel", "ps2_projected_gel_consumer_absent", "CE Xbox environment lighting binds the light gel texture; PS2 scene lighting carries baked ambient/sun and point-light values without gel texture identity/sampling."),
    ("matg", "rasterizer_data.active_camouflage_distortion"): ("ce_xbox_active_camo_helper", "ps2_active_camo_distortion_consumer_absent", "CE Xbox active-camouflage rasterizer samples this texture; no corresponding PS2 material consumer is implemented."),
    ("matg", "rasterizer_data.distance_attenuation"): ("ce_xbox_distance_attenuation_helper", "ps2_distance_attenuation_consumer_absent", "CE Xbox environment rasterizer binds this lookup texture; PS2 object lighting uses precomputed per-vertex light terms."),
    ("matg", "rasterizer_data.vector_normalization"): ("ce_xbox_vector_normalization_helper", "ps2_vector_normalization_consumer_absent", "CE Xbox environment rasterizer binds this lookup texture; PS2 lighting uses CPU/VU vector math."),
    ("matg", "rasterizer_data.default_textures"): ("ce_xbox_default_texture", "ps2_default_3d_cube_consumer_absent", "CE Xbox default hardware-format lookup reads the default texture slots; PS2 OTEX does not use 3D/cube default payloads."),
}


def audit_survival(diagnostic_path: Path, ctag_path: Path, schema_elf_path: Path) -> dict[str, Any]:
    """Join every non-2D image in the admitted survival closure to schema owners."""
    import ctag
    from hcu_profile_validate import _entries, _schema_dependencies
    from hcu_schema_manifest import Elf32, SchemaManifest
    from halo2ps2 import bitmaps, texconv

    diagnostic_path, ctag_path, schema_elf_path = (p.resolve() for p in (diagnostic_path, ctag_path, schema_elf_path))
    d = json.loads(diagnostic_path.read_text())
    if d.get("format") != "hcu-profile-diagnostic-v1" or d.get("profile") != "survival-beavercreek":
        raise ValueError("expected the pinned survival-beavercreek profile diagnostic")
    ctag_bytes, elf_bytes = ctag_path.read_bytes(), schema_elf_path.read_bytes()
    if sha256(ctag_path) != d.get("unadmitted_ctag_sha256"):
        raise ValueError("survival CTAG pin mismatch")
    if sha256(schema_elf_path) != d.get("schema_elf_sha256"):
        raise ValueError("survival schema ELF pin mismatch")
    schema = SchemaManifest(Elf32(schema_elf_path)).build()
    image = ctag.decode(ctag_bytes, max_image_size=len(ctag_bytes)).image
    _, tags = _entries(image)
    _, _, _, consumers = _schema_dependencies(image, schema, tags)
    by_bitmap: dict[int, list[dict[str, Any]]] = {}
    for c in consumers:
        by_bitmap.setdefault(c["bitmap_output_datum"], []).append(c)
    deps = {int(x["output_datum"]): x for x in d["dependencies"]}
    source_maps = d.get("source_maps", {})
    maps = {}
    for key, row in source_maps.items():
        path = ROOT / row["path"]
        if not path.is_file() or sha256(path) != row.get("sha256"):
            raise ValueError(f"survival source-map pin mismatch: {key}")
        maps[key] = texconv.MapData.open(path)

    grouped: dict[tuple, dict[str, Any]] = {}
    unknown = False
    for tag in tags:
        if tag["group"] != "bitm":
            continue
        dep = deps.get(tag["output_datum"])
        if not dep or dep.get("group") != "bitm":
            raise ValueError(f"survival bitmap tag has no diagnostic dependency row: {tag['output_datum']}")
        m = maps[dep["source_key"]]
        source_entry = m.by_id.get(int(dep["source_datum"]))
        if source_entry is None or source_entry.path != dep["path"]:
            raise ValueError(f"survival bitmap source identity mismatch: {dep['path']}")
        images = bitmaps.parse_images(m.region, m.base, source_entry.data_address)
        for img in images:
            if img.is_2d:
                continue
            refs = by_bitmap.get(tag["output_datum"], [])
            owner_fields = sorted({(r["owner_group"], r["field"]) for r in refs})
            if not owner_fields:
                unknown = True
                classification = {"classification": "unknown_fail_closed", "feature_gate": None,
                                  "payload_disposition": "retain_or_block_profile", "reason": "no typed bitmap owner in schema dependency walk"}
            else:
                results = []
                for owner_group, field in owner_fields:
                    rule = FIELD_RULES.get((owner_group, field))
                    if rule is None:
                        results.append({"classification": "unknown_fail_closed", "feature_gate": None,
                                        "payload_disposition": "retain_or_block_profile",
                                        "reason": f"no source-backed rule for {owner_group}.{field}"})
                        unknown = True
                    else:
                        cname, gate, reason = rule
                        results.append({"classification": cname, "feature_gate": gate,
                                        "payload_disposition": "exclude_from_current_ps2_visual_profile_under_explicit_feature_gate",
                                        "consumer_evidence": reason,
                                        "replacement_if_enabled": "Implement the indicated CE material/effect consumer with native 3D volume or six-face cube sampling and actual PS2 presentation; extracted 2D slices/faces alone are not acceptance."})
                classification = {"owner_dispositions": results,
                                  "classification": "unknown_fail_closed" if any(r["classification"] == "unknown_fail_closed" for r in results) else "role_gated_no_current_ps2_payload_consumer",
                                  "feature_gate": sorted({r["feature_gate"] for r in results if r["feature_gate"]})}
            key = (dep["path"], img.index, img.type, img.width, img.height, img.depth, img.format,
                   tuple(owner_fields))
            row = grouped.setdefault(key, {"path": dep["path"], "image_index": img.index, "image_type": img.type,
                "dimensions": [img.width, img.height, img.depth], "format": img.format_name,
                "pixel_offset": img.pixel_offset, "pixel_bytes": img.pixel_size,
                "owners": [], "source_occurrences": [], **classification})
            row["source_occurrences"].append({"source_key": dep["source_key"], "source_datum": dep["source_datum"],
                                               "output_datum": tag["output_datum"]})
            for ref in refs:
                owner = {k: ref[k] for k in ("owner_output_datum", "owner_group", "owner_path", "definition", "field")}
                if owner not in row["owners"]:
                    row["owners"].append(owner)
    rows = sorted(grouped.values(), key=lambda r: (r["path"], r["image_index"], r["image_type"], r["owners"][0]["owner_group"] if r["owners"] else ""))
    source_files = [PLAN, MODEL_POLICY, PS2_OBJTEX, PS2_TEXCONV, PS2_SCEN_H, PS2_ARCH,
                    XBOX_MODEL, XBOX_RASTERIZER, XBOX_ENVIRONMENT, XBOX_CAMO, XBOX_PLASMA, XBOX_WATER, GLOBALS]
    pins = {str(p): sha256(ROOT / p) for p in source_files}
    pins[display_path(diagnostic_path)] = sha256(diagnostic_path)
    pins[display_path(ctag_path)] = sha256(ctag_path)
    pins[display_path(schema_elf_path)] = sha256(schema_elf_path)
    pins.update({row["path"]: row["sha256"] for row in source_maps.values()})
    counts: dict[str, int] = {}
    for row in rows:
        for item in row.get("owner_dispositions", []):
            counts[item["classification"]] = counts.get(item["classification"], 0) + len(row["source_occurrences"])
    return {"schema": "m2-c1-survival-non2d-consumer-audit-v1",
            "status": "incomplete" if unknown else "partial", "runtime_admitted": False,
            "profile": d["profile"], "diagnostic_failure_stage": d["failure_stage"],
            "diagnostic_error": d["error"], "ctag_tag_count": len(tags),
            "non2d_image_occurrence_count": sum(len(x["source_occurrences"]) for x in rows),
            "unique_non2d_role_count": len(rows), "role_counts": counts,
            "policy": "C1 #4 retains payload only for proven live supported consumers. CE tags, owners, and all non-2D image metadata stay accounted for. Current PS2 exclusions are explicit feature gates; no face/slice extraction is represented as shader or presentation parity.",
            "pins": pins, "roles": rows}


def run(catalog_path: Path = ROOT / CATALOG, media_path: Path = ROOT / MEDIA) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text())
    media = json.loads(media_path.read_text())
    pins = [PLAN, MODEL_POLICY, XBOX_MODEL, XBOX_RASTERIZER, XBOX_ENVIRONMENT, XBOX_CAMO, GLOBALS, CINEMATICS, MEDIA]
    evidence_pins = {str(p): sha256(ROOT / p) for p in pins}
    evidence_pins[display_path(catalog_path)] = sha256(catalog_path)
    for item in catalog.get("source_maps", {}).values():
        p = ROOT / item["path"]
        if not p.exists() or sha256(p) != item["sha256"]:
            raise ValueError(f"staged catalog source map pin mismatch: {item['path']}")
    if sha256(ROOT / catalog["diagnostic_path"]) != catalog["diagnostic_sha256"]:
        raise ValueError("diagnostic pin mismatch")
    if sha256(ROOT / catalog["ctag_path"]) != catalog["ctag_sha256"]:
        raise ValueError("CTAG pin mismatch")
    media_by_path = {}
    for m in media["maps"]:
        if m.get("source_map") == "ui.map":
            for row in m["bitmap_owners"]:
                media_by_path[row["path"].lower()] = row
    failures = catalog.get("failures", [])
    rows = []
    for f in failures:
        path = f["path"]
        media_row = media_by_path.get(path.lower())
        if not media_row:
            disposition = {"classification": "unknown_fail_closed", "payload_disposition": "retain_or_block_profile", "reason": "no UI owner row in pinned media audit"}
            owners = []
        else:
            owners = media_row["owners"]
            image_type = f.get("failure", "").rsplit("type=", 1)[-1].rstrip("]")
            typ = {"1": "3d", "2": "cube"}.get(image_type, "unknown")
            disposition = classify(path, typ, owners)
        rows.append({"path": path, "datum": f.get("source_datum"), "image_index": f.get("image_index"), "image_type": {"1": "3d", "2": "cube"}.get(f.get("failure", "").rsplit("type=", 1)[-1].rstrip("]"), "unknown"), "owners": owners, **disposition})
    return {
        "schema": "m2-c1-ui-non2d-consumer-audit-v1",
        "status": "partial" if rows and all(r["classification"] != "unknown_fail_closed" for r in rows) else "incomplete",
        "runtime_admitted": False,
        "scope": "the nine non-2D image conversion failures in the pinned UI diagnostic; CE bitmap tags/references remain source metadata",
        "catalog": {"path": display_path(catalog_path), "sha256": sha256(catalog_path), "ctag_sha256": catalog["ctag_sha256"], "diagnostic_sha256": catalog["diagnostic_sha256"], "schema_elf_sha256": catalog["schema_elf_sha256"], "source_maps": catalog["source_maps"]},
        "source_pins": evidence_pins,
        "policy": "C1 #4 requires proven live consumers. No plan waiver authorizes treating cube faces/slices as visual parity. The only explicit fuel-rod reflection omission policy does not apply to these records; exclusions below are gated by current PS2 consumer absence and retain CE metadata.",
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=("ui", "survival"), default="ui")
    ap.add_argument("--catalog", type=Path, default=ROOT / CATALOG)
    ap.add_argument("--media", type=Path, default=ROOT / MEDIA)
    ap.add_argument("--diagnostic", type=Path, default=ROOT / "build/m2-c1-survival-dedup/survival-beavercreek.failure.json")
    ap.add_argument("--ctag", type=Path, default=ROOT / "build/m2-c1-survival-dedup/survival-beavercreek.unadmitted.ctag")
    ap.add_argument("--schema-elf", type=Path, default=ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf")
    ap.add_argument("--output", type=Path, default=ROOT / "docs/reports/m2-c1-ui-non2d-consumers-2026-10-23.json")
    a = ap.parse_args()
    if a.profile == "survival":
        result = audit_survival(a.diagnostic, a.ctag, a.schema_elf)
        if a.output == ROOT / "docs/reports/m2-c1-ui-non2d-consumers-2026-10-23.json":
            a.output = ROOT / "docs/reports/m2-c1-survival-non2d-consumers-2026-10-23.json"
    else:
        result = run(a.catalog, a.media)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "rows": len(result.get("rows", result.get("roles", []))), "output": display_path(a.output)}))
    return 0 if result["status"] == "partial" else 1


if __name__ == "__main__":
    raise SystemExit(main())
