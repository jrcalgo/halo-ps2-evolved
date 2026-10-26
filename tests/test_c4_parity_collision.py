"""C4 member-exact collision parity probes.

Each test drives one CE consumer path on a synthetic square and checks that the
consumer's observable result changes exactly as the varied member changes.
Host ILP32 only (gcc -m32 via host_abi32). Members that cannot be driven on the
host are recorded as blocked (with the reason) in
docs/reports/m4-c4-parity-collision-2026-10-26.json.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tools"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402

WALK_MAIN = ROOT / "tests/c4_parity_collision_walk_main.c"
PREAMBLE = ROOT / "tests/m3_ce_collision_host_preamble.h"
SOURCES = [
    HCU / "source/physics/collision_bsp.c",
    HCU / "source/physics/bsp2d.c",
    HCU / "source/physics/collision_features.c",
]


def _build_walk(temporary):
    compiler = shutil.which("gcc")
    if not compiler:
        raise unittest.SkipTest("GCC unavailable for HCU collision parity fixture")
    executable = Path(temporary) / "c4-parity-collision-walk"
    command = [
        compiler, *host_abi32_flags(), "-std=gnu99", "-O2", "-fshort-wchar",
        "-DHALO_PS2=1", "-D_X86_=1", "-D_STDCALL_SUPPORTED=1",
        "-D__COLLISION_USAGE_H=1",
        "-D__cdecl=", "-D__stdcall=", "-D__fastcall=", "-D__declspec(x)=",
        "-ffunction-sections", "-fdata-sections", "-Wno-unused-function",
        "-I" + str(HCU / "port/ps2/include"),
        "-I" + str(HCU / "port/include/xdk"),
        "-I" + str(HCU / "source/tag_files"),
        "-I" + str(HCU / "source/memory"),
        "-I" + str(HCU / "source/math"),
        "-I" + str(HCU / "source"), "-I" + str(HCU / "source/cseries"),
        "-I" + str(HCU / "source/objects"), "-I" + str(HCU / "source/scenario"),
        "-I" + str(HCU / "source/physics"),
        "-I" + str(ROOT / "src"),
        "-include", str(PREAMBLE),
        "-include", str(ROOT / "tests/c4_host_shims/c4_collision_order.h"),
        "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
        str(WALK_MAIN),
        *[str(source) for source in SOURCES],
        "-Wl,--gc-sections", "-lm", "-o", str(executable),
    ]
    built = subprocess.run(command, capture_output=True, text=True)
    if built.returncode != 0:
        raise AssertionError((built.stdout + built.stderr)[-20000:])
    return executable


_CACHE = {}


def _walk_output():
    """Build and run the walk probe once per test session; return its stdout."""
    if "out" not in _CACHE:
        with tempfile.TemporaryDirectory() as temporary:
            executable = _build_walk(temporary)
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            if run.returncode in (-31, 159):
                raise unittest.SkipTest("sandbox blocks native ILP32 execution with SIGSYS")
            _CACHE["out"] = run.stdout
            _CACHE["rc"] = run.returncode
            _CACHE["err"] = run.stderr
    return _CACHE["out"]


def _line(member, variant):
    for line in _walk_output().splitlines():
        if line.startswith(f"member={member} variant={variant} "):
            return line
    raise AssertionError(f"no probe line for {member} variant={variant}\n{_walk_output()}")


class C4ParityCollision(unittest.TestCase):
    def test_probe_process_exits_clean(self):
        _walk_output()
        self.assertEqual(_CACHE["rc"], 0, _CACHE["out"] + _CACHE["err"])
        self.assertIn("c4_collision_walk failures=0", _CACHE["out"])

    def test_collision_surface_first_edge_index(self):
        # Start ring at edge 2 rotates the CE polygon; edge 7 is bounded empty.
        self.assertIn("points=[0,1,2,3] edge_count=4 status=passed",
                      _line("collision_surface.first_edge_index", "baseline"))
        self.assertIn("points=[2,3,0,1] edge_count=4 status=passed",
                      _line("collision_surface.first_edge_index", "start2"))
        self.assertIn("points=0 edge_count=0 status=bounded",
                      _line("collision_surface.first_edge_index", "out_of_range"))

    def test_collision_edge_edge_indices(self):
        # Re-linking edge 0 to edge 2 drops vertex 1 from the CE ring walk.
        self.assertIn("points=[0,2,3] edge_count=3 status=passed",
                      _line("collision_edge.edge_indices", "skip_edge1"))

    def test_collision_edge_surface_indices(self):
        # Surface 0 on the reverse side flips the walk to vertex 1 / edge 3.
        self.assertIn("points=[1,3] edge_count=2 status=passed",
                      _line("collision_edge.surface_indices", "reverse_edge0"))

    def test_collision_vertex_first_edge_index(self):
        # Vertex feature is taken from its first edge's surface; a missing or
        # surface-less edge yields no feature (CE returns without emitting).
        self.assertIn("sphere_count=1 surface=0 status=passed",
                      _line("collision_vertex.first_edge_index", "baseline"))
        self.assertIn("sphere_count=0 status=bounded",
                      _line("collision_vertex.first_edge_index", "out_of_range"))
        self.assertIn("sphere_count=0 status=bounded",
                      _line("collision_vertex.first_edge_index", "edge_without_surface"))


RENDER_BOUNDS_MAIN = ROOT / "tests/c4_parity_collision_render_bounds_main.c"
RENDER_CAMERAS = HCU / "source/render/render_cameras.c"
_RENDER_CACHE = {}


def _render_bounds_output():
    """Build render_cameras.c + the world_bounds probe once and run it."""
    if "out" not in _RENDER_CACHE:
        compiler = shutil.which("gcc")
        if not compiler:
            raise unittest.SkipTest("GCC unavailable for HCU render bounds fixture")
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "c4-parity-render-bounds"
            command = [
                compiler, *host_abi32_flags(), "-std=gnu99", "-O2", "-fshort-wchar",
                "-DHALO_PS2=1", "-D_X86_=1", "-D_STDCALL_SUPPORTED=1",
                "-D__cdecl=", "-D__stdcall=", "-D__fastcall=", "-D__declspec(x)=",
                "-I" + str(HCU / "port/ps2/include"),
                "-I" + str(HCU / "port/include/xdk"),
                "-I" + str(HCU / "source/tag_files"),
                "-I" + str(HCU / "source/memory"),
                "-I" + str(HCU / "source/math"),
                "-I" + str(HCU / "source"), "-I" + str(HCU / "source/cseries"),
                "-I" + str(HCU / "source/objects"), "-I" + str(HCU / "source/scenario"),
                "-I" + str(HCU / "source/render"),
                "-include", str(PREAMBLE),
                "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
                str(RENDER_BOUNDS_MAIN), str(RENDER_CAMERAS),
                "-Wl,--gc-sections", "-lm", "-o", str(executable),
            ]
            built = subprocess.run(command, capture_output=True, text=True)
            if built.returncode != 0:
                raise AssertionError((built.stdout + built.stderr)[-20000:])
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            if run.returncode in (-31, 159):
                raise unittest.SkipTest("sandbox blocks native ILP32 execution with SIGSYS")
            _RENDER_CACHE["out"] = run.stdout + run.stderr
            _RENDER_CACHE["rc"] = run.returncode
    return _RENDER_CACHE["out"]


class C4ParityRenderBounds(unittest.TestCase):
    def test_frustum_world_bounds_consumer_render_cameras(self):
        out = _render_bounds_output()
        self.assertEqual(_RENDER_CACHE["rc"], 0, out)
        # Frustum consumer only: baseline bounds admit the cube; moving x or z
        # range culls it at the early-out (render_cameras.c:526-546).
        self.assertIn("variant=baseline visible=2 status=passed", out)
        self.assertIn("variant=x_shifted visible=0 status=passed", out)
        self.assertIn("variant=z_excluded visible=0 status=passed", out)


if __name__ == "__main__":
    unittest.main()
