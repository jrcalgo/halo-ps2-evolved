"""C4 item 3 (real-source): live-unit pathfinding, smoothing, avoidance, actor movement and replan,
mid-path breakable destruction, and point-to-surface selection with the real ground search.

Unchanged CE translation units are built as clang -m32 (ILP32): ai/path.c, ai/path_smoothing.c,
ai/path_structure_bsp.c, ai/path_obstacle_avoidance.c, ai/path_obstacles.c, ai/actor_moving.c,
ai/ai_profile.c, math/real_math.c, math/matrix_math.c, physics/bsp2d.c. Two files are generated from
the HCU source by exact text: physics/collision_bsp.c (the whole file, with its own header include
dropped and the header's result structs inserted, because of Xbox header conflicts on this host) and
the actor/biped functions (ai/actors.c, units/bipeds.c). The retail payload is copied byte-for-byte
from the decompressed Prisoner BSP. Data-only and abort-only stubs are in tests/c4_live_pathfinding_*.c.
"""
from pathlib import Path
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
SOURCE = HCU / "source"
sys.path.insert(0, str(ROOT / "tests"))
import test_hcu_mp_path_consumer  # noqa: E402,F401  (puts halo2ps2 and tools on sys.path)
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from tools.ctag_schema_walk import read_xbox_tag_region  # noqa: E402

PRELUDE = ["-std=gnu99", "-m32", "-fms-extensions", "-fshort-wchar", "-fwrapv",
           "-fno-strict-aliasing", "-w", "-include", str(ROOT / "tests/soundreq_host_prefix.h")]
RETAIL_PROBES = (0, 94, 100, 457, 500, 902, 1, 2838)   # verdict/ground mix, all selected as themselves
WALL_PROBES = {401: 1373, 2834: 1373}                    # vertical walls: ground search returns the floor below


def extract(path, marker):
    source = Path(path).read_text()
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise AssertionError(f"unterminated {marker}")


def include_dirs():
    dirs = [str(d) for d in sorted(p for p in SOURCE.rglob("*") if p.is_dir())] + [str(SOURCE)]
    return ([f"-I{ROOT / 'tests/c4_shim'}", f"-I{HCU / 'port/ps2/include'}", f"-I{HCU / 'port/linux/game'}",
             f"-I{HCU / 'port/include'}", f"-I{HCU / 'port/include/xdk'}",
             f"-I{ROOT / 'submodules/halo-ps2/engine/src'}", f"-I{ROOT / 'src'}", f"-I{ROOT / 'tests'}"]
            + [f"-I{d}" for d in dirs])


