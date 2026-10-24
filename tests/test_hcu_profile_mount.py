"""Mount actual UI and selected-session HCPs through PS2 CE/CBSP visitors."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest
from tools import hcu_profile_chunks

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
HCU = ROOT / "submodules/halo-ce-universal"
ENGINE = ROOT / "submodules/halo-ps2/engine"
PORT = HCU / "port/ps2"
SCHEMA = HCU / "port/linux/game"
ARTIFACTS = Path(os.environ.get("HCU_PROFILE_MOUNT_ARTIFACTS",
                               ROOT / "build/m2-c1-profile-mount")).resolve()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _c_bytes(digest: str) -> str:
    raw = bytes.fromhex(digest)
    return ", ".join(f"0x{value:02x}" for value in raw)


def _write_bindings(manifest: dict, package: Path, artifacts: Path) -> tuple[Path, int, int]:
    artifacts.mkdir(parents=True, exist_ok=True)
    profile = manifest["profile"]
    roots = profile["bsp_roots"]
    assert roots
    root = roots[0]
    row = next(binding for binding in manifest["chunk_bindings"]
               if binding["kind"] == "CBSP" and
               binding["owner"]["source_key"] == root["source_key"] and
               binding["owner"]["source_datum"] == root["source_datum"])
    dependencies = {(item["source_key"], item["path"]): item["output_datum"]
                    for item in manifest["dependencies"]}
    resource_rows = []
    profile_map = profile["map"]
    for resource in manifest["resources"]:
        if resource["source"] != profile_map:
            continue
        assert resource["source_sha256"] == manifest["source_maps"][resource["source"]]["sha256"]
        output_datum = dependencies[(resource["source"], resource["tag"])]
        resource_rows.append((output_datum, resource["source_offset"], resource["bytes"]))
    assert resource_rows and all(size for _, _, size in resource_rows)
    source_map_sha = root["source_map_sha256"]
    assert source_map_sha == manifest["source_maps"][root["source_key"]]["sha256"]
    from tools.hcu_profile_validate import parse_package
    parsed = parse_package(package.read_bytes(), expected_package_sha256=manifest["package_sha256"],
                           expected_profile_id=profile["id"])
    ce = parsed["chunks"][(1, 0)]
    image_bytes = int.from_bytes(ce[12:16], "little")
    tag_capacity = (image_bytes + 15) & ~15
    bsp_capacity = (int(root["payload_bytes"]) + 15) & ~15
    assert resource_rows and all(size for _, _, size in resource_rows)
    lines = [
        "#ifndef HCU_PROFILE_MOUNT_FIXTURE_BINDINGS_H",
        "#define HCU_PROFILE_MOUNT_FIXTURE_BINDINGS_H",
        "#include \"stream/hcu_profile_mount.h\"",
        f"#define HCU_PROFILE_MOUNT_TEST_PROFILE_ID {profile['id']}u",
        f'#define HCU_PROFILE_MOUNT_TEST_MAP_NAME "{profile_map}"',
        f"#define HCU_PROFILE_MOUNT_TEST_TAG_CACHE_BYTES {tag_capacity}u",
        f"#define HCU_PROFILE_MOUNT_TEST_BSP_CACHE_BYTES {bsp_capacity}u",
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
    path = artifacts / "hcu_profile_mount_fixture_bindings.h"
    path.write_text("\n".join(lines))
    return path, root["source_file_offset"], root["source_file_size"]


def _compile(bindings_header: Path, artifacts: Path) -> tuple[list[str], Path, subprocess.CompletedProcess[str]]:
    sys.path.insert(0, str(ROOT / "tools"))
    from host_abi32 import flags as abi32_flags

    compiler = shutil.which("gcc-13") or shutil.which("gcc") or shutil.which("cc")
    if not compiler:
        pytest.skip("GCC unavailable for ILP32 HCP mount fixture")
    semantics = artifacts / "halo_ps2_msvc_semantics.h"
    # The pinned ILP32 glibc sysroot omits this kernel UAPI header. Supply only
    # linux/limits.h from the host headers; keep the rest of header resolution
    # inside the pinned sysroot.
    uapi_include = artifacts / "host-uapi"
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
        HCU / "source/bitmaps", HCU / "port/include/xdk", artifacts,
        Path("/usr/include"), ROOT / "submodules/ps2sdk/common/include", ROOT / "submodules/ps2sdk/ee/include",
        ROOT / "submodules/ps2sdk/ee/kernel/include",
        ROOT / "submodules/ps2sdk/ee/rpc/filexio/include",
    ]
    command = [compiler, *abi32_flags(), "-std=gnu99", "-fms-extensions",
               "-fshort-wchar", "-fwrapv", "-fno-strict-aliasing", "-fcommon",
               "-ffunction-sections", "-fdata-sections", "-no-pie",
               "-D_EE", "-DHALO_FILE_USE_FILEXIO", "-Wno-int-to-pointer-cast",
               "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
               "-include", str(semantics), "-w", "-g"]
    command += ["-I" + str(uapi_include)]
    # Residency slot count for the C2.4 measurement; unset keeps the default of 16.
    slots = os.environ.get("HCU_PROFILE_MOUNT_RESIDENCY_SLOTS")
    if slots:
        command.append(f"-DHCU_PROFILE_MOUNT_TEST_RESIDENCY_SLOTS={int(slots)}u")
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
    exe = artifacts / "hcu-profile-mount-fixture"
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


def _profiles():
    current = ROOT / "build/m2-c2-hcp2-primary"
    yield "ui", current / "ui.hcp", current / "ui.json"
    # Every retained session row (26 = 13 maps x marine shotgun / mounted gunner),
    # each a complete CTAG+BSP+media+bindings HCP2 package from its selection JSON.
    selected = ROOT / "build/m2-c2-r3-selected-packages/pkg"
    for selection in sorted((ROOT / "build/m2-c2-r3-selected-packages/selections").glob("*.selection.json")):
        name = selection.name[: -len(".selection.json")]
        yield name, selected / name / f"{name}.hcp", selected / name / f"{name}.json"


def _assert_recipe_remaps(manifest: dict) -> int:
    dependencies = manifest.get("dependencies", [])
    dep_keys = {(d["source_key"], d["group"], d["path"], int(d["output_datum"]))
                for d in dependencies}
    checked = 0
    for binding in manifest.get("actor_bindings", []):
        source = binding["source_key"]
        assert (source, "actv", binding["path"], int(binding["output_datum"])) in dep_keys
        recipe = binding["recipe"]
        assert recipe.get("variant", {}).get("output_datum") == binding["output_datum"]
        stack = [recipe]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if value.get("group") and value.get("path") and "output_datum" in value:
                    key = (source, value["group"], value["path"], int(value["output_datum"]))
                    assert key in dep_keys, f"recipe reference is not bound to a package dependency: {key}"
                    checked += 1
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    return checked


@pytest.mark.parametrize("profile_name,package,manifest_path", list(_profiles()))
def test_actual_profile_hcp_mounts_through_ps2_cache(tmp_path, profile_name, package, manifest_path):
    artifacts_root = ARTIFACTS
    if "HCU_PROFILE_MOUNT_ARTIFACTS" not in os.environ:
        artifacts_root = ROOT / ("build/m2-c2-selected-native-" + profile_name)
    artifacts = artifacts_root.resolve()
    if not package.is_file() or not manifest_path.is_file():
        pytest.skip(f"built HCP package is not available for {profile_name}")
    manifest = json.loads(manifest_path.read_text())
    map_name = manifest["profile"]["map"]
    map_path = ROOT / f"build/retail-maps/decompressed/{map_name}.map"
    if not map_path.is_file():
        pytest.skip(f"pinned retail source map is not available for {profile_name}")
    artifacts.mkdir(parents=True, exist_ok=True)
    source_package = package
    assert _sha(package) == manifest["package_sha256"]
    recipe_remaps_checked = _assert_recipe_remaps(manifest)
    from tools.build_hcu_runtime_metadata import build as build_runtime_metadata
    runtime_metadata = build_runtime_metadata(manifest_path, package)
    hcm_header = struct.Struct("<4sHHIIIIII")
    magic, version, header_size, total_size, _pid, bitmap_count, cbsp_count, sound_range_count, _reserved = hcm_header.unpack_from(runtime_metadata)
    assert magic == b"HCM1" and version == 1 and header_size == hcm_header.size
    assert total_size == len(runtime_metadata)
    assert bitmap_count == len([b for b in manifest["chunk_bindings"] if b["kind"] == "BITM"])
    assert cbsp_count == len(manifest["profile"]["bsp_roots"])
    expected_local_ranges = sum(1 for r in manifest["resources"]
        if r.get("source") == map_name and r.get("definition") == "sound_permutation" and r.get("field") == "samples")
    assert sound_range_count == expected_local_ranges
    source_info = manifest["source_maps"][map_name]
    assert _sha(map_path) == source_info["sha256"]
    bindings_header, _, _ = _write_bindings(manifest, package, artifacts)
    # The fixture flips bytes to prove late-corruption fail-closed behavior.
    # Run it only on a verified copy so the pinned corpus package is never written.
    under_test = artifacts / (profile_name + "-under-test.hcp")
    shutil.copyfile(package, under_test)
    assert _sha(under_test) == manifest["package_sha256"]
    package = under_test
    package_bytes = package.read_bytes()
    from tools.hcu_profile_validate import parse_package
    logical = parse_package(package_bytes,
                            expected_package_sha256=manifest["package_sha256"],
                            expected_profile_id=manifest["profile"]["id"])
    ce_payload = logical["chunks"][(1, 0)]
    ce_ctag_image_bytes = int.from_bytes(ce_payload[12:16], "little")
    command, exe, built = _compile(bindings_header, artifacts)
    compile_log = artifacts / "compile.log"
    compile_log.write_text("$ " + " ".join(command) + "\n" + built.stdout + built.stderr)
    assert built.returncode == 0, built.stdout + built.stderr
    run_command = [str(exe), str(package), str(map_path)]
    run = subprocess.run(run_command, capture_output=True, text=True)
    if run.returncode in (-31, 159):
        pytest.skip("sandbox blocks native ILP32 HCP mount fixture with SIGSYS")
    run_log = artifacts / "run.log"
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
        "schema": "hcu-profile-mount-native-selected-v1",
        "status": "host_profile_mounted_and_validated",
        "runtime_admitted": False,
        "product_mapservice_integrated": False,
        "actual_ps2_cache_stream_mount": True,
        "actual_ce_tag_validator": True,
        "actual_cbsp_rebase": True,
        "package_format": logical["format"],
        "physical_segment_count": len(logical["segments"]),
        "maximum_physical_segment_bytes": max(row["size"] for row in logical["segments"]),
        "actual_gs_or_spu2_playback": False,
        "target_tag_cache_capacity_bytes": ((ce_ctag_image_bytes + 15) & ~15),
        "ce_ctag_image_bytes": ce_ctag_image_bytes,
        "actor_recipe_rebound_reference_count": recipe_remaps_checked,
        "runtime_metadata": {"format": "HCM1", "bytes": len(runtime_metadata),
                             "sha256": hashlib.sha256(runtime_metadata).hexdigest(),
                             "bitmap_bindings": bitmap_count, "cbsp_bindings": cbsp_count,
                             "loaded_map_sound_ranges": sound_range_count,
                             "other_source_sound_ranges_have_no_raw_io_gate": True},
        "target_bsp_cache_capacity_bytes": (int(manifest["profile"]["bsp_roots"][0]["payload_bytes"]) + 15) & ~15,
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
    (artifacts / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    # Keep each package's own copy: the shared result.json is overwritten by the next package.
    (artifacts / f"{profile_name}.result.json").write_text(json.dumps(report, indent=2) + "\n")
