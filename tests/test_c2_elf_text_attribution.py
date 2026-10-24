#!/usr/bin/env python3
"""Synthetic-map tests for tools/c2_elf_text_attribution.py.

No game data or toolchain is needed: the map is written here, and the
reachability and attribution functions are called on hand-built inputs.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import c2_elf_text_attribution as c  # noqa: E402


SYNTHETIC_MAP = """\
Discarded input sections

 .reginfo       0x00000000       0x18 /tmp/gone.o

Memory Configuration

Name             Origin             Length             Attributes
*default*        0x00000000         0xffffffff

Linker script and memory map

.text           0x00100000      0x2c0
 .text.alpha    0x00100000       0x40 /closure/all-no-bootstrap-memory/source_a.c.o
                0x00100000                alpha
 .text.beta
                0x00100040       0x80 /closure/all-no-bootstrap-memory/rooted.o
                0x00100040                beta
 *fill*         0x001000c0        0x4
 .text.gamma    0x001000c4       0x20 /parent-hcu-gameplay-60869cbb0e20/core/mat.o
 .text.delta    0x001000e4      0x1dc /closure/all-no-bootstrap-memory/libx.o
.rodata         0x002bc640     0x1000
 .rodata.cst4   0x002bc63c        0x0 /tmp/ltrans.o
 .rodata.s_mem_layout_v2_names
                0x002bc640    0x3c4ff /parent-hcu-gameplay-60869cbb0e20/core/mem.o
                                 0x12 (size before relaxing)
 .rodata.str1.8
                0x002f8b3f        0x0 /parent-hcu-gameplay-60869cbb0e20/core/mem.o
 .rodata.table  0x002f8b40       0x30 /toolchain/install/ps2sdk/ee/lib/libfoo.a(bar.o)
.bss            0x00317a80      0x2000
 .bss.state     0x00317a80       0x10 /closure/all-no-bootstrap-memory/source_a.c.o
 COMMON         0x00318000      0x0f00 /closure/all-no-bootstrap-memory/rooted.o
                0x00318000                shared_one
                0x00318010                shared_two
.data           0x00400000        0x8
 .data.one      0x00400000        0x8 /closure/all-no-bootstrap-memory/source_a.c.o
