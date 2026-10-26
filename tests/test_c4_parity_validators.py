"""C4 validator parity for the three zero-byte BSP schema check descriptors.

Members (ledger family bsp-root-and-checks, gap validator-execution-unqualified):
  structure_bsp.structure_bsp_check
  structure_detail_object_data.structure_detail_object_data_check
  collision_bsp.structure_collision_bsp_check

tests/c4_validators_main.c includes CE's tag_schema_collision.c verbatim, so the static
callbacks and their callees run unmodified. The structs they use are copied verbatim from
tag_validate.c (where CE keeps them private) by this harness. Only the reporting functions
and data accessors are stubbed (see the driver's comments). Valid structures must be
accepted with no correction; malformed ones must be refused with a message, or corrected in
place with the rewritten value asserted.
"""
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
GAME = ROOT / "submodules/halo-ce-universal/port/linux/game"
SCHEMA = GAME / "tag_schema_collision.c"
VALIDATE = GAME / "tag_validate.c"
SCHEMA_SHA256 = "7163d79c74270009e7fe371422aa7997c5caeba5f12ae24647474b1d6e8d1b52"
VALIDATE_SHA256 = "750928041f687eb612e5af70df37fde81c7601ca773454886582cd32c0bee9cc"
DRIVER = ROOT / "tests/c4_validators_main.c"
HCU = ROOT / "submodules/halo-ce-universal"

# name -> (result, corrections, refused, message fragment or None, extra printed value or None)
EXPECTED = {
    "collision_valid_one_leaf": (1, 0, 0, None, None),
    "collision_nodes_without_planes": (0, 0, 1, "and no planes", None),
    "collision_child_leaf_out_of_range": (1, 1, 0, "is not a leaf nor a node of the tree", ("CHILD_AFTER", "-1")),
    "collision_bsp2d_refs_without_surfaces": (1, 1, 0, "has 2 bsp2d references and no surfaces", ("REFS_AFTER", "0")),
    "detail_no_cells": (1, 0, 0, None, ("DETAIL_VALID_AFTER_EMPTY", "1")),
    "detail_cells_out_of_order": (1, 1, 0, "out of order or past its objects", ("DETAIL_VALID_AFTER_ORDER", "0")),
    "detail_negative_count_index": (1, 1, 0, "out of order or past its objects", ("DETAIL_VALID_AFTER_NEGATIVE", "0")),
    "structure_valid_with_collision": (1, 0, 0, None, None),
    "structure_without_collision_bsp": (0, 0, 1, "has no collision bsp", None),
    "structure_leaf_references_out_of_range": (1, 1, 0, "are not the bsp's 0: none", ("LEAF_COUNT_AFTER", "0")),
    "structure_surface_reference_node_out_of_range": (1, 1, 0, "is not the collision bsp's 1", ("NODE_REF_AFTER", "-1")),
    "structure_negative_leaf_reference_count": (1, 1, 0, "are not the bsp's 0: none", None),
    "structure_portal_plane_out_of_range": (1, 1, 0, "is not the collision bsp's 1", ("PORTAL_PLANE_AFTER", "0")),
    "material_vertex_buffer_contained": (1, 0, 0, None, ("MATERIAL_VB_FORMAT_AFTER_CONTAINED", "1")),
    "material_vertex_buffer_past_region": (0, 1, 0, "are not in a buffer of the bsp's: none", ("MATERIAL_VB_FORMAT_AFTER_PAST", "0")),
}


def _verbatim_types() -> str:
    src = VALIDATE.read_text()
    depth = src.index("MAXIMUM_VALIDATION_DEPTH = 32")
    enum_start = src.rindex("\nenum", 0, depth) + 1
    enum_end = src.index("};", depth) + 2
    frame_start = src.index("struct tag_validation_frame\n{")
    struct_end = src.index("\n};", src.index("struct tag_validation\n{")) + 3
    return src[enum_start:enum_end] + "\n\n" + src[frame_start:struct_end] + "\n"


def _semantics(tmp: Path) -> Path:
    out = tmp / "halo_ps2_msvc_semantics.h"
    subprocess.run([sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                    "--output", str(out), "--all-inlines", "--tags", str(HCU / "source"),
                    "--inlines", str(HCU / "source"), "--inlines", str(HCU / "port/include/xdk")],
                   check=True, capture_output=True, text=True)
    return out


