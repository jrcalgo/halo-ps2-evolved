"""Mount the actual UI HCP through the PS2 cache's CE and CBSP stream visitors."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from tools import hcu_profile_chunks

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
ENGINE = ROOT / "submodules/halo-ps2/engine"
PORT = HCU / "port/ps2"
SCHEMA = HCU / "port/linux/game"
ARTIFACTS = ROOT / "build/m2-c1-profile-mount"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _c_bytes(digest: str) -> str:
    raw = bytes.fromhex(digest)
    return ", ".join(f"0x{value:02x}" for value in raw)


def _write_bindings(manifest: dict) -> tuple[Path, int, int]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    profile = manifest["profile"]
    roots = profile["bsp_roots"]
    assert len(roots) == 1
    root = roots[0]
    row = next(binding for binding in manifest["chunk_bindings"]
               if binding["kind"] == "CBSP" and
               binding["owner"]["source_key"] == root["source_key"] and
               binding["owner"]["source_datum"] == root["source_datum"])
    dependencies = {(item["source_key"], item["path"]): item["output_datum"]
                    for item in manifest["dependencies"]}
    resource_rows = []
    for resource in manifest["resources"]:
        assert resource["source_sha256"] == manifest["source_maps"][resource["source"]]["sha256"]
        output_datum = dependencies[(resource["source"], resource["tag"])]
        resource_rows.append((output_datum, resource["source_offset"], resource["bytes"]))
    assert resource_rows and all(size for _, _, size in resource_rows)
    source_map_sha = root["source_map_sha256"]
    assert source_map_sha == manifest["source_maps"][root["source_key"]]["sha256"]
    lines = [
        "#ifndef HCU_PROFILE_MOUNT_FIXTURE_BINDINGS_H",
        "#define HCU_PROFILE_MOUNT_FIXTURE_BINDINGS_H",
        "#include \"stream/hcu_profile_mount.h\"",
        f"#define HCU_PROFILE_MOUNT_TEST_PROFILE_ID {profile['id']}u",
        f"#define HCU_PROFILE_MOUNT_TEST_BSP_OFFSET {root['source_file_offset']}u",
        f"#define HCU_PROFILE_MOUNT_TEST_BSP_SIZE {root['source_file_size']}u",
        f"#define HCU_PROFILE_MOUNT_TEST_CBSP_COUNT {1}u",
        f"#define HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT {len(resource_rows)}u",
        "static const hcu_profile_cbsp_binding hcu_profile_mount_test_cbsp_bindings[] = {",
        "\t{ %uu, %uu, %uu, { %s }, { %s } }," % (
            root["source_file_offset"], root["source_file_size"], row["chunk_id"],
            _c_bytes(source_map_sha), _c_bytes(row["sha256"])),
        "};",
        "static const hcu_profile_resource_range hcu_profile_mount_test_resource_ranges[] = {",
    ]
    lines += [f"\t{{ {datum}u, {offset}u, {size}u }},"
              for datum, offset, size in resource_rows]
    lines += ["};", "#endif", ""]
    path = ARTIFACTS / "hcu_profile_mount_fixture_bindings.h"
    path.write_text("\n".join(lines))
    return path, root["source_file_offset"], root["source_file_size"]


def _compile(bindings_header: Path) -> tuple[list[str], Path, subprocess.CompletedProcess[str]]:
    sys.path.insert(0, str(ROOT / "tools"))
    from host_abi32 import flags as abi32_flags

    compiler = shutil.which("gcc-13") or shutil.which("gcc") or shutil.which("cc")
    if not compiler:
        pytest.skip("GCC unavailable for ILP32 HCP mount fixture")
    semantics = ARTIFACTS / "halo_ps2_msvc_semantics.h"
    # The pinned ILP32 glibc sysroot omits this kernel UAPI header. Supply only
    # linux/limits.h from the host headers; keep the rest of header resolution
    # inside the pinned sysroot.
    uapi_include = ARTIFACTS / "host-uapi"
    linux_limits = uapi_include / "linux/limits.h"
    linux_limits.parent.mkdir(parents=True, exist_ok=True)
    host_linux_limits = Path("/usr/include/linux/limits.h")
    if not host_linux_limits.is_file():
        pytest.skip("host linux/limits.h unavailable for ILP32 sysroot supplement")
    shutil.copyfile(host_linux_limits, linux_limits)
    generated = subprocess.run([
        sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
        "--output", str(semantics), "--all-inlines",
        "--tags", str(HCU / "source"), "--inlines", str(HCU / "source"),
        "--inlines", str(HCU / "port/include/xdk"),
    ], capture_output=True, text=True)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    includes = [
        ROOT / "tests", ROOT / "src", ROOT / "submodules/halo-ps2/engine/src",
        HCU / "port/ps2/include", HCU / "port/linux/game", HCU / "port/linux/include",
        HCU / "port/include", HCU / "port/include/xdk", HCU / "source",
        HCU / "source/cseries", HCU / "source/math", HCU / "source/cache",
        HCU / "source/tag_files", HCU / "source/structures", HCU / "source/render",
        HCU / "source/bitmaps", HCU / "port/include/xdk", ARTIFACTS,
        Path("/usr/include"), ROOT / "submodules/ps2sdk/common/include", ROOT / "submodules/ps2sdk/ee/include",
        ROOT / "submodules/ps2sdk/ee/kernel/include",
        ROOT / "submodules/ps2sdk/ee/rpc/filexio/include",
    ]
    command = [compiler, *abi32_flags(), "-std=gnu99", "-fms-extensions",
               "-fshort-wchar", "-fwrapv", "-fno-strict-aliasing", "-fcommon",
               "-ffunction-sections", "-fdata-sections", "-no-pie",
               "-D_EE", "-DHALO_FILE_USE_FILEXIO", "-Wno-int-to-pointer-cast",
               "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
               "-include", str(semantics), "-w"]
    command += ["-I" + str(uapi_include)]
    command.extend("-I" + str(path) for path in includes)
    sources = [
        ROOT / "tests/hcu_profile_mount_main.c",
        ROOT / "src/stream/hcu_profile_mount.c",
        ROOT / "src/stream/hcu_asset_profile.c",
        ROOT / "src/stream/hcu_map_catalog.c",
        ROOT / "src/stream/ctag_ps2_backend.c",
        ROOT / "src/stream/hmap.c", ROOT / "src/stream/sha256.c",
        SCHEMA / "tag_validate.c",
        *[SCHEMA / f"tag_schema_{name}.c" for name in
          ("groups", "collision", "models", "objects", "render", "effects", "scenario")],
        PORT / "src/ps2_cache.c", PORT / "src/ps2_ctag.c", PORT / "src/ps2_cbsp.c",
    ]
    exe = ARTIFACTS / "hcu-profile-mount-fixture"
    command += ["-Wl,--gc-sections", *(str(source) for source in sources),
                "-lm", "-o", str(exe)]
    built = subprocess.run(command, capture_output=True, text=True)
    return command, exe, built


CORPUS_DIRS = (
    ROOT / os.environ.get("HCU_C1_PROFILES", "build/m2-c1-corpus-primary-v3"),   # preferred; may be corrupted
    ROOT / os.environ.get("HCU_C1_REBUILD", "build/m2-c1-corpus-rebuild-v3"),    # intact pinned fallback
)


def _select_corpus_package() -> tuple[Path, Path, dict]:
    """Return the first corpus UI package whose SHA equals its manifest pin."""
    for corpus in CORPUS_DIRS:
        package = corpus / "ui.hcp"
        manifest_path = corpus / "ui.json"
        if not package.is_file() or not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        if _sha(package) == manifest["package_sha256"]:
            return package, manifest_path, manifest
    pytest.fail("no UI HCP in the HCU_C1_PROFILES or HCU_C1_REBUILD corpus directories "
                "matches its manifest package_sha256: " + ", ".join(str(c) for c in CORPUS_DIRS))


def test_actual_ui_hcp_mounts_through_ps2_cache(tmp_path):
    map_path = ROOT / "build/retail-maps/decompressed/ui.map"
    if not map_path.is_file():
        pytest.skip("pinned retail UI map is not available")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    package, manifest_path, manifest = _select_corpus_package()
    source_package = package
    assert _sha(package) == manifest["package_sha256"]
    source_info = manifest["source_maps"]["ui"]
    assert _sha(map_path) == source_info["sha256"]
    bindings_header, _, _ = _write_bindings(manifest)
    # The fixture flips bytes to prove late-corruption fail-closed behavior.
    # Run it only on a verified copy so the pinned corpus package is never written.
    under_test = ARTIFACTS / "ui-under-test.hcp"
    shutil.copyfile(package, under_test)
    assert _sha(under_test) == manifest["package_sha256"]
    package = under_test
    package_bytes = package.read_bytes()
    ce_row = None
    for index in range(hcu_profile_chunks.HEADER.unpack_from(package_bytes)[4]):
        record = hcu_profile_chunks.RECORD.unpack_from(
            package_bytes, hcu_profile_chunks.HEADER.size + index * hcu_profile_chunks.RECORD.size)
        if record[0:2] == (1, 0):
            ce_row = record
            break
    assert ce_row is not None
    ce_ctag_image_bytes = int.from_bytes(package_bytes[ce_row[2] + 12:ce_row[2] + 16], "little")
    command, exe, built = _compile(bindings_header)
    compile_log = ARTIFACTS / "compile.log"
    compile_log.write_text("$ " + " ".join(command) + "\n" + built.stdout + built.stderr)
    assert built.returncode == 0, built.stdout + built.stderr
    run_command = [str(exe), str(package), str(map_path)]
    run = subprocess.run(run_command, capture_output=True, text=True)
    if run.returncode in (-31, 159):
        pytest.skip("sandbox blocks native ILP32 HCP mount fixture with SIGSYS")
    run_log = ARTIFACTS / "run.log"
    run_log.write_text(run.stdout + run.stderr)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "PROFILE_MOUNT_OK" in run.stdout
    pins = [
        ROOT / "src/stream/hcu_profile_mount.c", ROOT / "src/stream/hcu_profile_mount.h",
        ROOT / "src/stream/hcu_asset_profile.c", ROOT / "src/stream/hcu_asset_profile.h",
        ROOT / "src/stream/hcu_map_catalog.c", ROOT / "src/stream/hcu_map_catalog.h",
        ROOT / "src/stream/ctag_ps2_backend.c", ROOT / "src/stream/ctag_mount.h",
        ROOT / "src/stream/hmap.h", ROOT / "src/stream/sha256.c",
        ROOT / "tests/hcu_profile_mount_main.c", ROOT / "tests/test_hcu_profile_mount.py",
        ROOT / "tests/hcu_scenario_host32_prefix.h",
        HCU / "port/ps2/src/ps2_cache.c", HCU / "port/ps2/src/ps2_ctag.c",
        HCU / "port/ps2/src/ps2_cbsp.c", HCU / "port/ps2/include/ps2_ctag.h",
        HCU / "port/ps2/include/ps2_cbsp.h",
        HCU / "port/ps2/include/halo_ps2_cache.h",
        SCHEMA / "tag_validate.c",
        *[SCHEMA / f"tag_schema_{name}.c" for name in
          ("groups", "collision", "models", "objects", "render", "effects", "scenario")],
    ]
    report = {
        "schema": "hcu-profile-mount-native-ui-v1",
        "status": "host_ui_mounted_and_validated",
        "runtime_admitted": False,
        "product_mapservice_integrated": False,
        "actual_ps2_cache_stream_mount": True,
        "actual_ce_tag_validator": True,
        "actual_cbsp_rebase": True,
        "actual_gs_or_spu2_playback": False,
        "target_tag_cache_capacity_bytes": 2 * 1024 * 1024,
        "ui_ctag_image_bytes": ce_ctag_image_bytes,
        "source_package": {"path": source_package.relative_to(ROOT).as_posix(),
                           "sha256": _sha(source_package)},
        "profile": {"path": package.relative_to(ROOT).as_posix(), "sha256": _sha(package)},
        "manifest": {"path": manifest_path.relative_to(ROOT).as_posix(), "sha256": _sha(manifest_path)},
        "source_map": {"path": map_path.relative_to(ROOT).as_posix(), "sha256": _sha(map_path),
                        "file_length": map_path.stat().st_size},
        "generated_bindings_header": {"path": bindings_header.relative_to(ROOT).as_posix(),
                                       "sha256": _sha(bindings_header)},
        "compile_command": command,
        "compile_returncode": built.returncode,
        "compile_log": {"path": compile_log.relative_to(ROOT).as_posix(), "sha256": _sha(compile_log)},
        "executable": {"path": exe.relative_to(ROOT).as_posix(), "sha256": _sha(exe)},
        "run_command": run_command,
        "run_returncode": run.returncode,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "run_log": {"path": run_log.relative_to(ROOT).as_posix(), "sha256": _sha(run_log)},
        "implementation_source_sha256": {
            source.relative_to(ROOT).as_posix(): _sha(source) for source in pins},
    }
    (ARTIFACTS / "result.json").write_text(json.dumps(report, indent=2) + "\n")
