#!/usr/bin/env python3
"""Run CE's visible-PVS sound obstruction branch against a raw-source MP pair.

The CE BSP and sound routine are package-backed. A test-only collision spy
returns a deterministic miss, so this qualifies CE's branch policy and call
contract without claiming geometry or audible-output parity.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools"),
                str(ROOT / "submodules/halo-ps2/tools")]
import test_hcu_mp_capacity as mp  # noqa: E402
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from tools.ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from test_hcu_scenario_bsp_switch import (  # noqa: E402
    retail_source_pvs_pair_oracle,
    STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET,
    TAG_DATA_ADDRESS_OFFSET,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def c_float(value):
    text = f"{float(value):.9g}"
    if "." not in text and "e" not in text.lower():
        text += ".0"
    return text + "f"


def raw_sound_pair(path, pair):
    header = mapinfo.read_header(path)
    index = tagindex.TagIndex.read(path)
    tag_region, _, _ = read_xbox_tag_region(path)
    locations = bsp.locate(index, tag_region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"expected one stock MP BSP, got {len(locations)}")
    location = locations[0]
    with path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    cluster_count = struct.unpack_from("<i", image, root + 308)[0]
    count = struct.unpack_from(
        "<i", image, root + STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET)[0]
    sound_address = struct.unpack_from(
        "<I", image, root + STRUCTURE_BSP_SOUND_CLUSTER_DATA_OFFSET +
        TAG_DATA_ADDRESS_OFFSET)[0]
    sound_offset = sound_address - location.address
    required = cluster_count * (cluster_count - 1) // 2
    if count < required or sound_offset < 0 or sound_offset + required > len(image):
        raise AssertionError("invalid raw sound-cluster extent")
    first, second = pair
    if first == second or not (0 <= first < cluster_count and
                               0 <= second < cluster_count):
        raise AssertionError("raw PVS pair is invalid")
    low, high = sorted((first, second))
    pair_index = (low * (cluster_count - 1) - low * (low + 1) // 2 + high - 1)
    return image[sound_offset + pair_index], hashlib.sha256(image).hexdigest(), location.path


def main():
    source_map = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
    source_sha = sha(source_map)
    if source_sha != mp.MP_SOURCE_SHA256["bloodgulch"]:
        raise SystemExit("Blood Gulch raw-map pin changed")
    source_oracle = retail_source_pvs_pair_oracle(source_map, 1)[0]
    pair = source_oracle["visible"]
    encoded, raw_bsp_sha, bsp_path = raw_sound_pair(source_map, pair)
    if encoded == 0xFF or (encoded & 0x7F) >= 127:
        raise SystemExit("selected visible pair is not acoustically reachable")

    out = ROOT / "build" / f"m2-mp-visible-pvs-sound-{time.time_ns()}"
    out.mkdir(parents=True, exist_ok=False)
    golden = out / "hcu_mp_visible_sound_golden.h"
    golden.write_text("\n".join([
        "typedef struct hcu_mp_visible_sound_golden {",
        "    unsigned from_cluster, to_cluster, encoded_distance;",
        "    float source_distance, expected_cluster_distance;",
        "} hcu_mp_visible_sound_golden;",
        "static const hcu_mp_visible_sound_golden hcu_mp_visible_sound = {",
        f"    {pair[0]}u, {pair[1]}u, {encoded}u, 80.0f,",
        f"    {c_float((encoded & 0x7F) * (256.0 / 127.0))}",
        "};", "",
    ]))

    test_source = (ROOT / "tests/test_hcu_mp_capacity.py").read_text()
    test_source = test_source.replace(
        "ROOT = Path(__file__).resolve().parents[1]",
        f"ROOT = Path({str(ROOT)!r})")
    old_source_list = '            sources = [ROOT / "tests/hcu_mp_capacity_main.c",'
    injection = r'''            main_source = (ROOT / "tests/hcu_mp_capacity_main.c").read_text()
            main_source = main_source.replace(
                '#include "hcu_mp_lifecycle_generated.h"',
                '#include "hcu_mp_lifecycle_generated.h"\n#include "hcu_mp_visible_sound_golden.h"')
            query = r"""
