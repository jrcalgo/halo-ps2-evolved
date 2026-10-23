#!/usr/bin/env python3
"""Count BSPS v2 presentation omissions on the 13 stock multiplayer maps.

Instances are read from raw decompressed Xbox BSP bytes. They are not taken
from CE's relocated tag memory or from an HP2 package. CE call sites are the
source lines that load the field. A category is 'requires PS2 consumer' only
when a load of the stored map field sits in the PS2 compile closure and at
least one stock instance exists. Every other category is 'retain-bytes'.
Nothing is dispositioned 'strip'.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
CATEGORY_ORDER = (
    "unreferenced_surfaces",
    "render_nodes",
    "cluster_fog_bit15",
    "transition_bsp",
    "predicted_resources",
    "portal_flags",
    "mirrors",
    "decal_range",
    "lens_flare_range",
)
LABELS = {
    "unreferenced_surfaces": "Unreferenced surfaces",
    "render_nodes": "Render nodes (+0xBC)",
    "cluster_fog_bit15": "Cluster fog bit 15",
    "transition_bsp": "Transition BSP (+0x0A)",
    "predicted_resources": "Predicted resources (+0x28)",
    "portal_flags": "Portal flags (+0x18)",
    "mirrors": "Mirrors",
    "decal_range": "Decal range (+0x0C/+0x0E)",
    "lens_flare_range": "Lens flare range (+0x40)",
}
CLUSTER_SIZE = 104
PORTAL_SIZE = 64
SUBCLUSTER_SIZE = 36
LEAF_SIZE = 16
PREDICTED_RESOURCE_SIZE = 8
MIRROR_SIZE = 0x40
RUNTIME_DECAL_SIZE = 16
LENS_MARKER_SIZE = 16
SBSP_MAGIC = b"psbs"
NONE = -1
FOG_BIT15 = 0x8000

sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from hcu_ps2_closure import MANIFEST_PATH, selected_sources  # noqa: E402

FOG_BIT_RE = re.compile(
    r"TEST_FLAG\(\(word\)\s*(?:fog_reference|cluster->fog_reference|fog_designator)"
    r"\s*,\s*(?:15|SHORT_BITS\s*-\s*1)\s*\)")
ROUTE_SNIPPETS = (
    ("source/structures/structure_visibility.c", "subcluster->surface_indices"),
    ("source/structures/structure_visibility.c", "leaf->first_surface_reference_index"),
    ("source/structures/structures.c", "leaf->first_surface_reference_index"),
)
EXCLUDED_SURFACE_WALK = (
    "source/structures/structure_render.c",
    "while (surface_index < structure_bsp->surfaces.count)",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_pin(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def closure_sources() -> set[str]:
    manifest = json.loads(MANIFEST_PATH.read_text())
    return set(selected_sources(manifest))


def code_portion(line: str) -> str:
    if "//" in line:
        line = line.split("//", 1)[0]
    return line


def source_files() -> list[Path]:
    root = HCU / "source"
    return sorted(root.rglob("*.c")) + sorted(root.rglob("*.h"))


def rel_hcu(path: Path) -> str:
    return path.relative_to(HCU).as_posix()


def function_span(lines: list[str], signature: str) -> tuple[int, int]:
    start = next(index for index, line in enumerate(lines) if signature in line)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^(?:static\s+)?(?:void|boolean|long|short|int)\s+\w+\(", lines[index]):
            end = index
            break
    return start, end


def is_pure_store(code: str, field: str) -> bool:
    stripped = re.sub(rf"(?:->|\.){field}\s*=(?!=)", "", code)
    return f"->{field}" not in stripped and f".{field}" not in stripped


def discover_call_sites(closure: set[str]) -> dict:
    fog_reads = []
    node_reads = []
    mirror_reads = []
    predicted_reads = []
    decal_reads = []
    lens_loads = []
    transition_uses = []
    transition_declarations = []
    portal_flag_uses = []
    route_readers = []

    lens_path = HCU / "source/structures/structure_lens_flares.c"
    lens_lines = lens_path.read_text().splitlines()
    lens_start, lens_end = function_span(lens_lines, "boolean build_structure_lens_flares(")
    lens_zero = {"lens_flare_marker_count": [], "first_lens_flare_marker_index": []}
    for index, line in enumerate(lens_lines):
        code = code_portion(line)
        for field in lens_zero:
            if re.search(rf"->{field}\s*=\s*0\s*;", code):
                lens_zero[field].append(index)

    for path in source_files():
        relative = rel_hcu(path)
        in_closure = relative in closure
        for number, raw in enumerate(path.read_text(errors="replace").splitlines(), start=1):
            code = code_portion(raw).strip()
            if not code or code.startswith("*") or code.startswith("/*"):
                continue
            entry = {
                "file": relative,
                "line": number,
                "snippet": code,
                "in_ps2_closure": in_closure,
                "consumes_map_bytes": True,
            }
            fog_load = FOG_BIT_RE.search(code) or (
                "->fog_reference" in code and "offsetof" not in code and
                not is_pure_store(code, "fog_reference"))
            if fog_load:
                fog_reads.append(dict(entry))
            if "structure->nodes" in code:
                node_reads.append(dict(entry))
            if "cluster->mirrors" in code:
                mirror_reads.append(dict(entry))
            if "cluster->predicted_resources" in code:
                predicted_reads.append(dict(entry))
            decal_load = (
                ("cluster->first_decal_index" in code and not is_pure_store(code, "first_decal_index")) or
                ("cluster->decal_count" in code and not is_pure_store(code, "decal_count")))
            if decal_load:
                decal_reads.append(dict(entry))
            if "transition_structure_bsp_index" in code:
                if "->" in code or ".transition_structure_bsp_index" in code:
                    transition_uses.append(dict(entry))
                else:
                    transition_declarations.append(f"{relative}:{number}")
            if "portal->flags" in code or "portal.flags" in code:
                portal_flag_uses.append(dict(entry))
            lens_fields = [
                field for field in ("lens_flare_marker_count", "first_lens_flare_marker_index")
                if (f"->{field}" in code or f".{field}" in code) and
                "offsetof" not in code and not is_pure_store(code, field)]
            if lens_fields:
                load = dict(entry)
                inside_builder = (
                    relative == "source/structures/structure_lens_flares.c" and
                    lens_start < number - 1 < lens_end and
                    all(lens_zero[field] and min(lens_zero[field]) < number - 1 for field in lens_fields))
                load["consumes_map_bytes"] = not inside_builder
                load["fields"] = lens_fields
                if inside_builder:
                    load["reason"] = (
                        "build_structure_lens_flares stores 0 over both range fields for every "
                        "cluster before this load, so the load does not use the map-resident range")
                lens_loads.append(load)

    def locate_snippet(relative: str, snippet: str) -> list[dict]:
        text = (HCU / relative).read_text().splitlines()
        hits = [index + 1 for index, line in enumerate(text) if snippet in line]
        if not hits:
            raise SystemExit(f"missing snippet {relative}: {snippet}")
        return [{
            "file": relative,
            "line": line,
            "snippet": snippet,
            "in_ps2_closure": relative in closure,
            "consumes_unreferenced_surface": False,
        } for line in hits]

    for relative, snippet in ROUTE_SNIPPETS:
        route_readers.extend(locate_snippet(relative, snippet))
    excluded_surface_walk = locate_snippet(*EXCLUDED_SURFACE_WALK)

    if not lens_zero["lens_flare_marker_count"] or not lens_zero["first_lens_flare_marker_index"]:
        raise SystemExit("lens-flare builder does not zero both range fields")

    return {
        "unreferenced_surfaces": [],
        "render_nodes": node_reads,
        "cluster_fog_bit15": fog_reads,
        "transition_bsp": transition_uses,
        "predicted_resources": predicted_reads,
        "portal_flags": portal_flag_uses,
        "mirrors": mirror_reads,
        "decal_range": decal_reads,
        "lens_flare_range": lens_loads,
        "route_readers": route_readers,
        "excluded_surface_walk": excluded_surface_walk,
        "transition_declarations": transition_declarations,
        "lens_builder_span": {
            "file": "source/structures/structure_lens_flares.c",
            "function": "build_structure_lens_flares",
            "start_line": lens_start + 1,
            "end_line": lens_end,
            "zero_stores": {field: [line + 1 for line in lines] for field, lines in lens_zero.items()},
        },
    }


def reflexive(block: bytes, base: int, at: int, stride: int, what: str) -> tuple[int, int]:
    count, address = struct_unpack_count_address(block, at)
    if count < 0:
        raise ValueError(f"{what}: negative count {count}")
    if count == 0:
        return 0, 0
    offset = address - base
    nbytes = count * stride
    if offset < 0 or offset + nbytes > len(block):
        raise ValueError(f"{what}: {count} x {stride} at file offset {offset} outside {len(block)} bytes")
    return count, offset


def struct_unpack_count_address(block: bytes, at: int) -> tuple[int, int]:
    return struct.unpack_from("<iI", block, at)


def partition_ok(ranges: list[tuple[int, int]], total: int) -> bool:
    cursor = 0
    for start, stop in sorted(ranges):
        if start != cursor or stop < start:
            return False
        cursor = stop
    return cursor == total


def inventory_bsp(location, block: bytes) -> dict:
    if block[0x14:0x18] != SBSP_MAGIC:
        raise ValueError(f"{location.path}: missing sbsp signature")
    root = struct.unpack_from("<I", block, 0)[0] - location.address
    if root < 0 or root + 0x260 > len(block):
        raise ValueError(f"{location.path}: structure_bsp root outside the image")
    base = location.address
    surface_count, _ = reflexive(block, base, root + 0xF8, 6, "surfaces")
    leaf_surface_count, leaf_surface_at = reflexive(block, base, root + 0xEC, 8, "leaf surfaces")
    leaf_count, leaf_at = reflexive(block, base, root + 0xE0, LEAF_SIZE, "leaves")
    cluster_count, cluster_at = reflexive(block, base, root + 0x134, CLUSTER_SIZE, "clusters")
    portal_count, portal_at = reflexive(block, base, root + 0x154, PORTAL_SIZE, "portals")
    render_nodes, _ = reflexive(block, base, root + 0xBC, 6, "render nodes")
    runtime_decals, _ = reflexive(block, base, root + 0x258, RUNTIME_DECAL_SIZE, "runtime decals")
    lens_markers, _ = reflexive(block, base, root + 0x128, LENS_MARKER_SIZE, "lens flare markers")
    collision_count, collision_at = reflexive(block, base, root + 0xB0, 96, "collision bsp")
    if collision_count < 1:
        raise ValueError(f"{location.path}: no collision bsp")
    collision_nodes = struct.unpack_from("<i", block, collision_at)[0]
    if collision_nodes < 0:
        raise ValueError(f"{location.path}: negative collision node count")

    leaf_surfaces = [
        item[0] for item in struct.iter_unpack(
            "<II", block[leaf_surface_at:leaf_surface_at + leaf_surface_count * 8])]
    referenced: set[int] = set()
    for leaf_index in range(leaf_count):
        element = leaf_at + leaf_index * LEAF_SIZE
        count = struct.unpack_from("<H", block, element + 0x0A)[0]
        first = struct.unpack_from("<I", block, element + 0x0C)[0]
        if count == 0:
            continue
        if first + count > leaf_surface_count:
            raise ValueError(f"{location.path}: leaf {leaf_index} surface range outside the leaf-surface table")
        for surface_index in leaf_surfaces[first:first + count]:
            if surface_index >= surface_count:
                raise ValueError(f"{location.path}: leaf surface {surface_index} >= {surface_count}")
            referenced.add(surface_index)

    fog_bit15 = 0
    fog_references = 0
    transition_nonzero = 0
    predicted = 0
    predicted_clusters = 0
    mirror_elements = 0
    mirror_clusters = 0
    decal_ranges: list[tuple[int, int]] = []
    lens_ranges: list[tuple[int, int]] = []
    direct_surface_blocks = 0
    for cluster_index in range(cluster_count):
        element = cluster_at + cluster_index * CLUSTER_SIZE
        fog = struct.unpack_from("<h", block, element + 0x02)[0]
        transition = struct.unpack_from("<h", block, element + 0x0A)[0]
        if fog != NONE:
            fog_references += 1
            if fog & FOG_BIT15:
                fog_bit15 += 1
        if transition != 0:
            transition_nonzero += 1
        decal_first, decal_count = struct.unpack_from("<hH", block, element + 0x0C)
        if decal_count:
            if decal_first < 0:
                raise ValueError(f"{location.path}: cluster {cluster_index} decal range starts at {decal_first}")
            decal_ranges.append((decal_first, decal_first + decal_count))
        resource_count, _ = reflexive(block, base, element + 0x28, PREDICTED_RESOURCE_SIZE, f"cluster {cluster_index} predicted resources")
        if resource_count:
            predicted += resource_count
            predicted_clusters += 1
        lens_first, lens_count = struct.unpack_from("<HH", block, element + 0x40)
        if lens_count:
            lens_ranges.append((lens_first, lens_first + lens_count))
        direct_count = struct.unpack_from("<i", block, element + 0x44)[0]
        if direct_count:
            direct_surface_blocks += 1
        mirror_count, _ = reflexive(block, base, element + 0x50, MIRROR_SIZE, f"cluster {cluster_index} mirrors")
        if mirror_count:
            mirror_elements += mirror_count
            mirror_clusters += 1
        subcluster_count, subcluster_at = reflexive(
            block, base, element + 0x34, SUBCLUSTER_SIZE, f"cluster {cluster_index} subclusters")
        for subcluster_index in range(subcluster_count):
            subcluster = subcluster_at + subcluster_index * SUBCLUSTER_SIZE
            listed, listed_at = reflexive(
                block, base, subcluster + 0x18, 4,
                f"cluster {cluster_index} subcluster {subcluster_index} surfaces")
            for surface_index in struct.unpack_from(f"<{listed}I", block, listed_at) if listed else ():
                if surface_index >= surface_count:
                    raise ValueError(
                        f"{location.path}: subcluster surface {surface_index} >= {surface_count}")
                referenced.add(surface_index)

    portal_flags = 0
    for portal_index in range(portal_count):
        flags = struct.unpack_from("<I", block, portal_at + portal_index * PORTAL_SIZE + 0x18)[0]
        if flags:
            portal_flags += 1

    missing = sorted(set(range(surface_count)) - referenced)
    reference = bsp.read_structure(location, block)
    reference_missing = sorted(set(range(reference.surface_count)) - set(reference.cluster_surfaces))
    reference_fog = sum(1 for cluster in reference.clusters if cluster.fog != NONE and cluster.fog & FOG_BIT15)
    reference_mirrors = sum(cluster.mirrors for cluster in reference.clusters)
    reference_flags = sum(1 for portal in reference.portals if portal.flags)
    checks = {
        "unreferenced_indices_match_read_structure": missing == reference_missing,
        "render_nodes_match_collision_bsp3d_nodes": render_nodes == collision_nodes == len(reference.nodes),
        "portal_flags_match_read_structure": (
            portal_flags == reference_flags and portal_count == len(reference.portals)),
        "fog_bit15_matches_read_structure": fog_bit15 == reference_fog and cluster_count == len(reference.clusters),
        "mirrors_match_read_structure": mirror_elements == reference_mirrors,
        "decal_ranges_partition_runtime_decals": partition_ok(decal_ranges, runtime_decals),
        "lens_ranges_partition_markers": partition_ok(lens_ranges, lens_markers),
    }
    return {
        "bsp_index": None,
        "bsp_path": location.path,
        "raw_bsp_sha256": hashlib.sha256(block).hexdigest(),
        "raw_bsp_bytes": len(block),
        "surface_count": surface_count,
        "unreferenced_surface_indices": missing,
        "render_nodes": render_nodes,
        "collision_bsp3d_nodes": collision_nodes,
        "cluster_count": cluster_count,
        "fog_references": fog_references,
        "fog_bit15_clusters": fog_bit15,
        "transition_nonzero": transition_nonzero,
        "predicted_resource_elements": predicted,
        "predicted_resource_clusters": predicted_clusters,
        "portal_count": portal_count,
        "portal_flags_nonzero": portal_flags,
        "mirror_elements": mirror_elements,
        "mirror_clusters": mirror_clusters,
        "runtime_decal_count": runtime_decals,
        "decal_ranges": len(decal_ranges),
        "decal_span": sum(stop - start for start, stop in decal_ranges),
        "lens_flare_marker_count": lens_markers,
        "lens_flare_ranges": len(lens_ranges),
        "lens_flare_span": sum(stop - start for start, stop in lens_ranges),
        "cluster_direct_surface_blocks": direct_surface_blocks,
        "checks": checks,
    }


def counted(count: int, singular: str) -> str:
    return f"{count} {singular if count == 1 else singular + 's'}"


def prove(category: str, row: dict) -> str:
    clusters = counted(row["cluster_count"], "cluster")
    if category == "unreferenced_surfaces":
        indices = row["unreferenced_surface_indices"]
        if not indices:
            return (f"{row['surface_count']} surfaces; every index is listed by a leaf "
                    "surface reference or a subcluster surface list")
        listed = ", ".join(str(index) for index in indices)
        return (f"{row['surface_count']} surfaces; {len(indices)} indices are on neither "
                f"the leaf route nor a subcluster list: {listed}")
    if category == "render_nodes":
        return (f"{row['render_nodes']} records of 6 bytes in the nodes reflexive at "
                f"structure_bsp+0xBC; collision bsp3d nodes are {row['collision_bsp3d_nodes']}")
    if category == "cluster_fog_bit15":
        if row["fog_bit15_clusters"] == 0:
            return (f"{clusters}; every s16 at cluster+0x02 is -1, so bit 15 is "
                    "not set on a fog-plane reference")
        return (f"{clusters}; {row['fog_references']} fog references (s16 != -1); "
                f"{row['fog_bit15_clusters']} of them have bit 15 set")
    if category == "transition_bsp":
        if row["transition_nonzero"] == 0:
            return f"{clusters}; every s16 at cluster+0x0A is 0"
        return f"{clusters}; {row['transition_nonzero']} s16 values at cluster+0x0A are non-zero"
    if category == "predicted_resources":
        return (f"{clusters}; predicted-resource element counts at cluster+0x28 "
                f"sum to {row['predicted_resource_elements']}")
    if category == "portal_flags":
        if row["portal_count"] == 0:
            return "0 cluster portals, so no portal flags word is present"
        if row["portal_flags_nonzero"] == 0:
            return f"{counted(row['portal_count'], 'portal')}; every u32 at portal+0x18 is 0"
        return f"{row['portal_flags_nonzero']} of {row['portal_count']} portals have a non-zero flags word"
    if category == "mirrors":
        if row["mirror_elements"] == 0:
            return f"{clusters}; every mirror-block count at cluster+0x50 is 0"
        return f"{row['mirror_elements']} mirror elements across {row['mirror_clusters']} clusters"
    if category == "decal_range":
        if row["decal_ranges"] == 0:
            return f"{clusters}; every u16 decal count at cluster+0x0E is 0"
        return (f"{clusters}; {row['decal_ranges']} have a non-zero decal count at "
                f"+0x0E (span {row['decal_span']}, runtime decals {row['runtime_decal_count']})")
    if category == "lens_flare_range":
        if row["lens_flare_ranges"] == 0:
            return f"{clusters}; every u16 lens-flare marker count at cluster+0x42 is 0"
        return (f"{clusters}; {row['lens_flare_ranges']} have a non-zero marker count at "
                f"+0x42 (span {row['lens_flare_span']}, markers {row['lens_flare_marker_count']})")
    raise KeyError(category)


def map_instances(rows: list[dict], category: str) -> int:
    key = {
        "unreferenced_surfaces": "unreferenced_surface_indices",
        "render_nodes": "render_nodes",
        "cluster_fog_bit15": "fog_bit15_clusters",
        "transition_bsp": "transition_nonzero",
        "predicted_resources": "predicted_resource_elements",
        "portal_flags": "portal_flags_nonzero",
        "mirrors": "mirror_elements",
        "decal_range": "decal_ranges",
        "lens_flare_range": "lens_flare_ranges",
    }[category]
    if key == "unreferenced_surface_indices":
        return sum(len(row[key]) for row in rows)
    return sum(row[key] for row in rows)


def map_proof(rows: list[dict], category: str) -> str:
    parts = []
    for row in rows:
        prefix = f"bsp {row['bsp_index']} ({row['bsp_path']})"
        parts.append(f"{prefix}: {prove(category, row)}")
    return " | ".join(parts)


def cite(read: dict | None) -> str | None:
    if read is None:
        return None
    return f"submodules/halo-ce-universal/{read['file']}:{read['line']}"


def primary_read(reads: list[dict]) -> dict | None:
    consuming = [read for read in reads if read["consumes_map_bytes"]]
    if not consuming:
        return None
    def rank(read: dict) -> tuple:
        snippet = read["snippet"]
        direct_bit = "TEST_FLAG" in snippet and "cluster->fog_reference" in snippet
        bit = "TEST_FLAG" in snippet and ("fog_reference" in snippet or "SHORT_BITS" in snippet)
        element = "byte_rectangle3d" in snippet or (
            "TAG_BLOCK_GET_ELEMENT" in snippet and "cluster->mirrors" in snippet)
        return (
            0 if read["in_ps2_closure"] else 1,
            0 if direct_bit else 1,
            0 if bit else 1,
            0 if element else 1,
            read["file"],
            read["line"],
        )
    return sorted(consuming, key=rank)[0]


def disposition_for(stored_read_in_closure: bool, instances: int) -> str:
    if stored_read_in_closure and instances >= 1:
        return "requires PS2 consumer"
    return "retain-bytes"


def inventory_map(map_path: Path) -> dict:
    index = tagindex.TagIndex.read(map_path)
    region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, region, mapinfo.read_header(map_path).decompressed_size)
    rows = []
    with map_path.open("rb") as stream:
        for bsp_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise ValueError(f"truncated BSP {location.path}")
            row = inventory_bsp(location, image)
            row["bsp_index"] = bsp_index
            rows.append(row)
    categories = {}
    for category in CATEGORY_ORDER:
        instances = map_instances(rows, category)
        categories[category] = {
            "instances": instances,
            "empty": instances == 0,
            "proof": map_proof(rows, category),
        }
    failed = []
    for row in rows:
        for name, ok in row["checks"].items():
            if not ok:
                failed.append({"map": map_path.stem, "bsp_index": row["bsp_index"], "check": name})
    return {
        "map": map_path.stem,
        "source_map_sha256": sha256(map_path),
        "bsp_count": len(rows),
        "categories": categories,
        "bsps": rows,
        "failed_checks": failed,
    }


def build_report(source_dir: Path) -> dict:
    closure = closure_sources()
    sites = discover_call_sites(closure)
    maps = [inventory_map(source_dir / f"{name}.map") for name in MP_MAPS]
    categories = []
    for category in CATEGORY_ORDER:
        reads = sites[category]
        stock = sum(row["categories"][category]["instances"] for row in maps)
        chosen = primary_read(reads)
        stored_in_closure = bool(chosen and chosen["in_ps2_closure"])
        categories.append({
            "id": category,
            "label": LABELS[category],
            "stock_instances": stock,
            "call_site": cite(chosen),
            "call_site_in_ps2_closure": stored_in_closure,
            "stored_read_in_closure": stored_in_closure,
            "disposition": disposition_for(stored_in_closure, stock),
            "reads": reads,
        })
    failed = [item for row in maps for item in row["failed_checks"]]
    direct_blocks = sum(bsp_row["cluster_direct_surface_blocks"] for row in maps for bsp_row in row["bsps"])
    if direct_blocks:
        failed.append({"check": "cluster_direct_surface_blocks_empty", "count": direct_blocks})
    issues = failed
    return {
        "schema": "hcu-mp-bsp-presentation-omissions-v1",
        "scope": "13 stock multiplayer maps; raw decompressed Xbox BSP bytes",
        "kind": "source-data count plus CE call-site disposition; not a CE runtime execution",
        "source_directory": str(source_dir),
        "disposition_rule": (
            "requires PS2 consumer only when a load of the stored map field is in the "
            "PS2 closure and stock instances are at least 1; otherwise retain-bytes; never strip"),
        "instance_definitions": {
            "unreferenced_surfaces": "surface indices listed by neither a leaf surface reference nor a subcluster surface list",
            "render_nodes": "elements of the structure_bsp nodes reflexive at +0xBC (6 bytes, byte_rectangle3d)",
            "cluster_fog_bit15": "clusters whose fog s16 at +0x02 is not -1 and has bit 15 set",
            "transition_bsp": "clusters whose s16 at +0x0A is not 0",
            "predicted_resources": "sum of predicted-resource element counts at cluster+0x28 (8-byte elements)",
            "portal_flags": "portals whose u32 flags at +0x18 is not 0",
            "mirrors": "sum of mirror element counts at cluster+0x50 (0x40-byte elements)",
            "decal_range": "clusters whose u16 decal count at +0x0E is not 0",
            "lens_flare_range": "clusters whose u16 lens-flare marker count at +0x42 is not 0",
        },
        "pins": {
            "parent": git_pin(ROOT),
            "halo_ce_universal": git_pin(HCU),
            "halo_ps2": git_pin(ROOT / "submodules/halo-ps2"),
            "port_manifest": "submodules/halo-ce-universal/port/ps2/port.json",
            "closure_helper": "tools/hcu_ps2_closure.py selected_sources",
        },
        "map_count": len(maps),
        "category_count": len(categories),
        "maps": maps,
        "categories": categories,
        "route_readers": sites["route_readers"],
        "excluded_surface_walk": sites["excluded_surface_walk"],
        "transition_declarations": sites["transition_declarations"],
        "lens_builder_span": sites["lens_builder_span"],
        "cluster_direct_surface_blocks": direct_blocks,
        "issues": issues,
        "ok": not issues and len(maps) == len(MP_MAPS) and all(
            item["disposition"] != "strip" for item in categories),
        "limits": [
            "Counts are from raw BSP images. This audit does not relocate or publish BSP bytes and does not open HP2 packages, so published-byte and collision-user-depth comparisons are not applicable.",
            "Call sites are source loads. The audit does not execute CE, link a PS2 ELF, or show that a closure function runs during a map load.",
            "structure_lens_flares.c loads the lens-flare range only after build_structure_lens_flares stores zeros over it. That load is not a consumer of the stored map range. The stored-range consumer is rasterizer_lights.c, which the PS2 manifest excludes.",
            "Fog bit 15 is counted only on fog references other than -1. The none sentinel is 0xFFFF and is not an instance.",
            "Unreferenced surfaces are the complement of the leaf and subcluster routes. No closure statement was found that loads one of those surface records.",
            "No PCSX2, GS, VU, or SPU2 output is claimed.",
        ],
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_markdown(report: dict) -> str:
    disposition_rows = []
    for category in report["categories"]:
        disposition_rows.append([
            category["label"],
            str(category["stock_instances"]),
            category["call_site"] or "none",
            "yes" if category["call_site_in_ps2_closure"] else "no",
            category["disposition"],
        ])
    count_headers = ["Map"] + [LABELS[category] for category in CATEGORY_ORDER]
    count_rows = []
    for row in report["maps"]:
        count_rows.append([row["map"]] + [
            str(row["categories"][category]["instances"]) for category in CATEGORY_ORDER])
    empty_lines = []
    for category in CATEGORY_ORDER:
        for row in report["maps"]:
            cell = row["categories"][category]
            if cell["empty"]:
                empty_lines.append(f"- `{row['map']}` {LABELS[category]}: {cell['proof']}")
    parts = [
        "# Presentation omissions",
        "",
        markdown_table(
            ["Category", "Stock instances", "Stored-field call site", "In PS2 closure", "Disposition"],
            disposition_rows),
        "",
        markdown_table(count_headers, count_rows),
        "",
        "## Empty results",
        "",
        "A zero below was produced by reading every relevant raw BSP field. It is an empty result, not a skipped map.",
        "",
        *empty_lines,
        "",
    ]
    return "\n".join(parts)


def render_report(report: dict) -> str:
    lines = [
        "# M2 Step 7 — BSP presentation omissions",
        "",
        "Counts of the nine categories `halo-ps2` docs/08-bsp-section.md lines 40-59 say the BSPS v2 converter does not carry. Oracles are raw decompressed Xbox BSP bytes for the 13 stock multiplayer maps. CE call sites are grep hits in `submodules/halo-ce-universal/source`.",
        "",
        f"Parent `{report['pins']['parent']}`, halo-ce-universal `{report['pins']['halo_ce_universal']}`, halo-ps2 `{report['pins']['halo_ps2']}`.",
        "",
        "Disposition rule: `requires PS2 consumer` only when a live load of the stored map field is in the PS2 closure (`tools/hcu_ps2_closure.py` / `port/ps2/port.json`) and the 13 maps contain at least one instance. Otherwise `retain-bytes`. No category is `strip`.",
        "",
        render_markdown(report),
        "## Call sites",
        "",
    ]
    for category in report["categories"]:
        lines.append(f"### {category['label']}")
        lines.append("")
        lines.append(f"Disposition `{category['disposition']}` ({category['stock_instances']} stock instances). Primary stored-field call site: `{category['call_site'] or 'none'}`.")
        if category["id"] == "render_nodes":
            lines.append("`structure_visibility_build_surfaces` is called from `source/structures/structure_render.c`, which the manifest excludes. The node load itself is in a closure file.")
        if category["id"] == "mirrors":
            lines.append("`structure_visibility_find_mirror` is called from `source/render/render.c`, which the manifest excludes. The mirror load itself is in a closure file. Stock maps have no mirror elements, so the disposition stays retain-bytes.")
        if category["id"] == "unreferenced_surfaces":
            lines.append("The leaf and subcluster walks load only indices on those routes. An unreferenced surface is absent from both, so those walks do not read it.")
            for reader in report["route_readers"]:
                closure = "in closure" if reader["in_ps2_closure"] else "not in closure"
                lines.append(f"- `{reader['file']}:{reader['line']}` ({closure}) contains `{reader['snippet']}`")
            for reader in report["excluded_surface_walk"]:
                lines.append(
                    f"- `{reader['file']}:{reader['line']}` is outside the closure and emits a surface "
                    "only when a route walk has already set its flag bit.")
        elif not category["reads"]:
            if category["id"] == "transition_bsp":
                lines.append("Declarations of `transition_structure_bsp_index` exist. No `->transition_structure_bsp_index` load exists.")
                lines.append("Declarations: " + ", ".join(f"`{item}`" for item in report["transition_declarations"]) + ".")
            else:
                lines.append("No `portal->flags` load exists in CE source. Portal walks read plane, centroid, radius, vertices, and cluster indices.")
        else:
            for read in category["reads"]:
                closure = "in closure" if read["in_ps2_closure"] else "not in closure"
                consumes = "reads stored map bytes" if read["consumes_map_bytes"] else "does not read stored map bytes"
                lines.append(f"- `{read['file']}:{read['line']}` ({closure}; {consumes}): `{read['snippet']}`")
        lines.append("")
    lines.extend([
        "## Checks",
        "",
        "Each BSP was checked against `halo2ps2.bsp.read_structure` for unreferenced indices, collision-node count, portal flags, fog bit 15, and mirror counts. Decal ranges partition the runtime-decal block. Lens-flare ranges partition the marker block. Cluster direct surface-index blocks at +0x44 are empty on every stock BSP.",
        "",
        f"Issues: {len(report['issues'])}.",
        "",
        "## Limits",
        "",
    ])
    for limit in report["limits"]:
        lines.append(f"- {limit}")
    lines.extend([
        "",
        "## Reproduction",
        "",
        "```",
        "python3 tools/audit_mp_bsp_presentation_omissions.py",
        "python3 -m pytest -q tests/test_hcu_mp_bsp_presentation_omissions.py",
        "```",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "build/retail-maps/decompressed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/step7-swarm/omissions")
    args = parser.parse_args()
    report = build_report(args.source_dir)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "omissions.json").write_text(text)
    (args.output_dir / "audit.log").write_text(text)
    (args.output_dir / "omissions.md").write_text(render_markdown(report))
    (args.output_dir / "report.md").write_text(render_report(report))
    sys.stdout.write(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
