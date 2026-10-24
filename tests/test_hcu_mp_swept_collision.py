"""CE pill and sphere queries against one raw Blood Gulch collision BSP.

The oracle is computed from the decompressed Xbox BSP bytes before CE runs.
CE collision_bsp_test_pill and collision_bsp_test_sphere are the compiled
source, not a reimplementation. A synthetic square floor, the same geometry
as tests/m3_ce_collision_synthetic_main.c, is the reference control.
"""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MAP_NAME = "bloodgulch"
MAP_SHA256 = "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1"
PACKAGE_SHA256 = "ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011"
PACKAGE = Path("/tmp/hcu-m2-capacity-repro.P5qdmI/packages/bloodgulch.hp2")
OUT = ROOT / "build/step7-swarm/swept"
RADIUS = np.float32(0.25)
PILL_EPSILON = np.float32(1.0 / 4096.0)
STRIDES = (12, 16, 8, 8, 20, 12, 24, 16)
MAPPINGS = (((2, 1), (1, 2)), ((0, 2), (2, 0)), ((1, 0), (0, 1)))

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402
from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bits(value):
    return struct.unpack("<I", np.float32(value).tobytes())[0]


def _f32(value):
    return np.float32(value)


def _load_collision(map_path):
    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp_tools.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError("Blood Gulch must contain one raw BSP")
    location = locations[0]
    with Path(map_path).open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    if len(image) != location.size:
        raise AssertionError("truncated raw BSP image")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 0xB0 + 8 > len(image):
        raise AssertionError("raw BSP root leaves the image")

    def block(base, offset):
        count, address = struct.unpack_from("<II", image, base + offset)
        data = address - location.address if address else 0
        if count < 0:
            raise AssertionError("negative collision block count")
        return count, data

    material_count, material_offset = block(root, 0xA4)
    collision_count, collision_offset = block(root, 0xB0)
    if collision_count != 1:
        raise AssertionError("expected one collision BSP")
    if material_count < 0 or material_offset < 0:
        raise AssertionError("invalid collision material block")
    if material_count and material_offset + material_count * 20 > len(image):
        raise AssertionError("collision materials leave the BSP image")
    counts = []
    offsets = []
    for field, stride in zip((0x00, 0x0C, 0x18, 0x24, 0x30, 0x3C, 0x48, 0x54),
                             STRIDES):
        count, data = block(collision_offset, field)
        if count and (data < 0 or data + count * stride > len(image)):
            raise AssertionError("collision array leaves the BSP image")
        counts.append(count)
        offsets.append(data)
    node_count, plane_count, leaf_count, ref_count, bsp2d_count, surface_count, edge_count, vertex_count = counts
    planes = np.ndarray((plane_count, 4), np.float32, image, offsets[1]).copy()
    vertices = np.ndarray((vertex_count,), np.dtype([("p", "<f4", 3), ("e", "<i4")]),
                          image, offsets[7])["p"].copy()
    nodes = np.ndarray((node_count, 3), np.uint32, image, offsets[0]).copy()
    leaves = np.ndarray((leaf_count,), np.dtype([
        ("flags", "<u2"), ("count", "<i2"), ("first", "<i4")]), image, offsets[2]).copy()
    refs = np.ndarray((ref_count, 2), np.uint32, image, offsets[3]).copy()
    bsp2d = np.ndarray((bsp2d_count,), np.dtype([
        ("n", "<f4", 2), ("d", "<f4"), ("c", "<u4", 2)]), image, offsets[4]).copy()
    surfaces = np.ndarray((surface_count,), np.dtype([
        ("des", "<i4"), ("first", "<i4"), ("flags", "u1"), ("brk", "u1"),
        ("mat", "<i2")]), image, offsets[5]).copy()
    edges = np.ndarray((edge_count, 6), np.int32, image, offsets[6]).copy()
    types = [struct.unpack_from("<h", image, material_offset + index * 20 + 18)[0]
             for index in range(material_count)]
    payload = b"".join(image[offset:offset + count * stride]
                       for count, offset, stride in zip(counts, offsets, STRIDES))
    return {
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "counts": counts,
        "planes": planes,
        "vertices": vertices,
        "nodes": nodes,
        "leaves": leaves,
        "refs": refs,
        "bsp2d": bsp2d,
        "surfaces": surfaces,
        "edges": edges,
        "material_types": types,
        "max_z": _f32(vertices[:, 2].max()) if vertex_count else _f32(0),
    }


