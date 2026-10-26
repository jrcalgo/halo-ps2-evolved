#!/usr/bin/env python3
"""C4 member-exact consumer parity for fog / weather / lens-flare / lighting members.

Each CE consumer body is extracted verbatim from the pinned CE source, compiled
with a synthetic BSP driven from stdin (tests/c4_parity_fog_*_main.c), and its
output is compared with an oracle written here from the CE semantics. Members
that are not driven are reported as blocked in
docs/reports/m4-c4-parity-fog-2026-10-26.json, never marked passing.
"""
import hashlib
import itertools
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CE_SRC = ROOT / "submodules/halo-ce-universal/source"
SCENARIO_C = ROOT / "tests/c4_parity_fog_scenario_main.c"
LENS_C = ROOT / "tests/c4_parity_fog_lens_main.c"
NONE = -1
SHORT_MAX = 32767


def extract_function(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f"unterminated CE function: {marker}")


def build_and_run(template, ce_functions, prelude, stdin_text, name):
    with tempfile.TemporaryDirectory(prefix=f"c4-fog-{name}-") as td:
        src = Path(td) / f"{name}.c"
        exe = Path(td) / name
        src.write_text(template.replace("/*CE_FUNCTIONS*/", prelude + ce_functions))
        built = subprocess.run(["cc", "-std=gnu99", "-O1", str(src), "-o", str(exe), "-lm"],
                               capture_output=True, text=True)
        if built.returncode != 0:
            raise AssertionError(built.stderr)
        run = subprocess.run([str(exe)], input=stdin_text, capture_output=True, text=True)
        if run.returncode != 0:
            raise AssertionError(run.stdout + run.stderr)
        return run.stdout.splitlines()


# ---------------------------------------------------------------- scenario oracle

def oracle_region(bsp, cluster_index, pos):
    if cluster_index == NONE:
        return NONE
    fog_reference = bsp["clusters"][cluster_index]["fog_reference"]
    result = NONE
    if fog_reference != NONE:
        if fog_reference < 0 and (fog_reference & SHORT_MAX) >= len(bsp["planes"]):
            return NONE
        if fog_reference < 0:
            plane = bsp["planes"][fog_reference & SHORT_MAX]
            fog_index = oracle_fog_index(bsp, plane["region_index"])
            plane_distance = 0.0
            if fog_index != NONE:
                fog = bsp["fog_defs"][fog_index]
                if fog["flags"] & 1:
                    plane_distance = fog["plane_distance"]
            if pos is None:
                result = plane["region_index"]
            else:
                n = plane["n"]
                dist = pos[0] * n[0] + pos[1] * n[1] + pos[2] * n[2] - plane["d"]
                if dist + plane_distance < 0.0:
                    result = plane["region_index"]
        else:
            result = fog_reference & SHORT_MAX
        if not (0 <= result < len(bsp["regions"])):
            result = NONE
    return result


def oracle_fog_index(bsp, region_index):
    if 0 <= region_index < len(bsp["regions"]):
        palette_index = bsp["regions"][region_index]["fog_palette_index"]
        if 0 <= palette_index < len(bsp["palette"]):
            fog = bsp["palette"][palette_index]
            if fog != NONE:
                return fog
    return NONE


def oracle_underwater(bsp, cluster_index, pos):
    region = oracle_region(bsp, cluster_index, pos)
    weather = NONE
    underwater = False
    if region != NONE:
        fog_index = oracle_fog_index(bsp, region)
        if fog_index != NONE:
            underwater = bool(bsp["fog_defs"][fog_index]["flags"] & 1)
        weather = bsp["regions"][region]["weather_palette_index"]
    if weather == NONE and cluster_index != NONE:
        weather = bsp["clusters"][cluster_index]["weather_palette_index"]
    if not (0 <= weather < bsp["weather_count"]):
        weather = NONE
    return region, underwater, weather


