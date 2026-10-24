#!/usr/bin/env python3
"""Cross-check retail scenario BSP references against the tag index and HP2 CBIX.

This is an offline source-identity audit, not a loader/capacity/runtime claim. It
uses the compiler-derived schema manifest to locate the scenario reference block
and independently resolves each datum through the retail tag index and package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
PS2_TOOLS = ROOT / "submodules/halo-ps2/tools"
if str(PS2_TOOLS) not in sys.path:
    sys.path.insert(0, str(PS2_TOOLS))

from halo2ps2 import mapinfo, tagindex, bsp  # noqa: E402

try:
    from . import ctag, cbsp
    from .ctag_schema_walk import read_xbox_tag_region
    from .hcu_schema_manifest import Elf32, SchemaManifest
except ImportError:
    import ctag  # noqa: E402
    import cbsp  # noqa: E402
    from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
    from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402


def _field(definition: dict, name: str) -> dict:
    found = [item for item in definition["fields"] if item["name"] == name]
    if len(found) != 1:
        raise ValueError(f"expected one schema field {definition['name']}.{name}")
    return found[0]


def _scenario_reference_layout(manifest: dict) -> tuple[int, int, int, int, int]:
    groups = [item for item in manifest["groups"] if item["group"] == "scnr"]
    if len(groups) != 1 or not groups[0].get("definition"):
        raise ValueError("schema manifest must contain one concrete scnr group")
    scenario = manifest["definitions"][str(groups[0]["definition"])]
    block = _field(scenario, "structure_bsp_references")
    ref_address = block["definition"]
    ref = manifest["definitions"][str(ref_address)]
    reference = _field(ref, "structure_bsp")
    reference_offset = reference["offset"]
    # Scenario tag structure base is independently fixed by the CE schema ABI.
    if block["kind"] != "block" or block["size"] != 12 or reference["kind"] != "reference":
        raise ValueError("scenario structure BSP schema shape is not the expected CE tag_block/tag_reference")
    if reference.get("groups") != ["sbsp"] or reference["size"] != 16:
        raise ValueError("scenario BSP reference does not target the sbsp group")
    return block["offset"], block["maximum"], ref["size"], reference_offset, reference["size"]


def _retail_map(path: Path, manifest: dict) -> tuple[dict, list[dict]]:
    index = tagindex.TagIndex.read(path)
    image, tag_base, source = read_xbox_tag_region(path)
    offset, maximum, stride, reference_offset, reference_size = _scenario_reference_layout(manifest)
    scenario_index = index.header.scenario_tag_id & 0xFFFF
    if scenario_index >= len(index.entries):
        raise ValueError(f"{path.name}: scenario datum index outside tag table")
    scenario_entry = index.entries[scenario_index]
    if scenario_entry.group != "scnr" or scenario_entry.tag_id != index.header.scenario_tag_id:
        raise ValueError(f"{path.name}: scenario datum does not resolve to the indexed scnr")
    scenario_root = scenario_entry.data_address - tag_base
    if scenario_root < 0 or scenario_root + offset + 12 > len(image):
        raise ValueError(f"{path.name}: scenario structure-BSP block header leaves tag region")
    count, address, _definition = struct.unpack_from("<iII", image, scenario_root + offset)
    if count < 0 or (maximum > 0 and count > maximum):
        raise ValueError(f"{path.name}: invalid scenario BSP reference count {count}")
    if count == 0:
        refs_offset = 0
    else:
        refs_offset = address - tag_base
        if refs_offset < 0 or count > (len(image) - refs_offset) // stride:
            raise ValueError(f"{path.name}: scenario BSP references leave tag region")

    indexed = {entry.tag_id: entry for entry in index.entries}
    locations = bsp.locate(index, image, source["file_size"])
    by_path: dict[str, list] = {}
    by_tag = {entry.tag_id: entry for entry in index.entries if entry.group == "sbsp"}
    for location in locations:
        by_path.setdefault(location.path.casefold(), []).append(location)
    output = []
    for ordinal in range(count):
        ref = refs_offset + ordinal * stride
        group, name_ptr, name_length, tag_id = struct.unpack_from(
            "<4I", image, ref + reference_offset)
        target = indexed.get(tag_id)
        # Retail reference FourCC words are byte-reversed in the Xbox image,
        # matching tagindex.fourcc()'s raw-byte reversal convention.
        if group != int.from_bytes(b"psbs", "little"):
            raise ValueError(f"{path.name}: scenario BSP ref {ordinal} has wrong group {group:#x}")
        if target is None or target.group != "sbsp" or target.tag_id != tag_id:
            raise ValueError(f"{path.name}: scenario BSP ref {ordinal} has unresolved/wrong datum {tag_id:#x}")
        name_offset = name_ptr - tag_base
        if name_offset < 0 or name_offset >= len(image):
            raise ValueError(f"{path.name}: scenario BSP ref {ordinal} name pointer leaves tag image")
        terminator = image.find(b"\0", name_offset, min(len(image), name_offset + 256))
        if terminator < 0:
            raise ValueError(f"{path.name}: scenario BSP ref {ordinal} has unterminated name")
        name = image[name_offset:terminator].decode("ascii", "strict")
        # Retail CE leaves the tag_reference name_length word zero for these
        # scenario BSP references; the authoritative name is the bounded NUL
        # string and datum. Record the raw value rather than treating zero as
        # an empty path or imposing a converter-specific length contract.
        if name != target.path:
            raise ValueError(f"{path.name}: scenario BSP ref {ordinal} name {name!r} != indexed path {target.path!r}")
        candidates = by_path.get(name.casefold(), [])
        if len(candidates) != 1:
            raise ValueError(f"{path.name}: scenario BSP ref {ordinal} maps to {len(candidates)} BSP extents")
        location = candidates[0]
        output.append({
            "ordinal": ordinal,
            "scenario_reference_tag_id": f"0x{tag_id:08x}",
            "scenario_reference_path": name,
            "scenario_reference_name_length_field": name_length,
            "tag_index_tag_id": f"0x{target.tag_id:08x}",
            "tag_index_path": target.path,
            "source_file_offset": location.file_offset,
            "source_file_size": location.size,
        })
    if len(locations) != count:
        raise ValueError(f"{path.name}: scenario has {count} refs, BSP locator found {len(locations)}")
    # The tag datum and scenario's reference list must identify each located
    # BSP exactly once; matching only aggregate counts would miss duplicates.
    referenced_ids = [int(row["scenario_reference_tag_id"], 16) for row in output]
    located_ids = [entry.tag_id for entry in by_tag.values() if entry.path.casefold() in by_path]
    if len(referenced_ids) != len(set(referenced_ids)) or set(referenced_ids) != set(located_ids):
        raise ValueError(f"{path.name}: scenario references and indexed sbsp datum set differ")
    return {
        "map": path.stem,
        "map_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scenario_path": scenario_entry.path,
        "scenario_tag_id": f"0x{scenario_entry.tag_id:08x}",
        "scenario_reference_count": count,
        "references": output,
    }, output


def audit(map_dir: Path, package_dir: Path, schema_elf: Path) -> dict:
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    rows = []
    total_refs = 0
    for map_path in sorted(map_dir.glob("*.map")):
        row, refs = _retail_map(map_path, manifest)
        package_path = package_dir / f"{map_path.stem}.hp2"
        if not package_path.is_file():
            raise ValueError(f"missing package {package_path}")
        package_bytes = package_path.read_bytes()
        parsed = ctag._hp2_module().parse(package_bytes)
        cat = cbsp.decode_catalog(parsed.read("CBIX"),
                                  expected_file_length=mapinfo.read_header(map_path).decompressed_size)
        expected = [(entry.file_offset, entry.file_size, entry.section_tag)
                    for entry in cat]
        actual = [(ref["source_file_offset"], ref["source_file_size"], f"B{ref['ordinal']:03d}")
                  for ref in refs]
        # CBIX order is extent-sorted. Scenario order is a separate game datum
        # ordering; compare rows by source extent and validate canonical package
        # section identity Bnnn against that map's exact extent.
        by_extent = {(off, size): tag for off, size, tag in expected}
        for ref in refs:
            extent = (ref["source_file_offset"], ref["source_file_size"])
            tag = by_extent.get(extent)
            if tag is None:
                raise ValueError(f"{map_path.name}: scenario ref {ref['ordinal']} extent absent from CBIX")
            ref["cbix_section_tag"] = tag
        if len(actual) != len(expected) or {item[:2] for item in actual} != set(by_extent):
            raise ValueError(f"{map_path.name}: scenario reference extents differ from CBIX extent set")
        row["package_sha256"] = hashlib.sha256(package_bytes).hexdigest()
        row["scenario_order_matches_cbix_extent_order"] = [
            (a["source_file_offset"], a["source_file_size"]) for a in refs
        ] == [(off, size) for off, size, _tag in expected]
        row["references"] = refs
        rows.append(row)
        total_refs += len(refs)
    if len(rows) != 24 or total_refs != 82:
        raise ValueError(f"expected 24 maps/82 references, got {len(rows)}/{total_refs}")
    return {
        "format": "retail-ce-scenario-bsp-reference-audit-v1",
        "schema_elf_sha256": manifest["elf_sha256"],
        "map_count": len(rows),
        "scenario_bsp_reference_count": total_refs,
        "maps": rows,
        "interpretation": "Offline retail source/tag/package identity audit only; no runtime load, capacity, CE globals, or rendering claim.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", type=Path, help="directory of decompressed retail Xbox maps")
    parser.add_argument("packages", type=Path, help="directory of corresponding HP2 packages")
    parser.add_argument("schema_elf", type=Path, help="linked HCU ELF with compiler-derived schema")
    parser.add_argument("--output", type=Path, required=True, help="new JSON report (never overwritten)")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite report: {args.output}")
    try:
        result = audit(args.maps, args.packages, args.schema_elf)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    except (OSError, ValueError, KeyError, struct.error, UnicodeError) as error:
        parser.exit(2, f"scenario BSP reference audit failed: {error}\n")
    print(json.dumps({k: v for k, v in result.items() if k != "maps"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
