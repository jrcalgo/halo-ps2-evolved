"""C4 consumer-level parity over the synthetic nonempty fixtures (tests/fixtures/c4).

Each fixture is validated by the schema walker, then its field is decoded from the image by the
manifest route. The decoded values become the input of a verbatim CE consumer (spliced from the pinned
submodule source and compiled with the host cc). An independent Python oracle, written from the CE semantics, gives
the expected output. Varied inputs mutate the fixture payload bytes (re-validated by the walker) or
compose the test-supplied companion fields the fixture does not carry, and are named in each case.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ctag_schema_walk import walk_structure_bsp  # noqa: E402
from tools.hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402

FIXTURE_DIR = ROOT / "tests/fixtures/c4"
SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
SOURCE_BASE = 0x70000000
ROOT_OFFSET = 32
LONG_MAX = 0x7FFFFFFF
LONG_MIN = -0x80000000
CE_LEAF_MAP = ROOT / "submodules/halo-ce-universal/source/structures/leaf_map.c"
CE_CLUSTER = ROOT / "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c"
CE_MATERIAL = ROOT / "submodules/halo-ce-universal/port/linux/game/custom_edition_geometry.c"
HARNESS = {
    "leaf": ROOT / "tests/c4_synth_consumer_leaf_main.c",
    "cluster": ROOT / "tests/c4_synth_consumer_cluster_main.c",
    "material": ROOT / "tests/c4_synth_consumer_material_main.c",
}
OUT = ROOT / "build/c4-synth-consumers"


# ---------------------------------------------------------------- fixture loading and decoding
def load_manifest():
    return json.loads((FIXTURE_DIR / "manifest.json").read_text())


_SCHEMA = None


def schema():
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = SchemaManifest(Elf32(SCHEMA_ELF)).build()
    return _SCHEMA


def fixture_image(field: str) -> bytearray:
    entry = load_manifest()["fields"][field]
    image = bytearray((FIXTURE_DIR / entry["file"]).read_bytes())
    if hashlib.sha256(image).hexdigest() != entry["sha256"]:
        raise AssertionError(f"{field}: fixture sha256 does not match the manifest")
    walk_structure_bsp(schema(), bytes(image), SOURCE_BASE)  # schema walker must accept the image
    return image


def validated(image: bytearray) -> bytes:
    walk_structure_bsp(schema(), bytes(image), SOURCE_BASE)
    return bytes(image)


def _defn(defn_id):
    return schema()["definitions"][str(defn_id)]


def _field(defn, name):
    return next(f for f in defn["fields"] if f["name"] == name)


def _i32(image, off):
    return struct.unpack_from("<i", image, off)[0]


def _u32(image, off):
    return struct.unpack_from("<I", image, off)[0]


def _root():
    group = next(g for g in schema()["groups"] if g["group"] == "sbsp")
    return _defn(group["definition"])


def resolve(image: bytes, route):
    """Follow a schema route from the sbsp root. Returns the final block or data field.

    Ancestor blocks are the single synthetic element the fixture builder writes. Returns
    ("block", count, element_addr_offset, element_size, element_defn) or ("data", size, addr_offset).
    """
    defn = _root()
    base = ROOT_OFFSET
    for name in route[:-1]:
        f = _field(defn, name)
        if f["kind"] == "struct":
            base += f["offset"]
            defn = _defn(f["definition"])
        elif f["kind"] == "block":
            count = _i32(image, base + f["offset"])
            addr = _u32(image, base + f["offset"] + 4) - SOURCE_BASE
            if count != 1:
                raise AssertionError(f"ancestor block {name} has count {count}")
            base = addr
            defn = _defn(f["definition"])
        else:
            raise AssertionError(f"unexpected ancestor kind {f['kind']} for {name}")
    f = _field(defn, route[-1])
    if f["kind"] == "block":
        count = _i32(image, base + f["offset"])
        addr = _u32(image, base + f["offset"] + 4) - SOURCE_BASE
        elem = _defn(f["definition"])
        return ("block", count, addr, elem["size"], elem)
    if f["kind"] == "data":
        size = _i32(image, base + f["offset"])
        addr = _u32(image, base + f["offset"] + 12) - SOURCE_BASE
        return ("data", size, addr)
    raise AssertionError(f"route end {route[-1]} is {f['kind']}")


def route_of(field):
    return load_manifest()["fields"][field]["construction_recipe"]["route"]


def elements(image: bytes, field: str):
    kind, count, addr, size, _ = resolve(image, route_of(field))
    return [bytes(image[addr + i * size: addr + (i + 1) * size]) for i in range(count)]


def decode_designators(image: bytes):
    kind, count, addr, size, _ = resolve(image, route_of("map_leaf.portal_designators"))
    assert kind == "block" and size == 4
    return [struct.unpack_from("<i", image, addr + 4 * i)[0] for i in range(count)]


def decode_leaf_element(elem: bytes):
    """map_leaf (24 bytes): faces block at +0, portal_designators block at +12 (manifest offsets)."""
    f_count, f_addr = struct.unpack_from("<iI", elem, 0)
    d_count, d_addr = struct.unpack_from("<iI", elem, 12)
    return {"faces": f_count, "designators_count": d_count}


def decode_portal_element(elem: bytes):
    """leaf_portal (24 bytes): plane_index @0, leaf_indices[2] @4, vertices block @12 (CE struct layout)."""
    plane, l0, l1 = struct.unpack_from("<iii", elem, 0)
    v_count = struct.unpack_from("<i", elem, 12)[0]
    return {"leaf_indices": (l0, l1), "plane": plane, "vertices": v_count}


def decode_face_element(elem: bytes):
    """map_leaf_face (16 bytes): node_index @0 (CE layout), vertices block @4 (manifest)."""
    node = struct.unpack_from("<h", elem, 0)[0]
    v_count = struct.unpack_from("<i", elem, 4)[0]
    return {"node": node, "vertices": v_count}


def decode_cluster_list(image: bytes):
    kind, count, addr, size, _ = resolve(image, route_of("structure_cluster.surface_indices"))
    return [struct.unpack_from("<i", image, addr + 4 * i)[0] for i in range(count)]


def decode_material_data(image: bytes):
    kind, size, addr = resolve(image, route_of("structure_material.uncompressed_vertex_data"))
    return bytes(image[addr:addr + size])


# ---------------------------------------------------------------- verbatim CE splicing and compile
def extract_definition(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    prototype_end = source.find(";", start, opening)
    if prototype_end >= 0:
        start = source.index(marker, prototype_end + 1)
        opening = source.index("{", start)
    depth = 0
    for position in range(opening, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start:position + 1]
    raise AssertionError(f"unterminated CE function {marker}")


def run_harness(kind: str, bodies: str, stdin_text: str) -> str:
    template = HARNESS[kind].read_text()
    marker = {"leaf": "/* CE_LEAF_MAP_FUNCTIONS */", "cluster": "/* CE_CLUSTER_FUNCTIONS */",
              "material": "/* CE_MATERIAL_CONVERT */"}[kind]
    OUT.mkdir(parents=True, exist_ok=True)
    source = OUT / f"c4_synth_{kind}.c"
    executable = OUT / f"c4_synth_{kind}"
    source.write_text(template.replace(marker, bodies))
    cc = os.environ.get("CC", "cc")
    compiled = subprocess.run(
        [cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
         "-Wno-unused-parameter", "-Wno-unused-variable", str(source), "-o", str(executable), "-lm"],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        raise AssertionError(compiled.stdout + compiled.stderr)
    result = subprocess.run([str(executable)], input=stdin_text, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def leaf_bodies():
    text = CE_LEAF_MAP.read_text(errors="replace")
    return "\n".join([
        extract_definition(text, "void leaf_map_close_portal("),
        extract_definition(text, "boolean leaf_map_leaf_is_closed("),
        extract_definition(text, "void leaf_map_get_leaf_bounds("),
    ])


def cluster_bodies():
    return extract_definition(CE_CLUSTER.read_text(errors="replace"), "static void structure_cluster_check(")


def material_bodies():
    return extract_definition(CE_MATERIAL.read_text(errors="replace"), "static boolean structure_material_convert(")


# ---------------------------------------------------------------- leaf-map case model and oracle
def leaf_case_text(leaves, portals, ops):
    lines = [f"LEAVES {len(leaves)}"]
    for i, leaf in enumerate(leaves):
        lines.append(f"LEAF {i} {len(leaf['designators'])} " +
                     " ".join(str(d) for d in leaf["designators"]) +
                     f" {leaf['faces']}")
    lines.append(f"PORTALS {len(portals)}")
    for i, p in enumerate(portals):
        lines.append(f"PORTAL {i} {p['leaf_indices'][0]} {p['leaf_indices'][1]} {p['vertices']}")
    lines += ops
    return "\n".join(lines) + "\n"


def oracle_leaf(leaves, portals, ops):
    """CE semantics of leaf_map_close_portal / leaf_map_leaf_is_closed / leaf_map_get_leaf_bounds."""
    designators = [list(l["designators"]) for l in leaves]
    out = []
    for op in ops:
        tag, arg = op.split()
        if tag == "CLOSE":
            p = int(arg)
            out.append(f"CLOSE {p}")
            for side in range(2):
                leaf = portals[p]["leaf_indices"][side] & LONG_MAX
                ds = designators[leaf]
                found = None
                for i, d in enumerate(ds):
                    if (d & LONG_MAX) == p:
                        ds[i] = d | LONG_MIN
                        found = i
                        break
                if found is None:
                    out.append("ASSERT 673")
        elif tag == "CLOSED":
            l = int(arg)
            ds = designators[l & LONG_MAX]
            # CE: FALSE at the first open designator, else (boolean) designator count
            closed = 1 if (ds and all(d & LONG_MIN for d in ds)) else 0
            out.append(f"CLOSED {l} {closed}")
        elif tag == "BOUNDS":
            l = int(arg)
            leaf = leaves[l & LONG_MAX]
            # bounds stay at the CE null rectangle unless a designator's portal or a face contributes a vertex;
            # every vertex in these cases is absent, so the null rectangle (x0=FLT_MAX, x1=-FLT_MAX, ...) is kept.
            center = (0.0, 0.0, 0.0)
            out.append(f"BOUNDS {l} center {float_hex(center[0])} {float_hex(center[1])} {float_hex(center[2])} "
                       f"radius inf")
    return out


def float_hex(v: float) -> str:
    return "0x0p+0" if v == 0 else v.hex()


def parse_stdout_to_lines(stdout: str):
    return [line.rstrip() for line in stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------- cluster oracle
NONE = -1


def oracle_cluster(surfaces, lightmaps, materials_vertex_counts, lst):
    """structure_cluster_check surface-list semantics for one lightmap with the given material vertex counts."""
    lst = list(lst)
    messages = []
    count = len(lst)
    index = 0
    while index + 3 <= count:
        li = lst[index]
        mi = lst[index + 1]
        group_count = lst[index + 2]
        if li < 0 or li >= lightmaps:
            break
        if mi < 0 or mi >= 1:  # one lightmap holds materials_vertex_counts (one material per case)
            break
        mat_vertices = materials_vertex_counts
        index += 3
        if group_count <= 0:
            group_end = index
        elif group_count > count - index:
            group_end = count
        else:
            group_end = index + group_count
        while index < group_end:
            si = lst[index]
            if si < 0 or si >= len(surfaces):
                index += 1
                continue
            verts = surfaces[si]
            if any(v >= mat_vertices for v in verts):
                messages.append(f"cluster 0's surface {si} is not of its group's material (lightmap {li}'s {mi}): none")
                lst[index] = NONE
            index += 1
    return lst, messages


def cluster_output(lst_before, surfaces, mats, lightmaps=1):
    lst, msgs = oracle_cluster(surfaces, lightmaps, mats, lst_before)
    lines = ["RUN"] + [f"CORRECT {m}" for m in msgs] + ["LIST " + " ".join(str(v) for v in lst)]
    return lines


# ---------------------------------------------------------------- material oracle
def oracle_material(vc, lc, data: bytes):
    lines = [f"CONVERT vc={vc} lc={lc}"]
    env_uncomp, env_comp, lm_uncomp, lm_comp = 56, 20, 20, 12
    success = True
    if vc:
        lines += compress_line(vc, 0, vc * env_uncomp, data)
        lines.append(f"VB type=1 count={vc} bytes={vc * env_comp}")
    if success and lc:
        off = vc * env_uncomp
        lines += compress_line(lc, off, lc * lm_uncomp, data)
        lines.append(f"VB type=3 count={lc} bytes={lc * lm_comp}")
    lines.append("RESULT 1")
    return lines


def compress_line(count, offset, dst_bytes, data):
    need = offset + dst_bytes
    if need > len(data):
        return [f"COMPRESS count={count} dst_offset={offset} dst_bytes={dst_bytes} OVERRUN need={need} have={len(data)}"]
    hexes = "".join(f" {b:02x}" for b in data[offset:offset + dst_bytes])
    return [f"COMPRESS count={count} dst_offset={offset} dst_bytes={dst_bytes} BYTES{hexes}"]


def material_stdin(vc, lc, data: bytes):
    return (f"DATA {len(data)}\n" + "BYTES " + " ".join(f"{b:02x}" for b in data) + "\n" +
            f"MATERIAL {vc} {lc}\n")
