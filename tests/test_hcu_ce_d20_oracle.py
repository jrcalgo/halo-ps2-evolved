"""Exercise real CE D20/B000 loading on overprovisioned host-only buffers."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tools"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402
from test_hcu_scenario_bsp_switch import (  # noqa: E402
    retail_source_collision_goldens,
    write_collision_golden_header,
    write_player_pvs_golden_header,
    write_sound_pas_golden_header,
    write_fog_plane_golden_header,
)


class HcuCeD20HostOracleTests(unittest.TestCase):
    def test_real_ce_d20_scenario_and_initial_bsp_load_unload(self):
        artifacts = ROOT / "build/m2-artifacts/d20-host-oracle-30b2a4a3"
        package = artifacts / "d20.hp2"
        source_map = ROOT / "build/retail-maps/decompressed/d20.map"
        if not package.is_file() or not source_map.is_file():
            self.skipTest("build the pinned D20 HP2 package and source map")
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC unavailable for host ILP32 CE fixture")

        sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
        from halo2ps2 import hp2
        from tools.cbsp import HEADER as CBSP_HEADER

        # Safety check: the one-map bypass is a private host-oracle define and
        # must not leak into the production R5900 profile.
        for path in (
            ROOT / "tools/ee-world.mk",
            HCU / "port/ps2/port.json",
            HCU / "port/ps2/Makefile",
        ):
            if path.is_file():
                self.assertNotIn("HCU_M2_D20_HOST_ORACLE", path.read_text())
                self.assertNotIn("HCU_M2_MP_HOST_ORACLE", path.read_text())

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            semantics = temp / "halo_ps2_msvc_semantics.h"
            link_map = temp / "ce-d20-oracle.map"
            # The shared CE scenario/BSP fixture includes these generated
            # goldens unconditionally; generate them exactly as its sibling
            # lifecycle test does.
            write_collision_golden_header(
                temp / "hcu_collision_golden.h",
                [(30, retail_source_collision_goldens(
                    ROOT / "build/retail-maps/decompressed/a30.map", 2)),
                 (50, retail_source_collision_goldens(
                    ROOT / "build/retail-maps/decompressed/a50.map", 4))])
            write_player_pvs_golden_header(temp / "hcu_player_pvs_golden.h", [])
            write_sound_pas_golden_header(temp / "hcu_sound_pas_golden.h", [])
            write_fog_plane_golden_header(temp / "hcu_fog_plane_golden.h", [])
            executable = temp / "ce-d20-oracle"
            subprocess.run([
                sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                "--output", str(semantics), "--all-inlines",
                "--tags", str(HCU / "source"),
                "--inlines", str(HCU / "source"),
                "--inlines", str(HCU / "port/include/xdk"),
            ], check=True, capture_output=True, text=True)
            includes = [
                temp, ROOT / "tests", ROOT / "tests/hcu_scenario_host_shim",
                HCU / "port/ps2/include", HCU / "port/linux/game",
                HCU / "port/include", HCU / "source", HCU / "source/cseries",
                HCU / "source/scenario", HCU / "source/structures",
                HCU / "source/cache", HCU / "source/tag_files",
                HCU / "source/math", HCU / "source/sound",
                HCU / "source/objects", HCU / "source/physics", ROOT / "src",
                ROOT / "submodules/halo-ps2/engine/src",
                ROOT / "submodules/halo-ps2/engine/tests/hp2_world_shim",
                Path("/usr/include"),
            ]
            command = [
                compiler, *host_abi32_flags(), "-fshort-wchar", "-std=gnu99",
                "-fms-extensions", "-fcommon", "-fwrapv", "-ffunction-sections",
                "-fdata-sections", "-fno-strict-aliasing",
                "-fno-delete-null-pointer-checks", "-DHCU_BSP_RETAIL_INTEGRATION=1",
                "-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
                "-DHCU_M2_D20_HOST_ORACLE=1", "-DBSP_CACHE_BYTES=16777216",
                "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                "-include", str(semantics), "-w",
            ]
            command.extend("-I" + str(path) for path in includes)
            port = HCU / "port/ps2"
            schema = HCU / "port/linux/game"
            command.extend([
                "-Wl,--gc-sections", "-Wl,-u,scenario_load",
                "-Wl,-u,scenario_unload", "-Wl,-Map=" + str(link_map),
                "-Wl,--wrap=read", "-Wl,--wrap=ps2_cache_release_map_owner",
                "-Wl,--wrap=world_visit_section_with_scratch",
                str(ROOT / "tests/hcu_ce_map_lifecycle_main.c"),
                str(port / "src/ps2_animation_trace.c"),
                str(HCU / "source/scenario/scenario.c"),
                str(HCU / "source/tag_files/tag_files.c"),
                str(port / "src/ps2_cache.c"), str(port / "src/ps2_ctag.c"),
                str(port / "src/ps2_cbsp.c"),
                *[str(schema / name) for name in (
                    "tag_schema_groups.c", "tag_schema_collision.c",
                    "tag_schema_models.c", "tag_schema_objects.c",
                    "tag_schema_render.c", "tag_schema_effects.c",
                    "tag_schema_scenario.c")],
                str(ROOT / "src/stream/hcu_map_service.c"),
                str(ROOT / "src/stream/hcu_profile_mount.c"),
                str(ROOT / "src/stream/hcu_profile_metadata.c"),
                str(ROOT / "src/stream/hcu_map_catalog.c"),
                str(ROOT / "src/stream/hcu_local_setup.c"),
                str(ROOT / "src/stream/ctag_mount.c"),
                str(ROOT / "src/stream/ctag_ps2_backend.c"),
                str(ROOT / "src/stream/cbsp_catalog.c"),
                str(ROOT / "src/stream/ctag_resource_index.c"),
                str(ROOT / "src/stream/ctag_map_source.c"),
                str(ROOT / "src/stream/hcu_asset_profile.c"),
                str(ROOT / "src/stream/sha256.c"), str(ROOT / "src/stream/hmap.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/world/section.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/stream/hp2.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/stream/file.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/core/mem.c"),
                "-o", str(executable),
            ])
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            map_text = link_map.read_text()
            for symbol in (
                "scenario_load", "scenario_unload", "scenario_tags_load",
                "hcu_map_service_preflight", "map_loader", "file_reader_open",
            ):
                self.assertIn(symbol, map_text)

            asset_root = temp / "assets"
            maps = asset_root / "maps"
            maps.mkdir(parents=True)
            shutil.copyfile(package, maps / "d20.hp2")
            shutil.copyfile(source_map, maps / "d20.map")
            run = subprocess.run(
                [str(executable), str(asset_root) + "/", "d20"],
                capture_output=True, text=True,
            )
            if run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ce-d20-oracle loaded scenario=levels\\d20\\d20", run.stdout)
            self.assertIn("B001 late-write failure restored B000", run.stdout)
            self.assertEqual(run.stdout.count("ce-d20-oracle bsp-switch index="), 4)
            self.assertIn("ce-d20-oracle scenario unload released CE globals", run.stdout)

            # Exercise the actual CE switch/rollback transaction against an
            # outer HP2 section-CRC and inner CBSP image-CRC failure for every
            # noninitial D20 BSP. Every
            # case must preserve the live B000 state and accept a same-process
            # retry after the injected package fault is removed.
            original_bytes = package.read_bytes()
            original_pack = hp2.parse(original_bytes)
            outer_runs = {}
            for bsp_index in range(1, 5):
                bsp_tag = f"B{bsp_index:03d}"
                section = original_pack.find(bsp_tag)
                outer_bad = bytearray(original_bytes)
                outer_crc_offset = hp2.HEADER_SIZE + \
                    original_pack.sections.index(section) * hp2.ENTRY_SIZE + 20
                outer_bad[outer_crc_offset] ^= 1
                case_name = f"d20-outer-crc-{bsp_tag}"
                outer_root = temp / case_name
                (outer_root / "maps").mkdir(parents=True)
                (outer_root / "maps/d20.hp2").write_bytes(outer_bad)
                shutil.copyfile(source_map, outer_root / "maps/d20.map")
                outer_run = subprocess.run(
                    [str(executable), str(outer_root) + "/", "d20", case_name],
                    capture_output=True, text=True)
                if outer_run.returncode in (-31, 159):
                    self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
                self.assertEqual(outer_run.returncode, 0,
                                 outer_run.stdout + outer_run.stderr)
                self.assertIn(f"{case_name} rejected {bsp_tag} and restored B000",
                              outer_run.stdout)
                self.assertIn("cbsp-section-visit end status=8", outer_run.stdout)
                outer_runs[bsp_tag] = (outer_bad, outer_run)

            inner_runs = {}
            for bsp_index in range(1, 5):
                bsp_tag = f"B{bsp_index:03d}"
                bad_image = bytearray(original_pack.read(bsp_tag))
                self.assertGreater(len(bad_image), CBSP_HEADER.size)
                bad_image[CBSP_HEADER.size] ^= 1
                inner_sections = [
                    (section.tag, bytes(bad_image) if section.tag == bsp_tag
                     else original_pack.read(section.tag))
                    for section in original_pack.sections
                ]
                inner_bad = hp2.build(original_pack.name, inner_sections)
                case_name = f"d20-inner-crc-{bsp_tag}"
                inner_root = temp / case_name
                (inner_root / "maps").mkdir(parents=True)
                (inner_root / "maps/d20.hp2").write_bytes(inner_bad)
                shutil.copyfile(source_map, inner_root / "maps/d20.map")
                inner_run = subprocess.run(
                    [str(executable), str(inner_root) + "/", "d20", case_name],
                    capture_output=True, text=True)
                if inner_run.returncode in (-31, 159):
                    self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
                self.assertEqual(inner_run.returncode, 0,
                                 inner_run.stdout + inner_run.stderr)
                self.assertIn(f"{case_name} rejected {bsp_tag} and restored B000",
                              inner_run.stdout)
                self.assertIn("cbsp-section-visit end status=0", inner_run.stdout)
                inner_runs[bsp_tag] = (inner_bad, inner_run)

            visitor_runs = {}
            for bsp_index in range(1, 5):
                bsp_tag = f"B{bsp_index:03d}"
                case_name = f"d20-visitor-fail-{bsp_tag}"
                visitor_run = subprocess.run(
                    [str(executable), str(asset_root) + "/", "d20", case_name],
                    capture_output=True, text=True)
                if visitor_run.returncode in (-31, 159):
                    self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
                self.assertEqual(visitor_run.returncode, 0,
                                 visitor_run.stdout + visitor_run.stderr)
                self.assertIn(f"{case_name} rejected {bsp_tag} and restored B000",
                              visitor_run.stdout)
                self.assertIn(f"{case_name} same-process retry loaded {bsp_tag}",
                              visitor_run.stdout)
                visitor_runs[bsp_tag] = visitor_run

            production_command = list(command)
            production_command.remove("-DHCU_M2_D20_HOST_ORACLE=1")
            production_command[production_command.index("-Wl,-Map=" + str(link_map))] = (
                "-Wl,-Map=" + str(temp / "ce-d20-production-guard.map"))
            production_executable = temp / "ce-d20-production-guard"
            production_command[production_command.index("-o") + 1] = str(production_executable)
            production_build = subprocess.run(
                production_command, capture_output=True, text=True)
            self.assertEqual(production_build.returncode, 0,
                             production_build.stdout + production_build.stderr)
            production_run = subprocess.run(
                [str(production_executable), str(asset_root) + "/", "d20"],
                capture_output=True, text=True)
            if production_run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(production_run.returncode, 0,
                             production_run.stdout + production_run.stderr)
            self.assertIn("production admission guard rejected d20", production_run.stdout)

            retained = ROOT / "build/m2-d20-host-oracle"
            retained.mkdir(parents=True, exist_ok=True)
            retained_executable = retained / "ce-d20-oracle"
            retained_map = retained / "ce-d20-oracle.map"
            retained_executable.write_bytes(executable.read_bytes())
            retained_map.write_bytes(link_map.read_bytes())
            (retained / "ce-d20-oracle.log").write_text(run.stdout + run.stderr)
            production_elf = retained / "ce-d20-production-guard"
            production_log = retained / "ce-d20-production-guard.log"
            production_elf.write_bytes(production_executable.read_bytes())
            production_map = retained / "ce-d20-production-guard.map"
            production_map.write_bytes((temp / "ce-d20-production-guard.map").read_bytes())
            production_log.write_text(production_run.stdout + production_run.stderr)
            crc_failure_runs = {}
            for bsp_tag, (outer_bad, outer_run) in outer_runs.items():
                stem = f"d20-{bsp_tag.lower()}-outer-crc-invalid"
                outer_package_artifact = retained / f"{stem}.hp2"
                outer_log_artifact = retained / f"{stem}.log"
                outer_package_artifact.write_bytes(outer_bad)
                outer_log_text = outer_run.stdout + outer_run.stderr
                outer_log_artifact.write_text(outer_log_text)
                crc_failure_runs[f"outer_hp2_crc_{bsp_tag}"] = {
                    "package_sha256": hashlib.sha256(outer_bad).hexdigest(),
                    "package_artifact": outer_package_artifact.name,
                    "log_sha256": hashlib.sha256(outer_log_text.encode()).hexdigest(),
                    "log_artifact": outer_log_artifact.name,
                    "asserted_hp2_status": "HP2_ERR_CRC",
                    "b000_restored": True,
                }
            for bsp_tag, (inner_bad, inner_run) in inner_runs.items():
                stem = f"d20-{bsp_tag.lower()}-inner-crc-invalid"
                inner_package_artifact = retained / f"{stem}.hp2"
                inner_log_artifact = retained / f"{stem}.log"
                inner_package_artifact.write_bytes(inner_bad)
                inner_log_text = inner_run.stdout + inner_run.stderr
                inner_log_artifact.write_text(inner_log_text)
                crc_failure_runs[f"inner_cbsp_crc_{bsp_tag}"] = {
                    "package_sha256": hashlib.sha256(inner_bad).hexdigest(),
                    "package_artifact": inner_package_artifact.name,
                    "log_sha256": hashlib.sha256(inner_log_text.encode()).hexdigest(),
                    "log_artifact": inner_log_artifact.name,
                    "asserted_hp2_status": "HP2_OK",
                    "ce_cbsp_validation_rejected": True,
                    "b000_restored": True,
                }
            visitor_abort_runs = {}
            for bsp_tag, visitor_run in visitor_runs.items():
                log_text = visitor_run.stdout + visitor_run.stderr
                log_artifact = retained / f"d20-{bsp_tag.lower()}-visitor-abort.log"
                log_artifact.write_text(log_text)
                visitor_abort_runs[bsp_tag] = {
                    "source_package_sha256": hashlib.sha256(
                        package.read_bytes()).hexdigest(),
                    "log_sha256": hashlib.sha256(log_text.encode()).hexdigest(),
                    "log_artifact": log_artifact.name,
                    "late_partial_write_failure": True,
                    "b000_restored": True,
                    "same_process_retry_succeeded": True,
                }
            manifest = {
                "result": "passed",
                "fixture": "real-ce-d20-bsp-host-lifecycle-and-crc-rollback-oracle",
                "host_only_admission_macro": True,
                "production_profile_macro_absent": True,
                "claim_scope": "host lifecycle only; not EE capacity or gameplay fit",
                "all_five_ce_bsp_switches_passed": True,
                "b001_partial_write_failure_restored_b000": True,
                "late_visitor_abort_failed_bsp_indices": [1, 2, 3, 4],
                "late_visitor_abort_retry_succeeded_bsp_indices": [1, 2, 3, 4],
                "d20_outer_hp2_crc_failure_restored_b000": True,
                "d20_outer_hp2_crc_failed_bsp_indices": [1, 2, 3, 4],
                "d20_inner_cbsp_crc_failure_restored_b000": True,
                "d20_inner_cbsp_crc_failed_bsp_indices": [1, 2, 3, 4],
                "lifecycle_source_sha256": hashlib.sha256(
                    (ROOT / "tests/hcu_ce_map_lifecycle_main.c").read_bytes()).hexdigest(),
                "python_test_source_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()).hexdigest(),
                "elf_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "link_map_sha256": hashlib.sha256(link_map.read_bytes()).hexdigest(),
                "d20_hp2_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                "d20_map_sha256": hashlib.sha256(source_map.read_bytes()).hexdigest(),
                "runtime_log_sha256": hashlib.sha256(
                    (run.stdout + run.stderr).encode()).hexdigest(),
                "production_profile_rejected_d20": True,
                "production_guard_elf_sha256": hashlib.sha256(
                    production_executable.read_bytes()).hexdigest(),
                "production_guard_log_sha256": hashlib.sha256(
                    (production_run.stdout + production_run.stderr).encode()).hexdigest(),
                "crc_failure_runs": crc_failure_runs,
                "late_visitor_abort_runs": visitor_abort_runs,
            }
            (retained / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