def _decode_surface(raw, surface_index):
    surfaces = raw["surfaces"]
    edges = raw["edges"]
    vertices = raw["vertices"]
    designator = int(surfaces[surface_index]["des"])
    first = int(surfaces[surface_index]["first"])
    flags = int(surfaces[surface_index]["flags"])
    material = int(surfaces[surface_index]["mat"])
    edge_index = first
    seen = set()
    polygon = []
    edge_count = len(edges)
    vertex_count = len(vertices)
    for _ in range(9):
        if edge_index in seen or not 0 <= edge_index < edge_count:
            return None
        seen.add(edge_index)
        vertex0, vertex1, edge0, edge1, surface0, surface1 = (
            int(value) for value in edges[edge_index])
        reverse = int(surface1 == surface_index)
        if (surface0, surface1)[reverse] != surface_index:
            return None
        vertex_index = (vertex0, vertex1)[reverse]
        if not 0 <= vertex_index < vertex_count:
            return None
        polygon.append(vertices[vertex_index].astype(np.float64))
        edge_index = (edge0, edge1)[reverse]
        if edge_index == first:
            break
    if len(polygon) < 3 or edge_index != first:
        return None
    plane_index = designator & 0x7FFFFFFF
    if not 0 <= plane_index < len(raw["planes"]):
        return None
    return designator, flags, material, plane_index, polygon


def _oriented_plane(raw, designator):
    plane = raw["planes"][designator & 0x7FFFFFFF]
    if designator & 0x80000000:
        return (-plane).astype(np.float32)
    return plane.copy()


def _plane_distance(plane, point):
    return _f32(_f32(plane[0]) * _f32(point[0]) +
                _f32(plane[1]) * _f32(point[1]) +
                _f32(plane[2]) * _f32(point[2]) - _f32(plane[3]))


def _edge_inset(polygon, point, normal):
    axis = int(np.argmax(np.abs(normal)))
    keep = [index for index in range(3) if index != axis]
    sign = 0
    inset = 1e9
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        cross = ((end[keep[0]] - start[keep[0]]) * (point[keep[1]] - start[keep[1]]) -
                 (end[keep[1]] - start[keep[1]]) * (point[keep[0]] - start[keep[0]]))
        if abs(cross) <= 1e-4:
            return -1.0
        current = 1 if cross > 0.0 else -1
        if sign and current != sign:
            return -1.0
        sign = current
        span = end - start
        length_squared = float(np.dot(span, span))
        if length_squared <= 1e-12:
            return -1.0
        parameter = min(1.0, max(0.0, float(np.dot(point - start, span) / length_squared)))
        closest = start + span * parameter
        inset = min(inset, float(np.linalg.norm(point - closest)))
    return inset


def _polygon_distance(point, polygon, plane):
    distance = float(np.dot(plane[:3], point) - plane[3])
    projected = point - plane[:3] * distance
    if _edge_inset(polygon, projected, plane[:3]) >= 0.0:
        return abs(distance)
    best = 1e9
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        span = end - start
        length_squared = float(np.dot(span, span)) or 1.0
        parameter = min(1.0, max(0.0, float(np.dot(point - start, span) / length_squared)))
        best = min(best, float(np.linalg.norm(point - (start + span * parameter))))
    return best


def _aabb_lower(point, polygon):
    stacked = np.stack(polygon)
    low = stacked.min(axis=0)
    high = stacked.max(axis=0)
    delta = np.maximum(np.maximum(low - point, point - high), 0.0)
    return float(np.linalg.norm(delta))