def scenario_stdin(bsp, queries, fill):
    lines = [str(len(bsp["fog_defs"]))]
    for d in bsp["fog_defs"]:
        lines.append(f"{d['flags']} {d['plane_distance']}")
    lines.append(str(len(bsp["palette"])))
    lines += [str(v) for v in bsp["palette"]]
    lines.append(str(len(bsp["regions"])))
    lines += [f"{r['fog_palette_index']} {r['weather_palette_index']}" for r in bsp["regions"]]
    lines.append(str(len(bsp["planes"])))
    for p in bsp["planes"]:
        n = p["n"]
        lines.append(f"{p['region_index']} {n[0]} {n[1]} {n[2]} {p['d']}")
    lines.append(str(bsp["weather_count"]))
    lines.append(str(len(bsp["clusters"])))
    lines += [f"{c['fog_reference']} {c['weather_palette_index']}" for c in bsp["clusters"]]
    lines.append(str(int(fill)))
    lines.append(str(len(queries)))
    for cl, pos in queries:
        if pos is None:
            lines.append(f"{cl} 0 0 0 0")
        else:
            lines.append(f"{cl} 1 {pos[0]} {pos[1]} {pos[2]}")
    return "\n".join(lines) + "\n"


def scenario_expected(bsp, queries):
    out = []
    for i, (cl, pos) in enumerate(queries):
        region, underwater, weather = oracle_underwater(bsp, cl, pos)
        out.append(f"q {i} region={region} underwater={int(underwater)} weather={weather}")
    for r in range(len(bsp["regions"])):
        out.append(f"r {r} fog={oracle_fog_index(bsp, r)}")
    return out


BASE_SCENARIO = {
    "fog_defs": [{"flags": 1, "plane_distance": 2}, {"flags": 0, "plane_distance": 0}],
    "palette": [0, 1, NONE],
    "regions": [
        {"fog_palette_index": 0, "weather_palette_index": 0},
        {"fog_palette_index": 1, "weather_palette_index": NONE},
        {"fog_palette_index": 2, "weather_palette_index": 1},
        {"fog_palette_index": 0, "weather_palette_index": 1},
    ],
    "planes": [
        {"region_index": 0, "n": (0, 1, 0), "d": 0},
        {"region_index": 1, "n": (1, 0, 0), "d": 5},
    ],
    "weather_count": 2,
    "clusters": [
        {"fog_reference": NONE, "weather_palette_index": 1},
        {"fog_reference": -32768, "weather_palette_index": NONE},   # plane 0
        {"fog_reference": -32767, "weather_palette_index": 0},      # plane 1
        {"fog_reference": 1, "weather_palette_index": NONE},        # region 1
        {"fog_reference": 3, "weather_palette_index": NONE},        # region 3
        {"fog_reference": 9, "weather_palette_index": NONE},        # invalid region
        {"fog_reference": -32763, "weather_palette_index": 1},      # invalid plane
    ],
}
SCENARIO_QUERIES = [
    (0, None), (1, (0, -3, 0)), (1, (0, 3, 0)), (2, (7, 0, 0)), (2, (2, 0, 0)),
    (3, None), (4, (0, 0, 0)), (5, None), (6, None), (NONE, None),
]


def scenario_case(bsp, queries, fill):
    return {"bsp": bsp, "queries": queries, "fill": fill}


def deep_copy_bsp(bsp, **changes):
    import copy
    new = copy.deepcopy(bsp)
    new.update(changes)
    return new


def run_scenario_case(test, case, label):
    bsp, queries = case["bsp"], case["queries"]
    prelude = ""
    ce = "\n".join([
        "long scenario_fog_region_get_fog_index(short fog_region_index);",
        "short scenario_get_fog_region_index(const struct location *location, const real_point3d *position);",
        extract_function(SCENARIO_SRC, "short scenario_get_fog_region_index("),
        extract_function(SCENARIO_SRC, "boolean scenario_location_underwater("),
        extract_function(SCENARIO_SRC, "long scenario_fog_region_get_fog_index("),
    ])
    lines = build_and_run(SCENARIO_C.read_text(), ce, prelude,
                          scenario_stdin(bsp, queries, case["fill"]), "scenario")
    test.assertEqual(lines, scenario_expected(bsp, queries), label)


SCENARIO_SRC = (CE_SRC / "scenario/scenario.c").read_text()


