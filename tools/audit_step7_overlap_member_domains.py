#!/usr/bin/env python3
"""Add exact-spelling and index-domain triage for the 46 C0 overlap ranges.

This deliberately does not upgrade semantic qualification. A global field-name
spelling may belong to another same-named type; the report therefore separates
spelling evidence from type association and records unresolved domains openly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAP = ROOT / "docs/reports/m2-step7-gap-consumer-evidence-2026-10-22.json"
OUT = ROOT / "docs/reports/m2-step7-overlap-member-domain-audit-2026-10-22.json"
CE = ROOT / "submodules/halo-ce-universal/source"

# Domain dispositions are only recorded where a named field and source bounds
# or source tag-block access make the domain explicit. `evidence` points to the
# implementation containing that source-level evidence.
DOMAINS = {
    "plane_index": ("index", "collision_bsp.bsp3d.planes", "source/structures/structure_visibility.c", "Bounds checked against the selected collision BSP plane block before lookup."),
    "fog_reference": ("encoded_index", "structure_bsp.fog_planes", "source/physics/collisions.c", "NONE and high-bit encoding are checked; low 15 bits index fog_planes, then region_index is checked against fog_regions."),
    "bsp3d_node_index": ("index", "collision_bsp.bsp3d.nodes", "source/structures/structures.c", "NONE sentinel is checked before lookup in the selected collision BSP's nodes block."),
    "first_surface_reference_index": ("block_start_index", "structure_bsp.surface_references", "source/structures/structures.c", "Used as the first index in a range bounded by surface_reference_count; consumer checks the range against surface_references.count."),
    "surface_reference_count": ("count", "structure_bsp.surface_references", "source/structures/structures.c", "Count paired with first_surface_reference_index; range is checked against the surface_references block."),
    "first_surface_index": ("block_start_index", "structure_bsp.surfaces", "source/structures/structure_bsp_definitions.c", "Partitions the surfaces block with surface_count; current material lookup checks surface bounds."),
    "surface_count": ("count", "structure_bsp.surfaces", "source/structures/structure_bsp_definitions.c", "Count paired with first_surface_index to define a surface interval."),
    "bitmap_index": ("external_tag_index", "bitmap tag resource group", "source/structures/structure_render.c", "NONE is checked before the bitmap index is passed to the bitmap/tag resource path; not a BSP-local array index."),
    "resource_index": ("external_tag_index", "bitmap tag resource group", "source/cache/predicted_resources.c", "Host member fixture checks resource-index bounds and bitmap-group/type resolution; this is a tag/resource domain, not a BSP block."),
    "root_index": ("encoded_index", "bsp2d nodes or collision leaves", "source/physics/bsp2d.c", "Non-negative node indices index the supplied node block; high-bit values encode leaf indices, with NONE rejected."),
    "child_indices": ("encoded_index", "bsp2d nodes or collision leaves", "source/physics/bsp2d.c", "Selected child is fed back into traversal: node indices address the supplied node block and high-bit values encode leaves."),
    "bsp2d_reference_count": ("count", "collision_leaf.bsp2d_references", "submodules/halo-ce-universal/source/physics/collision_bsp.c", "Bounds a contiguous reference interval beginning at first_bsp2d_reference_index."),
    "first_bsp2d_reference_index": ("block_start_index", "collision_bsp.bsp2d.references", "submodules/halo-ce-universal/source/physics/collision_bsp.c", "Start of the collision leaf's contiguous BSP2D reference interval."),
    "breakable_surface_index": ("index", "structure_bsp.breakable_surfaces", "source/physics/collision_bsp.c", "Byte index is checked against breakable_surface_count before breakable-surface handling."),
    "collision_surface_index": ("index", "structure_bsp.collision_bsp.surfaces", "source/physics/breakable_surfaces.c", "Used to resolve a collision surface from the active collision BSP; full host gap-member fixture is not yet present."),
    "sky_index": ("index", "scenario sky palette", "source/structures/structures.c", "Source consumer associates the cluster's sky index with scenario sky data; exact malformed-index fixture absent."),
    "leaf_indices": ("encoded_index", "leaf_map.leaves", "source/structures/leaf_map.c", "Portal sides select map leaves after masking the leaf/node high-bit designator; portal construction writes these values using index_from_node."),
    "node_index": ("index", "leaf_map.bsp.nodes", "source/structures/leaf_map.c", "Map leaf-face node_index selects a BSP3D node in the leaf map's BSP; no exact malformed-member fixture is mapped."),
    "point_light_indices": ("runtime_index", "debug_rasterizer_light_count", "source/render/render_objects.c", "Renderer checks each active point-light index against debug_rasterizer_light_count; this is renderer state, not a BSP-local block."),
    "permutation_index": ("shader_permutation_index", "active material shader permutation set", "source/structures/structure_render.c", "Passed alongside the resolved material shader to triangle draw consumers; exact shader permutation bounds are handled downstream and not qualified here."),
    "vertex_indices": ("index", "structure_material.vertices", "source/structures/structure_lens_flares.c", "Lens-flare surface consumer checks each triangle vertex index against material.vertices.count before dereference; broader renderer traversal still needs its own qualification."),
    "palette_index": ("index", "structure_bsp.runtime_decals palette", "source/structures/structure_runtime_decals.c", "Used to select the runtime decal palette; exact member/bounds host fixture absent."),
    "wind_global_function_index": ("index", "global-function palette", "source/scenario/wind.c", "Source consumer resolves the index through the global-function/tag path; exact gap-member bounds fixture absent."),
    "runtime_particle_system_global_function_index": ("index", "global-function palette", "source/effects/weather_particle_systems.c", "Source consumer resolves this index through the global-function/tag path; exact gap-member bounds fixture absent."),
}

INDEX_WORDS = re.compile(r"(?:^|_)(?:index|indices|count|reference|references|root|child|palette)(?:$|_)")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files() -> list[Path]:
    return sorted(p for p in CE.rglob("*") if p.is_file() and p.suffix in {".c", ".h"})


def hits(field: str, sources: list[Path]) -> list[dict]:
    pat = re.compile(r"(?:->|\.)\s*" + re.escape(field) + r"\b")
    found = []
    for path in sources:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if pat.search(line):
                found.append({"path": str(path.relative_to(ROOT)), "line": n,
                              "excerpt": line.strip()[:220]})
    return found


def build() -> dict:
    base = json.loads(GAP.read_text())
    sources = files()
    pins: dict[str, str] = {str(GAP.relative_to(ROOT)): sha(GAP)}
    output = []
    for row in base["rows"]:
        members = []
        for member in row["compiled_member_overlaps"]:
            name = member["name"]
            if name.startswith("(anonymous"):
                accesses = []
                status = "anonymous_member_no_source_name"
                domain = {"kind": "unknown", "domain": "unresolved", "status": "open",
                          "evidence": None, "basis": "DWARF has no member name; no safe name-based source association."}
            else:
                accesses = hits(name, sources)
                for hit in accesses:
                    p = ROOT / hit["path"]
                    pins[hit["path"]] = sha(p)
                status = "exact_member_spelling_found_type_association_unverified" if accesses else "no_exact_member_spelling_found_family_type_association_only"
                if name in DOMAINS:
                    kind, dom, ev, basis = DOMAINS[name]
                    domain = {"kind": kind, "domain": dom, "status": "source_backed_domain_identified",
                              "evidence": ev, "basis": basis}
                    p = ROOT / ev if ev.startswith("submodules/") else CE / ev
                    if p.is_file():
                        pins[str(p.relative_to(ROOT))] = sha(p)
                elif INDEX_WORDS.search(name):
                    domain = {"kind": "index_or_count_by_name", "domain": "unresolved",
                              "status": "open", "evidence": None,
                              "basis": "Name indicates index/count/reference semantics; no type-specific local block or pointer domain was established by this audit."}
                elif any(k in name.lower() for k in ("unused", "reserved", "pad", "copious")):
                    domain = {"kind": "not_applicable_candidate", "domain": "none_claimed",
                              "status": "open_semantics", "evidence": None,
                              "basis": "Name suggests padding/reserved storage, but name alone does not justify dropping the bytes or closing semantic disposition."}
                else:
                    domain = {"kind": "non_index_geometry_or_scalar_candidate", "domain": "not_assessed",
                              "status": "open", "evidence": None,
                              "basis": "No pointer/index domain inferred from the member name; member semantics remain open."}
            members.append({
                "member": name,
                "source_access_classification": status,
                "exact_source_member_spellings": accesses,
                "domain_assessment": domain,
                "fixture_disposition": "existing_direct_member_fixture" if row.get("direct_member_fixture_claims") and any(c["member"] == name for c in row["direct_member_fixture_claims"]) else "no_member_specific_host_fixture_claimed",
                "semantic_disposition": "open",
            })
        output.append({"definition_id": row["definition_id"], "definition": row["definition"],
                       "schema_gap_range": row["schema_gap_range"], "inventory_path": row["inventory_path"],
                       "members": members})
    return {
        "format": "m2-step7-overlap-member-domain-audit-v1",
        "generated_by": "tools/audit_step7_overlap_member_domains.py",
        "input": {str(GAP.relative_to(ROOT)): sha(GAP)},
        "source_pins": dict(sorted(pins.items())),
        "rows": output,
        "summary": {
            "overlap_range_count": len(output),
            "member_segment_count": sum(len(r["members"]) for r in output),
            "exact_member_spelling_segments": sum(bool(m["exact_source_member_spellings"]) for r in output for m in r["members"]),
            "type_association_only_segments": sum(not m["exact_source_member_spellings"] for r in output for m in r["members"]),
            "source_backed_index_or_pointer_domains": sum(m["domain_assessment"]["status"] == "source_backed_domain_identified" for r in output for m in r["members"]),
            "unresolved_index_or_pointer_domains": sum(m["domain_assessment"]["kind"] in ("index_or_count_by_name", "unknown") for r in output for m in r["members"]),
            "member_specific_host_fixtures": sum(m["fixture_disposition"] == "existing_direct_member_fixture" for r in output for m in r["members"]),
            "semantic_dispositions_closed": 0,
            "limitations": [
                "Global exact field spelling is not proof that the occurrence uses this DWARF type; type association needs AST/data-flow or a focused fixture.",
                "Source-backed index domains are code-reading evidence, not proof of complete bounds safety or target execution.",
                "Only resource_index currently has a direct member-specific host fixture among these overlap segments.",
                "All 46 range semantics remain open; this audit does not convert layout overlap, retention, or family fixtures into closure.",
            ],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--output", type=Path, default=OUT)
    args = ap.parse_args()
    data = build()
    encoded = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text() != encoded:
            raise SystemExit("overlap member domain report is stale; regenerate")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(json.dumps(data["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