def _projection_axes(plane, designator):
    absolute = np.abs(plane[:3].astype(np.float64))
    if absolute[2] >= absolute[1] and absolute[2] >= absolute[0]:
        axis = 2
    elif absolute[1] >= absolute[0]:
        axis = 1
    else:
        axis = 0
    sign = (float(plane[axis]) > 0.0) != bool(designator & 0x80000000)
    return MAPPINGS[axis][int(sign)]


def _bsp2d_surface(raw, root, point2d):
    node = int(root)
    depth = 0
    nodes = raw["bsp2d"]
    while not (node & 0x80000000):
        if node >= len(nodes) or depth >= 128:
            return None
        depth += 1
        normal = nodes[node]["n"]
        distance = _f32(_f32(normal[0]) * _f32(point2d[0]) +
                        _f32(normal[1]) * _f32(point2d[1]) - _f32(nodes[node]["d"]))
        child0, child1 = (int(value) for value in nodes[node]["c"])
        node = child1 if float(distance) >= 0.0 else child0
    if node == 0xFFFFFFFF:
        return None
    return node & 0x7FFFFFFF


def _leaf_surface(raw, leaf_index, stack, point):
    """First stack-matched BSP2D reference, as collision_bsp.c tests a leaf."""
    leaf = raw["leaves"][leaf_index]
    count = int(leaf["count"])
    first = int(leaf["first"])
    if count <= 0 or first < 0 or first + count > len(raw["refs"]):
        return None, None
    stacked = {int(value) for value in stack}
    for reference_index in range(first, first + count):
        designator = int(raw["refs"][reference_index, 0])
        if designator not in stacked:
            continue
        plane = raw["planes"][designator & 0x7FFFFFFF]
        distance = _plane_distance(plane, point)
        shift = _f32(-distance)
        projected = np.array([
            _f32(_f32(point[axis]) + _f32(plane[axis]) * shift) for axis in range(3)
        ], dtype=np.float32)
        axes = _projection_axes(plane, designator)
        surface = _bsp2d_surface(
            raw, int(raw["refs"][reference_index, 1]),
            (projected[axes[0]], projected[axes[1]]))
        return surface, designator
    return None, None


def _enter(raw, node_index, depth, remaining):
    if 0 <= node_index < len(raw["nodes"]) and depth < 128 and remaining[0] > 0:
        remaining[0] -= 1
        return True
    return False


def _sphere_selection(raw, point, radius, wanted):
    remaining = [len(raw["nodes"])]
    found = []

    def walk(node_index, depth, stack):
        node_index = int(node_index)
        while not (node_index & 0x80000000):
            if not _enter(raw, node_index, depth, remaining):
                return
            depth += 1
            designator, child0, child1 = (int(value) for value in raw["nodes"][node_index])
            distance = float(_plane_distance(
                raw["planes"][designator & 0x7FFFFFFF], point))
            if distance > -float(radius) and distance < float(radius):
                stack.append(designator | 0x80000000)
                walk(child0, depth, stack)
                stack.pop()
                stack.append(designator & 0x7FFFFFFF)
                walk(child1, depth, stack)
                stack.pop()
                return
            node_index = child1 if distance > -float(radius) else child0
        if node_index != 0xFFFFFFFF:
            leaf_index = node_index & 0x7FFFFFFF
            if 0 <= leaf_index < len(raw["leaves"]):
                surface, designator = _leaf_surface(raw, leaf_index, stack, point)
                if surface == wanted:
                    found.append((leaf_index, designator))

    walk(0, 0, [])
    return found


