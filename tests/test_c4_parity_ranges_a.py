#!/usr/bin/env python3
"""C4 ranges-a member-exact parity for unnamed ranges inside CE structs.

Ledger members covered (names as in docs/reports/m4-c4-range-dispositions-2026-10-26.json):
  detail_object_cell.<unclassified@0x0>, detail_object_count.<unclassified@0x0>,
  structure_weather_polyhedron.<unclassified@0x0>, structure_material.<unclassified@0x10>,
  structure_lens_flare_marker.<unclassified@0x0>, structure_fog_plane.<unclassified@0x4>,
  structure_lightmap.<unclassified@0x0>, render_lighting.<unclassified@0x0>,
  render_lighting.<unclassified@0xe>, render_lighting.<unclassified@0x42>.
Blocked members (no host-drivable consumer; precise reasons in BLOCKED below):
  structure_runtime_decal.<unclassified@0x0>, detail_object_z_reference_vector.<unclassified@0x0>,
  detail_object.<unclassified@0x0>, structure_material.<unclassified@0x9c>,
  (round 2 moved structure_runtime_decal, structure_breakable_surface, structure_weather_palette_entry
  @0x90 and structure_material @0xae to driven tests.)

Consumers are CE function bodies extracted verbatim (fog.extract_definition) and compiled
with the C drivers tests/c4_parity_ranges_a_*_main.c; each result is compared with an
oracle written here from the CE semantics. A failing oracle is a finding, not relaxed.
Run: python3 -I -m pytest -q tests/test_c4_parity_ranges_a.py
"""
import bisect
import math
import math
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_c4_parity_fog as fog  # noqa: E402  (reuse verbatim extraction + lighting oracle)

ROOT = HERE.parent
CE_SRC = ROOT / "submodules/halo-ce-universal/source"
DETAIL_SRC = (CE_SRC / "structures/structure_detail_objects.c").read_text()
WEATHER_SRC = (CE_SRC / "effects/weather_particle_systems.c").read_text()
MATERIAL_SRC = (CE_SRC / "structures/structure_bsp_definitions.c").read_text()
LENS_SRC = fog.LENS_SRC
LIGHTING_SRC = fog.OBJECT_LIGHTS_SRC

DETAIL_C = HERE / "c4_parity_ranges_a_detail_main.c"
WEATHER_C = HERE / "c4_parity_ranges_a_weather_main.c"
MATERIAL_C = HERE / "c4_parity_ranges_a_material_main.c"
LENS_C = HERE / "c4_parity_ranges_a_lens_main.c"
LIGHTING_C = fog.LIGHTING_C

BLOCKED = {
    "detail_object_z_reference_vector.<unclassified@0x0>":
        "the only consumer of the z_reference_vector components is the Xbox rasterizer "
        "(rasterizer/xbox/rasterizer_xbox_detail_objects.c:867-879); the CPU-side selection at "
        "structure_detail_objects.c:536-541 is inline in the whole structure_render_detail_objects "
        "body (420-593), which cannot be extracted without its render-state stubs. PS2 has no reader.",
    "detail_object.<unclassified@0x0>":
        "the pixel consumer detail_object_build_vertices (rasterizer/xbox/rasterizer_xbox_detail_objects.c:"
        "280-320) is Xbox-only vertex packing; no PS2 detail-object drawing exists (unsupported). The "
        "CPU-side cell selector does not read position, data or color.",
    "structure_material.<unclassified@0x9c>":
        "plane is passed to the render pass only when the coplanar flag is set (structure_render.c:615-617) "
        "into the rasterizer draw path; the result is GPU/draw state with no host-observable output.",
}


def _definition(source, name):
    """Verbatim CE definition including its return type: fog.extract_definition starts at the name,
    so the line head (return type) is re-attached from the source."""
    text = fog.extract_definition(source, name)
    start = source.index(text)
    line_start = source.rfind("\n", 0, start) + 1
    return source[line_start:start + len(text)]


def _run(template, ce, stdin_text, name):
    return fog.build_and_run(template.read_text(), ce, "", stdin_text, name)


# ------------------------------------------------------------ detail object cell + count

DETAIL_CE = None


def _detail_ce():
    return "\n".join([
        _definition(DETAIL_SRC, "key_compare_cells_lower_bound("),
        _definition(DETAIL_SRC, "key_compare_cells_upper_bound("),
        _definition(DETAIL_SRC, "get_lower_bound_cell("),
        _definition(DETAIL_SRC, "get_upper_bound_cell("),
        _definition(DETAIL_SRC, "structure_detail_objects_port_count("),
    ])


def detail_oracle_bounds(cells, key):
    """Independent model: cells sorted by (cell_x, cell_y, cell_z); lower bound is the first cell
    not less than key, upper bound the first cell greater than key (CE binary searches)."""
    keys = [(c[0], c[1], c[2]) for c in cells]
    return bisect.bisect_left(keys, key), bisect.bisect_right(keys, key)


def detail_oracle_count(counts, nobjects, count_index, first):
    if 0 <= count_index < len(counts):
        count = counts[count_index]
        if 0 <= first <= nobjects and count <= nobjects - first:
            return count
    return 0


def detail_stdin(counts, nobjects, cells, queries, port):
    lines = [str(len(counts))] + [str(c) for c in counts] + [str(nobjects)]
    lines.append(str(len(cells)))
    lines += [f"{x} {y} {z}" for x, y, z in cells]
    lines += [f"q {x} {y} {z}" for x, y, z in queries]
    lines += [f"p {ci} {first}" for ci, first in port]
    lines.append("end")
    return "\n".join(lines) + "\n"


DETAIL_CELLS = [(-2, 0, 0), (-2, 0, 3), (0, -1, 5), (0, 0, 0), (0, 0, 1), (1, 4, -2), (3, 0, 0)]
DETAIL_QUERIES = [(-3, 0, 0), (-2, 0, 0), (-2, 0, 3), (-2, 0, 4), (0, 0, 0), (0, 0, 2), (0, 9, 9), (4, 0, 0), (1, 4, -2)]
DETAIL_PORT = [(0, 0), (1, 0), (2, 1), (1, 5), (3, 0), (-1, 0), (2, 6), (2, 2)]


