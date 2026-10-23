"""Relocated CBSP detail-object gate for the 13 stock multiplayer maps.

Raw Xbox BSP bytes are the oracle. Each map is published through the
production PS2 cache/CBSP loader, then the actual CE detail-object entry
runs at every subcluster bounds center. Rasterizer hooks only count calls.
"""
from pathlib import Path
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/step7-swarm/detail"
PACKAGES = Path("/tmp/hcu-m2-capacity-repro.P5qdmI/packages")
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
DETAIL_ROOT_OFFSET = 588
CLUSTER_BLOCK_OFFSET = 308
CLUSTER_STRIDE = 0x68
SUBCLUSTER_BLOCK_OFFSET = 0x34
SUBCLUSTER_STRIDE = 0x24
DETAIL_ROOT_BYTES = 64

sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from host_abi32 import flags  # noqa: E402
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from test_hcu_scenario_bsp_switch import (  # noqa: E402
    write_collision_golden_header,
    write_fog_plane_golden_header,
    write_player_pvs_golden_header,
    write_sound_pas_golden_header,
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_detail_oracle(map_name):
    """Read detail roots and subcluster bounds from the decompressed Xbox map."""
    path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    source_hash = sha256_file(path)
    if source_hash != MAP_SHA256[map_name]:
        raise AssertionError(f"{map_name} source hash changed")
    header = mapinfo.read_header(path)
    index = tagindex.TagIndex.read(path)
    region, _tag_base, _info = read_xbox_tag_region(path)
    locations = bsp.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{map_name}: expected one stock multiplayer BSP")
    location = locations[0]
    image = path.read_bytes()[location.file_offset:location.file_offset + location.size]
    if len(image) != location.size:
        raise AssertionError(f"{map_name}: truncated BSP image")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError(f"{map_name}: structure BSP root leaves the source image")
    detail_count, detail_address, detail_definition = struct.unpack_from(
        "<iII", image, root + DETAIL_ROOT_OFFSET)
    if detail_count != 1 or detail_definition != 0:
        raise AssertionError(
            f"{map_name}: raw detail_object_data block is {detail_count}, "
            f"definition {detail_definition:#x}")
    detail_offset = detail_address - location.address
    if detail_offset < 0 or detail_offset + DETAIL_ROOT_BYTES > len(image):
        raise AssertionError(f"{map_name}: detail root leaves the source BSP")
    raw_root = image[detail_offset:detail_offset + DETAIL_ROOT_BYTES]
    children = []
    for child in range(4):
        count, address, definition = struct.unpack_from("<iII", raw_root, child * 12)
        children.append((count, address, definition))
        if count != 0 or address != 0 or definition != 0:
            raise AssertionError(
                f"{map_name}: raw detail child {child} is not empty "
                f"({count}, {address:#x}, {definition:#x})")
    valid = raw_root[48]
    if valid != 0 or raw_root != bytes(DETAIL_ROOT_BYTES):
        raise AssertionError(f"{map_name}: raw detail root is not an empty valid=0 record")
    cluster_count, cluster_address, cluster_definition = struct.unpack_from(
        "<iII", image, root + CLUSTER_BLOCK_OFFSET)
    if cluster_count <= 0 or cluster_definition != 0:
        raise AssertionError(f"{map_name}: unexpected raw cluster block")
    cluster_offset = cluster_address - location.address
    if (cluster_offset < 0 or
            cluster_offset + cluster_count * CLUSTER_STRIDE > len(image)):
        raise AssertionError(f"{map_name}: raw clusters leave the source BSP")
    samples = []
    for cluster_index in range(cluster_count):
        base = cluster_offset + cluster_index * CLUSTER_STRIDE + SUBCLUSTER_BLOCK_OFFSET
        sub_count, sub_address, sub_definition = struct.unpack_from("<iII", image, base)
        if sub_count < 0 or sub_definition != 0:
            raise AssertionError(f"{map_name}: bad subcluster block on cluster {cluster_index}")
        if sub_count == 0:
            if sub_address != 0:
                raise AssertionError(
                    f"{map_name}: empty subcluster block has address {sub_address:#x}")
            continue
        sub_offset = sub_address - location.address
        if (sub_offset < 0 or
                sub_offset + sub_count * SUBCLUSTER_STRIDE > len(image)):
            raise AssertionError(
                f"{map_name}: subclusters of cluster {cluster_index} leave the source BSP")
        for sub_index in range(sub_count):
            bounds = struct.unpack_from(
                "<6I", image, sub_offset + sub_index * SUBCLUSTER_STRIDE)
            samples.append((cluster_index, sub_index, bounds))
    return {
        "name": map_name,
        "source_sha256": source_hash,
        "bsp_file_offset": location.file_offset,
        "bsp_file_size": location.size,
        "raw_bsp_sha256": hashlib.sha256(image).hexdigest(),
        "detail_count": detail_count,
        "valid": valid,
        "children": children,
        "raw_root": raw_root,
        "cluster_count": cluster_count,
        "samples": samples,
    }


def write_oracle_header(path, rows):
    lines = [
        "#ifndef HCU_DETAIL_PRESENT_BOUND_ORACLE_H",
        "#define HCU_DETAIL_PRESENT_BOUND_ORACLE_H",
        "struct hcu_detail_map_oracle {",
        "    unsigned map_id, bsp_file_offset, bsp_file_size;",
        "    unsigned cluster_count, subcluster_begin, subcluster_count;",
        "    unsigned detail_count, valid;",
        "    int child_count[4];",
        "    unsigned child_address[4];",
        "    unsigned char raw_root[64];",
        "    char name[16];",
        "};",
        "struct hcu_detail_subcluster_oracle {",
        "    unsigned map_id, cluster_index, subcluster_index, bounds_bits[6];",
        "};",
        "static const struct hcu_detail_map_oracle hcu_detail_maps[] = {",
    ]
    samples = []
    begin = 0
    for index, row in enumerate(rows):
        map_id = 101 + index
        child_counts = ", ".join(str(item[0]) for item in row["children"])
        child_addresses = ", ".join(f"{item[1]}u" for item in row["children"])
        raw = ", ".join(f"0x{byte:02x}" for byte in row["raw_root"])
        lines.append(
            "    {%uu, %uu, %uu, %uu, %uu, %uu, %uu, %uu, {%s}, {%s}, {%s}, \"%s\"}," % (
                map_id, row["bsp_file_offset"], row["bsp_file_size"],
                row["cluster_count"], begin, len(row["samples"]),
                row["detail_count"], row["valid"], child_counts, child_addresses,
                raw, row["name"]))
        for cluster_index, sub_index, bounds in row["samples"]:
            bits = ", ".join(f"0x{bit:08x}u" for bit in bounds)
            samples.append(
                f"    {{{map_id}u, {cluster_index}u, {sub_index}u, {{{bits}}}}},")
        begin += len(row["samples"])
    lines += [
        "};",
        f"#define HCU_DETAIL_MAP_COUNT {len(rows)}u",
        "static const struct hcu_detail_subcluster_oracle hcu_detail_subclusters[] = {",
    ]
    lines += samples
    lines += [
        "};",
        f"#define HCU_DETAIL_SUBCLUSTER_COUNT {len(samples)}u",
        "#endif",
        "",
    ]
    path.write_text("\n".join(lines))
    return len(samples)


def prepare_fixture(work, rows):
    common = (ROOT / "tests/hcu_scenario_bsp_switch_main.c").read_text()
    scratch = "retail_section_scratch_bytes[131072]"
    if common.count(scratch) != 1:
        raise AssertionError("section scratch declaration changed")
    common = common.replace(scratch, "retail_section_scratch_bytes[524288]")
    include = '"../submodules/'
    if common.count(include) != 3:
        raise AssertionError("switch fixture submodule include changed")
    common = common.replace(include, '"' + str(ROOT / "submodules") + "/")
    (work / "hcu_scenario_bsp_switch_main.c").write_text(common)
    lifecycle = (ROOT / "tests/hcu_ce_map_lifecycle_main.c").read_text()
    if lifecycle.count("int main(int argc, char **argv)") != 1:
        raise AssertionError("lifecycle main declaration changed")
    lifecycle = lifecycle.replace(
        "int main(int argc, char **argv)",
        "int hcu_detail_unused_lifecycle_main(int argc, char **argv)")
    (work / "hcu_detail_present_bound_lifecycle.h").write_text(lifecycle)
    write_oracle_header(work / "hcu_detail_present_bound_oracle.h", rows)
    write_collision_golden_header(work / "hcu_collision_golden.h", [])
    write_player_pvs_golden_header(work / "hcu_player_pvs_golden.h", [])
    write_sound_pas_golden_header(work / "hcu_sound_pas_golden.h", [])
    write_fog_plane_golden_header(work / "hcu_fog_plane_golden.h", [])


class DetailPresentBoundTest(unittest.TestCase):
    def test_relocated_empty_detail_roots_draw_nothing(self):
        rows = [raw_detail_oracle(name) for name in MP_MAPS]
        self.assertEqual([row["name"] for row in rows], list(MP_MAPS))
        for row in rows:
            self.assertEqual(row["valid"], 0)
            self.assertEqual(row["children"], [(0, 0, 0)] * 4)
            self.assertGreater(row["cluster_count"], 0)
            self.assertGreater(len(row["samples"]), 0, row["name"])
        OUT.mkdir(parents=True, exist_ok=True)
        work = OUT / "work"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        prepare_fixture(work, rows)
        assets = work / "assets/maps"
        assets.mkdir(parents=True)
        package_hashes = {}
        for name in MP_MAPS:
            package = PACKAGES / f"{name}.hp2"
            source = ROOT / "build/retail-maps/decompressed" / f"{name}.map"
            self.assertTrue(package.is_file(), f"missing HP2 package {package}")
            self.assertTrue(source.is_file(), f"missing source map {source}")
            package_hashes[name] = sha256_file(package)
            for suffix, target in (("hp2", package), ("map", source)):
                link = assets / f"{name}.{suffix}"
                link.symlink_to(target)
        semantics = work / "halo_ps2_msvc_semantics.h"
        subprocess.run([
            sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
            "--output", str(semantics), "--all-inlines",
            "--tags", str(HCU / "source"), "--inlines", str(HCU / "source"),
            "--inlines", str(HCU / "port/include/xdk"),
        ], check=True, capture_output=True, text=True)
        includes = [work, ROOT / "tests", ROOT / "tests/hcu_scenario_host_shim",
                    HCU / "port/ps2/include", HCU / "port/linux/game", HCU / "port/include",
                    HCU / "source", *[HCU / "source" / directory for directory in (
                        "cseries", "scenario", "structures", "cache", "tag_files", "objects",
                        "physics", "game", "interface", "math", "sound", "memory", "input",
                        "render", "rasterizer")],
                    ROOT / "src", ROOT / "src/stream", ROOT / "submodules/halo-ps2/engine/src",
                    ROOT / "submodules/halo-ps2/engine/tests/hp2_world_shim",
                    Path("/usr/include")]
        sources = [ROOT / "tests/hcu_detail_present_bound_main.c",
                   HCU / "source/structures/structure_detail_objects.c",
                   ROOT / "tests/hcu_mp_sound_environment_host32.c",
                   ROOT / "tests/hcu_game_sound_host32.c",
                   ROOT / "tests/hcu_objects_host32.c",
                   ROOT / "tests/hcu_player_pvs_host32.c",
                   ROOT / "tests/hcu_real_math_host32.c",
                   ROOT / "tests/hcu_real_math_source_host32.c",
                   ROOT / "tests/hcu_bsp3d_host32.c",
                   ROOT / "tests/hcu_geometry_source_host32.c"]
        sources += [HCU / "source" / relative for relative in (
            "scenario/scenario.c", "scenario/wind.c", "math/random_math.c",
            "sound/sound_environment_definitions.c", "tag_files/tag_files.c",
            "memory/data.c", "math/integer_math.c", "physics/collisions.c",
            "physics/collision_bsp.c", "physics/bsp2d.c")]
        sources += [HCU / "port/ps2/src" / relative for relative in (
            "ps2_animation_trace.c", "ps2_cache.c", "ps2_ctag.c", "ps2_cbsp.c")]
        sources += [HCU / "port/linux/game" / f"tag_schema_{name}.c" for name in (
            "groups", "collision", "models", "objects", "render", "effects", "scenario")]
        sources += [ROOT / "src/stream" / f"{name}.c" for name in (
            "hcu_map_catalog", "ctag_mount", "ctag_ps2_backend", "cbsp_catalog",
            "ctag_resource_index", "ctag_map_source", "sha256", "hmap")]
        sources.append(ROOT / "src/stream/hcu_map_service.c")
        sources += [ROOT / "submodules/halo-ps2/engine/src" / relative for relative in (
            "world/section.c", "stream/hp2.c", "stream/file.c", "core/mem.c")]
        for source_path, alias in (
                (ROOT / "tests/hcu_objects_host32.c", "hcu_detail_objects_halo_ce_random"),
                (ROOT / "tests/hcu_player_pvs_host32.c", "hcu_detail_pvs_halo_ce_random"),
                (ROOT / "tests/hcu_bsp3d_host32.c", "hcu_detail_bsp_halo_ce_random")):
            generated = work / source_path.name
            generated.write_text(f"#define halo_ce_random {alias}\n" + source_path.read_text())
            sources[sources.index(source_path)] = generated
        wind_text = (HCU / "source/scenario/wind.c").read_text().replace(
            "uniform_cubic_spline_vector3d(",
            "wind_uniform_cubic_spline_vector3d_inline(")
        generated_wind = work / "hcu_detail_wind.c"
        generated_wind.write_text(wind_text)
        sources[sources.index(HCU / "source/scenario/wind.c")] = generated_wind
        generated_real_math = work / "hcu_detail_real_math_source_host32.c"
        generated_real_math.write_text(
            "#define global_projection3d_mappings hcu_detail_projection3d_mappings\n"
            "#define fast_vector_intersects_sphere hcu_detail_fast_vector_intersects_sphere\n"
            f'#include "{ROOT / "tests/hcu_real_math_source_host32.c"}"\n')
        sources[sources.index(ROOT / "tests/hcu_real_math_source_host32.c")] = generated_real_math
        executable = OUT / "detail-present-bound"
        link_map = OUT / "detail-present-bound.map"
        command = [shutil.which("gcc"), *flags(), "-fshort-wchar", "-std=gnu99",
                   "-fms-extensions", "-fcommon", "-fwrapv", "-fgnu89-inline",
                   "-ffunction-sections", "-fdata-sections", "-fno-strict-aliasing",
                   "-fno-delete-null-pointer-checks",
                   "-DHCU_BSP_RETAIL_INTEGRATION=1", "-DHALO_PS2=1",
                   "-DHALO_PS2_M2_ANIMATION_TRACE=1",
                   "-DHALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC=1",
                   "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                   "-include", str(semantics), "-w",
                   *["-I" + str(path) for path in includes],
                   "-Wl,--gc-sections", "-Wl,--wrap=read",
                   "-Wl,--wrap=global_structure_bsp_get",
                   "-Wl,--wrap=ps2_cache_release_map_owner",
                   "-Wl,--wrap=world_visit_section_with_scratch",
                   "-Wl,-Map=" + str(link_map), *map(str, sources), "-lm",
                   "-o", str(executable)]
        built = subprocess.run(command, capture_output=True, text=True)
        (OUT / "compile.log").write_text(built.stdout + built.stderr)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        link_text = link_map.read_text(errors="replace")
        required_symbols = (
            "structure_render_detail_objects",
            "structure_detail_objects_initialize",
            "structure_detail_objects_initialize_for_new_map",
            "get_lower_bound_cell", "get_upper_bound_cell",
            "structure_detail_objects_port_count",
            "scenario_load", "ps2_cbsp_rebase_in_place",
            "ps2_cbsp_materialize",
            "__wrap_global_structure_bsp_get",
            "rasterizer_detail_objects_begin",
            "rasterizer_detail_objects_draw",
        )
        missing = [symbol for symbol in required_symbols if symbol not in link_text]
        self.assertEqual(missing, [])
        self.assertNotIn("rasterizer_xbox", link_text)
        # file_set_default_root stores at most 63 characters and requires a
        # trailing slash. A workspace-relative root fits; an absolute one does not.
        asset_root = assets.parent.relative_to(ROOT).as_posix() + "/"
        self.assertLess(len(asset_root), 64)
        run = subprocess.run([str(executable), asset_root],
                             cwd=ROOT, capture_output=True, text=True)
        (OUT / "run.log").write_text(run.stdout + run.stderr)
        if run.returncode in (-31, 159):
            self.skipTest("sandbox blocks native ILP32 execution with SIGSYS; rerun outside the sandbox")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        pattern = re.compile(
            r"^detail-present map=([a-z]+) id=(\d+) bsp=(\d+) detail_roots=(\d+) "
            r"valid=(\d+) cells=(\d+) objects=(\d+) counts=(\d+) zrefs=(\d+) "
            r"child_addresses=0 clusters=(\d+) subclusters=(\d+) camera_calls=(\d+) "
            r"bsp_gets=(\d+) rasterizer_begin=0 rebuild=0 draw=0 end=0 "
            r"bsp_bytes=(\d+) bsp_sha256=([0-9a-f]{64}) bsp_unchanged=1 "
            r"collision_depth=(-?\d+) collision_depth_unchanged=1 status=passed$")
        parsed = [pattern.match(line) for line in run.stdout.splitlines()
                  if line.startswith("detail-present map=")]
        self.assertEqual(len(parsed), len(MP_MAPS))
        self.assertTrue(all(parsed))
        camera_total = 0
        for row, match in zip(rows, parsed):
            with self.subTest(map=row["name"]):
                self.assertEqual(match.group(1), row["name"])
                self.assertEqual(int(match.group(2)), 101 + MP_MAPS.index(row["name"]))
                self.assertEqual(int(match.group(3)), 0)
                self.assertEqual(int(match.group(4)), 1)
                self.assertEqual(int(match.group(5)), 0)
                self.assertEqual((int(match.group(6)), int(match.group(7)),
                                  int(match.group(8)), int(match.group(9))), (0, 0, 0, 0))
                self.assertEqual(int(match.group(10)), row["cluster_count"])
                self.assertEqual(int(match.group(11)), len(row["samples"]))
                self.assertEqual(int(match.group(12)), len(row["samples"]))
                self.assertEqual(int(match.group(13)), 2 * len(row["samples"]))
                self.assertEqual(int(match.group(14)), row["bsp_file_size"])
                camera_total += len(row["samples"])
        self.assertIn(
            f"detail-present summary maps=13 camera_calls={camera_total} "
            "rasterizer_calls=0 status=passed", run.stdout)
        self.assertEqual(camera_total, sum(len(row["samples"]) for row in rows))
        source_files = (
            ROOT / "tests/test_hcu_mp_detail_present_bound.py",
            ROOT / "tests/hcu_detail_present_bound_main.c",
        )
        hashes = {path.name: sha256_file(path) for path in source_files}
        hashes[executable.name] = sha256_file(executable)
        hashes["run.log"] = sha256_file(OUT / "run.log")
        hashes["compile.log"] = sha256_file(OUT / "compile.log")
        report = [
            "# Step 7 swarm — relocated detail-object present bound",
            "",
            "PASS. All 13 stock multiplayer BSPs publish one detail-object root through the production PS2 CBSP/cache path. Raw Xbox bytes and the relocated payload are 64 zero bytes: `valid == 0` and the cells, instances, counts, and z-reference blocks are empty. `structure_render_detail_objects` ran at every raw-proven subcluster bounds center and issued no rasterizer calls. Published BSP bytes and collision-user depth stayed unchanged.",
            "",
            "This does not draw detail sprites and does not claim PCSX2, GS, VU, or SPU2 output.",
            "",
            "## Reproduction",
            "",
            "```sh",
            "python3 -m pytest -q tests/test_hcu_mp_detail_present_bound.py",
            "```",
            "",
            "Native ILP32 execution can raise SIGSYS inside a sandbox. Rerun that same command with sandbox restrictions disabled.",
            "",
            "## Counts",
            "",
            "- Tests: 1",
            "- Subtests: 13 (one per stock multiplayer map)",
            f"- Camera samples: {camera_total}",
            "- Rasterizer begin/rebuild/draw/end calls: 0",
            "",
            "## Per-map results",
            "",
            "| Map | Detail roots | valid | Child counts | Clusters | Subcluster cameras | BSP gets | Rasterizer | BSP bytes unchanged |",
            "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for row, match in zip(rows, parsed):
            report.append(
                f"| {row['name']} | 1 | 0 | 0,0,0,0 | {row['cluster_count']} | "
                f"{len(row['samples'])} | {2 * len(row['samples'])} | 0 | yes |")
        report += [
            "",
            "Every map's raw child addresses are 0, and the relocated child addresses are NULL. No map has an empty subcluster set, so none is an empty camera-sample result. The detail-object instances themselves are an explicit empty result on every map.",
            "",
            "## SHA-256",
            "",
        ]
        for name, digest in hashes.items():
            report.append(f"- `{name}`: `{digest}`")
        report += ["", "## Packages", ""]
        for name in MP_MAPS:
            report.append(f"- `{name}.hp2`: `{package_hashes[name]}`")
        report += [
            "",
            "## Issues",
            "",
            "None.",
            "",
            "## Limits",
            "",
            "- Host ILP32 semantic fixture. It is not EE RAM, target timing, or PCSX2/GS/VU/SPU2 evidence.",
            "- The CE valid-data camera-cell search is not entered, because every stock root is `valid == 0`. That search remains covered only by the separate synthetic consumer fixture.",
            "- Rasterizer hooks count calls. They are not a detail-sprite renderer.",
            "- Map admission uses the existing `HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC` compile switch, which already names these 13 maps. Production sources were not edited.",
            "",
        ]
        (OUT / "report.md").write_text("\n".join(report))


if __name__ == "__main__":
    unittest.main()