def _pill_selection(raw, point, vector, radius, wanted):
    remaining = [len(raw["nodes"])]
    found = []

    def walk(node_index, depth, stack):
        node_index = int(node_index)
        if not (node_index & 0x80000000) and _enter(raw, node_index, depth, remaining):
            designator, child0, child1 = (int(value) for value in raw["nodes"][node_index])
            plane = raw["planes"][designator & 0x7FFFFFFF]
            distance0 = _plane_distance(plane, point)
            dot = _f32(_f32(plane[0]) * _f32(vector[0]) +
                       _f32(plane[1]) * _f32(vector[1]) +
                       _f32(plane[2]) * _f32(vector[2]))
            distance1 = _f32(dot + distance0)
            limit = float(radius) + float(PILL_EPSILON)
            reaches_back = float(distance0) <= limit or float(distance1) <= limit
            reaches_front = float(distance0) >= -limit or float(distance1) >= -limit
            if reaches_back and reaches_front:
                front = float(dot) > 0.0
                stack.append((designator | 0x80000000) if front else (designator & 0x7FFFFFFF))
                walk(child0 if front else child1, depth + 1, stack)
                stack.pop()
                walk(child1 if front else child0, depth + 1, stack)
            else:
                walk(child1 if reaches_front else child0, depth + 1, stack)
        elif (node_index & 0x80000000) and node_index != 0xFFFFFFFF:
            leaf_index = node_index & 0x7FFFFFFF
            if 0 <= leaf_index < len(raw["leaves"]):
                surface, designator = _leaf_surface(raw, leaf_index, stack, point)
                if surface == wanted:
                    found.append((leaf_index, designator))

    walk(0, 0, [])
    return found


def _reachable_leaves(raw, point, radius, vector):
    """Leaves a radius-expanded BSP3D walk enters. Independent of CE memory."""
    reached = set()

    def consider(node_index):
        node_index = int(node_index)
        if (node_index & 0x80000000) and node_index != 0xFFFFFFFF:
            leaf_index = node_index & 0x7FFFFFFF
            if 0 <= leaf_index < len(raw["leaves"]):
                reached.add(leaf_index)

    remaining = [len(raw["nodes"])]

    def sphere_walk(node_index, depth):
        node_index = int(node_index)
        while not (node_index & 0x80000000):
            if not _enter(raw, node_index, depth, remaining):
                return
            depth += 1
            designator, child0, child1 = (int(value) for value in raw["nodes"][node_index])
            distance = float(_plane_distance(
                raw["planes"][designator & 0x7FFFFFFF], point))
            if distance > -float(radius) and distance < float(radius):
                sphere_walk(child0, depth)
                sphere_walk(child1, depth)
                return
            node_index = child1 if distance > -float(radius) else child0
        consider(node_index)

    sphere_walk(0, 0)
    remaining[0] = len(raw["nodes"])

    def pill_walk(node_index, depth):
        node_index = int(node_index)
        if not (node_index & 0x80000000) and _enter(raw, node_index, depth, remaining):
            designator, child0, child1 = (int(value) for value in raw["nodes"][node_index])
            plane = raw["planes"][designator & 0x7FFFFFFF]
            distance0 = _plane_distance(plane, point)
            dot = _f32(_f32(plane[0]) * _f32(vector[0]) +
                       _f32(plane[1]) * _f32(vector[1]) +
                       _f32(plane[2]) * _f32(vector[2]))
            distance1 = _f32(dot + distance0)
            limit = float(radius) + float(PILL_EPSILON)
            reaches_back = float(distance0) <= limit or float(distance1) <= limit
            reaches_front = float(distance0) >= -limit or float(distance1) >= -limit
            if reaches_back and reaches_front:
                front = float(dot) > 0.0
                pill_walk(child0 if front else child1, depth + 1)
                pill_walk(child1 if front else child0, depth + 1)
            else:
                pill_walk(child1 if reaches_front else child0, depth + 1)
        else:
            consider(node_index)

    pill_walk(0, 0)
    return sorted(reached)


def _minimum_other_distance(raw, decoded, surface_index, point):
    best = 1e9
    for other_index, other in enumerate(decoded):
        if other_index == surface_index or other is None:
            continue
        polygon = other[4]
        if _aabb_lower(point, polygon) > 0.50:
            best = min(best, _aabb_lower(point, polygon))
            continue
        designator, _flags, _material, plane_index, polygon = other
        plane = _oriented_plane(raw, designator).astype(np.float64)
        best = min(best, _polygon_distance(point, polygon, plane))
    return best


def _unpinned_pill_t(plane, point, vector, radius):
    distance0 = _plane_distance(plane, point)
    dot = _f32(_f32(plane[0]) * _f32(vector[0]) +
               _f32(plane[1]) * _f32(vector[1]) +
               _f32(plane[2]) * _f32(vector[2]))
    if float(dot) == 0.0:
        return 0.0
    inverse = _f32(1.0 / float(dot))
    return float(_f32(-(_f32(inverse) * distance0) - _f32(abs(float(inverse))) * radius))


