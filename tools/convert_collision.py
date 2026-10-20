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
# NUMBER_OF_MATERIAL_TYPES in pinned halo-ce-universal/source/game/game_globals.h.
CE_MATERIAL_TYPE_COUNT = 26

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
    """COLL payload: 9 counts, tables, 16-byte starts, runtime material types."""
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
    material_count, material_addr = struct.unpack_from("<II", block, root + 0xA4)
    material_off = material_addr - address
    if material_count > 256 or material_off < 0 or material_off + material_count * 20 > len(block):
        raise ValueError("BSP collision-material block is out of range")
    material_types = bytearray()
    for index in range(material_count):
        # structure_collision_material: tag_reference (16), pad (2),
        # runtime_physics_material_type (s16), per pinned CE structure header.
        material_type = struct.unpack_from("<h", block, material_off + index * 20 + 18)[0]
        # collision_structure_material_type returns NONE for invalid enum
        # values; preserve that lookup behavior in the converted table.
        if material_type < 0 or material_type >= CE_MATERIAL_TYPE_COUNT:
            material_type = -1
        material_types += struct.pack("<h", material_type)
    tags = _tags(data)
    payload = struct.pack("<9I", *counts) + b"".join(parts) + bytes(spawns)
    payload += struct.pack("<I", material_count) + bytes(material_types)
    return payload, tags


def location_payload(source: Path) -> bytes:
    """LOC1: CE BSP leaf/cluster/fog data needed for point media lookup.

    This intentionally follows scenario_location_from_point and
    scenario_location_underwater; collision material types are not a water
    proxy. Offsets/strides are pinned in halo-ce-universal's structure BSP,
    collision BSP, and fog definitions.
    """
    import math
    import struct as st

    data, raw, loc = _decompressed(source)
    block = raw[loc.file_offset:loc.file_offset + loc.size]
    address = loc.address
    root = st.unpack_from("<I", block, 0)[0] - address

    def table(offset: int, stride: int, name: str):
        count, pointer = st.unpack_from("<II", block, root + offset)
        start = pointer - address if count else 0
        if count > 1_000_000 or (count and (start < 0 or start + count * stride > len(block))):
            raise ValueError(f"structure BSP {name} block is out of range")
        return count, start

    leaf_count, leaf_start = table(0xE0, 0x10, "leaves")
    cluster_count, cluster_start = table(0x134, 0x68, "clusters")
    plane_count, plane_start = table(0x178, 0x20, "fog planes")
    region_count, region_start = table(0x184, 0x28, "fog regions")
    palette_count, palette_start = table(0x190, 0x88, "fog palette")
    if leaf_count > 32767 or cluster_count > 32767 or plane_count > 32767 or region_count > 32767:
        raise ValueError("structure BSP location table exceeds signed CE indices")

    leaves = []
    for i in range(leaf_count):
        cluster, = st.unpack_from("<h", block, leaf_start + i * 0x10 + 8)
        if cluster < -1 or cluster >= cluster_count:
            cluster = -1
        leaves.append(cluster)
    clusters = []
    for i in range(cluster_count):
        reference, = st.unpack_from("<h", block, cluster_start + i * 0x68 + 2)
        clusters.append(reference)

    regions = []
    for i in range(region_count):
        palette, = st.unpack_from("<h", block, region_start + i * 0x28 + 0x24)
        underwater, plane_distance = 0, 0.0
        if 0 <= palette < palette_count:
            reference = palette_start + palette * 0x88 + 0x20
            group = block[reference:reference + 4][::-1].decode("ascii", "replace")
            tag_id, = st.unpack_from("<I", block, reference + 12)
            fog = data.by_id.get(tag_id) if tag_id != 0xFFFFFFFF else None
            if group == "fog " and fog is not None and fog.group == "fog ":
                fog_base = fog.data_address - data.base
                flags, = st.unpack_from("<B", data.region, fog_base)
                plane_distance, = st.unpack_from("<f", data.region, fog_base + 0x74)
                if math.isfinite(plane_distance):
                    underwater = flags & 1
                else:
                    plane_distance = 0.0
        regions.append((underwater, plane_distance))

    planes = []
    for i in range(plane_count):
        at = plane_start + i * 0x20
        region, = st.unpack_from("<h", block, at)
        equation = st.unpack_from("<4f", block, at + 4)
        if (region < -1 or region >= region_count or
                not all(math.isfinite(value) for value in equation)):
            region, equation = -1, (0.0, 0.0, 0.0, 0.0)
        planes.append((region, *equation))

    # Every count and stride is explicit; location views point into this
    # immutable pack section and require no allocations on EE.
    payload = bytearray(st.pack("<4sHHIIII", b"LOC1", 1, 0,
                                leaf_count, cluster_count, plane_count, region_count))
    payload += st.pack("<" + "h" * leaf_count, *leaves)
    payload += st.pack("<" + "h" * cluster_count, *clusters)
    for plane in planes:
        payload += st.pack("<h4f", *plane)
    for underwater, plane_distance in regions:
        payload += st.pack("<B3xf", underwater, plane_distance)
    return bytes(payload)


