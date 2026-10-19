"""Decode the Halo 2 energy-blade first-person idle into port pose tables.

Reads the ignored shared.map staged under build/h2-reference/. Writes the
camera-relative oracle next to the map and the C tables the play build
links. Halo 2 meshes are not copied. The ISO is not opened.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "build/h2-reference/maps/shared.map"
OUT_H = ROOT / "src/game/sword_idle.h"
OUT_JSON = ROOT / "build/h2-reference/sword-idle-oracle.json"
CE_MAP = ROOT / "data/retail/weapon-audit-maps/bloodgulch.map"
BLOB_OFF = 0xBE4ECD0
BLOB_SIZE = 13864
FRAMES = 89
MAP_SHA = "6c0afbcf46ecd3a70ef5106e4f51d68414d5a389c1e0b1d14c47a2766abddfe0"

H2_NAMES = [
    "base", "l_upperarm", "r_upperarm", "l_forearm", "r_forearm", "l_hand", "r_hand",
    "l_index_low", "l_middle_low", "l_pinky_low", "l_ring_low", "l_thumb_low",
    "r_index_low", "r_middle_low", "r_pinky_low", "r_ring_low", "r_thumb_low",
    "l_index_mid", "l_middle_mid", "l_pinky_mid", "l_ring_mid", "l_thumb_mid",
    "r_index_mid", "r_middle_mid", "r_pinky_mid", "r_ring_mid", "r_thumb_mid",
    "l_index_tip", "l_middle_tip", "l_pinky_tip", "l_ring_tip", "l_thumb_tip",
    "r_index_tip", "r_middle_tip", "r_pinky_tip", "r_ring_tip", "r_thumb_tip",
    "handle", "blades", "camera_control",
]


def ce_name(h2: str) -> str:
    special = {
        "base": "frame bone24",
        "l_hand": "frame l wriste",
        "r_hand": "frame r wriste",
        "l_middle_low": "frame l middlelow",
    }
    if h2 in special:
        return special[h2]
    side, rest = h2.split("_", 1)
    return f"frame {side} {rest.replace('_', ' ')}"


def u32(blob: bytes, at: int) -> int:
    return struct.unpack_from("<I", blob, at)[0]


def f32(blob: bytes, at: int) -> float:
    return struct.unpack_from("<f", blob, at)[0]


def read_mask(blob: bytes, at: int, count: int) -> list[bool]:
    out = []
    for n in range(count):
        word = u32(blob, at + (n // 32) * 4)
        out.append((word & (1 << (n % 32))) != 0)
    return out


def channel(mask: list[bool], node: int) -> int:
    if not mask[node]:
        return -1
    return sum(1 for i in range(node) if mask[i])


def read_q(blob: bytes, at: int) -> list[float]:
    q = [struct.unpack_from("<h", blob, at + i * 2)[0] / 32767.0 for i in range(4)]
    n = math.sqrt(sum(c * c for c in q))
    if n == 0.0:
        raise RuntimeError(f"zero quaternion at {at:#x}")
    return [c / n for c in q]


def f32s(values: list[float]) -> list[float]:
    return [struct.unpack("<f", struct.pack("<f", c))[0] for c in values]


def cfloat(value: float) -> str:
    text = format(struct.unpack("<f", struct.pack("<f", value))[0], ".9g")
    if "." not in text and "e" not in text:
        text += ".0"
    return text + "f"


def mat_from_trs(q: list[float], t: list[float]) -> list[list[float]]:
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    k = 2.0 / n if n > 0.0 else 0.0
    xx, yy, zz = x * x * k, y * y * k, z * z * k
    xy, xz, yz = x * y * k, x * z * k, y * z * k
    wx, wy, wz = w * x * k, w * y * k, w * z * k
    return [
        [1.0 - yy - zz, xy + wz, xz - wy, 0.0],
        [xy - wz, 1.0 - xx - zz, yz + wx, 0.0],
        [xz + wy, yz - wx, 1.0 - xx - yy, 0.0],
        [t[0], t[1], t[2], 1.0],
    ]


def mat_mul(a, b):
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for k in range(4):
            out[i][k] = (
                a[i][0] * b[0][k] + a[i][1] * b[1][k]
                + a[i][2] * b[2][k] + a[i][3] * b[3][k]
            )
    return out


def load_ce_arms() -> list[dict]:
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import texconv
    from halo2ps2.scenconv import Region

    data = texconv.MapData.open(CE_MAP)
    region = Region(data)
    arms = next(
        e for e in data.index.entries
        if e.group == "mode" and e.path == r"characters\cyborg\fp\fp"
    )
    block = region.block(arms)
    count, offset = region.reflexive(block + 0xB8, 156, 256)
    nodes = []
    for i in range(count):
        rec = offset + i * 156
        name = region.cstr(rec, 32)
        _sib, _child, parent = struct.unpack_from("<3h", region.data, rec + 32)
        trans = struct.unpack_from("<3f", region.data, rec + 0x28)
        nodes.append({"name": name, "parent": parent, "t": list(trans)})
    return nodes


def decode(blob: bytes) -> dict:
    count = len(H2_NAMES)
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
    if [sum(m) for m in masks] != expected:
        raise RuntimeError(f"mask popcounts {[sum(m) for m in masks]} != {expected}")
    rot_stride = u32(blob, anim + 20)
    if rot_stride != FRAMES * 8 or blob[anim + 2] != 0:
        raise RuntimeError("idle is not 89 rotation-only animated frames")
    animated_end = anim + 32 + blob[anim + 1] * rot_stride
    if animated_end != masks_at:
        raise RuntimeError(f"animated data ends at {animated_end:#x}, masks at {masks_at:#x}")
    both = [H2_NAMES[n] for n in range(count) if masks[0][n] and masks[3][n]]
    if both:
        raise RuntimeError("static and animated rotation on " + ", ".join(both))
    scale = f32(blob, u32(blob, 16))
    if abs(scale - 1.0) > 1e-6:
        raise RuntimeError(f"static scale {scale} is not 1")
    return {
        "masks": masks,
        "static_trans_at": u32(blob, 12),
        "anim": anim,
        "rot_stride": rot_stride,
        "header_rate": f32(blob, anim + 8),
    }


def locals_at(blob: bytes, info: dict, ce: list[dict], frame: int):
    masks = info["masks"]
    local_q = []
    local_t = []
    override = []
    for n, name in enumerate(H2_NAMES):
        if n < 37:
            if ce[n]["name"] != ce_name(name):
                raise RuntimeError(f"node {n} is {ce[n]['name']}, expected {ce_name(name)}")
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
        override.append(trans >= 0)
        if trans >= 0:
            p = info["static_trans_at"] + trans * 12
            local_t[n] = [f32(blob, p), f32(blob, p + 4), f32(blob, p + 8)]
    return local_q, local_t, override


def compose(local_q, local_t, parents):
    world = [None] * len(parents)
    pending = set(range(len(parents)))
    while pending:
        ready = [n for n in pending if parents[n] < 0 or parents[n] not in pending]
        if not ready:
            raise RuntimeError("cycle in the sword skeleton")
        for n in ready:
            local = mat_from_trs(local_q[n], local_t[n])
            parent = parents[n]
            world[n] = local if parent < 0 else mat_mul(local, world[parent])
            pending.remove(n)
    return world


def battery_check(data: bytes) -> float:
    """Inverse Forward/Left/Up are the columns of the Hamilton matrix."""
    want = struct.pack("<f", -0.258819044)
    start = 0
    while True:
        at = data.find(want, start)
        if at < 4:
            break
        x, y, z, w = struct.unpack_from("<4f", data, at - 4)
        start = at + 1
        if abs(y + 0.258819044) > 1e-6 or abs(w + 0.9659258) > 1e-4:
            continue
        if abs(x) > 1e-4 or abs(z) > 1e-4:
            continue
        inv = [
            struct.unpack_from("<3f", data, at - 4 + 0x14),
            struct.unpack_from("<3f", data, at - 4 + 0x20),
            struct.unpack_from("<3f", data, at - 4 + 0x2C),
        ]
        m = mat_from_trs([x, y, z, w], [0.0, 0.0, 0.0])
        columns = (
            (m[0][0], m[1][0], m[2][0]),
            (m[0][1], m[1][1], m[2][1]),
            (m[0][2], m[1][2], m[2][2]),
        )
        err = max(abs(columns[i][k] - inv[i][k]) for i in range(3) for k in range(3))
        if err < 1e-5:
            return err
    raise RuntimeError("battery inverse-bind vectors do not match the Hamilton columns")


def main() -> None:
    data = MAP.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MAP_SHA:
        raise SystemExit(f"shared.map hash {digest} != {MAP_SHA}")
    blob = data[BLOB_OFF:BLOB_OFF + BLOB_SIZE]
    if len(blob) != BLOB_SIZE:
        raise SystemExit("sword idle blob is short")
    info = decode(blob)
    column_error = battery_check(data)
    ce = load_ce_arms()
    if len(ce) != 37:
        raise SystemExit(f"cyborg fp has {len(ce)} nodes")
    parents = [ce[i]["parent"] for i in range(37)] + [6, 37, 0]
    q0, t0, override = locals_at(blob, info, ce, 0)
    quats: list[float] = []
    nodes = []
    for n in range(37):
        animated = channel(info["masks"][3], n) >= 0
        q_at = len(quats) // 4
        count = FRAMES if animated else 1
        if animated:
            for frame in range(FRAMES):
                q, _t, _o = locals_at(blob, info, ce, frame)
                quats.extend(f32s(q[n]))
        else:
            quats.extend(f32s(q0[n]))
        nodes.append({
            "name": ce[n]["name"],
            "parent": parents[n],
            "override": 1 if override[n] else 0,
            "q_at": q_at,
            "q_n": count,
            "t": f32s(t0[n]),
        })
    handle_q = f32s(q0[37])
    handle_t = f32s(t0[37])
    oracle = []
    for frame in range(FRAMES):
        q, t, _o = locals_at(blob, info, ce, frame)
        world = compose(q, t, parents)
        if frame == 0:
            cam = world[39]
            if max(abs(cam[3][k]) for k in range(3)) > 1e-5:
                raise SystemExit(f"camera_control is not at the origin: {cam[3][:3]}")
        handle = world[37]
        oracle.append({
            "l_hand": f32s([world[5][3][0], world[5][3][1], world[5][3][2]]),
            "r_hand": f32s([world[6][3][0], world[6][3][1], world[6][3][2]]),
            "index_tip": f32s([world[32][3][0], world[32][3][1], world[32][3][2]]),
            "handle": f32s([handle[3][0], handle[3][1], handle[3][2]]),
            "handle_x": f32s([handle[0][0], handle[0][1], handle[0][2]]),
        })
    expect = (0.96604869, 0.20639936, 0.15540025)
    fwd = oracle[0]["handle_x"]
    if max(abs(fwd[k] - expect[k]) for k in range(3)) > 1e-5:
        raise SystemExit(f"frame 0 blade axis {fwd} != {expect}")
    hand = oracle[0]["r_hand"]
    hand_expect = (0.07349667, -0.15695362, -0.12469744)
    if max(abs(hand[k] - hand_expect[k]) for k in range(3)) > 1e-4:
        raise SystemExit(f"frame 0 right hand {hand} != {hand_expect}")
    move = max(math.dist(oracle[0]["r_hand"], oracle[f]["r_hand"]) for f in range(FRAMES))
    if move < 0.01:
        raise SystemExit("right hand does not move across the idle")
    write_header(quats, nodes, oracle, handle_q, handle_t, info["header_rate"], column_error, move)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "map_sha256": digest,
        "blob_offset": BLOB_OFF,
        "blob_size": BLOB_SIZE,
        "frames": FRAMES,
        "codec_header_float": info["header_rate"],
        "playback": "one frame per 30 Hz tick; the codec header float is not a frame rate",
        "fp_weapon_offset": "not applied; the exe placement function was not located",
        "quaternion": "tag samples as Hamilton; inverse bind vectors are Hamilton columns",
        "battery_column_error": column_error,
        "right_hand_travel_m": move,
        "oracle": oracle,
    }, indent=2) + "\n")
    print(
        f"wrote {OUT_H.name} ({OUT_H.stat().st_size} bytes), "
        f"hand travel {move:.3f} m, codec float {info['header_rate']:.4f}, "
        f"battery column error {column_error:.3e}"
    )


def write_header(quats, nodes, oracle, handle_q, handle_t, rate, column_error, move) -> None:
    lines = [
        "/* Generated by tools/extract_sword_idle.py. Do not edit by hand.",
        " * Halo 2 Vista shared.map SHA-256",
        f" * {MAP_SHA}.",
        " * jmad 0xEE9B3436 first_person:idle, 89 frames, file offset 0xBE4ECD0.",
        " * Local rotations are tag samples used as Hamilton quaternions (x, y, z, w).",
        " * Frame 0 of this idle aims the blade along +x, and a render-model node's",
        " * Inverse Forward/Left/Up vectors are the columns of that same matrix",
        f" * (battery column error {column_error:.3e}).",
        " * A translation is stored only where Halo 2 has a translation channel;",
        " * every other translation is the CE cyborg fp bind, which matches the",
        " * Halo 2 rest pose. The codec header float is "
        f"{rate:.6f}, not a frame rate.",
        " * Playback is one frame per 30 Hz tick. First Person Weapon Offset",
        " * (0.05, 0, 0) is not applied: the idle already places the handle in",
        " * camera space, and the exe placement function was not located.",
        f" * Right-hand travel across the loop: {move:.4f} m. */",
        "#ifndef GAME_SWORD_IDLE_H",
        "#define GAME_SWORD_IDLE_H",
        "#include <stdint.h>",
        "#include <string.h>",
        "#define PLAY_FP_SWORD_FRAMES 89",
        f"#define PLAY_FP_SWORD_NODES {len(nodes)}",
        "typedef struct {",
        "    const char *name;",
        "    int16_t parent;",
        "    uint8_t trans_override;",
        "    uint16_t q_at;",
        "    uint16_t q_n;",
        "    float t[3];",
        "} play_fp_sword_node;",
        "typedef struct {",
        "    float l_hand[3];",
        "    float r_hand[3];",
        "    float index_tip[3];",
        "    float handle[3];",
        "    float handle_x[3];",
        "} play_fp_sword_oracle;",
        "static const float PLAY_FP_SWORD_Q[] = {",
    ]
    for i in range(0, len(quats), 4):
        lines.append("    " + ", ".join(cfloat(c) for c in quats[i:i + 4]) + ",")
    lines.append("};")
    lines.append("static const play_fp_sword_node PLAY_FP_SWORD_NODE[PLAY_FP_SWORD_NODES] = {")
    for node in nodes:
        t = ", ".join(cfloat(c) for c in node["t"])
        lines.append(
            f'    {{ "{node["name"]}", {node["parent"]}, {node["override"]}, '
            f'{node["q_at"]}, {node["q_n"]}, {{ {t} }} }},'
        )
    lines.append("};")
    lines.append(
        "static const float PLAY_FP_SWORD_HANDLE_Q[4] = { "
        + ", ".join(cfloat(c) for c in handle_q) + " };"
    )
    lines.append(
        "static const float PLAY_FP_SWORD_HANDLE_T[3] = { "
        + ", ".join(cfloat(c) for c in handle_t) + " };"
    )
    lines.append("static const play_fp_sword_oracle PLAY_FP_SWORD_ORACLE[PLAY_FP_SWORD_FRAMES] = {")
    for frame in oracle:
        def vec(name: str) -> str:
            return ", ".join(cfloat(c) for c in frame[name])
        lines.append(
            "    {{" + vec("l_hand") + "}, {" + vec("r_hand") + "}, {"
            + vec("index_tip") + "}, {" + vec("handle") + "}, {" + vec("handle_x") + "}},"
        )
    lines += [
        "};",
        "static inline int play_fp_sword_find(const char *name)",
        "{",
        "    int i;",
        "    for (i = 0; i < PLAY_FP_SWORD_NODES; i++)",
        "        if (strcmp(PLAY_FP_SWORD_NODE[i].name, name) == 0) return i;",
        "    return -1;",
        "}",
        "static inline const float *play_fp_sword_node_quat(int node, int frame)",
        "{",
        "    const play_fp_sword_node *n = &PLAY_FP_SWORD_NODE[node];",
        "    unsigned f = n->q_n > 1 ? (unsigned)frame % PLAY_FP_SWORD_FRAMES : 0u;",
        "    return &PLAY_FP_SWORD_Q[(n->q_at + f) * 4];",
        "}",
        "#endif",
    ]
    OUT_H.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
