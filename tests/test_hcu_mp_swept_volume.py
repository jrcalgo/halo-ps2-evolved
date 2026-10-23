"""Compile CE sphere/pill tests against one raw Blood Gulch collision floor."""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MAP = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
OUT = ROOT / "build/step7-swarm/swept"
MAP_SHA256 = "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1"
sys.path.extend([str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")])
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from host_abi32 import flags as host_abi32_flags  # noqa: E402


def raw_floor():
    digest = hashlib.sha256(MAP.read_bytes()).hexdigest()
    if digest != MAP_SHA256:
        raise AssertionError("Blood Gulch source hash changed")
    region, _, _ = read_xbox_tag_region(MAP)
    locations = bsp.locate(
        tagindex.TagIndex.read(MAP), region,
        mapinfo.read_header(MAP).decompressed_size)
    if len(locations) != 1:
        raise AssertionError("expected one Blood Gulch BSP")
    location = locations[0]
    image = MAP.read_bytes()[location.file_offset:location.file_offset + location.size]
    root = struct.unpack_from("<I", image)[0] - location.address
    collision_count, collision_address = struct.unpack_from("<iI", image, root + 0xB0)
    if collision_count != 1:
        raise AssertionError("Blood Gulch collision BSP count changed")
    collision = collision_address - location.address
    plane_count, plane_address = struct.unpack_from("<iI", image, collision + 0x0C)
    surface_count, surface_address = struct.unpack_from("<iI", image, collision + 0x3C)
    edge_count, edge_address = struct.unpack_from("<iI", image, collision + 0x48)
    vertex_count, vertex_address = struct.unpack_from("<iI", image, collision + 0x54)
    path_count, path_address = struct.unpack_from("<iI", image, root + 0x1E4)
    plane_at = plane_address - location.address
    surface_at = surface_address - location.address
    edge_at = edge_address - location.address
    vertex_at = vertex_address - location.address
    path_flags = image[path_address - location.address:
                       path_address - location.address + path_count]
    chosen = None
    for surface_index in range(min(surface_count, path_count)):
        if not (path_flags[surface_index] & (1 << 6)):
            continue
        plane_index = struct.unpack_from("<i", image, surface_at + surface_index * 12)[0]
        if not 0 <= plane_index < plane_count:
            continue
        ni, nj, nk, d = struct.unpack_from("<4f", image, plane_at + plane_index * 16)
        if nk < 0.95:
            continue
        first_edge = struct.unpack_from("<i", image, surface_at + surface_index * 12 + 4)[0]
        ring = []
        edge_index = first_edge
        for _ in range(8):
            if not 0 <= edge_index < edge_count:
                break
            v0, v1, next0, next1, s0, s1 = struct.unpack_from(
                "<6i", image, edge_at + edge_index * 24)
            right = surface_index == s1
            vertex = v1 if right else v0
            if not 0 <= vertex < vertex_count:
                break
            ring.append(struct.unpack_from("<3f", image, vertex_at + vertex * 16))
            edge_index = next1 if right else next0
            if edge_index == first_edge:
                break
        if len(ring) == 4:
            chosen = {
                "surface_index": surface_index,
                "plane": (ni, nj, nk, d),
                "vertices": ring,
            }
            break
    if chosen is None:
        raise AssertionError("no walkable 4-edge upward Blood Gulch floor")
    chosen["source_map_sha256"] = digest
    chosen["raw_bsp_sha256"] = hashlib.sha256(image).hexdigest()
    return chosen


class MultiplayerSweptVolumeTest(unittest.TestCase):
    def test_ce_sphere_and_pill_on_raw_bloodgulch_floor(self):
        floor = raw_floor()
        plane = ",".join("%.9gf" % value for value in floor["plane"])
        verts = ",\n    ".join(
            "{%.9gf,%.9gf,%.9gf}" % vertex for vertex in floor["vertices"])
        source = (ROOT / "tests/hcu_mp_swept_bloodgulch_main.c").read_text()
        source = (source.replace("__RAW_PLANE__", plane)
                  .replace("__RAW_VERTS__", verts)
                  .replace("__SURFACE__", str(floor["surface_index"])))
        OUT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hcu-mp-swept-") as temp_name:
            temp = Path(temp_name)
            c_file = temp / "swept.c"
            exe = temp / "swept"
            c_file.write_text(source)
            command = [
                os.environ.get("CC", "gcc"), *host_abi32_flags(), "-std=gnu99",
                "-O2", "-fshort-wchar", "-DHALO_PS2=1", "-D_X86_=1",
                "-D_STDCALL_SUPPORTED=1", "-D__COLLISION_USAGE_H=1",
                "-D__cdecl=", "-D__stdcall=", "-D__fastcall=",
                "-D__declspec(x)=", "-ffunction-sections", "-fdata-sections",
                "-Wno-unused-function",
                "-I" + str(HCU / "port/ps2/include"),
                "-I" + str(HCU / "port/include/xdk"),
                "-I" + str(HCU / "source/tag_files"),
                "-I" + str(HCU / "source/memory"),
                "-I" + str(HCU / "source/math"),
                "-I" + str(HCU / "source"),
                "-I" + str(HCU / "source/cseries"),
                "-I" + str(HCU / "source/objects"),
                "-I" + str(HCU / "source/scenario"),
                "-I" + str(ROOT / "src"),
                "-include", str(ROOT / "tests/m3_ce_collision_host_preamble.h"),
                "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
                str(c_file),
                str(HCU / "source/physics/collision_bsp.c"),
                str(HCU / "source/physics/bsp2d.c"),
                "-Wl,--gc-sections", "-lm", "-o", str(exe),
            ]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, (built.stdout + built.stderr)[-20000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            if run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("status=passed", run.stdout)
            payload = {
                "map": "bloodgulch",
                "source_map_sha256": floor["source_map_sha256"],
                "raw_bsp_sha256": floor["raw_bsp_sha256"],
                "surface_index": floor["surface_index"],
                "plane": floor["plane"],
                "vertices": floor["vertices"],
                "stdout": run.stdout.strip(),
            }
            (OUT / "swept-bloodgulch.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
