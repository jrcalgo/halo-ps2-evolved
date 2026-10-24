#!/usr/bin/env python3
"""Inventory separately sourced first-person pose assets and their consumers.

This is source/dependency metadata only. It does not create HCP chunks or claim
that the CE snapshot renderer consumes these legacy parent presentation arrays.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "6c0afbcf46ecd3a70ef5106e4f51d68414d5a389c1e0b1d14c47a2766abddfe0"
POSE_HEADER = struct.Struct("<4s6H2I")
POSE_NODE = struct.Struct("<IhBBHHHH")
POSE_MAX_BYTES = 65536
ASSETS = {
    "sword": {"header": "sword_idle.h", "prefix": "SWORD", "consumer_path": "weapons\\energy sword\\energy sword", "frames": 89, "jmad": "0xEE9B3436", "node_size_ilp32": 24, "supported": True},
    "gravity_rifle": {"header": "carbine_idle.h", "prefix": "CARBINE", "consumer_path": "weapons\\gravity rifle\\gravity rifle", "frames": 89, "jmad": "0xEC973232", "node_size_ilp32": 16, "supported": True},
    "fuel_rod": {"header": "flak_idle.h", "prefix": "FLAK", "consumer_path": "weapons\\fuel rod gun\\fuel rod", "frames": 73, "jmad": "0xEDCC3367", "node_size_ilp32": 16, "supported": False},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body(src: str, name: str) -> str:
    m = re.search(r"\b" + re.escape(name) + r"\s*(?:\[[^]]*\])?\s*=\s*\{", src)
    if not m:
        raise ValueError(f"missing initializer for {name}")
    start = src.find("{", m.start())
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{": depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start + 1:i]
    raise ValueError(f"unterminated initializer for {name}")


def _float_count(src: str, name: str) -> int:
    body = _body(src, name)
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)
    return len(re.findall(r"(?<![\w.])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?f\b", body))


def _float_values(src: str, name: str) -> list[float]:
    body = _body(src, name)
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)
    return [float(x) for x in re.findall(r"(?<![\w.])([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)f\b", body)]


def _node_records(src: str, prefix: str, sword: bool) -> list[tuple[str, int, int, int, int, int, int]]:
    body = _body(src, prefix + "NODE")
    rows = []
    # The generated headers use one initializer per line. Sword stores its
    # translation inline; carbine stores explicit translation sample ranges.
    for line in body.splitlines():
        m = re.search(r'\{\s*"([^"]+)"\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(.*)\}', line)
        if not m:
            continue
        name, parent, override, q_at, q_n, rest = m.groups()
        if sword:
            t_at, t_n = 0, 1
        else:
            vals = re.match(r"\s*,\s*(\d+)\s*,\s*(\d+)", rest)
            if not vals:
                raise ValueError(f"bad node translation range for {name}")
            t_at, t_n = map(int, vals.groups())
        rows.append((name, int(parent), int(override), int(q_at), int(q_n), t_at, t_n))
    return rows


def _pose_chunk(root: Path, asset: str) -> bytes:
    spec = ASSETS[asset]
    src = (root / "src/game" / spec["header"]).read_text()
    hold_src = (root / "src/game/hold_pose.h").read_text()
    prefix = "PLAY_FP_" + spec["prefix"] + "_"
    q = _float_values(src, prefix + "Q")
    t = [] if asset == "sword" else _float_values(src, prefix + "T")
    nodes = _node_records(src, prefix, asset == "sword")
    hold_key = {"sword": "SWORD", "gravity_rifle": "CARBINE"}[asset]
    hold_match = re.search(rf"PLAY_FP_Q_{hold_key}\[4\]\s*=\s*\{{([^}}]+)\}}", hold_src)
    mesh_q = _float_values(src, prefix + ("HANDLE_Q" if asset == "sword" else "GUN_Q"))
    mesh_t = _float_values(src, prefix + ("HANDLE_T" if asset == "sword" else "GUN_T"))
    if not hold_match:
        raise ValueError(f"missing camera hold quaternion for {asset}")
    hold_q = [float(v) for v in re.findall(r"([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)f", hold_match.group(1))]
    constants = hold_q + mesh_q + mesh_t
    if len(q) % 4 or len(t) % 3 or len(constants) != 11 or not nodes:
        raise ValueError(f"invalid {asset} source array cardinality")
    if any(not math.isfinite(v) for v in q + t + constants):
        raise ValueError(f"non-finite {asset} source float")
    name_blob = bytearray()
    name_offsets = {}
    for row in nodes:
        name = row[0]
        if name in name_offsets:
            raise ValueError(f"duplicate node name {name}")
        name_offsets[name] = len(name_blob)
        name_blob.extend(name.encode("ascii") + b"\0")
    node_blob = bytearray()
    for node_index, (name, parent, override, q_at, q_n, t_at, t_n) in enumerate(nodes):
        if not 0 <= q_at < len(q) // 4 or q_n < 1 or q_at + q_n > len(q) // 4:
            raise ValueError(f"invalid quaternion range for {name}")
        if t and (not 0 <= t_at < len(t) // 3 or t_n < 1 or t_at + t_n > len(t) // 3):
            raise ValueError(f"invalid translation range for {name}")
        if asset == "sword":
            t_at = node_index
        node_blob.extend(POSE_NODE.pack(name_offsets[name], parent, override, 0, q_at, q_n, t_at, t_n))
    if asset == "sword":
        # Sword translations are the fixed per-node bind/rest translations.
        t = [v for row in nodes for v in _node_inline_translation(src, row[0])]
    float_blob = struct.pack("<" + "f" * (len(q) + len(t) + len(constants)), *(q + t + constants))
    body = bytes(name_blob + node_blob) + float_blob
    header = POSE_HEADER.pack(b"HPOS", 1, 1 if asset == "sword" else 2,
                              int(spec["frames"]), len(nodes), len(q) // 4,
                              len(t) // 3, len(name_blob), len(body))
    result = header + body
    if len(result) > POSE_MAX_BYTES or len(nodes) > 64 or int(spec["frames"]) > 256:
        raise ValueError("pose asset exceeds fixed HPOS v1 bounds")
    return result


def _node_inline_translation(src: str, target: str) -> list[float]:
    body = _body(src, "PLAY_FP_SWORD_NODE")
    for line in body.splitlines():
        if f'"{target}"' not in line:
            continue
        m = re.search(r"\{\s*([-+0-9.eE]+)f\s*,\s*([-+0-9.eE]+)f\s*,\s*([-+0-9.eE]+)f\s*\}\s*\}\s*,?", line)
        if m:
            return [float(x) for x in m.groups()]
    raise ValueError(f"missing sword translation for {target}")


def build_presentation(root: Path = ROOT) -> dict:
    """Build independently addressable pointer-free sword and gravity pose blobs."""
    root = Path(root)
    chunks = {1: _pose_chunk(root, "sword"), 2: _pose_chunk(root, "gravity_rifle")}
    bindings = []
    provenance = {}
    for asset, cid in (("sword", 1), ("gravity_rifle", 2)):
        spec = ASSETS[asset]
        header = root / "src/game" / spec["header"]
        binding = {"asset_id": asset, "tag_group": "weap", "tag_path": spec["consumer_path"],
                   "jmad": spec["jmad"], "kind": "POSE", "chunk_id": cid,
                   "chunk_sha256": hashlib.sha256(chunks[cid]).hexdigest(),
                   "runtime_admitted": False}
        bindings.append(binding)
        provenance[asset] = {"source_map": "Halo 2 Vista shared.map",
                             "source_map_build": "11081.07.04.30.0934.main",
                             "source_map_sha256": SOURCE_SHA,
                             "source_map_path": "build/h2-reference/shared.map",
                             "source_map_retained": False,
                             "source_header": str(header.relative_to(root)),
                             "source_header_sha256": sha(header)}
    adapter_paths = [root / "src/game/sword_idle.h", root / "src/game/carbine_idle.h",
                     root / "src/game/hold_pose.h", root / "src/game/play_fp.c",
                     root / "tools/extract_sword_idle.py", root / "tools/extract_h2_hold.py"]
    return {"format": "hcu-pose-payload-set-v1", "chunk_magic": "HPOS", "chunk_version": 1,
            "chunks": chunks, "bindings": bindings, "provenance": provenance,
            "presentation_provenance": {"adapter_files": {str(p.relative_to(root)): sha(p) for p in adapter_paths},
                                         "source_animation_map": {"path": "build/h2-reference/shared.map",
                                                                  "sha256": SOURCE_SHA, "retained": False}},
            "memory": {"total_chunk_bytes": sum(map(len, chunks.values())),
                       "per_chunk_bytes": {str(k): len(v) for k, v in chunks.items()},
                       "retained_copy_bytes": sum(map(len, chunks.values())),
                       "lifetime": "caller owns immutable chunk bytes; sampler retains no pointers between calls"}}


def build_report(root: Path = ROOT) -> dict:
    consumer = root / "src/game/play_fp.c"
    pose = root / "src/game/hold_pose.h"
    plan = root / "plans/7.hcu-remake-m2-m4.md"
    final_plan = root / "docs/investigations/final_milestone_plan.md"
    weapon_report_path = root / "docs/reports/m2-c1-special-weapons-2026-10-23.json"
    weapon_report = json.loads(weapon_report_path.read_text())
    pose_set = build_presentation(root)
    report = {
        "format": "hcu-profile-presentation-dependencies-v1",
        "scope": "special_weapon_first_person_pose_assets",
        "source_provenance": {"source": "Halo 2 Vista shared.map", "build": "11081.07.04.30.0934.main", "sha256": SOURCE_SHA, "provenance_is_header_recorded": True},
        "governing_policy": {"plan": "plans/7.hcu-remake-m2-m4.md", "requirement": "C1-5", "policy": "include separately sourced presentation assets with preserved provenance; resolve and classify fuel-rod bitmap metadata before visual admission", "acceptance": "complete three weapon closures; resolve both fuel-rod bitmap metadata records before visual admission", "c1_payload_policy": "independently addressable chunks with integrity checks; include only data with proven live consumers"},
        "consumer": {"source": "src/game/play_fp.c", "kind": "legacy parent first-person wrapper", "exact_paths_and_callbacks_are_source_pinned": True, "linked_by": "tools/ee-world.mk", "ce_snapshot_renderer_consumer": False, "target_scene_qualification": False},
        "weapons": {},
        "custom_source_hashes": {},
    }
    source_paths = [consumer, pose, plan, final_plan, root / "tools/ee-world.mk",
                    root / "src/stream/hcu_pose_asset.c", root / "src/stream/hcu_pose_asset.h",
                    root / "tests/hcu_pose_asset_main.c", weapon_report_path,
                    root / "tools/hcu_profile_presentation.py"]
    report["source_pins"] = {str(p.relative_to(root)): sha(p) for p in source_paths}
    csrc, hsrc = consumer.read_text(), pose.read_text()
    for weapon, spec in ASSETS.items():
        rel = Path("src/game") / spec["header"]
        path = root / rel
        src = path.read_text()
        prefix = f"PLAY_FP_{spec['prefix']}_"
        qn = _float_count(src, prefix + "Q")
        tn = _float_count(src, prefix + "T") if weapon != "sword" else 0
        node_count = int(re.search(rf"#define {prefix}NODES (\d+)", src).group(1))
        frames = int(re.search(rf"#define {prefix}FRAMES (\d+)", src).group(1))
        oracle_count = len(re.findall(rf"\b{prefix}ORACLE\s*\[", src))
        in_consumer = spec["consumer_path"].replace("\\", "\\\\") in csrc and f"play_fp_{spec['prefix'].lower()}_" in csrc
        if weapon == "fuel_rod":
            # Explicit source branch: the fuel-rod model seats on the rocket launcher graph.
            live_arrays = False
            disposition = "exclude_pose_arrays_from_profile_payload; fuel rod uses CE generic weapon path and arms-only presentation per plan"
            caveat = "legacy HOLDS table contains flak callbacks, but active fuel-rod branch rejects hold-arms and seats via rocket-launcher graph; no qualified CE renderer consumer"
        else:
            live_arrays = in_consumer
            disposition = "candidate separately sourced pose dependency for legacy sword/gravity adapter; not yet bound to CE snapshot renderer"
            caveat = "legacy parent consumer only; profile chunk admission requires a proven live target consumer"
        # Required payload bytes include packed node records and consumed sampled arrays;
        # oracle arrays are test-only and intentionally omitted.
        chunk_id = None
        if weapon == "fuel_rod":
            arrays = {"legacy_quaternion_source_bytes": qn * 4,
                      "legacy_translation_source_bytes": tn * 4,
                      "legacy_node_records_ilp32": node_count * spec["node_size_ilp32"]}
            payload = 0
        else:
            chunk_id = 1 if weapon == "sword" else 2
            chunk = pose_set["chunks"][chunk_id]
            _magic, _version, _asset, _frames, wire_nodes, q_samples, t_samples, name_bytes, _body = POSE_HEADER.unpack_from(chunk)
            arrays = {"header_bytes": POSE_HEADER.size, "node_names_bytes": name_bytes,
                      "pointer_free_node_records_bytes": wire_nodes * POSE_NODE.size,
                      "quaternion_sample_bytes": q_samples * 16,
                      "translation_sample_bytes": t_samples * 12,
                      "camera_and_weapon_transform_constants_bytes": 44}
            payload = len(chunk)
        report["weapons"][weapon] = {
            "tag_path": spec["consumer_path"], "jmad": spec["jmad"], "header": str(rel), "header_sha256": sha(path),
            "frames": frames, "nodes": node_count, "consumer_reference": in_consumer,
            "consumer_reference_kind": "HOLDS table entry; active sampling path rejected for fuel rod" if weapon == "fuel_rod" else "legacy parent callback table and sampling path",
            "active_legacy_array_sampling": bool(live_arrays),
            "consumed_arrays": [prefix + x for x in (["Q", "NODE"] if weapon == "sword" else ["Q", "T", "NODE"])],
            "array_payload_bytes": arrays, "candidate_runtime_payload_bytes": payload,
            "chunk_kind": "POSE" if chunk_id is not None else None, "chunk_id": chunk_id,
            "chunk_sha256": hashlib.sha256(pose_set["chunks"][chunk_id]).hexdigest() if chunk_id is not None else None,
            "oracle_fixture_only": {"array": prefix + "ORACLE", "present": bool(oracle_count), "included_in_runtime_payload": False},
            "profile_disposition": disposition, "limitation": caveat,
        }
        report["custom_source_hashes"][weapon] = {"header": sha(path), "header_path": str(rel), "source_map_sha256": SOURCE_SHA}
    # Pin/expose actual named consumer functions, including the fuel-rod diversion.
    report["consumer_references"] = {
        "pose_table": "HOLDS", "sword_callbacks": ["play_fp_sword_find", "play_fp_sword_node_quat", "play_fp_sword_on_hand"],
        "gravity_callbacks": ["play_fp_carbine_find", "play_fp_carbine_node_quat", "play_fp_carbine_node_trans", "play_fp_carbine_on_hand"],
        "fuel_rod_callbacks_listed": ["play_fp_flak_find", "play_fp_flak_node_quat", "play_fp_flak_node_trans", "play_fp_flak_on_hand"],
        "fuel_rod_active_pose": "rocket-launcher graph; no active flak idle sampling",
        "hold_arms_rejects_fuel_rod": bool(re.search(r"fuel rod|fuel_rod", csrc, re.I)),
    }
    report["memory_summary"] = {
        "candidate_sword_and_gravity_pose_bytes": sum(len(b) for b in pose_set["chunks"].values()),
        "fuel_rod_pose_payload_bytes": 0,
        "measurement_basis": "exact independently serialized HPOS v1 chunk byte lengths; includes string table, fixed-width pointer-free nodes, frame samples and transform constants",
        "chunk_bytes": {str(k): len(v) for k, v in pose_set["chunks"].items()},
        "not_included": ["CE tags/textures", "renderer command/frame storage", "flak pose/oracle fixture", "HCP directory/alignment overhead"],
    }
    report["acceptance_assessment"] = {
        "separate_source_provenance_retained": True,
        "independent_chunks_required_by_policy": True,
        "current_chunks_exist_for_these_pose_assets": True,
        "legacy_compiled_assets_satisfy_independent_chunk_requirement": False,
        "only_proven_live_consumer_is_legacy_parent_wrapper": True,
        "qualified_hcu_target_consumer": False,
        "result": "partial",
        "concrete_gap": "Sword/gravity HPOS chunks now have a pointer-free C parser/sampler and exhaustive host parity; profile builder integration must join them to selected source-owner tuples and HCP media catalog entries. No target renderer or CE snapshot consumer is claimed. The pinned C1 special-weapons audit reports overall visual_admitted=true under its base/diffuse policy while classifying optional cube reflections for omission; this is not full visual parity. Fuel-rod flak pose bytes remain excluded because the governing plan calls for arms-only presentation.",
    }
    report["special_weapons_audit"] = {
        "path": str(weapon_report_path.relative_to(root)), "sha256": sha(weapon_report_path),
        "overall_visual_admitted": weapon_report.get("visual_admitted"),
        "presentation_policy": weapon_report.get("presentation_policy"),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path("build/m2-c1-presentation-dependencies/report.json"))
    args = ap.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "sha256": sha(args.output), "result": report["acceptance_assessment"]["result"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