def retail_swept_oracle(map_path):
    raw = _load_collision(map_path)
    if raw["counts"][5] == 0:
        return {"empty": True, "raw": raw}
    decoded = [_decode_surface(raw, index) for index in range(raw["counts"][5])]
    material_count = len(raw["material_types"])
    for surface_index, decoded_surface in enumerate(decoded):
        if decoded_surface is None:
            continue
        designator, flags, material, plane_index, polygon = decoded_surface
        if flags != 0 or not 0 <= material < material_count:
            continue
        plane = raw["planes"][plane_index]
        oriented = _oriented_plane(raw, designator).astype(np.float64)
        magnitude = float(np.linalg.norm(oriented[:3]))
        if not 0.98 < magnitude < 1.02 or float(oriented[2]) < 0.95:
            continue
        centroid = sum(polygon) / len(polygon)
        centroid_error = float(np.dot(oriented[:3], centroid) - oriented[3])
        if abs(centroid_error) > 0.005:
            continue
        projected = centroid - oriented[:3] * centroid_error
        if _edge_inset(polygon, projected, oriented[:3]) < 0.80:
            continue
        center = (projected.astype(np.float32) +
                  _oriented_plane(raw, designator)[:3] * _f32(0.10))
        center = np.array(center, dtype=np.float32)
        vector = (-_oriented_plane(raw, designator)[:3]).astype(np.float32)
        oriented_distance = float(_plane_distance(_oriented_plane(raw, designator), center))
        stored_distance = float(_plane_distance(plane, center))
        if not 0.05 < oriented_distance < float(RADIUS):
            continue
        if abs(stored_distance) >= float(RADIUS):
            continue
        center64 = center.astype(np.float64)
        center_projection = center64 - oriented[:3] * oriented_distance
        inset = _edge_inset(polygon, center_projection, oriented[:3])
        if inset < float(RADIUS) + 0.20:
            continue
        if _unpinned_pill_t(plane, center, vector, RADIUS) >= -0.01:
            continue
        sphere_hits = _sphere_selection(raw, center, RADIUS, surface_index)
        pill_hits = _pill_selection(raw, center, vector, RADIUS, surface_index)
        if not sphere_hits or not pill_hits:
            continue
        if sphere_hits[0][0] != pill_hits[0][0]:
            continue
        surface_bits = designator & 0xFFFFFFFF
        if ((sphere_hits[0][1] & 0xFFFFFFFF) != surface_bits or
                (pill_hits[0][1] & 0xFFFFFFFF) != surface_bits):
            continue
        other = _minimum_other_distance(raw, decoded, surface_index, center64)
        if other <= float(RADIUS) + 0.20:
            continue
        miss = np.array([center[0], center[1],
                         _f32(raw["max_z"] + RADIUS + _f32(2.0))], dtype=np.float32)
        clearance = float(miss[2]) - float(raw["max_z"])
        if clearance <= float(RADIUS) + 1.0:
            raise AssertionError("open-air point is not above every collision vertex")
        miss_vector = np.array([_f32(0.5), _f32(0.0), _f32(0.0)], dtype=np.float32)
        reached = _reachable_leaves(raw, miss, RADIUS, miss_vector)
        if designator & 0x80000000:
            plane_words = struct.unpack("<4I", plane.tobytes())
            plane_bytes = struct.pack("<4I", *(word ^ 0x80000000 for word in plane_words))
        else:
            plane_bytes = plane.tobytes()
        return {
            "empty": False,
            "raw": raw,
            "surface": surface_index,
            "material": material,
            "material_type": raw["material_types"][material],
            "leaf": sphere_hits[0][0],
            "designator": surface_bits - 0x100000000 if surface_bits & 0x80000000 else surface_bits,
            "center": center,
            "vector": vector,
            "miss": miss,
            "miss_vector": miss_vector,
            "plane_bytes": plane_bytes,
            "oriented_distance": oriented_distance,
            "inset": inset,
            "other_distance": other,
            "clearance": clearance,
            "reachable_leaves": reached,
            "surface_count": raw["counts"][5],
            "decoded_surfaces": sum(row is not None for row in decoded),
        }
    raise AssertionError("raw Blood Gulch BSP has no clearly isolated floor query")


