#!/usr/bin/env python3
"""Cross-reference C0 schema-gap ranges with CE field accesses and fixtures.

This is discovery/coverage evidence only. Textual field access cannot prove
runtime reachability, and a related fixture does not qualify every field in a
record. The output preserves those distinctions explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DWARF = ROOT / "docs/reports/m2-step7-schema-gap-dwarf-members-2026-10-22.json"
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
OUT = ROOT / "docs/reports/m2-step7-gap-consumer-evidence-2026-10-22.json"
CE_SOURCE = ROOT / "submodules/halo-ce-universal/source"

# These associations point to a fixture which exercises a related consumer
# path. They do not claim that the fixture observes every byte/member in a gap.
FIXTURES = {
    "leaf_portal": ["tests/test_hcu_mp_portal_visibility.py"],
    "map_leaf_face": ["tests/test_hcu_mp_portal_visibility.py"],
    "structure_cluster_portal": ["tests/test_hcu_mp_portal_visibility.py"],
    "structure_cluster": ["tests/test_hcu_mp_portal_visibility.py"],
    "structure_subcluster": ["tests/test_hcu_mp_portal_visibility.py"],
    "structure_leaf": ["tests/test_hcu_mp_portal_visibility.py"],
    "structure_runtime_decal": ["tests/test_hcu_runtime_decals_consumer.py"],
    "structure_detail_object_data": ["tests/test_hcu_mp_detail_object_consumer.py"],
    "detail_object": ["tests/test_hcu_mp_detail_object_consumer.py"],
    "structure_sound_environment_palette_entry": [
        "tests/test_hcu_mp_sound_scenery_runtime.py"],
    "structure_background_sound_palette_entry": [
        "tests/test_hcu_mp_sound_scenery_runtime.py"],
    "structure_weather_palette_entry": [
        "tests/test_hcu_mp_weather_particle_consumer.py",
        "tests/test_hcu_mp_wind_package.py"],
    "structure_weather_polyhedron": [
        "tests/test_hcu_mp_weather_particle_consumer.py"],
    "structure_fog_palette_entry": [
        "tests/test_hcu_mp_weather_particle_all13.py",
        "tests/test_location.py",
        "docs/reports/m2-step7-mp-valid-fog-selection-all13-2026-10-22.md"],
    "structure_fog_region": [
        "tests/test_hcu_mp_weather_particle_all13.py",
        "tests/test_location.py",
        "docs/reports/m2-step7-mp-valid-fog-selection-all13-2026-10-22.md"],
    "structure_fog_plane": [
        "tests/test_hcu_mp_wind_package.py",
        "tests/test_location.py",
        "docs/reports/m2-step7-fog-plane-consumer-qualification-2026-10-21.md"],
    "structure_breakable_surface": [
        "tests/test_hcu_mp_breakable_runtime.py"],
    "structure_lens_flare_marker": ["tests/test_hcu_mp_lens_flare_consumer.py"],
    "structure_lightmap": ["tests/test_hcu_mp_lightmap_surface_consumer.py"],
    "structure_material": ["tests/test_hcu_mp_lightmap_surface_consumer.py"],
    "structure_surface": ["tests/test_hcu_mp_lightmap_surface_consumer.py"],
    "structure_surface_reference": [
        "tests/test_hcu_mp_lightmap_surface_consumer.py",
        "tests/test_hcu_mp_portal_visibility.py"],
    "render_lighting": ["tests/test_hcu_mp_lightmap_surface_consumer.py"],
    "collision_vertex": ["tests/test_m3_collision_oracle.py"],
    "collision_surface": ["tests/test_m3_collision_oracle.py"],
    "collision_leaf": ["tests/test_m3_collision_oracle.py"],
    "bsp2d_node": ["tests/test_m3_collision_oracle.py"],
    "bsp2d_reference": ["tests/test_m3_collision_oracle.py"],
    "bsp3d_node": ["tests/test_m3_collision_oracle.py"],
    "real_plane3d": ["tests/test_m3_collision_oracle.py"],
    "real_point3d": ["tests/test_m3_collision_oracle.py"],
    "real_point2d": ["tests/test_m3_collision_oracle.py"],
    "structure_collision_material": ["tests/test_m3_collision_oracle.py"],
    "predicted_resource": ["tests/test_hcu_mp_predicted_resource_member.py"],
}

SOURCE_REFS = {
    "leaf_portal": ["source/structures/structure_visibility.c"],
    "map_leaf_face": ["source/structures/structure_visibility.c"],
    "structure_runtime_decal": ["source/structures/structure_runtime_decals.c"],
    "structure_detail_object_data": ["source/structures/structure_detail_objects.c"],
    "detail_object": ["source/structures/structure_detail_objects.c"],
    "structure_sound_environment_palette_entry": [
        "source/sound/sound_environment.c", "source/scenario/scenario.c"],
    "structure_background_sound_palette_entry": [
        "source/sound/sound_environment.c", "source/scenario/scenario.c"],
    "structure_weather_palette_entry": [
        "source/scenario/wind.c", "source/effects/weather_particle_systems.c"],
    "structure_weather_polyhedron": ["source/effects/weather_particle_systems.c"],
    "structure_fog_palette_entry": ["source/scenario/scenario.c"],
    "structure_fog_region": ["source/scenario/scenario.c"],
    "structure_fog_plane": ["source/structures/structure_fog_planes.c"],
    "structure_breakable_surface": ["source/physics/breakable_surfaces.c"],
    "structure_lens_flare_marker": ["source/structures/structure_lens_flares.c"],
    "structure_lightmap": ["source/structures/structure_bsp_definitions.c"],
    "structure_material": [
        "source/structures/structure_bsp_definitions.c",
        "source/structures/structures.c"],
    "structure_surface": ["source/structures/structure_render.c"],
    "structure_surface_reference": [
        "source/structures/structure_visibility.c", "source/structures/structures.c"],
    "structure_cluster_portal": ["source/structures/structure_visibility.c"],
    "structure_cluster": ["source/structures/structure_visibility.c"],
    "structure_subcluster": ["source/structures/structure_visibility.c"],
    "structure_leaf": ["source/structures/structure_visibility.c"],
    "render_lighting": ["source/structures/structure_render.c"],
    "collision_vertex": ["source/physics/collisions.c"],
    "collision_surface": ["source/physics/collisions.c"],
    "collision_leaf": ["source/physics/collisions.c"],
    "bsp2d_node": ["source/physics/collisions.c"],
    "bsp2d_reference": ["source/physics/collisions.c"],
    "bsp3d_node": ["source/physics/collisions.c"],
    "real_plane3d": ["source/physics/collisions.c"],
    "real_point3d": ["source/physics/collisions.c"],
    "real_point2d": ["source/physics/collisions.c"],
    "structure_collision_material": ["source/physics/collisions.c"],
    "predicted_resource": ["source/cache/predicted_resources.c", "source/camera/observer.c"],
}
EXACT_FIXTURE_MEMBERS = {
    "predicted_resource": {
        "resource_index": "Host fixture extracts CE predicted_resource_valid and proves bitmap resource_index acceptance/rejection at valid, end, and negative indices; also exercises sound group and missing-tag rejection.",
    },
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def explicit_accesses(field: str, paths: list[str]) -> list[dict]:
    pattern = re.compile(r"(?:->|\.)\s*" + re.escape(field) + r"\b")
    accesses = []
    for rel in paths:
        path = ROOT / "submodules/halo-ce-universal" / rel
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if pattern.search(line):
                # This flag is deliberately syntactic. It is not an AST or
                # data-flow proof and must not be read as semantic closure.
                lhs = re.search(r"(?:->|\.)\s*" + re.escape(field) +
                                r"\s*(?:[+\-*/]?=|\+\+|--)", line)
                accesses.append({"path": str(path.relative_to(ROOT)), "line": number,
                                 "mode_hint": "assignment_syntax" if lhs else "read_or_unknown",
                                 "source_excerpt": line.strip()[:240]})
    return accesses

def build_report() -> dict:
    dwarf = json.loads(DWARF.read_text())
    inventory = json.loads(INVENTORY.read_text())
    row_by_key = {(row["definition_id"], row["offset_within_definition"], row["size"]): row
                  for row in inventory["members"]}
    rows = []
    source_pins: dict[str, str] = {
        str(DWARF.relative_to(ROOT)): sha256(DWARF),
        str(INVENTORY.relative_to(ROOT)): sha256(INVENTORY),
    }
    for gap in dwarf["ranges"]:
        overlaps = gap.get("member_overlap_evidence", [])
        if not overlaps:
            continue
        key = (gap["definition_id"], gap["schema_range"]["offset"],
               gap["schema_range"]["size"])
        inventory = row_by_key.get(key)
        if inventory is None:
            continue
        definition = gap["definition"]
        source_files = SOURCE_REFS.get(definition, [])
        related = FIXTURES.get(definition, [])
        tests = [rel for rel in related if rel.startswith("tests/")]
        reports = [rel for rel in related if rel.startswith("docs/")]
        for rel in source_files + related:
            candidate = ROOT / rel if rel.startswith("tests/") or rel.startswith("docs/") else ROOT / "submodules/halo-ce-universal" / rel
            if candidate.is_file():
                source_pins[str(candidate.relative_to(ROOT))] = sha256(candidate)
        members = []
        for overlap in overlaps:
            field = overlap["member"]
            accesses = explicit_accesses(field, source_files) if field else []
            for hit in accesses:
                path = ROOT / hit["path"]
                source_pins[hit["path"]] = sha256(path)
            members.append({
                "name": field if field else "(anonymous member; DWARF name unavailable)",
                "overlap": overlap["schema_gap_overlap"],
                "member_extent": overlap["member_range"],
                "explicit_accesses_in_candidate_sources": accesses,
                "access_search_limit": "Only explicit .field/->field spellings in listed candidate files; macros, aliases, indirect code, and call reachability are not resolved.",
            })
        rows.append({
            "definition_id": gap["definition_id"], "definition": definition,
            "schema_gap_range": gap["schema_range"],
            "inventory_path": inventory["path"],
            "compiled_member_overlaps": members,
            "candidate_ce_source_files": source_files,
            "related_fixtures": [
                {"path": rel, "sha256": sha256(ROOT / rel),
                 "relation": "related consumer fixture; not proof that every overlapping member is observed"}
                for rel in tests if (ROOT / rel).is_file()
            ],
            "related_reports": [
                {"path": rel, "sha256": sha256(ROOT / rel),
                 "relation": "supporting report; not itself an executable fixture"}
                for rel in reports if (ROOT / rel).is_file()
            ],
            "direct_member_fixture_claims": [
                {"member": member["name"], "claim": claim,
                 "test": "tests/test_hcu_mp_predicted_resource_member.py"}
                for member in members
                for claim in [EXACT_FIXTURE_MEMBERS.get(definition, {}).get(member["name"])]
                if claim
            ],
            "fixture_status": "related_fixture_exists" if tests else "no_behavior_fixture_mapped",
            "target_consumer_execution": False,
            "semantic_qualification": "open",
            "limitation": "DWARF overlap identifies source-layout members only. Textual accesses and related fixtures do not establish complete semantic behavior or target execution.",
        })
    rows.sort(key=lambda r: (r["definition"], r["schema_gap_range"]["offset"]))
    return {
        "format": "m2-step7-gap-consumer-evidence-v1",
        "generated_by": "tools/audit_step7_gap_consumer_evidence.py",
        "input_artifacts": {
            str(DWARF.relative_to(ROOT)): sha256(DWARF),
            str(INVENTORY.relative_to(ROOT)): sha256(INVENTORY),
        },
        "source_pins": dict(sorted(source_pins.items())),
        "summary": {
            "compiled_member_overlap_ranges": len(rows),
            "member_overlap_segments": sum(len(r["compiled_member_overlaps"]) for r in rows),
            "ranges_with_related_fixture": sum(bool(r["related_fixtures"]) for r in rows),
            "ranges_with_related_report_only": sum(bool(r["related_reports"]) and not r["related_fixtures"] for r in rows),
            "ranges_without_mapped_fixture": sum(not r["related_fixtures"] for r in rows),
            "ranges_with_target_consumer_execution": sum(bool(r["target_consumer_execution"]) for r in rows),
            "semantic_qualifications_closed": 0,
            "limitations": [
                "Textual source access is discovery evidence, not call-graph/data-flow proof.",
                "A consumer fixture can be related to a type without asserting every overlapping member.",
                "Host harness execution does not establish PCSX2 or physical-console behavior.",
                "Retained bytes and compiler layout do not establish the correct relocated pointer domain.",
            ],
        },
        "rows": rows,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_report()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text() != encoded:
            raise SystemExit("consumer evidence report is stale; regenerate without --check")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(json.dumps(report["summary"], sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
