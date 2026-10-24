"""Host-sized semantic coverage of stock MP maps, separate from EE proof."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
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
MP_FOG_PLANE_MAPS = {"beavercreek", "chillout", "damnation"}
MP_FOG_NONE_MAPS = {
    "bloodgulch", "boardingaction", "carousel", "hangemhigh", "longest",
    "prisoner", "putput", "ratrace", "sidewinder", "wizard",
}
SCHEMA_ELF_SHA256 = "2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa"
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
MP_PACKAGE_SHA256 = {
    "beavercreek": "4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc",
    "bloodgulch": "ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011",
    "boardingaction": "2c12e7c0cf555698b837397666b1f343a6864fe16deeffb0b0d4a007e869acd0",
    "carousel": "e24191ed1e660dfb3c9c9bcd88abcff61c366690f6d903f3b0622eb2c2e751b4",
    "chillout": "727abc7401a530892f1136f082a6254544915e0d85f2a068f63d9530189b1bf0",
    "damnation": "ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d",
    "hangemhigh": "1e2a4df7a5ba17d0742bd30484fcfe63db011e6c47a87ac0f2d06ac6f5cab58f",
    "longest": "6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b",
    "prisoner": "3bb10f06c785da93fe0f7257be9f06519b7ccb6c155801a7a04a5e6d56352136",
    "putput": "6d66e4ecf9c51b3ae417d85356de9ff66c14bc9fc19dd4a2bd2a2954f6b4f3bd",
    "ratrace": "a735d4a5bef86cc7277ae888a1ef9da25f28f0ab6e45dff010da53dc41e685da",
    "sidewinder": "968ab65ea7ae6fbd15925ed28eb0f8eafc267c78f53150b59b4cc1dea2d017f5",
    "wizard": "00bf468d4d8c96e234ef21e5bfb59b410cac7c3e8c9f4f848ea20fbfacf01c57",
}
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from host_abi32 import flags
from halo2ps2 import bsp, mapinfo, tagindex
from ctag_schema_walk import read_xbox_tag_region
from test_hcu_scenario_bsp_switch import (
    retail_source_collision_goldens, write_collision_golden_header,
    retail_source_player_pvs_oracle, write_player_pvs_golden_header,
    retail_source_pvs_pair_oracle,
    retail_source_sound_environment_oracle,
    write_sound_pas_golden_header,
    retail_source_fog_plane_oracle,
    retail_source_fog_none_oracle,
    write_fog_plane_golden_header,
)
from test_hcu_wind_consumer import _expected_vectors, _c_float


def retail_source_weather_wind_oracle(map_path):
    """Read source-BSP palette, cluster selectors, and referenced wind tags."""
    index = tagindex.TagIndex.read(map_path)
    tag_region, tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, tag_region,
                           mapinfo.read_header(map_path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"expected one stock-MP BSP in {map_path.name}, got {len(locations)}")
    location = locations[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    if len(image) != location.size:
        raise AssertionError(f"truncated BSP image: {map_path.name}")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError(f"BSP root outside image: {map_path.name}")
    palette_count, palette_address = struct.unpack_from("<iI", image, root + 436)
    palette_offset = palette_address - location.address if palette_address else 0
    if (palette_count < 0 or palette_count > 32 or
            (palette_count and (palette_offset < 0 or
             palette_offset + palette_count * 0xF0 > len(image)))):
        raise AssertionError(f"invalid weather palette extent: {map_path.name}")
    tag_by_datum = {entry.tag_id: entry for entry in index.entries}
    palette = []
    for palette_index in range(palette_count):
        offset = palette_offset + palette_index * 0xF0
        group_raw = image[offset + 0x80:offset + 0x84]
        datum = struct.unpack_from("<I", image, offset + 0x8C)[0]
        direction = struct.unpack_from("<3f", image, offset + 0x90)
        magnitude = struct.unpack_from("<f", image, offset + 0x9C)[0]
        if group_raw != b"dniw":
            raise AssertionError(f"unexpected raw weather reference group {group_raw!r}")
        if datum == 0xFFFFFFFF:
            definition = (0.0,) * 7
            tag_path = None
        else:
            tag = tag_by_datum.get(datum)
            if tag is None or tag.group != "wind":
                raise AssertionError(f"palette datum {datum:#010x} is not a wind tag")
            tag_offset = tag.data_address - tag_base
            if tag_offset < 0 or tag_offset + 0x40 > len(tag_region):
                raise AssertionError(f"wind definition leaves tag region: {tag.path}")
            definition = struct.unpack_from("<7f", tag_region, tag_offset)
            tag_path = tag.path
        palette.append({"datum": datum, "direction": direction,
                        "magnitude": magnitude, "definition": definition,
                        "tag_path": tag_path})
    cluster_count, cluster_address = struct.unpack_from("<iI", image, root + 308)
    cluster_offset = cluster_address - location.address if cluster_address else 0
    if (cluster_count < 0 or cluster_offset < 0 or
            cluster_offset + cluster_count * 0x68 > len(image)):
        raise AssertionError(f"invalid cluster extent: {map_path.name}")
    refs = [struct.unpack_from("<h", image, cluster_offset + i * 0x68 + 8)[0]
            for i in range(cluster_count)]
    if any(value != -1 and not 0 <= value < palette_count for value in refs):
        raise AssertionError(f"invalid cluster weather index in {map_path.name}: {refs}")
    return {"map": map_path.stem, "bsp_path": location.path,
            "raw_bsp_sha256": hashlib.sha256(image).hexdigest(),
            "palette": palette, "cluster_weather_indices": refs}


def retail_source_fogged_sound_environment_oracle(map_path):
    """Derive CE's sound selector for a raw, valid fog-plane cluster.

    This deliberately admits only the three audited MP fog-plane maps and
    requires their referenced fog definitions to have no sound-environment
    override. That lets the CE source's actual priority ordering fall through
    to the cluster palette, while still exercising position-dependent fog
    selection with a point derived from the raw plane equation.
    """
    from test_hcu_scenario_bsp_switch import retail_source_fog_plane_oracle

    map_path = Path(map_path)
    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    tag_region, tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, tag_region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError("fogged selector expects one stock-MP BSP")
    fog_rows = retail_source_fog_plane_oracle(map_path, 1)
    if len(fog_rows) != 1:
        raise AssertionError("expected one valid raw fog-plane/region chain")
    fog_row = fog_rows[0]
    location = locations[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    if len(image) != location.size:
        raise AssertionError("truncated raw BSP")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError("raw BSP root leaves image")

    def block(offset, stride, label):
        count, address = struct.unpack_from("<iI", image, root + offset)
        target = address - location.address if address else 0
        if count < 0 or (count and (target < 0 or
                                    target + count * stride > len(image))):
            raise AssertionError(f"invalid {label} block")
        return count, target

    cluster_count, clusters = block(308, 0x68, "cluster")
    background_count, backgrounds = block(508, 0x74, "background palette")
    environment_count, environments = block(520, 0x50, "environment palette")
    cluster_index = fog_row["cluster_index"]
    if not 0 <= cluster_index < cluster_count:
        raise AssertionError("fog-plane cluster is outside cluster block")
    cluster = clusters + cluster_index * 0x68
    fog_reference, background_index, environment_index = struct.unpack_from(
        "<hhh", image, cluster + 2)
    if fog_reference != fog_row["reference"]:
        raise AssertionError("cluster fog reference differs from fog oracle")

    tags_by_id = {entry.tag_id: entry for entry in index.entries}
    fog_tag = tags_by_id.get(fog_row["fog_datum"] & 0xFFFFFFFF)
    if not fog_tag or fog_tag.group != "fog ":
        raise AssertionError("fog-plane palette datum is not an in-map fog tag")
    fog_offset = fog_tag.data_address - tag_base
    if fog_offset < 0 or fog_offset + 0x114 > len(tag_region):
        raise AssertionError("fog definition leaves source tag region")
    fog_data = tag_region[fog_offset:fog_offset + 0x114]
    fog_environment_datum = struct.unpack_from("<i", fog_data, 0x110)[0]
    if fog_environment_datum != -1:
        raise AssertionError("fog sound-environment override needs priority arbitration")

    if not 0 <= environment_index < environment_count:
        raise AssertionError("fog-plane cluster lacks environment palette entry")
    environment_datum = struct.unpack_from(
        "<i", image, environments + environment_index * 0x50 + 0x2C)[0]
    environment_tag = tags_by_id.get(environment_datum & 0xFFFFFFFF)
    if not environment_tag or environment_tag.group != "snde":
        raise AssertionError("cluster palette reference is not a sound-environment tag")
    environment_offset = environment_tag.data_address - tag_base
    if environment_offset < 0 or environment_offset + 0x48 > len(tag_region):
        raise AssertionError("sound-environment definition leaves tag region")
    priority = struct.unpack_from("<h", tag_region, environment_offset + 4)[0]
    if priority <= -32768:
        raise AssertionError("cluster sound environment cannot beat CE initial priority")

    background_datum = -1
    if 0 <= background_index < background_count:
        background_datum = struct.unpack_from(
            "<i", image, backgrounds + background_index * 0x74 + 0x2C)[0]

    # CE evaluates distance(n, p) + plane_distance < 0. These fog definitions
    # are non-water (flag bit 0 clear), so plane_distance is not applied.
    normal = fog_row["plane"]
    norm_squared = sum(component * component for component in normal[:3])
    if norm_squared <= 0.0:
        raise AssertionError("fog-plane normal is degenerate")
    scale = (abs(normal[3]) + 1000.0) / norm_squared
    position = tuple(-normal[axis] * scale for axis in range(3))
    if sum(normal[axis] * position[axis] for axis in range(3)) + normal[3] >= 0:
        raise AssertionError("derived point is not on the CE fog-region side")
    return {
        "bsp_index": 0,
        "cluster_index": cluster_index,
        "fog_region": fog_row["region_index"],
        "fog_datum": fog_row["fog_datum"],
        "fog_environment_datum": fog_environment_datum,
        "palette_index": environment_index,
        "environment_tag": environment_datum,
        "environment_priority": priority,
        "background_tag": background_datum,
        "position": position,
        "plane": normal,
        "source_bsp_sha256": hashlib.sha256(image).hexdigest(),
    }


def write_mp_weather_wind_golden(path, map_id_by_name, raw_by_name):
    """Emit source-bound palette/tag/vector and per-cluster selector rows."""
    palette_rows = []
    cluster_rows = []
    for name in MP_MAPS:
        map_id = map_id_by_name[name]
        raw = raw_by_name[name]
        expected = _expected_vectors(raw, 0x13579BDF, 0x89ABCDEF)
        for palette_index, entry in enumerate(raw["palette"]):
            vectors = expected.get((palette_index, "normal"), (0.0, 0.0, 0.0))
            simple = expected.get((palette_index, "simple"), (0.0, 0.0, 0.0))
            damped = expected.get((palette_index, "damped"), (0.0, 0.0, 0.0))
            palette_rows.append((map_id, palette_index, entry, vectors, simple, damped))
        cluster_rows.extend((map_id, cluster, weather_index)
                            for cluster, weather_index in enumerate(
                                raw["cluster_weather_indices"]))
    lines = [
        "typedef struct hcu_mp_weather_wind_palette_golden {",
        "    unsigned map_id, palette_index, datum;",
        "    float direction[3], magnitude, definition[7];",
        "    float normal[3], simple[3], damped[3];",
        "} hcu_mp_weather_wind_palette_golden;",
        "static const hcu_mp_weather_wind_palette_golden hcu_mp_weather_wind_palette[] = {",
    ]
    def floats(values):
        return "{ " + ", ".join(_c_float(float(value)) for value in values) + " }"
    for map_id, palette_index, entry, normal, simple, damped in palette_rows:
        lines.append("    {%du, %du, 0x%08Xu, %s, %s, %s, %s, %s, %s}," % (
            map_id, palette_index, entry["datum"], floats(entry["direction"]),
            _c_float(entry["magnitude"]), floats(entry["definition"]),
            floats(normal), floats(simple), floats(damped)))
    lines += [
        "};",
        "#define HCU_MP_WEATHER_WIND_PALETTE_GOLDEN_COUNT %du" % len(palette_rows),
        "typedef struct hcu_mp_weather_wind_cluster_golden {",
        "    unsigned map_id, cluster_index; int weather_palette_index;",
        "} hcu_mp_weather_wind_cluster_golden;",
        "static const hcu_mp_weather_wind_cluster_golden hcu_mp_weather_wind_clusters[] = {",
    ]
    lines.extend("    {%du, %du, %d}," % row for row in cluster_rows)
    lines += [
        "};",
        "#define HCU_MP_WEATHER_WIND_CLUSTER_GOLDEN_COUNT %du" % len(cluster_rows),
        "",
    ]
    path.write_text("\n".join(lines))
    return {"palette_rows": len(palette_rows), "cluster_rows": len(cluster_rows)}


class MultiplayerHostCollisionMatrix(unittest.TestCase):
    def test_host_sized_13_map_lifecycle_and_collision(self):
        packages = {
            "longest": ROOT / "build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2",
            "bloodgulch": ROOT / "build/retail-maps/bloodgulch-with-bsps.hp2",
            "beavercreek": ROOT / "build/m2-mp-extra/beavercreek-all-bsps.hp2",
            "prisoner": ROOT / "build/m2-mp-extra/prisoner-all-bsps.hp2",
            "boardingaction": ROOT / "build/m2-mp-all-map-packages/boardingaction-all-bsps.hp2",
            "carousel": ROOT / "build/m2-mp-all-map-packages/carousel-all-bsps.hp2",
            "chillout": ROOT / "build/m2-mp-all-map-packages/chillout-all-bsps.hp2",
            "damnation": ROOT / "build/m2-mp-extra/damnation-wind-all-bsps.hp2",
            "hangemhigh": ROOT / "build/m2-mp-all-map-packages/hangemhigh-all-bsps.hp2",
            "putput": ROOT / "build/m2-mp-all-map-packages/putput-all-bsps.hp2",
            "ratrace": ROOT / "build/m2-mp-all-map-packages/ratrace-all-bsps.hp2",
            "sidewinder": ROOT / "build/m2-mp-all-map-packages/sidewinder-all-bsps.hp2",
            "wizard": ROOT / "build/m2-mp-all-map-packages/wizard-all-bsps.hp2",
        }
        expected_order = (
            "longest", "bloodgulch", "beavercreek", "prisoner", "boardingaction",
            "carousel", "chillout", "damnation", "hangemhigh",
            "putput", "ratrace", "sidewinder", "wizard")
        self.assertEqual(tuple(packages), expected_order)
        self.assertEqual(set(MP_MAPS), set(packages))
        map_id_by_name = {name: 101 + i for i, name in enumerate(packages)}
        schema_elf = ROOT / "build/m2-artifacts/schema-2fba411b-prior/halo-local.elf"
        self.assertTrue(schema_elf.is_file(), f"missing audited schema ELF {schema_elf}")
        self.assertEqual(hashlib.sha256(schema_elf.read_bytes()).hexdigest(),
                         SCHEMA_ELF_SHA256, "schema ELF changed; re-audit package conversions")
        damnation_record_path = ROOT / "build/m2-mp-wind-package/manifest.json"
        self.assertTrue(damnation_record_path.is_file(),
                        f"missing audited Damnation package record {damnation_record_path}")
        damnation_record = json.loads(damnation_record_path.read_text())
        # Manifests produced by the current fixture use source_map_sha256;
        # accept the former spelling for retained historical artifacts.
        source_map_hash = damnation_record.get(
            "source_map_sha256", damnation_record.get("map_source_sha256"))
        self.assertEqual(source_map_hash,
                         MP_SOURCE_SHA256["damnation"])
        self.assertEqual(damnation_record["schema_elf_sha256"], SCHEMA_ELF_SHA256)
        self.assertEqual(damnation_record["package_sha256"],
                         MP_PACKAGE_SHA256["damnation"])
        for name, package in packages.items():
            self.assertTrue(package.is_file(), f"missing audited MP package {package}")
            self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(),
                             MP_PACKAGE_SHA256[name],
                             f"unverified package hash for {name}; re-audit instead of skipping")
            source_map = ROOT / f"build/retail-maps/decompressed/{name}.map"
            self.assertTrue(source_map.is_file(), f"missing MP source map {source_map}")
            self.assertEqual(hashlib.sha256(source_map.read_bytes()).hexdigest(),
                             MP_SOURCE_SHA256[name],
                             f"unverified source-map hash for {name}")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            # Reuse semantic shims with their explicitly host-sized 16/8 MiB
            # tag/BSP arrays. These capacities let collision behavior run across
            # the full set; they are not PS2/EE RAM placement or capacity evidence.
            common = (ROOT / "tests/hcu_scenario_bsp_switch_main.c").read_text()
            old = "retail_section_scratch_bytes[131072]"
            self.assertEqual(common.count(old), 1, old)
            common = common.replace(old, "retail_section_scratch_bytes[524288]")
            common = common.replace('"../submodules/', '"' + str(ROOT / "submodules") + "/")
            (temp / "hcu_scenario_bsp_switch_main.c").write_text(common)
            lifecycle = (ROOT / "tests/hcu_ce_map_lifecycle_main.c").read_text()
            lifecycle = lifecycle.replace("int main(int argc, char **argv)",
                                          "int unused_lifecycle_main(int argc, char **argv)")
            (temp / "hcu_mp_lifecycle_generated.h").write_text(lifecycle)
            # Permit the thirteen stock MP maps only in this generated host
            # diagnostic; production map admission remains UI-only.
            map_service = (ROOT / "src/stream/hcu_map_service.c").read_text()
            old_mp_gate = '\t\tstrcmp(entry->identity.map_name, "beavercreek") != 0) {'
            new_mp_gate = '\t\tstrcmp(entry->identity.map_name, "beavercreek") != 0'
            for name in MP_MAPS:
                if name not in ("longest", "bloodgulch", "beavercreek"):
                    new_mp_gate += f' &&\n\t\tstrcmp(entry->identity.map_name, "{name}") != 0'
            new_mp_gate += ') {'
            self.assertEqual(map_service.count(old_mp_gate), 1)
            map_service = map_service.replace(old_mp_gate, new_mp_gate)
            (temp / "hcu_map_service_host.c").write_text(map_service)
            collision_goldens_by_map = {
                name: retail_source_collision_goldens(
                    ROOT / f"build/retail-maps/decompressed/{name}.map", 1,
                    include_prisoner_directional=name == "prisoner",
                    include_prisoner_breakable=name == "prisoner")
                for name in packages
            }
            write_collision_golden_header(temp / "hcu_collision_golden.h", [
                (map_id_by_name[name], collision_goldens_by_map[name])
                for name in packages
            ])
            location_inventory = {
                "scope": "raw-source BSP3D inside start and outside endpoint; CE location APIs",
                "maps": {name: {
                    "map_id": map_id_by_name[name],
                    "source_map_sha256": MP_SOURCE_SHA256[name],
                    "package_sha256": MP_PACKAGE_SHA256[name],
                    "cases": [{
                        "bsp_index": row["bsp_index"],
                        "start": row["start"],
                        "expected_start_leaf": row["leaf_index"],
                        "expected_start_cluster": row["cluster_index"],
                        "outside_endpoint": [
                            row["start"][axis] + row["vector"][axis]
                            for axis in range(3)],
                        "expected_outside_leaf": -1,
                    } for row in collision_goldens_by_map[name]],
                } for name in packages},
            }
            (temp / "mp_location_source_inventory.json").write_text(
                json.dumps(location_inventory, indent=2, sort_keys=True) + "\n")
            # Longest has no usable PVS extent for player aggregation. Blood
            # Gulch does, so qualify the real CE player iterator/root refresh
            # there instead of pretending the one-cluster map covers it.
            write_player_pvs_golden_header(temp / "hcu_player_pvs_golden.h", [
                (102, retail_source_player_pvs_oracle(
                    ROOT / "build/retail-maps/decompressed/bloodgulch.map", 1))
            ])
            fog_plane_by_map = {
                name: retail_source_fog_plane_oracle(
                    ROOT / f"build/retail-maps/decompressed/{name}.map", 1)
                for name in packages
            }
            fog_none_by_map = {
                name: retail_source_fog_none_oracle(
                    ROOT / f"build/retail-maps/decompressed/{name}.map", 1)
                for name in packages
            }
            self.assertEqual({name for name, rows in fog_plane_by_map.items() if rows},
                             MP_FOG_PLANE_MAPS)
            self.assertEqual({name for name, rows in fog_none_by_map.items() if rows},
                             MP_FOG_NONE_MAPS)
            write_fog_plane_golden_header(
                temp / "hcu_fog_plane_golden.h",
                [(map_id_by_name[name], fog_plane_by_map[name])
                 for name in packages],
                none_rows=[(map_id_by_name[name], fog_none_by_map[name])
                           for name in packages])
            fog_source_inventory = {
                "scope": "13 source-hash-pinned stock MP BSPs",
                "valid_plane_maps": sorted(MP_FOG_PLANE_MAPS),
                "none_reference_maps": sorted(MP_FOG_NONE_MAPS),
                "maps": {name: {
                    "map_id": map_id_by_name[name],
                    "source_map_sha256": MP_SOURCE_SHA256[name],
                    "valid_fog_plane_cases": fog_plane_by_map[name],
                    "fog_none_cases": fog_none_by_map[name],
                } for name in packages},
            }
            (temp / "mp_fog_source_inventory.json").write_text(
                json.dumps(fog_source_inventory, indent=2, sort_keys=True) + "\n")
            # Bind CE's real sound-obstruction consumer to an independently
            # selected reachable-but-PVS-hidden raw Blood Gulch pair.
            bloodgulch_source = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
            pvs_sound_oracle = retail_source_pvs_pair_oracle(bloodgulch_source, 1)[0]
            hidden_pair = pvs_sound_oracle["hidden_reachable"]
            self.assertIsNotNone(hidden_pair,
                                 "Blood Gulch needs a reachable hidden sound pair")
            from_cluster, to_cluster, encoded_distance = hidden_pair
            obstruction_distance = 80.0
            cluster_distance = (encoded_distance & 0x7F) * (256.0 / 127.0)
            expected_occlusion = max(0.0, min(1.0,
                (1.0 - obstruction_distance /
                 (cluster_distance + obstruction_distance)) * 1.4))
            def c_float_literal(value):
                literal = f"{float(value):.9g}"
                if "." not in literal and "e" not in literal.lower():
                    literal += ".0"
                return literal + "f"
            (temp / "hcu_mp_sound_obstruction_golden.h").write_text("\n".join([
                "typedef struct hcu_mp_sound_obstruction_golden {",
                "    unsigned map_id, bsp_index, from_cluster, to_cluster;",
                "    unsigned encoded_distance; float distance, expected_occlusion;",
                "} hcu_mp_sound_obstruction_golden;",
                "static const hcu_mp_sound_obstruction_golden",
                "hcu_mp_sound_obstruction_goldens[] = {",
                f"    {{102u, 0u, {from_cluster}u, {to_cluster}u, "
                f"{encoded_distance}u, {c_float_literal(obstruction_distance)}, "
                f"{c_float_literal(expected_occlusion)}}},",
                "};",
                "#define HCU_MP_SOUND_OBSTRUCTION_GOLDEN_COUNT 1u",
                "",
            ]))
            sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
            from halo2ps2 import bsp, mapinfo, tagindex
            from ctag_schema_walk import read_xbox_tag_region
            catalog_text = (ROOT / "src/stream/hcu_map_catalog.c").read_text()
            sound_environment_source_inventory = {}
            for name in MP_MAPS:
                source_map = ROOT / f"build/retail-maps/decompressed/{name}.map"
                self.assertTrue(source_map.is_file(), f"missing MP source map {source_map}")
                self.assertIn(f'"{name}"', catalog_text)
                self.assertIn(f'maps/{name}.map', catalog_text)
                header = mapinfo.read_header(source_map)
                tag_region, _, _ = read_xbox_tag_region(source_map)
                locations = bsp.locate(tagindex.TagIndex.read(source_map), tag_region,
                                       header.decompressed_size)
                oracle = retail_source_sound_environment_oracle(
                    source_map, len(locations))
                sound_environment_source_inventory[name] = {
                    "source_map_sha256": hashlib.sha256(
                        source_map.read_bytes()).hexdigest(),
                    "bsp_count": len(locations),
                    "fog_free_selector_candidates": [oracle[index]
                        for index in sorted(oracle)],
                }
            self.assertEqual(set(sound_environment_source_inventory), set(MP_MAPS))
            candidate_map_names = {name for name, row in
                sound_environment_source_inventory.items()
                if row["fog_free_selector_candidates"]}
            self.assertEqual(candidate_map_names,
                             set(MP_MAPS) - {
                                 "beavercreek", "chillout", "damnation"})
            sound_environment_goldens = []
            fogged_sound_environment_inventory = {}
            for i, name in enumerate(packages):
                source_map = ROOT / f"build/retail-maps/decompressed/{name}.map"
                oracle = retail_source_sound_environment_oracle(source_map, 1)
                if name in MP_FOG_PLANE_MAPS:
                    self.assertFalse(oracle,
                        f"{name}: fog-plane selector must use explicit side case")
                    row = retail_source_fogged_sound_environment_oracle(source_map)
                    fogged_sound_environment_inventory[name] = row
                    sound_environment_goldens.append((
                        101 + i, row["bsp_index"], row["cluster_index"],
                        row["palette_index"], row["environment_tag"],
                        row["background_tag"], row["fog_region"],
                        row["environment_priority"], *row["position"]))
                else:
                    self.assertEqual(set(oracle), {0},
                                     f"{name} has at most one BSP palette candidate")
                    row = oracle[0]
                    sound_environment_goldens.append((
                        101 + i, row["bsp_index"], row["cluster_index"],
                        row["palette_index"], row["environment_tag"],
                        row["background_tag"], -1, 0,
                        1.25, 2.5, 3.75))
            sound_header = [
                "typedef struct hcu_mp_sound_environment_golden {",
                "\tunsigned map_id, bsp_index, cluster_index;",
                "\tint palette_index; long environment_tag, background_tag;",
                "\tint fog_region, environment_priority; float position[3];",
                "} hcu_mp_sound_environment_golden;",
                "static const hcu_mp_sound_environment_golden",
                "hcu_mp_sound_environment_goldens[] = {",
            ]
            sound_header.extend("\t{%du, %du, %du, %d, %dL, %dL, %d, %d, {%s}}," % (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7],
                ", ".join(_c_float(value) for value in row[8:11]))
                for row in sound_environment_goldens)
            sound_header += [
                "};",
                "#define HCU_MP_SOUND_ENVIRONMENT_GOLDEN_COUNT "
                f"{len(sound_environment_goldens)}u",
                "",
            ]
            (temp / "hcu_mp_sound_environment_golden.h").write_text(
                "\n".join(sound_header))
            inventory = {
                "scope": "13 stock multiplayer maps only; campaign maps excluded",
                "maps": sound_environment_source_inventory,
                "fogged_selector_cases": fogged_sound_environment_inventory,
            }
            (temp / "mp_sound_environment_source_inventory.json").write_text(
                json.dumps(inventory, indent=2, sort_keys=True) + "\n")
            write_sound_pas_golden_header(temp / "hcu_sound_pas_golden.h", [])
            pvs_lines = []
            for i, name in enumerate(packages):
                source = ROOT / f"build/retail-maps/decompressed/{name}.map"
                header = mapinfo.read_header(source)
                region, _, _ = read_xbox_tag_region(source)
                location = bsp.locate(tagindex.TagIndex.read(source), region,
                                      header.decompressed_size)[0]
                with source.open("rb") as stream:
                    stream.seek(location.file_offset)
                    image = stream.read(location.size)
                root = struct.unpack_from("<I", image, 0)[0] - location.address
                clusters = struct.unpack_from("<I", image, root + 308)[0]
                words = (clusters + 31) // 32
                pvs = struct.unpack_from("<I", image, root + 332)[0] - location.address
                data = struct.unpack_from("<" + "I" * (clusters * words), image, pvs)
                pvs_lines.append(f"static const unsigned long mp_pvs_{i}[] = {{" +
                                 ",".join(f"0x{x:08x}UL" for x in data) + "};")
                pvs_lines.append(f"#define MP_CLUSTERS_{i} {clusters}u")
            (temp / "hcu_mp_pvs_golden.h").write_text("\n".join(pvs_lines) + "\n")
            weather_wind_raw = {
                name: retail_source_weather_wind_oracle(
                    ROOT / f"build/retail-maps/decompressed/{name}.map")
                for name in MP_MAPS
            }
            self.assertEqual(set(weather_wind_raw), set(MP_MAPS))
            for name, raw in weather_wind_raw.items():
                self.assertEqual(hashlib.sha256(
                    (ROOT / f"build/retail-maps/decompressed/{name}.map").read_bytes()
                ).hexdigest(), MP_SOURCE_SHA256[name])
                self.assertTrue(raw["palette"], f"{name} must have a weather palette")
                self.assertTrue(raw["cluster_weather_indices"],
                                f"{name} must have clusters")
            weather_wind_golden_counts = write_mp_weather_wind_golden(
                temp / "hcu_mp_weather_wind_golden.h", map_id_by_name,
                weather_wind_raw)
            weather_wind_inventory = {
                "scope": "13 stock multiplayer maps; all 13 have one BSP",
                "kind": "source-derived weather palette, wind tag, and cluster refs",
                "maps": {name: {
                    "map_id": map_id_by_name[name],
                    "source_map_sha256": MP_SOURCE_SHA256[name],
                    "raw_bsp_sha256": raw["raw_bsp_sha256"],
                    "bsp_path": raw["bsp_path"],
                    "palette": raw["palette"],
                    "cluster_weather_indices": raw["cluster_weather_indices"],
                } for name, raw in weather_wind_raw.items()},
                "golden_counts": weather_wind_golden_counts,
            }
            (temp / "mp_weather_wind_source_inventory.json").write_text(
                json.dumps(weather_wind_inventory, indent=2, sort_keys=True) + "\n")
            semantics = temp / "halo_ps2_msvc_semantics.h"
            subprocess.run([sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                            "--output", str(semantics), "--all-inlines", "--tags", str(HCU / "source"),
                            "--inlines", str(HCU / "source"), "--inlines", str(HCU / "port/include/xdk")],
                           check=True, capture_output=True, text=True)
            includes = [temp, ROOT / "tests", ROOT / "tests/hcu_scenario_host_shim",
                        HCU / "port/ps2/include", HCU / "port/linux/game", HCU / "port/include",
                        HCU / "source", *[HCU / "source" / d for d in (
                            "cseries", "scenario", "structures", "cache", "tag_files", "objects",
                            "physics", "game", "interface", "math", "sound", "memory", "input")],
                        ROOT / "src", ROOT / "submodules/halo-ps2/engine/src",
                        ROOT / "submodules/halo-ps2/engine/tests/hp2_world_shim", Path("/usr/include")]
            sources = [ROOT / "tests/hcu_mp_capacity_main.c",
                       ROOT / "tests/hcu_mp_weather_wind_host32.c",
                       ROOT / "tests/hcu_mp_sound_environment_host32.c",
                       ROOT / "tests/hcu_game_sound_host32.c",
                       ROOT / "tests/hcu_objects_host32.c",
                       ROOT / "tests/hcu_player_pvs_host32.c",
                       ROOT / "tests/hcu_real_math_host32.c", ROOT / "tests/hcu_bsp3d_host32.c"]
            sources.append(ROOT / "tests/hcu_geometry_source_host32.c")
            sources += [HCU / "source" / p for p in (
                "scenario/scenario.c", "scenario/wind.c", "math/random_math.c",
                "sound/sound_environment_definitions.c",
                "tag_files/tag_files.c", "memory/data.c", "math/integer_math.c", "physics/collisions.c",
                "physics/collision_bsp.c", "physics/bsp2d.c")]
            sources += [HCU / "port/ps2/src" / p for p in (
                "ps2_animation_trace.c", "ps2_cache.c", "ps2_ctag.c", "ps2_cbsp.c")]
            sources += [HCU / "port/linux/game" / f"tag_schema_{p}.c" for p in (
                "groups", "collision", "models", "objects", "render", "effects", "scenario")]
            sources += [temp / "hcu_map_service_host.c"]
            sources += [ROOT / "src/stream" / f"{p}.c" for p in (
                "hcu_map_catalog", "ctag_mount", "ctag_ps2_backend",
                "cbsp_catalog", "ctag_resource_index", "ctag_map_source", "sha256", "hmap",
                "hcu_asset_profile", "hcu_profile_mount", "hcu_profile_metadata")]
            sources += [ROOT / "submodules/halo-ps2/engine/src" / p for p in (
                "world/section.c", "stream/hp2.c", "stream/file.c", "core/mem.c")]
            # Resolve wind.c's CE spline call to the inline body included by
            # that same TU, matching the already-qualified MP wind fixture.
            wind_path = HCU / "source/scenario/wind.c"
            wind_text = wind_path.read_text().replace(
                "uniform_cubic_spline_vector3d(",
                "wind_uniform_cubic_spline_vector3d_inline(")
            generated_wind = temp / "wind_hcu_mp_matrix.c"
            generated_wind.write_text(wind_text)
            sources[sources.index(wind_path)] = generated_wind
            generated_real_math = temp / "hcu_real_math_source_host32.c"
            generated_real_math.write_text(
                "#define global_projection3d_mappings hcu_mp_projection3d_mappings\n"
                "#define fast_vector_intersects_sphere hcu_mp_fast_vector_intersects_sphere\n"
                f'#include "{ROOT / "tests/hcu_real_math_source_host32.c"}"\n')
            sources.append(ROOT / "tests/hcu_real_math_source_host32.c")
            sources[sources.index(ROOT / "tests/hcu_real_math_source_host32.c")] = generated_real_math
            for source_path, alias in (
                    (ROOT / "tests/hcu_objects_host32.c", "hcu_wind_objects_halo_ce_random"),
                    (ROOT / "tests/hcu_player_pvs_host32.c", "hcu_wind_pvs_halo_ce_random"),
                    (ROOT / "tests/hcu_bsp3d_host32.c", "hcu_wind_bsp_halo_ce_random")):
                text = source_path.read_text()
                generated = temp / ("matrix_" + source_path.name)
                generated.write_text(f"#define halo_ce_random {alias}\n" + text)
                sources[sources.index(source_path)] = generated
            executable, linkmap = temp / "mp-capacity", temp / "mp-capacity.map"
            command = [shutil.which("gcc"), *flags(), "-fshort-wchar", "-std=gnu99",
                       "-fms-extensions", "-fcommon", "-fwrapv", "-ffunction-sections",
                       "-fdata-sections", "-fgnu89-inline", "-fno-strict-aliasing", "-fno-delete-null-pointer-checks",
                       "-DHCU_BSP_RETAIL_INTEGRATION=1", "-DHALO_PS2=1",
                       "-DHALO_PS2_M2_ANIMATION_TRACE=1", "-DHCU_M2_MP_HOST_ORACLE=1",
                       "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                       "-include", str(semantics), "-w", *["-I" + str(p) for p in includes],
                       "-Wl,--gc-sections", "-Wl,--wrap=read",
                       "-Wl,--wrap=ps2_cache_release_map_owner",
                       "-Wl,--wrap=world_visit_section_with_scratch", "-Wl,-Map=" + str(linkmap),
                       *map(str, sources), "-lm", "-o", str(executable)]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            link_text = linkmap.read_text()
            for symbol in ("wind_initialize_for_new_map", "wind_update",
                           "scenario_get_current_from_weather_palette",
                           "random_math_initialize", "geosphere_new", "tag_get"):
                self.assertIn(symbol, link_text,
                              f"CE weather/wind source closure omitted {symbol}")
            assets = temp / "assets/maps"
            assets.mkdir(parents=True)
            for name, package in packages.items():
                (assets / f"{name}.hp2").symlink_to(package)
                (assets / f"{name}.map").symlink_to(ROOT / f"build/retail-maps/decompressed/{name}.map")
            retained_relative = Path(os.environ.get(
                "HCU_MP_CAPACITY_RETENTION_DIR", "build/m2-mp-weather-wind-13"))
            if retained_relative.is_absolute() or ".." in retained_relative.parts:
                raise AssertionError("retention directory must be a workspace-relative path")
            retained = ROOT / retained_relative
            retained.mkdir(parents=True, exist_ok=True)
            # Keep this focused extension's candidate image separate from any
            # concurrently retained native run of the older matrix binary.
            retained_executable = retained / "mp-weather-wind-location"
            retained_linkmap = retained / "mp-weather-wind-location.map"
            shutil.copy2(executable, retained_executable)
            shutil.copy2(linkmap, retained_linkmap)
            shutil.copy2(temp / "hcu_mp_weather_wind_golden.h",
                         retained / "hcu_mp_weather_wind_golden.h")
            shutil.copy2(temp / "mp_weather_wind_source_inventory.json",
                         retained / "mp_weather_wind_source_inventory.json")
            shutil.copy2(temp / "hcu_fog_plane_golden.h",
                         retained / "hcu_fog_plane_golden.h")
            shutil.copy2(temp / "mp_fog_source_inventory.json",
                         retained / "mp_fog_source_inventory.json")
            shutil.copy2(temp / "mp_location_source_inventory.json",
                         retained / "mp_location_source_inventory.json")
            shutil.copy2(temp / "hcu_collision_golden.h",
                         retained / "hcu_collision_golden.h")
            shutil.copy2(temp / "hcu_collision_golden.h",
                         retained / "hcu_collision_golden.h")
            shutil.copy2(temp / "mp_location_source_inventory.json",
                         retained / "mp_location_source_inventory.json")
            retained_assets = retained / "assets/maps"
            retained_assets.mkdir(parents=True, exist_ok=True)
            for name, package in packages.items():
                for suffix, target in (
                        ("hp2", package),
                        ("map", ROOT / f"build/retail-maps/decompressed/{name}.map")):
                    destination = retained_assets / f"{name}.{suffix}"
                    if destination.is_symlink() or destination.exists():
                        destination.unlink()
                    destination.symlink_to(target)
            fixture_command = [
                str(retained_executable.relative_to(ROOT)),
                str((retained / "assets").relative_to(ROOT)) + "/"]
            run = subprocess.run(fixture_command, cwd=ROOT,
                                 capture_output=True, text=True)
            if run.returncode in (-31, 159):
                (retained / "run.log").write_text(run.stdout + run.stderr)
                self.skipTest(
                    "sandbox blocks native ILP32 execution with SIGSYS; run outside sandbox: " +
                    " ".join(fixture_command))
            shutil.copy2(executable, retained_executable)
            shutil.copy2(linkmap, retained_linkmap)
            shutil.copy2(temp / "hcu_player_pvs_golden.h",
                         retained / "hcu_player_pvs_golden.h")
            shutil.copy2(temp / "hcu_mp_pvs_golden.h",
                         retained / "hcu_mp_pvs_golden.h")
            shutil.copy2(temp / "hcu_mp_sound_environment_golden.h",
                         retained / "hcu_mp_sound_environment_golden.h")
            shutil.copy2(temp / "hcu_mp_sound_obstruction_golden.h",
                         retained / "hcu_mp_sound_obstruction_golden.h")
            shutil.copy2(temp / "hcu_collision_golden.h",
                         retained / "hcu_collision_golden.h")
            shutil.copy2(temp / "hcu_mp_weather_wind_golden.h",
                         retained / "hcu_mp_weather_wind_golden.h")
            shutil.copy2(temp / "mp_weather_wind_source_inventory.json",
                         retained / "mp_weather_wind_source_inventory.json")
            shutil.copy2(temp / "mp_sound_environment_source_inventory.json",
                         retained / "mp_sound_environment_source_inventory.json")
            (retained / "run.log").write_text(run.stdout + run.stderr)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            late_failure_maps = re.findall(
                r"^mp-capacity late-B000-failure unpublished-and-retry "
                r"map=([a-z]+) cycle=0$", run.stdout, re.MULTILINE)
            self.assertEqual(
                late_failure_maps, list(packages),
                "each pinned stock MP map must exercise late B000 visitor "
                "failure, CE unpublish/owner cleanup, and same-process retry")
            self.assertEqual(run.stdout.count("mp-host-map map="), 2 * len(packages))
            nested_census_rows = re.findall(
                r"^mp-nested-census map=(\d+) bsp=(\d+) path_surfaces=(\d+) "
                r"path_edges=(\d+) decals=(\d+) detail_roots=(\d+) "
                r"lens_markers=(\d+) sound_scenery=(\d+) status=passed$",
                run.stdout, re.MULTILINE)
            self.assertEqual(len(nested_census_rows), 2 * len(packages),
                             "nested BSP/tag extent census must run in both CE load cycles for every stock MP map")
            self.assertEqual({int(row[0]) for row in nested_census_rows},
                             set(map_id_by_name.values()))
            location_rows = [tuple(map(int, row)) for row in re.findall(
                r"^mp-location map=(\d+) bsp=(\d+) start_leaf=(\d+) "
                r"start_cluster=(\d+) outside_leaf=-1 outside_cluster=-1 "
                r"status=passed$", run.stdout, re.MULTILINE)]
            expected_location_rows = {
                (map_id_by_name[name], row["bsp_index"], row["leaf_index"],
                 row["cluster_index"])
                for name, rows in collision_goldens_by_map.items()
                for row in rows
            }
            self.assertEqual(len(location_rows), 2 * len(expected_location_rows),
                             "each raw source BSP location query must run in both lifecycle cycles")
            self.assertEqual(set(location_rows), expected_location_rows,
                             "CE point-to-leaf/cluster result differs from raw BSP3D oracle")
            fog_plane_rows = [tuple(map(int, row)) for row in re.findall(
                r"^fog-plane map=(\d+) bsp=(\d+) cluster=(\d+) reference=(-?\d+) "
                r"plane=(\d+) region=(\d+) fog=(-?\d+) weather=(-?\d+) "
                r"underwater=(\d+) status=passed$", run.stdout, re.MULTILINE)]
            expected_fog_plane_rows = {
                (map_id_by_name[name], row["bsp_index"], row["cluster_index"],
                 row["reference"], row["plane_index"], row["region_index"],
                 row["fog_datum"], row["weather"])
                for name, rows in fog_plane_by_map.items() for row in rows
            }
            self.assertEqual(len(fog_plane_rows), 2 * len(expected_fog_plane_rows),
                             "every raw valid MP fog-plane case must run each load cycle")
            self.assertEqual({row[:8] for row in fog_plane_rows},
                             expected_fog_plane_rows)
            self.assertEqual(run.stdout.count("fog-none map="),
                             2 * sum(bool(rows) for rows in fog_none_by_map.values()),
                             "every raw MP NONE fog reference must preserve CE no-region result")
            self.assertEqual(run.stdout.count("mp-sound-obstruction map=102 bsp=0"), 2,
                             "Blood Gulch CE sound obstruction must run each load cycle")
            self.assertEqual(run.stdout.count("mp-weather-wind map="),
                             2 * len(packages),
                             "every stock MP BSP must run CE wind per load cycle")
            sound_rows = [tuple(map(int, row)) for row in re.findall(
                r"^mp-sound-environment map=(\d+) bsp=(\d+) cluster=(\d+) "
                r"palette=(-?\d+) tag=(-?\d+) background=(-?\d+) "
                r"fog_region=(-?\d+) priority=(-?\d+) calls=2 "
                r"status=passed$", run.stdout, re.MULTILINE)]
            self.assertEqual(len(sound_rows), 2 * len(sound_environment_goldens),
                             "CE listener selector must run in both reload cycles for each package golden")
            self.assertEqual({row for row in sound_rows},
                             {row[:8] for row in sound_environment_goldens})
            self.assertEqual({row[0] for row in sound_rows},
                             {row[0] for row in sound_environment_goldens})
            source_sha256 = {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sources + [ROOT / "tests/hcu_player_pvs_host32.c",
                                    ROOT / "tests/hcu_ce_map_lifecycle_main.c",
                                    ROOT / "tests/hcu_mp_nested_bsp_census.h",
                                    ROOT / "tests/test_hcu_scenario_bsp_switch.py",
                                    ROOT / "tests/test_hcu_wind_consumer.py",
                                    Path(__file__)] if p.is_relative_to(ROOT)
            }
            # hcu_player_pvs_host32.c includes the retail CE players.c TU; bind
            # that transitive source identity separately because it is not a
            # second translation unit in this fixture.
            source_sha256[str(HCU.relative_to(ROOT) / "source/game/players.c")] = (
                hashlib.sha256((HCU / "source/game/players.c").read_bytes()).hexdigest())
            source_sha256["src/stream/hcu_map_catalog.c"] = hashlib.sha256(
                (ROOT / "src/stream/hcu_map_catalog.c").read_bytes()).hexdigest()
            source_sha256["tools/pack_retail_ctag_hp2.py"] = hashlib.sha256(
                (ROOT / "tools/pack_retail_ctag_hp2.py").read_bytes()).hexdigest()
            source_sha256["build/m2-artifacts/schema-2fba411b-prior/halo-local.elf"] = (
                hashlib.sha256(schema_elf.read_bytes()).hexdigest())
            source_sha256["build/m2-mp-wind-package/manifest.json"] = hashlib.sha256(
                damnation_record_path.read_bytes()).hexdigest()
            # The executable compiles these generated/re-written fixtures, not
            # the originals named in the derivation list. Retain exact hashes
            # of the actual translation-unit inputs as well as their sources.
            source_sha256["generated/hcu_scenario_bsp_switch_main.c"] = hashlib.sha256(
                (temp / "hcu_scenario_bsp_switch_main.c").read_bytes()).hexdigest()
            source_sha256["generated/hcu_map_service_host.c"] = hashlib.sha256(
                (temp / "hcu_map_service_host.c").read_bytes()).hexdigest()
            source_sha256["generated/hcu_mp_lifecycle_generated.h"] = hashlib.sha256(
                (temp / "hcu_mp_lifecycle_generated.h").read_bytes()).hexdigest()
            source_sha256["generated/hcu_mp_pvs_golden.h"] = hashlib.sha256(
                (temp / "hcu_mp_pvs_golden.h").read_bytes()).hexdigest()
            source_sha256["generated/hcu_collision_golden.h"] = hashlib.sha256(
                (temp / "hcu_collision_golden.h").read_bytes()).hexdigest()
            source_sha256["generated/hcu_mp_sound_environment_golden.h"] = hashlib.sha256(
                (temp / "hcu_mp_sound_environment_golden.h").read_bytes()).hexdigest()
            source_sha256["generated/hcu_mp_sound_obstruction_golden.h"] = hashlib.sha256(
                (temp / "hcu_mp_sound_obstruction_golden.h").read_bytes()).hexdigest()
            source_sha256["generated/hcu_mp_weather_wind_golden.h"] = hashlib.sha256(
                (temp / "hcu_mp_weather_wind_golden.h").read_bytes()).hexdigest()
            source_sha256["generated/wind_hcu_mp_matrix.c"] = hashlib.sha256(
                generated_wind.read_bytes()).hexdigest()
            source_sha256["generated/hcu_real_math_source_host32.c"] = hashlib.sha256(
                generated_real_math.read_bytes()).hexdigest()
            source_sha256["generated/hcu_fog_plane_golden.h"] = hashlib.sha256(
                (temp / "hcu_fog_plane_golden.h").read_bytes()).hexdigest()
            source_sha256["generated/mp_fog_source_inventory.json"] = hashlib.sha256(
                (temp / "mp_fog_source_inventory.json").read_bytes()).hexdigest()
            source_sha256["generated/mp_location_source_inventory.json"] = hashlib.sha256(
                (temp / "mp_location_source_inventory.json").read_bytes()).hexdigest()
            source_sha256["generated/mp_sound_environment_source_inventory.json"] = hashlib.sha256(
                (temp / "mp_sound_environment_source_inventory.json").read_bytes()).hexdigest()
            manifest = {"status": "passed", "native_ilp32": True, "ee_evidence": False,
                        "capacity_scope": "host semantic fixture only; not PS2/EE target memory evidence",
                        "late_cbsp_failure_atomicity": {
                            "status": "passed",
                            "maps": late_failure_maps,
                            "attempts": len(late_failure_maps),
                            "fault_point": "after first decoded B000 sink write, before CE BSP publication",
                            "checks": [
                                "nonzero decoded bytes reached fixed BSP destination",
                                "scenario/BSP/collision/game globals unpublished",
                                "tag globals/cache publication cleared",
                                "map mount/source descriptors closed",
                                "map-owner and scratch cursors returned to zero",
                                "same-process preflight, remount, and scenario_load retry succeeded",
                            ],
                        },
                        "nested_bsp_extent_census": {
                            "status": "passed",
                            "rows": len(nested_census_rows),
                            "maps": sorted({int(row[0]) for row in nested_census_rows}),
                            "cycles_per_map": 2,
                            "scope": "CE post-load tag/BSP pointers bounded by mounted tag_data_size and active B000 file_size",
                            "checked": ["scenario root and sound scenery placement/palette blocks",
                                        "BSP pathfinding surface/edge byte blocks",
                                        "runtime decals and detail-object root/nested blocks",
                                        "lens-flare markers and cluster decal/marker ranges"],
                            "not_checked": ["opaque legacy BSP markers block (not schema-relocated)",
                                            "consumer behavior or independent semantic parity"],
                        },
                        "capacities": {"tag": 16 * 1024 * 1024, "bsp": 8 * 1024 * 1024,
                                       "claims": 4 * 1024 * 1024, "map_owner": 1048576,
                                       "streaming_scratch": 524288},
                        "elf_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                        "link_map_sha256": hashlib.sha256(linkmap.read_bytes()).hexdigest(),
                        "player_pvs_golden_sha256": hashlib.sha256(
                            (temp / "hcu_player_pvs_golden.h").read_bytes()).hexdigest(),
                        "sound_environment_golden_sha256": hashlib.sha256(
                            (temp / "hcu_mp_sound_environment_golden.h").read_bytes()).hexdigest(),
                        "sound_obstruction_golden_sha256": hashlib.sha256(
                            (temp / "hcu_mp_sound_obstruction_golden.h").read_bytes()).hexdigest(),
                        "weather_wind_golden_sha256": hashlib.sha256(
                            (temp / "hcu_mp_weather_wind_golden.h").read_bytes()).hexdigest(),
                        "weather_wind_source_inventory_sha256": hashlib.sha256(
                            (temp / "mp_weather_wind_source_inventory.json").read_bytes()).hexdigest(),
                        "fog_plane_golden_sha256": hashlib.sha256(
                            (temp / "hcu_fog_plane_golden.h").read_bytes()).hexdigest(),
                        "fog_source_inventory_sha256": hashlib.sha256(
                            (temp / "mp_fog_source_inventory.json").read_bytes()).hexdigest(),
                        "location_source_inventory_sha256": hashlib.sha256(
                            (temp / "mp_location_source_inventory.json").read_bytes()).hexdigest(),
                        "collision_golden_sha256": hashlib.sha256(
                            (temp / "hcu_collision_golden.h").read_bytes()).hexdigest(),
                        "sound_environment_source_inventory_sha256": hashlib.sha256(
                            (temp / "mp_sound_environment_source_inventory.json").read_bytes()).hexdigest(),
                        "source_sha256": source_sha256,
                        "packages": {name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for name, p in packages.items()},
                        "package_generation": {
                            name: {
                                "generation_record": (
                                    "build/m2-mp-wind-package/manifest.json; validated MP wind package"
                                    if name == "damnation" else
                                    "tools/pack_retail_ctag_hp2.py " +
                                    f"build/retail-maps/decompressed/{name}.map " +
                                    "build/m2-artifacts/schema-2fba411b-prior/halo-local.elf " +
                                    f"{package.relative_to(ROOT)} --include-all-bsps"),
                                "schema_elf_sha256": SCHEMA_ELF_SHA256,
                                "source_map_sha256": MP_SOURCE_SHA256[name],
                                "package_sha256": MP_PACKAGE_SHA256[name],
                            } for name, package in packages.items()
                        },
                        "source_maps": {name: hashlib.sha256((ROOT /
                            f"build/retail-maps/decompressed/{name}.map").read_bytes()).hexdigest()
                            for name in MP_MAPS}}
            for name, path in (("parent", ROOT), ("hcu", HCU),
                               ("halo_ps2", ROOT / "submodules/halo-ps2")):
                manifest[name + "_head"] = subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "HEAD"], check=True,
                    capture_output=True, text=True).stdout.strip()
            (retained / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
