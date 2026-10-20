"""Build an HP2 loader package with schema-converted CTAG and CRNG sections.

This is not a complete game-map pack: the decompressed retail map remains a
separate source file for the bounded resource reader, and presentation sections
must be supplied by the existing PS2 converters.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

try:
    from . import ctag
    from . import ctag_resources
    from . import cbsp
    from . import hmap
    from .audit_ctag_retail_maps import audit_map
    from .audit_retail_bsp_capacity import audit_map as audit_bsp_map
    from .convert_retail_bsp import convert_one as convert_retail_bsp
    from .convert_retail_ctag import convert_retail_map
    from .hcu_schema_manifest import Elf32, SchemaManifest
except ImportError:
    import ctag
    import ctag_resources
    import cbsp
    import hmap
    from audit_ctag_retail_maps import audit_map
    from audit_retail_bsp_capacity import audit_map as audit_bsp_map
    from convert_retail_bsp import convert_one as convert_retail_bsp
    from convert_retail_ctag import convert_retail_map
    from hcu_schema_manifest import Elf32, SchemaManifest


def parse_section(spec: str) -> tuple[str, bytes]:
    if "=" not in spec:
        raise ValueError("section must be TAG=PATH")
    tag, path_text = spec.split("=", 1)
    if (not 1 <= len(tag) <= 4 or any(ord(c) < 0x20 or ord(c) > 0x7E for c in tag) or
            tag in ("CTAG", "CRNG", "CBIX", "HMAP")):
        raise ValueError(f"invalid or reserved HP2 section tag: {tag!r}")
    path = Path(path_text)
    return tag, path.read_bytes()


def pack_retail_map(map_path: Path, schema_elf: Path, *,
                    presentation_sections: list[tuple[str, bytes]] | None = None,
                    include_all_bsps: bool = False,
                    manifest: dict | None = None) -> tuple[bytes, dict]:
    if manifest is None:
        manifest = SchemaManifest(Elf32(schema_elf)).build()
    ctag_payload, summary = convert_retail_map(map_path, manifest=manifest)
    audit = audit_map(map_path, manifest)
    crng_payload = ctag_resources.from_audit(audit)
    hmap_payload = hmap.encode(
        map_path.stem, audit["file_size"], audit["tag_data_offset"],
        audit["tag_data_size"], bytes.fromhex(audit["source_sha256"]))
    sections = list(presentation_sections or [])
    generated_bsp_metadata = []
    if include_all_bsps:
        if any(len(tag) == 4 and tag[0] == "B" and tag[1:].isdigit()
               for tag, _payload in sections):
            raise ValueError("do not combine include_all_bsps with explicit Bxxx sections")
        bsp_map = audit_bsp_map(map_path, capacity=0xFFFFFFFF)
        ordered_bsps = sorted(bsp_map["structure_bsps"],
                              key=lambda row: row["file_offset"])
        for index, row in enumerate(ordered_bsps):
            tag = f"B{index:03d}"
            payload, metadata = convert_retail_bsp(map_path, schema_elf,
                                                     row["path"])
            sections.append((tag, payload))
            generated_bsp_metadata.append(metadata)
    tags = [tag for tag, _data in sections]
    if len(tags) != len(set(tags)):
        raise ValueError("duplicate presentation section tag")
    if any(not 1 <= len(tag) <= 4 for tag in tags):
        raise ValueError("presentation section tags must be 1-4 characters")
    if any(tag == "CBSP" for tag in tags):
        raise ValueError("single CBSP sections are unsupported; provide B000..B031 for every map BSP")
    bsp_sections = [(tag, data) for tag, data in sections
                    if len(tag) == 4 and tag[0] == "B" and tag[1:].isdigit()]
    bsp_catalog_payload = None
    decoded_bsps = {}
    bsp_summary = None
    if bsp_sections:
        canonical_tags = {f"B{index:03d}" for index in range(len(bsp_sections))}
        if {tag for tag, _payload in bsp_sections} != canonical_tags:
            raise ValueError("CBSP HP2 sections must be named contiguously B000, B001, ...")
        source_map = audit_bsp_map(map_path, capacity=0xFFFFFFFF)
        expected = {(row["file_offset"], row["file_size"])
                    for row in source_map["structure_bsps"]}
        entries = []
        for tag, payload in bsp_sections:
            decoded = cbsp.decode(payload, max_image_size=len(payload))
            extent = (decoded.source_file_offset, decoded.source_file_size)
            if extent not in expected:
                raise ValueError(f"{tag} CBSP extent is not a BSP reference in this map")
            if any((entry.file_offset, entry.file_size) == extent for entry in entries):
                raise ValueError("two CBSP sections target the same retail BSP extent")
            entries.append(cbsp.CatalogEntry(*extent, tag))
            decoded_bsps[tag] = decoded
        if {(entry.file_offset, entry.file_size) for entry in entries} != expected:
            raise ValueError("CBSP catalog must provide every BSP referenced by the retail map")
        entries.sort(key=lambda entry: entry.file_offset)
        bsp_catalog_payload = cbsp.encode_catalog(entries,
                                                  file_length=audit["file_size"])
        bsp_summary = {
            "cbsp_count": len(entries),
            "cbsp_section_bytes": sum(len(payload) for _tag, payload in bsp_sections),
            "cbsp_image_bytes": sum(len(decoded.image)
                                    for decoded in decoded_bsps.values()),
            "cbsp_internal_relocation_fields": sum(
                len(decoded.relocations) for decoded in decoded_bsps.values()),
            "cbsp_tag_name_relocation_fields": sum(
                len(decoded.tag_relocations) for decoded in decoded_bsps.values()),
            "cbsp_source_paths": sorted(metadata["bsp_path"]
                                         for metadata in generated_bsp_metadata),
        }
    elif "CBIX" in tags:
        raise ValueError("CBIX is generated from a complete CBSP section set")
    if bsp_catalog_payload is not None:
        sections.append(("CBIX", bsp_catalog_payload))
        tags.append("CBIX")
    name = map_path.stem
    try:
        hp2 = ctag._hp2_module()
        packed = hp2.build(name, [("CTAG", ctag_payload), ("CRNG", crng_payload),
                                  ("HMAP", hmap_payload),
                                  *sections])
        parsed = hp2.parse(packed)
        loaded_ctag = ctag.decode(parsed.read("CTAG"),
                                  max_image_size=len(ctag_payload))
        loaded_crng = ctag_resources.decode(
            parsed.read("CRNG"), expected_file_length=audit["file_size"],
            expected_tag_data_offset=audit["tag_data_offset"],
            expected_tag_data_size=audit["tag_data_size"],
        )
        loaded_hmap = hmap.decode(parsed.read("HMAP"),
                                  expected_map_name=map_path.stem)
        if (loaded_hmap.file_length != audit["file_size"] or
                loaded_hmap.tag_data_offset != audit["tag_data_offset"] or
                loaded_hmap.tag_data_size != audit["tag_data_size"] or
                loaded_hmap.source_sha256.hex() != audit["source_sha256"]):
            raise ValueError("HMAP source identity changed during packaging")
        if bsp_catalog_payload is not None:
            loaded_catalog = cbsp.decode_catalog(
                parsed.read("CBIX"), expected_file_length=audit["file_size"])
            if len(loaded_catalog) != len(decoded_bsps):
                raise ValueError("HP2 CBIX count changed during packaging")
            for tag, decoded_bsp in decoded_bsps.items():
                if cbsp.decode(parsed.read(tag), max_image_size=len(parsed.read(tag))) != decoded_bsp:
                    raise ValueError(f"HP2 {tag} CBSP section changed during packaging")
    except (ValueError, KeyError) as error:
        raise ValueError(f"retail HP2 validation failed: {error}") from error
    if loaded_ctag.scenario_tag_index != summary["scenario_tag_index"]:
        raise ValueError("HP2 CTAG scenario identity changed during packaging")
    if len(loaded_crng.intervals) != audit["resource_interval_index"]["map"]["interval_count"]:
        raise ValueError("HP2 CRNG interval count changed during packaging")
    return packed, {
        **summary,
        "source_sha256": audit["source_sha256"],
        "ctag_section_bytes": len(ctag_payload),
        "crng_section_bytes": len(crng_payload),
        "hmap_section_bytes": len(hmap_payload),
        "resource_interval_count": len(loaded_crng.intervals),
        "presentation_section_tags": tags,
        "complete_bsp_catalog": bsp_catalog_payload is not None,
        **(bsp_summary or {}),
        "hp2_bytes": len(packed),
        "hp2_sha256": hashlib.sha256(packed).hexdigest(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", type=Path, help="decompressed retail Xbox cache map")
    parser.add_argument("schema_elf", type=Path, help="linked HCU ELF with CE schemas")
    parser.add_argument("output", type=Path, help="new HP2 output path; must not exist")
    parser.add_argument("--section", action="append", default=[], metavar="TAG=PATH",
                        help="optional already-converted PS2 presentation section")
    parser.add_argument("--include-all-bsps", action="store_true",
                        help="schema-convert and include every retail BSP plus CBIX (large output; no capacity claim)")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    try:
        sections = [parse_section(spec) for spec in args.section]
        packed, summary = pack_retail_map(args.map, args.schema_elf,
                                          presentation_sections=sections,
                                          include_all_bsps=args.include_all_bsps)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(packed)
    except (OSError, ValueError) as error:
        parser.exit(2, f"retail HP2 packaging failed: {error}\n")
    print(" ".join(f"{key}={value}" for key, value in summary.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