class C4ScenarioFogParityTest(unittest.TestCase):
    def test_structure_sizes_match_ce_header(self):
        header = (CE_SRC / "structures/structure_bsp_definitions.h").read_text()
        self.assertIn("sizeof(struct structure_fog_region) == 0x28", header)
        self.assertIn("sizeof(struct structure_fog_plane) == 0x20", header)
        self.assertIn("sizeof(struct structure_fog_palette_entry) == 0x88", header)
        self.assertIn("sizeof(struct structure_cluster) == 0x68", header)
        self.assertIn("long fog_unused[6];", header)
        self.assertIn("long weather_unused[6];", header)

    def test_fog_palette_index_and_fog_palette_member_exact(self):
        # fog_palette_index selects the palette entry; the entry's fog index is
        # the output. Varying either one must change the consumer output as CE does.
        base = scenario_case(BASE_SCENARIO, SCENARIO_QUERIES, 0)
        run_scenario_case(self, base, "baseline")
        for region_idx in range(len(BASE_SCENARIO["regions"])):
            changed = deep_copy_bsp(BASE_SCENARIO)
            changed["regions"][region_idx]["fog_palette_index"] = NONE
            run_scenario_case(self, scenario_case(changed, SCENARIO_QUERIES, 0), f"palette-index-none-{region_idx}")
        changed = deep_copy_bsp(BASE_SCENARIO, palette=[1, 1, NONE])
        run_scenario_case(self, scenario_case(changed, SCENARIO_QUERIES, 0), "palette-entry0-changed")
        changed = deep_copy_bsp(BASE_SCENARIO, palette=[])
        run_scenario_case(self, scenario_case(changed, SCENARIO_QUERIES, 0), "palette-empty")

    def test_weather_palette_member_exact(self):
        for count in (0, 1, 2, 3):
            changed = deep_copy_bsp(BASE_SCENARIO, weather_count=count)
            run_scenario_case(self, scenario_case(changed, SCENARIO_QUERIES, 0), f"weather-count-{count}")

    def test_fog_unused_weather_unused_spans_do_not_affect_consumers(self):
        # fog_unused[6] and weather_unused[6] are retained but never read: poisoning
        # every unused byte of the consumer structs must not change any output.
        run_scenario_case(self, scenario_case(BASE_SCENARIO, SCENARIO_QUERIES, 0), "unused-clean")
        run_scenario_case(self, scenario_case(BASE_SCENARIO, SCENARIO_QUERIES, 1), "unused-poisoned")

    def test_fog_unused_weather_unused_have_no_ce_accesses(self):
        for member in ("fog_unused", "weather_unused"):
            hits = []
            for path in CE_SRC.rglob("*.[ch]"):
                text = path.read_text(errors="replace")
                hits += [str(path) for _ in re.finditer(r"(\.|->)\s*" + member + r"\b", text)]
            self.assertEqual(hits, [], member)


# ---------------------------------------------------------------- lens-flare oracle

def oracle_lens(flare_tags, marker_flares, clusters):
    lines = []
    limit = min(len(marker_flares), SHORT_MAX + 1 - 128)
    for c, (first, count) in enumerate(clusters):
        for k in range(count):
            ix = first + k
            if ix >= limit:
                lines.append(f"e {c} marker")
                break
            lfi = marker_flares[ix]
            if lfi >= len(flare_tags):
                lines.append(f"e {c} lens flare")
                continue
            tag = flare_tags[lfi]
            definition = tag if 0 <= tag < 256 else -1
            lines.append(f"s {c} {ix} {definition} 0")
        lines.append(f"c {c} done")
    return lines


def lens_stdin(flare_tags, marker_flares, clusters):
    lines = [str(len(flare_tags))] + [str(t) for t in flare_tags]
    lines += [str(len(marker_flares))] + [str(v) for v in marker_flares]
    lines += [str(len(clusters))] + [f"{f} {c}" for f, c in clusters]
    return "\n".join(lines) + "\n"


