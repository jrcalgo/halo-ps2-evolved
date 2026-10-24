#!/usr/bin/env python3
"""Attribute C1 resident CE image bytes to schema fields and owning tag groups.

This is a read-only accounting audit. It does not infer that an extent can be
removed or streamed: CE pointer lifetime remains unchanged. Per-field data
payloads are exact schema-checked in-image extents, useful for choosing a
future bounded-storage experiment.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "build/m2-c1-corpus-rebuild-v3"
QUALIFICATION = ROOT / "docs/reports/m2-c1-qualification-2026-10-23.json"
OUT = ROOT / "docs/reports/m2-c2-ce-image-owner-audit-2026-10-23.json"
SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"

sys.path.insert(0, str(ROOT / "tools"))
import ctag  # noqa: E402
import hcu_profile_chunks as chunks  # noqa: E402
import hcu_profile_validate as profile_validate  # noqa: E402
from ctag_schema_walk import Walker  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_package_allowing_legacy_media(package_path: Path, manifest: dict) -> dict:
    """Verify the package envelope while bypassing only today's admission cap.

    The C1 artifact corpus predates the C2 MEDIA size cap. The normal parser
    rejects those packages before yielding CE, so temporarily raise its
    parser-only limit while retaining package, directory, extent, ordering,
    and every physical/logical digest check. This does not make the packages
    C2-admissible.
    """
    previous = chunks.MAX_MEDIA_CHUNK_BYTES
    chunks.MAX_MEDIA_CHUNK_BYTES = 0xFFFFFFFF
    try:
        return profile_validate.parse_package(
            package_path.read_bytes(), expected_package_sha256=manifest["package_sha256"],
            expected_profile_id=int(manifest["validation"]["profile_id"]))
    finally:
        chunks.MAX_MEDIA_CHUNK_BYTES = previous


def analyze_profile(spec: dict, schema: dict) -> dict:
    name = spec["name"]
    manifest_path = CORPUS / f"{name}.json"
    package_path = CORPUS / f"{name}.hcp"
    manifest = json.loads(manifest_path.read_text())
    package = load_package_allowing_legacy_media(package_path, manifest)
    decoded = ctag.decode(package["chunks"][(1, 0)],
                          max_image_size=len(package["chunks"][(1, 0)]))
    walker = Walker(schema, decoded.image, 0, file_data_policy="inventory",
                    unknown_group_policy="reject")
    walked = walker.run()
    if walked.image != decoded.image:
        raise ValueError(f"{name}: C1 CE image is not schema-normalized")

    counts = Counter()
    for row in walked.group_spans:
        group, start, end, owner = row
        category = ("tag_root" if owner.startswith("tag root ") else
                    "tag_block_elements" if owner.startswith("block ") else
                    "in_image_data_payload" if owner.startswith("data ") else
                    "other_schema_span")
        counts[(group, category)] += end - start
    group_tags = Counter()
    table_offset = int.from_bytes(decoded.image[0:4], "little")
    tag_count = int.from_bytes(decoded.image[12:16], "little")
    for i in range(tag_count):
        offset = table_offset + i * 32
        raw = int.from_bytes(decoded.image[offset:offset + 4], "little")
        group_tags["".join(chr(b) if 32 <= b < 127 else "?"
                           for b in raw.to_bytes(4, "big"))] += 1

    data_bytes = Counter()
    data_records = Counter()
    for group, definition, field, size, _offset in walked.group_in_image_data_records:
        data_bytes[(group, definition, field)] += size
        data_records[(group, definition, field)] += 1
    by_group = {}
    for group in sorted(group_tags):
        by_group[group] = {
            "tag_count": group_tags[group],
            "schema_extent_bytes": sum(value for (g, _kind), value in counts.items() if g == group),
            "tag_root_bytes": counts[(group, "tag_root")],
            "tag_block_element_bytes": counts[(group, "tag_block_elements")],
            "in_image_data_payload_bytes": counts[(group, "in_image_data_payload")],
            "other_schema_span_bytes": counts[(group, "other_schema_span")],
        }
    field_rows = [
        {"tag_group": group, "definition": definition, "field": field,
         "record_count": data_records[(group, definition, field)], "payload_bytes": size}
        for (group, definition, field), size in sorted(data_bytes.items(),
                                                        key=lambda item: (-item[1], item[0]))
    ]
    tag_table_bytes = tag_count * 32
    attributed = sum(item["schema_extent_bytes"] for item in by_group.values())
    return {
        "profile": name,
        "kind": spec["kind"],
        "package_sha256": sha(package_path),
        "manifest_sha256": sha(manifest_path),
        "resident_ce_bytes": len(decoded.image),
        "tag_count": tag_count,
        "tag_instance_table_bytes": tag_table_bytes,
        "group_schema_extent_bytes": attributed,
        "unattributed_image_bytes": len(decoded.image) - tag_table_bytes - attributed,
        "group_bytes": by_group,
        "in_image_data_fields": field_rows,
        "opaque_group_instances": [
            {"tag_index": index, "tag_group": group, "root_offset": root}
            for index, group, root in walked.opaque_groups
        ],
        "schema_visited_bytes": walked.visited_bytes,
    }


def main() -> int:
    qualification = json.loads(QUALIFICATION.read_text())
    specs = json.loads((CORPUS / "specs.json").read_text())
    schema = SchemaManifest(Elf32(SCHEMA_ELF)).build()
    elf_pin = next((row for row in qualification["verification_inputs"]
                    if Path(row["path"]).name == SCHEMA_ELF.name), None)
    if elf_pin is None or schema["elf_sha256"] != elf_pin["sha256"]:
        raise ValueError("schema ELF does not match the pinned C1 qualification input")
    profiles = [analyze_profile(spec, schema) for spec in specs["profiles"]]
    target = next(item for item in profiles if item["profile"] == "survival-bloodgulch")
    survival = [item for item in profiles if item["kind"] == "survival"]
    report = {
        "format": "hcu-c2-ce-image-owner-audit-v1",
        "date": "2026-10-23",
        "scope": "Exact schema-walk accounting of existing C1 decoded CE images; no bytes are declared removable or streamable.",
        "inputs": {
            "qualification": {"path": str(QUALIFICATION.relative_to(ROOT)), "sha256": sha(QUALIFICATION)},
            "profile_specs": {"path": "build/m2-c1-corpus-rebuild-v3/specs.json",
                              "sha256": sha(CORPUS / "specs.json")},
            "schema_elf": {"path": str(SCHEMA_ELF.relative_to(ROOT)), "sha256": sha(SCHEMA_ELF)},
            "schema_walker": {"path": "tools/ctag_schema_walk.py", "sha256": sha(ROOT / "tools/ctag_schema_walk.py")},
            "audit_tool": {"path": "tools/audit_hcu_c2_ce_image_owners.py",
                           "sha256": sha(ROOT / "tools/audit_hcu_c2_ce_image_owners.py")},
        },
        "headline": {
            "profile": target["profile"],
            "resident_ce_bytes": target["resident_ce_bytes"],
            "nominal_10mib_backing_bytes": 10_485_760,
            "excess_over_entire_10mib_bytes": target["resident_ce_bytes"] - 10_485_760,
            "largest_in_image_data_field": target["in_image_data_fields"][0],
            "top_12_in_image_data_fields": target["in_image_data_fields"][:12],
            "largest_tag_groups_by_schema_extent": sorted(
                ({"tag_group": group, **values} for group, values in target["group_bytes"].items()),
                key=lambda row: (-row["schema_extent_bytes"], row["tag_group"]))[:12],
            "max_survival_animation_data_bytes": max(
                (row["payload_bytes"] for profile in survival for row in profile["in_image_data_fields"]
                 if row["definition"] == "animation" and row["field"] == "data"), default=0),
            "max_survival_animation_data_profile": max(
                survival,
                key=lambda profile: sum(row["payload_bytes"] for row in profile["in_image_data_fields"]
                                        if row["definition"] == "animation" and row["field"] == "data"))["profile"],
        },
        "accounting_rules": [
            "Group schema extents are the disjoint root, tag-block element, and in-image tag_data payload spans accepted by the compiled CE schema walker.",
            "Tag-instance table bytes are reported separately because the table is shared and is not owned by one tag group.",
            "Unattributed image bytes include names, header/other structural bytes, and any unvisited bytes; they are not an omission or removal recommendation.",
            "Field rows count only nonempty in-image tag_data payloads; file_data extents are external and not resident CE image bytes.",
            "Existing C1 HCP envelopes are integrity-checked while temporarily relaxing only the parser's newer media-size admission check; this report does not qualify those packages for C2.4.",
            "No schema extent can be moved out of the CE image without preserving every consumer's pointer lifetime and validating runtime parity.",
        ],
        "profiles": profiles,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(profiles)} profiles; "
          f"{target['profile']} has {target['resident_ce_bytes']} CE bytes, "
          f"including {target['in_image_data_fields'][0]['payload_bytes']} bytes in "
          f"{target['in_image_data_fields'][0]['tag_group']}/"
          f"{target['in_image_data_fields'][0]['definition']}.{target['in_image_data_fields'][0]['field']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
