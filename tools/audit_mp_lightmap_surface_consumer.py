#!/usr/bin/env python3
"""Audit CE lightmap/material surface lookup on the 13 stock multiplayer maps.

The oracle is a linear read of raw Xbox BSP bytes. The lookup under test is the
unmodified CE function structure_bsp_find_material_for_surface, compiled ILP32
and run on a relocated copy of the published CBSP image. BSPS v2 / TEXS shader
identity is taken from halo2ps2's converters because the capacity packages do
not store those sections. Nothing here is treated as safe to strip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
CE_SOURCE = HCU / "source/structures/structure_bsp_definitions.c"
HARNESS = ROOT / "tests/lightmap_surface_consumer_main.c"
OUT = ROOT / "build/step7-swarm/lightmap"
SOURCE_DIR = Path(os.environ.get(
    "HALO_HCU_MP_MAP_DIR", ROOT / "build/retail-maps/decompressed"))
TAG_BASE = 0xE0000000
SURFACE_AT = 0xF8
LIGHTMAP_AT = 0x104
MATERIAL_SIZE = 256
LIGHTMAP_SIZE = 32
CE_SOURCE_SHA256 = "c15b1b1b6ab0b8c24e494e3bf3a5340eca89899ded49f900a2b544241374afee"

MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
MAP_SHA256 = {
    "beavercreek": "eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a",
    "bloodgulch": "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1",
    "boardingaction": "34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522",
    "carousel": "3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1",
    "chillout": "52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb",
    "damnation": "87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c",
    "hangemhigh": "e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f",
    "longest": "e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9",
    "prisoner": "85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307",
    "putput": "efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243",
    "ratrace": "577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e",
    "sidewinder": "995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc",
    "wizard": "978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb",
}
PACKAGE_SHA256 = {
    "beavercreek": "4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc",
    "bloodgulch": "ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011",
    "boardingaction": "2c12e7c0cf555698b837397666b1f343a6864fe16deeffb0b0d4a007e869acd0",
    "carousel": "e24191ed1e660dfb3c9c9bcd88abcff61c366690f6d903f3b0622eb2c2e751b4",
    "chillout": "727abc7401a530892f1136f082a6254544915e0d85f2a068f63d9530189b1bf0",
    "damnation": "ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d",
    "hangemhigh": "1e2a4df7a5ba17d0742bd30484fcfe63db011e6c47a87ac0f2d06ac6f5cab58f",
    "longest": "6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b",
    "prisoner": "3bb10f06c785da93fe0f7257be9f06519b7ccb6c155801a7a04a5e6d56352136",
    "putput": "6d66e4ecf9c51b3ae417d85356de9ff66c14bc9fc19dd4a2bd2a2954f6b4f3bd",
    "ratrace": "a735d4a5bef86cc7277ae888a1ef9da25f28f0ab6e45dff010da53dc41e685da",
    "sidewinder": "968ab65ea7ae6fbd15925ed28eb0f8eafc267c78f53150b59b4cc1dea2d017f5",
    "wizard": "00bf468d4d8c96e234ef21e5bfb59b410cac7c3e8c9f4f848ea20fbfacf01c57",
}

sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")]
from hcu_package_root import LEGACY_DIR, resolve_package_dir  # noqa: E402

# Pin-verified package root (env var, historical /tmp dir, then persistent
# build/mp-fog-selection-*/assets/maps); None when no verified set exists.
PACKAGE_DIR_RESOLVED = resolve_package_dir(PACKAGE_SHA256)
PACKAGE_DIR = PACKAGE_DIR_RESOLVED or LEGACY_DIR
from host_abi32 import flags as host_abi32_flags  # noqa: E402
from halo2ps2 import bsp, bspconv, hp2, mapinfo, tagindex, texconv  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
import cbsp  # noqa: E402


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fnv1a(data: bytes) -> int:
    hash_value = 2166136261
    for byte in data:
        hash_value ^= byte
        hash_value = (hash_value * 16777619) & 0xFFFFFFFF
    return hash_value


def git_head(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def extract_function(source: str) -> str:
    marker = "boolean structure_bsp_find_material_for_surface("
    start = source.find(marker)
    second = source.find(marker, start + 1)
    if start < 0 or second >= 0:
        raise AssertionError("expected one CE structure_bsp_find_material_for_surface body")
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                body = source[start:offset + 1]
                if body not in source:
                    raise AssertionError("extracted CE function is not verbatim")
                return body
    raise AssertionError("unterminated CE function")


def compile_harness(log: list[str]) -> tuple[Path, str]:
    source = CE_SOURCE.read_text(encoding="utf-8")
    if sha256_file(CE_SOURCE) != CE_SOURCE_SHA256:
        raise RuntimeError("CE structure_bsp_definitions.c hash differs from the pinned source")
    body = extract_function(source)
    template = HARNESS.read_text(encoding="utf-8")
    token = "/* CE_FUNCTION */"
    if template.count(token) != 1:
        raise RuntimeError("harness is missing the CE function splice point")
    generated = OUT / "lightmap_surface_consumer_generated.c"
    executable = OUT / "lightmap_surface_consumer"
    generated.write_text(template.replace(token, body + "\n"), encoding="utf-8")
    command = [
        os.environ.get("CC", "gcc"), *host_abi32_flags(),
        "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-O2", "-fno-strict-aliasing",
        str(generated), "-o", str(executable),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    log.append("compile " + " ".join(command))
    if result.stdout:
        log.append(result.stdout.rstrip())
    if result.stderr:
        log.append(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError("ILP32 harness failed to compile")
    return executable, body


class Material(object):
    def __init__(self, lightmap, material, bitmap, group, shader_id, permutation,
                 flags, first, count, rendered_vertices, lightmap_vertices):
        self.lightmap = lightmap
        self.material = material
        self.bitmap = bitmap
        self.group = group
        self.shader_id = shader_id
        self.permutation = permutation
        self.flags = flags
        self.first = first
        self.count = count
        self.rendered_vertices = rendered_vertices
        self.lightmap_vertices = lightmap_vertices

    def identity(self):
        return (self.bitmap, self.group, self.shader_id, self.permutation, self.flags,
                self.first, self.count, self.rendered_vertices, self.lightmap_vertices)


class ParsedBsp(object):
    def __init__(self):
        self.surface_count = 0
        self.surfaces = b""
        self.surface_definition = 0
        self.lightmap_count = 0
        self.lightmap_definition = 0
        self.header_materials = 0
        self.header_materials_again = 0
        self.materials = []
        self.lightmap_definitions = []
        self.followed_pointers = []
        self.root = 0


def parse_bsp(image: bytes, pointer_base: int) -> ParsedBsp:
    parsed = ParsedBsp()
    if len(image) < 0x18 or image[0x14:0x18] != b"psbs":
        raise ValueError("BSP image is missing the psbs signature")
    header = struct.unpack_from("<5I", image, 0)
    parsed.header_materials = header[1]
    parsed.header_materials_again = header[3]
    root_pointer = header[0]
    parsed.root = root_pointer - pointer_base
    if parsed.root < 0 or parsed.root + 0x110 > len(image):
        raise ValueError(f"structure_bsp root {parsed.root} leaves the image")

    def block(offset):
        count, address, definition = struct.unpack_from("<iII", image, parsed.root + offset)
        if count < 0:
            raise ValueError(f"negative block count at {offset:#x}")
        if count == 0:
            return 0, 0, definition
        start = address - pointer_base
        return count, start, definition

    surface_count, surface_at, surface_definition = block(SURFACE_AT)
    if surface_count and (surface_at < 0 or surface_at + surface_count * 6 > len(image)):
        raise ValueError("surface array leaves the image")
    lightmap_count, lightmap_at, lightmap_definition = block(LIGHTMAP_AT)
    if lightmap_count and (lightmap_at < 0 or lightmap_at + lightmap_count * LIGHTMAP_SIZE > len(image)):
        raise ValueError("lightmap array leaves the image")
    parsed.surface_count = surface_count
    parsed.surfaces = image[surface_at:surface_at + surface_count * 6] if surface_count else b""
    parsed.surface_definition = surface_definition
    parsed.lightmap_count = lightmap_count
    parsed.lightmap_definition = lightmap_definition
    if lightmap_count:
        parsed.followed_pointers.append(parsed.root + LIGHTMAP_AT + 4)
    for lightmap_index in range(lightmap_count):
        record = lightmap_at + lightmap_index * LIGHTMAP_SIZE
        bitmap = struct.unpack_from("<H", image, record)[0]
        material_count, material_address, material_definition = struct.unpack_from("<iII", image, record + 0x14)
        parsed.lightmap_definitions.append(material_definition)
        if material_count < 0:
            raise ValueError(f"lightmap {lightmap_index} has a negative material count")
        material_at = material_address - pointer_base if material_count else 0
        if material_count and (material_at < 0 or material_at + material_count * MATERIAL_SIZE > len(image)):
            raise ValueError(f"lightmap {lightmap_index} materials leave the image")
        if material_count:
            parsed.followed_pointers.append(record + 0x18)
        for material_index in range(material_count):
            material = material_at + material_index * MATERIAL_SIZE
            group = image[material:material + 4]
            shader_id = struct.unpack_from("<I", image, material + 0x0C)[0]
            permutation, flags = struct.unpack_from("<hH", image, material + 0x10)
            first, count = struct.unpack_from("<ii", image, material + 0x14)
            rendered = struct.unpack_from("<I", image, material + 0xB4)[0]
            lightmap_vertices = struct.unpack_from("<I", image, material + 0xC8)[0]
            parsed.materials.append(Material(
                lightmap_index, material_index, bitmap, group, shader_id, permutation,
                flags, first, count, rendered, lightmap_vertices))
    return parsed


def load_raw(map_path: Path):
    index = tagindex.TagIndex.read(map_path)
    region, _tag_base, _meta = read_xbox_tag_region(map_path)
    header = mapinfo.read_header(map_path)
    locations = bsp.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise ValueError(f"{map_path.name} has {len(locations)} BSP blocks")
    location = locations[0]
    image = map_path.read_bytes()[location.file_offset:location.file_offset + location.size]
    if len(image) != location.size:
        raise ValueError(f"truncated BSP in {map_path.name}")
    parsed = parse_bsp(image, location.address)
    return index, location, image, parsed


def interval_and_vertex_issues(parsed: ParsedBsp, tags_by_id: dict) -> list[dict]:
    issues = []
    if parsed.header_materials != parsed.header_materials_again or parsed.header_materials != len(parsed.materials):
        issues.append({
            "kind": "header-material-count",
            "header": parsed.header_materials,
            "header_again": parsed.header_materials_again,
            "walked": len(parsed.materials),
        })
    if parsed.lightmap_definition != 0:
        issues.append({"kind": "lightmap-definition", "value": parsed.lightmap_definition})
    if parsed.surface_definition != 0:
        issues.append({"kind": "surface-definition", "value": parsed.surface_definition})
    covered = [0] * parsed.surface_count
    previous_span = None
    grouped = {}
    for material in parsed.materials:
        grouped.setdefault(material.lightmap, []).append(material)
    for lightmap_index in range(parsed.lightmap_count):
        materials = grouped.get(lightmap_index, [])
        definition = parsed.lightmap_definitions[lightmap_index] if lightmap_index < len(parsed.lightmap_definitions) else None
        if definition:
            issues.append({"kind": "material-definition", "lightmap": lightmap_index, "value": definition})
        if not materials:
            issues.append({"kind": "empty-lightmap", "lightmap": lightmap_index})
            continue
        previous_first = None
        for material in materials:
            group_name = material.group[::-1].decode("ascii", "replace")
            if material.first < 0 or material.count < 0 or material.first + material.count > parsed.surface_count:
                issues.append({
                    "kind": "material-range",
                    "lightmap": material.lightmap,
                    "material": material.material,
                    "first": material.first,
                    "count": material.count,
                    "surfaces": parsed.surface_count,
                })
            if previous_first is not None and material.first < previous_first:
                issues.append({
                    "kind": "unsorted-material",
                    "lightmap": material.lightmap,
                    "material": material.material,
                    "first": material.first,
                    "previous_first": previous_first,
                })
            if previous_first is not None:
                previous = materials[materials.index(material) - 1]
                if material.first < previous.first + previous.count:
                    issues.append({
                        "kind": "overlap-material",
                        "lightmap": material.lightmap,
                        "material": material.material,
                        "first": material.first,
                        "previous_first": previous.first,
                        "previous_count": previous.count,
                    })
            previous_first = material.first
            if material.count == 0:
                issues.append({
                    "kind": "empty-material",
                    "lightmap": material.lightmap,
                    "material": material.material,
                    "first": material.first,
                })
            for surface in range(max(0, material.first), min(parsed.surface_count, material.first + max(material.count, 0))):
                covered[surface] += 1
            if material.count > 0 and 0 <= material.first < parsed.surface_count:
                for offset in range(material.count):
                    surface = material.first + offset
                    if not 0 <= surface < parsed.surface_count:
                        continue
                    indices = struct.unpack_from("<3H", parsed.surfaces, surface * 6)
                    if max(indices) >= material.rendered_vertices:
                        issues.append({
                            "kind": "vertex-index",
                            "lightmap": material.lightmap,
                            "material": material.material,
                            "surface": surface,
                            "indices": list(indices),
                            "rendered_vertices": material.rendered_vertices,
                            "lightmap_vertices": material.lightmap_vertices,
                        })
            tag = tags_by_id.get(material.shader_id)
            if material.shader_id == 0xFFFFFFFF or tag is None:
                issues.append({
                    "kind": "shader-unresolved",
                    "lightmap": material.lightmap,
                    "material": material.material,
                    "shader_id": material.shader_id,
                    "group": group_name,
                })
            elif tag.group != group_name:
                issues.append({
                    "kind": "shader-group",
                    "lightmap": material.lightmap,
                    "material": material.material,
                    "shader_id": material.shader_id,
                    "raw_group": group_name,
                    "tag_group": tag.group,
                    "path": tag.path,
                })
        start = materials[0].first
        end = materials[-1].first + materials[-1].count
        if previous_span is not None and start < previous_span[1] and previous_span[0] < end:
            issues.append({
                "kind": "overlap-lightmap",
                "lightmap": lightmap_index,
                "start": start,
                "end": end,
                "previous_lightmap": previous_span[2],
                "previous_start": previous_span[0],
                "previous_end": previous_span[1],
            })
        previous_span = (start, end, lightmap_index)
    uncovered = [index for index, count in enumerate(covered) if count == 0]
    multi = [index for index, count in enumerate(covered) if count > 1]
    if uncovered:
        issues.append({"kind": "uncovered-surfaces", "count": len(uncovered), "surfaces": uncovered})
    if multi:
        issues.append({"kind": "multi-owned-surfaces", "count": len(multi), "surfaces": multi})
    return issues


def compare_published(raw: ParsedBsp, published: ParsedBsp) -> list[dict]:
    issues = []
    if raw.surface_count != published.surface_count or raw.lightmap_count != published.lightmap_count:
        issues.append({
            "kind": "cbsp-block-count",
            "raw_surfaces": raw.surface_count,
            "cbsp_surfaces": published.surface_count,
            "raw_lightmaps": raw.lightmap_count,
            "cbsp_lightmaps": published.lightmap_count,
        })
    if raw.surfaces != published.surfaces:
        mismatches = []
        limit = min(len(raw.surfaces), len(published.surfaces))
        for offset in range(limit):
            if raw.surfaces[offset] != published.surfaces[offset]:
                mismatches.append({
                    "offset": offset,
                    "raw": raw.surfaces[offset],
                    "cbsp": published.surfaces[offset],
                })
                if len(mismatches) == 8:
                    break
        issues.append({
            "kind": "cbsp-surface-bytes",
            "raw_bytes": len(raw.surfaces),
            "cbsp_bytes": len(published.surfaces),
            "compared_prefix_mismatches": mismatches,
        })
    if len(raw.materials) != len(published.materials):
        issues.append({
            "kind": "cbsp-material-count",
            "raw": len(raw.materials),
            "cbsp": len(published.materials),
        })
    for raw_material, published_material in zip(raw.materials, published.materials):
        if raw_material.identity() != published_material.identity():
            issues.append({
                "kind": "cbsp-material-field",
                "lightmap": raw_material.lightmap,
                "material": raw_material.material,
                "raw": {
                    "bitmap": raw_material.bitmap,
                    "group": raw_material.group[::-1].decode("ascii", "replace"),
                    "shader_id": raw_material.shader_id,
                    "permutation": raw_material.permutation,
                    "flags": raw_material.flags,
                    "first": raw_material.first,
                    "count": raw_material.count,
                    "rendered_vertices": raw_material.rendered_vertices,
                    "lightmap_vertices": raw_material.lightmap_vertices,
                },
                "cbsp": {
                    "bitmap": published_material.bitmap,
                    "group": published_material.group[::-1].decode("ascii", "replace"),
                    "shader_id": published_material.shader_id,
                    "permutation": published_material.permutation,
                    "flags": published_material.flags,
                    "first": published_material.first,
                    "count": published_material.count,
                    "rendered_vertices": published_material.rendered_vertices,
                    "lightmap_vertices": published_material.lightmap_vertices,
                },
            })
    return issues


def owners_for(parsed: ParsedBsp) -> dict:
    owners = {}
    for material in parsed.materials:
        for surface in range(material.first, material.first + material.count):
            if 0 <= surface < parsed.surface_count:
                owners.setdefault(surface, []).append(material)
    return owners


def compare_ce(parsed: ParsedBsp, queries: list[int], rows: list[tuple[int, int, int]]) -> list[dict]:
    issues = []
    owners = owners_for(parsed)
    if len(rows) != len(queries):
        return [{"kind": "ce-result-length", "queries": len(queries), "rows": len(rows)}]
    for surface, (found, lightmap, material) in zip(queries, rows):
        if surface < 0 or surface >= parsed.surface_count:
            if found:
                issues.append({
                    "kind": "ce-mismatch",
                    "surface": surface,
                    "ce_found": found,
                    "ce_lightmap": lightmap,
                    "ce_material": material,
                    "oracle": "out-of-range",
                })
            continue
        owned = owners.get(surface, [])
        if len(owned) == 1 and found and lightmap == owned[0].lightmap and material == owned[0].material:
            continue
        issues.append({
            "kind": "ce-mismatch",
            "surface": surface,
            "ce_found": found,
            "ce_lightmap": lightmap,
            "ce_material": material,
            "oracle_owners": [
                {"lightmap": item.lightmap, "material": item.material,
                 "first": item.first, "count": item.count, "shader_id": item.shader_id}
                for item in owned
            ],
        })
    return issues


def write_fixture(path: Path, image: bytes, relocations: tuple, tag_relocations: tuple,
                  queries: list[int], expected_lightmaps: int, mat0_first: int, mat0_count: int) -> None:
    tag_fields = [field for field, _target in tag_relocations]
    blob = bytearray(b"LMFIX01\x00")
    blob += struct.pack(
        "<IIIIiiiI", len(image), len(relocations), len(tag_fields), len(queries),
        expected_lightmaps, mat0_first, mat0_count, TAG_BASE)
    blob += image
    if relocations:
        blob += struct.pack("<" + "I" * len(relocations), *relocations)
    if tag_fields:
        blob += struct.pack("<" + "I" * len(tag_fields), *tag_fields)
    if queries:
        blob += struct.pack("<" + "i" * len(queries), *queries)
    path.write_bytes(blob)


def read_results(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 44 or data[:4] != b"LMOK":
        raise ValueError("CE result header is missing")
    (bytes_unchanged, depth_before, depth_after, slow_path, seen_lightmaps,
     mat0_first, mat0_count, fnv_before, fnv_after, query_count) = struct.unpack_from("<IiiIiiiIII", data, 4)
    body = data[44:]
    if query_count * 12 != len(body):
        raise ValueError(f"CE result body is {len(body)} bytes for {query_count} queries")
    rows = [tuple(item) for item in struct.iter_unpack("<iii", body)]
    return {
        "bytes_unchanged": bytes_unchanged,
        "depth_before": depth_before,
        "depth_after": depth_after,
        "slow_path": slow_path,
        "seen_lightmaps": seen_lightmaps,
        "mat0_first": mat0_first,
        "mat0_count": mat0_count,
        "fnv_before": fnv_before,
        "fnv_after": fnv_after,
        "rows": rows,
    }


def map_batches(materials, structure, section) -> tuple[dict, list[dict]]:
    groups = {}
    issues = []
    for material_index, material in enumerate(materials):
        for triangle_index, surface_id in enumerate(material.surfaces):
            clusters = structure.cluster_surfaces.get(surface_id)
            if clusters:
                groups.setdefault((tuple(sorted(clusters)), material_index), []).append(triangle_index)
    covered = {}
    batch_index = 0
    ordered_groups = sorted(groups.items(), key=lambda item: (item[0][0][0], item[0][1], item[0][0]))
    for (clusters, material_index), triangles in ordered_groups:
        material = materials[material_index]
        ordered = bspconv._spatial_order(material, triangles)
        for start in range(0, len(ordered), bspconv.MAX_TRIS):
            chunk = ordered[start:start + bspconv.MAX_TRIS]
            if batch_index >= len(section.batches):
                issues.append({"kind": "bsps-batch-sequence", "batch": batch_index, "section_batches": len(section.batches)})
                return covered, issues
            batch = section.batches[batch_index]
            if batch["material"] != material_index or batch["triangles"] != len(chunk):
                issues.append({
                    "kind": "bsps-batch-identity",
                    "batch": batch_index,
                    "section_material": batch["material"],
                    "section_triangles": batch["triangles"],
                    "source_material": material_index,
                    "source_triangles": len(chunk),
                    "shader_id": material.shader_id,
                })
            for triangle_index in chunk:
                covered[material.surfaces[triangle_index]] = (batch_index, material_index, material.shader_id)
            batch_index += 1
    if batch_index != len(section.batches):
        issues.append({
            "kind": "bsps-batch-sequence",
            "reconstructed_batches": batch_index,
            "section_batches": len(section.batches),
        })
    return covered, issues


def compare_bsps(image: bytes, location, parsed: ParsedBsp) -> dict:
    issues = []
    summary = bsp.summarise(location, image)
    if summary.problems:
        issues.append({"kind": "halo2ps2-summary", "problems": list(summary.problems)})
    if summary.counts.get("surfaces") != parsed.surface_count or summary.counts.get("lightmaps") != parsed.lightmap_count:
        issues.append({
            "kind": "halo2ps2-counts",
            "summary_surfaces": summary.counts.get("surfaces"),
            "summary_lightmaps": summary.counts.get("lightmaps"),
            "raw_surfaces": parsed.surface_count,
            "raw_lightmaps": parsed.lightmap_count,
        })
    materials, bounds = bspconv.read_materials(image, location)
    kept = [item for item in parsed.materials if item.count > 0 and item.rendered_vertices > 0]
    if len(materials) != len(kept):
        issues.append({"kind": "bsps-material-count", "raw_kept": len(kept), "bsps_reader": len(materials)})
    for index, (raw, converted) in enumerate(zip(kept, materials)):
        if converted.shader_id != raw.shader_id:
            issues.append({
                "kind": "bsps-shader",
                "material_ordinal": index,
                "lightmap": raw.lightmap,
                "material": raw.material,
                "raw_shader_id": raw.shader_id,
                "bsps_shader_id": converted.shader_id,
            })
        expected_page = raw.bitmap if raw.lightmap_vertices else bspconv.NO_LIGHTMAP
        if converted.lightmap_page != expected_page:
            issues.append({
                "kind": "bsps-lightmap-page",
                "material_ordinal": index,
                "lightmap": raw.lightmap,
                "material": raw.material,
                "raw_bitmap": raw.bitmap,
                "raw_lightmap_vertices": raw.lightmap_vertices,
                "bsps_page": converted.lightmap_page,
            })
        expected_surfaces = list(range(raw.first, raw.first + raw.count))
        if converted.surfaces != expected_surfaces:
            issues.append({
                "kind": "bsps-surface-span",
                "material_ordinal": index,
                "lightmap": raw.lightmap,
                "material": raw.material,
                "raw_first": raw.first,
                "raw_count": raw.count,
                "bsps_count": len(converted.surfaces),
                "bsps_first": converted.surfaces[0] if converted.surfaces else None,
                "bsps_last": converted.surfaces[-1] if converted.surfaces else None,
            })
        for surface_id, triangle in zip(converted.surfaces, converted.tris):
            if not 0 <= surface_id < parsed.surface_count:
                issues.append({"kind": "bsps-surface-id", "surface": surface_id, "shader_id": converted.shader_id})
                continue
            raw_triangle = struct.unpack_from("<3H", parsed.surfaces, surface_id * 6)
            if tuple(raw_triangle) != tuple(triangle):
                issues.append({
                    "kind": "bsps-triangle",
                    "surface": surface_id,
                    "raw_indices": list(raw_triangle),
                    "bsps_indices": list(triangle),
                    "shader_id": raw.shader_id,
                })
    structure = bsp.read_structure(location, image)
    section_bytes = bspconv.build_section(materials, bounds, structure)
    section = bspconv.parse_section(section_bytes)
    for index, (converted, record) in enumerate(zip(materials, section.materials)):
        if record["shader_id"] != converted.shader_id:
            issues.append({
                "kind": "bsps-section-shader",
                "material_ordinal": index,
                "reader_shader_id": converted.shader_id,
                "section_shader_id": record["shader_id"],
                "section_triangles": record["triangles"],
            })
    covered, batch_issues = map_batches(materials, structure, section)
    issues.extend(batch_issues)
    owner = {}
    for material in parsed.materials:
        for surface in range(material.first, material.first + material.count):
            if 0 <= surface < parsed.surface_count:
                owner[surface] = material
    dropped = []
    referenced_dropped = []
    for converted in materials:
        for surface_id in converted.surfaces:
            found = covered.get(surface_id)
            if found is None:
                routes = sorted(structure.cluster_surfaces.get(surface_id, ()))
                raw_material = owner.get(surface_id)
                record = {
                    "surface": surface_id,
                    "lightmap": None if raw_material is None else raw_material.lightmap,
                    "material": None if raw_material is None else raw_material.material,
                    "shader_id": None if raw_material is None else raw_material.shader_id,
                    "group": None if raw_material is None else raw_material.group[::-1].decode("ascii", "replace"),
                    "first": None if raw_material is None else raw_material.first,
                    "count": None if raw_material is None else raw_material.count,
                    "cluster_routes": routes,
                }
                if routes:
                    referenced_dropped.append(record)
                else:
                    dropped.append(record)
                continue
            _batch, material_index, shader_id = found
            raw_material = owner.get(surface_id)
            if raw_material is None or raw_material.shader_id != shader_id:
                issues.append({
                    "kind": "bsps-surface-shader",
                    "surface": surface_id,
                    "batch_shader_id": shader_id,
                    "raw_shader_id": None if raw_material is None else raw_material.shader_id,
                    "raw_lightmap": None if raw_material is None else raw_material.lightmap,
                    "raw_material": None if raw_material is None else raw_material.material,
                    "bsps_material": material_index,
                })
    if referenced_dropped:
        issues.append({
            "kind": "bsps-dropped-referenced-surface",
            "count": len(referenced_dropped),
            "surfaces": [item["surface"] for item in referenced_dropped],
            "owners": referenced_dropped,
        })
    return {
        "issues": issues,
        "bytes": len(section_bytes),
        "sha256": sha256_bytes(section_bytes),
        "batches": len(section.batches),
        "triangles": section.triangles,
        "materials": len(section.materials),
        "dropped": len(referenced_dropped),
        "unreferenced": dropped,
    }


def compare_texs(map_path: Path, parsed: ParsedBsp) -> dict:
    converted = texconv.convert_map(map_path, lightmaps=False)
    pack = hp2.parse(converted.pack)
    if "TEXS" not in [section.tag for section in pack.sections]:
        raise texconv.TexError("converter pack has no TEXS section")
    view = texconv.parse_texs(pack.read("TEXS"))
    bindings = {binding["shader_id"]: binding for binding in view.bindings}
    raw_ids = []
    issues = []
    for material in parsed.materials:
        if material.count <= 0 or material.rendered_vertices <= 0:
            continue
        raw_ids.append(material.shader_id)
        group_name = material.group[::-1].decode("ascii", "replace")
        binding = bindings.get(material.shader_id)
        if binding is None:
            issues.append({
                "kind": "texs-missing-shader",
                "lightmap": material.lightmap,
                "material": material.material,
                "shader_id": material.shader_id,
                "group": group_name,
            })
            continue
        expected_group = texconv.GROUP_CODES.get(group_name)
        if expected_group is None or binding["group"] != expected_group:
            issues.append({
                "kind": "texs-group",
                "shader_id": material.shader_id,
                "raw_group": group_name,
                "expected_code": expected_group,
                "texs_group": binding["group"],
                "texture": binding["texture"],
            })
    extra = sorted(set(bindings) - set(raw_ids))
    if extra:
        issues.append({"kind": "texs-extra-shader", "shader_ids": extra})
    opened = texconv.MapData.open(map_path)
    untextured = []
    unexpected = []
    for binding in view.bindings:
        if binding["texture"] != texconv.NO_TEXTURE:
            continue
        info = texconv.resolve_shader(opened, binding["shader_id"])
        record = {
            "shader_id": binding["shader_id"],
            "group": binding["group"],
            "texture": binding["texture"],
            "group_name": info.group,
            "path": info.path,
            "note": info.note,
        }
        untextured.append(record)
        if info.note != "no base map":
            unexpected.append(record)
    if unexpected:
        issues.append({"kind": "texs-untextured", "bindings": unexpected})
    return {
        "issues": issues,
        "bindings": len(view.bindings),
        "textures": len(view.textures),
        "untextured": len(untextured),
        "bytes": len(pack.read("TEXS")),
        "sha256": sha256_bytes(pack.read("TEXS")),
    }


def execute_ce(executable: Path, image: bytes, relocations, tag_relocations,
               lightmap_count: int, mat0_first: int, mat0_count: int,
               queries: list[int], work: Path) -> tuple[int, str, dict | None]:
    fixture = work / "fixture.bin"
    results_path = work / "results.bin"
    write_fixture(fixture, image, relocations, tag_relocations, queries,
                  lightmap_count, mat0_first, mat0_count)
    completed = subprocess.run(
        [str(executable), "fixture", str(fixture), str(results_path)],
        capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    parsed = None
    if results_path.exists():
        parsed = read_results(results_path)
    return completed.returncode, output.rstrip(), parsed


def count_kind(issues: list[dict], kinds: set[str]) -> int:
    total = 0
    for issue in issues:
        if issue.get("kind") in kinds:
            total += issue.get("count", 1)
    return total


def audit_map(name: str, executable: Path, log: list[str]) -> dict:
    map_path = SOURCE_DIR / f"{name}.map"
    package_path = PACKAGE_DIR / f"{name}.hp2"
    source_hash = sha256_file(map_path)
    package_hash = sha256_file(package_path)
    issues = []
    if source_hash != MAP_SHA256[name]:
        issues.append({"kind": "source-hash", "actual": source_hash, "pinned": MAP_SHA256[name]})
    if package_hash != PACKAGE_SHA256[name]:
        issues.append({"kind": "package-hash", "actual": package_hash, "pinned": PACKAGE_SHA256[name]})
    index, location, raw_image, raw = load_raw(map_path)
    tags_by_id = {entry.tag_id: entry for entry in index.entries}
    issues.extend(interval_and_vertex_issues(raw, tags_by_id))
    package = hp2.parse(package_path.read_bytes())
    sections = [section.tag for section in package.sections]
    for tag in sections:
        if tag in ("BSPS", "TEXS") or tag.startswith("LM"):
            issues.append({"kind": "unexpected-package-section", "tag": tag})
    payload = package.read("B000")
    published = cbsp.decode(payload, max_image_size=32 * 1024 * 1024)
    if published.source_file_offset != location.file_offset or published.source_file_size != location.size:
        issues.append({
            "kind": "cbsp-source-extent",
            "package_offset": published.source_file_offset,
            "package_size": published.source_file_size,
            "raw_offset": location.file_offset,
            "raw_size": location.size,
        })
    if published.image != payload[cbsp.HEADER.size:cbsp.HEADER.size + len(published.image)]:
        issues.append({"kind": "cbsp-decode-image"})
    published_parsed = parse_bsp(published.image, 0)
    issues.extend(compare_published(raw, published_parsed))
    bsps = compare_bsps(raw_image, location, raw)
    issues.extend(bsps["issues"])
    texs = compare_texs(map_path, raw)
    issues.extend(texs["issues"])
    queries = list(range(raw.surface_count))
    endpoints = []
    for material in raw.materials:
        if material.count > 0:
            endpoints.extend((
                material.first,
                material.first + material.count // 2,
                material.first + material.count - 1,
            ))
    mat0_first = raw.materials[0].first if raw.materials else -1
    mat0_count = raw.materials[0].count if raw.materials else -1
    relocation_fields = set(published.relocations)
    missing_relocations = [field for field in published_parsed.followed_pointers if field not in relocation_fields]
    if 0 not in relocation_fields:
        missing_relocations.append(0)
    if any(value != 0 for value in raw.lightmap_definitions) or raw.lightmap_definition != 0:
        code, output, ce = 0, "skipped CE call because a lightmap definition pointer is nonzero", None
        issues.append({"kind": "ce-skipped", "reason": "nonzero-lightmap-definition"})
    elif missing_relocations:
        issues.append({
            "kind": "cbsp-pointer-not-relocated",
            "count": len(missing_relocations),
            "fields": missing_relocations[:16],
        })
        code, output, ce = 0, "skipped CE call because a followed pointer is not relocated", None
    else:
        work = OUT / name
        work.mkdir(parents=True, exist_ok=True)
        code, output, ce = execute_ce(
            executable, published.image, published.relocations, published.tag_relocations,
            published_parsed.lightmap_count, mat0_first, mat0_count, queries, work)
    if output:
        log.append(f"{name}: {output}")
    if code != 0:
        issues.append({"kind": "ce-exit", "code": code, "output": output[-2000:]})
    bytes_unchanged = 0
    depth_before = None
    depth_after = None
    ce_rows = []
    if ce is not None:
        bytes_unchanged = ce["bytes_unchanged"]
        depth_before = ce["depth_before"]
        depth_after = ce["depth_after"]
        ce_rows = ce["rows"]
        if ce["fnv_before"] != fnv1a(published.image) or ce["fnv_after"] != ce["fnv_before"]:
            issues.append({
                "kind": "published-bytes",
                "fnv_before": ce["fnv_before"],
                "fnv_after": ce["fnv_after"],
                "oracle_fnv": fnv1a(published.image),
            })
        if ce["bytes_unchanged"] != 1:
            issues.append({"kind": "published-bytes", "bytes_unchanged": ce["bytes_unchanged"]})
        if ce["depth_before"] != 0 or ce["depth_after"] != 0:
            issues.append({
                "kind": "collision-user-depth",
                "before": ce["depth_before"],
                "after": ce["depth_after"],
            })
        if ce["slow_path"] != 0:
            issues.append({"kind": "tag-block-slow-path", "calls": ce["slow_path"]})
        if ce["seen_lightmaps"] != raw.lightmap_count:
            issues.append({
                "kind": "ce-lightmap-count",
                "ce": ce["seen_lightmaps"],
                "raw": raw.lightmap_count,
            })
        issues.extend(compare_ce(raw, queries, ce_rows))
    bounds_probes = []
    if code == 0 and ce is not None and raw.surface_count >= 0:
        for label, query in (("before", -1), ("after", raw.surface_count)):
            probe_dir = work / f"bounds-{label}"
            probe_dir.mkdir(parents=True, exist_ok=True)
            probe_code, probe_output, probe = execute_ce(
                executable, published.image, published.relocations, published.tag_relocations,
                published_parsed.lightmap_count, mat0_first, mat0_count, [query], probe_dir)
            entry = {"label": label, "query": query, "code": probe_code}
            if probe_code == 11:
                entry["assert"] = probe_output.strip()
                issues.append({
                    "kind": "ce-bounds-assert",
                    "query": query,
                    "assert": entry["assert"],
                })
            elif probe is not None and probe["rows"]:
                found, lightmap, material = probe["rows"][0]
                entry.update({
                    "found": found,
                    "lightmap": lightmap,
                    "material": material,
                    "bytes_unchanged": probe["bytes_unchanged"],
                    "depth_before": probe["depth_before"],
                    "depth_after": probe["depth_after"],
                })
                if found:
                    issues.append({
                        "kind": "ce-mismatch",
                        "surface": query,
                        "ce_found": found,
                        "ce_lightmap": lightmap,
                        "ce_material": material,
                        "oracle": "out-of-range",
                    })
                if probe["bytes_unchanged"] != 1 or probe["depth_before"] != 0 or probe["depth_after"] != 0:
                    issues.append({
                        "kind": "bounds-probe-state",
                        "query": query,
                        "bytes_unchanged": probe["bytes_unchanged"],
                        "depth_before": probe["depth_before"],
                        "depth_after": probe["depth_after"],
                    })
            else:
                issues.append({
                    "kind": "bounds-probe",
                    "query": query,
                    "code": probe_code,
                    "output": probe_output[-500:],
                })
            bounds_probes.append(entry)
            if probe_output and probe_code not in (0, 11):
                log.append(f"{name} bounds {query}: {probe_output}")
    package_after = sha256_file(package_path)
    if package_after != package_hash:
        issues.append({"kind": "package-file-changed", "before": package_hash, "after": package_after})
    groups = Counter(material.group[::-1].decode("ascii", "replace") for material in raw.materials)
    endpoint_mismatches = 0
    if ce_rows:
        by_surface = {surface: row for surface, row in zip(queries, ce_rows)}
        oracle = owners_for(raw)
        for surface in endpoints:
            found, lightmap, material = by_surface[surface]
            owned = oracle.get(surface, [])
            if not (len(owned) == 1 and found and lightmap == owned[0].lightmap and material == owned[0].material):
                endpoint_mismatches += 1
    raw_empty = raw.surface_count == 0 and len(raw.materials) == 0 and raw.lightmap_count == 0
    if raw_empty:
        issues = [issue for issue in issues if issue["kind"] != "uncovered-surfaces"]
        issues.append({
            "kind": "raw-empty",
            "detail": "raw-source-proven empty: zero lightmaps, materials, and surfaces",
        })
    row = {
        "map": name,
        "bsp_path": location.path,
        "source_sha256": source_hash,
        "package_sha256": package_hash,
        "package_hash_unchanged": package_after == package_hash,
        "raw_bsp_sha256": sha256_bytes(raw_image),
        "cbsp_sha256": sha256_bytes(published.image),
        "package_sections": sections,
        "surfaces": raw.surface_count,
        "lightmaps": raw.lightmap_count,
        "materials": len(raw.materials),
        "shaders": len({material.shader_id for material in raw.materials}),
        "groups": dict(groups),
        "queries": len(queries),
        "endpoint_queries": len(endpoints),
        "bounds_probes": bounds_probes,
        "endpoint_mismatches": endpoint_mismatches,
        "ce_hits": sum(1 for found, _lightmap, _material in ce_rows if found),
        "bytes_unchanged": bytes_unchanged,
        "collision_user_depth_before": depth_before,
        "collision_user_depth_after": depth_after,
        "raw_empty": raw_empty,
        "bsps_bytes": bsps["bytes"],
        "bsps_sha256": bsps["sha256"],
        "bsps_batches": bsps["batches"],
        "bsps_triangles": bsps["triangles"],
        "bsps_materials": bsps["materials"],
        "bsps_dropped": bsps["dropped"],
        "bsps_unreferenced": [item["surface"] for item in bsps["unreferenced"]],
        "texs_bindings": texs["bindings"],
        "texs_textures": texs["textures"],
        "texs_untextured": texs["untextured"],
        "texs_bytes": texs["bytes"],
        "texs_sha256": texs["sha256"],
        "issues": issues,
    }
    row["ce_mismatches"] = count_kind(issues, {
        "ce-mismatch", "ce-exit", "ce-result-length", "ce-lightmap-count", "ce-bounds-assert",
    })
    row["vertex_faults"] = count_kind(issues, {"vertex-index"})
    row["interval_faults"] = count_kind(issues, {
        "header-material-count", "empty-lightmap", "material-range", "unsorted-material",
        "overlap-material", "overlap-lightmap", "uncovered-surfaces", "multi-owned-surfaces",
        "empty-material", "shader-unresolved", "shader-group", "lightmap-definition",
        "material-definition", "surface-definition", "halo2ps2-summary", "halo2ps2-counts",
    })
    row["bsps_shader_mismatches"] = count_kind(issues, {
        "bsps-shader", "bsps-section-shader", "bsps-surface-shader", "bsps-material-count",
        "bsps-surface-span", "bsps-triangle", "bsps-batch-identity", "bsps-batch-sequence",
        "bsps-lightmap-page", "bsps-dropped-referenced-surface", "bsps-surface-id",
    })
    row["texs_mismatches"] = count_kind(issues, {
        "texs-missing-shader", "texs-group", "texs-extra-shader", "texs-untextured",
    })
    row["cbsp_field_mismatches"] = count_kind(issues, {
        "cbsp-block-count", "cbsp-surface-bytes", "cbsp-material-count", "cbsp-material-field",
        "cbsp-source-extent", "cbsp-decode-image",
    })
    log.append(
        f"{name}: surfaces={row['surfaces']} lightmaps={row['lightmaps']} materials={row['materials']} "
        f"queries={row['queries']} ce_hits={row['ce_hits']} issues={len(issues)} "
        f"dropped={row['bsps_dropped']} bytes_unchanged={bytes_unchanged}")
    return row


def render_report(payload: dict) -> str:
    lines = [
        "# Lightmap surface consumer",
        "",
        "Status: **" + payload["status"] + "**.",
        "",
        "CE `structure_bsp_find_material_for_surface` "
        "(`source/structures/structure_bsp_definitions.c`, the pinned body spliced verbatim) "
        "ran ILP32 on a relocated copy of each map's published `B000` CBSP image. "
        "The oracle is a separate linear read of the raw decompressed Xbox BSP: material "
        "surface intervals, shader tag references, and `surfaces[].vertex_indices` against "
        "each material's rendered vertex count. Queries are every surface index in range. "
        "First, middle, and last of each material interval are included in that set. "
        "Index -1 and the index equal to the surface count are separate probes.",
        "",
        "Capacity packages contain `CTAG`, `CRNG`, `HMAP`, `B000`, and `CBIX`. They do not "
        "contain `BSPS` or `TEXS`. Shader and batch identity is compared with BSPS v2 and TEXS "
        "built by `submodules/halo-ps2/tools/halo2ps2` (`bspconv`, `texconv`) from the same raw BSP. "
        "Every examined lightmap, material, shader reference, surface, and vertex field stays "
        "retained. This audit does not authorize stripping any of them, and it does not claim "
        "PCSX2, GS, VU, or SPU2 output.",
        "",
        f"Synthetic empty lightmap block: `{payload['empty']}`.",
        "",
        "| map | surfaces | lightmaps | materials | shaders | queries | CE hits | endpoint faults | vertex faults | interval faults | BSPS faults | BSPS dropped | TEXS faults | CBSP faults | bytes | depth |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["maps"]:
        lines.append(
            f"| {row['map']} | {row['surfaces']} | {row['lightmaps']} | {row['materials']} | "
            f"{row['shaders']} | {row['queries']} | {row['ce_hits']} | {row['endpoint_mismatches']} | "
            f"{row['vertex_faults']} | {row['interval_faults']} | {row['bsps_shader_mismatches']} | "
            f"{row['bsps_dropped']} | {row['texs_mismatches']} | {row['cbsp_field_mismatches']} | "
            f"{row['bytes_unchanged']} | {row['collision_user_depth_before']}->{row['collision_user_depth_after']} |"
        )
    lines.extend(["", "## Groups", ""])
    for row in payload["maps"]:
        groups = ", ".join(f"{name} {count}" for name, count in sorted(row["groups"].items()))
        lines.append(
            f"- `{row['map']}` `{row['bsp_path']}`: {groups}; "
            f"BSPS batches {row['bsps_batches']}, triangles {row['bsps_triangles']}, "
            f"materials {row['bsps_materials']}, unreferenced {row['bsps_unreferenced'] or 'none'}; "
            f"TEXS bindings {row['texs_bindings']}, "
            f"untextured {row['texs_untextured']}; sections {', '.join(row['package_sections'])}."
        )
    lines.extend(["", "## Out-of-range probes", ""])
    for row in payload["maps"]:
        parts = []
        for probe in row.get("bounds_probes", []):
            if probe.get("code") == 11:
                parts.append(f"query {probe['query']} checked assert `{probe.get('assert', '')}`")
            else:
                parts.append(
                    f"query {probe['query']} code {probe.get('code')} found {probe.get('found')} "
                    f"lightmap {probe.get('lightmap')} material {probe.get('material')}"
                )
        lines.append(f"- `{row['map']}`: " + "; ".join(parts))
    lines.extend(["", "## Issues", ""])
    if payload["issues"]:
        for issue in payload["issues"]:
            lines.append(f"- `{json.dumps(issue, sort_keys=True)}`")
    else:
        lines.append("Provable issues: none.")
    lines.extend([
        "",
        "## Limits",
        "",
        "- The collision-user value is a local sentinel in this harness. The fixture does not link CE collision or publish a BSP through `scenario_switch_structure_bsp`, so it does not observe that stack. The sentinel stays 0, and the published CBSP bytes (collision records included) are checksum-compared before and after the queries.",
        "- CE's search reads lightmap and material interval fields only. Vertex indices and shader references are oracle and pack checks, not return values of this function.",
        "- A surface index of -1 is not a retail surface. The port returns FALSE when the query is before the settled lightmap's first material, so the Xbox `match_assert` is not reached. Those probes run in their own process. In-range surfaces are a separate call.",
        "- BSPS omits a surface that neither a leaf nor a subcluster lists (`08-bsp-section.md`). That documented omission is counted under `bsps_unreferenced`, not as a converter fault. A listed/referenced surface absent from batches remains an issue.",
        "- TEXS bindings are converter output for shader identity, not a section stored in the capacity package and not GS upload evidence. An `senv` with no base map uses its self-illumination bitmap when present.",
        "- No retail map in this set was an empty lightmap/material/surface BSP. An empty result would be reported from the raw counts rather than omitted.",
        "",
        "## Pins and hashes",
        "",
    ])
    for key, value in payload["hashes"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    log = [
        f"parent {git_head(ROOT)}",
        f"hcu {git_head(HCU)}",
        f"halo-ps2 {git_head(ROOT / 'submodules/halo-ps2')}",
        f"source_dir {SOURCE_DIR}",
        f"package_dir {PACKAGE_DIR}",
    ]
    executable, body = compile_harness(log)
    empty = subprocess.run([str(executable), "empty"], capture_output=True, text=True)
    log.append("empty " + (empty.stdout or "").rstrip() + (empty.stderr or "").rstrip())
    if empty.returncode != 0:
        raise RuntimeError("synthetic empty lightmap call failed: " + (empty.stderr or empty.stdout or ""))
    maps = []
    global_issues = []
    for name in MP_MAPS:
        try:
            maps.append(audit_map(name, executable, log))
        except Exception as exc:
            log.append(traceback.format_exc())
            global_issues.append({"kind": "audit-exception", "map": name, "error": f"{type(exc).__name__}: {exc}"})
    for row in maps:
        global_issues.extend({"map": row["map"], **issue} for issue in row["issues"] if issue["kind"] != "raw-empty")
    status = "PASS" if not global_issues and len(maps) == len(MP_MAPS) else "ISSUES"
    if any(issue["kind"] == "audit-exception" for issue in global_issues):
        status = "ISSUES"
    log_path = OUT / "run.log"
    log_path.write_text("\n".join(log) + "\n", encoding="utf-8")
    payload = {
        "status": status,
        "empty": (empty.stdout or "").strip(),
        "maps": maps,
        "issues": global_issues,
        "ce_function_sha256": sha256_bytes(body.encode("utf-8")),
        "hashes": {
            "ce_source": sha256_file(CE_SOURCE),
            "harness": sha256_file(HARNESS),
            "audit_tool": sha256_file(Path(__file__).resolve()),
            "pytest": sha256_file(ROOT / "tests/test_hcu_mp_lightmap_surface_consumer.py"),
            "generated_c": sha256_file(OUT / "lightmap_surface_consumer_generated.c"),
            "executable": sha256_file(executable),
            "log": sha256_file(log_path),
            "ce_function": sha256_bytes(body.encode("utf-8")),
        },
    }
    pytest_path = ROOT / "tests/test_hcu_mp_lightmap_surface_consumer.py"
    if pytest_path.exists():
        payload["hashes"]["pytest"] = sha256_file(pytest_path)
    (OUT / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "report.md").write_text(render_report(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        payload = run()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        blocked = OUT / "run.log"
        blocked.write_text(traceback.format_exc(), encoding="utf-8")
        (OUT / "report.md").write_text(
            "# Lightmap surface consumer\n\nStatus: **BLOCKED**.\n\n"
            f"`{type(exc).__name__}: {exc}`\n\n"
            "Every examined field stays retained. This audit does not authorize stripping any of them, "
            "and it does not claim PCSX2, GS, VU, or SPU2 output.\n",
            encoding="utf-8")
        print(f"BLOCKED {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(payload["status"])
    for row in payload["maps"]:
        print(
            f"{row['map']} surfaces={row['surfaces']} lightmaps={row['lightmaps']} "
            f"materials={row['materials']} issues={len(row['issues'])}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