LENS_CASES = {
    "baseline": ([0, 1, 2], [0, 1, 2, 0, 1], [(0, 2), (2, 3)]),
    "marker-lens-flare-index-out-of-range": ([0, 1, 2], [0, 3, 1, 255, 2], [(0, 5)]),
    "lens-flare-tag-index-resolution": ([-1, 5, 300], [0, 1, 2, 2], [(0, 4)]),
    "lens-flares-count-zero": ([], [0, 0], [(0, 2)]),
    "lens-flare-markers-count-truncates": ([0, 1], [0, 1], [(0, 5)]),
    "marker-range-capacity-boundary": ([0], [0] * 32800, [(32630, 20)]),
    "empty-cluster": ([0], [0, 0], [(0, 0)]),
}


LENS_SRC = (CE_SRC / "rasterizer/rasterizer_lights.c").read_text()


class C4LensFlareParityTest(unittest.TestCase):
    def test_lens_flares_lens_flare_markers_lens_flare_index_member_exact(self):
        ce = extract_function(LENS_SRC, "void rasterizer_lens_flare_submit_for_cluster(")
        for label, (tags, markers, clusters) in LENS_CASES.items():
            with self.subTest(case=label):
                lines = build_and_run(LENS_C.read_text(), ce, "", lens_stdin(tags, markers, clusters), "lens")
                self.assertEqual(lines, oracle_lens(tags, markers, clusters))


# ---------------------------------------------------------------- distant lighting

LIGHTING_C = ROOT / "tests/c4_parity_fog_lighting_main.c"
OBJECT_LIGHTS_SRC = (CE_SRC / "objects/object_lights.c").read_text()
NONE_I = -1
DEFAULT_OBJECT_LIGHTING = {  # verbatim from object_lights.c default_object_lighting
    "ambient": (0.2, 0.2, 0.2), "dlc": 2,
    "dl": [((1.0, 1.0, 1.0), (-0.577, -0.577, -0.577)), ((0.4, 0.4, 0.5), (0.0, 0.0, 1.0))],
    "plc": 0, "pli": (0, 0), "tint": (0.5, 1.0, 1.0, 1.0), "shadow_vec": (0.0, 0.0, -1.0),
    "shadow_col": (0.0, 0.0, 0.0),
}


def extract_definition(source, name):
    """Return the verbatim CE definition (not a prototype) of a static or extern function."""
    start = 0
    while True:
        start = source.index(name, start)
        line_start = source.rfind("\n", 0, start) + 1
        head = source[line_start:start]
        if head.strip() in ("", "static", "static void", "boolean", "void", "real") or head.lstrip().startswith(("static", "boolean", "void", "real", "long", "short")):
            body_open = source.find("{", start)
            semi = source.find(";", start)
            if body_open != -1 and (semi == -1 or body_open < semi):
                return extract_function(source, source[start:body_open + 1])
        start += len(name)


def _pin(n, floor, ceiling):
    return floor if n < floor else min(n, ceiling)