def _write_oracle_header(path, oracle):
    counts = ", ".join(f"{count}u" for count in oracle["raw"]["counts"])
    def words(values):
        return ", ".join(f"0x{_bits(value):08x}u" for value in values)
    plane_words = struct.unpack("<4I", oracle["plane_bytes"])
    plane = ", ".join(f"0x{word:08x}u" for word in plane_words)
    path.write_text(
        "/* Generated from raw Blood Gulch collision bytes. Do not edit. */\n"
        "#ifndef HCU_SWEPT_ORACLE_H\n"
        "#define HCU_SWEPT_ORACLE_H\n"
        f"#define HCU_SWEPT_SURFACE {oracle['surface']}\n"
        f"#define HCU_SWEPT_MATERIAL {oracle['material']}\n"
        f"#define HCU_SWEPT_LEAF {oracle['leaf']}\n"
        f"#define HCU_SWEPT_PLANE_DESIGNATOR {oracle['designator']}\n"
        f"#define HCU_SWEPT_RADIUS_BITS 0x{_bits(RADIUS):08x}u\n"
        f"static unsigned const hcu_swept_counts[8] = {{{counts}}};\n"
        f"static unsigned const hcu_swept_hit_point[3] = {{{words(oracle['center'])}}};\n"
        f"static unsigned const hcu_swept_hit_vector[3] = {{{words(oracle['vector'])}}};\n"
        f"static unsigned const hcu_swept_miss_point[3] = {{{words(oracle['miss'])}}};\n"
        f"static unsigned const hcu_swept_miss_vector[3] = {{{words(oracle['miss_vector'])}}};\n"
        f"static unsigned const hcu_swept_plane[4] = {{{plane}}};\n"
        "#endif\n")


def _write_blob(path, payload, counts):
    header = b"SWP1" + struct.pack("<8I", *counts)
    path.write_bytes(header + payload)


