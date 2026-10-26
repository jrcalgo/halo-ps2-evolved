"""C4 narrow consumer extraction probes for collision-adjacent members.

The consumer routines are copied verbatim from the pinned CE sources at test
time (tests/c4_parity_collision_consumer_main.c includes the generated file).
Only global/runtime reads are stubbed. Expected values come from independent
Python arithmetic, not from the C output. Host ILP32 only.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tools"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402

MAIN = ROOT / "tests/c4_parity_collision_consumer_main.c"
PREAMBLE = ROOT / "tests/m3_ce_collision_host_preamble.h"
ORDER = ROOT / "tests/c4_host_shims/c4_collision_order.h"
SRC_VEHICLES = HCU / "source/units/vehicles.c"
SRC_BREAK = HCU / "source/physics/breakable_surfaces.c"
SRC_PATH = HCU / "source/ai/path.c"
SRC_LIGHTS = HCU / "source/objects/object_lights.c"
SRC_VIS = HCU / "source/structures/structure_visibility.c"


def _lines(path):
    return Path(path).read_text(encoding="latin-1").split("\n")


def _slice_verbatim(path, start_line, end_line, expect_first, expect_last):
    """1-based inclusive slice of a CE source, asserting its boundary text."""
    lines = _lines(path)
    first = lines[start_line - 1].strip()
    last = lines[end_line - 1].strip()
    if expect_first not in first or expect_last not in last:
        raise AssertionError(f"extraction boundary moved in {path}: {first!r} .. {last!r}")
    return "\n".join(lines[start_line - 1:end_line]) + "\n"


def _function_verbatim(path, signature, after_line=0):
    """Verbatim text from a definition line starting with `signature` (at or
    after 1-based line `after_line`) through the first following line that is
    exactly `}` or `};` (a column-zero close)."""
    lines = _lines(path)
    for index, line in enumerate(lines):
        if index < after_line:
            continue
        if line.startswith(signature) and not line.rstrip().endswith(";"):
            for end in range(index, len(lines)):
                if lines[end] in ("}", "};"):
                    return "\n".join(lines[index:end + 1]) + "\n"
            break
    raise AssertionError(f"signature not found in {path}: {signature}")


def _render_gate_condition():
    """The condition of structure_render.c:590, taken verbatim from the source
    line (the gate's `if (` and `)` are the only text outside it)."""
    line = _lines(HCU / "source/structures/structure_render.c")[589].strip()
    prefix, suffix = "if (", ")"
    assert line.startswith(prefix) and line.endswith(suffix), line
    condition = line[len(prefix):-len(suffix)]
    assert condition == "breakable_surface_extant(material->breakable_surface_index)", condition
    return condition


def _generate_inc(directory):
    # vehicles.c:2681-2698: the floor/ceiling clamp block inside the
    # vehicle update (the block the CE reads at 2681-2682).
    vehicle = _slice_verbatim(SRC_VEHICLES, 2681, 2698,
                              "real floor = global_structure_bsp_get()->vehicle_floor;", "}")
    # line 71 is the prototype; the definition is at line 338.
    breakable_valid = _function_verbatim(SRC_BREAK, "static boolean breakable_surface_indices_valid(", 337)
    breakable_extant = _function_verbatim(SRC_BREAK, "boolean breakable_surface_extant(")
    # line 246 is the prototype; the definition is at line 632.
    surface_broken = _function_verbatim(SRC_PATH, "static boolean surface_is_broken(", 631)
    # object_lights.c:258-260 macro and 270-277 struct, verbatim.
    lights = _lines(SRC_LIGHTS)
    macro = "\n".join(lights[257:260]) + "\n"
    vertex_struct = _function_verbatim(SRC_LIGHTS, "struct environment_vertex_compressed")
    assert macro.startswith("#define structure_material_get_vertex("), macro
    assert "struct environment_vertex_compressed" in vertex_struct
    # structure_visibility.c:192-196 struct and the leaf surface-reference
    # loop (the for loop inside structure_visibility_build_surfaces_traverse_leaf).
    vis = _lines(SRC_VIS)
    loop_start = [i for i, line in enumerate(vis)
                  if line.strip() == "for (reference_index = leaf->first_surface_reference_index;"]
    assert len(loop_start) == 1, loop_start
    loop_end = next(i for i in range(loop_start[0], len(vis)) if vis[i] == "\t\t}")
    surface_reference_loop = "\n".join(vis[loop_start[0]:loop_end + 1]) + "\n"
    surface_reference_struct = _function_verbatim(SRC_VIS, "struct structure_visibility_surface_reference")
    text = (
        "/* generated from CE sources by test_c4_parity_collision_consumers.py */\n"
        "static void c4_vehicle_bounds_clamp(struct c4_vehicle *vehicle)\n{\n"
        + vehicle
        + "}\n"
        + breakable_valid
        + breakable_extant
        + surface_broken
        + "static int c4_material_breakable_gate(struct c4_material_breakable const *material)\n{\n"
        + "\tif (" + _render_gate_condition() + ")\n\t\treturn 1;\n\treturn 0;\n}\n"
        + "static boolean c4_surface_broken(struct structure_bsp const *structure, long surface_index)\n{\n"
        + "\treturn surface_is_broken(structure, surface_index);\n}\n"
        + surface_reference_struct
        + "static short c4_leaf_surface_refs(struct c4_vis_structure *structure, struct c4_leaf *leaf,\n"
        + "\tunsigned long *surface_flags, long *surface_indices, short maximum_count)\n{\n"
        + "\tshort found_count = 0;\n"
        + "\tlong reference_index;\n"  # declared at structure_visibility.c:1359
        + surface_reference_loop
        + "\treturn found_count;\n}\n"
        + vertex_struct
        + macro
        + "static struct environment_vertex_compressed const *c4_vertex_at(struct c4_material const *material, long index)\n{\n"
        + "\treturn structure_material_get_vertex(material, index);\n}\n"
    )
    # surface_is_broken is static in path.c; forward-declared text is copied
    # verbatim, so it is defined here as static too.
    text = text.replace("static boolean surface_is_broken(", "static boolean surface_is_broken(", 1)
    (Path(directory) / "c4_extract_consumers.inc").write_text(text, encoding="latin-1")
    return text


_CACHE = {}


def _run(args):
    if "exe" not in _CACHE:
        compiler = shutil.which("gcc")
        if not compiler:
            raise unittest.SkipTest("GCC unavailable for C4 consumer probe")
        directory = tempfile.mkdtemp(prefix="c4-consumers-")
        _CACHE["dir"] = directory
        _generate_inc(directory)
        exe = Path(directory) / "c4-consumers"
        command = [
            compiler, *host_abi32_flags(), "-std=gnu99", "-O2", "-fshort-wchar",
            "-DHALO_PS2=1", "-D_X86_=1", "-D_STDCALL_SUPPORTED=1",
            "-D__cdecl=", "-D__stdcall=", "-D__fastcall=", "-D__declspec(x)=",
            "-I" + directory,
            "-I" + str(HCU / "port/ps2/include"),
            "-I" + str(HCU / "port/include/xdk"),
            "-I" + str(HCU / "source/tag_files"),
            "-I" + str(HCU / "source/memory"),
            "-I" + str(HCU / "source/math"),
            "-I" + str(HCU / "source"), "-I" + str(HCU / "source/cseries"),
            "-I" + str(HCU / "source/objects"), "-I" + str(HCU / "source/scenario"),
            "-I" + str(HCU / "source/physics"),
            "-include", str(PREAMBLE),
            "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
            "-include", str(ORDER),
            str(MAIN), str(HCU / "source/physics/bsp2d.c"),
            "-Wl,--gc-sections", "-lm", "-o", str(exe),
        ]
        built = subprocess.run(command, capture_output=True, text=True)
        if built.returncode != 0:
            raise AssertionError((built.stdout + built.stderr)[-20000:])
        _CACHE["exe"] = exe
    run = subprocess.run([str(_CACHE["exe"])] + list(args), capture_output=True, text=True)
    if run.returncode in (-31, 159):
        raise unittest.SkipTest("sandbox blocks native ILP32 execution with SIGSYS")
    if run.returncode != 0:
        raise AssertionError(run.stdout + run.stderr)
    return run.stdout.strip()


def _vehicle_oracle(floor, ceiling, z, vz, seat):
    """Independent restatement of vehicles.c:2684-2697 for float32 inputs."""
    f32 = lambda v: struct.unpack("f", struct.pack("f", v))[0]  # noqa: E731
    if floor != 0.0 and z < floor:
        vz = f32(vz + f32(f32(f32(f32(floor - z) * f32(0.015625)) - f32(vz * f32(0.0625))) * seat))
    if ceiling != 0.0 and z > ceiling:
        vz = f32(vz - f32(f32(f32(f32(z - ceiling) * f32(0.015625)) + f32(vz * f32(0.0625))) * seat))
    return vz


class C4ConsumerVehicleFloorCeiling(unittest.TestCase):
    def _vz(self, floor, ceiling, z, vz=-1.0, seat=2.0):
        out = _run(["v", repr(floor), repr(ceiling), repr(z), repr(vz), repr(seat)])
        return float(out.split("=")[1])

    def test_vehicle_floor_clamp_matches_oracle_and_varies_with_floor(self):
        self.assertAlmostEqual(self._vz(0.0, 0.0, 1.0), -1.0, places=5)  # disabled
        floor_a = self._vz(5.0, 0.0, 1.0)
        floor_b = self._vz(8.0, 0.0, 1.0)
        self.assertAlmostEqual(floor_a, _vehicle_oracle(5.0, 0.0, 1.0, -1.0, 2.0), places=4)
        self.assertAlmostEqual(floor_b, _vehicle_oracle(8.0, 0.0, 1.0, -1.0, 2.0), places=4)
        self.assertNotAlmostEqual(floor_a, floor_b, places=3)

    def test_vehicle_ceiling_clamp_matches_oracle_and_varies_with_ceiling(self):
        ceil_a = self._vz(0.0, 5.0, 9.0)
        ceil_b = self._vz(0.0, 7.0, 9.0)
        self.assertAlmostEqual(ceil_a, _vehicle_oracle(0.0, 5.0, 9.0, -1.0, 2.0), places=4)
        self.assertAlmostEqual(ceil_b, _vehicle_oracle(0.0, 7.0, 9.0, -1.0, 2.0), places=4)
        self.assertNotAlmostEqual(ceil_a, ceil_b, places=3)

    def test_bounds_inside_leave_velocity_unchanged(self):
        self.assertAlmostEqual(self._vz(2.0, 9.0, 5.0), -1.0, places=5)


class C4ConsumerBreakableMaterial(unittest.TestCase):
    def _extant(self, index, flags):
        return int(_run(["m", str(index), flags]).split("=")[1])

    def test_structure_render_gate_follows_material_index(self):
        # structure_render.c:590: draw is gated on breakable_surface_extant(material index).
        self.assertEqual(self._extant(-1, "0"), 1)                  # NONE: always drawn
        self.assertEqual(self._extant(3, "8"), 1)                   # bit 3 set: intact
        self.assertEqual(self._extant(3, "0"), 0)                   # bit 3 clear: broken, gated
        self.assertEqual(self._extant(4, "8"), 0)                   # bit 4 clear: broken, gated
        self.assertEqual(self._extant(40, "0"), 0)                  # in range, bit clear: broken
        self.assertEqual(self._extant(300, "0"), 1)                 # past MAXIMUM_BREAKABLE_SURFACES_PER_MAP: never broken


class C4ConsumerCollisionSurfaceBreakable(unittest.TestCase):
    def _broken(self, index, flags):
        return int(_run(["s", str(index), flags]).split("=")[1])

    def test_surface_is_broken_follows_breakable_index(self):
        # path.c surface_is_broken (ai/path.c:637-660) reads collision_surface.breakable_surface_index.
        self.assertEqual(self._broken(2, "0"), 1)     # bit 2 clear: broken
        self.assertEqual(self._broken(2, "4"), 0)     # bit 2 set: intact
        self.assertEqual(self._broken(5, "4"), 1)     # index 5 bit clear: broken, so index changes result


def _surface_refs_oracle(refs, surface_count, env_flags, maximum):
    """Independent restatement of structure_visibility.c:1357-1377."""
    out = []
    for index in refs:
        if index < 0 or index >= surface_count:
            continue
        if not (env_flags >> index) & 1 or index in out:
            continue
        if len(out) >= maximum:
            break
        out.append(index)
    return out


class C4ConsumerSurfaceReferences(unittest.TestCase):
    def _refs(self, env, refs, maximum):
        out = _run(["r", format(env, "x"), ",".join(str(r) for r in refs), str(maximum)])
        body = out.split("surface_refs=[", 1)[1].split("]", 1)[0]
        return [int(v) for v in body.split(",") if v]

    def test_surface_references_leaf_loop_follows_surface_index(self):
        env = 0b1111  # surfaces 0..3 are environment surfaces
        base = self._refs(env, [0, 1, 2], 8)
        self.assertEqual(base, _surface_refs_oracle([0, 1, 2], 4, env, 8))
        moved = self._refs(env, [0, 3, 2], 8)  # one reference's surface_index changed
        self.assertEqual(moved, _surface_refs_oracle([0, 3, 2], 4, env, 8))
        self.assertNotEqual(base, moved)
        # out-of-range reference (index 9 >= surfaces.count) is skipped
        self.assertEqual(self._refs(env, [0, 9, 2], 8), [0, 2])
        # maximum_count bounds the output
        self.assertEqual(self._refs(env, [0, 1, 2], 2), [0, 1])


class C4ConsumerCompressedVertexData(unittest.TestCase):
    def test_vertex_lookup_follows_compressed_vertex_data_address(self):
        # object_lights.c:258-260 macro, verbatim; index 1 readback from each buffer.
        self.assertEqual(_run(["x", "A"]), "vertex_x=1")
        self.assertEqual(_run(["x", "B"]), "vertex_x=7")


if __name__ == "__main__":
    unittest.main()