class ValidatorWiringTest(unittest.TestCase):
    def test_source_is_pinned_and_callbacks_are_wired(self):
        schema = SCHEMA.read_bytes()
        validate = VALIDATE.read_bytes()
        self.assertEqual(hashlib.sha256(schema).hexdigest(), SCHEMA_SHA256)
        self.assertEqual(hashlib.sha256(validate).hexdigest(), VALIDATE_SHA256)
        text = schema.decode()
        for definition in ("static boolean structure_collision_bsp_check(",
                           "static boolean structure_detail_object_data_check(",
                           "static boolean structure_bsp_check("):
            self.assertIn(definition, text)
        self.assertIn("COLLISION_BSP_FIELDS(structure_collision_surface_schema, structure_collision_bsp_check)", text)
        self.assertIn("TAG_SCHEMA_CHECK(structure_detail_object_data_check),", text)
        self.assertIn("TAG_SCHEMA_CHECK(structure_bsp_check),", text)
        self.assertIn("case _tag_schema_check:", validate.decode())


class ValidatorExecutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("gcc unavailable for the ILP32 validator driver")
        if not Path(os.environ.get("HALO_HOST_ABI32_ROOT", ROOT / "build/host-abi32/root")).exists():
            raise unittest.SkipTest("host ILP32 sysroot missing")
        import host_abi32
        cls.tmp = Path(tempfile.mkdtemp(prefix="c4-validators-"))
        (cls.tmp / "c4_validators_types.inc").write_text(_verbatim_types())
        semantics = _semantics(cls.tmp)
        includes = [".", "tests", "tests/hcu_scenario_host_shim",
                    "submodules/halo-ce-universal/port/ps2/include",
                    "submodules/halo-ce-universal/port/linux/game",
                    "submodules/halo-ce-universal/port/include",
                    "submodules/halo-ce-universal/source",
                    *[f"submodules/halo-ce-universal/source/{d}" for d in (
                        "cseries", "scenario", "structures", "cache", "tag_files", "objects",
                        "physics", "game", "interface", "math", "sound", "memory", "input")],
                    "src", "submodules/halo-ps2/engine/src",
                    "submodules/halo-ps2/engine/tests/hp2_world_shim"]
        cmd = [cc, *host_abi32.flags(), "-fshort-wchar", "-std=gnu99", "-fms-extensions",
               "-fcommon", "-fwrapv", "-fno-strict-aliasing", "-fno-delete-null-pointer-checks",
               "-DHCU_BSP_RETAIL_INTEGRATION=1", "-DHALO_PS2=1",
               "-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
               "-include", str(semantics), "-w", "-I" + str(cls.tmp)]
        cmd += ["-I" + str(ROOT / p) for p in includes] + ["-I/usr/include"]
        cmd += ["-c", str(DRIVER), "-o", str(cls.tmp / "driver.o")]
        built = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        if built.returncode:
            raise AssertionError(built.stdout + built.stderr)
        exe = cls.tmp / "validators"
        linked = subprocess.run([cc, *host_abi32.flags(), str(cls.tmp / "driver.o"), "-lm",
                                 "-o", str(exe)], capture_output=True, text=True)
        if linked.returncode:
            raise AssertionError(linked.stdout + linked.stderr)
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        if run.returncode == -31:
            raise unittest.SkipTest("sandbox blocks native ILP32 execution with SIGSYS")
        if run.returncode != 0:
            raise AssertionError(run.stdout + run.stderr)
        cls.output = run.stdout
        cls.cases = {}
        cls.values = {}
        for line in run.stdout.splitlines():
            m = re.match(r'CASE (\S+) result=(\d) corrections=(-?\d+) refused=(\d) message="(.*)"$', line)
            if m:
                cls.cases[m.group(1)] = dict(result=int(m.group(2)), corrections=int(m.group(3)),
                                             refused=int(m.group(4)), message=m.group(5))
                continue
            parts = line.split()
            if len(parts) == 2 and parts[0].isupper() and "_" in parts[0]:
                cls.values[parts[0]] = parts[1]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_case_ran(self):
        self.assertEqual(sorted(self.cases), sorted(EXPECTED))

    def test_valid_accepted_and_malformed_rejected_or_corrected(self):
        for name, (result, corrections, refused, fragment, value) in EXPECTED.items():
            with self.subTest(case=name):
                got = self.cases[name]
                self.assertEqual(got["result"], result, got)
                self.assertEqual(got["corrections"], corrections, got)
                self.assertEqual(got["refused"], refused, got)
                if fragment:
                    self.assertIn(fragment, got["message"])
                if value:
                    self.assertEqual(self.values.get(value[0]), value[1], self.output)


if __name__ == "__main__":
    unittest.main()