def oracle_lighting(case):
    """Independent model of CE lights_distant_lighting_at_point (object_lights.c:2388) for the
    configured cases. Shading and sampling helpers are the stubs the C driver uses."""
    d = case["default"]
    default_ambient_red = d["ambient"][0]
    if default_ambient_red != 0.0:
        out = {"ambient": d["ambient"], "dlc": 2, "dl": [tuple(x) for x in d["dl"]], "plc": d["plc"],
               "pli": tuple(d["pli"]), "tint": tuple(d["tint"]), "shadow_vec": tuple(d["shadow_vec"]),
               "shadow_col": tuple(d["shadow_col"])}
    else:
        out = {k: (v if not isinstance(v, list) else [tuple(x) for x in v]) for k, v in DEFAULT_OBJECT_LIGHTING.items()}
        out["pli"] = tuple(out["pli"])
    if not case["hit"] or case["lightmap_group"] == NONE_I:
        return False, out
    if case["shader_env"] == 0 or case["base_map"] == NONE_I or case["lightmap_bitmap"] == NONE_I:
        return False, out
    s = t = 0.25
    w = 1.0 - s - t
    def shade(a, b, c):
        return tuple(w * a[i] + s * b[i] + t * c[i] for i in range(3))
    def norm(v):
        l = sum(x * x for x in v) ** 0.5
        return tuple(x / l for x in v) if l > 0 else v, l
    D, Lc = case["diffuse"], case["lightmap"]
    normals = case["normals"]
    surface_normal, _ = norm(shade(*normals))
    rad = []
    lengths = []
    for r in case["radiosity"]:
        nr, l = norm(r)
        rad.append(nr)
        lengths.append(l)
    radiosity_normal, _ = norm(shade(*rad))
    acc = w * lengths[0] + s * lengths[1] + t * lengths[2]
    brightness = Lc[0] * 0.299 + Lc[1] * 0.587 + Lc[2] * 0.114
    ambient = tuple(Lc[i] * 0.4 + 0.03 for i in range(3))
    dl0_col = Lc
    dl0_dir = tuple(-x for x in radiosity_normal)
    dl1_col = tuple(D[i] * 1.0 * brightness for i in range(3))
    tint_a = _pin(brightness * 1.5 + 0.25, 0.0, 1.0)
    tint = [_pin(D[i] * 3.0 + 0.5, 0.0, 1.0) for i in range(3)]
    tint = [tint[i] * _pin(Lc[i] * 2.0 + 0.25, 0.0, 1.0) for i in range(3)]
    accuracy = acc ** 0.25
    sv = [dl0_dir[0] * accuracy, dl0_dir[1] * accuracy]
    h = (sv[0] ** 2 + sv[1] ** 2) ** 0.5
    if h < 0.707:
        sk = -(1.0 - h * h) ** 0.5
    else:
        sk = -0.707
        h2 = 0.707 / h
        sv = [sv[0] * h2, sv[1] * h2]
    amb = (1.0 - acc) * 0.5
    shadow_col = tuple(_pin(1.0 - dl0_col[i] * 1.3 + amb, 0.03, 1.0) for i in range(3))
    out = {"ambient": ambient, "dlc": 2, "dl": [(dl0_col, dl0_dir), (dl1_col, surface_normal)],
           "plc": out["plc"], "pli": out["pli"], "tint": (tint_a, tint[0], tint[1], tint[2]),
           "shadow_vec": (sv[0], sv[1], sk), "shadow_col": shadow_col}
    return True, out


def parse_lighting(line):
    fields = dict(tok.split("=", 1) for tok in line.split(" ") if "=" in tok and not tok.startswith("dl"))
    dl = []
    for tok in line.split(" "):
        if tok.startswith("dl") and "=" in tok:
            vals = [float(x) for x in re.split(r"[=,|]", tok)[1:]]
            dl.append((tuple(vals[0:3]), tuple(vals[3:6])))
    tokens = line.split(" ")
    get = lambda key: next(t.split("=", 1)[1] for t in tokens if t.startswith(key + "="))
    return {
        "result": bool(int(get("result"))),
        "ambient": tuple(float(x) for x in get("ambient").split(",")),
        "dlc": int(get("distant")),
        "dl": dl,
        "plc": int(get("point")),
        "pli": (int(get("pli0")), int(get("pli1"))),
        "tint": tuple(float(x) for x in get("tint").split(",")),
        "shadow_vec": tuple(float(x) for x in get("shadow_vec").split(",")),
        "shadow_col": tuple(float(x) for x in get("shadow_col").split(",")),
    }


def close(a, b, tol=2e-5):
    if isinstance(a, tuple) or isinstance(a, list):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    return abs(a - b) <= tol * max(1.0, abs(b))


def lighting_stdin(case_list):
    lines = [str(len(case_list))]
    for c in case_list:
        d = c["default"]
        lines.append(str(c["flags"]))
        lines.append(" ".join(str(x) for x in (
            *d["ambient"], d["dlc"],
            *[v for dl in d["dl"] for pair in dl for v in pair],
            d["plc"], *d["pli"], *d["tint"], *d["shadow_vec"], *d["shadow_col"])))
        lines.append(f"{c['lightmap_group']}")
        lines.append(f"{int(c['hit'])}")
        lines.append(f"{c['shader_env']} {c['base_map']} {c['lightmap_bitmap']} {c['permutation']}")
        lines.append(" ".join(str(x) for x in (*c["diffuse"], *c["lightmap"])))
        lines.append(" ".join(str(x) for x in (*[v for n in c["normals"] for v in n],
                                               *[v for r in c["radiosity"] for v in r])))
    return "\n".join(lines) + "\n"