OUTPUT(/closure/out.elf elf32-nlittlemips)
"""


class ParseMapTest(unittest.TestCase):
    def setUp(self):
        self.sections = c.parse_map(SYNTHETIC_MAP.splitlines())

    def by_name(self, name):
        return [s for s in self.sections if s["name"] == name]

    def test_two_line_and_inline_entries_are_kept(self):
        alpha = self.by_name(".text.alpha")
        self.assertEqual(len(alpha), 1)
        self.assertEqual(alpha[0]["size"], 0x40)
        self.assertEqual(alpha[0]["kind"], "text")
        beta = self.by_name(".text.beta")
        self.assertEqual(beta[0]["size"], 0x80)
        self.assertTrue(beta[0]["path"].endswith("rooted.o"))

    def test_fill_and_zero_sizes_are_dropped(self):
        self.assertFalse(any(s["path"].startswith("*fill*") for s in self.sections))
        self.assertFalse(any(s["size"] == 0 for s in self.sections))

    def test_relaxed_string_section_takes_its_own_size(self):
        mem = self.by_name(".rodata.s_mem_layout_v2_names")
        self.assertEqual(len(mem), 1)
        self.assertEqual(mem[0]["size"], 0x12)
        self.assertTrue(mem[0]["relaxed_from_map"])

    def test_common_block_splits_into_symbols(self):
        one = [s for s in self.sections if s["name"] == "COMMON:shared_one"]
        two = [s for s in self.sections if s["name"] == "COMMON:shared_two"]
        self.assertEqual(one[0]["size"], 0x10)
        # The last symbol runs to the end of the block.
        self.assertEqual(two[0]["size"], 0x0f00 - 0x10)
        self.assertTrue(all(s["kind"] == "bss" for s in one + two))

    def test_kinds(self):
        self.assertEqual(c.section_kind(".text.x"), "text")
        self.assertEqual(c.section_kind(".rodata.str1.8"), "rodata")
        self.assertEqual(c.section_kind(".sdata"), "data")
        self.assertEqual(c.section_kind(".bss.y"), "bss")
        self.assertEqual(c.section_kind("COMMON:z"), "bss")
        self.assertIsNone(c.section_kind(".reginfo"))
        self.assertIsNone(c.section_kind(".pdr"))

    def test_map_header_totals(self):
        totals = c.map_output_totals(SYNTHETIC_MAP.splitlines())
        self.assertEqual(totals, {"text": 0x2c0, "rodata": 0x1000, "bss": 0x2000, "data": 0x8})

    def test_reconcile_adds_one_residual_per_kind(self):
        totals = c.map_output_totals(SYNTHETIC_MAP.splitlines())
        out = c.reconcile(self.sections, totals)
        for kind, want in totals.items():
            have = sum(s["size"] for s in out if s["kind"] == kind)
            self.assertEqual(have, want, kind)
        self.assertTrue(any(s["name"] == "map-residual:rodata" for s in out))

    def test_missing_section_header_raises(self):
        with self.assertRaises(ValueError):
            c.parse_map(["no map here"])


class AttributionTest(unittest.TestCase):
    CLOSURE = "/closure/all-no-bootstrap-memory"
    UNITS = {"source_a.c.o": "source/a.c"}

    def test_closure_unit_maps_to_source(self):
        label = c.source_for(self.CLOSURE + "/source_a.c.o", self.CLOSURE, "/parent-hcu-gameplay-",
                             self.UNITS)
        self.assertEqual(label, "source/a.c")

    def test_unlisted_closure_object_is_labelled_closure(self):
        label = c.source_for(self.CLOSURE + "/other.o", self.CLOSURE, "/parent-hcu-gameplay-", self.UNITS)
        self.assertEqual(label, "closure:other.o")

    def test_rooted_object_uses_its_symbol_owner(self):
        label = c.source_for(self.CLOSURE + "/rooted.o", self.CLOSURE, "/parent-hcu-gameplay-",
                             self.UNITS, sym_owner=lambda sec: self.CLOSURE + "/source_a.c.o",
                             section=".text.alpha")
        self.assertEqual(label, "source/a.c")

    def test_parent_path_is_relative_to_its_marker(self):
        label = c.source_for("/build/parent-hcu-gameplay-60869cbb0e20/core/mat.o", self.CLOSURE,
                             "/parent-hcu-gameplay-", self.UNITS)
        self.assertEqual(label, "parent:60869cbb0e20/core/mat.c")

    def test_sdk_and_gcc_labels(self):
        self.assertEqual(c.source_for("/x/toolchain/install/ps2sdk/ee/lib/libfoo.a", self.CLOSURE,
                                      "/parent-hcu-gameplay-", self.UNITS), "sdk:lib")
        self.assertTrue(c.source_for("/x/toolchain/install/ee/lib/crt0.o", self.CLOSURE,
                                     "/parent-hcu-gameplay-", self.UNITS).startswith("gcc-lib:"))


class ReachabilityTest(unittest.TestCase):
    def setUp(self):
        # root -> a -> b, root -> c, d is reached only through b.
        self.edges = {
            ("root", ".text.root"): {("u", ".text.a"), ("u", ".text.c")},
            ("u", ".text.a"): {("u", ".text.b")},
            ("u", ".text.b"): {("u", ".text.d")},
        }
        self.roots = [("root", ".text.root")]

    def test_reach_and_parent_chain(self):
        visited, parent = c.reach(self.edges, self.roots)
        self.assertIn(("u", ".text.d"), visited)
        self.assertNotIn(("u", ".text.missing"), visited)
        chain = c.path_to(parent, ("u", ".text.d"))
        self.assertEqual([n[1] for n in chain],
                         [".text.root", ".text.a", ".text.b", ".text.d"])

    def test_blocking_a_node_removes_what_only_it_reaches(self):
        blocked = {("u", ".text.b")}
        kept_edges = {k: {v for v in vs if v not in blocked} for k, vs in self.edges.items()
                      if k not in blocked}
        full, _ = c.reach(self.edges, self.roots)
        kept, _ = c.reach(kept_edges, self.roots)
        self.assertEqual(full - kept, {("u", ".text.b"), ("u", ".text.d")})


if __name__ == "__main__":
    unittest.main()
