#!/usr/bin/env python3
"""Validate a retained native ILP32 combined CE-map/texture diagnostic run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAPS = (
    "longest", "bloodgulch", "beavercreek", "prisoner", "boardingaction",
    "carousel", "chillout", "damnation", "hangemhigh", "putput", "ratrace",
    "sidewinder", "wizard",
)
TEXTURE_CAPACITY = 4_014_936
SCRATCH_CAPACITY = 524_288


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   cwd=ROOT, text=True).strip()


def main() -> int:
    aligned_pad8 = "--pad-texture-boundary-8" in sys.argv[1:]
    args = [arg for arg in sys.argv[1:] if arg != "--pad-texture-boundary-8"]
    if len(args) != 1:
        raise SystemExit("usage: verify_hcu_mp_candidate_combined_textures.py RETAINED_DIR [--pad-texture-boundary-8]")
    texture_capacity = 4_014_928 if aligned_pad8 else TEXTURE_CAPACITY
    bsp_capacity = 1_993_712 if aligned_pad8 else 1_993_704
    map_capacity = 6_470_832 if aligned_pad8 else 6_470_824
    retained = Path(args[0])
    if not retained.is_absolute():
        retained = ROOT / retained
    retained = retained.resolve()
    log = retained / "combined-texture-run.log"
    binaries = [p for p in retained.glob("mp-weather-wind*")
                if p.is_file() and p.suffix != ".map"]
    if len(binaries) != 1:
        raise SystemExit(f"expected one retained MP fixture executable, found {len(binaries)}")
    binary = binaries[0]
    linkmap = binary.with_suffix(".map")
    texture_root = retained / "assets/textures"
    for path in (log, binary, linkmap):
        if not path.is_file():
            raise SystemExit(f"required retained artifact missing: {path}")
    output = log.read_text(errors="replace")
    texture_re = re.compile(
        r"^mp-combined-texture map=(\w+) cycle=(\d+) texs=(\d+) lm_bytes=(\d+) "
        r"lm_count=(\d+) otex=(\d+) raw=(\d+) retained=(\d+) align_pad=(\d+) "
        r"peak=(\d+) rollback_peak=(\d+) scratch=(\d+)/(\d+) rollback=crc-safe$",
        re.MULTILINE)
    rows = []
    for match in texture_re.finditer(output):
        name, cycle = match.group(1), int(match.group(2))
        values = [int(x) for x in match.groups()[2:]]
        row = dict(zip((
            "texs_raw_bytes", "lm_raw_bytes", "lm_section_count", "otex_raw_bytes",
            "all_texture_raw_bytes", "texture_owner_retained_bytes", "alignment_bytes",
            "normal_peak_bytes", "rollback_peak_bytes", "scratch_high_water_bytes",
            "scratch_capacity_bytes"), values))
        row.update(map=name, cycle=cycle)
        rows.append(row)
    expected = {(name, cycle) for name in MAPS for cycle in (0, 1)}
    observed = {(r["map"], r["cycle"]) for r in rows}
    if len(rows) != 26 or observed != expected:
        raise SystemExit(f"expected 26 distinct map/cycle rows, got {len(rows)}")
    if any(r["normal_peak_bytes"] > texture_capacity or
           r["rollback_peak_bytes"] > texture_capacity or
           r["scratch_high_water_bytes"] > SCRATCH_CAPACITY or
           r["scratch_capacity_bytes"] != SCRATCH_CAPACITY or
           r["lm_section_count"] < 1 for r in rows):
        raise SystemExit("candidate texture/scratch capacity or LM assertion failed")
    host_rows = re.findall(
        r"^mp-host-map map=(\w+) cycle=(\d+) tag_cap=(\d+) bsp_cap=(\d+) "
        r"owner_used=(\d+) owner_high=(\d+) owner_cap=(\d+) scratch_high=(\d+) "
        r"scratch_cap=(\d+) claims_cap=(\d+)$", output, re.MULTILINE)
    if len(host_rows) != 26:
        raise SystemExit(f"expected 26 CE map capacity/query rows, got {len(host_rows)}")
    for name, cycle, tag_cap, bsp_cap, owner_used, owner_high, owner_cap, scratch_high, scratch_cap, claims_cap in host_rows:
        if (int(tag_cap), int(bsp_cap), int(owner_cap), int(scratch_cap), int(claims_cap)) != (
                4_477_120, bsp_capacity, 1_048_576, 524_288, 808_856):
            raise SystemExit(f"candidate CE owner/capacity mismatch on {name} cycle {cycle}")
        if int(owner_high) > int(owner_cap) or int(scratch_high) > int(scratch_cap):
            raise SystemExit(f"CE map-service owner/scratch overflow on {name} cycle {cycle}")
    expected_crc_errors = len(re.findall(
        r"^\[err\] textures/\w+\.bad\.tex\.hp2: decoding TEXS failed \(8\)$",
        output, re.MULTILINE))
    if expected_crc_errors != 26:
        raise SystemExit(f"expected 26 intentional TEXS CRC rejection/rollback cases, got {expected_crc_errors}")
    if "mp-host-collision 13-map CE hit/PVS/reload matrix passed; candidate ILP32 profile only; not PS2/EE" not in output:
        raise SystemExit("CE all-map semantic/query completion marker missing")
    if len(re.findall(r"^mp-weather-wind map=", output, re.MULTILINE)) != 26:
        raise SystemExit("CE weather/wind query did not complete on every loaded map")

    texture_assets = {}
    for p in sorted(texture_root.iterdir()):
        if p.is_file():
            texture_assets[p.name] = {"bytes": p.stat().st_size, "sha256": sha(p)}
    if len(texture_assets) != 39:
        raise SystemExit(f"expected 39 converter-backed wrapper files, found {len(texture_assets)}")
    manifest = {
        "schema": "hcu-mp-candidate-combined-map-texture-host-run-v1",
        "scope": "13 retail multiplayer maps, two load/query/unload cycles each; campaign excluded",
        "status": "passed-diagnostic-only",
        "profile": {
            "tag_cache_bytes": 4_477_120,
            "bsp_cache_bytes_including_sidewinder_tail": bsp_capacity,
            "combined_tag_bsp_bytes": map_capacity,
            "adjacent_texture_owner_bytes": texture_capacity,
            "combined_map_texture_bytes": 10_485_760,
            "map_owner_bytes": 1_048_576,
            "shared_section_scratch_bytes": SCRATCH_CAPACITY,
            "claims_bytes": 808_856,
        },
        "diagnostic_only": True,
        "native_ilp32_host_only": True,
        "ps2_ee_placement_or_performance_evidence": False,
        "texture_safety_or_render_success_proven": False,
        "production_budgets_or_admission_changed": False,
        "parents": {
            "parent": pin(ROOT),
            "halo_ce_universal": pin(ROOT / "submodules/halo-ce-universal"),
            "halo_ps2": pin(ROOT / "submodules/halo-ps2"),
        },
        "artifacts": {
            "retained_binary": str(binary.relative_to(ROOT)), "binary_sha256": sha(binary),
            "link_map": str(linkmap.relative_to(ROOT)), "link_map_sha256": sha(linkmap),
            "run_log": str(log.relative_to(ROOT)), "run_log_sha256": sha(log),
            "candidate_runner": "tools/test_hcu_mp_candidate_topology.py",
            "candidate_runner_sha256": sha(ROOT / "tools/test_hcu_mp_candidate_topology.py"),
            "c_texture_bridge": "tests/mp_texture_candidate_owner.c",
            "c_texture_bridge_sha256": sha(ROOT / "tests/mp_texture_candidate_owner.c"),
            "real_section_loader_sha256": sha(ROOT / "submodules/halo-ps2/engine/src/world/section.c"),
            "real_texture_parser_sha256": sha(ROOT / "submodules/halo-ps2/engine/src/world/tex.c"),
            "real_hp2_streamer_sha256": sha(ROOT / "submodules/halo-ps2/engine/src/stream/hp2.c"),
            "real_file_reader_sha256": sha(ROOT / "submodules/halo-ps2/engine/src/stream/file.c"),
            "real_arena_sha256": sha(ROOT / "submodules/halo-ps2/engine/src/core/mem.c"),
        },
        "converter_wrapper_assets": texture_assets,
        "row_count": len(rows),
        "all_map_cycle_rows": rows,
        "max_texture_normal_peak_bytes": max(r["normal_peak_bytes"] for r in rows),
        "max_texture_crc_failure_rollback_peak_bytes": max(r["rollback_peak_bytes"] for r in rows),
        "max_texture_alignment_overhead_bytes": max(r["alignment_bytes"] for r in rows),
        "max_shared_section_scratch_high_water_bytes": max(r["scratch_high_water_bytes"] for r in rows),
        "max_ce_map_owner_high_water_bytes": max(int(r[5]) for r in host_rows),
        "intentional_texture_crc_failures_and_safe_rollback": expected_crc_errors,
        "interpretation": [
            "Each CE tag/BSP map remains loaded during TEXS, all emitted LM sections, and scenario-selected OTEX load; CE collision/PVS/weather/sound queries then run before unload.",
            "TEXS/LM/OTEX bytes are production-converter outputs in narrowed HP2 wrappers; OTEX wrapper contains only OTEX, not the full object pack.",
            "The texture owner is a disjoint adjacent static slice in the 10 MiB host candidate store. The 512 KiB section scratch is the map fixture's same shared scratch slice, reused sequentially after CE map load.",
            "This does not model DMA/GS upload, renderer texture residency/eviction, simultaneous frame assets, target address placement, R5900 timing, or EE RAM contention.",
            "No dynamic_simulation actor/biped/animation/effect inventory is included; this measures only static per-map decoded texture-section ownership under this fixture topology.",
        ],
    }
    manifest_path = retained / "combined-texture-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"validated 26/26 CE map+texture rows; max texture peak="
          f"{manifest['max_texture_normal_peak_bytes']}/{texture_capacity}; "
          f"max CRC rollback peak={manifest['max_texture_crc_failure_rollback_peak_bytes']}; "
          f"manifest={manifest_path.relative_to(ROOT)} sha256={sha(manifest_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
