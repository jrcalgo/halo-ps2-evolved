"""Decode Halo 2 carbine and flak first-person idles into port pose tables.

The carbine idle is the gravity rifle's pose. The flak idle is the fuel rod's
pose. Reads the ignored shared.map under build/h2-reference/. Does not copy
Halo 2 meshes and does not open the ISO.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

from extract_sword_idle import (
    MAP, MAP_SHA, ce_name, cfloat, channel, f32, f32s, load_ce_arms, mat_from_trs,
    mat_mul, read_mask, read_q, u32,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "build/h2-reference"

ARM = [
    "base", "l_upperarm", "r_upperarm", "l_forearm", "r_forearm", "l_hand", "r_hand",
    "l_index_low", "l_middle_low", "l_pinky_low", "l_ring_low", "l_thumb_low",
    "r_index_low", "r_middle_low", "r_pinky_low", "r_ring_low", "r_thumb_low",
    "l_index_mid", "l_middle_mid", "l_pinky_mid", "l_ring_mid", "l_thumb_mid",
    "r_index_mid", "r_middle_mid", "r_pinky_mid", "r_ring_mid", "r_thumb_mid",
    "l_index_tip", "l_middle_tip", "l_pinky_tip", "l_ring_tip", "l_thumb_tip",
    "r_index_tip", "r_middle_tip", "r_pinky_tip", "r_ring_tip", "r_thumb_tip",
]
CARBINE_TAIL = ["gun", "barrel", "battery", "hood", "display", "camera_control"]
FLAK_TAIL = ["gun", "ammo_bottom", "barrel", "ammo_top", "cowling", "camera_control"]
CARBINE_PARENTS = [6, 37, 37, 37, 39, 0]
FLAK_PARENTS = [6, 37, 37, 38, 39, 0]

JOBS = (
    {
        "key": "carbine",
        "prefix": "CARBINE",
        "guard": "GAME_CARBINE_IDLE_H",
        "header": ROOT / "src/game/carbine_idle.h",
        "json": OUT_DIR / "carbine-idle-oracle.json",
        "offset": 0xBC0B5A0,
        "size": 6836,
        "frames": 89,
        "datum": "0xEC973232",
        "port": "gravity rifle",
        "names": ARM + CARBINE_TAIL,
        "tail_parents": CARBINE_PARENTS,
        "gun": 37,
        "camera": 42,
        "expect_x": (0.99857987, 0.05268516, 0.00790667),
    },
    {
        "key": "flak",
        "prefix": "FLAK",
        "guard": "GAME_FLAK_IDLE_H",
        "header": ROOT / "src/game/flak_idle.h",
        "json": OUT_DIR / "flak-idle-oracle.json",
        "offset": 0xBD3B590,
        "size": 3952,
        "frames": 73,
        "datum": "0xEDCC3367",
        "port": "fuel rod",
        "names": ARM + FLAK_TAIL,
        "tail_parents": FLAK_PARENTS,
        "gun": 37,
        "camera": 42,
        "expect_x": (0.99487001, 0.04482703, -0.09068741),
    },
)


def decode(blob: bytes, names: list[str], frames: int) -> dict:
    count = len(names)
    words = (count + 31) // 32
    mask_bytes = words * 4
    masks_at = len(blob) - 6 * mask_bytes
    masks = [read_mask(blob, masks_at + m * mask_bytes, count) for m in range(6)]
    static_rot, static_trans, static_scale = blob[1], blob[2], blob[3]
    anim = max(
        32 + static_rot * 8,
        u32(blob, 12) + static_trans * 12,
        u32(blob, 16) + static_scale * 4,
    )
    if blob[anim] != 3:
        raise RuntimeError("animated section is not codec 3")
    expected = [static_rot, static_trans, static_scale, blob[anim + 1], blob[anim + 2], blob[anim + 3]]
    if [sum(mask) for mask in masks] != expected:
        raise RuntimeError(f"mask popcounts {[sum(m) for m in masks]} != {expected}")
    rot_stride = u32(blob, anim + 20)
    trans_stride = u32(blob, anim + 24)
    if rot_stride != frames * 8:
        raise RuntimeError(f"rotation stride {rot_stride} is not {frames} frames")
    anim_trans = blob[anim + 2]
    trans_at = u32(blob, anim + 12) if anim_trans else 0
    animated_end = anim + 32 + blob[anim + 1] * rot_stride
    if anim_trans:
        animated_end = max(animated_end, anim + trans_at + anim_trans * trans_stride)
    if animated_end != masks_at:
        raise RuntimeError(f"animated data ends at {animated_end:#x}, masks at {masks_at:#x}")
    both = [names[n] for n in range(count) if masks[0][n] and masks[3][n]]
    if both:
        raise RuntimeError("static and animated rotation on " + ", ".join(both))
    both_t = [names[n] for n in range(count) if masks[1][n] and masks[4][n]]
    if both_t:
        raise RuntimeError("static and animated translation on " + ", ".join(both_t))
    scale = f32(blob, u32(blob, 16))
    if abs(scale - 1.0) > 1e-5:
        raise RuntimeError(f"static scale {scale} is not 1")
    return {
        "masks": masks,
        "static_trans_at": u32(blob, 12),
        "anim": anim,
        "rot_stride": rot_stride,
        "trans_stride": trans_stride,
        "trans_at": trans_at,
        "header_rate": f32(blob, anim + 8),
    }


def sample(blob: bytes, info: dict, names: list[str], ce: list[dict], frame: int):
    masks = info["masks"]
    local_q, local_t, override = [], [], []
    for n, name in enumerate(names):
        if n < 37:
            if ce[n]["name"] != ce_name(name):
                raise RuntimeError(f"{name} maps to {ce_name(name)}, model has {ce[n]['name']}")
            local_t.append(list(ce[n]["t"]))
        else:
            local_t.append([0.0, 0.0, 0.0])
        local_q.append([0.0, 0.0, 0.0, 1.0])
        rot = channel(masks[0], n)
        if rot >= 0:
            local_q[n] = read_q(blob, 32 + rot * 8)
        anim_rot = channel(masks[3], n)
        if anim_rot >= 0:
            at = info["anim"] + 32 + anim_rot * info["rot_stride"] + frame * 8
            local_q[n] = read_q(blob, at)
        trans = channel(masks[1], n)
        anim_trans = channel(masks[4], n)
        override.append(trans >= 0 or anim_trans >= 0)
        if trans >= 0:
            p = info["static_trans_at"] + trans * 12
            local_t[n] = [f32(blob, p), f32(blob, p + 4), f32(blob, p + 8)]
        if anim_trans >= 0:
            p = info["anim"] + info["trans_at"] + anim_trans * info["trans_stride"] + frame * 12
            local_t[n] = [f32(blob, p), f32(blob, p + 4), f32(blob, p + 8)]
    return local_q, local_t, override


def compose(local_q, local_t, parents):
    world = [None] * len(parents)
    pending = set(range(len(parents)))
    while pending:
        ready = [n for n in pending if parents[n] < 0 or parents[n] not in pending]
        if not ready:
            raise RuntimeError("cycle in the hold skeleton")
        for n in ready:
            local = mat_from_trs(local_q[n], local_t[n])
            parent = parents[n]
            world[n] = local if parent < 0 else mat_mul(local, world[parent])
            pending.remove(n)
    return world


def write_header(job, quats, trans, nodes, oracle, gun_q, gun_t, rate, move) -> None:
    prefix = job["prefix"]
    lines = [
        "/* Generated by tools/extract_h2_hold.py. Do not edit by hand.",
        " * Halo 2 Vista shared.map SHA-256",
        f" * {MAP_SHA}.",
        f" * jmad {job['datum']} first_person:idle, {job['frames']} frames,",
        f" * file offset {job['offset']:#x}. This is the {job['port']} pose.",
        " * Rotations are tag samples used as Hamilton quaternions. The CE mesh",
        " * root sits on the gun node (gun local x right wrist). No First Person",
        " * Weapon Offset is applied. Playback is one frame per 30 Hz tick; the",
        f" * codec header float is {rate:.6f}, not a frame rate.",
        f" * Right-hand travel across the loop: {move:.4f} m. */",
        f"#ifndef {job['guard']}",
        f"#define {job['guard']}",
        "#include <stdint.h>",
        "#include <string.h>",
        f"#define PLAY_FP_{prefix}_FRAMES {job['frames']}",
        f"#define PLAY_FP_{prefix}_NODES {len(nodes)}",
        "typedef struct {",
        "    const char *name;",
        "    int16_t parent;",
        "    uint8_t trans_override;",
        "    uint16_t q_at;",
        "    uint16_t q_n;",
        "    uint16_t t_at;",
        "    uint16_t t_n;",
        f"}} play_fp_{job['key']}_node;",
        "typedef struct {",
        "    float l_hand[3];",
        "    float r_hand[3];",
        "    float index_tip[3];",
        "    float gun[3];",
        "    float gun_x[3];",
        f"}} play_fp_{job['key']}_oracle;",
        f"static const float PLAY_FP_{prefix}_Q[] = {{",
    ]
    for i in range(0, len(quats), 4):
        lines.append("    " + ", ".join(cfloat(c) for c in quats[i:i + 4]) + ",")
    lines.append("};")
    lines.append(f"static const float PLAY_FP_{prefix}_T[] = {{")
    for i in range(0, len(trans), 3):
        lines.append("    " + ", ".join(cfloat(c) for c in trans[i:i + 3]) + ",")
    lines.append("};")
    lines.append(f"static const play_fp_{job['key']}_node PLAY_FP_{prefix}_NODE[PLAY_FP_{prefix}_NODES] = {{")
    for node in nodes:
        lines.append(
            f'    {{ "{node["name"]}", {node["parent"]}, {node["override"]}, '
            f'{node["q_at"]}, {node["q_n"]}, {node["t_at"]}, {node["t_n"]} }},'
        )
    lines.append("};")
    lines.append(
        f"static const float PLAY_FP_{prefix}_GUN_Q[4] = {{ "
        + ", ".join(cfloat(c) for c in gun_q) + " };"
    )
    lines.append(
        f"static const float PLAY_FP_{prefix}_GUN_T[3] = {{ "
        + ", ".join(cfloat(c) for c in gun_t) + " };"
    )
    if job["key"] == "flak":
        lines.append(
            "/* CE fuel-rod vertices reach x=-0.336. The Halo 2 flak geometry reaches\n"
            " * 0.174 m behind its gun node (bounds min -0.232 minus the gun-node\n"
            " * x -0.058). This shifts the CE mesh forward along the gun so those rears match. */"
        )
        lines.append("static const float PLAY_FP_FLAK_MESH_X = 0.162027f;")
    lines.append(
        f"static const play_fp_{job['key']}_oracle "
        f"PLAY_FP_{prefix}_ORACLE[PLAY_FP_{prefix}_FRAMES] = {{"
    )
    for frame in oracle:
        def vec(name: str) -> str:
            return ", ".join(cfloat(c) for c in frame[name])
        lines.append(
            "    {{" + vec("l_hand") + "}, {" + vec("r_hand") + "}, {"
            + vec("index_tip") + "}, {" + vec("gun") + "}, {" + vec("gun_x") + "}},"
        )
    key = job["key"]
    lines += [
        "};",
        f"static inline int play_fp_{key}_find(const char *name)",
        "{",
        f"    int i;",
        f"    for (i = 0; i < PLAY_FP_{prefix}_NODES; i++)",
        f"        if (strcmp(PLAY_FP_{prefix}_NODE[i].name, name) == 0) return i;",
        "    return -1;",
        "}",
        f"static inline const float *play_fp_{key}_node_quat(int node, int frame)",
        "{",
        f"    const play_fp_{key}_node *n = &PLAY_FP_{prefix}_NODE[node];",
        f"    unsigned f = n->q_n > 1 ? (unsigned)frame % PLAY_FP_{prefix}_FRAMES : 0u;",
        f"    return &PLAY_FP_{prefix}_Q[(n->q_at + f) * 4];",
        "}",
        f"static inline const float *play_fp_{key}_node_trans(int node, int frame)",
        "{",
        f"    const play_fp_{key}_node *n = &PLAY_FP_{prefix}_NODE[node];",
        f"    unsigned f = n->t_n > 1 ? (unsigned)frame % PLAY_FP_{prefix}_FRAMES : 0u;",
        f"    return &PLAY_FP_{prefix}_T[(n->t_at + f) * 3];",
        "}",
        "#endif",
    ]
    job["header"].write_text("\n".join(lines) + "\n")


def build(data: bytes, ce: list[dict], job: dict) -> None:
    blob = data[job["offset"]:job["offset"] + job["size"]]
    if len(blob) != job["size"]:
        raise SystemExit(f"{job['key']} blob is short")
    info = decode(blob, job["names"], job["frames"])
    parents = [ce[i]["parent"] for i in range(37)] + job["tail_parents"]
    q0, t0, override = sample(blob, info, job["names"], ce, 0)
    quats: list[float] = []
    trans: list[float] = []
    nodes = []
    for n in range(37):
        animated_q = channel(info["masks"][3], n) >= 0
        animated_t = channel(info["masks"][4], n) >= 0
        q_at = len(quats) // 4
        t_at = len(trans) // 3
        q_n = job["frames"] if animated_q else 1
        t_n = job["frames"] if animated_t else 1
        if animated_q or animated_t:
            for frame in range(job["frames"]):
                q, t, _o = sample(blob, info, job["names"], ce, frame)
                if animated_q:
                    quats.extend(f32s(q[n]))
                if animated_t:
                    trans.extend(f32s(t[n]))
        if not animated_q:
            quats.extend(f32s(q0[n]))
        if not animated_t:
            trans.extend(f32s(t0[n]))
        nodes.append({
            "name": ce[n]["name"],
            "parent": parents[n],
            "override": 1 if override[n] else 0,
            "q_at": q_at,
            "q_n": q_n,
            "t_at": t_at,
            "t_n": t_n,
        })
    gun_q = f32s(q0[job["gun"]])
    gun_t = f32s(t0[job["gun"]])
    oracle = []
    for frame in range(job["frames"]):
        q, t, _o = sample(blob, info, job["names"], ce, frame)
        world = compose(q, t, parents)
        if frame == 0:
            cam = world[job["camera"]]
            if max(abs(cam[3][k]) for k in range(3)) > 1e-4:
                raise SystemExit(f"{job['key']} camera is not at the origin")
        gun = world[job["gun"]]
        oracle.append({
            "l_hand": f32s([world[5][3][0], world[5][3][1], world[5][3][2]]),
            "r_hand": f32s([world[6][3][0], world[6][3][1], world[6][3][2]]),
            "index_tip": f32s([world[32][3][0], world[32][3][1], world[32][3][2]]),
            "gun": f32s([gun[3][0], gun[3][1], gun[3][2]]),
            "gun_x": f32s([gun[0][0], gun[0][1], gun[0][2]]),
        })
    fwd = oracle[0]["gun_x"]
    if max(abs(fwd[k] - job["expect_x"][k]) for k in range(3)) > 1e-5:
        raise SystemExit(f"{job['key']} frame 0 gun axis {fwd} != {job['expect_x']}")
    move = max(math.dist(oracle[0]["r_hand"], oracle[f]["r_hand"]) for f in range(job["frames"]))
    if move < 0.0005:
        raise SystemExit(f"{job['key']} right hand does not move ({move} m)")
    write_header(job, quats, trans, nodes, oracle, gun_q, gun_t, info["header_rate"], move)
    job["json"].write_text(json.dumps({
        "map_sha256": hashlib.sha256(data).hexdigest(),
        "datum": job["datum"],
        "frames": job["frames"],
        "blob_offset": job["offset"],
        "gun_local_q": gun_q,
        "gun_local_t": gun_t,
        "mesh_seat": "CE model origin at the Halo 2 gun node; no extra mesh offset",
        "right_hand_travel_m": move,
        "frame0_gun": oracle[0]["gun"],
        "frame0_gun_x": oracle[0]["gun_x"],
    }, indent=2) + "\n")
    print(f"{job['key']}: {job['header'].name} {job['header'].stat().st_size} bytes, "
          f"hand travel {move:.3f} m, gun {oracle[0]['gun']}")


def main() -> None:
    data = MAP.read_bytes()
    if hashlib.sha256(data).hexdigest() != MAP_SHA:
        raise SystemExit("shared.map hash mismatch")
    ce = load_ce_arms()
    if len(ce) != 37:
        raise SystemExit("cyborg fp node count")
    for job in JOBS:
        build(data, ce, job)


if __name__ == "__main__":
    main()