def lighting_case(**kw):
    base = {
        "flags": 0, "lightmap_group": 0, "hit": True, "shader_env": 1, "base_map": 0,
        "lightmap_bitmap": 0, "permutation": 0,
        "diffuse": (0.4, 0.5, 0.6), "lightmap": (0.3, 0.2, 0.1),
        "normals": ((0.0, 0.0, 1.0), (0.0, 0.6, 0.8), (0.6, 0.0, 0.8)),
        "radiosity": ((0.1, 0.2, 0.9), (0.0, 0.3, 0.7), (0.2, 0.0, 0.8)),
        "default": {"ambient": (0.1, 0.2, 0.3), "dlc": 0,
                    "dl": [((0.9, 0.8, 0.7), (0.0, 0.0, 1.0)), ((0.1, 0.1, 0.1), (1.0, 0.0, 0.0))],
                    "plc": 1, "pli": (5, 6), "tint": (0.5, 0.2, 0.3, 0.4),
                    "shadow_vec": (0.1, 0.2, -0.9), "shadow_col": (0.3, 0.3, 0.3)},
    }
    base.update(kw)
    return base


def default_with(**kw):
    d = lighting_case()["default"]
    d = {k: (list(v) if isinstance(v, list) else v) for k, v in d.items()}
    d.update(kw)
    return d


LIGHTING_CASES = {
    "hit-env-lightmap-group-valid": lighting_case(),
    "hit-sideways-raycast": lighting_case(flags=1),
    "lightmap-group-none": lighting_case(lightmap_group=NONE_I),
    "default-ambient-zero-uses-table": lighting_case(default=default_with(ambient=(0.0, 0.2, 0.3))),
    "default-point-count-0": lighting_case(hit=False, default=default_with(plc=0)),
    "default-point-count-2": lighting_case(hit=False, default=default_with(plc=2)),
    "default-distant-count-7": lighting_case(hit=False, default=default_with(dlc=7)),
    "no-hit-default-copy": lighting_case(hit=False),
    "non-environment-shader": lighting_case(shader_env=0),
    "lightmap-bitmap-none": lighting_case(lightmap_bitmap=NONE_I),
    "base-map-none": lighting_case(base_map=NONE_I),
}


class C4LightingParityTest(unittest.TestCase):
    def test_lightmap_group_default_lighting_distant_light_count_point_light_count_member_exact(self):
        ce = (extract_definition(OBJECT_LIGHTS_SRC, "static void brighten_real_rgb_color(")
              + "\n" + extract_definition(OBJECT_LIGHTS_SRC, "static void build_distant_lights(")
              + "\n" + extract_definition(OBJECT_LIGHTS_SRC, "boolean lights_distant_lighting_at_point("))
        names = list(LIGHTING_CASES)
        cases = [LIGHTING_CASES[n] for n in names]
        lines = build_and_run(LIGHTING_C.read_text(), ce, "", lighting_stdin(cases), "lighting")
        self.assertEqual(len(lines), len(cases))
        for name, case, line in zip(names, cases, lines):
            with self.subTest(case=name):
                expected_result, expected = oracle_lighting(case)
                got = parse_lighting(line)
                self.assertEqual(got["result"], expected_result)
                self.assertEqual(got["dlc"], expected["dlc"])
                self.assertEqual(got["plc"], expected["plc"])
                self.assertEqual(got["pli"], expected["pli"])
                self.assertTrue(close(got["ambient"], expected["ambient"]))
                self.assertTrue(close(got["tint"], expected["tint"]))
                self.assertTrue(close(got["shadow_vec"], expected["shadow_vec"]))
                self.assertTrue(close(got["shadow_col"], expected["shadow_col"]))
                for i in range(2):
                    self.assertTrue(close(got["dl"][i][0], expected["dl"][i][0]), (name, i))
                    self.assertTrue(close(got["dl"][i][1], expected["dl"][i][1]), (name, i))

    def test_member_variations_change_output(self):
        # lightmap_group NONE, default ambient zero and a non-environment shader each change
        # the output relative to the hit baseline, as CE does.
        lines = build_and_run(LIGHTING_C.read_text(),
                              "\n".join([extract_definition(OBJECT_LIGHTS_SRC, "static void brighten_real_rgb_color("),
                                          extract_definition(OBJECT_LIGHTS_SRC, "static void build_distant_lights("),
                                          extract_definition(OBJECT_LIGHTS_SRC, "boolean lights_distant_lighting_at_point(")]),
                              "", lighting_stdin([LIGHTING_CASES["hit-env-lightmap-group-valid"],
                                                  LIGHTING_CASES["lightmap-group-none"],
                                                  LIGHTING_CASES["non-environment-shader"]]), "lighting_var")
        self.assertNotEqual(lines[0], lines[1])
        self.assertNotEqual(lines[0], lines[2])