class DetailObjectCellUnclassified0x0Test(unittest.TestCase):
    """detail_object_cell.<unclassified@0x0> (cell_x/cell_y/cell_z sort keys, cell index bounds) and
    detail_object_count.<unclassified@0x0> (structure_detail_object_data counts word), CE
    structure_detail_objects.c."""

    def _check(self, cells, counts=(4, 0, 2, 7), nobjects=8, queries=DETAIL_QUERIES, port=DETAIL_PORT, label=""):
        out = _run(DETAIL_C, _detail_ce(), detail_stdin(list(counts), nobjects, cells, queries, port),
                   "detail" + re.sub(r"\W", "", label))
        expected = []
        for q in queries:
            lb, ub = detail_oracle_bounds(cells, q)
            expected.append(f"q lb={lb} ub={ub}")
        for ci, first in port:
            expected.append(f"p {detail_oracle_count(list(counts), nobjects, ci, first)}")
        self.assertEqual(out, expected, label)
        return out

    def test_detail_object_cell_unclassified_0x0_sort_keys_member_exact(self):
        base = self._check(DETAIL_CELLS, label="baseline")
        # cell_z of the (-2,0,*) pair moved within its ordering: the bounds of the key change.
        moved = list(DETAIL_CELLS)
        moved[1] = (-2, 0, 4)
        out = self._check(moved, label="cell-z-moved")
        self.assertNotEqual(base, out)
        # cell_y change that keeps the cells sorted changes the lower bound for keys in its range.
        moved = list(DETAIL_CELLS)
        moved[2] = (0, 1, 5)
        self._check(moved, label="cell-y-moved")
        # cell_x shift of the last cell.
        moved = list(DETAIL_CELLS)
        moved[6] = (5, 0, 0)
        self._check(moved, label="cell-x-moved")
        # single cell and empty cell list (no cells: both bounds 0).
        self._check([(0, 0, 0)], label="one-cell")
        self._check([], label="no-cells")

    def test_detail_object_count_unclassified_0x0_member_exact(self):
        # counts[] word value that fits, equals the remainder, exceeds it, and out-of-range indices.
        out_a = self._check(DETAIL_CELLS, counts=(4, 0, 2, 7), port=DETAIL_PORT, label="counts-a")
        out_b = self._check(DETAIL_CELLS, counts=(4, 0, 2, 9), port=DETAIL_PORT, label="counts-b")
        self.assertNotEqual(out_a, out_b)
        self._check(DETAIL_CELLS, counts=(65535, 0), nobjects=3, port=[(0, 0), (0, 1), (0, 3)], label="counts-huge")
        self._check(DETAIL_CELLS, counts=(), nobjects=0, port=[(0, 0)], label="counts-empty")


# ------------------------------------------------------------ weather polyhedron

def weather_oracle(camera, max_distance, polys):
    threshold_base = max_distance
    out = []
    for index, (cx, cy, cz, r) in enumerate(polys):
        d2 = (camera[0] - cx) ** 2 + (camera[1] - cy) ** 2 + (camera[2] - cz) ** 2
        if d2 < (threshold_base + r) ** 2:
            if len(out) < 8:
                out.append(index)
    return out


def weather_stdin(camera, max_distance, polys):
    lines = [f"{camera[0]} {camera[1]} {camera[2]} {max_distance} {len(polys)}"]
    lines += [f"{x} {y} {z} {r}" for x, y, z, r in polys]
    return "\n".join(lines) + "\n"


class WeatherPolyhedronUnclassified0x0Test(unittest.TestCase):
    """structure_weather_polyhedron.<unclassified@0x0>: bounding_sphere_center (0x0) and
    bounding_sphere_radius (0xc) feed the visibility cull in weather_polyhedra_find
    (effects/weather_particle_systems.c:449-478). The trailing unused long (0x10) has no access."""

    CASES = {
        "all-visible": ((0, 0, 0), 10, [(1, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 1)]),
        "radius-decides": ((0, 0, 0), 5, [(12, 0, 0, 2), (12, 0, 0, 8), (-30, 0, 0, 20)]),
        "cap-at-eight": ((0, 0, 0), 2, [(1, i, 0, 1) for i in range(10)]),
        "none-visible": ((0, 0, 0), 1, [(50, 0, 0, 1), (0, 0, -60, 2)]),
        "center-shift": ((0, 0, 0), 5, [(10, 0, 0, 0), (0, 10, 0, 0), (0, 0, 10, 0)]),
    }

    def _check(self, label, camera, max_distance, polys):
        ce = _definition(WEATHER_SRC, "weather_polyhedra_find(")
        out = _run(WEATHER_C, ce, weather_stdin(camera, max_distance, polys), "weather" + re.sub(r"\W", "", label))
        idx = weather_oracle(camera, max_distance, polys)
        self.assertEqual(out, [f"w {len(idx)} " + " ".join(str(i) for i in idx) if idx else "w 0"], label)
        return out

    def test_structure_weather_polyhedron_unclassified_0x0_member_exact(self):
        results = {}
        for label, (camera, dist, polys) in self.CASES.items():
            results[label] = self._check(label, camera, dist, polys)
        # moving one polyhedron's center in or out of the cull changes the output, as CE does.
        camera, dist, polys = self.CASES["center-shift"]
        self.assertNotEqual(self._check("shift-a", camera, dist, polys),
                            self._check("shift-b", camera, dist, [(0, 0, 0, 0)] + polys[1:]))
        camera, dist, polys = self.CASES["radius-decides"]
        self.assertNotEqual(self._check("radius-a", camera, dist, polys),
                            self._check("radius-b", camera, dist, [(12, 0, 0, 8)] + polys[1:]))


# ------------------------------------------------------------ material span search

def material_oracle(lightmaps, surface):
    for li, materials in enumerate(lightmaps):
        for mi, (first, count) in enumerate(materials):
            if first <= surface < first + count:
                return ("s 1 %d %d" % (li, mi))
    return "s 0"


def material_stdin(lightmaps, queries):
    lines = [str(len(lightmaps))]
    for materials in lightmaps:
        lines.append(str(len(materials)))
        lines += [f"{f} {c}" for f, c in materials]
    lines += [f"s {q}" for q in queries]
    lines.append("e")
    return "\n".join(lines) + "\n"


