"""Compare CE's actual path edge builder with an independent raw Xbox BSP walk."""
from pathlib import Path
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
MP_SOURCE_SHA256 = {
    "beavercreek": "eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a",
    "bloodgulch": "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1",
    "boardingaction": "34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522",
    "carousel": "3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1",
    "chillout": "52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb",
    "damnation": "87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c",
    "hangemhigh": "e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f",
    "longest": "e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9",
    "prisoner": "85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307",
    "putput": "efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243",
    "ratrace": "577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e",
    "sidewinder": "995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc",
    "wizard": "978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb",
}
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from tools.ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def extract_c_function(source_path, marker):
    """Return one balanced top-level CE function, retaining its source verbatim."""
    source = source_path.read_text()
    start = source.index(marker)
    opening = source.index("{", start)
    semicolon = source.find(";", start, opening)
    if semicolon != -1:
        start = source.index(marker, semicolon + 1)
        opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise AssertionError(f"unterminated CE function {marker}")


def raw_fixture(map_name):
    """Decode original map bytes and produce independent CE-edge expectations."""
    map_path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    source_hash = hashlib.sha256(map_path.read_bytes()).hexdigest()
    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    region, _tag_base, _ = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{map_name}: expected exactly one stock MP BSP")
    location = locations[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 0x27C > len(image):
        raise AssertionError(f"{map_name}: invalid raw structure BSP root")

    def block(base, at, stride, label):
        count, address = struct.unpack_from("<iI", image, base + at)
        offset = address - location.address
        if count < 0 or (count and (offset < 0 or offset + count * stride > len(image))):
            raise AssertionError(f"{map_name}: invalid raw {label} extent")
        return count, offset

    collision_count, collision = block(root, 0xB0, 96, "collision BSP")
    if collision_count != 1:
        raise AssertionError(f"{map_name}: collision BSP count is {collision_count}")
    surface_count, surface_at = block(collision, 0x3C, 12, "collision surfaces")
    edge_count, edge_at = block(collision, 0x48, 24, "collision edges")
    vertex_count, vertex_at = block(collision, 0x54, 16, "collision vertices")
    path_count, path_at = block(root, 0x1E4, 1, "pathfinding surfaces")
    first_edges = []
    for i in range(surface_count):
        first_edges.append(struct.unpack_from("<i", image, surface_at + i * 12 + 4)[0])
    edges = [struct.unpack_from("<6i", image, edge_at + i * 24)
             for i in range(edge_count)]
    vertices = [struct.unpack_from("<3f", image, vertex_at + i * 16)
                for i in range(vertex_count)]
    path_flags = image[path_at:path_at + path_count]
    if len(path_flags) != path_count:
        raise AssertionError(f"{map_name}: truncated pathfinding flags")

    def f32(value):
        return struct.unpack("<f", struct.pack("<f", value))[0]

    def walk(surface_index):
        output = []
        edge_index = first_edges[surface_index]
        while 0 <= edge_index < edge_count and len(output) < 8:
            edge = edges[edge_index]
            if any(not 0 <= v < vertex_count for v in edge[:2]):
                break
            right = surface_index == edge[5]
            if not right and surface_index != edge[4]:
                break
            adjacent = edge[4] if right else edge[5]
            if (adjacent != -1 and
                    (not 0 <= adjacent < surface_count or adjacent >= path_count)):
                neighbor_flag = 0
            elif adjacent == -1 and path_count <= 0:
                neighbor_flag = 0
            else:
                neighbor_flag = path_flags[adjacent]
            v0, v1 = vertices[edge[0]], vertices[edge[1]]
            vector = tuple(f32(v1[axis] - v0[axis]) for axis in range(3))
            output.append((adjacent, neighbor_flag, v0, vector))
            edge_index = edge[3 if right else 2]
            if edge_index == first_edges[surface_index]:
                break
        return output

    # Independent walkable adjacency used by the CE A* fixture. Build it from
    # retail collision edge rings and pathfinding flags, not CE's path result.
    adjacency = [[] for _ in range(surface_count)]
    for surface_index in range(min(surface_count, path_count)):
        if not (path_flags[surface_index] & (1 << 6)):
            continue
        for adjacent, neighbor_flag, _base, _vector in walk(surface_index):
            if (0 <= adjacent < surface_count and adjacent < path_count and
                    (neighbor_flag & (1 << 6))):
                adjacency[surface_index].append(adjacent)

    # Select a deterministic short route from the largest connected component.
    # This exercises real adjacency while keeping CE's 1,024-node search bound
    # meaningful; broad route/performance stress is a separate workload gate.
    def bfs(start):
        distance = {start: 0}
        queue = [start]
        for current in queue:
            for neighbor in adjacency[current]:
                if neighbor not in distance:
                    distance[neighbor] = distance[current] + 1
                    queue.append(neighbor)
        return distance

    walkable_surfaces = [i for i in range(min(surface_count, path_count))
                         if path_flags[i] & (1 << 6)]
    if not walkable_surfaces:
        raise AssertionError(f"{map_name}: no walkable route candidates")
    components = []
    unseen = set(walkable_surfaces)
    while unseen:
        seed = min(unseen)
        distances = bfs(seed)
        component = set(distances).intersection(unseen)
        unseen.difference_update(component)
        components.append(component)
    component = max(components, key=lambda values: (len(values), -min(values)))
    route_start = min(component)
    distances = bfs(route_start)
    candidates = sorted(value for value in component
                        if distances.get(value) == 2)
    if not candidates:
        candidates = sorted(value for value in component
                            if distances.get(value) == 1)
    if not candidates:
        raise AssertionError(f"{map_name}: connected walkable graph has no nontrivial route")
    route_goal = candidates[0]

    def fnv_byte(hash_value, value):
        return ((hash_value ^ value) * 1099511628211) & 0xFFFFFFFFFFFFFFFF

    def fnv_u32(hash_value, value):
        for shift in range(0, 32, 8):
            hash_value = fnv_byte(hash_value, (value >> shift) & 255)
        return hash_value

    def fnv_float(hash_value, value):
        bits, = struct.unpack("<I", struct.pack("<f", value))
        return fnv_u32(hash_value, bits)

    digest = 14695981039346656037
    flags_digest = 14695981039346656037
    count_total = walkable = 0
    records = {}
    for surface_index in range(surface_count):
        found = walk(surface_index)
        flags = path_flags[surface_index] if surface_index < path_count else 0
        flags_digest = fnv_byte(flags_digest, flags)
        if surface_index < path_count and flags & (1 << 6):
            walkable += 1
        digest = fnv_u32(digest, surface_index)
        digest = fnv_u32(digest, len(found))
        count_total += len(found)
        for adjacent, neighbor_flag, base, vector in found:
            digest = fnv_u32(digest, adjacent & 0xFFFFFFFF)
            digest = fnv_byte(digest, neighbor_flag)
            for value in (*base, *vector):
                digest = fnv_float(digest, value)
        if surface_index in (0, surface_count // 2, surface_count - 1):
            records[surface_index] = found[0] if found else None
    payload = bytearray(struct.pack("<4I", surface_count, edge_count,
                                    vertex_count, path_count))
    payload.extend(b"".join(struct.pack("<4x i 4x", first) for first in first_edges))
    # CE collision_surface is 12 bytes; only first_edge_index is significant.
    payload.extend(b"".join(struct.pack("<6i", *edge) for edge in edges))
    payload.extend(b"".join(struct.pack("<3f i", *vertex, 0) for vertex in vertices))
    payload.extend(path_flags)
    return {
        "source_map_sha256": source_hash, "bsp_path": location.path,
        "raw_bsp_sha256": hashlib.sha256(image).hexdigest(),
        "surface_count": surface_count, "path_count": path_count,
        "walkable": walkable, "edges": count_total,
        "route_start": route_start, "route_goal": route_goal,
        "route_depth": distances[route_goal],
        "walkable_adjacency": adjacency,
        "flags_fnv": f"{flags_digest:016x}", "edges_fnv": f"{digest:016x}",
        "samples": records, "payload": bytes(payload),
    }


class MultiplayerPathConsumerTest(unittest.TestCase):
    def test_ce_edge_consumer_matches_raw_bsp_oracle(self):
        with tempfile.TemporaryDirectory(prefix="hcu-mp-path-") as temporary:
            temp = Path(temporary)
            path_source = HCU / "source/ai/path.c"
            bsp_source = HCU / "source/physics/collision_bsp.c"
            collision_valid = extract_c_function(
                bsp_source, "boolean collision_bsp_valid_surface_index(")
            ring_continues = extract_c_function(
                bsp_source, "boolean collision_surface_edge_ring_continues(")
            edge_builder = extract_c_function(
                path_source, "static short build_path_edges_for_surface(")
            runner_source = temp / "hcu_mp_path_consumer_main.c"
            runner_source.write_text(
                (ROOT / "tests/hcu_mp_path_consumer_main.c").read_text().replace(
                    "/* CE_PATH_AND_BSP_FUNCTIONS */",
                    "#define long int32_t\n" + collision_valid + "\n" +
                    ring_continues + "\n" + edge_builder + "\n#undef long"))
            executable = temp / "mp-path-consumer"
            command = [
                os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra",
                "-Werror", str(runner_source), "-o", str(executable),
            ]
            compiled = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            for map_name in MP_MAPS:
                with self.subTest(map=map_name):
                    raw = raw_fixture(map_name)
                    self.assertEqual(raw["source_map_sha256"], MP_SOURCE_SHA256[map_name])
                    payload = temp / f"{map_name}.bin"
                    payload.write_bytes(raw["payload"])
                    run = subprocess.run([str(executable), str(payload)],
                                         capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    expected = (
                        f"ce-path-consumer surfaces={raw['surface_count']} "
                        f"path_flags={raw['path_count']} walkable={raw['walkable']} "
                        f"edges={raw['edges']} flags_fnv={raw['flags_fnv']} "
                        f"edges_fnv={raw['edges_fnv']} status=passed"
                    )
                    self.assertIn(expected, run.stdout)
                    for surface_index, record in raw["samples"].items():
                        match = next(line for line in run.stdout.splitlines()
                                     if line.startswith(f"sample surface={surface_index} "))
                        if record is None:
                            self.assertIn("count=0", match)
                        else:
                            adjacent, flags, base, vector = record
                            expected_sample = (
                                f"adjacent={adjacent} flags={flags} "
                                f"base={base[0]:.9g},{base[1]:.9g},{base[2]:.9g} "
                                f"vector={vector[0]:.9g},{vector[1]:.9g},{vector[2]:.9g}"
                            )
                            self.assertIn(expected_sample, match)


if __name__ == "__main__":
    unittest.main()
