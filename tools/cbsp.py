"""Bounded CBSP v1 envelope for schema-walked retail CE structure BSPs.

CBSP keeps CE's BSP image and records its two pointer domains separately:
internal pointers target the BSP image; typed tag-reference names target the
materialized CTAG image. The header also binds the exact retail source-file
extent so CE's cache reader can substitute only that BSP read. It does not omit render data or establish that a BSP
fits the PS2 arena. The source-schema walk must be performed before encoding.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib


MAGIC = b"CBSP"
VERSION = 1
HEADER = struct.Struct("<4s8I")
MAX_RELOCS = 1_000_000
NO_SOURCE_OFFSET = 0xFFFFFFFF
CATALOG_MAGIC = b"CBIX"
CATALOG_HEADER = struct.Struct("<4s6I")
CATALOG_RECORD = struct.Struct("<II4sI")


@dataclass(frozen=True)
class CatalogEntry:
    file_offset: int
    file_size: int
    section_tag: str


def encode_catalog(entries, *, file_length: int) -> bytes:
    """Encode the bounded map index mapping each retail BSP extent to an HP2 section."""
    entries = tuple(entries)
    if not 0 < file_length <= 0xFFFFFFFF:
        raise CbspError("CBSP catalog file length is invalid")
    if not entries or len(entries) > 32:
        raise CbspError("CBSP catalog count is outside HP2 section bounds")
    rows = bytearray()
    prior_end = 0
    tags = set()
    for entry in entries:
        tag = entry.section_tag.encode("ascii", errors="strict")
        if len(tag) != 4 or any(byte < 0x20 or byte > 0x7E for byte in tag):
            raise CbspError("CBSP catalog section tag must be four printable bytes")
        if (entry.file_size <= 0 or entry.file_offset < prior_end or
                entry.file_offset > file_length or
                entry.file_size > file_length - entry.file_offset):
            raise CbspError("CBSP catalog extent is invalid, overlapping, or unsorted")
        if tag in tags or tag in (b"CTAG", b"CRNG", b"CBIX"):
            raise CbspError("CBSP catalog section tag is reserved or repeated")
        tags.add(tag)
        rows.extend(CATALOG_RECORD.pack(entry.file_offset, entry.file_size, tag, 0))
        prior_end = entry.file_offset + entry.file_size
    return CATALOG_HEADER.pack(CATALOG_MAGIC, 1, len(entries), file_length,
                               CATALOG_HEADER.size,
                               zlib.crc32(rows) & 0xFFFFFFFF, 0) + rows


def decode_catalog(payload: bytes, *, expected_file_length: int) -> tuple[CatalogEntry, ...]:
    if len(payload) < CATALOG_HEADER.size:
        raise CbspError("truncated CBSP catalog")
    magic, version, count, file_length, records_offset, checksum, reserved = \
        CATALOG_HEADER.unpack_from(payload)
    if (magic != CATALOG_MAGIC or version != 1 or reserved or
            records_offset != CATALOG_HEADER.size or
            file_length != expected_file_length or count == 0 or count > 32 or
            len(payload) != records_offset + count * CATALOG_RECORD.size):
        raise CbspError("invalid CBSP catalog header/length")
    rows = payload[records_offset:]
    if zlib.crc32(rows) & 0xFFFFFFFF != checksum:
        raise CbspError("CBSP catalog checksum mismatch")
    entries = []
    prior_end = 0
    tags = set()
    for index in range(count):
        offset, size, tag_bytes, row_reserved = CATALOG_RECORD.unpack_from(
            rows, index * CATALOG_RECORD.size)
        try:
            tag = tag_bytes.decode("ascii")
        except UnicodeDecodeError as error:
            raise CbspError("CBSP catalog tag is not ASCII") from error
        if (row_reserved or any(byte < 0x20 or byte > 0x7E for byte in tag_bytes) or
                size == 0 or offset < prior_end or offset > file_length or
                size > file_length - offset or tag in tags or
                tag in ("CTAG", "CRNG", "CBIX")):
            raise CbspError("invalid, repeated, overlapping, or unsorted CBSP entry")
        tags.add(tag)
        entries.append(CatalogEntry(offset, size, tag))
        prior_end = offset + size
    return tuple(entries)


class CbspError(ValueError):
    """Malformed or unsupported CBSP v1 payload."""


@dataclass(frozen=True)
class CbspImage:
    image: bytes
    relocations: tuple[int, ...]
    tag_relocations: tuple[tuple[int, int], ...]
    source_file_offset: int
    source_file_size: int

    def materialize(self, bsp_base: int, tag_base: int, tag_size: int) -> bytes:
        _validate(self.image, self.relocations, self.tag_relocations)
        if not 0 < bsp_base <= 0xFFFFFFFF or not 0 < tag_base <= 0xFFFFFFFF:
            raise CbspError("materialization bases must be nonzero 32-bit addresses")
        if (bsp_base & 15) or (tag_base & 15):
            raise CbspError("materialization bases must be 16-byte aligned")
        if bsp_base + len(self.image) > 0x1_0000_0000:
            raise CbspError("BSP image wraps the 32-bit address space")
        if tag_size < 0 or tag_base + tag_size > 0x1_0000_0000:
            raise CbspError("tag image extent wraps the 32-bit address space")
        result = bytearray(self.image)
        for field in self.relocations:
            target = struct.unpack_from("<I", result, field)[0]
            if target:
                address = bsp_base + target
                if address > 0xFFFFFFFF:
                    raise CbspError("BSP pointer overflows the 32-bit address space")
                struct.pack_into("<I", result, field, address)
        for field, target in self.tag_relocations:
            if target >= tag_size:
                raise CbspError("tag-name relocation target leaves CTAG image")
            address = tag_base + target
            if address > 0xFFFFFFFF:
                raise CbspError("tag-name pointer overflows the 32-bit address space")
            struct.pack_into("<I", result, field, address)
        return bytes(result)


def _validate(image: bytes, relocations, tag_relocations) -> None:
    if len(image) < 24 or image[20:24] != b"psbs":
        raise CbspError("bad CE structure-BSP header signature")
    if len(relocations) + len(tag_relocations) > MAX_RELOCS:
        raise CbspError("combined relocation count exceeds configured bound")
    slots = []
    for field in relocations:
        if not isinstance(field, int) or field < 0 or field > len(image) - 4:
            raise CbspError("BSP relocation field leaves image")
        target = struct.unpack_from("<I", image, field)[0]
        if target and target >= len(image):
            raise CbspError("BSP relocation target leaves image")
        slots.append(field)
    for field, target in tag_relocations:
        if (not isinstance(field, int) or field < 0 or field > len(image) - 4 or
                not isinstance(target, int) or target < 0 or target > 0xFFFFFFFF):
            raise CbspError("tag-reference relocation is out of bounds")
        if struct.unpack_from("<I", image, field)[0] != target:
            raise CbspError("tag-reference relocation does not match image value")
        slots.append(field)
    if len(set(slots)) != len(slots):
        raise CbspError("relocation domains reuse a pointer field")


def encode(image: bytes, relocations, tag_relocations, *,
           source_file_offset: int = NO_SOURCE_OFFSET,
           source_file_size: int = 0) -> bytes:
    """Encode normalized offset pointers and their schema-derived slot tables."""
    relocations = tuple(relocations)
    tag_relocations = tuple(tag_relocations)
    _validate(image, relocations, tag_relocations)
    if tuple(sorted(relocations)) != relocations:
        raise CbspError("BSP relocation fields are not sorted")
    if tuple(sorted(tag_relocations)) != tag_relocations:
        raise CbspError("tag-reference relocations are not sorted")
    if source_file_offset == NO_SOURCE_OFFSET:
        if source_file_size != 0:
            raise CbspError("unknown source offset must have zero source size")
    elif (not isinstance(source_file_offset, int) or source_file_offset < 0 or
          source_file_offset > 0xFFFFFFFF or source_file_size != len(image) or
          source_file_offset + source_file_size > 0x1_0000_0000):
        raise CbspError("source BSP file extent is invalid")
    # One canonical table contains (field, domain, target) entries. Domain 0
    # targets this BSP; domain 1 targets CTAG, so ordering is globally checked.
    rows = []
    for field in relocations:
        rows.append((field, 0, struct.unpack_from("<I", image, field)[0]))
    for field, target in tag_relocations:
        rows.append((field, 1, target))
    rows.sort()
    if len({row[0] for row in rows}) != len(rows):
        raise CbspError("relocation domains reuse a pointer field")
    table_offset = HEADER.size + len(image)
    table = b"".join(struct.pack("<IB3xI", *row) for row in rows)
    header = HEADER.pack(MAGIC, VERSION, len(image), len(rows), table_offset,
                         zlib.crc32(image) & 0xFFFFFFFF, source_file_offset,
                         source_file_size, 0)
    return header + image + table


def decode(payload: bytes, *, max_image_size: int) -> CbspImage:
    if len(payload) < HEADER.size:
        raise CbspError("truncated CBSP header")
    (magic, version, image_size, count, table_offset, checksum,
     source_file_offset, source_file_size, reserved) = HEADER.unpack_from(payload)
    if magic != MAGIC:
        raise CbspError("bad CBSP magic")
    if version != VERSION:
        raise CbspError(f"unsupported CBSP version {version}")
    if reserved:
        raise CbspError("nonzero CBSP reserved field")
    if source_file_offset == NO_SOURCE_OFFSET:
        if source_file_size != 0:
            raise CbspError("unknown source offset must have zero source size")
    elif (source_file_size != image_size or
          source_file_offset + source_file_size > 0x1_0000_0000):
        raise CbspError("source BSP file extent is invalid")
    if image_size < 24 or image_size > max_image_size:
        raise CbspError("CBSP image size is outside configured bound")
    image_end = HEADER.size + image_size
    if table_offset != image_end or count > MAX_RELOCS:
        raise CbspError("CBSP relocation table offset/count is invalid")
    if count * 12 != len(payload) - image_end:
        raise CbspError("CBSP payload length does not match relocation count")
    image = payload[HEADER.size:image_end]
    if zlib.crc32(image) & 0xFFFFFFFF != checksum:
        raise CbspError("CBSP image checksum mismatch")
    internal, external = [], []
    previous_field = -1
    for index in range(count):
        field, domain, target = struct.unpack_from("<IB3xI", payload, image_end + index * 12)
        if field > image_size - 4:
            raise CbspError("CBSP relocation field leaves image")
        if field <= previous_field:
            raise CbspError("CBSP relocation fields are not strictly sorted")
        previous_field = field
        if domain == 0:
            if struct.unpack_from("<I", image, field)[0] != target:
                raise CbspError("BSP relocation target does not match image value")
            internal.append(field)
        elif domain == 1:
            if struct.unpack_from("<I", image, field)[0] != target:
                raise CbspError("tag relocation target does not match image value")
            external.append((field, target))
        else:
            raise CbspError("unsupported CBSP relocation domain")
    _validate(image, tuple(internal), tuple(external))
    return CbspImage(image, tuple(internal), tuple(external),
                     source_file_offset, source_file_size)