def _tags(data) -> dict[str, float]:
    import math
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


def _cyborg_vitality(data) -> bytes:
    """Pack the player cyborg's collision-model damage_resistance records.

    Layout is pinned to halo-ce-universal's object_definitions.h,
    collision_model_definitions.h and damage_resistances.h. The play diagnostic
    uses the indirect damage material; all records are retained for future hit
    region resolution.
    """
    import math
    import struct as st

    region = data.region
    bipd = next((entry for entry in data.index.entries
                 if entry.group == "bipd" and entry.path == r"characters\cyborg_mp\cyborg_mp"), None)
    if bipd is None:
        raise ValueError("Blood Gulch map is missing the player cyborg biped")
    bipd_base = bipd.data_address - data.base
    collision_model_id = st.unpack_from("<I", region, bipd_base + 124)[0]
    collision_model = data.by_id.get(collision_model_id)
    if collision_model is None or collision_model.group != "coll":
        raise ValueError("player cyborg collision-model reference is missing or not coll")
    base = collision_model.data_address - data.base
    indirect_index = st.unpack_from("<h", region, base + 4)[0]
    maximum_body = st.unpack_from("<f", region, base + 8)[0]
    maximum_shield = st.unpack_from("<f", region, base + 204)[0]
    shield_material_type = st.unpack_from("<h", region, base + 210)[0]
    minimum_shield_stun = st.unpack_from("<f", region, base + 268)[0]
    shield_stun_seconds = st.unpack_from("<f", region, base + 272)[0]
    recharge_step = st.unpack_from("<f", region, base + 448)[0]
    material_count, material_address = st.unpack_from("<II", region, base + 564)
    region_count, region_address = st.unpack_from("<II", region, base + 0x240)
    material_base = material_address - data.base
    region_base = region_address - data.base
    if (material_count == 0 or material_count > 40 or indirect_index < 0 or
            indirect_index >= material_count or material_base < 0 or
            material_base + material_count * 0x48 > len(region) or
            region_count > 16 or (region_count and (region_base < 0 or
            region_base + region_count * 0x54 > len(region)))):
        raise ValueError("player cyborg damage_resistance materials are malformed")
    if shield_material_type < 0 or shield_material_type >= 26:
        shield_material_type = -1
    profile = (maximum_body, maximum_shield, minimum_shield_stun,
               shield_stun_seconds, recharge_step)
    if not all(math.isfinite(value) for value in profile) or maximum_body <= 0.0 or maximum_shield <= 0.0:
        raise ValueError("player cyborg damage_resistance profile has invalid values")
    records = bytearray()
    region_thresholds = []
    for index in range(region_count):
        threshold = st.unpack_from("<f", region, region_base + index * 0x54 + 0x28)[0]
        if not math.isfinite(threshold) or threshold < 0.0:
            raise ValueError(f"player cyborg damage region {index} has invalid threshold")
        region_thresholds.append(threshold)
    for index in range(material_count):
        item = material_base + index * 0x48
        material_type = st.unpack_from("<h", region, item + 0x24)[0]
        shield_leak, shield_multiplier = st.unpack_from("<2f", region, item + 0x28)
        body_multiplier = st.unpack_from("<f", region, item + 0x3C)[0]
        if material_type < 0 or material_type >= 26:
            material_type = -1
        if not all(math.isfinite(value) for value in (shield_leak, shield_multiplier, body_multiplier)):
            raise ValueError(f"player cyborg damage material {index} has invalid values")
        records += st.pack("<h3f", material_type, shield_leak, shield_multiplier, body_multiplier)
    # VIT1 v2: v1 profile fields, region count/reserved, source-ordered region
    # damage thresholds, then source-ordered damage-resistance materials.
    return (st.pack("<4sHHhh5fHH", b"VIT1", 2, material_count, indirect_index,
                    shield_material_type, *profile, region_count, 0) +
            st.pack("<" + "f" * region_count, *region_thresholds) + bytes(records))