# Contiguous spans per lightmap (the domain CE's binary search is written for). A surface in a gap
# between a lightmap's material spans reaches the Xbox match_assert at structure_bsp_definitions.c:103
# instead of returning FALSE: recorded as a finding in docs/reports/m4-c4-parity-ranges-a-2026-10-26.json.
MATERIAL_CASES = {
    "two-lightmaps": ([[(0, 4), (4, 2), (6, 3)], [(9, 5), (14, 1)]], [0, 1, 3, 4, 5, 6, 8, 9, 13, 14, 15]),
    "single-material": ([[(7, 1)]], [6, 7, 8]),
    "single-lightmap-one-material": ([[(0, 3)]], [0, 2, 3]),
}


class MaterialFirstSurfaceSurfaceCountUnclassified0x10Test(unittest.TestCase):
    """structure_material.<unclassified@0x10>: the span members first_surface_index (0x14) and
    surface_count (0x18) drive structure_bsp_find_material_for_surface
    (structures/structure_bsp_definitions.c:76-200). permutation_index (0x10), flags (0x12) and
    centroid (0x1c) are read by the render pass, not this search, and are not covered here."""

    def _check(self, label, lightmaps, queries):
        ce = fog.extract_definition(MATERIAL_SRC, "boolean structure_bsp_find_material_for_surface(")
        out = _run(MATERIAL_C, ce, material_stdin(lightmaps, queries), "material" + re.sub(r"\W", "", label))
        expected = [material_oracle(lightmaps, q) for q in queries]
        self.assertEqual(out, expected, label)
        return out

    def test_structure_material_unclassified_0x10_span_members_member_exact(self):
        for label, (lightmaps, queries) in MATERIAL_CASES.items():
            self._check(label, lightmaps, queries)
        # first_surface_index change moves a surface out of its material: output changes.
        queries = MATERIAL_CASES["two-lightmaps"][1]
        base = self._check("span-base", *MATERIAL_CASES["two-lightmaps"])
        # first_surface_index of the second material moves down by one (spans stay contiguous)
        moved = [[(0, 4), (4, 2), (6, 3)], [(9, 5), (14, 1)]]
        moved[0] = [(0, 3), (3, 3), (6, 3)]
        self.assertNotEqual(base, self._check("span-first-moved", moved, queries))
        # surface_count grows, the next material's first surface moves with it
        grown = [[(0, 4), (4, 3), (7, 2)], [(9, 5), (14, 1)]]
        self.assertNotEqual(base, self._check("span-count-grown", grown, queries))


# ------------------------------------------------------------ lens flare marker

def lens_oracle(markers, clusters, flare_count):
    lines = []
    limit = min(len(markers), 32767 + 1 - 128)
    for c, (first, count) in enumerate(clusters):
        for k in range(count):
            ix = first + k
            if ix >= limit:
                break
            px, py, pz, ii, jj, kk, lfi = markers[ix]
            if lfi >= flare_count:
                continue
            d = [ii / 127.0, jj / 127.0, kk / 127.0]
            l = math.sqrt(sum(v * v for v in d))
            d = [v / l for v in d]
            lines.append(("v", c, (px, py, pz), d))
        # the verbatim consumer does not print per cluster
    return lines


def lens_stdin(flare_tags, markers, clusters):
    lines = [str(len(flare_tags))] + [str(t) for t in flare_tags]
    lines.append(str(len(markers)))
    lines += [f"{lfi} {i} {j} {k} {x} {y} {z}" for x, y, z, i, j, k, lfi in markers]
    lines.append(str(len(clusters)))
    lines += [f"{f} {c}" for f, c in clusters]
    return "\n".join(lines) + "\n"


LENS_MARKERS = [
    (1.5, 2.0, -3.0, 127, 0, 0, 0),
    (0.0, 0.5, 4.25, -60, 80, 30, 1),
    (-7.0, 1.0, 0.0, 10, -20, -127, 2),
    (2.0, 2.0, 2.0, 50, 50, 50, 0),
    (9.0, 9.0, 9.0, 1, 2, 3, 9),          # flare index out of range: skipped
    (4.0, -1.0, 6.0, -100, 0, 100, 1),
]
LENS_FLARES = [0, 1, 2]
LENS_CLUSTERS = [(0, 3), (3, 3)]


class LensFlareMarkerUnclassified0x0Test(unittest.TestCase):
    """structure_lens_flare_marker.<unclassified@0x0>: position (0x0..0xb) and the i/j/k direction
    bytes (0xc..0xe) are converted and submitted per marker in
    rasterizer_lens_flare_submit_for_cluster (rasterizer/rasterizer_lights.c:771-835). The stand-in
    records the direction and up vectors; the test checks them against normalize(ijk/127), with up a
    unit vector perpendicular to direction."""

    def _check(self, label, markers, clusters, flares):
        ce = fog.extract_definition(LENS_SRC, "void rasterizer_lens_flare_submit_for_cluster(")
        out = _run(LENS_C, ce, lens_stdin(flares, markers, clusters), "lens" + re.sub(r"\W", "", label))
        expected = lens_oracle(markers, clusters, len(flares))
        self.assertEqual(len(out), len(expected), label)
        for line, (_, c, pos, d) in zip(out, expected):
            vals = [float(x) for x in line.split()[2:]]
            self.assertEqual(int(line.split()[1]), c, label)
            self.assertTrue(fog.close(tuple(vals[0:3]), tuple(pos), 1e-5), (label, line))
            self.assertTrue(fog.close(tuple(vals[3:6]), tuple(d), 1e-5), (label, line))
            up = vals[6:9]
            self.assertAlmostEqual(math.sqrt(sum(v * v for v in up)), 1.0, places=4, msg=label)
            self.assertAlmostEqual(sum(a * b for a, b in zip(up, d)), 0.0, places=4, msg=label)
        return out

    def test_structure_lens_flare_marker_unclassified_0x0_member_exact(self):
        base = self._check("baseline", LENS_MARKERS, LENS_CLUSTERS, LENS_FLARES)
        changed = list(LENS_MARKERS)
        changed[1] = (0.0, 0.5, 4.25, 60, -80, -30, 1)
        out = self._check("direction-bytes-changed", changed, LENS_CLUSTERS, LENS_FLARES)
        self.assertNotEqual(base, out)
        moved = list(LENS_MARKERS)
        moved[0] = (1.5, 2.0, -2.5, 127, 0, 0, 0)
        self.assertNotEqual(base, self._check("position-changed", moved, LENS_CLUSTERS, LENS_FLARES))


