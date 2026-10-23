"""Run CE cluster/subcluster/portal walks against a raw Xbox BSP oracle.

The host compiles the extracted CE functions from structure_visibility.c and
structure_bsp_definitions.c. Expectations are read from the decompressed map
bytes, not from CE's relocated image. A BSPS v2 section is generated with
halo2ps2's bspconv and compared by per-cluster portal count and surface-set
cardinality.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/step7-swarm/portals"
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
VISIBILITY_SHA256 = "9f1d05ac81293ecd895986561ceea0413383a7d43e8ec6cbfe3453a211b55a25"
BSP_DEFS_SHA256 = "c15b1b1b6ab0b8c24e494e3bf3a5340eca89899ded49f900a2b544241374afee"
FNV_INIT = 14695981039346656037
FNV_PRIME = 1099511628211
FIXTURE_MAGIC = 0x54524F50
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
from halo2ps2 import bsp, bspconv, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from host_abi32 import flags, prepare, sysroot  # noqa: E402


def fnv_u32(hash_value, value):
    hash_value ^= value & 0xFFFFFFFF
    return (hash_value * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF


def hash_sorted(values):
    hash_value = fnv_u32(FNV_INIT, len(values))
    for value in sorted(values):
        hash_value = fnv_u32(hash_value, value)
    return hash_value


def extract_c_function(source, marker):
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


def read_block(image, base, at, stride, label):
    count, address, definition = struct.unpack_from("<iII", image, at)
    if definition != 0:
        raise AssertionError(f"{label} definition is {definition:#x}")
    if count < 0 or count > 0x1000000:
        raise AssertionError(f"{label} count {count}")
    if count == 0:
        return 0, 0
    offset = address - base
    extent = count * stride
    if offset < 0 or offset + extent > len(image):
        raise AssertionError(f"{label} extent leaves the BSP image")
    return count, offset


def raw_oracle(map_name):
    """Portal adjacency and cluster/leaf surface sets from raw BSP bytes."""
    map_path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    source_hash = hashlib.sha256(map_path.read_bytes()).hexdigest()
    if source_hash != MP_SOURCE_SHA256[map_name]:
        raise AssertionError(f"{map_name} source hash changed")
    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{map_name}: expected one stock MP BSP")
    location = locations[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    if len(image) != location.size or image[0x14:0x18] != b"psbs":
        raise AssertionError(f"{map_name}: BSP image is not a signed sbsp block")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 0x228 > len(image):
        raise AssertionError(f"{map_name}: structure root leaves the BSP image")

    surface_count, _surfaces_at = read_block(image, location.address, root + 0xF8, 6, "surfaces")
    cluster_count, clusters_at = read_block(image, location.address, root + 0x134, 0x68, "clusters")
    portal_count, portals_at = read_block(image, location.address, root + 0x154, 0x40, "portals")
    leaf_count, leaves_at = read_block(image, location.address, root + 0xE0, 16, "leaves")
    reference_count, references_at = read_block(
        image, location.address, root + 0xEC, 8, "surface references")
    collision_count, collision_at = read_block(
        image, location.address, root + 0xB0, 96, "collision bsp")
    if collision_count < 1:
        raise AssertionError(f"{map_name}: collision BSP is empty")
    plane_count, _planes_at = read_block(
        image, location.address, collision_at + 12, 16, "planes")

    portals = []
    for portal_index in range(portal_count):
        entry = portals_at + portal_index * 0x40
        back, front, plane = struct.unpack_from("<hhi", image, entry)
        vertex_count, _vertex_at = read_block(
            image, location.address, entry + 0x34, 12, f"portal {portal_index} vertices")
        if not -1 <= back < cluster_count or not -1 <= front < cluster_count:
            raise AssertionError(f"{map_name} portal {portal_index} cluster {back},{front}")
        if not 0 <= plane < plane_count:
            raise AssertionError(f"{map_name} portal {portal_index} plane {plane}")
        portals.append({"back": back, "front": front, "plane": plane,
                        "vertices": vertex_count})

    cluster_surfaces = []
    portal_lists = []
    legacy = 0
    mirrors = 0
    sub_refs = 0
    for cluster_index in range(cluster_count):
        entry = clusters_at + cluster_index * 0x68
        sub_count, sub_at = read_block(
            image, location.address, entry + 0x34, 0x24, f"cluster {cluster_index} subclusters")
        surfaces = set()
        for sub_index in range(sub_count):
            list_count, list_at = read_block(
                image, location.address, sub_at + sub_index * 0x24 + 0x18, 4,
                f"cluster {cluster_index} subcluster {sub_index} surfaces")
            sub_refs += list_count
            if list_count:
                values = struct.unpack_from(f"<{list_count}I", image, list_at)
                for value in values:
                    if value >= surface_count:
                        raise AssertionError(
                            f"{map_name} cluster {cluster_index} surface {value}")
                    surfaces.add(value)
        legacy_count, _legacy_at = read_block(
            image, location.address, entry + 0x44, 4, f"cluster {cluster_index} legacy")
        mirror_count, mirror_at = read_block(
            image, location.address, entry + 0x50, 0x40, f"cluster {cluster_index} mirrors")
        list_count, list_at = read_block(
            image, location.address, entry + 0x5C, 2, f"cluster {cluster_index} portals")
        legacy += legacy_count
        mirrors += mirror_count
        indices = list(struct.unpack_from(f"<{list_count}h", image, list_at)) if list_count else []
        for portal_index in indices:
            if not 0 <= portal_index < portal_count:
                raise AssertionError(
                    f"{map_name} cluster {cluster_index} portal index {portal_index}")
            ends = (portals[portal_index]["back"], portals[portal_index]["front"])
            if cluster_index not in ends:
                raise AssertionError(
                    f"{map_name} cluster {cluster_index} lists portal {portal_index} "
                    f"with ends {ends}")
        if mirror_count:
            for mirror_index in range(mirror_count):
                read_block(image, location.address, mirror_at + mirror_index * 0x40 + 0x34,
                           12, f"mirror {mirror_index} points")
        cluster_surfaces.append(surfaces)
        portal_lists.append(indices)

    leaf_hash = FNV_INIT
    leaf_emit = 0
    leaf_surfaces = set()
    for leaf_index in range(leaf_count):
        entry = leaves_at + leaf_index * 16
        cluster_index, reference_span = struct.unpack_from("<hh", image, entry + 8)
        first = struct.unpack_from("<i", image, entry + 12)[0]
        if not 0 <= cluster_index < cluster_count:
            raise AssertionError(f"{map_name} leaf {leaf_index} cluster {cluster_index}")
        if (reference_span < 0 or first < 0 or
                first > reference_count - reference_span):
            emitted = []
        else:
            emitted = []
            seen = set()
            for slot in range(reference_span):
                surface = struct.unpack_from("<I", image, references_at + (first + slot) * 8)[0]
                if surface >= surface_count:
                    raise AssertionError(f"{map_name} leaf {leaf_index} surface {surface}")
                if surface not in seen:
                    seen.add(surface)
                    emitted.append(surface)
        leaf_hash = fnv_u32(leaf_hash, leaf_index)
        leaf_hash = fnv_u32(leaf_hash, len(emitted))
        for surface in emitted:
            leaf_hash = fnv_u32(leaf_hash, surface)
            leaf_surfaces.add(surface)
        leaf_emit += len(emitted)

    union = set()
    for surfaces in cluster_surfaces:
        union |= surfaces
    unreferenced = [index for index in range(surface_count)
                    if index not in union and index not in leaf_surfaces]
    section = bspconv.parse_section(bspconv.convert_block(image, location))
    return {
        "map": map_name,
        "source_sha256": source_hash,
        "bsp_sha256": hashlib.sha256(image).hexdigest(),
        "bsp_path": location.path,
        "image": image,
        "base": location.address,
        "root": root,
        "surface_count": surface_count,
        "cluster_count": cluster_count,
        "portal_count": portal_count,
        "leaf_count": leaf_count,
        "reference_count": reference_count,
        "plane_count": plane_count,
        "cluster_surfaces": cluster_surfaces,
        "portal_lists": portal_lists,
        "portals": portals,
        "legacy": legacy,
        "mirrors": mirrors,
        "sub_refs": sub_refs,
        "union": union,
        "leaf_emit": leaf_emit,
        "leaf_fnv": leaf_hash,
        "unreferenced": unreferenced,
        "section": section,
    }


def portal_fnv(indices, portals):
    hash_value = FNV_INIT
    for index in indices:
        portal = portals[index]
        hash_value = fnv_u32(hash_value, index)
        hash_value = fnv_u32(hash_value, portal["back"])
        hash_value = fnv_u32(hash_value, portal["front"])
        hash_value = fnv_u32(hash_value, portal["plane"])
    return hash_value


def parse_host(text):
    clusters = []
    summary = None
    unref = None
    status = None
    for line in text.splitlines():
        if line.startswith("CLUSTER "):
            parts = line.split()
            row = {key: value for key, value in
                   (part.split("=", 1) for part in parts[2:])}
            row["index"] = parts[1]
            clusters.append(row)
        elif line.startswith("GLOBAL "):
            summary = {key: value for key, value in
                       (part.split("=", 1) for part in line.split()[1:])}
        elif line.startswith("UNREF "):
            unref = line.split("indices=", 1)[1]
        elif line.startswith("STATUS "):
            status = line
    return clusters, summary, unref, status


class MultiplayerPortalVisibilityTest(unittest.TestCase):
    results = []

    @classmethod
    def setUpClass(cls):
        visibility = (HCU / "source/structures/structure_visibility.c").read_bytes()
        definitions = (HCU / "source/structures/structure_bsp_definitions.c").read_bytes()
        if hashlib.sha256(visibility).hexdigest() != VISIBILITY_SHA256:
            raise AssertionError("structure_visibility.c hash changed")
        if hashlib.sha256(definitions).hexdigest() != BSP_DEFS_SHA256:
            raise AssertionError("structure_bsp_definitions.c hash changed")
        visibility_text = visibility.decode("utf-8")
        definition_text = definitions.decode("utf-8")
        markers = (
            (visibility_text, "static short bounding_rectangles_intersect("),
            (visibility_text, "static long planes_intersect_rectangle("),
            (visibility_text, "static void grow_clipping_rectangle_by_portal_hull("),
            (visibility_text, "static short portal_hull_from_portal("),
            (visibility_text, "static void structure_visibility_traverse_subclusters("),
            (visibility_text, "static void structure_visibility_traverse_surface_lists("),
            (visibility_text, "static short structure_visibility_build_surfaces_traverse_clusters("),
            (visibility_text, "static short structure_visibility_build_surfaces_traverse_leaf("),
            (visibility_text, "static void structure_visibility_traverse_cluster("),
            (definition_text, "boolean structure_bsp_port_verify("),
            (definition_text, "unsigned long *structure_bsp_get_cluster_pvs("),
            (visibility_text, "boolean structure_visibility_find_mirror("),
        )
        bodies = "\n\n".join(extract_c_function(source, marker) for source, marker in markers)
        if "collision_user" in bodies:
            raise AssertionError("extracted visibility functions reference the collision user")
        OUT.mkdir(parents=True, exist_ok=True)
        template = (ROOT / "tests/hcu_mp_portal_visibility_host.c").read_text()
        tu = OUT / "portal_visibility_tu.c"
        tu.write_text(template.replace("/* CE_PORTAL_VISIBILITY_FUNCTIONS */", bodies))
        if not (sysroot() / "usr/lib32/ld-linux.so.2").exists():
            prepare()
        cls.executable = OUT / "portal-visibility"
        command = [os.environ.get("CC", "gcc"), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                   "-Wno-unused-parameter", *flags(), str(tu), "-lm", "-o", str(cls.executable)]
        compiled = subprocess.run(command, capture_output=True, text=True)
        if compiled.returncode != 0:
            raise AssertionError(compiled.stdout + compiled.stderr)
        cls.log_path = OUT / "portal-visibility.log"
        cls.log_path.write_text("")
        cls.results = []

    def test_ce_portal_and_surface_walks_match_raw_bsp(self):
        for map_name in MP_MAPS:
            with self.subTest(map=map_name):
                raw = raw_oracle(map_name)
                fixture = OUT / f"{map_name}.fixture"
                fixture.write_bytes(struct.pack(
                    "<4I", FIXTURE_MAGIC, raw["base"], raw["root"], len(raw["image"])) + raw["image"])
                before = hashlib.sha256((ROOT / "build/retail-maps/decompressed" /
                                         f"{map_name}.map").read_bytes()).hexdigest()
                run = subprocess.run([str(self.executable), str(fixture)],
                                     capture_output=True, text=True)
                after = hashlib.sha256((ROOT / "build/retail-maps/decompressed" /
                                        f"{map_name}.map").read_bytes()).hexdigest()
                with self.log_path.open("a") as log:
                    log.write(f"===== {map_name} =====\n")
                    log.write(run.stdout)
                    if run.stderr:
                        log.write(run.stderr)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertEqual(before, after)
                self.assertEqual(before, MP_SOURCE_SHA256[map_name])
                clusters, summary, unref, status = parse_host(run.stdout)
                self.assertEqual(status, "STATUS passed")
                self.assertEqual(len(clusters), raw["cluster_count"])
                for cluster_index, row in enumerate(clusters):
                    surfaces = raw["cluster_surfaces"][cluster_index]
                    portals = raw["portal_lists"][cluster_index]
                    self.assertEqual(int(row["sub"]), len(surfaces))
                    self.assertEqual(int(row["sfnv"], 16), hash_sorted(surfaces))
                    self.assertEqual(int(row["ports"]), len(portals))
                    self.assertEqual(int(row["pfnv"], 16), portal_fnv(portals, raw["portals"]))
                self.assertEqual(int(summary["clusters"]), raw["cluster_count"])
                self.assertEqual(int(summary["surfaces"]), raw["surface_count"])
                self.assertEqual(int(summary["portals"]), raw["portal_count"])
                self.assertEqual(int(summary["leaves"]), raw["leaf_count"])
                self.assertEqual(int(summary["refs"]), raw["reference_count"])
                self.assertEqual(int(summary["sub_unique"]), len(raw["union"]))
                self.assertEqual(int(summary["sub_fnv"], 16), hash_sorted(raw["union"]))
                self.assertEqual(int(summary["leaf_emit"]), raw["leaf_emit"])
                self.assertEqual(int(summary["leaf_fnv"], 16), raw["leaf_fnv"])
                self.assertEqual(summary["bytes_same"], "1")
                self.assertEqual(summary["depth"], "0")
                self.assertEqual(summary["oob_get"], "0")
                self.assertEqual(summary["plane_fail"], "0")
                self.assertEqual(int(summary["plane_ok"]), raw["portal_count"])
                self.assertEqual(summary["mirrors"], "0")
                self.assertEqual(summary["mirror_found"], "0")
                self.assertEqual(summary["legacy"], "0")
                self.assertEqual(summary["list_added"], "0")
                self.assertEqual(raw["legacy"], 0)
                self.assertEqual(raw["mirrors"], 0)
                got_unref = [] if unref == "-" else [int(part) for part in unref.split(",")]
                self.assertEqual(got_unref, raw["unreferenced"])

                section = raw["section"]
                self.assertEqual(len(section.clusters), raw["cluster_count"])
                self.assertEqual(len(section.portals), raw["portal_count"])
                self.assertEqual(section.triangles, raw["surface_count"] - len(raw["unreferenced"]))
                for cluster_index, cluster in enumerate(section.clusters):
                    pack_portals = section.cluster_portals[
                        cluster["first_portal"]:cluster["first_portal"] + cluster["portal_count"]]
                    self.assertEqual(cluster["triangles"], len(raw["cluster_surfaces"][cluster_index]))
                    self.assertEqual(cluster["portal_count"], len(raw["portal_lists"][cluster_index]))
                    self.assertEqual(sorted(pack_portals), sorted(raw["portal_lists"][cluster_index]))
                for portal_index, portal in enumerate(section.portals):
                    raw_portal = raw["portals"][portal_index]
                    front = raw_portal["front"] if raw_portal["front"] >= 0 else 0xFFFF
                    back = raw_portal["back"] if raw_portal["back"] >= 0 else 0xFFFF
                    self.assertEqual(portal["a"], front)
                    self.assertEqual(portal["b"], back)

                record = {
                    "map": map_name,
                    "clusters": raw["cluster_count"],
                    "surfaces": raw["surface_count"],
                    "sub_refs": raw["sub_refs"],
                    "sub_unique": len(raw["union"]),
                    "portals": raw["portal_count"],
                    "portals_empty": raw["portal_count"] == 0,
                    "leaves": raw["leaf_count"],
                    "leaf_emit": raw["leaf_emit"],
                    "mirrors": raw["mirrors"],
                    "legacy": raw["legacy"],
                    "unreferenced": raw["unreferenced"],
                    "plane_ok": int(summary["plane_ok"]),
                    "traverse_plane_checks": int(summary["traverse_plane_checks"]),
                    "bsps_triangles": section.triangles,
                    "bsps_portals": len(section.portals),
                    "bytes_same": 1,
                    "collision_user_depth": 0,
                }
                self.results.append(record)
                if raw["portal_count"] == 0:
                    self.assertTrue(all(len(indices) == 0 for indices in raw["portal_lists"]))
                    self.assertEqual(len(section.portals), 0)

    @classmethod
    def tearDownClass(cls):
        if cls.results:
            (OUT / "results.json").write_text(json.dumps(cls.results, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
