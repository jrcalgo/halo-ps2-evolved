#!/usr/bin/env python3
"""Build/run actual HCU map-service preflight with fixed PS2-sized MP arenas.

The binary must run as native ILP32. On sandboxed hosts where that syscall is
blocked, compilation still qualifies and the script reports the exact command
for an unsandboxed/native run; it does not substitute Python envelope checks.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools"),
                str(ROOT / "submodules/halo-ps2/tools")]
import test_hcu_mp_capacity as mp
from host_abi32 import flags
from test_hcu_scenario_bsp_switch import (
    retail_source_fog_none_oracle,
    retail_source_fog_plane_oracle,
    write_fog_plane_golden_header,
    write_sound_pas_golden_header,
)

PACKAGES = {
    "beavercreek": ROOT / "build/m2-mp-extra/beavercreek-all-bsps.hp2",
    "bloodgulch": ROOT / "build/retail-maps/bloodgulch-with-bsps.hp2",
    "boardingaction": ROOT / "build/m2-mp-all-map-packages/boardingaction-all-bsps.hp2",
    "carousel": ROOT / "build/m2-mp-all-map-packages/carousel-all-bsps.hp2",
    "chillout": ROOT / "build/m2-mp-all-map-packages/chillout-all-bsps.hp2",
    "damnation": ROOT / "build/m2-mp-extra/damnation-wind-all-bsps.hp2",
    "hangemhigh": ROOT / "build/m2-mp-all-map-packages/hangemhigh-all-bsps.hp2",
    "longest": ROOT / "build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2",
    "prisoner": ROOT / "build/m2-mp-extra/prisoner-all-bsps.hp2",
    "putput": ROOT / "build/m2-mp-all-map-packages/putput-all-bsps.hp2",
    "ratrace": ROOT / "build/m2-mp-all-map-packages/ratrace-all-bsps.hp2",
    "sidewinder": ROOT / "build/m2-mp-all-map-packages/sidewinder-all-bsps.hp2",
    "wizard": ROOT / "build/m2-mp-all-map-packages/wizard-all-bsps.hp2",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if set(PACKAGES) != set(mp.MP_MAPS):
        raise SystemExit("expected exact stock 13-map package set")
    for name, package in PACKAGES.items():
        source = ROOT / f"build/retail-maps/decompressed/{name}.map"
        if sha(package) != mp.MP_PACKAGE_SHA256[name]:
            raise SystemExit(f"package pin mismatch: {name}")
        if sha(source) != mp.MP_SOURCE_SHA256[name]:
            raise SystemExit(f"retail source-map pin mismatch: {name}")

    with tempfile.TemporaryDirectory(prefix="hcu-mp-target-preflight-") as tmp_text:
        tmp = Path(tmp_text)
        common = (ROOT / "tests/hcu_scenario_bsp_switch_main.c").read_text()
        replacements = {
            "#define TAG_CACHE_BYTES (16u * 1024u * 1024u)":
                "#define TAG_CACHE_BYTES (2u * 1024u * 1024u)",
            "#define BSP_CACHE_BYTES (8u * 1024u * 1024u)":
                "#define BSP_CACHE_BYTES (4u * 1024u * 1024u)",
            "#define OWNER_ARENA_BYTES (16u * 1024u * 1024u)":
                "#define OWNER_ARENA_BYTES (1024u * 1024u)",
            "#define BSP_SCRATCH_BYTES (16u * 1024u * 1024u)":
                "#define BSP_SCRATCH_BYTES (512u * 1024u)",
            "retail_section_scratch_bytes[131072]":
                "retail_section_scratch_bytes[524288]",
            "retail_claims_bytes[4u * 1024u * 1024u]":
                "retail_claims_bytes[786432u]",
        }
        for old, new in replacements.items():
            if common.count(old) != 1:
                raise SystemExit(f"expected one capacity declaration: {old}")
            common = common.replace(old, new)
        common = common.replace('"../submodules/', '"' + str(ROOT / "submodules") + "/")
        (tmp / "hcu_scenario_bsp_switch_main.c").write_text(common)

        lifecycle = (ROOT / "tests/hcu_ce_map_lifecycle_main.c").read_text()
        if lifecycle.count("int main(int argc, char **argv)") != 1:
            raise SystemExit("unexpected lifecycle main definition")
        lifecycle = lifecycle.replace("int main(int argc, char **argv)",
                                      "int unused_lifecycle_main(int argc, char **argv)")
        (tmp / "hcu_mp_target_preflight_lifecycle.h").write_text(lifecycle)
        for name in ("hcu_collision_golden.h", "hcu_player_pvs_golden.h",
                     "hcu_mp_pvs_golden.h"):
            source = ROOT / "build/m2-mp-host-13-collision" / name
            if not source.is_file():
                raise SystemExit(f"missing generated compile fixture {source}")
            shutil.copy2(source, tmp / name)
        write_sound_pas_golden_header(tmp / "hcu_sound_pas_golden.h", [])
        # The copied fog fixture predates the fog-none golden type that the
        # shared scenario fixture now compiles; regenerate it exactly as the
        # 13-map capacity test does (same map ids, plane and none rows).
        map_id_by_name = {name: 101 + i for i, name in enumerate(mp.MP_MAPS)}
        fog_maps = {name: ROOT / f"build/retail-maps/decompressed/{name}.map"
                    for name in mp.MP_MAPS}
        write_fog_plane_golden_header(
            tmp / "hcu_fog_plane_golden.h",
            [(map_id_by_name[name], retail_source_fog_plane_oracle(fog_maps[name], 1))
             for name in mp.MP_MAPS],
            none_rows=[(map_id_by_name[name], retail_source_fog_none_oracle(fog_maps[name], 1))
                       for name in mp.MP_MAPS])

        map_service = (ROOT / "src/stream/hcu_map_service.c").read_text()
        old_gate = '\t\tstrcmp(entry->identity.map_name, "beavercreek") != 0) {'
        if map_service.count(old_gate) != 1:
            raise SystemExit("MP host-oracle gate changed; re-audit patch seam")
        new_gate = '\t\tstrcmp(entry->identity.map_name, "beavercreek") != 0'
        for name in mp.MP_MAPS:
            if name not in ("longest", "bloodgulch", "beavercreek"):
                new_gate += f' &&\n\t\tstrcmp(entry->identity.map_name, "{name}") != 0'
        map_service = map_service.replace(old_gate, new_gate + ") {")
        # The production callback convention reports outer HP2 IO when the
        # visitor rejects a chunk. Preserve the inner validator status only
        # in this generated diagnostic copy so the test can distinguish the
        # expected image-capacity bound from unrelated visitor failures.
        status_edits = (
            ("\tint initialized;\n\tint failed;\n} ctag_first_pass;",
             "\tint initialized;\n\tint failed;\n"
             "\tps2_ctag_status rejection_status;\n} ctag_first_pass;"),
            ("\t\tif (status != PS2_CTAG_OK) {\n\t\t\tpass->failed = 1;",
             "\t\tif (status != PS2_CTAG_OK) {\n"
             "\t\t\tpass->rejection_status = status;\n\t\t\tpass->failed = 1;"),
            ("\tif (ok) {\n\t\tresult->image_size = info.image_size;",
             "\tif (!ok && first_pass.failed &&\n"
             "\t\tfirst_pass.rejection_status != PS2_CTAG_OK)\n"
             "\t\tstatus = first_pass.rejection_status;\n"
             "\tif (ok) {\n\t\tresult->image_size = info.image_size;"),
        )
        for old, new in status_edits:
            if map_service.count(old) != 1:
                raise SystemExit("validator-status instrumentation seam changed")
            map_service = map_service.replace(old, new)
        (tmp / "hcu_map_service_host.c").write_text(map_service)

        semantics = tmp / "halo_ps2_msvc_semantics.h"
        subprocess.run([sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                        "--output", str(semantics), "--all-inlines", "--tags",
                        str(HCU / "source"), "--inlines", str(HCU / "source"),
                        "--inlines", str(HCU / "port/include/xdk")], check=True,
                       capture_output=True, text=True)
        includes = [tmp, ROOT / "tests", ROOT / "tests/hcu_scenario_host_shim",
                    HCU / "port/ps2/include", HCU / "port/linux/game",
                    HCU / "port/include", HCU / "source",
                    *[HCU / "source" / d for d in (
                        "cseries", "scenario", "structures", "cache", "tag_files",
                        "objects", "physics", "game", "interface", "math", "sound",
                        "memory", "input")], ROOT / "src",
                    ROOT / "submodules/halo-ps2/engine/src",
                    ROOT / "submodules/halo-ps2/engine/tests/hp2_world_shim",
                    Path("/usr/include")]
        sources = [ROOT / "tests/hcu_mp_target_preflight_main.c",
                   ROOT / "tests/hcu_objects_host32.c",
                   ROOT / "tests/hcu_game_sound_host32.c",
                   ROOT / "tests/hcu_player_pvs_host32.c",
                   ROOT / "tests/hcu_real_math_host32.c",
                   ROOT / "tests/hcu_bsp3d_host32.c"]
        sources += [HCU / "source" / p for p in (
            "scenario/scenario.c", "sound/sound_environment_definitions.c",
            "tag_files/tag_files.c", "memory/data.c", "math/integer_math.c",
            "physics/collisions.c", "physics/collision_bsp.c", "physics/bsp2d.c")]
        sources += [HCU / "port/ps2/src" / p for p in (
            "ps2_animation_trace.c", "ps2_cache.c", "ps2_ctag.c", "ps2_cbsp.c")]
        sources += [HCU / "port/linux/game" / f"tag_schema_{p}.c" for p in (
            "groups", "collision", "models", "objects", "render", "effects", "scenario")]
        sources += [tmp / "hcu_map_service_host.c"]
        sources += [ROOT / "src/stream" / f"{p}.c" for p in (
            "hcu_map_catalog", "ctag_mount", "ctag_ps2_backend", "cbsp_catalog",
            "ctag_resource_index", "ctag_map_source", "sha256", "hmap",
            "hcu_asset_profile", "hcu_profile_mount", "hcu_profile_metadata")]
        sources += [ROOT / "submodules/halo-ps2/engine/src" / p for p in (
            "world/section.c", "stream/hp2.c", "stream/file.c", "core/mem.c")]
        exe, linkmap = tmp / "mp-target-preflight", tmp / "mp-target-preflight.map"
        cmd = [shutil.which("gcc"), *flags(), "-fshort-wchar", "-std=gnu99",
               "-fms-extensions", "-fcommon", "-fwrapv", "-ffunction-sections",
               "-fdata-sections", "-fno-strict-aliasing",
               "-fno-delete-null-pointer-checks", "-DHCU_BSP_RETAIL_INTEGRATION=1",
               "-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
               "-DHCU_M2_MP_HOST_ORACLE=1", "-include",
               str(ROOT / "tests/hcu_scenario_host32_prefix.h"), "-include",
               str(semantics), "-w", *["-I" + str(p) for p in includes],
               "-Wl,--gc-sections", "-Wl,--wrap=read",
               "-Wl,-Map=" + str(linkmap), *map(str, sources), "-lm", "-o", str(exe)]
        build = subprocess.run(cmd, capture_output=True, text=True)
        if build.returncode:
            print(build.stdout + build.stderr, file=sys.stderr)
            return build.returncode

        retained = ROOT / "build/hcu-mp-target-preflight"
        assets = retained / "assets/maps"
        assets.mkdir(parents=True, exist_ok=True)
        for name, package in PACKAGES.items():
            for suffix, target in ((".hp2", package), (".map", ROOT /
                    f"build/retail-maps/decompressed/{name}.map")):
                link = assets / (name + suffix)
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(target)
        retained_exe = retained / "mp-target-preflight"
        retained_map = retained / "mp-target-preflight.map"
        shutil.copy2(exe, retained_exe)
        shutil.copy2(linkmap, retained_map)
        relative_assets_root = os.path.relpath(assets.parent, ROOT) + "/"
        run = subprocess.run([str(retained_exe), relative_assets_root],
                             cwd=ROOT, capture_output=True, text=True)
        if run.returncode in (-31, 159):
            print("native ILP32 execution blocked (SIGSYS); binary compiled successfully")
            print("run command:", str(retained_exe), relative_assets_root)
            return 77
        if run.returncode:
            print(run.stdout + run.stderr, file=sys.stderr)
            return run.returncode
        expected = 26
        rows = run.stdout.count("result=reject expected=ctag-image-capacity")
        status_rows = run.stdout.count("ctag-stream-rejected status=3 failed=1")
        if rows != expected or status_rows != expected:
            print(run.stdout, file=sys.stderr)
            raise SystemExit(f"expected {expected} capacity rejections, got rows={rows} status={status_rows}")
        run_log = retained / "run.log"
        run_log.write_text(run.stdout)
        generated_sha = {
            "hcu_scenario_bsp_switch_main.c": sha(tmp / "hcu_scenario_bsp_switch_main.c"),
            "hcu_mp_target_preflight_lifecycle.h": sha(tmp / "hcu_mp_target_preflight_lifecycle.h"),
            "hcu_map_service_host.c": sha(tmp / "hcu_map_service_host.c"),
            "halo_ps2_msvc_semantics.h": sha(semantics),
        }
        manifest = {
            "status": "passed-negative-capacity-gate",
            "scope": "13 pinned stock MP maps, 2 production-path preflight attempts each; no gameplay or BSP query",
            "native_ilp32": True,
            "ee_evidence": False,
            "attempts": 26,
            "ctag_capacity_status": 3,
            "ctag_capacity_status_name": "PS2_CTAG_ERR_BOUNDS (CTAG image exceeds configured maximum)",
            "profile": {"tag": 2097152, "bsp": 4194304, "owner": 1048576,
                        "scratch": 524288, "claims": 786432},
            "parent_head": subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
            "hcu_head": subprocess.check_output(
                ["git", "-C", str(HCU), "rev-parse", "HEAD"], text=True).strip(),
            "halo_ps2_head": subprocess.check_output(
                ["git", "-C", str(ROOT / "submodules/halo-ps2"), "rev-parse", "HEAD"],
                text=True).strip(),
            "runner_sha256": sha(Path(__file__).resolve()),
            "test_driver_sha256": sha(ROOT / "tests/hcu_mp_target_preflight_main.c"),
            "elf_sha256": sha(retained_exe),
            "link_map_sha256": sha(retained_map),
            "run_log_sha256": sha(run_log),
            "package_sha256": {name: sha(path) for name, path in PACKAGES.items()},
            "source_map_sha256": {name: sha(ROOT / f"build/retail-maps/decompressed/{name}.map")
                                  for name in PACKAGES},
            "generated_translation_unit_sha256": generated_sha,
            "production_source_sha256": {
                "src/stream/hcu_map_service.c": sha(ROOT / "src/stream/hcu_map_service.c"),
                "src/stream/ctag_mount.c": sha(ROOT / "src/stream/ctag_mount.c"),
                "src/stream/hcu_memory_bind.c": sha(ROOT / "src/stream/hcu_memory_bind.c"),
                "src/stream/hcu_main.c": sha(ROOT / "src/stream/hcu_main.c"),
                "halo-ce-universal/port/ps2/src/ps2_ctag.c": sha(HCU / "port/ps2/src/ps2_ctag.c"),
            },
            "fixture_source_sha256": {str(p.relative_to(ROOT)): sha(p)
                for p in sources if p.is_relative_to(ROOT)},
        }
        manifest_path = retained / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        manifest_sha256 = sha(manifest_path)
        manifest_path.with_suffix(".manifest.sha256").write_text(
            manifest_sha256 + "  manifest.json\n")
        print(run.stdout)
        print(json.dumps({**manifest, "maps": 13, "attempts_per_map": 2,
                          "ctag_capacity_status_rows": status_rows,
                          "manifest_sha256": manifest_sha256}, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