class HcuMpSweptCollision(unittest.TestCase):
    def test_bloodgulch_pill_and_sphere_match_raw_floor_oracle(self):
        compiler = shutil.which("gcc")
        if not compiler:
            self.fail("GCC is unavailable for the ILP32 CE collision fixture")
        map_path = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
        self.assertEqual(_sha256(map_path), MAP_SHA256)
        self.assertTrue(PACKAGE.is_file(), "pinned Blood Gulch package is missing")
        self.assertEqual(_sha256(PACKAGE), PACKAGE_SHA256)
        oracle = retail_swept_oracle(map_path)
        self.assertFalse(oracle["empty"])
        with self.subTest("raw hit geometry"):
            self.assertGreater(oracle["oriented_distance"], 0.05)
            self.assertLess(oracle["oriented_distance"], float(RADIUS))
            self.assertGreater(oracle["inset"], float(RADIUS))
            self.assertGreater(oracle["other_distance"], float(RADIUS))
        with self.subTest("raw open air"):
            self.assertGreater(oracle["clearance"] - float(RADIUS), 1.0)
            self.assertGreater(oracle["surface_count"], 0)
        OUT.mkdir(parents=True, exist_ok=True)
        _write_oracle_header(OUT / "hcu_swept_oracle.h", oracle)
        _write_blob(OUT / "bloodgulch_collision.bin",
                    oracle["raw"]["payload"], oracle["raw"]["counts"])
        record = {key: oracle[key] for key in (
            "surface", "material", "material_type", "leaf", "designator",
            "oriented_distance", "inset", "other_distance", "clearance",
            "surface_count", "decoded_surfaces")}
        record.update({
            "center": [float(value) for value in oracle["center"]],
            "vector": [float(value) for value in oracle["vector"]],
            "miss": [float(value) for value in oracle["miss"]],
            "reachable_leaf_count": len(oracle["reachable_leaves"]),
            "payload_sha256": oracle["raw"]["payload_sha256"],
            "bsp_image_sha256": oracle["raw"]["image_sha256"],
            "counts": oracle["raw"]["counts"],
        })
        (OUT / "oracle.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        executable = OUT / "hcu-swept-collision"
        linkmap = OUT / "hcu-swept-collision.map"
        includes = [
            "-I" + str(OUT), "-I" + str(ROOT / "tests"),
            "-I" + str(HCU / "port/ps2/include"),
            "-I" + str(HCU / "port/include/xdk"),
            "-I" + str(HCU / "source/tag_files"),
            "-I" + str(HCU / "source/memory"),
            "-I" + str(HCU / "source/math"),
            "-I" + str(HCU / "source"),
            "-I" + str(HCU / "source/cseries"),
            "-I" + str(HCU / "source/objects"),
            "-I" + str(HCU / "source/scenario"),
            "-I" + str(HCU / "source/physics"),
            "-I" + str(ROOT / "src"),
        ]
        command = [
            compiler, *host_abi32_flags(), "-std=gnu99", "-O2", "-fshort-wchar",
            "-fno-strict-aliasing", "-fwrapv",
            "-DHALO_PS2=1", "-D_X86_=1", "-D_STDCALL_SUPPORTED=1",
            "-D__COLLISION_USAGE_H=1",
            "-D__cdecl=", "-D__stdcall=", "-D__fastcall=", "-D__declspec(x)=",
            "-ffunction-sections", "-fdata-sections", "-Wno-unused-function", "-w",
            *includes,
            "-include", str(ROOT / "tests/m3_ce_collision_host_preamble.h"),
            "-include", str(ROOT / "tests/hcu_swept_collision_host.h"),
            "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
            str(ROOT / "tests/hcu_swept_collision_main.c"),
            str(HCU / "source/physics/collision_bsp.c"),
            str(HCU / "source/physics/bsp2d.c"),
            str(HCU / "source/math/real_math.c"),
            "-Wl,--gc-sections", "-Wl,-Map," + str(linkmap),
            "-lm", "-o", str(executable),
        ]
        built = subprocess.run(command, capture_output=True, text=True)
        (OUT / "compile.log").write_text(built.stdout + built.stderr)
        self.assertEqual(built.returncode, 0, (built.stdout + built.stderr)[-8000:])
        link_text = linkmap.read_text(errors="replace")
        for symbol in ("collision_bsp_test_pill", "collision_bsp_test_sphere",
                       "fast_vector_intersects_sphere"):
            self.assertIn(symbol, link_text, symbol)
        run = subprocess.run([str(executable), str(OUT / "bloodgulch_collision.bin")],
                             capture_output=True, text=True)
        log = run.stdout + run.stderr
        (OUT / "run.log").write_text(log)
        if run.returncode in (-31, 159):
            self.fail("sandbox blocks native ILP32 execution with SIGSYS")
        self.assertEqual(run.returncode, 0, log)
        expected_lines = [
            "swept-subtest synthetic_pill_hit surface=0 material=0 leaf=0 "
            "t=0.375000 status=passed",
            "swept-subtest synthetic_pill_miss hit=0 status=passed",
            "swept-subtest synthetic_sphere_hit surface=0 material=0 leaf=0 "
            "surfaces=1 edges=0 vertices=0 status=passed",
            "swept-subtest synthetic_sphere_miss hit=0 surfaces=0 edges=0 "
            "vertices=0 status=passed",
            "swept-subtest bloodgulch_sphere_hit surface={surface} material={material} "
            "leaf={leaf} surfaces=1 edges=0 vertices=0 status=passed".format(**oracle),
            "swept-subtest bloodgulch_sphere_miss hit=0 surfaces=0 edges=0 "
            "vertices=0 leaves=",
            "swept-subtest bloodgulch_pill_hit surface={surface} material={material} "
            "leaf={leaf} t=0.000000 status=passed".format(**oracle),
            "swept-subtest bloodgulch_pill_miss hit=0 leaves=",
            "swept-subtest bsp_bytes bytes={bytes} status=unchanged".format(
                bytes=len(oracle["raw"]["payload"])),
            "swept-subtest collision_user depth=1 user0=0x5ee7 status=unchanged",
        ]
        for line in expected_lines:
            with self.subTest(line=line):
                self.assertIn(line, run.stdout)
        subtests = [line for line in run.stdout.splitlines() if line.startswith("swept-subtest ")]
        self.assertEqual(len(subtests), 10)
        self.assertTrue(all("status=passed" in line or "status=unchanged" in line
                            for line in subtests))
        _write_report(oracle, subtests)


def _write_report(oracle, subtests):
    def digest(path):
        return _sha256(path)
    sources = [
        ROOT / "tests/test_hcu_mp_swept_collision.py",
        ROOT / "tests/hcu_swept_collision_main.c",
        ROOT / "tests/hcu_swept_collision_host.h",
        OUT / "hcu-swept-collision",
        OUT / "run.log",
    ]
    lines = [
        "# Swept collision slice",
        "",
        "Status: PASS",
        "",
        "CE `collision_bsp_test_pill` and `collision_bsp_test_sphere` from "
        "`source/physics/collision_bsp.c` ran on a synthetic square floor and on "
        "Blood Gulch. The Blood Gulch collision arrays are the raw Xbox BSP bytes "
        "with host tag-block pointers. The package was pinned by SHA-256 and was "
        "not the publisher that built the view.",
        "",
        "Reproduction:",
        "",
        "```",
        "python3 -m pytest -q tests/test_hcu_mp_swept_collision.py",
        "```",
        "",
        "Tests: 1. C subtests: 10.",
        "",
        "| map | raw surfaces | query | result |",
        "| --- | --- | --- | --- |",
        "| synthetic square | 1 | pill and sphere into the floor; pill outside the square; sphere in open air | "
        "pill hit surface 0 material 0 leaf 0 t=0.375; outside pill miss; sphere hit surface 0; open-air sphere miss |",
        "| bloodgulch | {surfaces} | sphere/pill center above surface {surface}, material {material} "
        "(palette type {material_type}), plane designator {designator}, leaf {leaf}; "
        "oriented distance {distance:.5f} < radius 0.25; edge inset {inset:.3f}; "
        "other polygons at least {other:.3f} away | hit, t=0, one surface, no edges or vertices |".format(
            surfaces=oracle["surface_count"], surface=oracle["surface"],
            material=oracle["material"], material_type=oracle["material_type"],
            designator=oracle["designator"], leaf=oracle["leaf"],
            distance=oracle["oriented_distance"], inset=oracle["inset"],
            other=oracle["other_distance"]),
        "| bloodgulch open air | {surfaces} | same XY, z = max vertex z + radius + 2 "
        "(clearance {clearance:.5f}); horizontal pill of length 0.5; "
        "{leaves} reachable leaves | sphere and pill miss, leaf_count 0; "
        "the raw walk also ends outside every leaf, and every vertex is "
        "clearance-radius below the sphere |".format(
            surfaces=oracle["surface_count"], clearance=oracle["clearance"],
            leaves=len(oracle["reachable_leaves"])),
        "| other 12 stock MP maps | not this slice | one BSP was requested | "
        "not claimed empty |",
        "",
        "Subtests:",
        "",
    ]
    lines.extend(f"- `{line}`" for line in subtests)
    lines.extend([
        "",
        "SHA-256:",
        "",
    ])
    for path in sources:
        lines.append(f"- `{path.name}` `{digest(path)}`")
    lines.extend([
        "",
        "Limits: host ILP32 only. No PCSX2, GS, VU, or SPU2 output. "
        "The scenario BSP publisher and the `collision_test_pill` / "
        "`collision_get_features_in_sphere` wrappers were not linked; those wrappers "
        "call `scenario_location_from_point` and object feature collection on top of "
        "the BSP functions tested here. Collision-log calls are host no-ops that do "
        "not change user depth. The open-air miss is proved by vertex height, not by "
        "replaying CE's surface resolver.",
        "",
    ])
    (OUT / "report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    unittest.main()
