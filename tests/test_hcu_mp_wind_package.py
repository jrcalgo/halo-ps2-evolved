"""Run CE wind init/update/current on a package-relocated MP structure BSP."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MAP_NAME = "damnation"
MAP_ID = 106
WIND_OFFSET = 436
WIND_STRIDE = 0xF0
CLUSTER_OFFSET = 308
CLUSTER_STRIDE = 0x68
WIND_REF_OFFSET = 0x8C
WIND_DIRECTION_OFFSET = 0x90
WIND_MAGNITUDE_OFFSET = 0x9C
WIND_DEF_BYTES = 0x40
LOCAL_SEED = 0x89ABCDEF
GLOBAL_SEED = 0x13579BDF

sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from host_abi32 import flags
from halo2ps2 import bsp, mapinfo, tagindex
from ctag_schema_walk import read_xbox_tag_region
from pack_retail_ctag_hp2 import pack_retail_map
from test_hcu_scenario_bsp_switch import (
    retail_source_collision_goldens, write_collision_golden_header,
    write_player_pvs_golden_header, write_sound_pas_golden_header,
    retail_source_fog_plane_oracle, write_fog_plane_golden_header,
)
from test_hcu_wind_consumer import _expected_vectors, _c_float


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def raw_weather_oracle(map_path):
    """Extract all palette/tag inputs and cluster indices from retail bytes."""
    index = tagindex.TagIndex.read(map_path)
    tag_region, tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, tag_region,
                           mapinfo.read_header(map_path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"expected one Damnation BSP, got {len(locations)}")
    location = locations[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    if len(image) != location.size:
        raise AssertionError("Damnation raw BSP is truncated")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError("Damnation BSP root leaves raw image")
    count, address = struct.unpack_from("<iI", image, root + WIND_OFFSET)
    offset = address - location.address if address else 0
    if count != 2 or offset < 0 or offset + count * WIND_STRIDE > len(image):
        raise AssertionError(f"unexpected Damnation weather palette extent: {count}")
    tags = {entry.tag_id: entry for entry in index.entries}
    palette = []
    for palette_index in range(count):
        entry = offset + palette_index * WIND_STRIDE
        datum = struct.unpack_from("<I", image, entry + WIND_REF_OFFSET)[0]
        direction = struct.unpack_from("<3f", image, entry + WIND_DIRECTION_OFFSET)
        magnitude = struct.unpack_from("<f", image, entry + WIND_MAGNITUDE_OFFSET)[0]
        if datum == 0xFFFFFFFF:
            definition = (0.0,) * 7
        else:
            tag = tags.get(datum)
            if tag is None or tag.group != "wind":
                raise AssertionError(f"palette datum {datum:#010x} is not a wind tag")
            data_offset = tag.data_address - tag_base
            if data_offset < 0 or data_offset + WIND_DEF_BYTES > len(tag_region):
                raise AssertionError(f"wind definition leaves tag region: {tag.path}")
            definition = struct.unpack_from("<7f", tag_region, data_offset)
        palette.append({"datum": datum, "direction": direction,
                        "magnitude": magnitude, "definition": definition})

    cluster_count, cluster_address = struct.unpack_from(
        "<iI", image, root + CLUSTER_OFFSET)
    cluster_offset = cluster_address - location.address if cluster_address else 0
    if (cluster_count != 12 or cluster_offset < 0 or
            cluster_offset + cluster_count * CLUSTER_STRIDE > len(image)):
        raise AssertionError(f"unexpected Damnation cluster extent: {cluster_count}")
    cluster_refs = [struct.unpack_from(
        "<h", image, cluster_offset + i * CLUSTER_STRIDE + 8)[0]
        for i in range(cluster_count)]
    if cluster_refs != [0] * cluster_count:
        raise AssertionError(f"unexpected Damnation cluster weather refs: {cluster_refs}")
    return {"bsp_path": location.path, "raw_bsp_sha256": sha256_bytes(image),
            "raw_bsp_bytes": len(image), "palette": palette,
            "cluster_count": cluster_count, "cluster_weather_indices": cluster_refs}


def write_expected_header(path, raw):
    expected = _expected_vectors(raw, GLOBAL_SEED, LOCAL_SEED)
    lines = [
        f"#define HCU_MP_WIND_PALETTE_COUNT {len(raw['palette'])}",
        f"#define HCU_MP_WIND_CLUSTER_COUNT {raw['cluster_count']}",
        f"#define HCU_MP_WIND_LOCAL_SEED 0x{LOCAL_SEED:08X}UL",
        "static const unsigned long HCU_MP_WIND_DATUMS[] = { " +
        ", ".join(f"0x{row['datum']:08X}UL" for row in raw["palette"]) + " };",
        "static const float HCU_MP_WIND_DIRECTIONS[][3] = { " +
        ", ".join("{ " + ", ".join(_c_float(x) for x in row["direction"]) + " }"
                  for row in raw["palette"]) + " };",
        "static const float HCU_MP_WIND_MAGNITUDES[] = { " +
        ", ".join(_c_float(row["magnitude"]) for row in raw["palette"]) + " };",
        "static const float hcu_mp_wind_expected_normal[3] = { " +
        ", ".join(_c_float(x) for x in expected[0, "normal"]) + " };",
        "static const float hcu_mp_wind_expected_simple[3] = { " +
        ", ".join(_c_float(x) for x in expected[0, "simple"]) + " };",
        "static const float hcu_mp_wind_expected_damped[3] = { " +
        ", ".join(_c_float(x) for x in expected[0, "damped"]) + " };",
        "",
    ]
    path.write_text("\n".join(lines))
    return {name: expected[0, name] for name in ("normal", "simple", "damped")}


class HcuMpWindPackageTest(unittest.TestCase):
    def test_relocated_damnation_bsp_drives_real_ce_wind(self):
        source_map = ROOT / f"build/retail-maps/decompressed/{MAP_NAME}.map"
        schema_elf = ROOT / "build/m2-artifacts/schema-2fba411b-prior/halo-local.elf"
        if not source_map.is_file() or not schema_elf.is_file():
            self.skipTest("Damnation source map or pinned package schema ELF is absent")
        self.assertEqual(sha256_bytes(source_map.read_bytes()),
                         "87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c")
        raw = raw_weather_oracle(source_map)
        self.assertEqual(raw["palette"][0]["datum"], 0xE84F06D9)
        self.assertEqual(raw["palette"][1]["datum"], 0xFFFFFFFF)

        with tempfile.TemporaryDirectory(prefix="hcu-mp-wind-") as temp_name:
            temp = Path(temp_name)
            package, package_summary = pack_retail_map(
                source_map, schema_elf, include_all_bsps=True)
            self.assertEqual(package_summary["complete_bsp_catalog"], True)
            assets = temp / "assets/maps"
            assets.mkdir(parents=True)
            (assets / f"{MAP_NAME}.hp2").write_bytes(package)
            (assets / f"{MAP_NAME}.map").symlink_to(source_map)

            # Build an isolated copy of the lifecycle harness with its existing
            # diagnostic capacity profile and a temporary map-admission case.
            common_original = ROOT / "tests/hcu_scenario_bsp_switch_main.c"
            common = common_original.read_text()
            replacements = {
                "#define TAG_CACHE_BYTES (16u * 1024u * 1024u)": "#define TAG_CACHE_BYTES 4477120u",
                "#define BSP_CACHE_BYTES (8u * 1024u * 1024u)": "#define BSP_CACHE_BYTES 1814336u",
                "#define OWNER_ARENA_BYTES (16u * 1024u * 1024u)": "#define OWNER_ARENA_BYTES 1048576u",
                "#define BSP_SCRATCH_BYTES (16u * 1024u * 1024u)": "#define BSP_SCRATCH_BYTES 1u",
                "retail_section_scratch_bytes[131072]": "retail_section_scratch_bytes[524288]",
                "retail_claims_bytes[4u * 1024u * 1024u]": "retail_claims_bytes[786432]",
            }
            for old, new in replacements.items():
                self.assertEqual(common.count(old), 1, old)
                common = common.replace(old, new)
            common = common.replace('"../submodules/', '"' + str(ROOT / "submodules") + "/")
            (temp / "hcu_scenario_bsp_switch_main.c").write_text(common)

            lifecycle = (ROOT / "tests/hcu_ce_map_lifecycle_main.c").read_text()
            self.assertEqual(lifecycle.count("int main(int argc, char **argv)"), 1)
            lifecycle = lifecycle.replace("int main(int argc, char **argv)",
                                          "int hcu_mp_wind_unused_lifecycle_main(int argc, char **argv)")
            (temp / "hcu_mp_wind_lifecycle_generated.h").write_text(lifecycle)
            expected_header = temp / "hcu_mp_wind_expected.h"
            expected = write_expected_header(expected_header, raw)
            write_collision_golden_header(temp / "hcu_collision_golden.h", [
                (MAP_ID, retail_source_collision_goldens(source_map, 1))])
            write_player_pvs_golden_header(temp / "hcu_player_pvs_golden.h", [])
            write_sound_pas_golden_header(temp / "hcu_sound_pas_golden.h", [])
            write_fog_plane_golden_header(temp / "hcu_fog_plane_golden.h", [
                (MAP_ID, retail_source_fog_plane_oracle(source_map, 1))])

            # The normal production source keeps admission UI-only. This exact
            # temporary copy expands the existing host-only allowlist to this
            # single evidence map; no production source or macro is changed.
            map_service_original = ROOT / "src/stream/hcu_map_service.c"
            map_service = map_service_original.read_text()
            old_guard = 'strcmp(entry->identity.map_name, "beavercreek") != 0) {'
            new_guard = ('strcmp(entry->identity.map_name, "beavercreek") != 0 &&\n'
                         '\t\tstrcmp(entry->identity.map_name, "damnation") != 0) {')
            self.assertEqual(map_service.count(old_guard), 1)
            map_service = map_service.replace(old_guard, new_guard)
            generated_map_service = temp / "hcu_map_service.c"
            generated_map_service.write_text(map_service)

            semantics = temp / "halo_ps2_msvc_semantics.h"
            subprocess.run([
                sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                "--output", str(semantics), "--all-inlines",
                "--tags", str(HCU / "source"), "--inlines", str(HCU / "source"),
                "--inlines", str(HCU / "port/include/xdk"),
            ], check=True, capture_output=True, text=True)
            includes = [temp, ROOT / "tests", ROOT / "tests/hcu_scenario_host_shim",
                        HCU / "port/ps2/include", HCU / "port/linux/game", HCU / "port/include",
                        HCU / "source", *[HCU / "source" / d for d in (
                            "cseries", "scenario", "structures", "cache", "tag_files", "objects",
                            "physics", "game", "interface", "math", "sound", "memory", "input")],
                        ROOT / "src", ROOT / "src/stream", ROOT / "submodules/halo-ps2/engine/src",
                        ROOT / "submodules/halo-ps2/engine/tests/hp2_world_shim",
                        Path("/usr/include")]
            sources = [ROOT / "tests/hcu_mp_wind_package_host32.c",
                       ROOT / "tests/hcu_mp_sound_environment_host32.c",
                       ROOT / "tests/hcu_game_sound_host32.c",
                       ROOT / "tests/hcu_objects_host32.c",
                       ROOT / "tests/hcu_player_pvs_host32.c",
                       ROOT / "tests/hcu_real_math_host32.c",
                       ROOT / "tests/hcu_real_math_source_host32.c",
                       ROOT / "tests/hcu_bsp3d_host32.c",
                       ROOT / "tests/hcu_geometry_source_host32.c"]
            # CE header inline implementations are TU-local in this host
            # profile. Add narrowly named support shims to the isolated
            # fixture, then rewrite only those calls in the geometry/wind TUs.
            sources += [HCU / "source" / p for p in (
                "scenario/scenario.c", "scenario/wind.c", "math/random_math.c",
                "sound/sound_environment_definitions.c", "tag_files/tag_files.c",
                "memory/data.c", "math/integer_math.c", "physics/collisions.c",
                "physics/collision_bsp.c", "physics/bsp2d.c")]
            sources += [HCU / "port/ps2/src" / p for p in (
                "ps2_animation_trace.c", "ps2_cache.c", "ps2_ctag.c", "ps2_cbsp.c")]
            sources += [HCU / "port/linux/game" / f"tag_schema_{p}.c" for p in (
                "groups", "collision", "models", "objects", "render", "effects", "scenario")]
            sources += [ROOT / "src/stream" / f"{p}.c" for p in (
                "hcu_map_catalog", "ctag_mount", "ctag_ps2_backend", "cbsp_catalog",
                "ctag_resource_index", "ctag_map_source", "sha256", "hmap",
                "hcu_asset_profile", "hcu_profile_mount", "hcu_profile_metadata")]
            sources += [generated_map_service]
            sources += [ROOT / "submodules/halo-ps2/engine/src" / p for p in (
                "world/section.c", "stream/hp2.c", "stream/file.c", "core/mem.c")]
            for source_path, alias in (
                    (ROOT / "tests/hcu_objects_host32.c", "hcu_wind_objects_halo_ce_random"),
                    (ROOT / "tests/hcu_player_pvs_host32.c", "hcu_wind_pvs_halo_ce_random"),
                    (ROOT / "tests/hcu_bsp3d_host32.c", "hcu_wind_bsp_halo_ce_random")):
                text = source_path.read_text()
                generated = temp / source_path.name
                generated.write_text(f"#define halo_ce_random {alias}\n" + text)
                sources[sources.index(source_path)] = generated
            # The production CE wind TU emits this header inline under a
            # private name but calls the regular external spelling. Match the
            # established isolated host fixture seam: its wrapper delegates
            # to the actual CE inline, avoiding a hand-copied polynomial.
            wind_path = HCU / "source/scenario/wind.c"
            wind_text = wind_path.read_text().replace(
                "uniform_cubic_spline_vector3d(",
                "wind_uniform_cubic_spline_vector3d_inline(")
            generated_wind = temp / "wind_hcu_mp.c"
            generated_wind.write_text(wind_text)
            sources[sources.index(wind_path)] = generated_wind
            generated_real_math = temp / "hcu_real_math_source_host32.c"
            generated_real_math.write_text(
                "#define global_projection3d_mappings hcu_mp_projection3d_mappings\n"
                "#define fast_vector_intersects_sphere hcu_mp_fast_vector_intersects_sphere\n"
                f'#include "{ROOT / "tests/hcu_real_math_source_host32.c"}"\n')
            sources[sources.index(ROOT / "tests/hcu_real_math_source_host32.c")] = generated_real_math
            executable, link_map = temp / "mp-wind", temp / "mp-wind.map"
            command = [shutil.which("gcc"), *flags(), "-fshort-wchar", "-std=gnu99",
                       "-fms-extensions", "-fcommon", "-fwrapv", "-fgnu89-inline",
                       "-ffunction-sections",
                       "-fdata-sections", "-fno-strict-aliasing", "-fno-delete-null-pointer-checks",
                       "-DHCU_BSP_RETAIL_INTEGRATION=1", "-DHALO_PS2=1",
                       "-DHALO_PS2_M2_ANIMATION_TRACE=1", "-DHCU_M2_MP_HOST_ORACLE=1",
                       "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                       "-include", str(semantics), "-w", *["-I" + str(p) for p in includes],
                       "-Wl,--gc-sections", "-Wl,--wrap=read",
                       "-Wl,--wrap=ps2_cache_release_map_owner",
                       "-Wl,--wrap=world_visit_section_with_scratch",
                       "-Wl,-Map=" + str(link_map), *map(str, sources), "-lm", "-o", str(executable)]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            self.assertNotIn("w uniform_cubic_spline_vector3d", link_map.read_text(),
                             "CE inline spline remained weak/unresolved")
            for symbol in ("wind_initialize_for_new_map", "wind_update",
                           "scenario_get_current_from_weather_palette", "tag_get",
                           "scenario_load", "hcu_map_service_init_with_arenas"):
                self.assertIn(symbol, link_map.read_text(),
                              f"linked fixture omitted real CE/loader symbol {symbol}")

            # Scenario map identity is catalog-checked independently from the
            # scenario tag path. The BSP file offset/size derive from raw map.
            index = tagindex.TagIndex.read(source_map)
            tag_region, _tag_base, _source = read_xbox_tag_region(source_map)
            location = bsp.locate(index, tag_region,
                                  mapinfo.read_header(source_map).decompressed_size)[0]
            retained = ROOT / "build/m2-mp-wind-package"
            retained.mkdir(parents=True, exist_ok=True)
            retained_package = retained / "damnation-all-bsps.hp2"
            retained_package.write_bytes(package)
            shutil.copy2(executable, retained / "mp-wind")
            shutil.copy2(link_map, retained / "mp-wind.map")
            run = subprocess.run([str(executable), str(assets.parent) + "/",
                                  str(location.file_offset), str(location.size)],
                                 capture_output=True, text=True)
            (retained / "run.log").write_text(run.stdout + run.stderr)
            (retained / "manifest.json").write_text(json.dumps({
                "fixture": "damnation-package-relocated-real-ce-wind",
                "parent_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "hcu_commit": subprocess.check_output(
                    ["git", "-C", str(HCU), "rev-parse", "HEAD"], text=True).strip(),
                "halo_ps2_commit": subprocess.check_output(
                    ["git", "-C", str(ROOT / "submodules/halo-ps2"),
                     "rev-parse", "HEAD"], text=True).strip(),
                "source_map_sha256": sha256_bytes(source_map.read_bytes()),
                "schema_elf_sha256": sha256_bytes(schema_elf.read_bytes()),
                "package_sha256": sha256_bytes(package),
                "package_bytes": len(package),
                "raw_bsp_sha256": raw["raw_bsp_sha256"],
                "raw_bsp_bytes": raw["raw_bsp_bytes"],
                "weather_palette_count": len(raw["palette"]),
                "weather_datums": [row["datum"] for row in raw["palette"]],
                "cluster_count": raw["cluster_count"],
                "cluster_weather_indices": raw["cluster_weather_indices"],
                "bsp_file_offset": location.file_offset,
                "bsp_bytes": location.size,
                "link_success": True,
                "execution_status": ("sandbox-sigsys" if run.returncode in (-31, 159)
                                     else run.returncode),
                "stdout": run.stdout,
                "stderr": run.stderr,
            }, indent=2) + "\n")
            if run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ce-mp-wind map=damnation bsp=0 palette_count=2 cluster_count=12", run.stdout)
            self.assertIn("none_entry=zero current=", run.stdout)
            self.assertIn("repeat=stable relocated=passed status=passed", run.stdout)
            self.assertIn(
                "mp-bsp-atomicity injected candidate B000 write failure restored old BSP; "
                "CE globals, owner bytes/cursors, and source handle preserved", run.stdout)
            self.assertIn(
                "mp-bsp-atomicity same-process replacement retry and owner/source unload passed",
                run.stdout)

            source_files = sources + [ROOT / "tests/hcu_mp_wind_package_host32.c",
                ROOT / "tests/hcu_mp_bsp_failure_atomicity_check.h",
                ROOT / "tests/test_hcu_mp_wind_package.py", common_original,
                ROOT / "tests/hcu_ce_map_lifecycle_main.c", map_service_original,
                HCU / "source/scenario/wind.c", HCU / "source/math/random_math.c",
                schema_elf]
            source_hashes = {}
            for path in source_files:
                if path.is_file() and path.is_relative_to(ROOT):
                    source_hashes[str(path.relative_to(ROOT))] = sha256_bytes(path.read_bytes())
            generated = {
                "common_fixture": sha256_bytes((temp / "hcu_scenario_bsp_switch_main.c").read_bytes()),
                "lifecycle_fixture": sha256_bytes((temp / "hcu_mp_wind_lifecycle_generated.h").read_bytes()),
                "host_only_map_service": sha256_bytes(generated_map_service.read_bytes()),
                "expected_wind_inputs": sha256_bytes(expected_header.read_bytes()),
            }
            manifest = {
                "status": "passed", "scope": "Damnation multiplayer BSP only; campaign excluded",
                "native_ilp32": True, "ee_evidence": False,
                "ce_actual_wind_init_update_current": True,
                "ce_mp_bsp_replacement_failure_atomicity": True,
                "failed_candidate_written_before_rollback": True,
                "old_bsp_globals_owner_bytes_cursors_and_source_handle_preserved": True,
                "same_process_replacement_retry_passed": True,
                "owner_source_unload_after_retry_passed": True,
                "run_returncode": run.returncode,
                "execution_status": run.returncode,
                "run_stdout": run.stdout,
                "run_stderr": run.stderr,
                "map_source_sha256": sha256_bytes(source_map.read_bytes()),
                "raw_bsp_sha256": raw["raw_bsp_sha256"],
                "raw_bsp_bytes": raw["raw_bsp_bytes"],
                "schema_elf_sha256": sha256_bytes(schema_elf.read_bytes()),
                "package_sha256": sha256_bytes(package),
                "package_summary": package_summary,
                "elf_sha256": sha256_bytes(executable.read_bytes()),
                "link_map_sha256": sha256_bytes(link_map.read_bytes()),
                "run_log_sha256": sha256_bytes((run.stdout + run.stderr).encode()),
                "expected_vectors": expected,
                "pins": {
                    name: subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                                  text=True).strip()
                    for name, path in (("parent", ROOT), ("hcu", HCU),
                                       ("halo_ps2", ROOT / "submodules/halo-ps2"))
                },
                "generated_fixture_sha256": generated,
                "source_sha256": source_hashes,
                "host_only_admission_override": "generated temporary copy admits only Damnation under HCU_M2_MP_HOST_ORACLE; production map-service source is unchanged",
                "limits": ["Host ILP32 only; no EE/PCSX2 evidence.",
                           "Uses a historical schema ELF for this diagnostic package, recorded by hash.",
                           "No weather-particle simulation, render cadence, co-op/bot concurrency, or target capacity claim."],
            }
            (retained / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