# ------------------------------------------------------------ fog plane (shared scenario harness)

class FogPlaneUnclassified0x4Test(unittest.TestCase):
    """structure_fog_plane.<unclassified@0x4>: the real_plane3d at 0x4 (n and d) selects the fog
    region in scenario_get_fog_region_index (scenario/scenario.c:677) and is reused from the
    scenario fog harness (tests/test_c4_parity_fog.py)."""

    def test_structure_fog_plane_unclassified_0x4_plane_member_exact(self):
        base = fog.deep_copy_bsp(fog.BASE_SCENARIO)
        fog.run_scenario_case(self, fog.scenario_case(base, fog.SCENARIO_QUERIES, 0), "plane-baseline")
        for distance in (-1, 0, 2, 6):
            changed = fog.deep_copy_bsp(fog.BASE_SCENARIO)
            changed["planes"][0] = dict(changed["planes"][0], d=distance)
            fog.run_scenario_case(self, fog.scenario_case(changed, fog.SCENARIO_QUERIES, 0), f"plane0-d-{distance}")
        for normal in ((0, -1, 0), (1, 1, 0)):
            changed = fog.deep_copy_bsp(fog.BASE_SCENARIO)
            changed["planes"][0] = dict(changed["planes"][0], n=normal)
            fog.run_scenario_case(self, fog.scenario_case(changed, fog.SCENARIO_QUERIES, 0), f"plane0-n-{normal}")
        a = fog.deep_copy_bsp(fog.BASE_SCENARIO)
        a["planes"][0] = dict(a["planes"][0], d=-1)
        self.assertNotEqual(fog.scenario_expected(fog.BASE_SCENARIO, fog.SCENARIO_QUERIES),
                            fog.scenario_expected(a, fog.SCENARIO_QUERIES))


# ------------------------------------------------------------ render lighting + lightmap

LIGHTING_ENTRY = "\n".join([
    fog.extract_definition(LIGHTING_SRC, "static void brighten_real_rgb_color("),
    fog.extract_definition(LIGHTING_SRC, "static void build_distant_lights("),
    fog.extract_definition(LIGHTING_SRC, "boolean lights_distant_lighting_at_point("),
])


def _run_lighting(test, names_or_cases, label):
    cases = [fog.LIGHTING_CASES[n] if isinstance(n, str) else n for n in names_or_cases]
    lines = _run(LIGHTING_C, LIGHTING_ENTRY, fog.lighting_stdin(cases), "lighting" + re.sub(r"\W", "", label))
    results = []
    for case, line in zip(cases, lines):
        expected_result, expected = fog.oracle_lighting(case)
        got = fog.parse_lighting(line)
        test.assertEqual(got["result"], expected_result, label)
        test.assertEqual(got["dlc"], expected["dlc"], label)
        test.assertEqual(got["plc"], expected["plc"], label)
        test.assertEqual(got["pli"], expected["pli"], label)
        test.assertTrue(fog.close(got["ambient"], expected["ambient"]), label)
        test.assertTrue(fog.close(got["tint"], expected["tint"]), label)
        test.assertTrue(fog.close(got["shadow_vec"], expected["shadow_vec"]), label)
        test.assertTrue(fog.close(got["shadow_col"], expected["shadow_col"]), label)
        results.append(got)
    return lines


class RenderLightingUnclassified0x0Test(unittest.TestCase):
    """render_lighting.<unclassified@0x0>: ambient_color (red tested against zero, selects the
    default object ambient table) in lights_distant_lighting_at_point (objects/object_lights.c:2388).
    Scope: the same verbatim consumer and oracle as tests/test_c4_parity_fog.py."""

    def test_render_lighting_unclassified_0x0_ambient_color_member_exact(self):
        zero = fog.lighting_case(default=fog.default_with(ambient=(0.0, 0.2, 0.3)))
        nonzero = fog.lighting_case(default=fog.default_with(ambient=(0.1, 0.2, 0.3)))
        lines = _run_lighting(self, [zero, nonzero, fog.LIGHTING_CASES["hit-env-lightmap-group-valid"]], "ambient")
        self.assertNotEqual(lines[0], lines[1])


class RenderLightingUnclassified0xeAndUnclassified0x42Test(unittest.TestCase):
    """render_lighting.<unclassified@0xe> (pad, 2 bytes) and render_lighting.<unclassified@0x42>
    (pad1 and point_light_indices). The lighting consumer never takes these as inputs: the pad
    bytes have no reader, and point_light_indices are read only by the dynamic object lighting
    path (objects/object_lights.c:2307-2316, object lighting type), not the BSP render lighting,
    whose point_light_count is forced to 0 by the schema. Result unchanged, bytes retained by the
    struct copy (structures/structure_render.c:622)."""

    def test_render_lighting_unclassified_0xe_and_unclassified_0x42_no_consumer_member_exact(self):
        base = _run_lighting(self, ["hit-env-lightmap-group-valid"], "pad-base")
        again = _run_lighting(self, ["hit-env-lightmap-group-valid"], "pad-again")
        self.assertEqual(base, again)
        pad_readers = []
        for path in (CE_SRC / "objects/object_lights.c", CE_SRC / "structures/structure_render.c"):
            for m in re.finditer(r"(\.|->)\s*(pad|pad1)\b", path.read_text(errors="replace")):
                pad_readers.append(path.name)
        self.assertEqual(pad_readers, [], "render_lighting pad readers")
        # point_light_indices readers: the object lighting paths only (object_lights.c writer,
        # render_objects.c copy, Xbox model rasterizer read guarded by point_light_count). The BSP
        # schema pins point_light_count to 0 (port/linux/game/tag_schema_collision.c:597).
        readers = set()
        for path in CE_SRC.rglob("*.c"):
            if re.search(r"point_light_indices", path.read_text(errors="replace")):
                readers.add(path.name)
        self.assertEqual(sorted(readers), ["object_lights.c", "rasterizer_xbox.c", "render_objects.c"])
        schema = (CE_SRC.parent / "port/linux/game/tag_schema_collision.c").read_text()
        self.assertIn("TAG_SCHEMA_ENUM(struct render_lighting, point_light_count, 1, 0)", schema)
        # byte retention: the BSP lighting is passed by address from the material (no copy, no write)
        render = (CE_SRC / "structures/structure_render.c").read_text()
        self.assertIn("&material->lighting,", render)
        self.assertEqual(re.findall(r"lighting\.(?:pad|pad1)\s*=", render), [])