def _cyborg_actor_collision(data) -> bytes:
    """Pack cyborg node-BSP triangles with CE damage indices and node metadata.

    ACOL v2 adds source-order model-node parent/default-pose records before
    the model-local triangles. These defaults are a bind-pose reference only;
    gameplay must use the animated node pose. Polygon rings follow
    collision_surface_polygon in halo-ce-universal.
    """
    import math
    import struct as st

    region = data.region
    coll = next((entry for entry in data.index.entries
                 if entry.group == "coll" and entry.path == r"characters\cyborg\cyborg"), None)
    if coll is None:
        raise ValueError("Blood Gulch map is missing the cyborg collision model")
    base = coll.data_address - data.base
    node_count, node_address = st.unpack_from("<II", region, base + 0x28C)
    if node_count == 0 or node_count > 256:
        raise ValueError("cyborg collision-model node count is invalid")
    node_base = node_address - data.base
    if node_base < 0 or node_base + node_count * 0x40 > len(region):
        raise ValueError("cyborg collision-model node block is out of range")

    # model_node in halo-ce-universal: 32-byte name, sibling/child/parent
    # indices and pad (8), translation (12), quaternion (16), distance (4),
    # unused[8] (32), runtime inverse matrix (52): 156 bytes total.
    bipd = next((entry for entry in data.index.entries
                 if entry.group == "bipd" and entry.path == r"characters\cyborg_mp\cyborg_mp"), None)
    if bipd is None:
        raise ValueError("Blood Gulch map is missing the player cyborg biped")
    bipd_base = bipd.data_address - data.base
    model_id, = st.unpack_from("<I", region, bipd_base + 52)
    model = data.by_id.get(model_id)
    if model is None or model.group != "mode":
        raise ValueError("player cyborg model reference is missing or not mode")
    model_base = model.data_address - data.base
    model_node_count, model_node_address = st.unpack_from("<II", region, model_base + 184)
    model_node_base = model_node_address - data.base
    if (model_node_count != node_count or model_node_base < 0 or
            model_node_base + model_node_count * 156 > len(region)):
        raise ValueError("player cyborg model and collision node tables do not align")
    node_records = bytearray()
    for node_index in range(node_count):
        model_node = model_node_base + node_index * 156
        coll_name = bytes(region[node_base + node_index * 0x40:
                                 node_base + node_index * 0x40 + 32]).split(b"\0", 1)[0]
        model_name = bytes(region[model_node:model_node + 32]).split(b"\0", 1)[0]
        if coll_name != model_name:
            raise ValueError(f"cyborg model/collision node {node_index} names do not align")
        parent, = st.unpack_from("<h", region, model_node + 36)
        translation = st.unpack_from("<3f", region, model_node + 40)
        rotation = st.unpack_from("<4f", region, model_node + 52)
        distance, = st.unpack_from("<f", region, model_node + 68)
        if parent < -1 or parent >= node_count or parent == node_index:
            raise ValueError(f"cyborg model node {node_index} has an invalid parent")
        if not all(math.isfinite(v) for v in (*translation, *rotation, distance)):
            raise ValueError(f"cyborg model node {node_index} has non-finite defaults")
        node_records += st.pack("<hh8f", node_index, parent, *translation, *rotation, distance)

    triangles = bytearray()
    triangle_count = 0
    for node_index in range(node_count):
        node = node_base + node_index * 0x40
        region_index, = st.unpack_from("<h", region, node + 32)
        runtime_damage_part, = st.unpack_from("<h", region, node + 50)
        bsp_count, bsp_address = st.unpack_from("<II", region, node + 52)
        if bsp_count > 32:
            raise ValueError(f"cyborg node {node_index} has too many BSPs")
        bsp_base = bsp_address - data.base if bsp_count else 0
        if bsp_count and (bsp_base < 0 or bsp_base + bsp_count * 96 > len(region)):
            raise ValueError(f"cyborg node {node_index} BSP block is out of range")
        for bsp_index in range(bsp_count):
            bsp = bsp_base + bsp_index * 96
            counts, addresses = [], []
            for block_index in range(8):
                count, address = st.unpack_from("<II", region, bsp + block_index * 12)
                offset = address - data.base if count else 0
                stride = (12, 16, 8, 8, 20, 12, 24, 16)[block_index]
                if count > 131072 or (count and (offset < 0 or offset + count * stride > len(region))):
                    raise ValueError(f"cyborg node {node_index} BSP block {block_index} is invalid")
                counts.append(count)
                addresses.append(offset)
            surface_count, edge_count, vertex_count = counts[5], counts[6], counts[7]
            for surface_index in range(surface_count):
                surface = addresses[5] + surface_index * 12
                first_edge, = st.unpack_from("<i", region, surface + 4)
                resistance_index, = st.unpack_from("<h", region, surface + 10)
                edge_index = first_edge
                points = []
                for edge_step in range(8):
                    if edge_index < 0 or edge_index >= edge_count:
                        raise ValueError(f"cyborg node {node_index} surface {surface_index} edge ring is invalid")
                    edge = addresses[6] + edge_index * 24
                    vertices = st.unpack_from("<2i", region, edge)
                    edge_indices = st.unpack_from("<2i", region, edge + 8)
                    surface_indices = st.unpack_from("<2i", region, edge + 16)
                    reverse = surface_indices[1] == surface_index
                    vertex_index = vertices[int(reverse)]
                    if vertex_index < 0 or vertex_index >= vertex_count:
                        raise ValueError(f"cyborg node {node_index} surface {surface_index} vertex is invalid")
                    vertex = addresses[7] + vertex_index * 16
                    points.append(st.unpack_from("<3f", region, vertex))
                    next_edge = edge_indices[int(reverse)]
                    if next_edge == first_edge:
                        break
                    edge_index = next_edge
                else:
                    raise ValueError(f"cyborg node {node_index} surface {surface_index} ring exceeds CE maximum")
                if len(points) < 3:
                    raise ValueError(f"cyborg node {node_index} surface {surface_index} has fewer than 3 points")
                for point in range(1, len(points) - 1):
                    vertices = (*points[0], *points[point], *points[point + 1])
                    triangles += st.pack("<5h9f", node_index, region_index,
                        runtime_damage_part, resistance_index, surface_index, *vertices)
                    triangle_count += 1
    # ACOL v2 header: magic, version, node count, triangle count, node stride.
    return st.pack("<4sHHII", b"ACL1", 2, node_count, triangle_count, 36) + node_records + triangles


def tags_payload(tags: dict[str, float]) -> bytes:
    return struct.pack("<I", len(TAG_NAMES)) + struct.pack("<" + "f" * len(TAG_NAMES), *(tags[name] for name in TAG_NAMES))


def build_pack(source: Path) -> bytes:
    from halo2ps2.hp2 import build
    payload, tags = collision_payload(source)
    data, _raw, _loc = _decompressed(source)
    return build("bloodgulch", [("COLL", payload), ("TAGS", tags_payload(tags)),
                                 ("LOC1", location_payload(source)),
                                 ("VITA", _cyborg_vitality(data)),
                                 ("ACOL", _cyborg_actor_collision(data))], compress=False)


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
