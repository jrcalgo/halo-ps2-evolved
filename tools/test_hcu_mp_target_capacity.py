#!/usr/bin/env python3
"""Exercise the current 13-map packages against the fixed PS2 map capacities.

This is an offline capacity/relocation gate, not a guest or native CE runtime
test. It uses the production CTAG/CBSP wire readers, enforces the configured
2 MiB tag + 4 MiB BSP split, computes the exact CE claims bitmap allocation,
and records why a runtime map query can or cannot be reached.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
import test_hcu_mp_capacity as mp  # package pins and stock-map paths
import cbsp
import ctag
from halo2ps2 import hp2

TAG_CAP = 2 * 1024 * 1024
BSP_CAP = 4 * 1024 * 1024
OWNER_CAP = 1024 * 1024
SCRATCH_CAP = 512 * 1024
CLAIMS_CAP = (TAG_CAP + BSP_CAP + 7) // 8

PACKAGES = {
    "beavercreek": ROOT / "build/m2-mp-extra/beavercreek-all-bsps.hp2",
    "bloodgulch": ROOT / "build/retail-maps/bloodgulch-with-bsps.hp2",
    "boardingaction": ROOT / "build/m2-mp-all-map-packages/boardingaction-all-bsps.hp2",
    "carousel": ROOT / "build/m2-mp-all-map-packages/carousel-all-bsps.hp2",
    "chillout": ROOT / "build/m2-mp-all-map-packages/chillout-all-bsps.hp2",
    "damnation": ROOT / "build/m2-mp-extra/damnation-wind-all-bsps.hp2",
    "hangemhigh": ROOT / "build/m2-mp-all-map-packages/hangemhigh-all-bsps.hp2",
    "longest": ROOT / "build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2",
    "prisoner": ROOT / "build/m2-mp-extra/prisoner-all-bsps.hp2",
    "putput": ROOT / "build/m2-mp-all-map-packages/putput-all-bsps.hp2",
    "ratrace": ROOT / "build/m2-mp-all-map-packages/ratrace-all-bsps.hp2",
    "sidewinder": ROOT / "build/m2-mp-all-map-packages/sidewinder-all-bsps.hp2",
    "wizard": ROOT / "build/m2-mp-all-map-packages/wizard-all-bsps.hp2",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(name: str, path: Path) -> dict:
    if sha(path) != mp.MP_PACKAGE_SHA256[name]:
        raise ValueError(f"{name}: package hash differs from audited 2fba pins")
    source_map = ROOT / f"build/retail-maps/decompressed/{name}.map"
    if not source_map.is_file() or sha(source_map) != mp.MP_SOURCE_SHA256[name]:
        raise ValueError(f"{name}: source-map hash differs from audited 2fba pins")
    pack = hp2.parse(path.read_bytes())
    ctag_payload = pack.read("CTAG")
    # Decode with the actual tag image cap. These known packages exceed it;
    # capture the exact production-shaped failure rather than silently parsing
    # against an oversized test buffer.
    try:
        image = ctag.decode(ctag_payload, max_image_size=TAG_CAP)
        tag_gate = "fits"
    except ctag.CtagError as error:
        image = ctag.decode(ctag_payload, max_image_size=0xFFFFFFFF)
        tag_gate = f"reject:{error}"

    bsp_rows = []
    for section in pack.sections:
        if len(section.tag) != 4 or not (section.tag.startswith("B") and
                                          section.tag[1:].isdigit()):
            continue
        payload = pack.read(section.tag)
        parsed = cbsp.decode(payload, max_image_size=BSP_CAP)
        # Exercise CE pointer rebasing on a non-overlapping diagnostic address
        # pair. This validates the envelope/relocations, not the runtime BSP
        # query consumer.
        materialized = parsed.materialize(0x02000000, 0x01000000, image.image)
        tail_bytes = (len(parsed.relocations) + len(parsed.tag_relocations)) * 12
        bsp_rows.append({
            "section": section.tag,
            "decoded_image_bytes": len(parsed.image),
            "relocation_count": len(parsed.relocations) + len(parsed.tag_relocations),
            "relocation_tail_bytes": tail_bytes,
            "transport_bytes": section.raw_size,
            "materialized_bytes": len(materialized),
            "bsp_gate": "fits",
        })
    if not bsp_rows:
        raise ValueError(f"{name}: missing CBSP sections")

    section_sizes = {section.tag: section.raw_size for section in pack.sections}
    missing = {"HMAP", "CRNG", "CBIX"} - set(section_sizes)
    if missing:
        raise ValueError(f"{name}: package lacks ownership sections {sorted(missing)}")

    # Match the actual preflight allocation sequence: decoded HMAP, CRNG,
    # CBIX (each output aligned to 64), then relocation rows (aligned to 4).
    # Map-owner begins on at least 16-byte alignment, but its cache-line phase
    # is not recorded by package data, so report the conservative maximum over
    # all possible 16-byte-aligned base phases.
    def allocated_end(base_phase: int, sizes: list[tuple[int, int]]) -> int:
        used = 0
        for size, alignment in sizes:
            address = base_phase + used
            used = ((address + alignment - 1) & ~(alignment - 1)) - base_phase + size
        return used

    preflight_allocations = [
        (section_sizes["HMAP"], 64), (section_sizes["CRNG"], 64),
        (section_sizes["CBIX"], 64), (len(image.relocations) * 4, 4),
    ]
    preflight_owner_peak = max(allocated_end(phase, preflight_allocations)
                               for phase in (0, 16, 32, 48))
    mount_allocations = [
        (section_sizes["CRNG"], 64), (section_sizes["CBIX"], 64),
        (len(image.relocations) * 4, 4),
    ]
    mount_owner_peak = max(allocated_end(phase, mount_allocations)
                           for phase in (0, 16, 32, 48))

    largest = max(bsp_rows, key=lambda row: row["decoded_image_bytes"])
    # Current BSP arena contains the 2 MiB tag reservation plus a disjoint
    # 4 MiB remainder. The loader streams the decoded image into that remainder
    # and stores relocation records in its tail, so include both in the peak.
    bsp_peak = largest["decoded_image_bytes"] + largest["relocation_tail_bytes"]
    image_bytes = len(image.image)
    # arena_alloc aligns absolute addresses. Parent guarantees 16-byte base
    # alignment, so the unknown cache-line phase adds at most 48 used bytes.
    reached_decode_scratch_peak = 98304 + 48
    full_preflight_scratch_peak = 262144 + 48
    owner_and_scratch_are_fixed = OWNER_CAP == 1024 * 1024 and SCRATCH_CAP == 512 * 1024
    return {
        "map": name,
        "package_sha256": sha(path),
        "source_map_sha256": sha(source_map),
        "ctag_image_bytes": image_bytes,
        "ctag_relocation_count": len(image.relocations),
        "tag_capacity_bytes": TAG_CAP,
        "tag_gate": tag_gate,
        "largest_cbsp": largest,
        "bsp_capacity_bytes": BSP_CAP,
        "bsp_peak_image_plus_relocation_tail_bytes": bsp_peak,
        "bsp_gate": "fits" if bsp_peak <= BSP_CAP else "reject:decoded image plus relocation tail exceeds 4 MiB",
        "paired_tag_plus_bsp_peak_bytes": image_bytes + bsp_peak,
        "map_owner_capacity_bytes": OWNER_CAP,
        "preflight_map_owner_peak_bound_bytes": preflight_owner_peak,
        "mount_map_owner_peak_bound_bytes": mount_owner_peak,
        "map_owner_gate": "fits" if max(preflight_owner_peak, mount_owner_peak) <= OWNER_CAP else "reject:owner allocation exceeds 1 MiB",
        "streaming_scratch_capacity_bytes": SCRATCH_CAP,
        "reached_path_streaming_scratch_peak_bound_bytes": reached_decode_scratch_peak,
        "full_success_path_streaming_scratch_peak_bound_bytes": full_preflight_scratch_peak,
        "streaming_scratch_gate": "fits" if full_preflight_scratch_peak <= SCRATCH_CAP else "reject:scratch high-water exceeds 512 KiB",
        "claims_capacity_bytes": CLAIMS_CAP,
        "source_hash_gate": "passed",
        "metadata_owner_gate": "static capacities recorded; runtime owner high-water unavailable in offline runner" if owner_and_scratch_are_fixed else "invalid profile",
        "map_load": "blocked-at-CTAG-capacity" if tag_gate.startswith("reject:") else "CTAG-accepted",
        "CE_query": "not-reachable:CTAG-capacity gate fails before map publication" if tag_gate.startswith("reject:") else "not-exercised-by-offline-runner",
    }


def main() -> int:
    rows = [audit(name, path) for name, path in PACKAGES.items()]
    if set(PACKAGES) != set(mp.MP_MAPS) or len(rows) != 13:
        raise SystemExit("runner requires exactly the 13 pinned stock multiplayer maps")
    for row in rows:
        row["claims_bitmap_formula"] = "ceil((2MiB + 4MiB) / 32 bits) * 4 bytes"
    output = {
        "schema": "hcu-mp-target-shaped-capacity-attempt-v1",
        "scope": "13 stock multiplayer packages only; campaign excluded",
        "profile": {
            "tag_bytes": TAG_CAP, "bsp_bytes": BSP_CAP,
            "map_owner_bytes": OWNER_CAP, "section_scratch_bytes": SCRATCH_CAP,
            "claims_bytes": CLAIMS_CAP,
        },
        "production_source": {
            "memory_bind_sha256": sha(ROOT / "src/stream/hcu_memory_bind.c"),
            "map_service_sha256": sha(ROOT / "src/stream/hcu_map_service.c"),
            "ctag_mount_sha256": sha(ROOT / "src/stream/ctag_mount.c"),
            "ctag_parser_sha256": sha(ROOT / "tools/ctag.py"),
            "cbsp_parser_sha256": sha(ROOT / "tools/cbsp.py"),
            "package_pin_source_sha256": sha(ROOT / "tests/test_hcu_mp_capacity.py"),
        },
        "parent_head": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "hcu_head": subprocess.check_output(["git", "-C", str(ROOT / "submodules/halo-ce-universal"), "rev-parse", "HEAD"], text=True).strip(),
        "halo_ps2_head": subprocess.check_output(["git", "-C", str(ROOT / "submodules/halo-ps2"), "rev-parse", "HEAD"], text=True).strip(),
        "all_13_ctag_fit": all(row["tag_gate"] == "fits" for row in rows),
        "all_13_cbsp_image_plus_tail_fit": all(row["bsp_gate"] == "fits" for row in rows),
        "all_13_map_owner_fits": all(row["map_owner_gate"] == "fits" for row in rows),
        "all_13_streaming_scratch_fits": all(row["streaming_scratch_gate"] == "fits" for row in rows),
        "all_13_load_and_query_reached": all(row["CE_query"] == "exercised" for row in rows),
        "maps": rows,
        "interpretation": [
            "This runner enforces exact fixed capacities with the production CTAG/CBSP envelope readers; no cache is enlarged.",
            "It decodes and rebases CBSP relocation records at diagnostic addresses, but does not execute HCU map service or CE BSP queries.",
            "CTAG capacity rejection is recorded as failure, not a pass; the current 2 MiB tag split prevents load/publication/query for packages whose CTAG exceeds it.",
            "Map-owner and section-scratch capacities are fixed profile values, but their runtime high-water marks need a guest or allowed native ILP32 execution.",
            "Package decoded image + relocation-tail is an offline lower-bound check; it is not EE simultaneous residency or timing evidence.",
        ],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