def raw_full_payload(map_name):
    """Collision records copied byte-for-byte from the decompressed BSP, plus the BSP3D/BSP2D trees.
    Layout: nine uint32 counts, then surfaces(12) edges(24) vertices(16) flags(1) bsp3d nodes(12)
    planes(16) leaves(8) bsp2d references(8) bsp2d nodes(20)."""
    map_path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    header = mapinfo.read_header(map_path)
    index = tagindex.TagIndex.read(map_path)
    region, _tag_base, _ = read_xbox_tag_region(map_path)
    location = bsp.locate(index, region, header.decompressed_size)[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    root = struct.unpack_from("<I", image, 0)[0] - location.address

    def block(base, at):
        count, address = struct.unpack_from("<iI", image, base + at)
        return count, address - location.address

    _count, coff = block(root, 0xB0)
    secs = [block(coff, 0x3C), block(coff, 0x48), block(coff, 0x54)]
    flags = block(root, 0x1E4)
    trees = [block(coff, 0), block(coff, 12), block(coff, 24), block(coff, 36), block(coff, 48)]
    out = bytearray(struct.pack("<9I", secs[0][0], secs[1][0], secs[2][0], flags[0],
                                trees[0][0], trees[1][0], trees[2][0], trees[3][0], trees[4][0]))
    for (count, at), stride in zip(secs, (12, 24, 16)):
        out += image[at:at + count * stride]
    out += image[flags[1]:flags[1] + flags[0]]
    for (count, at), stride in zip(trees, (12, 16, 8, 8, 20)):
        out += image[at:at + count * stride]
    return bytes(out)


def collision_whole_source():
    """collision_bsp.c verbatim, except its own header include (Xbox conflicts) and the header's result structs."""
    source = (SOURCE / "physics/collision_bsp.c").read_text()
    header = (SOURCE / "physics/collision_bsp.h").read_text()
    blocks = re.findall(r"^struct \w+\n\{.*?\n\};", header, re.S | re.M)
    lines = source.split("\n")
    last = max(i for i, line in enumerate(lines) if line.startswith("#include"))
    out = []
    for i, line in enumerate(lines):
        if line.startswith('#include "collision_bsp.h"'):
            continue
        out.append(line)
        if i == last:
            out.append("\n".join(blocks))
    return "\n".join(out)


def actors_slice_source():
    includes, seen = [], set()
    for path in (SOURCE / "ai/actors.c", SOURCE / "units/bipeds.c", SOURCE / "physics/collision_bsp.c"):
        for line in Path(path).read_text().splitlines():
            if line.startswith("#include") and line not in seen:
                seen.add(line)
                includes.append(line)
    bodies = "\n\n".join([
        extract(SOURCE / "units/bipeds.c", "static long biped_find_ground_surface("),
        extract(SOURCE / "ai/actors.c", "void actor_find_pathfinding_location("),
        extract(SOURCE / "units/bipeds.c", "long biped_find_pathfinding_surface_index("),
    ]).replace("struct vehicle_definition *", "void *")
    return "\n".join(includes) + '\n#include "cseries/errors.h"\n#include <stdlib.h>\n' + bodies + "\n"


def tag_slice_source():
    source = SOURCE / "tag_files/tag_groups.c"
    return ('#include "cseries/cseries.h"\n#include "tag_files/tag_files.h"\n#include "tag_files/tag_groups.h"\n'
            '#include "cseries/errors.h"\nboolean custom_edition_cache_tags_loaded(void);\n'
            "void tag_index_error(const char *what, long index, long count);\n"
            "enum { TAG_EMPTY_DATA_SIZE = 0x10000 };\n"
            "static unsigned long tag_empty_data_bytes[TAG_EMPTY_DATA_SIZE / sizeof(unsigned long)];\n"
            + extract(source, "void *tag_empty_data(") + "\n\n"
            + extract(source, "void *tag_block_get_element_with_size(") + "\n")


def compiler():
    cc = shutil.which("clang")
    if cc is None:
        raise unittest.SkipTest("clang -m32 required for the ILP32 host build")
    return cc


class C4RealPathfindingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="c4-real-path-")
        cls.addClassCleanup(cls.tmp.cleanup)
        work = Path(cls.tmp.name)
        cls.cc = compiler()
        cls.includes = include_dirs()
        (work / "collision_whole.c").write_text(collision_whole_source())
        (work / "actors_slice.c").write_text(actors_slice_source())
        (work / "tag_slice.c").write_text(tag_slice_source())
        (work / "retail-full.bin").write_bytes(raw_full_payload("prisoner"))
        cls.payload = work / "retail-full.bin"
        cls.sources = {
            "path": SOURCE / "ai/path.c",
            "path_smoothing": SOURCE / "ai/path_smoothing.c",
            "path_structure_bsp": SOURCE / "ai/path_structure_bsp.c",
            "path_obstacle_avoidance": SOURCE / "ai/path_obstacle_avoidance.c",
            "path_obstacles": SOURCE / "ai/path_obstacles.c",
            "actor_moving": SOURCE / "ai/actor_moving.c",
            "ai_profile": SOURCE / "ai/ai_profile.c",
            "real_math": SOURCE / "math/real_math.c",
            "matrix_math": SOURCE / "math/matrix_math.c",
            "bsp2d": SOURCE / "physics/bsp2d.c",
            "collision_whole": work / "collision_whole.c",
            "actors_slice": work / "actors_slice.c",
            "tag_slice": work / "tag_slice.c",
            "driver": ROOT / "tests/c4_live_pathfinding_real_host.c",
            "stubs": ROOT / "tests/c4_live_pathfinding_stubs.c",
            "abort": ROOT / "tests/c4_live_pathfinding_abort.c",
        }
        cls.work = work
        cls.opt = {opt: cls.build(opt) for opt in ("-O1", "-O0")}

    @classmethod
    def build(cls, opt):
        objects = []
        for name, source in cls.sources.items():
            obj = cls.work / f"{name}{opt.replace('-', '_')}.o"
            result = subprocess.run([cls.cc, *PRELUDE, "-c", opt, *cls.includes, str(source), "-o", str(obj)],
                                    capture_output=True, text=True)
            assert result.returncode == 0, f"{name}: {result.stdout}{result.stderr}"
            objects.append(str(obj))
        exe = cls.work / f"c4real{opt.replace('-', '_')}"
        link = subprocess.run([cls.cc, "-m32", "-rdynamic", "-o", str(exe), *objects, "-lm"],
                              capture_output=True, text=True)
        assert link.returncode == 0, link.stdout + link.stderr
        return exe

    def run_driver(self, exe, args=()):
        run = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=120)
        return run.returncode, run.stdout + run.stderr

    def test_synthetic_scenarios_pass_on_real_ce_code(self):
        code, output = self.run_driver(self.opt["-O1"])
        self.assertEqual(code, 0, output)
        for needle in (
            "smoothing.intact invariants=walkable,unbroken,segments_on_valid_ground,goal_preserved result=passed",
            "smoothing.deterministic result=passed",
            "smoothing.gate_blocked avoids_gate=1 result=passed",
            "breakable.smoothing_avoids_destroyed result=passed",
            "actor.progress ticks=81 bound=400 final_surface=9 result=passed",
            "actor.recovery stall_ticks=30 replans=1 held=30 ticks=118 final_surface=9 avoided_gate=1 result=passed",
            "selection.support_surface selected=7 projected=25.000,15.000 result=passed",
            "selection.attempt_throttled selected=-1 result=passed",
            "selection.flying selected=-1 result=passed",
            "disc.steer min_distance=2.504 radius=2.000 steered_around=1 result=passed",
            "disc.start_inside_characterised valid=1 steps=1 result=passed",
            "midpath.breakable crossed_before=1 broken_at_tick=20 entered_gate=0 ticks=88 final_surface=9 result=passed",
            "avoidance.blocked discs=8 find=1 avoid_returned=0 build_valid=0 result=passed",
            "summary scenarios=9 result=passed",
        ):
            self.assertIn(needle, output)

    def test_repeat_builds_at_two_optimisation_levels_agree(self):
        """Stand-in for native-versus-ILP32 parity, which cannot build (see the report)."""
        _, o1 = self.run_driver(self.opt["-O1"])
        _, o0 = self.run_driver(self.opt["-O0"])
        self.assertEqual(o1, o0, "output differs between -O1 and -O0 ILP32 builds")

    def test_retail_prisoner_selection_through_real_ground_search(self):
        for surface in RETAIL_PROBES:
            code, output = self.run_driver(self.opt["-O1"], ("retail", str(self.payload), str(surface)))
            self.assertEqual(code, 0, output)
            self.assertRegex(output, rf"retail\.selection surface={surface} .* selected={surface} result=passed")

    def test_retail_wall_surfaces_are_not_ground(self):
        """Vertical walls cannot be hit by the downward ground ray: the search returns the floor below."""
        for surface, floor in WALL_PROBES.items():
            code, output = self.run_driver(self.opt["-O1"], ("retail", str(self.payload), str(surface)))
            self.assertEqual(code, 1, output)
            self.assertIn(f"retail.selection surface={surface} ", output)
            self.assertIn(f"ground={floor} selected={floor} result=failed", output)

    def test_structure_bsp_pathfinding_surfaces_walkable_bit_gates_selection_and_routes(self):
        """Member structure_bsp.pathfinding_surfaces: the per-surface flag byte (bit 6 walkable, bit 7
        breakable) read by the real CE edge builder and selector. Asserts on the retail payload's flag
        block, and on the synthetic route that changes when the walkable bit of the gate is cleared."""
        payload = self.payload.read_bytes()
        counts = struct.unpack_from("<9I", payload, 0)
        surfaces, edges, vertices, flag_count = counts[0], counts[1], counts[2], counts[3]
        flags_at = 36 + surfaces * 12 + edges * 24 + vertices * 16
        flags = payload[flags_at:flags_at + flag_count]
        self.assertEqual(flag_count, surfaces)
        walkable = {surface for surface in RETAIL_PROBES if flags[surface] & (1 << 6)}
        # pinned from the stock Prisoner flag block: walkable 0, 1, 94, 500; not walkable 100, 457, 902, 2838
        self.assertEqual(walkable, {0, 1, 94, 500})
        inventory = json.loads((ROOT / "build/m2-mp-breakable-inventory-13/inventory.json").read_text())
        for row in inventory["maps"]["prisoner"]["breakable_surfaces"]:
            self.assertEqual(flags[row["surface_index"]] & (1 << 6), 0,
                             f"stock breakable {row['surface_index']} carries the walkable bit")
        code, driver_output = self.run_driver(self.opt["-O1"])
        self.assertEqual(code, 0, driver_output)
        self.assertIn("smoothing.gate_blocked avoids_gate=1 result=passed", driver_output)
        # the selector does not consult the walkable bit: non-walkable probes are still selected
        for surface in sorted(set(RETAIL_PROBES) - walkable):
            code, output = self.run_driver(self.opt["-O1"], ("retail", str(self.payload), str(surface)))
            self.assertEqual(code, 0, output)
            self.assertRegex(output, rf"selected={surface} result=passed")
        self.assertIn("breakable.smoothing_avoids_destroyed result=passed", driver_output)


if __name__ == "__main__":
    unittest.main()
