#!/usr/bin/env python3
"""Join CTAG and CE-BSP audits into a lower-bound per-map EE working set.

This is a feasibility screen, not a memory-placement proof: it omits validator
scratch, the external destination for projected BSP vertex data, alignment,
loader overlap, and PS2 render/texture/audio working sets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CTAG = ROOT / "docs/reports/retail-ctag-compaction-audit.json"
DEFAULT_SCHEMA = ROOT / "docs/reports/retail-ctag-schema-footprint-v5.json"
DEFAULT_BSP = ROOT / "docs/reports/retail-bsp-schema-capacity-projection.json"
DEFAULT_BUDGET = ROOT / "config/memory-budget.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def region_bytes(budget: dict, name: str) -> int:
    for region in budget["regions"]:
        if region["name"] == name:
            return int(region["bytes"])
    raise ValueError(f"memory budget has no {name!r} region")


def audit(ctag: dict, schema: dict, bsp: dict, budget: dict) -> dict:
    if ctag.get("format") != "retail-ctag-compaction-audit-v1":
        raise ValueError("unexpected CTAG report format")
    if bsp.get("format") != "retail-ce-bsp-schema-audit-v4":
        raise ValueError("expected retail CE BSP schema audit v4")
    if schema.get("format") != "retail-ctag-coverage-audit-v3":
        raise ValueError("expected retail CTAG schema footprint audit v3")
    schema_hash = ctag.get("schema_elf_sha256")
    if schema_hash != bsp.get("schema_elf_sha256") or schema_hash != schema.get("schema_elf_sha256"):
        raise ValueError("CTAG and BSP reports were produced from different schema ELFs")
    ctag_maps = {row["map"]: row for row in ctag["maps"]}
    bsp_maps = {row["map"]: row for row in bsp["maps"]}
    schema_maps = {row["map"].removesuffix(".map"): row for row in schema["maps"]}
    if (not ctag_maps or ctag_maps.keys() != bsp_maps.keys() or
            ctag_maps.keys() != schema_maps.keys()):
        raise ValueError("CTAG and BSP reports must cover the same nonempty map set")

    resident = region_bytes(budget, "resident_gameplay")
    current_bsp = region_bytes(budget, "current_bsp")
    rows = []
    for name in sorted(ctag_maps):
        source_hashes = {
            ctag_maps[name].get("source_sha256"),
            bsp_maps[name].get("source_sha256"),
            schema_maps[name].get("source_sha256"),
        }
        if len(source_hashes) != 1:
            raise ValueError(f"retail reports use different source maps for {name!r}")
        tag_bytes = int(ctag_maps[name]["image_size"])
        schema_tag_lower_bound = int(schema_maps[name]["schema_visited_bytes_lower_bound"])
        animation_bytes = int(
            schema_maps[name].get("in_image_data_bytes_by_owner", {}).get("animation.data", 0)
        )
        max_animation_record = int(
            schema_maps[name].get("in_image_data_maximum_record_bytes_by_owner", {}).get(
                "animation.data", 0
            )
        )
        structures = bsp_maps[name]["structure_bsps"]
        max_raw = max((int(row["raw_bytes"]) for row in structures), default=0)
        max_projected = max((
            int(row["bytes_if_compressed_vertices_externalized"])
            for row in structures
        ), default=0)
        combined = tag_bytes + max_projected
        schema_combined_lower_bound = schema_tag_lower_bound + max_projected
        schema_without_animation = max(0, schema_tag_lower_bound - animation_bytes)
        schema_animation_candidate_combined = schema_without_animation + max_projected
        tag_without_animation = max(0, tag_bytes - animation_bytes)
        animation_candidate_combined = tag_without_animation + max_projected
        rows.append({
            "map": name,
            "compact_tag_image_bytes": tag_bytes,
            "schema_visited_tag_bytes_lower_bound": schema_tag_lower_bound,
            "animation_data_bytes_candidate_externalization": animation_bytes,
            "largest_animation_data_record_bytes": max_animation_record,
            "tag_image_bytes_after_animation_data_externalization": tag_without_animation,
            "tag_after_animation_plus_projected_bsp_bytes": animation_candidate_combined,
            "animation_candidate_fits_resident_gameplay": tag_without_animation <= resident,
            "animation_candidate_fits_combined_regions":
                animation_candidate_combined <= resident + current_bsp,
            "largest_raw_active_bsp_bytes": max_raw,
            "largest_projected_active_bsp_bytes": max_projected,
            "tag_image_fits_resident_gameplay": tag_bytes <= resident,
            "projected_bsp_fits_current_bsp": max_projected <= current_bsp,
            "tag_plus_projected_bsp_bytes": combined,
            "tag_plus_projected_bsp_fits_combined_regions":
                combined <= resident + current_bsp,
            "schema_lower_bound_plus_projected_bsp_bytes": schema_combined_lower_bound,
            "schema_lower_bound_plus_projected_bsp_fits_combined_regions":
                schema_combined_lower_bound <= resident + current_bsp,
            "schema_lower_bound_after_animation_externalization_bytes":
                schema_without_animation,
            "schema_after_animation_plus_projected_bsp_bytes":
                schema_animation_candidate_combined,
            "schema_animation_candidate_fits_combined_regions":
                schema_animation_candidate_combined <= resident + current_bsp,
        })

    return {
        "format": "retail-map-minimum-working-set-v2",
        "schema_elf_sha256": bsp["schema_elf_sha256"],
        "map_count": len(rows),
        "resident_gameplay_capacity_bytes": resident,
        "current_bsp_capacity_bytes": current_bsp,
        "combined_capacity_bytes": resident + current_bsp,
        "tag_images_over_resident_gameplay": sum(
            not row["tag_image_fits_resident_gameplay"] for row in rows
        ),
        "schema_visited_lower_bounds_over_resident_gameplay": sum(
            row["schema_visited_tag_bytes_lower_bound"] > resident for row in rows
        ),
        "lower_bound_over_combined_regions": sum(
            not row["tag_plus_projected_bsp_fits_combined_regions"] for row in rows
        ),
        "schema_lower_bound_over_combined_regions": sum(
            not row["schema_lower_bound_plus_projected_bsp_fits_combined_regions"]
            for row in rows
        ),
        "schema_animation_candidate_over_combined_regions": sum(
            not row["schema_animation_candidate_fits_combined_regions"]
            for row in rows
        ),
        "animation_candidate_tag_images_over_resident_gameplay": sum(
            not row["animation_candidate_fits_resident_gameplay"] for row in rows
        ),
        "animation_candidate_tag_plus_bsp_over_combined_regions": sum(
            not row["animation_candidate_fits_combined_regions"] for row in rows
        ),
        "excluded_from_lower_bound": [
            "external destination for compressed BSP vertex data",
            "validator claims bitmap and schema-validation scratch",
            "arena alignment and load/unload peak overlap",
            "PS2 BSP/render packs, texture cache, streaming, and audio working sets",
        ],
        "interpretation": (
            "Each row compares the actual compact CTAG size and the schema-visited "
            "byte lower bound against the largest active CE BSP after hypothetical "
            "compressed-vertex externalization. The schema lower bound excludes "
            "names/opaque roots, and both are feasibility screens, not proof of a layout. "
            "The animation.data candidate keeps its whole byte extent outside the tag "
            "image; the report does not prove a streaming implementation, reference "
            "lifetime, active-animation working set, or destination-region fit."
            "A row over combined resident_gameplay + current_bsp cannot fit by "
            "repartitioning only those two budgets; rows under the sum still "
            "must pass per-region ownership and all excluded working-set checks."
        ),
        "maps": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ctag-report", type=Path, default=DEFAULT_CTAG)
    parser.add_argument("--schema-report", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--bsp-report", type=Path, default=DEFAULT_BSP)
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    parser.add_argument("--output", type=Path, help="new JSON output path; refuses overwrite")
    args = parser.parse_args(argv)
    try:
        result = audit(read_json(args.ctag_report), read_json(args.schema_report),
                       read_json(args.bsp_report), read_json(args.budget))
        rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            if args.output.exists():
                parser.error(f"refusing to overwrite existing report: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered)
        else:
            print(rendered, end="")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"retail working-set audit failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
