"""Run the pinned CE BSP pill code and parent oracle on one synthetic floor.

Host ILP32 only. This is deliberately not a retail-BSP or EE qualification.
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


class M3CeSyntheticCollision(unittest.TestCase):
    def test_ce_surface_aware_pill_matches_parent_on_synthetic_floor(self):
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC unavailable for HCU synthetic collision fixture")
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "m3-ce-synthetic-collision"
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
                "-I" + str(ROOT / "src"),
                "-include", str(ROOT / "tests/m3_ce_collision_host_preamble.h"),
                "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
                str(ROOT / "tests/m3_ce_collision_synthetic_main.c"),
                str(HCU / "source/physics/collision_bsp.c"),
                str(HCU / "source/physics/bsp2d.c"),
                str(ROOT / "src/game/collide.c"),
                str(ROOT / "src/game/pill.c"),
                "-Wl,--gc-sections", "-lm", "-o", str(executable),
            ]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, (built.stdout + built.stderr)[-20000:])
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            if run.returncode in (-31, 159):
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn(
                "synthetic_floor ce_surface=0 ce_t=0.375000 "
                "parent_pill_z=0.250000 parent_vector_t=0.500000 status=passed",
                run.stdout,
            )
            self.assertIn(
                "synthetic_boundary pill_new_t=0.375000 normal_z=1.000 status=observed",
                run.stdout,
            )
            self.assertIn(
                "synthetic_outside_square ce_surface_hit=0 parent_grounded=0 "
                "parent_z=-1.000 status=passed",
                run.stdout,
            )
            self.assertIn(
                "malformed_cycle ce_surface_hit=0 pill_new_hit=0 status=bounded",
                run.stdout,
            )
            self.assertIn(
                "malformed_child ce_surface_hit=0 status=bounded", run.stdout,
            )
            self.assertIn(
                "malformed_leaf_refs ce_surface_hit=0 status=bounded", run.stdout,
            )
            self.assertIn(
                "malformed_edge_ring edge_limit=8 polygon_limit=8 status=bounded",
                run.stdout,
            )


if __name__ == "__main__":
    unittest.main()