class GapSurfaceFindingTest(unittest.TestCase):
    """Finding (not a parity pass): CE's surface-to-material search asserts (match_assert at
    structure_bsp_definitions.c:103) for a surface in a gap between one lightmap's material spans,
    rather than returning FALSE. Retail span contiguity is not verified in this lane."""

    def test_structure_material_unclassified_0x10_gap_surface_reaches_match_assert(self):
        ce = fog.extract_definition(MATERIAL_SRC, "boolean structure_bsp_find_material_for_surface(")
        with self.assertRaises(AssertionError) as caught:
            _run(MATERIAL_C, ce, material_stdin([[(0, 2), (5, 2)]], [3]), "materialgap")
        self.assertIn("assert 103", str(caught.exception))


class LightmapBitmapIndexUnclassified0x0Test(unittest.TestCase):
    """structure_lightmap.<unclassified@0x0>: bitmap_index (0x0) selects the lightmap bitmap used by
    lights_distant_lighting_at_point; the validator maps out-of-range to NONE (validator evidence
    in the range ledger). NONE gives the default copy, a valid index gives the hit path."""

    def test_structure_lightmap_unclassified_0x0_bitmap_index_member_exact(self):
        none = fog.lighting_case(lightmap_bitmap=fog.NONE_I)
        zero = fog.lighting_case(lightmap_bitmap=0)
        three = fog.lighting_case(lightmap_bitmap=3)
        lines = _run_lighting(self, [none, zero, three], "lightmap-bitmap")
        self.assertNotEqual(lines[0], lines[1])
        self.assertFalse(fog.parse_lighting(lines[0])["result"])
        self.assertTrue(fog.parse_lighting(lines[1])["result"])
        self.assertTrue(fog.parse_lighting(lines[2])["result"])


# ------------------------------------------------------------ ledger-level checks

class BlockedRowsAreExplainedTest(unittest.TestCase):
    """Blocked members must have a precise reason and cite the CE source they depend on."""

    def test_blocked_rows_have_reasons(self):
        for member, reason in BLOCKED.items():
            with self.subTest(member=member):
                self.assertIn("unclassified@0x", member)
                self.assertTrue(len(reason) > 80)
                self.assertRegex(reason, r"\.c:\d+")


def _blocked_test(member):
    def test(self):
        self.assertIn(member, BLOCKED)
        self.assertTrue(BLOCKED[member])
    return test


_UNDERSCORE = {
    "detail_object_z_reference_vector.<unclassified@0x0>": "detail_object_z_reference_vector_unclassified_0x0",
    "detail_object.<unclassified@0x0>": "detail_object_unclassified_0x0",
    "structure_material.<unclassified@0x9c>": "structure_material_unclassified_0x9c",
}
for _member, _name in _UNDERSCORE.items():
    setattr(BlockedRowsAreExplainedTest, f"test_{_name}_blocked_reason", _blocked_test(_member))


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------------------------ runtime decal (round 2)

DECAL_SRC = (CE_SRC / "structures/structure_runtime_decals.c").read_text()
DECAL_C = HERE / "c4_parity_ranges_a_decal_main.c"
NONE_ID = -1


def decal_stdin(decals, palette, clusters, old, new, reconnect):
    lines = [str(len(decals))]
    for px, py, pz, pi, unused, yaw, pitch in decals:
        lines.append(f"{px} {py} {pz} {pi} {unused} {yaw} {pitch}")
    lines.append(str(len(palette)))
    lines += [str(p) for p in palette]
    lines.append(str(len(clusters)))
    lines += [f"{f} {c}" for f, c in clusters]
    lines.append(" ".join(str(int(b)) for b in old))
    lines.append(" ".join(str(int(b)) for b in new))
    lines.append(str(int(reconnect)))
    return "\n".join(lines) + "\n"


def decal_oracle(decals, palette, clusters, old, new, reconnect):
    """Model of structure_decals_update (structure_runtime_decals.c:~178-240) from the CE text: a
    cluster with decals is deleted when it leaves the PVS (unless reconnecting) and created when it
    enters (or reconnects); each decal index is bounds- and palette-checked, malformed ones are
    reported with the decal index and skipped, and the angles are yaw*(pi/127), pitch*(pi/254)."""
    out = []
    if not decals:
        return out
    for c, (first, count) in enumerate(clusters):
        has = first != NONE_ID and count != 0
        delete = has and not reconnect and old[c] and not new[c]
        create = has and (not old[c] or reconnect) and new[c]
        if delete:
            out.append(f"del {c}")
        elif create:
            k = 0
            while k < count:
                idx = first + k
                if not (0 <= idx < len(decals)):
                    out.append(f"bad {idx}")
                    break
                px, py, pz, pi, _unused, yaw, pitch = decals[idx]
                if pi >= len(palette):
                    out.append(f"bad {idx}")
                    k += 1
                    continue
                definition = palette[pi]
                if definition == NONE_ID:
                    out.append(f"bad {idx}")
                    k += 1
                    continue
                out.append(("new", definition, (px, py, pz), yaw * (math.pi / 127.0), pitch * (math.pi / 254.0)))
                k += 1
    return out


def decal_parse(lines):
    parsed = []
    for line in lines:
        tok = line.split()
        if tok[0] == "new":
            parsed.append(("new", int(tok[1]), tuple(float(x) for x in tok[2:5]),
                           float(tok[5]), float(tok[6])))
        else:
            parsed.append(" ".join(tok))
    return parsed


def decal_expected_parsed(expected):
    return [e if isinstance(e, str) else e for e in expected]


