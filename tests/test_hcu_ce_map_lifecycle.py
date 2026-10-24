"""Compose CE scenario lifecycle with the production parent map service."""
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
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402
from test_hcu_scenario_bsp_switch import (  # noqa: E402
    retail_source_collision_goldens,
    write_collision_golden_header,
    write_player_pvs_golden_header,
    write_sound_pas_golden_header,
    write_fog_plane_golden_header,
)
from hcu_profile_validate import parse_package, validate_files  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402

HCP2_UI_PACKAGE_SHA256 = "4ad8b57b7515b074d16d2b89e4f1787a9e37d6f6ab6127ababe9ac1d40a72ed7"
HCP2_UI_MANIFEST_SHA256 = "a94a3f2f4aeafefce71aa533e5914960190b35c7625c94f288842b5980866633"


class HcuCeMapLifecycleTests(unittest.TestCase):
    def test_real_ce_load_unload_and_same_map_reload(self):
        package = ROOT / "build/hcu-parent-link-probe/maps/ui-with-bsp.hp2"
        source_map = ROOT / "build/retail-maps/decompressed/ui.map"
        if not package.is_file() or not source_map.is_file():
            self.skipTest("build the audited UI HP2 package and decompressed ui.map")
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC unavailable for host ILP32 CE fixture")

        profile_dir = ROOT / os.environ.get(
            "HCU_C2_UI_PROFILE_DIR", "build/m2-ce-map-lifecycle-host-hcp2/producer-ui-verified")
        profile_source = profile_dir / "ui.hcp"
        manifest_source = profile_dir / "ui.json"
        schema_elf = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
        if not profile_source.is_file() or not manifest_source.is_file() or not schema_elf.is_file():
            self.skipTest("pinned C2 UI HCP2 package, manifest, and schema ELF are required")
        source_manifest_bytes = manifest_source.read_bytes()
        self.assertEqual(hashlib.sha256(source_manifest_bytes).hexdigest(), HCP2_UI_MANIFEST_SHA256,
                         "selected HCP2 UI manifest changed; update the fixture pin explicitly")
        profile_manifest = json.loads(source_manifest_bytes)
        self.assertEqual(profile_manifest.get("package_sha256"), HCP2_UI_PACKAGE_SHA256)
        self.assertEqual(profile_manifest.get("profile", {}).get("id"), 1)
        self.assertEqual(profile_manifest.get("profile", {}).get("scenario", {}).get("path"),
                         "levels\\ui\\ui")
        self.assertEqual(profile_manifest.get("schema_elf_sha256"),
                         hashlib.sha256(schema_elf.read_bytes()).hexdigest(),
                         "HCP2 manifest must pin the exact schema ELF used by this fixture")
        artifact_dir = ROOT / "build/m2-ce-map-lifecycle-host-hcp2"
        profile_artifacts = artifact_dir / "profile-input"
        profile_artifacts.mkdir(parents=True, exist_ok=True)
        profile_package = profile_artifacts / "ui.hcp"
        profile_manifest_path = profile_artifacts / "ui.json"
        shutil.copyfile(profile_source, profile_package)
        shutil.copyfile(manifest_source, profile_manifest_path)
        self.assertEqual(hashlib.sha256(profile_package.read_bytes()).hexdigest(),
                         HCP2_UI_PACKAGE_SHA256,
                         "staged HCP2 UI package changed; fixture input must stay manifest-pinned")
        self.assertEqual(hashlib.sha256(profile_manifest_path.read_bytes()).hexdigest(),
                         HCP2_UI_MANIFEST_SHA256)
        schema_manifest = SchemaManifest(Elf32(schema_elf)).build()
        with tempfile.TemporaryDirectory() as schema_temp:
            schema_path = Path(schema_temp) / "schema.json"
            schema_path.write_text(json.dumps(schema_manifest, sort_keys=True))
            validated_profile = validate_files(
                profile_package, profile_manifest_path, schema_path,
                expected_package_sha256=HCP2_UI_PACKAGE_SHA256,
                expected_profile_id=profile_manifest["profile"]["id"],
                expected_scenario=profile_manifest["profile"]["scenario"]["path"],
            )
        self.assertEqual(validated_profile["package_sha256"], HCP2_UI_PACKAGE_SHA256)
        package_bytes = profile_package.read_bytes()
        magic, version, header_size, profile_id, physical_count, directory, directory_size, total = struct.unpack_from(
            "<4s7I", package_bytes)
        self.assertEqual((magic, version, header_size, profile_id, total),
                         (b"HCP2", 2, 32, profile_manifest["profile"]["id"], len(package_bytes)))
        self.assertEqual(directory_size, physical_count * 96)
        decoded_profile = parse_package(package_bytes,
            expected_package_sha256=HCP2_UI_PACKAGE_SHA256,
            expected_profile_id=profile_manifest["profile"]["id"])
        logical_chunks = decoded_profile["directory"]
        expected_chunks = [(row["type"], row["id"], row["size"], bytes.fromhex(row["sha256"]))
                           for row in logical_chunks]
        first_payload_offset = struct.unpack_from("<I", package_bytes, directory + 8)[0]
        self.assertEqual(physical_count, len(decoded_profile["segments"]))
        self.assertEqual(len(logical_chunks), validated_profile["media_chunk_count"] + 2)
        profile_sha = hashlib.sha256(package_bytes).digest()
        def c_array(data):
            return ",".join(f"0x{byte:02x}" for byte in data)
        expectation_header = [
            "#ifndef HCU_HCP2_REAL_PROFILE_EXPECTATIONS_H",
            "#define HCU_HCP2_REAL_PROFILE_EXPECTATIONS_H",
            "typedef struct { unsigned int type, id, size; unsigned char sha256[32]; } hcu_hcp2_expected_chunk;",
            f"#define HCU_HCP2_PROFILE_VERSION {version}u",
            f"#define HCU_HCP2_PROFILE_ID {profile_id}u",
            f"#define HCU_HCP2_PACKAGE_BYTES {len(package_bytes)}u",
            f"#define HCU_HCP2_PHYSICAL_RECORD_COUNT {physical_count}u",
            f"#define HCU_HCP2_LOGICAL_CHUNK_COUNT {len(logical_chunks)}u",
            f"#define HCU_HCP2_PROFILE_PATH {json.dumps(str(profile_package))}",
            f"#define HCU_HCP2_FIRST_PAYLOAD_OFFSET {first_payload_offset}u",
            f"static const unsigned char hcu_hcp2_package_sha256[32] = {{{c_array(profile_sha)}}};",
            "static const hcu_hcp2_expected_chunk hcu_hcp2_expected_chunks[HCU_HCP2_LOGICAL_CHUNK_COUNT] = {",
        ]
        expectation_header.extend(
            f"{{{kind}u,{chunk_id}u,{size}u,{{{c_array(digest)}}}}},"
            for kind, chunk_id, size, digest in expected_chunks)
        expectation_header.extend(["};", "#endif", ""])

        sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
        from halo2ps2 import hp2
        ui_package = hp2.parse(package.read_bytes())
        owner_failure_cursor = 0
        for section_tag in ("HMAP", "CRNG", "CBIX"):
            payload_size = len(ui_package.read(section_tag))
            owner_failure_cursor = (owner_failure_cursor + 63) & ~63
            owner_failure_cursor += payload_size
        ctag_payload = ui_package.read("CTAG")
        relocation_count = struct.unpack_from("<I", ctag_payload, 16)[0]
        relocation_start = (owner_failure_cursor + 3) & ~3
        relocation_bytes = relocation_count * 4
        owner_failure_capacity = relocation_start + relocation_bytes - 1
        self.assertGreater(relocation_count, 0)
        self.assertLess(owner_failure_capacity, 16 * 1024 * 1024)

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            semantics = temp / "halo_ps2_msvc_semantics.h"
            (temp / "hcu_hcp2_real_profile_expectations.h").write_text("\n".join(expectation_header))
            link_map = temp / "ce-lifecycle.map"
            executable = temp / "ce-lifecycle"
            write_collision_golden_header(
                temp / "hcu_collision_golden.h",
                [(30, retail_source_collision_goldens(
                    ROOT / "build/retail-maps/decompressed/a30.map", 2)),
                 (50, retail_source_collision_goldens(
                    ROOT / "build/retail-maps/decompressed/a50.map", 4))])
            write_player_pvs_golden_header(temp / "hcu_player_pvs_golden.h", [])
            write_sound_pas_golden_header(temp / "hcu_sound_pas_golden.h", [])
            write_fog_plane_golden_header(temp / "hcu_fog_plane_golden.h", [])
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
                HCU / "source/objects", HCU / "source/physics",
                HCU / "source/game", HCU / "source/interface",
                HCU / "source/math", HCU / "source/sound", ROOT / "src",
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
                "-DHCU_HCP2_REAL_PROFILE=1",
                "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                "-include", str(semantics), "-w",
            ]
            command.extend("-I" + str(path) for path in includes)
            port = HCU / "port/ps2"
            schema = HCU / "port/linux/game"
            command.extend([
                "-Wl,--gc-sections", "-Wl,-u,scenario_load", "-Wl,-u,scenario_unload",
                "-Wl,-Map=" + str(link_map), "-Wl,--wrap=read",
                "-Wl,--wrap=ps2_cache_release_map_owner",
                "-Wl,--wrap=world_visit_section_with_scratch",
                str(ROOT / "tests/hcu_ce_map_lifecycle_main.c"),
                str(port / "src/ps2_animation_trace.c"),
                str(HCU / "source/scenario/scenario.c"),
                str(HCU / "source/tag_files/tag_files.c"),
                str(port / "src/ps2_cache.c"), str(port / "src/ps2_ctag.c"),
                str(port / "src/ps2_cbsp.c"),
                *[str(schema / name) for name in (
                    "tag_schema_groups.c", "tag_schema_collision.c", "tag_schema_models.c",
                    "tag_schema_objects.c", "tag_schema_render.c", "tag_schema_effects.c",
                    "tag_schema_scenario.c")],
                str(ROOT / "src/stream/hcu_map_service.c"),
                str(ROOT / "src/stream/hcu_profile_mount.c"),
                str(ROOT / "src/stream/hcu_profile_metadata.c"),
                str(ROOT / "src/stream/hcu_map_catalog.c"),
                str(ROOT / "src/stream/ctag_mount.c"),
                str(ROOT / "src/stream/ctag_ps2_backend.c"),
                str(ROOT / "src/stream/cbsp_catalog.c"),
                str(ROOT / "src/stream/ctag_resource_index.c"),
                str(ROOT / "src/stream/ctag_map_source.c"),
                str(ROOT / "src/stream/sha256.c"), str(ROOT / "src/stream/hmap.c"),
                str(ROOT / "src/stream/hcu_asset_profile.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/world/section.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/stream/hp2.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/stream/file.c"),
                str(ROOT / "submodules/halo-ps2/engine/src/core/mem.c"),
                "-o", str(executable),
            ])
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            map_text = link_map.read_text()
            for symbol in ("scenario_load", "scenario_unload", "scenario_tags_load",
                           "scenario_tags_unload", "cache_files_give_time_to_precache",
                           "hcu_map_service_preflight", "map_loader", "file_reader_open",
                           "ctag_mount_hp2_stream_verified_source_discover"):
                self.assertIn(symbol, map_text)

            asset_root = temp / "assets"
            maps = asset_root / "maps"
            maps.mkdir(parents=True)
            shutil.copyfile(package, maps / "ui.hp2")
            shutil.copyfile(source_map, maps / "ui.map")
            exhaustion_run = subprocess.run(
                [str(executable), str(asset_root) + "/", "owner-exhaustion",
                 str(owner_failure_capacity)], capture_output=True, text=True)
            self.assertEqual(exhaustion_run.returncode, 0,
                             exhaustion_run.stdout + exhaustion_run.stderr)
            allocation_failure = re.search(
                r"map-preflight ctag-relocation-allocation-failed bytes=(\d+) "
                r"used=(\d+) cap=(\d+)", exhaustion_run.stdout)
            self.assertIsNotNone(allocation_failure, exhaustion_run.stdout)
            self.assertEqual(tuple(map(int, allocation_failure.groups())),
                             (relocation_bytes, relocation_start,
                              owner_failure_capacity))
            self.assertIn(
                "bounded-owner exhaustion rolled back relocation allocation; "
                "same-process scenario retry passed", exhaustion_run.stdout)
            run = subprocess.run([str(executable), str(asset_root) + "/"],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("same-process deferred UI reload passed", run.stdout)
            self.assertIn(
                "late streamed CTAG visitor failure stayed unpublished; fresh remount retry passed",
                run.stdout,
            )
            self.assertIn(
                "post-copy tag validation failure released owner; full retry passed",
                run.stdout,
            )
            self.assertIn(
                "initial B000 late-write failure rolled back; retry passed",
                run.stdout,
            )
            self.assertIn(
                "rejected gameplay preflight preserved active UI snapshot",
                run.stdout,
            )
            self.assertIn(
                "same-map preflight changed only deferred request state",
                run.stdout,
            )
            for marker in (
                "trace-map-epoch failed-preflight-stable",
                "trace-map-epoch successful-remount-advanced",
                "trace-map-epoch unload-advanced",
            ):
                self.assertIn(marker, run.stdout)
            epoch_samples = re.findall(
                r"ce-lifecycle trace-map-epoch row=(\d+) epoch=(\d+)", run.stdout)
            self.assertGreaterEqual(len(epoch_samples), 5)
            self.assertIn("CE lifecycle observed damaged-media callback", run.stderr)
            retained = ROOT / "build/m2-ce-map-lifecycle-host"
            retained.mkdir(parents=True, exist_ok=True)
            retained_executable = retained / "ce-lifecycle"
            retained_map = retained / "ce-lifecycle.map"
            retained_executable.write_bytes(executable.read_bytes())
            retained_map.write_bytes(link_map.read_bytes())
            exhaustion_log = exhaustion_run.stdout + exhaustion_run.stderr
            (retained / "ce-lifecycle-owner-exhaustion.log").write_text(
                exhaustion_log)
            (retained / "ce-lifecycle.log").write_text(run.stdout + run.stderr)

            def git_head(path):
                return subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "HEAD"],
                    check=True, capture_output=True, text=True).stdout.strip()

            manifest = {
                "result": "passed",
                "fixture": "real-ce-scenario-map-service-lifecycle",
                "parent_head": git_head(ROOT),
                "hcu_head": git_head(HCU),
                "halo_ps2_head": git_head(ROOT / "submodules/halo-ps2"),
                "worktrees_dirty": True,
                "elf_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "link_map_sha256": hashlib.sha256(link_map.read_bytes()).hexdigest(),
                "ui_hp2_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                "ui_map_sha256": hashlib.sha256(source_map.read_bytes()).hexdigest(),
                "runtime_log_sha256": hashlib.sha256(
                    (run.stdout + run.stderr).encode()).hexdigest(),
                "native_ilp32": True,
                "preflight_relocation_arena_exhaustion_rejected": True,
                "preflight_relocation_arena_exhaustion_same_process_retry": True,
                "preflight_owner_capacity_bytes": owner_failure_capacity,
                "preflight_ctag_relocation_bytes": relocation_bytes,
                "preflight_ctag_relocation_aligned_start": relocation_start,
                "owner_exhaustion_log_sha256": hashlib.sha256(
                    exhaustion_log.encode()).hexdigest(),
                "post_unload_partial_read_eof_injected": True,
                "ce_tag_read_late_relocation_failure_unpublished": True,
                "same_mount_tag_read_retry": True,
                "post_copy_ce_tag_validation_failure_unpublished": True,
                "post_copy_ce_tag_validation_full_scenario_retry": True,
                "initial_ce_scenario_load_late_b000_write_failure_rolled_back": True,
                "initial_ce_scenario_load_same_process_retry": True,
                "rejected_gameplay_preflight_preserved_full_active_ui_snapshot": True,
                "same_map_preflight_only_changed_deferred_request_state": True,
                "trace_epoch_stable_on_failed_deferred_preflight": True,
                "trace_epoch_advances_on_successful_remount": True,
                "trace_epoch_advances_on_ce_unload": True,
                "trace_epoch_samples": [
                    {"row": int(row), "epoch": int(epoch)}
                    for row, epoch in epoch_samples
                ],
                "same_process_retry": True,
            }
            (retained / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n")

            stable_assets = artifact_dir / "assets"
            stable_maps = stable_assets / "maps"
            stable_maps.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package, stable_maps / "ui.hp2")
            shutil.copyfile(source_map, stable_maps / "ui.map")
            stable_assets_link = Path("/tmp") / f"hcu-c2-hcp2-{hashlib.sha256(str(artifact_dir).encode()).hexdigest()[:8]}"
            if stable_assets_link.is_symlink():
                stable_assets_link.unlink()
            stable_assets_link.symlink_to(stable_assets, target_is_directory=True)
            real_executable = artifact_dir / "ce-lifecycle"
            real_executable.write_bytes(executable.read_bytes())
            real_executable.chmod(0o755)
            real_link_map = artifact_dir / "ce-lifecycle.map"
            real_link_map.write_bytes(link_map.read_bytes())
            real_profile_run = subprocess.run(
                [str(real_executable), str(stable_assets_link) + "/", "actual-profile", str(profile_package)],
                capture_output=True, text=True)
            self.assertEqual(real_profile_run.returncode, 0,
                             real_profile_run.stdout + real_profile_run.stderr)
            self.assertIn("actual validated UI HCP identity and complete chunk inventory accepted",
                          real_profile_run.stdout)
            self.assertIn("actual UI HCP rejected for incompatible map before teardown",
                          real_profile_run.stdout)
            self.assertIn("corrupt actual UI HCP rejected before teardown",
                          real_profile_run.stdout)
            real_log = real_profile_run.stdout + real_profile_run.stderr
            (artifact_dir / "runtime.log").write_text(real_log)
            result = {
                "result": "passed",
                "scope": "exact pinned HCP2 UI identity/logical chunk inventory through CE pre-unload map service",
                "command": [str(real_executable), str(stable_assets_link) + "/", "actual-profile", str(profile_package)],
                "compile_command": command,
                "host_validation": validated_profile,
                "profile_package_sha256": hashlib.sha256(package_bytes).hexdigest(),
                "profile_manifest_sha256": hashlib.sha256(profile_manifest_path.read_bytes()).hexdigest(),
                "profile_format": "HCP2 v2",
                "profile_source_package": str(profile_source),
                "profile_source_manifest": str(manifest_source),
                "schema_elf_sha256": hashlib.sha256(schema_elf.read_bytes()).hexdigest(),
                "lifecycle_fixture_source_sha256": hashlib.sha256(
                    (ROOT / "tests/hcu_ce_map_lifecycle_main.c").read_bytes()).hexdigest(),
                "lifecycle_test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "elf_sha256": hashlib.sha256(real_executable.read_bytes()).hexdigest(),
                "link_map_sha256": hashlib.sha256(real_link_map.read_bytes()).hexdigest(),
                "runtime_log_sha256": hashlib.sha256(real_log.encode()).hexdigest(),
                "accepted_actual_package_before_teardown": True,
                "incompatible_actual_profile_rejected_before_teardown": True,
                "corrupt_actual_package_rejected_before_teardown": True,
                "active_ce_and_service_snapshot_preserved": True,
                "native_exit_code": real_profile_run.returncode,
            }
            (artifact_dir / "result.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
