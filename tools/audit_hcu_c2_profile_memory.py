#!/usr/bin/env python3
"""Bind current C1 profile memory measurements to the C2 partition inputs.

This is an evidence inventory, not a target-fit qualifier: C1's resident image
measurements do not include renderer high water, validator scratch, or the
loader's transient overlapping copies.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "build/m2-c1-corpus-rebuild-v3"
SPECS = CORPUS / "specs.json"
QUAL = ROOT / "docs/reports/m2-c1-qualification-2026-10-23.json"
BUDGET = ROOT / "config/memory-budget.json"
OUT = ROOT / "docs/reports/m2-c2-profile-memory-audit-2026-10-23.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    qualification = json.loads(QUAL.read_text())
    specs = json.loads(SPECS.read_text())
    budget = json.loads(BUDGET.read_text())
    req = {item["id"]: item["status"] for item in qualification["requirements"]}
    regions = {item["name"]: item["bytes"] for item in budget["regions"]}
    candidate = {"tag": 4_477_120, "bsp": 1_993_712, "render": 4_014_928}
    rows = []
    for spec in specs["profiles"]:
        name = spec["name"]
        manifest_path = CORPUS / f"{name}.json"
        package_path = CORPUS / f"{name}.hcp"
        manifest = json.loads(manifest_path.read_text())
        m = manifest["memory"]
        bsp_bytes = sum(int(item["payload_bytes"]) for item in spec.get("bsp_roots", []))
        tag = int(m["resident_ce_bytes"])
        # C1 provides a package payload floor. These derived values deliberately
        # do not claim to be runtime allocator requirements or a fit result.
        tag_capacity = (tag + 15) & ~15
        bsp_capacity = (bsp_bytes + 15) & ~15
        # Real validator stores one claim bit per byte in 32-bit words. The
        # claims owner is resident_gameplay, separate from map/render backing.
        claims_bytes = ((tag_capacity + bsp_capacity + 31) // 32) * 4
        rows.append({
            "profile": name,
            "kind": spec["kind"],
            "package_sha256": sha(package_path),
            "manifest_sha256": sha(manifest_path),
            "package_file_bytes": int(m["package_file_bytes"]),
            "resident_ce_bytes": tag,
            "normalized_ctag_bytes": int(m["normalized_ctag_bytes"]),
            "ctag_relocation_table_bytes": int(m["ctag_relocation_table_bytes"]),
            "pointer_relocations": int(m["pointer_relocations"]),
            "tag_relocations": int(m["tag_relocations"]),
            "tag_count": int(manifest["validation"]["tag_count"]),
            "bsp_count": int(manifest["validation"]["bsp_count"]),
            "independently_addressable_media_bytes": int(m["independently_addressable_media_bytes"]),
            "bsp_payload_bytes": bsp_bytes,
            "resident_ce_plus_bsp_bytes": tag + bsp_bytes,
            "cross_owner_tag_bsp_claims_payload_sum_bytes": tag + bsp_bytes + claims_bytes,
            "claims_bitmap_if_aligned_payload_capacities_bytes": claims_bytes,
            "owner_requirements": {
                "map_render": {"tag_capacity_bytes": tag_capacity,
                    "bsp_capacity_bytes": bsp_capacity, "inner_guard_bytes": 16,
                    "remaining_for_render_before_render_alignment_bytes":
                        10_485_760 - tag_capacity - bsp_capacity - 16},
                "resident_gameplay": {"claims_bytes": claims_bytes},
                "streaming_map_owner": {"ctag_relocation_staging_bytes":
                    int(m["ctag_relocation_table_bytes"])},
            },
            "relocation_table_staging_bytes": int(m["ctag_relocation_table_bytes"]),
            "tag_bsp_plus_relocation_staging_lower_bound_bytes": tag + bsp_bytes + int(m["ctag_relocation_table_bytes"]),
            "tag_over_candidate_bytes": tag - candidate["tag"],
            "map_owner_over_candidate_bytes": tag + bsp_bytes - candidate["tag"] - candidate["bsp"],
            "tag_bsp_over_current_production_map_region_bytes": tag + bsp_bytes - regions["current_bsp"],
            "render_residual_in_nominal_10mib_bytes": 10_485_760 - tag - bsp_bytes,
        })
    mp = [r for r in rows if r["kind"] == "bots"]
    survival = [r for r in rows if r["kind"] == "survival"]
    max_mp = max(mp, key=lambda r: r["resident_ce_plus_bsp_bytes"])
    max_bot_tag = max(mp, key=lambda r: r["resident_ce_bytes"])
    max_survival = max(survival, key=lambda r: r["resident_ce_bytes"])
    report = {
        "format": "hcu-c2-c1-profile-memory-audit-v1",
        "date": "2026-10-23",
        "scope": "C2 requirements 1-3 measurement/audit only; not production fit or C2 exit",
        "inputs": {
            "c1_qualification": {"path": str(QUAL.relative_to(ROOT)), "sha256": sha(QUAL), "qualified": qualification["qualified"], "requirements": req},
            "profile_specs": {"path": str(SPECS.relative_to(ROOT)), "sha256": sha(SPECS), "profile_count": len(specs["profiles"])},
            "memory_budget": {"path": str(BUDGET.relative_to(ROOT)), "sha256": sha(BUDGET), "version": budget["version"], "committed_bytes": budget["committed_bytes"], "reserve_bytes": budget["reserve_bytes"]},
            "production_binder": {"path": "src/stream/hcu_memory_bind.c", "sha256": sha(ROOT / "src/stream/hcu_memory_bind.c")},
            "arena_layout": {"path": "submodules/halo-ps2/engine/src/core/mem.c", "sha256": sha(ROOT / "submodules/halo-ps2/engine/src/core/mem.c")},
        },
        "candidate_partition_bytes": {**candidate, "combined": sum(candidate.values()), "nominal_10mib": 10_485_760},
        "alignment_bounds": {
            "arena_alloc_alignment": 16,
            "dma_region_alignment": 64,
            "production_layout_region_count": 9,
            "production_layout_max_cursor_alignment_slop_bytes": 8 * 15 + 63,
            "guarded_layout_guard_count": 10,
            "guarded_layout_guard_bytes_each": 16,
            "guarded_layout_fixed_guard_bytes": 160,
            "guarded_layout_max_cursor_alignment_slop_bytes": 8 * 15 + 63,
            "candidate_three_region_partition_max_alignment_slop_bytes": 3 * 15,
            "note": "Upper bounds from mem_layout_v2_init allocation order. Exact padding depends on backing address and prior cursor; these bytes are distinct from payload and 16-byte guards.",
        },
        "production_regions_bytes": {"current_bsp": regions["current_bsp"], "texture_cache": regions["texture_cache"], "resident_gameplay": regions["resident_gameplay"], "dynamic_simulation": regions["dynamic_simulation"], "streaming": regions["streaming"], "dma_commands": regions["dma_commands"], "frame_scratch": regions["frame_scratch"]},
        "summary": {
            "profile_count": len(rows),
            "max_bot_profile": max_bot_tag["profile"],
            "max_bot_resident_ce_bytes": max_bot_tag["resident_ce_bytes"],
            "candidate_tag_shortfall_for_max_bot_bytes": max_bot_tag["tag_over_candidate_bytes"],
            "max_bot_map_owner_profile": max_mp["profile"],
            "max_bot_tag_plus_bsp_bytes": max_mp["resident_ce_plus_bsp_bytes"],
            "candidate_map_owner_shortfall_for_max_bot_bytes": max_mp["map_owner_over_candidate_bytes"],
            "render_residual_for_max_bot_in_10mib_bytes": max_mp["render_residual_in_nominal_10mib_bytes"],
            "max_survival_profile": max_survival["profile"],
            "max_survival_resident_ce_bytes": max_survival["resident_ce_bytes"],
            "survival_exceeds_entire_10mib_bytes": max_survival["resident_ce_bytes"] - 10_485_760,
            "current_production_binding_fit_qualified": False,
            "all_profiles_fit_candidate_tag_bsp_split": False,
            "max_bot_tag_bsp_payload_lower_bound_profile": max_mp["profile"],
            "max_bot_tag_bsp_payload_lower_bound_bytes": max_mp["resident_ce_plus_bsp_bytes"],
            "max_bot_relocation_staging_bytes": max(mp, key=lambda r: r["ctag_relocation_table_bytes"])["ctag_relocation_table_bytes"],
            "max_bot_resident_owner_claims_bytes": max(r["claims_bitmap_if_aligned_payload_capacities_bytes"] for r in mp),
            "cross_owner_sum_is_not_a_map_render_requirement": True,
            "max_bot_tag_bsp_over_current_production_map_region_bytes": max(mp, key=lambda r: r["resident_ce_plus_bsp_bytes"])["resident_ce_plus_bsp_bytes"] - regions["current_bsp"],
            "survival_requires_roster_residency_or_proven_eviction": True,
            "candidate_is_fit_qualified": False,
        },
        "accounting_and_gaps": [
            "C1 resident_ce_bytes is the decoded CE image requirement; relocation-table bytes are separately reported as loader staging and excluded from that resident figure. They must be counted if live during a competing staging interval.",
            "BSP bytes are schema-derived C1 CBSP payload sizes, not a measured CE runtime allocator high water. BSP relocation, validation scratch, indexes/claims and alignment are not included in resident_ce_plus_bsp_bytes.",
            "C1 media bytes are independently addressable on-disk chunks; this report does not treat all media as simultaneously resident. It includes no renderer cache high water, decoded chunk/workspace overlap, source-copy overlap, DMA lifetime, or texture residency measurement.",
            "Production startup still uses the legacy fixed split. The new versioned profile API can partition the combined 10 MiB with nested and outer guards, but no fully measured production profile has been wired. Claims are charged to resident_gameplay after game state, and CTAG relocations to streaming staging; neither is subtracted from map/render backing.",
            "Alignment is reported as a structural upper bound, not folded into payload totals: production layout allocation order has up to 183 bytes of cursor alignment slop (8 x 15-byte 16-alignment gaps plus one 63-byte DMA gap); guarded mode adds ten 16-byte guards (160 bytes) plus the same slop. Exact per-profile padding depends on backing address and preceding cursor.",
            "The claims requirement uses the real 32-bit word formula ceil((aligned_tag_capacity + aligned_bsp_capacity)/32)*4. Per-profile capacities are 16-byte aligned payload floors; actual capacities and runtime BSP high-water may be larger. Cross-owner sums are informative totals and cannot be compared against a single owner's capacity.",
            "C1 tag_count and bsp_count expose index population, but production index/claims metadata beyond the claims bitmap, validator scratch, renderer cache high water, decoded chunk/workspace overlap, source-copy overlap, DMA lifetime, and texture residency are not measured by these manifests.",
            "Survival profile tag images contain all imported combat roster variants. Runtime active-roster streaming/eviction or another bounded residency design has not shown that those CE pointers can be safely absent while inactive.",
        ],
        "profiles": rows,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} profiles; max bot owner {max_mp['profile']}={max_mp['resident_ce_plus_bsp_bytes']} B; max survival CE {max_survival['profile']}={max_survival['resident_ce_bytes']} B")


if __name__ == "__main__":
    main()
