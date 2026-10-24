#!/usr/bin/env python3
"""C2 partition table and committed-memory audit for HCU selected profiles.

Reads the measured per-profile CE/BSP owner sizes (the C2 session map capacity
report and the archived profile memory audit), derives the versioned guarded
map/render partition that the planner in src/stream/hcu_memory_profile.c
accepts, adds the renderer terms (packet workspace, reserved texture pages,
texture-cache pages, simultaneous staging), checks everything against
config/memory-budget.json (committed 27,787,264 bytes, reserve 5,767,168
bytes), and attributes the static symbols of linked EE ELFs to their owners
(tools/audit_hcu_c2_budget_elf_owners.py) so each byte is counted once.

Writes (build/m2-c2-r2-budget/):
  partition-table-profile-v2.json
  partition-table-profile-v2.inc  (C initializer rows)
  budget-audit.json

Only exact, measured numbers are used. Renderer indices of the live set and
the target workload peaks are not in the input and are reported as unmeasured.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_hcu_c2_budget_elf_owners as elf_owners  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "config/memory-budget.json"
CAPACITY = ROOT / "docs/reports/m2-c2-session-map-capacity-2026-10-23.json"
PROFILE_MEMORY = ROOT / "docs/reports/m2-c2-profile-memory-audit-2026-10-23.json"
OUT = ROOT / "build/m2-c2-r2-budget"
LIMITS = ROOT / "submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h"
STORAGE_H = ROOT / "submodules/halo-ps2/engine/src/render/storage.h"
TEXCACHE_H = ROOT / "submodules/halo-ps2/engine/src/render/texcache.h"
STAGING_H = ROOT / "src/stream/staging.h"
ASSET_PROFILE_H = ROOT / "src/stream/hcu_asset_profile.h"
RENDER_TELEMETRY_H = ROOT / "src/stream/hcu_render_telemetry.h"
PACKAGES = ROOT / "docs/reports/m2-c2-r3-selected-packages-2026-10-23.json"
MEMORY_PROFILE_C = ROOT / "src/stream/hcu_memory_profile.c"

MAP_RENDER_BYTES = 6291456 + 4194304  # current_bsp + texture_cache backing (10 MiB)
GUARD = 16
# Residency span: 16 whole 64 KiB slots carved after the render span, behind one guard
# (hcu_memory_profile_plan_v1 and the r5 partition-runtime lane).
RESIDENCY_BYTES = 16 * 65536
RESIDENCY_SEGMENT_BYTES = 65536
ALIGN = 16
CLAIM_BITS = 32
CLAIM_WORD = 4
COMMITTED = 27787264
RESERVE = 5767168
MAX_PROFILE_VERSION = 2
RESIDENT_CAP = 6815744


def align16(value):
    return (value + ALIGN - 1) // ALIGN * ALIGN


def header_define(path, name):
    m = re.search(rf"#define {name}\s+\(?\s*([0-9]+)u?\)?", path.read_text())
    if not m:
        raise SystemExit(f"missing {name} in {path}")
    return int(m.group(1))


def header_define_expr(path, name):
    # e.g. "#define HCU_RENDER_TEXTURE_RESERVED_BYTES (17u * 8192u)"
    m = re.search(rf"#define {name}\s+\((\d+)u?\s*\*\s*(\d+)u?\)", path.read_text())
    if not m:
        raise SystemExit(f"missing {name} in {path}")
    return int(m.group(1)) * int(m.group(2))


def renderer_terms():
    return {
        "packet_workspace_bytes": header_define(STORAGE_H, "BSP_RENDER_WORKSPACE_BYTES"),
        "reserved_texture_bytes": header_define_expr(RENDER_TELEMETRY_H, "HCU_RENDER_TEXTURE_RESERVED_BYTES"),
        "texture_page_bytes": header_define(TEXCACHE_H, "TC_PAGE_BYTES"),
        "staging_slots": header_define(STAGING_H, "STAGING_SLOTS"),
        "staging_slot_bytes": header_define(ASSET_PROFILE_H, "HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES"),
    }


def package_media_bytes():
    """Independently addressable media per selected package (r3 report), keyed by package name."""
    data = json.loads(PACKAGES.read_text())
    return {p["name"]: p["media_bytes_independent"] for p in data["packages"]}


def game_state_bytes():
    text = LIMITS.read_text()
    vals = {}
    for name in ("HALO_PORT_GAME_STATE_CPU_SIZE", "HALO_PORT_GAME_STATE_GPU_SIZE"):
        m = re.search(rf"#define {name}\s+(0x[0-9A-Fa-f]+|\d+)", text)
        if not m:
            raise SystemExit(f"missing {name} in {LIMITS}")
        vals[name] = int(m.group(1), 0)
    return vals["HALO_PORT_GAME_STATE_CPU_SIZE"] + vals["HALO_PORT_GAME_STATE_GPU_SIZE"]


def budget_check(budget):
    regions = budget["regions"]
    total = sum(r["bytes"] for r in regions)
    reserve = next(r for r in regions if r["role"] == "reserve")["bytes"]
    committed = total - reserve
    ok = (total == 33554432 and reserve == RESERVE and committed == COMMITTED
          and budget["committed_bytes"] == COMMITTED and budget["reserve_bytes"] == RESERVE)
    return {
        "total_bytes": total,
        "committed_bytes": committed,
        "reserve_bytes": reserve,
        "reserve_start_offset": committed,
        "pass": ok,
        "regions": {r["name"]: r["bytes"] for r in regions},
    }


def ui_profile(memory):
    """The 27th archived profile (ui) is absent from the session capacity matrix."""
    row = next(p for p in memory["profiles"] if p["profile"] == "ui")
    return {
        "name": "ui",
        "map": "ui",
        "map_matrix_case": "ui",
        "local_players": 0,
        "aligned_ce_owner_bytes": align16(row["resident_ce_bytes"]),
        "aligned_bsp_owner_bytes": align16(row["bsp_payload_bytes"]),
        "resident_ce_bytes": row["resident_ce_bytes"],
        "bsp_payload_bytes": row["bsp_payload_bytes"],
        "ctag_relocation_staging_bytes": row["relocation_table_staging_bytes"],
        "full_union_resident_ce_bytes": row["resident_ce_bytes"],
        "render_owner_residual_after_ce_bsp_alignment_and_guard_bytes":
            MAP_RENDER_BYTES - (align16(row["resident_ce_bytes"]) + GUARD + align16(row["bsp_payload_bytes"])),
        "source": "docs/reports/m2-c2-profile-memory-audit-2026-10-23.json",
    }


def build_rows(capacity, terms, ui):
    gs = game_state_bytes()
    media = package_media_bytes()
    rows = []
    profiles = list(capacity["profiles"]) + [ui]
    for p in profiles:
        ce = p["aligned_ce_owner_bytes"]
        bsp = p["aligned_bsp_owner_bytes"]
        if ce != align16(p["resident_ce_bytes"]) or bsp != align16(p["bsp_payload_bytes"]):
            raise SystemExit(f"alignment mismatch for {p['name']}")
        map_parent = ce + GUARD + bsp
        # The render span is what remains of the texture parent after the residency span and its guard.
        render = MAP_RENDER_BYTES - map_parent - GUARD - RESIDENCY_BYTES
        claims = math.ceil((ce + bsp) / CLAIM_BITS) * CLAIM_WORD
        resident_need = gs + claims
        residual_check = p["render_owner_residual_after_ce_bsp_alignment_and_guard_bytes"]
        after_workspace = render - terms["packet_workspace_bytes"] - terms["reserved_texture_bytes"]
        staging_slots = terms["staging_slots"] * terms["staging_slot_bytes"]
        staging_simultaneous = p["ctag_relocation_staging_bytes"] + staging_slots
        pages_available = after_workspace // terms["texture_page_bytes"]
        media_bytes = media.get(p["name"])
        # Only whole-package media is measured (sounds included); no bitmap-only bytes exist in the inputs,
        # so the page need is an upper bound and not an estimate of the working set.
        pages_needed_bound = None if media_bytes is None else math.ceil(media_bytes / terms["texture_page_bytes"])
        rows.append({
            "name": p["name"],
            "map": p["map"],
            "map_matrix_case": p["map_matrix_case"],
            "local_players": p["local_players"],
            "tag_cache_bytes": ce,
            "structure_bsp_bytes": bsp,
            "map_parent_bytes": map_parent,
            "render_texture_bytes": render,
            "residency_bytes": RESIDENCY_BYTES,
            "residency_guard_bytes": GUARD,
            "render_residual_matches_capacity_report": render + GUARD + RESIDENCY_BYTES == residual_check,
            "map_render_backing_bytes": MAP_RENDER_BYTES,
            "claims_scratch_bytes": claims,
            "resident_gameplay_need_bytes": resident_need,
            "resident_gameplay_cap_bytes": RESIDENT_CAP,
            "resident_fits": resident_need <= RESIDENT_CAP,
            "resident_margin_bytes": RESIDENT_CAP - resident_need,
            "fits_guarded_map_render_backing":
                map_parent + render + GUARD + RESIDENCY_BYTES == MAP_RENDER_BYTES and render >= 0,
            "render_margin_before_renderer_minimum_bytes": render,
            "renderer_packet_workspace_bytes": terms["packet_workspace_bytes"],
            "renderer_reserved_texture_bytes": terms["reserved_texture_bytes"],
            "render_residual_after_renderer_terms_bytes": after_workspace,
            "texture_cache_pages_available": pages_available,
            "package_media_bytes": media_bytes,
            "texture_pages_needed_upper_bound": pages_needed_bound,
            "texture_pages_short_of_upper_bound":
                None if pages_needed_bound is None else pages_available < pages_needed_bound,
            "ctag_relocation_staging_bytes": p["ctag_relocation_staging_bytes"],
            "staging_slot_bytes": staging_slots,
            "simultaneous_staging_bytes": staging_simultaneous,
            "ctag_relocation_owner": "streaming/map-load staging",
            "full_union_resident_ce_bytes": p["full_union_resident_ce_bytes"],
            "source": p.get("source", "docs/reports/m2-c2-session-map-capacity-2026-10-23.json"),
        })
    return rows


def elf_audit(path, reserve_start, budget_static, budget_streaming, validator_stream):
    attribution = elf_owners.attribute(Path(path))
    loads_mem = subprocess.run(
        [str(elf_owners.READELF), "-lW", str(path)], capture_output=True, text=True, check=True).stdout
    mem_total = 0
    end = 0
    for line in loads_mem.splitlines():
        parts = line.split()
        if parts and parts[0] == "LOAD":
            vaddr, memsz = int(parts[2], 16), int(parts[5], 16)
            mem_total += memsz
            end = max(end, vaddr + memsz)
    attribution["highest_guest_byte_exclusive"] = end
    attribution["below_reserve"] = end <= reserve_start
    attribution["load_mem_size_total"] = mem_total
    attribution["elf_static_reservation_bytes"] = budget_static
    attribution["elf_static_excess_bytes"] = attribution["elf_static_need_bytes"] - budget_static
    attribution["elf_static_fits"] = attribution["elf_static_need_bytes"] <= budget_static
    attribution["streaming_owned_bss_bytes"] = attribution["owned_bss_by_region"].get("streaming", 0)
    attribution["streaming_reservation_bytes"] = budget_streaming
    attribution["streaming_owned_bss_fits"] = attribution["streaming_owned_bss_bytes"] <= budget_streaming
    attribution["path"] = str(Path(path).relative_to(ROOT)) if str(path).startswith(str(ROOT)) else str(path)
    return attribution


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--elf", action="append", default=[], help="linked EE ELF to check (repeatable)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    budget = json.loads(BUDGET.read_text())
    capacity = json.loads(CAPACITY.read_text())
    memory = json.loads(PROFILE_MEMORY.read_text())
    budget_result = budget_check(budget)
    terms = renderer_terms()
    rows = build_rows(capacity, terms, ui_profile(memory))

    fit = [r for r in rows if r["fits_guarded_map_render_backing"] and r["resident_fits"]]
    nofit = [r for r in rows if r not in fit]
    max_claims = max(r["claims_scratch_bytes"] for r in rows)
    smallest_render = min(rows, key=lambda r: r["render_texture_bytes"])
    largest_render = max(rows, key=lambda r: r["render_texture_bytes"])
    smallest_after = min(rows, key=lambda r: r["render_residual_after_renderer_terms_bytes"])
    max_staging = max(r["simultaneous_staging_bytes"] for r in rows)

    budget_static = next(r["bytes"] for r in budget["regions"] if r["name"] == "elf_static")
    budget_streaming = next(r["bytes"] for r in budget["regions"] if r["name"] == "streaming")
    elfs = [elf_audit(Path(e), budget_result["committed_bytes"], budget_static, budget_streaming, None)
            for e in args.elf]

    table = {
        "format": "hcu-c2-partition-profile-v2",
        "date": "2026-10-23",
        "version": MAX_PROFILE_VERSION,
        "basis": "measured CE/BSP owner sizes from the session capacity report, plus the archived ui profile",
        "map_render_backing_bytes": MAP_RENDER_BYTES,
        "guard_bytes": GUARD,
        "profiles": rows,
    }
    audit = {
        "format": "hcu-c2-partition-budget-audit-v2",
        "date": "2026-10-23",
        "inputs": {
            "budget": str(BUDGET.relative_to(ROOT)),
            "capacity": str(CAPACITY.relative_to(ROOT)),
            "profile_memory": str(PROFILE_MEMORY.relative_to(ROOT)),
            "game_state_bytes": game_state_bytes(),
        },
        "renderer_terms": terms,
        "committed_budget": budget_result,
        "elf_static_reservation_bytes": budget_static,
        "streaming_reservation_bytes": budget_streaming,
        "elf": elfs,
        "profiles_checked": len(rows),
        "profiles_fitting_guarded_backing": len(fit),
        "profiles_not_fitting_guarded_backing": [r["name"] for r in nofit],
        "max_claims_scratch_bytes": max_claims,
        "max_simultaneous_staging_bytes": max_staging,
        "smallest_render_margin": {"profile": smallest_render["name"], "bytes": smallest_render["render_texture_bytes"]},
        "smallest_render_residual_after_renderer_terms": {
            "profile": smallest_after["name"], "bytes": smallest_after["render_residual_after_renderer_terms_bytes"]},
        "largest_render_margin": {"profile": largest_render["name"], "bytes": largest_render["render_texture_bytes"]},
        "texture_pages": {
            "page_bytes": terms["texture_page_bytes"],
            "rows_with_package_media": sum(1 for r in rows if r["package_media_bytes"] is not None),
            "rows_without_package_media": [r["name"] for r in rows if r["package_media_bytes"] is None],
            "rows_short_of_media_upper_bound": [r["name"] for r in rows if r["texture_pages_short_of_upper_bound"]],
            "note": ("No bitmap-only byte count exists in the inputs. The bound uses independently addressable "
                     "media (sounds included) and is not the working set, so the flag does not show a shortfall."),
        },
        "unmeasured": [
            "renderer live-set indices and their pages",
            "target workload peaks",
            "DMA lifetime during a map boundary",
            "resident gameplay usage beyond the game-state reservation and claims",
        ],
    }
    (out / "partition-table-profile-v2.json").write_text(json.dumps(table, indent=1) + "\n")
    (out / "budget-audit.json").write_text(json.dumps(audit, indent=1) + "\n")

    lines = []
    for r in rows:
        lines.append(
            "\t{ \"%s\", { HCU_MEMORY_PROFILE_VERSION_1, %d, %d, %d, %d } }, /* %s */" % (
                r["name"], r["tag_cache_bytes"], r["structure_bsp_bytes"],
                r["render_texture_bytes"], r["residency_bytes"], r["map_matrix_case"]))
    (out / "partition-table-profile-v2.inc").write_text("\n".join(lines) + "\n")

    print(json.dumps({
        "committed_pass": budget_result["pass"],
        "committed_bytes": budget_result["committed_bytes"],
        "profiles": len(rows),
        "fit": len(fit),
        "not_fit": [r["name"] for r in nofit],
        "smallest_render_margin": audit["smallest_render_margin"],
        "smallest_render_residual_after_renderer_terms": audit["smallest_render_residual_after_renderer_terms"],
        "elf": [{"path": e["path"], "highest": hex(e["highest_guest_byte_exclusive"]),
                 "below_reserve": e["below_reserve"], "elf_static_need": e["elf_static_need_bytes"],
                 "elf_static_excess": e["elf_static_excess_bytes"]} for e in elfs],
    }, indent=1))
    return 0 if budget_result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