# ---------------------------------------------------------------- fog plane vertices (debug consumer)

FOG_PLANES_C = ROOT / "tests/c4_parity_fog_planes_main.c"
STRUCTURES_SRC = (CE_SRC / "structures/structures.c").read_text()


def oracle_fog_plane_debug(debug, cluster_fog_reference, max_distance, planes):
    """Model of render_debug_fog_planes (structures.c:628): draws each vertex edge and its offset edge."""
    lines = []
    if not debug or cluster_fog_reference is None:
        return lines + ["done"]
    plane = planes[cluster_fog_reference & SHORT_MAX]
    verts = plane
    n = len(verts)
    for i in range(n):
        p0 = verts[i]
        p1 = verts[(i + 1) % n]
        off = (0.0, 0.0, 1.0)  # plane normal (0,0,1)
        o0 = tuple(p0[k] + (off[k] * -max_distance) for k in range(3))
        o1 = tuple(p1[k] + (off[k] * -max_distance) for k in range(3))
        lines.append(("L", p0, p1, "white"))
        lines.append(("L", o0, o1, "black"))
        lines.append(("S", p0, o0))
        lines.append(("S", p1, o1))
    return lines + ["done"]


class C4FogPlaneVerticesTest(unittest.TestCase):
    def test_structure_fog_plane_vertices_debug_consumer_member_exact(self):
        ce = extract_definition(STRUCTURES_SRC, "void render_debug_fog_planes(")
        cases = {
            "debug-off": (0, 0, 2.0, [[(0, 0, 0), (1, 0, 0), (0, 1, 0)]]),
            "three-vertices": (1, 0, 2.0, [[(0, 0, 0), (1, 0, 0), (0, 1, 0)]]),
            "no-vertices": (1, 0, 2.0, [[]]),
            "two-planes-second-selected": (1, 1, 0.5, [[(0, 0, 0), (2, 0, 0)], [(5, 5, 5), (6, 5, 5), (6, 6, 5), (5, 6, 5)]]),
        }
        for label, (debug, ref, dist, planes) in cases.items():
            with self.subTest(case=label):
                stdin = [str(debug), str(ref), str(dist), str(len(planes))]
                for verts in planes:
                    stdin.append(str(len(verts)))
                    for v in verts:
                        stdin.append(f"{float(v[0])} {float(v[1])} {float(v[2])}")
                lines = build_and_run(FOG_PLANES_C.read_text(), ce, "", "\n".join(stdin) + "\n", "planes")
                expected = oracle_fog_plane_debug(debug, ref, dist, planes)
                self.assertEqual(len(lines), len(expected))
                self.assertEqual(lines[-1], "done")
                for got_line, exp in zip(lines[:-1], expected[:-1]):
                    parts = got_line.split(" ")
                    self.assertEqual(parts[0], exp[0])
                    a = tuple(float(x) for x in parts[1].split(","))
                    b = tuple(float(x) for x in parts[2].split(","))
                    self.assertTrue(close(a, exp[1]) and close(b, exp[2]), (label, got_line, exp))
                    if exp[0] == "L":
                        self.assertEqual(parts[3], exp[3])


# ---------------------------------------------------------------- compressed_vertex_data normals