class RuntimeDecalUnclassified0x0Test(unittest.TestCase):
    """structure_runtime_decal.<unclassified@0x0>: position (0x0), palette_index (0xc), yaw (0xe) and
    pitch (0xf) of structure_runtime_decal are consumed by structure_decals_update
    (structures/structure_runtime_decals.c) verbatim; unused (0xd) has no access. The decal manager
    is a data-only stand-in that records decal_new and decals_delete_permanent_from_cluster."""

    DECALS = [(0.5, 1.0, -2.0, 0, 0, 10, -20), (3.0, 0.0, 1.0, 1, 0, -5, 7),
              (2.0, 2.0, 2.0, 9, 0, 127, -127), (4.0, 4.0, 4.0, 0, 0, 0, 0)]
    PALETTE = [4, NONE_ID]
    CLUSTERS = [(0, 3), (3, 1), (NONE_ID, 0)]
    OLD = [False, True, False]
    NEW = [True, False, False]

    def _run(self, decals, palette=None, clusters=None, old=None, new=None, reconnect=False, label="run"):
        palette = self.PALETTE if palette is None else palette
        clusters = self.CLUSTERS if clusters is None else clusters
        old = self.OLD if old is None else old
        new = self.NEW if new is None else new
        ce = _definition(DECAL_SRC, "void structure_decals_update(")
        lines = _run(DECAL_C, ce, decal_stdin(decals, palette, clusters, old, new, reconnect),
                     "decal" + re.sub(r"\W", "", label))
        expected = decal_oracle(decals, palette, clusters, old, new, reconnect)
        self.assertEqual(len(lines), len(expected), label)
        for got_line, exp in zip(lines, expected):
            got = decal_parse([got_line])[0]
            if isinstance(exp, str):
                self.assertEqual(got, exp, label)
            else:
                _, d, p, yaw, pitch = exp
                self.assertEqual(got[0:2], ("new", d), label)
                self.assertTrue(fog.close(got[2], p, 1e-5), label)
                self.assertTrue(fog.close((got[3], got[4]), (yaw, pitch), 1e-5), label)
        return lines

    def test_structure_runtime_decal_unclassified_0x0_member_exact(self):
        base = self._run(self.DECALS, label="baseline")
        self.assertTrue(any(l.startswith("new") for l in base))
        self.assertTrue(any(l.startswith("bad") for l in base))
        self.assertTrue(any(l.startswith("del") for l in base))
        # palette_index: pointing a decal at the other palette entry changes its definition
        moved = list(self.DECALS)
        moved[0] = (0.5, 1.0, -2.0, 1, 0, 10, -20)
        self.assertNotEqual(base, self._run(moved, label="palette-index"))
        # yaw and pitch change the angles passed to decal_new
        moved = list(self.DECALS)
        moved[0] = (0.5, 1.0, -2.0, 0, 0, 11, -20)
        self.assertNotEqual(base, self._run(moved, label="yaw"))
        moved = list(self.DECALS)
        moved[0] = (0.5, 1.0, -2.0, 0, 0, 10, -19)
        self.assertNotEqual(base, self._run(moved, label="pitch"))
        # position change reaches decal_new
        moved = list(self.DECALS)
        moved[0] = (0.75, 1.0, -2.0, 0, 0, 10, -20)
        self.assertNotEqual(base, self._run(moved, label="position"))
        # unused (0xd) poisoned: no change (no CE access)
        poisoned = [(x, y, z, pi, 255, yaw, pitch) for x, y, z, pi, _u, yaw, pitch in self.DECALS]
        self.assertEqual(base, self._run(poisoned, label="unused-poisoned"))
        # reconnect re-creates clusters that were already in the PVS
        self._run(self.DECALS, old=[True, True, True], new=[True, True, True], reconnect=True, label="reconnect")


# ------------------------------------------------------------ breakable surface (round 2)

BREAKABLE_SRC = (CE_SRC / "physics/breakable_surfaces.c").read_text()
BREAKABLE_C = HERE / "c4_parity_ranges_a_breakable_main.c"


def breakable_stdin(surfaces, broken, enabled, damage, epicenter):
    lines = [str(len(surfaces))]
    lines += [f"{cx} {cy} {cz} {r} {ci}" for (cx, cy, cz), r, ci in surfaces]
    lines.append(" ".join(str(int(b)) for b in broken))
    lines.append(str(int(enabled)))
    lines.append(" ".join(str(v) for v in damage))
    lines.append(" ".join(str(v) for v in epicenter))
    return "\n".join(lines) + "\n"


def breakable_oracle(surfaces, broken, enabled, damage, epicenter):
    """Model of breakable_surface_damage_area_of_effect (physics/breakable_surfaces.c:~268-300): a
    surface is hit when it is not already broken, the damage is enabled with a nonzero bound, and
    its centroid lies within bounding_radius + cutoff_radius of the epicenter (inclusive)."""
    lower, upper, cutoff = damage
    out = []
    if not enabled or (lower == 0.0 and upper == 0.0):
        return out
    for index, ((cx, cy, cz), radius, collision) in enumerate(surfaces):
        if broken[index]:
            continue
        reach = radius + cutoff
        d2 = (cx - epicenter[0]) ** 2 + (cy - epicenter[1]) ** 2 + (cz - epicenter[2]) ** 2
        if d2 <= reach * reach:
            out.append(f"effect {index} {collision}")
    return out