static void assert_mp_visible_pvs_sound(unsigned map_id)
{
    real obstruction=-1.0f, occlusion=-1.0f;
    unsigned collision_calls=0;
    short depth_before=global_current_collision_user_depth;
    long collision_user=global_current_collision_users[0];
    struct structure_bsp *published=global_structure_bsp;
    if (map_id != 102u) return;
    assert(published != NULL && global_structure_bsp_index == 0);
    assert(BIT_VECTOR_TEST_FLAG(structure_bsp_get_cluster_pvs(published,
        (short)hcu_mp_visible_sound.from_cluster),
        hcu_mp_visible_sound.to_cluster));
    assert(structure_bsp_get_cluster_encoded_sound_distance(published,
        (short)hcu_mp_visible_sound.from_cluster,
        (short)hcu_mp_visible_sound.to_cluster) ==
        hcu_mp_visible_sound.encoded_distance);
    assert(hcu_mp_visible_sound.expected_cluster_distance < 256.0f);
    hcu_test_compute_sound_obstruction((short)hcu_mp_visible_sound.from_cluster,
        (short)hcu_mp_visible_sound.to_cluster, sound_obstruction_fixture_tick++,
        hcu_mp_visible_sound.source_distance, &obstruction, &occlusion,
        &collision_calls);
    /* The test bridge returns a controlled miss. CE must enter the visible-PVS
       collision path and clear both outputs on that miss. */
    assert(collision_calls == 1u);
    assert(fabsf(obstruction) < 0.00001f && fabsf(occlusion) < 0.00001f);
    assert(global_current_collision_user_depth == depth_before);
    assert(global_current_collision_users[0] == collision_user);
    assert(global_structure_bsp == published && global_structure_bsp_index == 0);
    printf("mp-sound-obstruction-visible map=%u from=%u to=%u encoded=%u "
        "pvs=1 collision_calls=1 spy=controlled-miss obstruction=%.6g "
        "occlusion=%.6g status=passed\n", map_id,
        hcu_mp_visible_sound.from_cluster, hcu_mp_visible_sound.to_cluster,
        hcu_mp_visible_sound.encoded_distance, obstruction, occlusion);
}
"""
            anchor = "static void mp_query(unsigned map_id)\n{"
            if main_source.count(anchor) != 1:
                raise AssertionError("mp_query insertion seam changed")
            main_source = main_source.replace(anchor, query + "\n" + anchor)
            anchor = "assert_mp_sound_obstruction(map_id);"
            if main_source.count(anchor) != 1:
                raise AssertionError("sound query insertion seam changed")
            main_source = main_source.replace(anchor,
                anchor + "\n\tassert_mp_visible_pvs_sound(map_id);")
            generated_main = temp / "hcu_mp_visible_sound_main.c"
            generated_main.write_text(main_source)
            sources = [generated_main,'''
    if test_source.count(old_source_list) != 1:
        raise SystemExit("MP fixture source-list seam changed")
    test_source = test_source.replace(old_source_list, injection)
    copy_header = (
        f"            shutil.copy2(ROOT / {str(golden.relative_to(ROOT))!r}, "
        "temp / 'hcu_mp_visible_sound_golden.h')\n")
    seam = "            generated_main.write_text(main_source)\n"
    if test_source.count(seam) != 1:
        raise SystemExit("generated-main seam changed")
    test_source = test_source.replace(seam, seam + copy_header)
    retained_seam = 'retained = ROOT / "build/m2-mp-weather-wind-13"'
    # The host file shim stores its default root in 64 bytes, so retain the
    # executable/package symlinks at a short stable path for the native run.
    test_source = test_source.replace(retained_seam,
        'retained = ROOT / "build/mp-vps-sound"')
    generated_test = out / "test_hcu_mp_visible_sound_generated.py"
    generated_test.write_text(test_source)
    env = dict(os.environ)
    env["PYTHONPATH"] = ":".join((str(ROOT / "tests"), str(ROOT / "tools"),
                                  str(ROOT / "submodules/halo-ps2/tools"), str(out)))
    proc = subprocess.run([
        sys.executable, "-m", "unittest", "-v",
        f"{generated_test.stem}.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision",
    ], cwd=ROOT, env=env, capture_output=True, text=True)
    (out / "native-run.log").write_text(proc.stdout + proc.stderr)
    manifest = {
        "schema": "hcu-mp-visible-pvs-sound-v1",
        "scope": "Blood Gulch stock multiplayer BSP; package-backed CE host ILP32",
        "raw_source_map_sha256": source_sha,
        "raw_bsp_sha256": raw_bsp_sha,
        "raw_bsp_path": bsp_path,
        "source_visible_pair": pair,
        "source_encoded_distance": encoded,
        "package_sha256": mp.MP_PACKAGE_SHA256["bloodgulch"],
        "hcu_pin": subprocess.check_output([
            "git", "-C", str(ROOT / "submodules/halo-ce-universal"),
            "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "halo_ps2_pin": subprocess.check_output([
            "git", "-C", str(ROOT / "submodules/halo-ps2"),
            "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runner_exit_code": proc.returncode,
        "runner_stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "runner_stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest(),
        "generated_test_sha256": sha(generated_test),
        "golden_sha256": sha(golden),
        "native_log_sha256": sha(out / "native-run.log"),
        "geometry_or_playback_proven": False,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(proc.stdout, end="")
    print(proc.stderr, end="", file=sys.stderr)
    print("artifacts", out.relative_to(ROOT), "manifest_sha256", sha(manifest_path))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
