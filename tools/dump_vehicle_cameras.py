#!/usr/bin/env python3
"""Dump the retail Xbox camera data of every vehicle and biped in a decompressed Halo CE map.

The map files come from the user's Xbox ISO (build/retail-maps/decompressed/<map>.map). For each vehi/bipd tag this
prints the unit camera, every seat's flags and camera (marker, pitch range, camera tracks), then every camera
track (trak) control point. These are the inputs CE's director (source/camera/director.c) and following camera
(source/camera/following_camera.c) read, so the third-person vehicle cameras are authored here, not in code.

Usage:  python3 -I tools/dump_vehicle_cameras.py bloodgulch

Struct offsets are the ILP32 layout of struct unit_definition / unit_seat / unit_camera in halo-ce-universal
(probed with clang -m32, the same way tools/audit_mp_vehicle_seat_actors.py probes them):
  unit_definition: flags 380, camera_field_of_view 416, camera_impulse_stiffness 420, unit.camera 424, seats 740
  unit_camera (88): marker 0, submerged marker 32, pitch autolevel 64, min 68, max 72, camera tracks block 76
  unit_seat (284): flags 0, label 4, camera 132;  unit_camera_track (28): tag reference at 0
  camera_track_definition: flags 0, control points block 4;  control point (60): position 3f, orientation 4f
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import texconv  # noqa: E402

SEAT_FLAGS = ["invisible", "locked", "driver", "gunner", "third_person_camera", "allows_weapons",
              "third_person_on_enter", "first_person_camera_slaved", "allow_vehicle_communication",
              "not_valid_without_driver", "allow_ai_noncombatants"]


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "bloodgulch"
    m = texconv.MapData.open(ROOT / f"build/retail-maps/decompressed/{name}.map")
    region, base = m.region, m.base

    def cstr(o: int, n: int = 32) -> str:
        raw = region[o:o + n]
        end = raw.find(b"\0")
        return raw[:end if end >= 0 else n].decode("latin1")

    def block(o: int) -> tuple[int, int]:
        count, addr, _ = struct.unpack_from("<iII", region, o)
        return count, addr - base

    def ref(o: int) -> str | None:
        _g, _n, _l, idx = struct.unpack_from("<4sIIi", region, o)
        entry = m.by_id.get(idx & 0xFFFFFFFF) if idx != -1 else None
        return entry.path if entry else None

    def camera(o: int, tag: str) -> str:
        autolevel, pmin, pmax = struct.unpack_from("<fff", region, o + 64)
        count, addr = block(o + 76)
        tracks = [ref(addr + i * 28) for i in range(count)]
        return (f"{tag}: marker='{cstr(o)}' submerged='{cstr(o + 32)}' autolevel={autolevel:.3f} "
                f"pitch=[{math.degrees(pmin):.1f},{math.degrees(pmax):.1f}]deg tracks={tracks}")

    seen = set()
    for e in m.index.entries:
        if e.group not in ("vehi", "bipd") or e.path in seen:
            continue
        seen.add(e.path)
        o = e.data_address - base
        flags, = struct.unpack_from("<I", region, o + 380)
        fov, stiffness = struct.unpack_from("<ff", region, o + 416)
        print(f"== {e.group} {e.path} unit_flags={flags:#x} camera_fov={math.degrees(fov):.1f}deg "
              f"impulse_stiffness={stiffness:.3f}")
        print("   " + camera(o + 424, "unit camera"))
        count, addr = block(o + 740)
        for i in range(count):
            so = addr + i * 284
            fl, = struct.unpack_from("<I", region, so)
            names = [n for b, n in enumerate(SEAT_FLAGS) if fl >> b & 1]
            print(f"   seat[{i}] '{cstr(so + 4)}' flags={fl:#x} {names}")
            print("      " + camera(so + 132, "seat camera"))
    print("-- camera tracks (trak)")
    for e in m.index.entries:
        if e.group != "trak":
            continue
        o = e.data_address - base
        fl, = struct.unpack_from("<I", region, o)
        count, addr = block(o + 4)
        print(f"== {e.path} flags={fl:#x} control_points={count}")
        for i in range(count):
            x, y, z, qi, qj, qk, qw = struct.unpack_from("<7f", region, addr + i * 60)
            print(f"   p{i}: pos=({x:.3f},{y:.3f},{z:.3f}) quat=({qi:.3f},{qj:.3f},{qk:.3f},{qw:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