class BreakableSurfaceUnclassified0x0Test(unittest.TestCase):
    """structure_breakable_surface.<unclassified@0x0>: centroid (0x0), bounding_radius (0xc) and
    collision_surface_index (0x10) of structure_breakable_surface drive
    breakable_surface_damage_area_of_effect (physics/breakable_surfaces.c) verbatim, with the
    extant check breakable_surface_extant and breakable_surface_indices_valid also verbatim. The
    queue (vitality, broken flags, effect call) is a data-only stand-in. unused[7] (0x14) has no
    access in CE."""

    SURFACES = [((0.0, 0.0, 0.0), 1.0, 7), ((3.0, 0.0, 0.0), 1.0, 8), ((0.0, 4.0, 0.0), 0.5, 9),
                ((-2.0, -2.0, 0.0), 2.0, 10), ((9.0, 9.0, 9.0), 1.0, 11)]
    BROKEN = [False, False, False, True, False]
    DAMAGE = (1.0, 2.0, 1.5)
    EPICENTER = (0.0, 0.0, 0.0)

    def _run(self, surfaces, broken=None, enabled=True, damage=None, epicenter=None, label="run"):
        broken = self.BROKEN if broken is None else broken
        damage = self.DAMAGE if damage is None else damage
        epicenter = self.EPICENTER if epicenter is None else epicenter
        ce = "\n".join([
            _definition(BREAKABLE_SRC, "static boolean breakable_surface_indices_valid("),
            _definition(BREAKABLE_SRC, "boolean breakable_surface_extant("),
            _definition(BREAKABLE_SRC, "void breakable_surface_damage_area_of_effect("),
        ])
        lines = _run(BREAKABLE_C, ce, breakable_stdin(surfaces, broken, enabled, damage, epicenter),
                     "breakable" + re.sub(r"\W", "", label))
        expected = breakable_oracle(surfaces, broken, enabled, damage, epicenter)
        self.assertEqual(lines, expected, label)
        return lines

    def test_structure_breakable_surface_unclassified_0x0_member_exact(self):
        damage = (1.0, 2.0, 3.5)
        base = self._run(self.SURFACES, damage=damage, label="baseline")
        self.assertEqual(base, ["effect 0 7", "effect 1 8", "effect 2 9"])
        # centroid: move surface 1 out of reach of the epicenter
        moved = list(self.SURFACES)
        moved[1] = ((9.0, 0.0, 0.0), 1.0, 8)
        self.assertNotEqual(base, self._run(moved, damage=damage, label="centroid-out"))
        # bounding_radius: a zero radius leaves surface 2 out of reach (4.0 > 0.5 + 3.5 - 0.5 + 0)
        moved = list(self.SURFACES)
        moved[2] = ((0.0, 4.0, 0.0), 0.0, 9)
        out = self._run(moved, damage=damage, label="radius")
        self.assertNotIn("effect 2 9", out)
        self.assertNotEqual(base, out)
        # collision_surface_index: the effect receives it
        moved = list(self.SURFACES)
        moved[0] = ((0.0, 0.0, 0.0), 1.0, 70)
        out = self._run(moved, damage=damage, label="collision-index")
        self.assertIn("effect 0 70", out)
        self.assertNotEqual(base, out)
        # broken flags: the surface already broken (index 3) is skipped, clearing it adds a hit
        self.assertNotEqual(base, self._run(self.SURFACES, broken=[False] * 5, damage=damage, label="unbroken-3"))

    def test_structure_breakable_surface_unclassified_0x0_gates_member_exact(self):
        # disabled damage and all-zero bounds break nothing
        self.assertEqual(self._run(self.SURFACES, enabled=False, label="disabled"), [])
        self.assertEqual(self._run(self.SURFACES, damage=(0.0, 0.0, 1.5), label="zero-bounds"), [])
        # every surface broken: nothing hit
        self.assertEqual(self._run(self.SURFACES, broken=[True] * 5, damage=(1.0, 2.0, 3.5), label="all-broken"), [])

    def test_structure_breakable_surface_unclassified_0x0_unused_has_no_ce_access(self):
        hits = re.findall(r"(->|\.)\s*unused\b", BREAKABLE_SRC)
        self.assertEqual(hits, [] , "breakable_surfaces.c reads of structure_breakable_surface.unused")


# ------------------------------------------------------------ wind direction / magnitude (round 2)

WIND_SRC = (CE_SRC / "scenario/wind.c").read_text()
REAL_MATH_SRC = (CE_SRC / "math/real_math.c").read_text()
WIND_C = HERE / "c4_parity_ranges_a_wind_main.c"
PINNED_BITS = [1, 0, 1, 1, 0]


def _pin(value, lower, upper):
    return lower if value < lower else (upper if value > upper else value)


def wind_oracle(palette, definitions):
    """Independent model of wind_update (scenario/wind.c) for one update from zero state with the
    pinned random bits (three per entry with a wind: velocity_variance, pitch, yaw, in order)."""
    bits = iter(PINNED_BITS[i % 5] for i in range(10_000))
    out = []
    for index, (wind_index, direction, magnitude) in enumerate(palette[:32]):
        if wind_index == NONE_ID:
            out.append((index, False, 0.0, (0.0, 0.0, 0.0)))
            continue
        d = definitions[wind_index]
        lo, hi, var_yaw, var_pitch, _lw, _lr = d
        vv = _pin(0.0 + (0.01 if next(bits) else -0.01), 0.0, 1.0)
        pitch_var = _pin(0.0 + (0.01 if next(bits) else -0.01), -1.0, 1.0)
        yaw_var = _pin(0.0 + (0.01 if next(bits) else -0.01), -1.0, 1.0)
        velocity = (hi - lo) * vv + lo
        x, y, z = direction
        yaw = math.atan2(y, x)
        pitch = math.atan2(z, math.sqrt(x * x + y * y))
        pitch += var_pitch * pitch_var * 0.5
        yaw += var_yaw * yaw_var * 0.5
        cp = math.cos(pitch)
        scale = magnitude * velocity
        v = (math.cos(yaw) * cp * scale, math.sin(yaw) * cp * scale, math.sin(pitch) * scale)
        out.append((index, True, velocity, v))
    return out


NONE_ID = -1


def wind_stdin(palette, definitions):
    lines = [str(len(palette))]
    for wind_index, (x, y, z), mag in palette:
        lines.append(f"{wind_index} {x} {y} {z} {mag}")
    lines.append(str(len(definitions)))
    for lo, hi, vy, vp, lw, lr in definitions:
        lines.append(f"{lo} {hi} {vy} {vp} {lw} {lr}")
    return "\n".join(lines) + "\n"


