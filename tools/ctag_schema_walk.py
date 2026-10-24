"""Convert Xbox CE tag pointers to offsets using a compiled schema manifest.

This is the schema walk stage only: it normalizes the CE tag image's in-cache
pointers and emits the relocation slots CTAG needs. It deliberately rejects
unsupported or out-of-range extents instead of guessing from DWORD values.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys


TAG_HEADER_SIZE = 36
TAG_INSTANCE_SIZE = 32
TAG_BLOCK_SIZE = 12
TAG_DATA_SIZE = 20
TAG_REFERENCE_SIZE = 16


class SchemaWalkError(ValueError):
    pass


@dataclass(frozen=True)
class SchemaWalkResult:
    image: bytes
    relocations: tuple[int, ...]
    scenario_tag_index: int
    visited_bytes: int
    stripped_file_data_bytes: int
    file_data_records: tuple[tuple[str, str, int, int, int], ...]
    unsupported_groups: tuple[tuple[int, str, int], ...]
    opaque_groups: tuple[tuple[int, str, int], ...]
    reference_target_counts: tuple[tuple[str, int], ...]
    schema_bytes_by_owner: tuple[tuple[str, int], ...]
    in_image_data_records: tuple[tuple[str, str, int, int], ...]


@dataclass(frozen=True)
class StructureBspWalkResult:
    """Schema-checked BSP with internal and cross-image relocation slots."""
    image: bytes
    relocations: tuple[int, ...]
    tag_relocations: tuple[tuple[int, int], ...]
    spans: tuple[tuple[int, int, str], ...]
    visited_bytes: int
    file_data_records: tuple[tuple[str, str, int, int, int], ...]
    normalizations: tuple[tuple[int, int, int, str], ...]


class Walker:
    def __init__(self, manifest: dict, image: bytes, source_base: int = 0,
                 file_data_policy: str = "reject", unknown_group_policy: str = "reject",
                 opaque_groups=(), external_reference_mapper=None):
        if manifest.get("format") != "hcu-schema-manifest-v1":
            raise SchemaWalkError("unsupported CE schema manifest")
        self.manifest = manifest
        self.image = bytearray(image)
        self.source_image = bytes(image)
        self.normalizations: list[tuple[int, int, int, str]] = []
        self.source_base = source_base
        if file_data_policy not in ("reject", "strip", "inventory"):
            raise SchemaWalkError("file_data_policy must be 'reject', 'strip', or 'inventory'")
        if unknown_group_policy not in ("reject", "inventory"):
            raise SchemaWalkError("unknown_group_policy must be 'reject' or 'inventory'")
        self.file_data_policy = file_data_policy
        self.unknown_group_policy = unknown_group_policy
        self.definitions = manifest.get("definitions", {})
        self.groups = {self.group_value(item["group"]): item
                       for item in manifest.get("groups", [])}
        self.opaque_groups = {str(group) for group in opaque_groups}
        self.external_reference_mapper = external_reference_mapper
        for group in self.opaque_groups:
            value = self.group_value(group)
            declaration = next((item for item in manifest.get("groups", [])
                                if item.get("group") == group), None)
            if declaration is None or declaration.get("definition") is not None:
                raise SchemaWalkError(
                    f"opaque group {group} must be declared by CE with a null schema")
            if value not in self.groups:
                raise SchemaWalkError(f"opaque group {group} has an invalid manifest entry")
        self.stripped_file_data_bytes = 0
        self.file_data_records: list[tuple[str, str, int, int, int]] = []
        self.in_image_data_records: list[tuple[str, str, int, int]] = []
        self.unsupported_groups: list[tuple[int, str, int]] = []
        self.opaque_group_instances: list[tuple[int, str, int]] = []
        self.tag_groups_by_handle: dict[int, str] = {}
        self.reference_target_counts: dict[str, int] = {}
        self.size = len(image)
        self.relocations = set()
        self.external_reference_relocations: list[tuple[int, int]] = []
        self.spans: list[tuple[int, int, str]] = []
        self.visiting = set()

    @staticmethod
    def group_value(group: str) -> int:
        try:
            raw = group.encode("ascii")
        except (AttributeError, UnicodeEncodeError) as error:
            raise SchemaWalkError(f"invalid tag group {group!r}") from error
        if len(raw) != 4:
            raise SchemaWalkError(f"tag group {group!r} is not four bytes")
        return int.from_bytes(raw, "big")

    @staticmethod
    def fourcc(value: int) -> str:
        return "".join(chr(item) if 0x20 <= item < 0x7F else "?"
                       for item in value.to_bytes(4, "big"))

    def u32(self, offset: int) -> int:
        self.require(offset, 4, "u32")
        return struct.unpack_from("<I", self.image, offset)[0]

    def i32(self, offset: int) -> int:
        self.require(offset, 4, "i32")
        return struct.unpack_from("<i", self.image, offset)[0]

    def write_u32(self, offset: int, value: int, reason: str = "internal-pointer"):
        self.require(offset, 4, "pointer field")
        if not 0 <= value <= 0xFFFFFFFF:
            raise SchemaWalkError("normalized pointer is outside u32")
        previous = self.u32(offset)
        struct.pack_into("<I", self.image, offset, value)
        self.normalizations.append((offset, previous, value, reason))

    def verify_bsp_preservation(self):
        """Require every byte change to be one explicit schema normalization.

        Replay in order: an overlapping schema field cannot hide a second
        unexplained write, and opaque/padding/payload bytes remain covered.
        """
        expected = bytearray(self.source_image)
        external_names = set(self.external_reference_relocations)
        for offset, previous, value, reason in self.normalizations:
            if reason not in {"internal-pointer", "external-name", "empty-pointer",
                              "runtime-definition", "file-data-pointer"}:
                raise SchemaWalkError(f"unapproved BSP normalization {reason!r}")
            if reason == "internal-pointer" and (
                    offset not in self.relocations or
                    value != (previous - self.source_base if previous else 0)):
                raise SchemaWalkError(f"invalid BSP pointer normalization at {offset:#x}")
            if reason == "external-name" and (
                    offset, value) not in external_names:
                raise SchemaWalkError(f"unregistered BSP tag name at {offset:#x}")
            if reason in {"empty-pointer", "runtime-definition", "file-data-pointer"} and value:
                raise SchemaWalkError(f"nonzero BSP reset at {offset:#x}")
            if struct.unpack_from("<I", expected, offset)[0] != previous:
                raise SchemaWalkError(f"unrecorded BSP write before {offset:#x}")
            struct.pack_into("<I", expected, offset, value)
        if expected != self.image:
            raise SchemaWalkError("BSP bytes changed outside schema normalizations")

    def require(self, offset: int, size: int, what: str):
        if offset < 0 or size < 0 or offset > self.size or size > self.size - offset:
            raise SchemaWalkError(f"{what} extent {offset:#x}+{size:#x} leaves {self.size:#x}-byte image")

    def pointer_target(self, field_offset: int, required: bool = False) -> int:
        value = self.u32(field_offset)
        if value == 0:
            self.relocations.add(field_offset)
            if required:
                raise SchemaWalkError(f"required pointer at {field_offset:#x} is null")
            return 0
        target = value - self.source_base if self.source_base else value
        if target < 0 or target >= self.size:
            raise SchemaWalkError(f"pointer {value:#x} at {field_offset:#x} leaves tag image")
        self.write_u32(field_offset, target)
        self.relocations.add(field_offset)
        return target

    def add_span(self, start: int, size: int, owner: str):
        self.require(start, size, owner)
        if size == 0:
            return
        end = start + size
        self.spans.append((start, end, owner))

    def validate_spans(self):
        ordered = sorted(self.spans)
        for previous, current in zip(ordered, ordered[1:]):
            previous_start, previous_end, previous_owner = previous
            start, end, owner = current
            if start < previous_end:
                raise SchemaWalkError(
                    f"{owner} {start:#x}..{end:#x} overlaps {previous_owner} "
                    f"{previous_start:#x}..{previous_end:#x}")

    def schema(self, address) -> dict:
        try:
            return self.definitions[str(address)]
        except KeyError as error:
            raise SchemaWalkError(f"manifest has no schema definition {address!r}") from error

    def walk_definition(self, definition_address, base: int, depth: int = 0):
        if depth > 32:
            raise SchemaWalkError("schema nesting exceeds CE validator depth")
        definition = self.schema(definition_address)
        self.require(base, definition["size"], definition["name"])
        key = (str(definition_address), base)
        if key in self.visiting:
            raise SchemaWalkError(f"cyclic tag-block graph at {base:#x}")
        self.visiting.add(key)
        for field in definition["fields"]:
            kind = field["kind"]
            stride = field["size"]
            count = field["count"]
            field_base = base + field["offset"]
            if count < 0 or stride < 0:
                raise SchemaWalkError(f"negative schema stride/count in {definition['name']}.{field['name']}")
            if kind == "struct":
                nested = self.schema(field["definition"])
                if count < 1 or nested["size"] > stride:
                    raise SchemaWalkError(f"invalid inline struct {definition['name']}.{field['name']}")
                for item in range(count):
                    self.walk_definition(field["definition"], field_base + item * stride, depth + 1)
            elif kind == "block":
                if stride != TAG_BLOCK_SIZE:
                    raise SchemaWalkError(f"unexpected tag_block stride {stride}")
                for item in range(count):
                    block = field_base + item * stride
                    block_count = self.i32(block)
                    address_field = block + 4
                    self.write_u32(block + 8, 0, "runtime-definition")
                    if block_count < 0:
                        raise SchemaWalkError(f"negative tag_block count in {definition['name']}.{field['name']}")
                    if not block_count:
                        self.write_u32(address_field, 0, "empty-pointer")
                        continue
                    target = self.pointer_target(address_field, required=True)
                    if target & 3:
                        raise SchemaWalkError(
                            f"tag_block target {target:#x} is not 4-byte aligned in "
                            f"{definition['name']}.{field['name']}")
                    maximum = field["maximum"]
                    if maximum > 0 and block_count > maximum:
                        raise SchemaWalkError(f"tag_block exceeds CE maximum in {definition['name']}.{field['name']}")
                    nested = self.schema(field["definition"])
                    byte_count = block_count * nested["size"]
                    self.require(target, byte_count, f"block {definition['name']}.{field['name']}")
                    self.add_span(target, byte_count, f"block {definition['name']}.{field['name']}")
                    for element in range(block_count):
                        self.walk_definition(field["definition"], target + element * nested["size"], depth + 1)
            elif kind in ("data", "file_data"):
                if stride != TAG_DATA_SIZE:
                    raise SchemaWalkError(f"unexpected tag_data stride {stride}")
                for item in range(count):
                    data = field_base + item * stride
                    data_size = self.i32(data)
                    if data_size < 0 or (field["maximum"] > 0 and data_size > field["maximum"]):
                        raise SchemaWalkError(f"invalid data size in {definition['name']}.{field['name']}")
                    address_field = data + 12
                    if kind == "file_data":
                        if data_size:
                            self.file_data_records.append((
                                definition["name"], field["name"], data_size,
                                self.u32(data + 4), self.i32(data + 8)))
                            if self.file_data_policy == "reject":
                                raise SchemaWalkError(
                                    f"file-backed data {definition['name']}.{field['name']} needs a resource policy")
                            if self.file_data_policy == "strip":
                                self.stripped_file_data_bytes += data_size
                                struct.pack_into("<i", self.image, data, 0)
                                struct.pack_into("<i", self.image, data + 8, 0)
                        self.write_u32(address_field, 0, "file-data-pointer")
                    else:
                        if not data_size:
                            self.write_u32(address_field, 0, "empty-pointer")
                        else:
                            target = self.pointer_target(address_field, required=True)
                            if target & 3:
                                raise SchemaWalkError(
                                    f"tag_data target {target:#x} is not 4-byte aligned in "
                                    f"{definition['name']}.{field['name']}")
                            self.require(target, data_size, f"data {definition['name']}.{field['name']}")
                            self.add_span(target, data_size, f"data {definition['name']}.{field['name']}")
                            self.in_image_data_records.append((
                                definition["name"], field["name"], data_size, target
                            ))
                    self.write_u32(data + 16, 0, "runtime-definition")
            elif kind == "reference":
                if stride != TAG_REFERENCE_SIZE:
                    raise SchemaWalkError(f"unexpected tag_reference stride {stride}")
                for item in range(count):
                    reference = field_base + item * stride
                    name_field = reference + 4
                    name_value = self.u32(name_field)
                    external_name = False
                    if (name_value and self.external_reference_mapper and
                            not (self.source_base <= name_value < self.source_base + self.size)):
                        name = self.external_reference_mapper(name_value)
                        if not isinstance(name, int) or name < 0 or name > 0xFFFFFFFF:
                            raise SchemaWalkError(
                                f"external tag-reference name {name_value:#x} has no bounded tag-image mapping")
                        self.write_u32(name_field, name, "external-name")
                        self.external_reference_relocations.append((name_field, name))
                        external_name = True
                    else:
                        name = self.pointer_target(name_field)
                    handle = self.u32(reference + 12)
                    if handle == 0xFFFFFFFF:
                        target_group = "NONE"
                    else:
                        target_group = self.tag_groups_by_handle.get(handle, "UNRESOLVED")
                    self.reference_target_counts[target_group] = self.reference_target_counts.get(target_group, 0) + 1
                    if name and not external_name:
                        end = self.image.find(0, name, min(self.size, name + 256))
                        if end < 0:
                            raise SchemaWalkError(f"unterminated tag reference name at {name:#x}")
            elif kind in ("tag_index", "block_index", "enum", "string", "reset", "check"):
                continue
            else:
                raise SchemaWalkError(f"unsupported schema kind {kind!r}")
        self.visiting.remove(key)

    def run(self) -> SchemaWalkResult:
        self.require(0, TAG_HEADER_SIZE, "CE tag header")
        if self.u32(32) != 0x74616773:
            raise SchemaWalkError("bad CE tag header signature")
        scenario = self.u32(4)
        tag_count = self.u32(12)
        table = self.pointer_target(0, required=True)
        self.pointer_target(20)
        self.pointer_target(28)
        if tag_count == 0 or (scenario & 0xFFFF) >= tag_count:
            raise SchemaWalkError("invalid scenario tag index")
        table_bytes = tag_count * TAG_INSTANCE_SIZE
        self.require(table, table_bytes, "tag-instance table")
        self.add_span(table, table_bytes, "tag-instance table")
        for index in range(tag_count):
            instance = table + index * TAG_INSTANCE_SIZE
            self.tag_groups_by_handle[self.u32(instance + 12)] = self.fourcc(self.u32(instance))
        for index in range(tag_count):
            instance = table + index * TAG_INSTANCE_SIZE
            group = self.u32(instance)
            tag_index = self.u32(instance + 12) & 0xFFFF
            if tag_index != index:
                raise SchemaWalkError(f"tag instance {index} has mismatched index {tag_index}")
            schema_group = self.groups.get(group)
            name = self.pointer_target(instance + 16)
            root = self.pointer_target(instance + 20)
            if name:
                end = self.image.find(0, name, min(self.size, name + 256))
                if end < 0:
                    raise SchemaWalkError(f"unterminated tag name at {name:#x}")
            if group == self.group_value("sbsp"):
                if root:
                    raise SchemaWalkError("structure BSP must not have a tag-root pointer")
                continue
            if not schema_group or not schema_group.get("definition"):
                group_name = self.fourcc(group)
                if group_name in self.opaque_groups:
                    if not root:
                        raise SchemaWalkError(f"opaque tag {index} ({group_name}) has no root data")
                    # The CE validator preserves the datum but skips root
                    # traversal when the linked group definition is null.
                    # Its internal bytes are intentionally not interpreted.
                    self.opaque_group_instances.append((index, group_name, root))
                    continue
                if self.unknown_group_policy == "inventory":
                    self.unsupported_groups.append((index, group_name, root))
                    continue
                raise SchemaWalkError(f"tag {index} has no linked CE schema for {group_name}")
            if root:
                definition = self.schema(schema_group["definition"])
                self.add_span(root, definition["size"],
                              f"tag root {self.fourcc(group)}")
                self.walk_definition(schema_group["definition"], root)
            else:
                raise SchemaWalkError(f"tag {index} ({self.fourcc(group)}) has no root data")
        self.validate_spans()
        owner_bytes: dict[str, int] = {}
        for start, end, owner in self.spans:
            owner_bytes[owner] = owner_bytes.get(owner, 0) + end - start
        return SchemaWalkResult(bytes(self.image), tuple(sorted(self.relocations)), scenario,
                                sum(end - start for start, end, _owner in self.spans),
                                self.stripped_file_data_bytes, tuple(self.file_data_records),
                                tuple(self.unsupported_groups), tuple(self.opaque_group_instances),
                                tuple(sorted(self.reference_target_counts.items())),
                                tuple(sorted(owner_bytes.items())),
                                tuple(self.in_image_data_records))

    def run_structure_bsp(self) -> StructureBspWalkResult:
        """Walk a standalone BSP image while keeping tag-name pointers typed.

        ``relocations`` target this BSP image. External tag-reference name
        pointers are returned separately as offsets into CTAG.
        """
        if len(self.image) < 24 or self.image[20:24] != b"psbs":
            raise SchemaWalkError("bad structure-BSP header signature")
        group = next((item for item in self.manifest.get("groups", [])
                      if item.get("group") == "sbsp"), None)
        if not group or not group.get("definition"):
            raise SchemaWalkError("manifest has no linked structure-BSP schema")
        root = self.pointer_target(0, required=True)
        if root & 3:
            raise SchemaWalkError("structure-BSP root target is not 4-byte aligned")
        definition = self.schema(group["definition"])
        self.add_span(root, definition["size"], "structure-BSP root")
        self.walk_definition(group["definition"], root)
        self.validate_spans()
        if self.file_data_policy == "strip":
            raise SchemaWalkError("BSP payload stripping is not a preservation policy")
        self.verify_bsp_preservation()
        return StructureBspWalkResult(
            bytes(self.image), tuple(sorted(self.relocations)),
            tuple(sorted(self.external_reference_relocations)),
            tuple(sorted(self.spans)), sum(end - start for start, end, _owner in self.spans),
            tuple(self.file_data_records), tuple(self.normalizations))


def walk_tag_image(manifest: dict, image: bytes, source_base: int = 0,
                   file_data_policy: str = "reject", unknown_group_policy: str = "reject",
                   opaque_groups=()) -> SchemaWalkResult:
    """Normalize schema-declared in-image pointers and return sorted CTAG relocations."""
    return Walker(manifest, image, source_base, file_data_policy, unknown_group_policy,
                  opaque_groups).run()


def walk_structure_bsp(manifest: dict, image: bytes, source_base: int,
                       tag_reference_mapper=None,
                       file_data_policy: str = "reject") -> StructureBspWalkResult:
    """Normalize schema-declared BSP pointers with checked cross-image names.

    ``tag_reference_mapper`` maps each retail tag-name address outside the BSP
    extent to a bounded offset in the final CTAG image. This returns relocation
    metadata; it does not materialize pointers or prove a runtime load.
    """
    if not isinstance(source_base, int) or source_base < 0 or source_base > 0xFFFFFFFF:
        raise SchemaWalkError("BSP source base is outside the 32-bit address space")
    if source_base + len(image) > 0x1_0000_0000:
        raise SchemaWalkError("BSP source extent wraps the 32-bit address space")
    walker = Walker(manifest, image, source_base, file_data_policy,
                    external_reference_mapper=tag_reference_mapper)
    return walker.run_structure_bsp()


def compact_pointer_image(image: bytes, relocations, removed_ranges):
    """Remove unreferenced byte ranges and rebase schema-declared pointers.

    ``relocations`` are the pointer-field offsets emitted by ``walk_tag_image``
    and their values must already be image-relative. Any pointer field or
    non-null pointer target that intersects a removed range fails closed.
    """
    ranges = sorted((int(start), int(end)) for start, end in removed_ranges)
    previous_end = 0
    for start, end in ranges:
        if start < previous_end or start < 0 or end < start or end > len(image):
            raise SchemaWalkError("removed image ranges overlap or leave the image")
        previous_end = end
    ranges = [(start, end) for start, end in ranges if start != end]

    def translate(offset: int, width: int = 1) -> int:
        if offset < 0 or width < 0 or offset > len(image) or width > len(image) - offset:
            raise SchemaWalkError("pointer field or target is outside source image")
        removed_before = 0
        for start, end in ranges:
            if offset < end and start < offset + width:
                raise SchemaWalkError("schema pointer field or target intersects removed image range")
            if end <= offset:
                removed_before += end - start
        return offset - removed_before

    chunks = []
    cursor = 0
    for start, end in ranges:
        chunks.append(image[cursor:start])
        cursor = end
    chunks.append(image[cursor:])
    compacted = bytearray().join(chunks)
    compact_relocations = []
    for field in relocations:
        compact_field = translate(field, 4)
        target = struct.unpack_from("<I", image, field)[0]
        compact_target = translate(target) if target else 0
        struct.pack_into("<I", compacted, compact_field, compact_target)
        compact_relocations.append(compact_field)
    return bytes(compacted), tuple(compact_relocations)


def tag_group_coverage(manifest: dict, entries) -> dict:
    """Summarize linked-schema coverage without treating missing schemas as safe.

    This inventory is deliberately separate from the converter: a group with
    no schema remains unsupported even when no declared tag-reference field
    names it. The reference count is evidence for follow-up ownership review,
    not proof that dynamic consumers do not exist.
    """
    groups = {item["group"]: item for item in manifest.get("groups", [])}
    reference_fields: dict[str, int] = {}
    for definition in manifest.get("definitions", {}).values():
        for field in definition.get("fields", []):
            if field.get("kind") == "reference":
                for group in field.get("groups") or []:
                    reference_fields[group] = reference_fields.get(group, 0) + 1

    totals: dict[str, dict] = {}
    for entry in entries:
        group = entry.group
        item = totals.setdefault(group, {
            "count": 0,
            "has_schema": bool(groups.get(group) and groups[group].get("definition")),
            "declared_reference_fields": reference_fields.get(group, 0),
            "examples": [],
        })
        item["count"] += 1
        if len(item["examples"]) < 8:
            item["examples"].append({"index": entry.index, "path": entry.path})
    return {"tag_count": len(entries), "groups": dict(sorted(totals.items()))}


def read_xbox_tag_region(map_path: Path):
    """Read an already-decompressed retail Xbox map and normalize its render header."""
    tools = Path(__file__).resolve().parents[1] / "submodules/halo-ps2/tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from halo2ps2 import mapinfo, tagindex

    header = mapinfo.read_header(map_path)
    if header.engine != 5 or map_path.stat().st_size != header.decompressed_size:
        raise SchemaWalkError("input must be a decompressed retail Xbox cache map")
    index = tagindex.TagIndex.read(map_path)
    with map_path.open("rb") as stream:
        stream.seek(header.tag_data_offset)
        image = bytearray(stream.read(header.tag_data_size))
    if len(image) != header.tag_data_size:
        raise SchemaWalkError("truncated Xbox tag region")
    # The PS2 renderer consumes HP2 geometry. CE's cache header keeps the tag
    # signature/table/scenario but must not expose Xbox D3D vertex/index tables.
    image[16:32] = bytes(16)
    return bytes(image), index.base, {
        "map": map_path.stem,
        "file_size": header.decompressed_size,
        "tag_data_offset": header.tag_data_offset,
        "tag_data_size": header.tag_data_size,
        "tag_count": index.header.tag_count,
        "scenario_tag_id": index.header.scenario_tag_id,
        "tag_table_pointer": index.header.tag_array_address,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", type=Path, help="decompressed retail Xbox cache map")
    parser.add_argument("--schema-manifest", required=True, type=Path)
    parser.add_argument("--file-data-policy", choices=("reject", "strip", "inventory"), default="reject",
                        help="strip/inventory are diagnostic only, not production resource policies")
    parser.add_argument("--unknown-group-policy", choices=("reject", "inventory"), default="reject",
                        help="inventory is diagnostic only; unsupported roots remain unconverted")
    parser.add_argument("--opaque-group", action="append", default=[], metavar="FOURCC",
                        help="preserve an audited no-schema group as opaque; repeat as needed")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.schema_manifest.read_text())
        image, base, source = read_xbox_tag_region(args.map)
        result = walk_tag_image(manifest, image, base, args.file_data_policy,
                                args.unknown_group_policy, args.opaque_group)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(2, f"schema walk failed: {error}\n")
    print(json.dumps({**source, "relocation_count": len(result.relocations),
                      "visited_bytes": result.visited_bytes,
                      "stripped_file_data_bytes": result.stripped_file_data_bytes,
                      "file_data_records": result.file_data_records,
                      "unsupported_groups": result.unsupported_groups,
                      "opaque_groups": result.opaque_groups,
                      "reference_target_counts": result.reference_target_counts}, sort_keys=True))


if __name__ == "__main__":
    main()