COMPRESSED_C = ROOT / "tests/c4_parity_fog_compressed_main.c"
RASTER_GEOMETRY_SRC = (CE_SRC / "rasterizer/rasterizer_geometry.c").read_text()
RETAIL_MAPS = ("beavercreek", "boardingaction", "damnation")
MATERIAL_SIZE = 256            # tools/audit_mp_lightmap_surface_consumer.py MATERIAL_SIZE
COMPRESSED_DATA_AT = 236       # structure_material.compressed_vertex_data offset (ledger)
ENV_VERTEX_STRIDE = 0x20       # structures/structure_visibility.c COMPRESSED_STRUCTURE_VERTEX_SIZE


def oracle_uncompress_normal(c):
    """Independent decode of CE uncompress_int32_to_real_vector3d (11/11/10-bit fields, ILP32 long)."""
    def signed32(v):
        v &= 0xFFFFFFFF
        return v - (1 << 32) if v & 0x80000000 else v
    i = (float(signed32(c << 21)) * (1.0 / 1048576.0) + 1.0) * (1.0 / 2047.0)
    c >>= 11
    j = (float(signed32(c << 21)) * (1.0 / 1048576.0) + 1.0) * (1.0 / 2047.0)
    c >>= 11
    k = (float(signed32(c << 22)) * (1.0 / 2097152.0) + 1.0) * (1.0 / 1023.0)
    return (i, j, k)


def retail_compressed_normals(map_name):
    sys.path.insert(0, str(ROOT / "tools"))
    import audit_mp_lightmap_surface_consumer as audit
    path = audit.SOURCE_DIR / f"{map_name}.map"
    if hashlib.sha256(path.read_bytes()).hexdigest() != audit.MAP_SHA256[map_name]:
        raise AssertionError(f"{map_name} source changed")
    _index, location, image, parsed = audit.load_raw(path)
    words = []
    root = parsed.root
    lightmap_count = parsed.lightmap_count
    lightmap_at = struct.unpack_from("<I", image, root + audit.LIGHTMAP_AT + 4)[0] - location.address
    for li in range(lightmap_count):
        record = lightmap_at + li * audit.LIGHTMAP_SIZE
        count, address, _d = struct.unpack_from("<iII", image, record + 0x14)
        base = address - location.address
        for mi in range(count):
            m = base + mi * MATERIAL_SIZE
            size, _pad, _fo, data_address, _def = struct.unpack_from("<iIiII", image, m + COMPRESSED_DATA_AT)
            if size <= 0:
                continue
            data = data_address - location.address
            for vi in range(size // ENV_VERTEX_STRIDE):
                words.append(struct.unpack_from("<I", image, data + vi * ENV_VERTEX_STRIDE + 12)[0])
    return words


import hashlib
import struct
import sys


class C4CompressedVertexNormalTest(unittest.TestCase):
    def test_structure_material_compressed_vertex_data_normal_decode_member_exact(self):
        ce = extract_definition(RASTER_GEOMETRY_SRC, "real_vector3d uncompress_int32_to_real_vector3d(")
        ce = ce.replace("unsigned long compressed", "unsigned int compressed")
        # CE `long` is 32-bit (ILP32); the LP64 host needs (int) for the same sign extension.
        assert ce.count("(real)(long)(compressed<<") == 3, "CE decode seam changed"
        ce = ce.replace("(real)(long)(compressed<<", "(real)(int)(compressed<<")
        ce = ce + "\n" + extract_definition(RASTER_GEOMETRY_SRC, "void environment_vertex_compressed_get_normal(")
        total = 0
        for name in RETAIL_MAPS:
            with self.subTest(map=name):
                words = retail_compressed_normals(name)
                self.assertGreater(len(words), 0, name)
                stdin = "\n".join(str(w) for w in words) + "\n"
                lines = build_and_run(COMPRESSED_C.read_text(), ce, "", stdin, "compressed")
                self.assertEqual(len(lines), len(words))
                for w, line in zip(words, lines):
                    got = tuple(float(x) for x in line.split())
                    exp = oracle_uncompress_normal(w)
                    self.assertTrue(close(got, exp, tol=1e-6), (name, hex(w), got, exp))
                total += len(words)
        self.assertGreater(total, 0)


if __name__ == "__main__":
    unittest.main()