class WindPaletteDirectionMagnitudeTest(unittest.TestCase):
    """structure_weather_palette_entry.<unclassified@0x90>: wind_direction (0x90, 12 bytes) and
    wind_magnitude (0x9c) of structure_weather_palette_entry drive wind_update (scenario/wind.c:184)
    verbatim, with the euler/vector helpers from math/real_math.c verbatim. seed_random_range is
    pinned to PINNED_BITS, so the output depends only on the synthetic palette and definition bytes.
    The padA0, wind_global_function and wind_unused members have no CE access."""

    DEFS = [(1.0, 3.0, 0.5, 0.25, 0.0, 0.0)]
    PALETTE = [(0, (1.0, 0.0, 0.0), 2.0), (0, (0.0, 1.0, 1.0), 0.5), (NONE_ID, (0.0, 0.0, 0.0), 9.0)]

    def _run(self, palette, definitions, label):
        ce = "\n".join([
            _definition(REAL_MATH_SRC, "real_euler_angles2d *euler_angles2d_from_vector3d("),
            _definition(REAL_MATH_SRC, "real_vector3d *vector3d_from_euler_angles2d("),
            _definition(WIND_SRC, "void wind_update("),
        ])
        lines = _run(WIND_C, ce, wind_stdin(palette, definitions), "wind" + re.sub(r"\W", "", label))
        expected = wind_oracle(palette, definitions)
        self.assertEqual(len(lines), len(expected), label)
        for line, (index, valid, velocity, v) in zip(lines, expected):
            tok = line.split()
            self.assertEqual(int(tok[1]), index, label)
            self.assertEqual(bool(int(tok[2])), valid, label)
            got = tuple(float(x) for x in tok[3:7])
            self.assertTrue(fog.close(got, (velocity,) + tuple(v), 1e-4), (label, line))
        return lines

    def test_structure_weather_palette_entry_unclassified_0x90_member_exact(self):
        base = self._run(self.PALETTE, self.DEFS, "baseline")
        moved = [(0, (0.0, 1.0, 0.0), 2.0), self.PALETTE[1], self.PALETTE[2]]
        self.assertNotEqual(base, self._run(moved, self.DEFS, "direction"))
        magnitude = [self.PALETTE[0], (0, (0.0, 1.0, 1.0), 4.0), self.PALETTE[2]]
        self.assertNotEqual(base, self._run(magnitude, self.DEFS, "magnitude"))
        # a wind-less entry is untouched by direction and magnitude bytes
        nowind = [self.PALETTE[0], self.PALETTE[1], (NONE_ID, (5.0, 5.0, 5.0), 3.0)]
        nowind_changed = [self.PALETTE[0], self.PALETTE[1], (NONE_ID, (1.0, 1.0, 1.0), 7.0)]
        self.assertEqual(self._run(nowind, self.DEFS, "nowind-a")[2], self._run(nowind_changed, self.DEFS, "nowind-b")[2])

    def test_structure_weather_palette_entry_unclassified_0x90_unused_no_ce_access(self):
        hits = re.findall(r"(\.|->)\s*(wind_unused|padA0|wind_global_function_index)\b", WIND_SRC)
        self.assertEqual(hits, [], "wind.c reads of the palette padding or function hook")


# ------------------------------------------------------------ material 0xae schema gap (round 2)

VALIDATOR_TEST = HERE / "test_c4_parity_validators.py"


class MaterialCopiousUnusedSpaceUnclassified0xaeTest(unittest.TestCase):
    """structure_material.<unclassified@0xae> (schema-gap). copious_unused_space (0xae, word) has no
    reader in CE. The inline vertex_buffer records next to it (vertices at 0xb0, lightmap_vertices at
    0xc4) are consumed by structure_vertex_buffer_check (port/linux/game/tag_schema_collision.c:1272),
    which is driven verbatim by tests/c4_validators_main.c (cases material_vertex_buffer_contained and
    material_vertex_buffer_past_region in test_c4_parity_validators.py). base_address has no reader
    outside rasterizer/xbox and the Xbox D3D path; hardware_format is read by the validator above and by
    port/linux/game/object_mesh.c (D3D8 vertex lock, Xbox API). No schema change was made."""

    def test_structure_material_unclassified_0xae_copious_unused_no_reader(self):
        readers = []
        for path in CE_SRC.rglob("*.[ch]"):
            text = path.read_text(errors="replace")
            if re.search(r"(\.|->)\s*copious_unused_space\b", text):
                readers.append(path.name)
        self.assertEqual(readers, [])

    def test_structure_material_unclassified_0xae_vertex_buffer_validator_cases_member_exact(self):
        import test_c4_parity_validators as validators
        for case in ("material_vertex_buffer_contained", "material_vertex_buffer_past_region"):
            self.assertIn(case, validators.EXPECTED)
        self.assertEqual(validators.EXPECTED["material_vertex_buffer_past_region"][:3], (0, 1, 0))

    def test_structure_material_unclassified_0xae_base_address_no_ps2_reader(self):
        hits = []
        for path in CE_SRC.parent.joinpath("port").rglob("*.c"):
            text = path.read_text(errors="replace")
            if re.search(r"vertices?(\.|->)base_address|vertex_buffer(\.|->)base_address", text):
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])


# ------------------------------------------------------------ retail span contiguity (round 2)

class RetailSpanContiguityTest(unittest.TestCase):
    """Gap-surface finding check: every lightmap's material spans in the retail structure BSPs are
    contiguous (each span starts where the previous ends), so the surface-in-gap condition that
    reaches match_assert in structure_bsp_definitions.c:103 does not occur on retail data. Maps are
    the decompressed retail .map files in build/retail-maps/decompressed, each verified against the
    source_sha256 pin in docs/reports/retail-bsp-preservation-2026-10-21.json before use."""

    def test_retail_lightmap_material_spans_are_contiguous(self):
        import hashlib
        import json
        import struct
        sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
        from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
        report = json.loads((ROOT / "docs/reports/retail-bsp-preservation-2026-10-21.json").read_text())
        maps_dir = ROOT / "build/retail-maps/decompressed"
        pins = {m["map"]: m["source_sha256"] for m in report["maps"]}
        for name in pins:
            if not (maps_dir / f"{name}.map").is_file():
                self.skipTest(f"retail map {name}.map missing from build/retail-maps/decompressed")
        bsps = lightmaps = 0
        gaps = []
        for name in sorted(pins):
            path = maps_dir / f"{name}.map"
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), pins[name], name)
            header = mapinfo.read_header(path)
            index = tagindex.TagIndex.read(path)
            region = raw[header.tag_data_offset:header.tag_data_offset + header.tag_data_size]
            for loc in bsp.locate(index, region, header.decompressed_size):
                bsps += 1
                block = raw[loc.file_offset:loc.file_offset + loc.size]
                root = struct.unpack_from("<I", block, 0)[0] - loc.address
                count, addr = struct.unpack_from("<II", block, root + 0x104)
                for i in range(count):
                    lightmaps += 1
                    mcount, maddr = struct.unpack_from("<II", block, addr - loc.address + i * 32 + 0x14)
                    if mcount == 0:
                        continue
                    base = maddr - loc.address
                    spans = [struct.unpack_from("<ii", block, base + m * bsp.MATERIAL_SIZE + 0x14)
                             for m in range(mcount)]
                    for k in range(len(spans) - 1):
                        if spans[k][0] + spans[k][1] != spans[k + 1][0]:
                            gaps.append((name, loc.path, i, k))
        self.assertGreater(bsps, 0)
        self.assertEqual(gaps, [])
