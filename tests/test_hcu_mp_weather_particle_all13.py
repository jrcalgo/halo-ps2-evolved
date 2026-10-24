"""CE weather selection and polyhedra lookup for all 13 stock MP maps.

The oracle is the raw Xbox BSP and tag bytes. The harness compiles the CE
bodies of scenario_get_fog_region_index, scenario_fog_region_get_fog_index,
scenario_location_underwater, scenario_get_current, weather_particle_systems_render,
and weather_polyhedra_find. Maps whose weather palette does not resolve a rain
tag are an explicit empty particle-system result. The particle sprite renderer
is not compiled.
"""
from pathlib import Path
import hashlib
import os
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MAP_ROOT = ROOT / "build/retail-maps/decompressed"
OUT_DIR = ROOT / "build/step7-swarm/weather"
HARNESS = ROOT / "tests/weather_mp_particle_all13_main.c"
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
MAP_SHA256 = {
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
SOURCE_SHA256 = {
    "scenario/scenario.c": "22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0",
    "scenario/wind.c": "b4464221406b8388a77815afd84a179f9b8fe2c835f841b34caa6f6bc815f911",
    "effects/weather_particle_systems.c": "5c6f2cbe81276d89203890b1dbba3eb833125b2eb1c8c24c4c96dd74d61360b3",
    "math/real_math.h": "f50befc4193d6d3d46cd00fc5f869c8a7a538a581b64ab8baeefce5e4d7220c5",
    "tag_files/tag_groups.h": "558afc4bfb81377af90d797cc6e7403b01196de1bd54469424dc7e773b3b9ff5",
}
RAIN_GROUP = 0x7261696E
NONE = -1
FORCE_WATER = 1 << 2
FORCE_NO_WATER = 1 << 3
POLY_FIND_DISTANCE_BITS = 0x49742400
FOG_MAPS = {"beavercreek", "chillout", "damnation"}

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from host_abi32 import flags as abi32_flags  # noqa: E402
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def s32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def f32_add(left, right):
    return f32(f32(left) + f32(right))


def f32_sub(left, right):
    return f32(f32(left) - f32(right))


def f32_mul(left, right):
    return f32(f32(left) * f32(right))


def f32_bits(value):
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def extract_function(source, signature):
    body = None
    pos = 0
    while True:
        start = source.find(signature, pos)
        if start < 0:
            break
        brace = source.find("{", start)
        semi = source.find(";", start)
        pos = start + len(signature)
        if brace < 0 or (semi >= 0 and semi < brace):
            continue
        if body is not None:
            raise AssertionError(f"multiple definitions for {signature}")
        depth = 0
        for index in range(brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    body = source[start:index + 1]
                    break
        if body is None:
            raise AssertionError(f"unterminated {signature}")
    if body is None:
        raise AssertionError(f"missing {signature}")
    if body not in source:
        raise AssertionError(f"extracted text left the source for {signature}")
    return body


def as_static(body):
    if body.startswith("__inline "):
        return "static " + body[len("__inline "):]
    if body.startswith("static __inline__ "):
        return "static " + body[len("static __inline__ "):]
    return body


def block_at(image, root, base, offset, stride):
    count, address = struct.unpack_from("<iI", image, root + offset)
    if count < 0:
        raise AssertionError(f"negative block count at {offset:#x}")
    data = address - base if address else 0
    if count and (data < 0 or data + count * stride > len(image)):
        raise AssertionError(f"block at {offset:#x} leaves the BSP image")
    raw_address = address
    return count, data, raw_address


def plane_distance(normal, point):
    nx, ny, nz, dist = normal
    acc = f32_mul(nx, point[0])
    acc = f32_add(acc, f32_mul(ny, point[1]))
    acc = f32_add(acc, f32_mul(nz, point[2]))
    return f32_sub(acc, dist)


def point_at_distance(normal, dist):
    nx, ny, nz, plane_d = normal
    mag2 = f32_add(f32_add(f32_mul(nx, nx), f32_mul(ny, ny)), f32_mul(nz, nz))
    if mag2 == 0.0:
        raise AssertionError("fog plane normal has zero length")
    scale = f32((f32(plane_d) + f32(dist)) / mag2)
    return (f32_mul(nx, scale), f32_mul(ny, scale), f32_mul(nz, scale))


def load_map(name):
    path = MAP_ROOT / f"{name}.map"
    raw_map = path.read_bytes()
    map_hash = hashlib.sha256(raw_map).hexdigest()
    if map_hash != MAP_SHA256[name]:
        raise AssertionError(f"{name}: source map hash changed: {map_hash}")
    index = tagindex.TagIndex.read(path)
    tag_region, tag_base, _source = read_xbox_tag_region(path)
    locations = bsp.locate(index, tag_region, mapinfo.read_header(path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{name}: expected one stock MP BSP")
    location = locations[0]
    image = raw_map[location.file_offset:location.file_offset + location.size]
    if len(image) != location.size:
        raise AssertionError(f"{name}: truncated BSP")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError(f"{name}: BSP root leaves the image")
    by_id = {entry.tag_id: entry for entry in index.entries}
    rain_tags = [entry.path for entry in index.entries if entry.group == "rain"]

    palette_count, palette_at, _palette_address = block_at(
        image, root, location.address, 0x1B4, 0xF0)
    poly_count, poly_at, poly_address = block_at(
        image, root, location.address, 0x1C0, 0x20)
    plane_count, plane_at, _plane_address = block_at(
        image, root, location.address, 0x178, 0x20)
    region_count, region_at, _region_address = block_at(
        image, root, location.address, 0x184, 0x28)
    fog_palette_count, fog_palette_at, _fog_palette_address = block_at(
        image, root, location.address, 0x190, 0x88)
    cluster_count, cluster_at, _cluster_address = block_at(
        image, root, location.address, 0x134, 0x68)

    palette = []
    for entry_index in range(palette_count):
        entry = palette_at + entry_index * 0xF0
        group = struct.unpack_from("<I", image, entry + 0x20)[0]
        datum_u = struct.unpack_from("<I", image, entry + 0x2C)[0]
        datum = s32(datum_u)
        resolved = None
        if datum != NONE:
            tag = by_id.get(datum_u)
            if tag is None or tag.group != "rain":
                raise AssertionError(
                    f"{name}: palette {entry_index} datum {datum_u:#x} "
                    f"does not resolve to a rain tag")
            resolved = tag.path
        elif datum_u in by_id:
            raise AssertionError(f"{name}: NONE datum collides with a tag id")
        palette.append({
            "group": group, "datum": datum, "datum_u": datum_u, "resolved": resolved,
        })

    polyhedra = []
    for poly_index in range(poly_count):
        base = poly_at + poly_index * 0x20
        center = tuple(f32(value) for value in struct.unpack_from("<3f", image, base))
        radius = f32(struct.unpack_from("<f", image, base + 12)[0])
        plane_n, plane_address = struct.unpack_from("<iI", image, base + 0x14)
        plane_data = plane_address - location.address if plane_address else 0
        if plane_n < 0 or (plane_n and (plane_data < 0 or plane_data + plane_n * 16 > len(image))):
            raise AssertionError(f"{name}: polyhedron {poly_index} planes leave the BSP")
        polyhedra.append({
            "center": center, "radius": radius, "planes": plane_n,
            "raw": image[base:base + 0x20],
        })

    planes = []
    for plane_index in range(plane_count):
        base = plane_at + plane_index * 0x20
        region, _material = struct.unpack_from("<hh", image, base)
        normal = tuple(f32(value) for value in struct.unpack_from("<4f", image, base + 4))
        planes.append({"region": region, "normal": normal, "raw": image[base:base + 0x20]})

    regions = []
    for region_index in range(region_count):
        base = region_at + region_index * 0x28
        fog_palette_index, weather = struct.unpack_from("<hh", image, base + 0x24)
        regions.append({
            "fog_palette": fog_palette_index, "weather": weather,
            "raw": image[base:base + 0x28],
        })

    fog_palette = []
    for palette_index in range(fog_palette_count):
        base = fog_palette_at + palette_index * 0x88
        datum_u = struct.unpack_from("<I", image, base + 0x2C)[0]
        fog_palette.append({"datum": s32(datum_u), "datum_u": datum_u, "raw": image[base:base + 0x88]})

    fogs = {}
    for entry in fog_palette:
        if entry["datum"] == NONE or entry["datum_u"] in fogs:
            continue
        tag = by_id.get(entry["datum_u"])
        if tag is None or tag.group != "fog ":
            raise AssertionError(f"{name}: fog datum {entry['datum_u']:#x} is not a fog tag")
        offset = tag.data_address - tag_base
        if offset < 0 or offset + 0x78 > len(tag_region):
            raise AssertionError(f"{name}: fog definition leaves the tag region")
        blob = tag_region[offset:offset + 0x78]
        fogs[entry["datum_u"]] = {
            "datum": entry["datum"], "flags": blob[0],
            "plane_distance": f32(struct.unpack_from("<f", blob, 0x74)[0]),
            "raw": blob, "path": tag.path,
        }

    clusters = []
    for cluster_index in range(cluster_count):
        base = cluster_at + cluster_index * 0x68
        fog_ref, weather = struct.unpack_from("<h", image, base + 2)[0], struct.unpack_from(
            "<h", image, base + 8)[0]
        clusters.append({
            "fog": fog_ref, "weather": weather, "raw": image[base:base + 0x68],
        })

    return {
        "name": name,
        "map_hash": map_hash,
        "bsp_sha": hashlib.sha256(image).hexdigest(),
        "bsp_path": location.path,
        "rain_tags": rain_tags,
        "palette": palette,
        "polyhedra": polyhedra,
        "poly_address": poly_address,
        "planes": planes,
        "regions": regions,
        "fog_palette": fog_palette,
        "fogs": fogs,
        "clusters": clusters,
        "cluster_bytes": image[cluster_at:cluster_at + cluster_count * 0x68],
        "plane_bytes": image[plane_at:plane_at + plane_count * 0x20],
        "region_bytes": image[region_at:region_at + region_count * 0x28],
        "fog_palette_bytes": image[fog_palette_at:fog_palette_at + fog_palette_count * 0x88],
        "weather_bytes": image[palette_at:palette_at + palette_count * 0xF0],
        "poly_bytes": image[poly_at:poly_at + poly_count * 0x20],
    }


def valid(index, count):
    return 0 <= index < count


def fog_datum_for_region(raw, region_index):
    if not valid(region_index, len(raw["regions"])):
        return None
    palette_index = raw["regions"][region_index]["fog_palette"]
    if not valid(palette_index, len(raw["fog_palette"])):
        return None
    datum = raw["fog_palette"][palette_index]["datum"]
    if datum == NONE:
        return None
    return raw["fog_palette"][palette_index]["datum_u"]


def water_offset(raw, region_index):
    datum = fog_datum_for_region(raw, region_index)
    if datum is None:
        return f32(0)
    fog = raw["fogs"][datum]
    if fog["flags"] & 1:
        return fog["plane_distance"]
    return f32(0)


def fog_region(raw, cluster, point, null_fog):
    ref = cluster["fog"]
    if ref == NONE:
        return NONE
    if (ref & 0x8000) and (ref & 0x7FFF) >= len(raw["planes"]):
        return NONE
    if ref & 0x8000:
        plane = raw["planes"][ref & 0x7FFF]
        offset = water_offset(raw, plane["region"])
        if null_fog or f32_add(plane_distance(plane["normal"], point), offset) < 0:
            result = plane["region"]
        else:
            result = NONE
    else:
        result = ref & 0x7FFF
    if not valid(result, len(raw["regions"])):
        return NONE
    return result


def particle_selection(raw, cluster_index, point):
    cluster = raw["clusters"][cluster_index]
    region = fog_region(raw, cluster, point, False)
    weather = NONE
    underwater = 0
    if region != NONE:
        datum = fog_datum_for_region(raw, region)
        if datum is not None and (raw["fogs"][datum]["flags"] & 1):
            underwater = 1
        weather = raw["regions"][region]["weather"]
    if weather == NONE:
        weather = cluster["weather"]
    if not valid(weather, len(raw["palette"])):
        weather = NONE
    particle = NONE if weather == NONE else raw["palette"][weather]["datum"]
    return {
        "fog": region, "weather": weather, "underwater": underwater,
        "datum": particle, "new": 0 if particle == NONE else 1,
    }


def current_selection(raw, cluster_index, point, flags):
    cluster = raw["clusters"][cluster_index]
    region = fog_region(raw, cluster, point, bool(flags & FORCE_WATER))
    weather = cluster["weather"]
    in_water = 0
    if region != NONE:
        record = raw["regions"][region]
        if valid(record["fog_palette"], len(raw["fog_palette"])) and record["weather"] != NONE:
            datum = raw["fog_palette"][record["fog_palette"]]["datum"]
            if datum != NONE:
                fog = raw["fogs"][raw["fog_palette"][record["fog_palette"]]["datum_u"]]
                if fog["flags"] & 1:
                    if not (flags & FORCE_NO_WATER):
                        weather = record["weather"]
                        in_water = 1
                elif not (flags & FORCE_WATER):
                    weather = record["weather"]
    return {"fog": region, "weather": weather, "in_water": in_water}


def side_point(raw, plane, inside):
    offset = water_offset(raw, plane["region"])
    for delta in (1.0, 2.0, 4.0, 8.0, 16.0):
        desired = f32(-delta if inside else delta)
        point = point_at_distance(plane["normal"], f32_sub(desired, offset))
        total = f32_add(plane_distance(plane["normal"], point), offset)
        if inside and total < 0:
            return point
        if not inside and total >= 0:
            return point
    raise AssertionError("could not place a fog-plane sample")


def plane_for_cluster(raw, cluster):
    ref = cluster["fog"]
    if ref == NONE or not (ref & 0x8000):
        return None
    index = ref & 0x7FFF
    if index >= len(raw["planes"]):
        return None
    return raw["planes"][index]


def build_queries(raw, map_index):
    queries = []
    origin = (f32(0), f32(0), f32(0))

    def add(cluster_index, point, flags, null_fog, particles):
        particle = particle_selection(raw, cluster_index, point)
        current = current_selection(raw, cluster_index, point, flags)
        fog = fog_region(raw, raw["clusters"][cluster_index], point, null_fog)
        queries.append({
            "map": raw["name"], "map_index": map_index, "cluster": cluster_index,
            "flags": flags, "null_fog": int(null_fog),
            "do_under": int(particles), "do_particles": int(particles),
            "do_current": 1, "point": point,
            "bits": tuple(f32_bits(value) for value in point),
            "exp_fog": fog,
            "exp_under_weather": particle["weather"],
            "exp_underwater": particle["underwater"],
            "exp_current_weather": current["weather"],
            "exp_in_water": current["in_water"],
            "exp_datum": particle["datum"],
            "exp_new": particle["new"] if particles else 0,
        })

    for cluster_index, cluster in enumerate(raw["clusters"]):
        plane = plane_for_cluster(raw, cluster)
        outside = side_point(raw, plane, False) if plane else origin
        add(cluster_index, outside, 0, False, True)
        if plane:
            inside = side_point(raw, plane, True)
            add(cluster_index, inside, 0, False, True)
            add(cluster_index, inside, FORCE_WATER, True, False)
            add(cluster_index, inside, FORCE_NO_WATER, False, False)
    return queries


def visible_polyhedra(raw):
    camera = (f32(0), f32(0), f32(0))
    maximum = f32(struct.unpack("<f", struct.pack("<I", POLY_FIND_DISTANCE_BITS))[0])
    found = []
    for index, poly in enumerate(raw["polyhedra"]):
        center = poly["center"]
        delta = (
            f32_sub(camera[0], center[0]), f32_sub(camera[1], center[1]),
            f32_sub(camera[2], center[2]))
        dist2 = f32_add(f32_add(f32_mul(delta[0], delta[0]), f32_mul(delta[1], delta[1])),
                        f32_mul(delta[2], delta[2]))
        reach = f32_add(maximum, poly["radius"])
        if dist2 < f32_mul(reach, reach) and len(found) < 8:
            found.append(index)
    return found


def c_bytes(data):
    if not data:
        return "{0}"
    rows = []
    for offset in range(0, len(data), 16):
        rows.append(",".join(f"0x{byte:02x}" for byte in data[offset:offset + 16]))
    return "{\n" + ",\n".join(rows) + "\n}"


def emit_data(maps, queries):
    parts = []
    for index, raw in enumerate(maps):
        prefix = raw["name"]
        parts.append(f"static struct structure_cluster {prefix}_clusters[{len(raw['clusters'])}];")
        parts.append(f"static const unsigned char {prefix}_cluster_bytes[] = {c_bytes(raw['cluster_bytes'])};")
        parts.append(f"static struct structure_weather_palette_entry {prefix}_weather[{len(raw['palette'])}];")
        parts.append(f"static const unsigned char {prefix}_weather_bytes[] = {c_bytes(raw['weather_bytes'])};")
        if raw["planes"]:
            parts.append(f"static struct structure_fog_plane {prefix}_planes[{len(raw['planes'])}];")
            parts.append(f"static const unsigned char {prefix}_plane_bytes[] = {c_bytes(raw['plane_bytes'])};")
        if raw["regions"]:
            parts.append(f"static struct structure_fog_region {prefix}_regions[{len(raw['regions'])}];")
            parts.append(f"static const unsigned char {prefix}_region_bytes[] = {c_bytes(raw['region_bytes'])};")
        if raw["fog_palette"]:
            parts.append(
                f"static struct structure_fog_palette_entry {prefix}_fog_palette[{len(raw['fog_palette'])}];")
            parts.append(
                f"static const unsigned char {prefix}_fog_palette_bytes[] = {c_bytes(raw['fog_palette_bytes'])};")
        if raw["polyhedra"]:
            parts.append(
                f"static struct structure_weather_polyhedron {prefix}_poly[{len(raw['polyhedra'])}];")
            parts.append(f"static const unsigned char {prefix}_poly_bytes[] = {c_bytes(raw['poly_bytes'])};")
            counts = ",".join(str(poly["planes"]) for poly in raw["polyhedra"])
            parts.append(f"static const long {prefix}_plane_counts[] = {{{counts}}};")
        if raw["fogs"]:
            parts.append(f"static struct fog_slot_tag {prefix}_fogs[{len(raw['fogs'])}];")
            blobs = b"".join(raw["fogs"][key]["raw"] for key in raw["fogs"])
            datums = ",".join(f"0x{key:08x}u" for key in raw["fogs"])
            parts.append(f"static const unsigned char {prefix}_fog_bytes[] = {c_bytes(blobs)};")
            parts.append(f"static const unsigned long {prefix}_fog_datums[] = {{{datums}}};")
        groups = ",".join(f"0x{entry['group']:08x}u" for entry in raw["palette"])
        datums = ",".join(f"{entry['datum']}L" for entry in raw["palette"])
        parts.append(f"static const unsigned long {prefix}_expect_group[] = {{{groups}}};")
        parts.append(f"static const long {prefix}_expect_datum[] = {{{datums}}};")
        found = visible_polyhedra(raw)
        parts.append(f"/* {prefix} visible polyhedra at origin: {found} */")
        raw["expect_poly_found"] = len(found)

    rows = []
    for raw in maps:
        prefix = raw["name"]
        fields = [
            f'.name = "{raw["name"]}"',
            f'.bsp_sha = "{raw["bsp_sha"]}"',
            f'.palette_count = {len(raw["palette"])}',
            f'.cluster_count = {len(raw["clusters"])}',
            f'.plane_count = {len(raw["planes"])}',
            f'.region_count = {len(raw["regions"])}',
            f'.fog_palette_count = {len(raw["fog_palette"])}',
            f'.poly_count = {len(raw["polyhedra"])}',
            f'.fog_count = {len(raw["fogs"])}',
            f'.expect_poly_found = {raw["expect_poly_found"]}',
            f'.clusters = {prefix}_clusters',
            f'.cluster_bytes = {prefix}_cluster_bytes',
            f'.cluster_bytes_n = sizeof {prefix}_cluster_bytes',
            f'.planes = {"0" if not raw["planes"] else prefix + "_planes"}',
            f'.plane_bytes = {"0" if not raw["planes"] else prefix + "_plane_bytes"}',
            f'.plane_bytes_n = {"0" if not raw["planes"] else "sizeof " + prefix + "_plane_bytes"}',
            f'.regions = {"0" if not raw["regions"] else prefix + "_regions"}',
            f'.region_bytes = {"0" if not raw["regions"] else prefix + "_region_bytes"}',
            f'.region_bytes_n = {"0" if not raw["regions"] else "sizeof " + prefix + "_region_bytes"}',
            f'.fog_palette = {"0" if not raw["fog_palette"] else prefix + "_fog_palette"}',
            f'.fog_palette_bytes = {"0" if not raw["fog_palette"] else prefix + "_fog_palette_bytes"}',
            f'.fog_palette_bytes_n = {"0" if not raw["fog_palette"] else "sizeof " + prefix + "_fog_palette_bytes"}',
            f'.weather = {prefix}_weather',
            f'.weather_bytes = {prefix}_weather_bytes',
            f'.weather_bytes_n = sizeof {prefix}_weather_bytes',
            f'.poly = {"0" if not raw["polyhedra"] else prefix + "_poly"}',
            f'.poly_bytes = {"0" if not raw["polyhedra"] else prefix + "_poly_bytes"}',
            f'.poly_bytes_n = {"0" if not raw["polyhedra"] else "sizeof " + prefix + "_poly_bytes"}',
            f'.plane_counts = {"0" if not raw["polyhedra"] else prefix + "_plane_counts"}',
            f'.fogs = {"0" if not raw["fogs"] else prefix + "_fogs"}',
            f'.fog_bytes = {"0" if not raw["fogs"] else prefix + "_fog_bytes"}',
            f'.fog_datums = {"0" if not raw["fogs"] else prefix + "_fog_datums"}',
            f'.expect_group = {prefix}_expect_group',
            f'.expect_datum = {prefix}_expect_datum',
        ]
        rows.append("{\n" + ",\n".join(fields) + "\n}")
    query_rows = []
    for query in queries:
        xb, yb, zb = query["bits"]
        query_rows.append(
            "{%d,%d,%d,%d,%d,%d,%d,0x%08xu,0x%08xu,0x%08xu,%d,%d,%d,%d,%d,%dL,%uu,0u,%uu}" % (
                query["map_index"], query["cluster"], query["flags"], query["null_fog"],
                query["do_under"], query["do_particles"], query["do_current"],
                xb, yb, zb, query["exp_fog"], query["exp_under_weather"],
                query["exp_underwater"], query["exp_current_weather"], query["exp_in_water"],
                query["exp_datum"], query["exp_new"], query["exp_new"]))
    parts.append("static struct map_view maps[] = {\n" + ",\n".join(rows) + "\n};")
    parts.append(f"static int map_count = {len(maps)};")
    parts.append("static struct weather_query queries[] = {\n" + ",\n".join(query_rows) + "\n};")
    parts.append(f"static unsigned query_count = {len(queries)}u;")
    return "\n".join(parts) + "\n"


def parse_fields(line):
    return dict(token.split("=", 1) for token in line.split() if "=" in token)


def require_line(lines, cursor, op):
    if cursor >= len(lines):
        raise AssertionError(f"missing CE output for {op}")
    fields = parse_fields(lines[cursor])
    if fields.get("op") != op and not lines[cursor].startswith(op):
        raise AssertionError(f"expected {op} at {lines[cursor]}")
    return fields, cursor + 1


class WeatherParticleAll13Test(unittest.TestCase):
    def test_ce_weather_selection_and_polyhedra_against_raw_bsp(self):
        for relative, digest in SOURCE_SHA256.items():
            actual = sha256(HCU / "source" / relative)
            self.assertEqual(actual, digest, relative)
        if f32_bits(1000000.0) != POLY_FIND_DISTANCE_BITS:
            raise AssertionError("polyhedra search distance bits changed")
        scenario = (HCU / "source/scenario/scenario.c").read_text()
        wind = (HCU / "source/scenario/wind.c").read_text()
        weather = (HCU / "source/effects/weather_particle_systems.c").read_text()
        math = (HCU / "source/math/real_math.h").read_text()
        tags = (HCU / "source/tag_files/tag_groups.h").read_text()
        bodies = {
            "fog": extract_function(scenario, "short scenario_get_fog_region_index("),
            "fog_index": extract_function(scenario, "long scenario_fog_region_get_fog_index("),
            "under": extract_function(scenario, "boolean scenario_location_underwater("),
            "current": extract_function(wind, "boolean scenario_get_current("),
            "render": extract_function(weather, "void weather_particle_systems_render("),
            "poly": extract_function(weather, "static short weather_polyhedra_find("),
        }
        self.assertIn("fog_region->weather_palette_index", bodies["under"])
        self.assertIn("cluster->weather_palette_index", bodies["under"])
        self.assertIn("scenario_get_fog_region_index(", bodies["current"])
        self.assertIn("fog_region->weather_palette_index", bodies["current"])
        self.assertIn("scenario_get_current_from_weather_palette(", bodies["current"])
        self.assertIn("particle_system.index", bodies["render"])
        self.assertNotIn("build_sprite", bodies["render"])
        self.assertIn("bounding_sphere_radius", bodies["poly"])
        self.assertIn("weather_polyhedra.count", bodies["poly"])
        math_bodies = [
            as_static(extract_function(math, "__inline real_vector3d *vector_from_points3d(")),
            as_static(extract_function(math, "__inline real magnitude_squared3d(")),
            as_static(extract_function(math, "__inline real distance_squared3d(")),
            as_static(extract_function(math, "__inline real dot_product3d(")),
            as_static(extract_function(math, "__inline real plane3d_distance_to_point(")),
        ]
        fast = as_static(extract_function(tags, "static __inline__ void *tag_block_get_element_fast("))
        maps = [load_map(name) for name in MP_MAPS]
        self.assertEqual([item["name"] for item in maps], list(MP_MAPS))
        queries = []
        summary = []
        for map_index, raw in enumerate(maps):
            with self.subTest(map=raw["name"], phase="raw"):
                self.assertGreater(len(raw["clusters"]), 0)
                self.assertGreater(len(raw["palette"]), 0)
                self.assertEqual(raw["rain_tags"], [])
                self.assertEqual(raw["polyhedra"], [])
                self.assertEqual(raw["poly_address"], 0)
                for entry in raw["palette"]:
                    self.assertEqual(entry["group"], RAIN_GROUP)
                    self.assertEqual(entry["datum"], NONE)
                    self.assertIsNone(entry["resolved"])
                if raw["name"] in FOG_MAPS:
                    self.assertGreater(len(raw["planes"]), 0)
                    self.assertTrue(any(cluster["fog"] != NONE for cluster in raw["clusters"]))
                else:
                    self.assertEqual(raw["planes"], [])
                    self.assertTrue(all(cluster["fog"] == NONE for cluster in raw["clusters"]))
            map_queries = build_queries(raw, map_index)
            queries.extend(map_queries)
            overrides = 0
            inside = 0
            for query in map_queries:
                cluster_weather = raw["clusters"][query["cluster"]]["weather"]
                if query["flags"] == 0 and query["exp_current_weather"] != cluster_weather:
                    overrides += 1
                if query["null_fog"] == 0 and query["exp_fog"] != NONE and query["do_particles"]:
                    inside += 1
            summary.append({
                "name": raw["name"], "bsp_sha": raw["bsp_sha"],
                "palettes": len(raw["palette"]), "clusters": len(raw["clusters"]),
                "fog_planes": len(raw["planes"]), "fog_regions": len(raw["regions"]),
                "polyhedra": len(raw["polyhedra"]), "rain_tags": len(raw["rain_tags"]),
                "resolved_particle_systems": sum(entry["resolved"] is not None for entry in raw["palette"]),
                "queries": len(map_queries), "inside_fog_particle_queries": inside,
                "weather_overrides": overrides,
                "particle_datums": [entry["datum"] for entry in raw["palette"]],
            })
            if raw["name"] in FOG_MAPS:
                self.assertGreater(inside, 0, raw["name"])
            self.assertEqual(overrides, 0, raw["name"])

        ce = "\n\n".join(bodies[name] for name in (
            "fog_index", "fog", "under", "current", "poly", "render"))
        source = HARNESS.read_text()
        for marker in ("/* INJECT_MATH */", "/* INJECT_FAST_BLOCK */",
                       "/* INJECT_CE */", "/* INJECT_DATA */"):
            self.assertIn(marker, source)
        source = source.replace("/* INJECT_MATH */", "\n".join(math_bodies))
        source = source.replace("/* INJECT_FAST_BLOCK */", fast)
        source = source.replace("/* INJECT_CE */", ce)
        source = source.replace("/* INJECT_DATA */", emit_data(maps, queries))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        generated = OUT_DIR / "weather_particle_all13.c"
        executable = OUT_DIR / "weather-particle-all13"
        generated.write_text(source)
        compile_log = OUT_DIR / "compile.log"
        built = subprocess.run(
            ["gcc", *abi32_flags(), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
             "-Wno-multichar", "-fno-strict-aliasing", "-fwrapv",
             str(generated), "-lm", "-o", str(executable)],
            capture_output=True, text=True)
        compile_log.write_text(built.stdout + built.stderr)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        elf = executable.read_bytes()
        self.assertEqual(elf[:4], b"\x7fELF")
        self.assertEqual(elf[4], 1)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        (OUT_DIR / "weather-particle-all13.log").write_text(run.stdout + run.stderr)
        lines = [line for line in run.stdout.splitlines()
                 if line.startswith("ce ") or line.startswith("ce-")]
        cursor = 0
        problems = []
        try:
            for query in queries:
                fields, cursor = require_line(lines, cursor, "fog")
                if (fields["map"] != query["map"] or int(fields["cluster"]) != query["cluster"] or
                        int(fields["null"]) != query["null_fog"] or
                        int(fields["fog"]) != query["exp_fog"]):
                    problems.append(f"fog {fields} expected {query['exp_fog']}")
                if query["do_under"]:
                    fields, cursor = require_line(lines, cursor, "underwater")
                    if (int(fields["weather"]) != query["exp_under_weather"] or
                            int(fields["underwater"]) != query["exp_underwater"]):
                        problems.append(f"underwater {fields}")
                if query["do_particles"]:
                    fields, cursor = require_line(lines, cursor, "particles")
                    if (int(fields["weather"]) != query["exp_under_weather"] or
                            int(fields["underwater"]) != query["exp_underwater"] or
                            int(fields["datum"]) != query["exp_datum"] or
                            int(fields["new"]) != query["exp_new"] or
                            int(fields["del"]) != 0 or int(fields["upd"]) != query["exp_new"]):
                        problems.append(f"particles {fields}")
                if query["do_current"]:
                    fields, cursor = require_line(lines, cursor, "current")
                    if (int(fields["flags"]) != query["flags"] or
                            int(fields["weather"]) != query["exp_current_weather"] or
                            int(fields["in_water"]) != query["exp_in_water"]):
                        problems.append(f"current {fields}")
            for raw in maps:
                fields, cursor = require_line(lines, cursor, "polyhedra")
                if (fields["map"] != raw["name"] or int(fields["count"]) != len(raw["polyhedra"]) or
                        int(fields["found"]) != raw["expect_poly_found"] or
                        int(fields["empty"]) != int(len(raw["polyhedra"]) == 0)):
                    problems.append(f"polyhedra {fields}")
                for entry_index, entry in enumerate(raw["palette"]):
                    fields, cursor = require_line(lines, cursor, "palette")
                    if (int(fields["index"]) != entry_index or
                            int(fields["group"], 16) != entry["group"] or
                            int(fields["datum"]) != entry["datum"]):
                        problems.append(f"palette {fields}")
                fields, cursor = require_line(lines, cursor, "identity")
                if fields["bsp_sha"] != raw["bsp_sha"]:
                    problems.append(f"identity {fields}")
                fields, cursor = require_line(lines, cursor, "stable")
                if fields["bsp"] != "1" or fields["depth"] != "1" or fields["user"] != "17":
                    problems.append(f"stable {fields}")
            summary_line = lines[cursor]
            cursor += 1
            summary_fields = parse_fields(summary_line)
            if (summary_fields.get("maps") != "13" or summary_fields.get("queries") != str(len(queries)) or
                    summary_fields.get("retail_new") != "0" or
                    summary_fields.get("retail_poly_found") != "0" or
                    summary_fields.get("result") != "passed"):
                problems.append(summary_line)
            control = lines[cursor]
            cursor += 1
            if "particles_datum=4" not in control or "new=1" not in control or "poly_near=1" not in control or "poly_far=0" not in control or "plane_count=2" not in control:
                problems.append(control)
            final = lines[cursor]
            if "mismatches=0" not in final or "result=passed" not in final:
                problems.append(final)
        except AssertionError as error:
            problems.append(str(error))
        result_lines = [
            "map palettes clusters fog_planes fog_regions polyhedra rain_tags "
            "resolved particle_datums queries inside_fog overrides bsp_sha"
        ]
        for row in summary:
            result_lines.append(
                f"{row['name']} palettes={row['palettes']} clusters={row['clusters']} "
                f"fog_planes={row['fog_planes']} fog_regions={row['fog_regions']} "
                f"polyhedra={row['polyhedra']} rain_tags={row['rain_tags']} "
                f"resolved={row['resolved_particle_systems']} "
                f"datums={','.join(str(item) for item in row['particle_datums'])} "
                f"queries={row['queries']} inside_fog={row['inside_fog_particle_queries']} "
                f"overrides={row['weather_overrides']} empty_particles=1 empty_polyhedra=1 "
                f"bsp_sha={row['bsp_sha']}")
        result_lines.append(
            f"queries={len(queries)} retail_new=0 retail_poly_found=0 problems={len(problems)}")
        (OUT_DIR / "results.txt").write_text("\n".join(result_lines) + "\n")
        if problems or run.returncode != 0:
            self.fail("\n".join(problems[:40]) + "\n" + run.stderr[-4000:] + "\n" +
                      f"exit={run.returncode}")
        for row in summary:
            with self.subTest(map=row["name"], phase="ce"):
                self.assertEqual(row["resolved_particle_systems"], 0)
                self.assertEqual(row["polyhedra"], 0)
                self.assertEqual(row["weather_overrides"], 0)
                self.assertEqual(row["rain_tags"], 0)


if __name__ == "__main__":
    unittest.main()
