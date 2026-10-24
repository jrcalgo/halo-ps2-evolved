#!/usr/bin/env python3
"""Inventory match-time tag closure and converted render assets for stock Halo CE MP maps.

Campaign maps are deliberately excluded. Tag closure is followed only through the exact
compiler-derived HCU schemas in the supplied PS2 ELF; conversion byte counts are outputs,
not a claim about simultaneous runtime residency.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "submodules/halo-ps2/tools"
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
MATCH_SEED_GROUPS = {"weap", "eqip", "bipd", "vehi", "proj", "matg", "hudg", "scnr"}
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT / "tools"))
from halo2ps2 import animconv, bitmaps, mapinfo, modelconv, scenconv, skyconv, tagindex, texconv  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pin(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   text=True).strip()


def union_bytes(intervals: list[tuple[int, int]]) -> int:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start for start, end in merged)


class Closure:
    def __init__(self, path: Path, manifest: dict):
        self.path = path
        self.map = texconv.MapData.open(path)
        self.index = self.map.index
        self.data = self.map.region
        self.base = self.map.base
        self.by_id = self.map.by_id
        self.schema_by_group = {g["group"]: g.get("definition") for g in manifest["groups"]}
        self.definitions = manifest["definitions"]
        self.edges: list[dict] = []
        self.spans: list[tuple[int, int]] = []
        self.file_data: list[dict] = []
        self.visited: dict[int, tagindex.TagEntry] = {}
        self.opaque_groups: Counter = Counter()

    def u32(self, off: int) -> int:
        if off < 0 or off + 4 > len(self.data):
            raise ValueError(f"{self.path.stem}: u32 outside tag image at {off:#x}")
        return struct.unpack_from("<I", self.data, off)[0]

    def i32(self, off: int) -> int:
        if off < 0 or off + 4 > len(self.data):
            raise ValueError(f"{self.path.stem}: i32 outside tag image at {off:#x}")
        return struct.unpack_from("<i", self.data, off)[0]

    def add_span(self, off: int, size: int, owner: str) -> None:
        if off < 0 or size < 0 or off > len(self.data) or size > len(self.data) - off:
            raise ValueError(f"{self.path.stem}: {owner} outside tag image {off:#x}+{size:#x}")
        if size:
            self.spans.append((off, off + size))

    def walk_definition(self, entry: tagindex.TagEntry, def_id: int, off: int,
                        depth: int = 0, active: set[tuple[str, int]] | None = None) -> None:
        if depth > 32:
            raise ValueError(f"{self.path.stem}: schema nesting >32 at {entry.path}")
        definition = self.definitions.get(str(def_id))
        if definition is None:
            self.opaque_groups[entry.group or "?"] += 1
            return
        self.add_span(off, int(definition["size"]), f"{entry.path}:{definition['name']}")
        active = set() if active is None else active
        key = (str(def_id), off)
        if key in active:
            raise ValueError(f"{self.path.stem}: recursive tag-block cycle at {entry.path}+{off:#x}")
        active.add(key)
        for field in definition["fields"]:
            kind, stride, count = field["kind"], int(field["size"]), int(field["count"])
            field_off = off + int(field["offset"])
            if count < 0 or stride < 0:
                raise ValueError(f"{self.path.stem}: negative schema span {entry.path}.{field['name']}")
            if kind == "struct":
                for i in range(count):
                    self.walk_definition(entry, int(field["definition"]), field_off + i * stride,
                                         depth + 1, active)
            elif kind == "block":
                if stride != 12:
                    raise ValueError(f"unexpected block stride {stride} in {field['name']}")
                for i in range(count):
                    block = field_off + i * stride
                    n = self.i32(block)
                    address = self.u32(block + 4)
                    if n < 0 or (n and not address):
                        raise ValueError(f"{self.path.stem}: invalid reflexive in {entry.path}.{field['name']}")
                    if n == 0:
                        continue
                    nested = self.definitions.get(str(field["definition"]))
                    if not nested:
                        raise ValueError(f"schema lacks nested definition for {entry.path}.{field['name']}")
                    target = address - self.base
                    byte_count = n * int(nested["size"])
                    self.add_span(target, byte_count, f"{entry.path}.{field['name']}")
                    for j in range(n):
                        self.walk_definition(entry, int(field["definition"]),
                                             target + j * int(nested["size"]), depth + 1, active)
            elif kind in ("data", "file_data"):
                for i in range(count):
                    data_at = field_off + i * stride
                    n = self.i32(data_at)
                    flags = self.u32(data_at + 4)
                    address = self.u32(data_at + 12)
                    file_offset = self.i32(data_at + 8)
                    if n < 0 or (field.get("maximum", 0) and n > int(field["maximum"])):
                        raise ValueError(f"{self.path.stem}: invalid data extent in {entry.path}.{field['name']}")
                    if kind == "file_data":
                        self.file_data.append({"tag": entry.path, "field": field["name"],
                                               "bytes": n, "flags": flags, "file_offset": file_offset})
                    elif n:
                        target = address - self.base
                        self.add_span(target, n, f"{entry.path}.{field['name']} payload")
            elif kind == "reference":
                if stride != 16:
                    raise ValueError(f"unexpected reference stride {stride} in {field['name']}")
                for i in range(count):
                    at = field_off + i * stride
                    raw_group = self.data[at:at + 4]
                    group = tagindex.fourcc(raw_group)
                    target_id = self.u32(at + 12)
                    if target_id == 0xFFFFFFFF or group is None:
                        continue
                    target = self.by_id.get(target_id)
                    self.edges.append({"from": entry.tag_id, "from_path": entry.path,
                                       "field": field["name"], "group": group,
                                       "target_id": target_id,
                                       "target_path": target.path if target else None,
                                       "target_group": target.group if target else None})
            # Scalar/check/string/enum fields contain no reference edges.
        active.remove(key)

    def run(self) -> dict:
        seeds = [e for e in self.index.entries if e.group in MATCH_SEED_GROUPS and e.data_address]
        pending = [e.tag_id for e in seeds]
        seen: set[int] = set()
        while pending:
            tid = pending.pop()
            if tid in seen:
                continue
            entry = self.by_id.get(tid)
            if entry is None:
                continue
            seen.add(tid)
            self.visited[tid] = entry
            definition = self.schema_by_group.get(entry.group or "")
            if entry.group == "sbsp" or not definition:
                self.opaque_groups[entry.group or "?"] += 1
                continue
            self.walk_definition(entry, int(definition), entry.data_address - self.base)
            for edge in self.edges:
                if edge["from"] == tid and edge["target_id"] not in seen and edge["target_path"]:
                    pending.append(edge["target_id"])
        # References are append-only. Keep only those whose source is in the reached set;
        # all edges were traversed only from reached entries, so this is the exact graph.
        return self.summary()

    def summary(self) -> dict:
        paths_by_group: dict[str, list[str]] = defaultdict(list)
        for entry in self.visited.values():
            paths_by_group[entry.group or "?"].append(entry.path)
        for paths in paths_by_group.values():
            paths.sort()
        return {
            "seed_group_counts": dict(sorted(Counter(e.group for e in self.index.entries
                                                       if e.group in MATCH_SEED_GROUPS).items())),
            "closure_tag_count": len(self.visited),
            "closure_group_counts": dict(sorted(Counter(e.group for e in self.visited.values()).items())),
            "closure_paths_by_group": dict(sorted(paths_by_group.items())),
            "closure_tag_root_block_and_in_image_data_union_bytes": union_bytes(self.spans),
            "closure_file_data_bytes_by_source_flag": dict(sorted(Counter({
                str(flag): sum(r["bytes"] for r in self.file_data if r["flags"] == flag)
                for flag in {r["flags"] for r in self.file_data}
            }).items())),
            "closure_file_data_record_count": len(self.file_data),
            "unresolved_reference_count": sum(e["target_path"] is None for e in self.edges),
            "references_to_structure_bsps": sum(e["group"] == "sbsp" for e in self.edges),
            "opaque_or_unwalked_group_roots": dict(sorted(self.opaque_groups.items())),
            "weapon_paths": sorted(e.path for e in self.visited.values() if e.group == "weap"),
            "special_weapon_presence": {
                "energy_sword": any(e.group == "weap" and "energy sword" in e.path.lower()
                                     for e in self.index.entries),
                "fuel_rod": any(e.group == "weap" and "fuel rod" in e.path.lower()
                                 for e in self.index.entries),
                "gravity_rifle": any(e.group == "weap" and "gravity rifle" in e.path.lower()
                                      for e in self.index.entries),
            },
            "bitmap_sources": self.bitmap_source_inventory(),
        }

    def bitmap_source_inventory(self) -> dict:
        sources: dict[str, dict] = {}
        for entry in self.visited.values():
            if entry.group != "bitm":
                continue
            try:
                images = self.map.images(entry.tag_id)
            except (ValueError, bitmaps.BitmapError):
                images = []
            for image in images:
                source = "bitmaps.map" if image.flags & (1 << 8) else self.path.name
                row = sources.setdefault(source, {"image_count": 0, "pixel_bytes_sum": 0,
                                                  "intervals": [], "undecodable_count": 0})
                row["image_count"] += 1
                row["pixel_bytes_sum"] += image.pixel_size
                row["undecodable_count"] += int(not image.decodable)
                if image.pixel_size:
                    row["intervals"].append((image.pixel_offset, image.pixel_offset + image.pixel_size))
        for row in sources.values():
            intervals = row.pop("intervals")
            row["unique_pixel_interval_bytes"] = union_bytes(intervals)
        return dict(sorted(sources.items()))


def convert_assets(path: Path, closure: Closure, static_asset_row: dict | None) -> dict:
    model_ids = sorted({e.tag_id for e in closure.visited.values() if e.group == "mode"})
    anim_ids = sorted({e.tag_id for e in closure.visited.values() if e.group == "antr"})
    complete_models = modelconv.convert_map(path, model_ids)
    complete_anims = animconv.build_section(path, anim_ids)
    baseline = scenconv.collect(path)
    baseline_models = set(baseline.model_tags)
    sky = skyconv.read_sky(path)
    if sky and sky["model_tag"]:
        baseline_models.add(sky["model_tag"])
    base_model_result = modelconv.convert_map(path, sorted(baseline_models))
    baseline_anims = animconv.build_section(path, baseline.anim_tags)
    extra_model_ids = sorted(set(model_ids) - baseline_models)
    extra_anim_ids = sorted(set(anim_ids) - set(baseline.anim_tags))
    return {
        "closure_model_tag_count": len(model_ids),
        "closure_animation_graph_tag_count": len(anim_ids),
        "scenario_baseline_model_tag_count": len(baseline_models),
        "scenario_baseline_animation_graph_count": len(baseline.anim_tags),
        "additional_model_tag_count_vs_scenario_baseline": len(extra_model_ids),
        "additional_animation_graph_count_vs_scenario_baseline": len(extra_anim_ids),
        "additional_model_paths_vs_scenario_baseline": [closure.by_id[t].path for t in extra_model_ids],
        "additional_animation_paths_vs_scenario_baseline": [closure.by_id[t].path for t in extra_anim_ids],
        "scenario_baseline_converted_MODL_bytes": len(base_model_result.modl),
        "scenario_baseline_converted_OTEX_bytes": len(base_model_result.otex),
        "scenario_baseline_converted_ANIM_bytes": len(baseline_anims),
        "full_match_closure_converted_MODL_bytes": len(complete_models.modl),
        "full_match_closure_converted_OTEX_bytes": len(complete_models.otex),
        "full_match_closure_converted_ANIM_bytes": len(complete_anims),
        "full_match_closure_OTEX_texture_pixel_bytes": sum(t.pixel_bytes for t in complete_models.otex_result.textures),
        "full_match_closure_OTEX_clut_bytes": sum(len(t.clut) for t in complete_models.otex_result.textures),
        "converted_MODL_sha256": sha256_bytes(complete_models.modl),
        "converted_OTEX_sha256": sha256_bytes(complete_models.otex),
        "converted_ANIM_sha256": sha256_bytes(complete_anims),
        "untextured_shader_count": complete_models.otex_result.untextured_shaders,
        "baseline_inventory_comparison": ({
            "prior_static_TEXS_bytes": static_asset_row["bsp_referenced_render_textures"]["texs_section_bytes"],
            "prior_static_OTEX_bytes": static_asset_row["scenario_object_selection"]["otex_section_bytes"],
            "prior_static_LM_sections_bytes": static_asset_row["lightmap_lmap_section_bytes_sum"],
        } if static_asset_row else None),
    }


def audit_map(path: Path, manifest: dict, static_row: dict | None) -> dict:
    closure = Closure(path, manifest)
    summary = closure.run()
    summary["map"] = path.stem
    summary["source_map_sha256"] = sha256_file(path)
    summary["converted_match_asset_sections"] = convert_assets(path, closure, static_row)
    # Keep edges in JSON so paths and source fields can be audited; no retail payload bytes are copied.
    summary["reference_edges"] = closure.edges
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("maps", type=Path, help="directory containing decompressed MP retail maps")
    ap.add_argument("--schema-elf", type=Path, required=True,
                    help="current HCU PS2 ELF carrying linked tag schemas")
    ap.add_argument("--static-inventory", type=Path,
                    help="JSON from tools/audit_mp_render_asset_bound.py for comparison")
    ap.add_argument("--output", type=Path, help="new JSON destination; refuses overwrite")
    args = ap.parse_args()
    paths = [args.maps / f"{name}.map" for name in MP_MAPS]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        ap.error("missing required multiplayer map(s): " + ", ".join(missing))
    static = json.loads(args.static_inventory.read_text()) if args.static_inventory else None
    static_by_map = {r["map"]: r for r in static["maps"]} if static else {}
    elf_hash = sha256_file(args.schema_elf)
    manifest = SchemaManifest(Elf32(args.schema_elf)).build()
    if manifest["elf_sha256"] != elf_hash:
        raise RuntimeError("schema ELF hash mismatch")
    rows = []
    for path in paths:
        print(f"auditing MP gameplay closure: {path.name}", file=sys.stderr, flush=True)
        rows.append(audit_map(path, manifest, static_by_map.get(path.stem)))
    union_paths = sorted({p for row in rows for group_paths in row["closure_paths_by_group"].values()
                          for p in group_paths})
    output = {
        "schema": "hcu-mp-match-content-closure-v1",
        "scope": "13 stock Halo CE multiplayer maps only; campaign is excluded",
        "method": "CE/HCU compiler-derived tag schemas; seed roots are map scnr/matg/hudg and all local weap/eqip/bipd/vehi/proj tags; recursive tag-reference closure",
        "source_map_directory": str(args.maps),
        "schema_elf": str(args.schema_elf),
        "schema_elf_sha256": elf_hash,
        "halo_ce_universal_commit": pin(ROOT / "submodules/halo-ce-universal"),
        "halo_ps2_commit": pin(ROOT / "submodules/halo-ps2"),
        "audit_tool_sha256": sha256_file(Path(__file__).resolve()),
        "map_count": len(rows),
        "reachable_unique_path_count_across_map_copies": len(union_paths),
        "summed_map_closure_tag_union_bytes_not_simultaneous": sum(
            r["closure_tag_root_block_and_in_image_data_union_bytes"] for r in rows),
        "largest_single_map_closure_tag_union_bytes": max(
            r["closure_tag_root_block_and_in_image_data_union_bytes"] for r in rows),
        "maps": rows,
        "interpretation_limits": [
            "tag closure covers linked-schema tag references from specified seeds; BSP roots are separately represented by sbsp references and static BSP packages",
            "opaque/unresolved roots are enumerated and are not falsely claimed as closed",
            "bitmap pixel extents and file-data records are source extents, not converted residency or EE peak",
            "MODL/OTEX/ANIM byte counts are independent offline converted outputs; do not sum them with tag-image bytes as if concurrently allocated",
            "no simultaneous runtime residency, animation pins, first-person switch peak, bot count, effects peak, DMA staging, or cache high-water is measured",
            "special weapon tag presence is source-map availability only; absent tags need separately provisioned special-weapon assets",
        ],
    }
    rendered = json.dumps(output, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            ap.error(f"refusing to overwrite existing output: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
