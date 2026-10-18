"""Convert one BSP's collision tables and the player-start list into an HP2 section.

The bytes are the gameplay adapter: collision queries read this pack, not the
Xbox map. Output stays under data/retail or build. The existing BSP, object,
and texture packs are not rewritten.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules" / "halo-ps2" / "tools"))

# physics.c global_gravity. It is not a tag field.
GRAVITY = 0.0035651792

# Order of the TAGS float block. move.h and pad.c cite the same fields.
TAG_NAMES = (
    "run_forward", "run_backward", "run_sideways", "run_acceleration",
    "sneak_forward", "sneak_backward", "sneak_sideways", "sneak_acceleration",
    "airborne_acceleration", "jump_velocity",
    "stand_camera", "crouch_camera", "stand_height", "crouch_height", "radius",
    "minimum_normal_k", "crouch_step",
    "downhill_k0", "downhill_k1", "downhill_scale",
    "uphill_k0", "uphill_k1", "uphill_scale",
    "gravity",
)


def _decompressed(source: Path):
    from halo2ps2 import texconv
    from halo2ps2.bsp import locate

    data = texconv.MapData.open(source)
    raw = source.read_bytes()
    return data, raw, locate(data.index, data.region, len(raw))[0]


def collision_payload(source: Path) -> tuple[bytes, dict[str, float]]:
    """COLL payload: 9 counts, tables, then 16-byte starts (x, y, z, yaw)."""
    data, raw, loc = _decompressed(source)
    block = raw[loc.file_offset:loc.file_offset + loc.size]
    address = loc.address
    root = struct.unpack_from("<I", block, 0)[0] - address
    base = struct.unpack_from("<II", block, root + 0xB0)[1] - address
    refs = []
    for index in range(8):
        count, addr = struct.unpack_from("<II", block, base + 12 * index)
        refs.append((count, addr - address))
    order = (1, 0, 2, 3, 4, 5, 6, 7)
    strides = (16, 12, 8, 8, 20, 12, 24, 16)
    parts = []
    counts = []
    for index, stride in zip(order, strides):
        count, off = refs[index]
        counts.append(count)
        parts.append(block[off:off + count * stride])
    scenario = data.index.scenario.data_address - data.base
    spawn_count, spawn_addr = struct.unpack_from("<II", data.region, scenario + 0x354)
    spawn_off = spawn_addr - data.base
    spawns = bytearray()
    for index in range(spawn_count):
        spawns += data.region[spawn_off + index * 52:spawn_off + index * 52 + 16]
    counts.append(spawn_count)
    tags = _tags(data)
    return struct.pack("<9I", *counts) + b"".join(parts) + bytes(spawns), tags


def _tags(data) -> dict[str, float]:
    import struct as st
    entry = next(item for item in data.index.entries if item.group == "matg")
    region = data.region
    base = entry.data_address - data.base
    count, addr = st.unpack_from("<II", region, base + 0x170)
    if count < 1:
        raise RuntimeError("globals tag has no player information")
    player = addr - data.base
    speeds = st.unpack_from("<11f", region, player + 16 + 28)
    cyborg = next(item for item in data.index.entries if item.path == r"characters\cyborg_mp\cyborg_mp")
    body = region[cyborg.data_address - data.base:]
    camera = st.unpack_from("<3f", body, 0x400)
    heights = st.unpack_from("<3f", body, 0x400 + 9 * 4)
    runtime = st.unpack_from("<7f", body, 0x400 + 50 * 4)
    slope = st.unpack_from("<7f", body, 0x3B4 - 23 * 4)
    values = {
        "run_forward": speeds[2], "run_backward": speeds[3], "run_sideways": speeds[4],
        "run_acceleration": speeds[5], "sneak_forward": speeds[6], "sneak_backward": speeds[7],
        "sneak_sideways": speeds[8], "sneak_acceleration": speeds[9],
        "airborne_acceleration": speeds[10], "jump_velocity": st.unpack_from("<f", body, 0x3B4)[0],
        "stand_camera": camera[0], "crouch_camera": camera[1],
        "stand_height": heights[0], "crouch_height": heights[1], "radius": heights[2],
        "minimum_normal_k": runtime[2], "crouch_step": runtime[1],
        "downhill_k0": runtime[3], "downhill_k1": runtime[4], "downhill_scale": slope[3],
        "uphill_k0": runtime[5], "uphill_k1": runtime[6], "uphill_scale": slope[6],
        "gravity": GRAVITY,
    }
    return {name: values[name] for name in TAG_NAMES}


def tags_payload(tags: dict[str, float]) -> bytes:
    return struct.pack("<I", len(TAG_NAMES)) + struct.pack("<" + "f" * len(TAG_NAMES), *(tags[name] for name in TAG_NAMES))


def build_pack(source: Path) -> bytes:
    from halo2ps2.hp2 import build
    payload, tags = collision_payload(source)
    return build("bloodgulch", [("COLL", payload), ("TAGS", tags_payload(tags))], compress=False)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", type=Path, required=True)
    args = parser.parse_args()
    output = args.o.resolve()
    if "retail" not in output.parts and "build" not in output.parts:
        raise SystemExit("collision pack must stay under data/retail or build")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_pack(args.source))
    print(output)


if __name__ == "__main__":
    main()
