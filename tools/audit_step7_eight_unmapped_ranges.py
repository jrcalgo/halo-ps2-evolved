#!/usr/bin/env python3
"""Bind eight BSP schema gaps to exact source declarations without closing semantics.

The inventory remains authoritative for serialized extents. This audit adds
source-backed member layout and pointer-domain notes, and deliberately leaves
schema preservation / runtime semantic dispositions open.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
OUT = ROOT / "docs/reports/m2-step7-eight-unmapped-range-source-map-2026-10-22.json"

# Offsets come from the pinned R5900 inventory extent and the declaration
# bodies named below. The ordinary tag_block/tag_reference triples retain
# their established serialized 12/16-byte layouts.
RANGES = {
    "detail_object_cell": {
        "definition_id": "2983192", "size": 32,
        "source": "submodules/halo-ce-universal/source/structures/structure_detail_objects.c",
        "declaration": "struct detail_object_cell_definition",
        "members": [
            ("cell_x", 0, 2, "signed scalar; cell coordinate"),
            ("cell_y", 2, 2, "signed scalar; cell coordinate"),
            ("cell_z", 4, 2, "signed scalar; cell coordinate"),
            ("offset_z", 6, 2, "signed scalar; fractional vertical offset"),
            ("valid_layers", 8, 4, "32-bit layer bitset"),
            ("start_index", 12, 4, "index into sibling detail_objects block"),
            ("count_index", 16, 4, "index into sibling counts block"),
            ("unused14", 20, 12, "declared unused storage; retained pending consumer disposition"),
        ],
        "consumer": "structure_detail_objects.c reads cell coordinates, layer bits, and start/count indices; count and object indices are bounds checked by structure_detail_objects_port_count.",
        "pointer_domains": {"start_index": "structure_detail_object_data.detail_objects", "count_index": "structure_detail_object_data.counts"},
        "consumer_evidence": [
            ("submodules/halo-ce-universal/source/structures/structure_detail_objects.c", "structure_render_detail_objects", "cell_x/cell_y/cell_z/offset_z construct camera-relative cells; valid_layers selects layers; start_index and count_index advance sibling blocks"),
            ("submodules/halo-ce-universal/source/structures/structure_detail_objects.c", "structure_detail_objects_port_count", "count_index must be inside counts; start_index and count must fit detail_objects"),
            ("submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c", "structure_detail_object_data_check", "valid_layers determines count entries; count_index plus selected layers is bounded by counts; cumulative counts validated against detail_objects"),
        ],
    },
    "detail_object_count": {
        "definition_id": "2983160", "size": 2,
        "source": "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c",
        "declaration": "TAG_SCHEMA_DEFINITION(detail_object_count, word, empty_fields)",
        "members": [("word", 0, 2, "unsigned 16-bit count value")],
        "consumer": "structure_detail_objects.c loads this value through detail_object_count_get and validates/clamps it against the sibling detail_objects extent.",
        "pointer_domains": {"value": "count of sibling detail_objects entries; not an address or serialized pointer"},
        "consumer_evidence": [("submodules/halo-ce-universal/source/structures/structure_detail_objects.c", "structure_detail_objects_port_count", "word is loaded as an unsigned count; count_index is bounded by counts and count is checked against detail_objects")],
    },
    "detail_object_z_reference_vector": {
        "definition_id": "2983144", "size": 16,
        "source": "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c",
        "declaration": "TAG_SCHEMA_DEFINITION(detail_object_z_reference_vector, real_vector4d, empty_fields)",
        "members": [("real_vector4d", 0, 16, "four 32-bit real components")],
        "consumer": "structure_detail_objects.c selects the vector at the same count_index; an absent/out-of-range vector uses the default runtime vector.",
        "pointer_domains": {"index": "structure_detail_object_data.z_reference_vectors"},
        "consumer_evidence": [("submodules/halo-ce-universal/source/structures/structure_detail_objects.c", "structure_render_detail_objects", "vector selected at the current sibling count index only when inside z_reference_vectors; otherwise default runtime vector is used")],
    },
    "structure_mirror": {
        "definition_id": "2984760", "size": 36,
        "source": "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c",
        "declaration": "struct structure_mirror",
        "members": [
            ("plane", 0, 16, "real_plane3d; mirror plane"),
            ("unused", 16, 20, "five declared longs; retained pending consumer disposition"),
        ],
        "consumer": "structure_visibility.c uses mirror->plane for mirror hull construction. The trailing declared unused array has no established runtime consumer in the inspected path.",
        "pointer_domains": {},
        "consumer_evidence": [("submodules/halo-ce-universal/source/structures/structure_visibility.c", "structure_visibility_find_mirror", "plane is passed to mirror hull construction and copied to the result; five-long unused array has no established consumer")],
    },
    "structure_node": {
        "definition_id": "2986248", "size": 6,
        "source": "submodules/halo-ce-universal/source/math/integer_math.h",
        "declaration": "union byte_rectangle3d",
        "members": [("x0,x1,y0,y1,z0,z1", 0, 6, "six byte bounds; not a pointer")],
        "consumer": "tag_schema_collision.c declares structure_node as byte_rectangle3d; byte_rectangle3d is six one-byte coordinates in integer_math.h.",
        "pointer_domains": {},
        "consumer_evidence": [("submodules/halo-ce-universal/source/structures/structure_visibility.c", "structure_visibility_build_surfaces_traverse_node", "node_index is bounded by both structure.nodes and collision.bsp3d.nodes; compressed byte rectangle is dequantized against parent_bounds")],
    },
    "structure_subcluster": {
        "definition_id": "2984928", "size": 24,
        "source": "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c",
        "declaration": "struct structure_subcluster",
        "members": [("world_bounds", 0, 24, "real_rectangle3d; subcluster world-space bounds")],
        "consumer": "structure_visibility.c uses subcluster world_bounds for frustum/cull tests. The following surface_indices tag_block starts at offset 24 and is independently declared in the schema.",
        "pointer_domains": {},
        "consumer_evidence": [("submodules/halo-ce-universal/source/structures/structure_visibility.c", "structure_visibility_traverse_subclusters", "world_bounds feeds frustum culling; surface_indices are iterated by block count and values outside structure.surfaces are skipped")],
    },
    "byte": {
        "definition_id": "2990064", "size": 1,
        "source": "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c",
        "declaration": "TAG_SCHEMA_DEFINITION(byte, byte, empty_fields)",
        "members": [("byte", 0, 1, "unsigned one-byte scalar")],
        "consumer": "Used for pathfinding byte blocks; each owning field defines its own interpretation. No pointer domain at the primitive type.",
        "pointer_domains": {},
        "consumer_evidence": [("submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c", "structure_bsp pathfinding_surfaces/pathfinding_edges schema blocks", "both sibling blocks use byte_schema; byte elements have no standalone pointer/index domain")],
    },
    "long": {
        "definition_id": "2990080", "size": 4,
        "source": "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c",
        "declaration": "TAG_SCHEMA_DEFINITION(long, long, empty_fields)",
        "members": [("long", 0, 4, "32-bit scalar; owning block defines index/value semantics")],
        "consumer": "Used for structure_subcluster.surface_indices and map_leaf.portal_designators. Each owning block defines the target domain; the primitive has no standalone pointer domain.",
        "pointer_domains": {"structure_subcluster.surface_indices": "structure_bsp.surfaces", "map_leaf.portal_designators": "leaf_map.portals"},
        "consumer_evidence": [
            ("submodules/halo-ce-universal/source/structures/structure_visibility.c", "structure_visibility_traverse_subclusters", "surface index values are checked against structure.surfaces.count before flag access"),
            ("submodules/halo-ce-universal/source/structures/leaf_map.c", "leaf_map_close_portal; leaf_map_leaf_is_closed", "LONG_MIN stores the closed bit and LONG_MAX masks the portal index into leaf_map.portals"),
        ],
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    inv = json.loads(INVENTORY.read_text())
    rows = {r["definition"]: r for r in inv["members"] if r["classification"] == "unclassified"}
    result = []
    for name, spec in RANGES.items():
        row = rows.get(name)
        if row is None:
            raise ValueError(f"inventory has no unclassified range for {name}")
        if row["definition_id"] != spec["definition_id"] or row["size"] != spec["size"] or row["offset_within_definition"] != 0:
            raise ValueError(f"inventory range changed for {name}: {row}")
        source = ROOT / spec["source"]
        result.append({
            "definition": name,
            "definition_id": spec["definition_id"],
            "inventory_range": {"offset": 0, "size": spec["size"], "path": row["path"]},
            "source_declaration": spec["declaration"],
            "source_path": spec["source"],
            "source_sha256": sha(source),
            "members": [{"name": n, "offset": o, "size": s, "interpretation": i} for n, o, s, i in spec["members"]],
            "consumer_and_domain_evidence": spec["consumer"],
            "consumer_evidence": [
                {"source_path": path, "source_sha256": sha(ROOT / path),
                 "function_or_owner": symbol, "access_and_domain": detail}
                for path, symbol, detail in spec["consumer_evidence"]
            ],
            "pointer_domains": spec["pointer_domains"],
            "schema_disposition": "open; byte retention and consumer semantics remain independently required",
            "evidence_level": "source inspection; offsets cross-checked against compiler-derived schema record extents",
        })
    return {
        "format": "hcu-step7-eight-unmapped-range-source-map-v1",
        "generated_by": "tools/audit_step7_eight_unmapped_ranges.py",
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha(INVENTORY),
        "scope": "The eight named unclassified compiler-derived BSP ranges; source layout/consumer notes only.",
        "interpretation": "These mappings identify serialized member ownership and sibling index domains where source proves them. They do not qualify target execution, justify normalization/removal, or close the schema byte-preservation gate.",
        "summary": {"ranges": len(result), "member_ranges_mapped": len(result), "semantic_dispositions_closed": 0},
        "ranges": result,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n")
    print(OUT.relative_to(ROOT))
