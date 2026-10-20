"""Bounded reader/writer for the PS2 CTAG v1 tag-image envelope.

The image is a little-endian CE tag image whose pointer fields contain offsets
until load time. This module validates the wire representation and requires
relocations for the fixed CE header and tag-instance pointers, then can
materialize pointers into a caller-selected 32-bit EE address. It deliberately
does not convert retail tags or claim that nested fields are schema-valid.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
import sys
from pathlib import Path
import zlib

MAGIC = b"CTAG"
VERSION = 1
HEADER = struct.Struct("<4s12I")
IMAGE_HEADER = struct.Struct("<9I")
TAG_SIGNATURE = 0x74616773  # retail Xbox/CE u32; little-endian bytes b"sgat"
HEADER_SIZE = HEADER.size
MAX_RELOCS = 1_000_000


class CtagError(ValueError):
    """Malformed or unsupported CTAG v1 payload."""


def _hp2_module():
    tools = Path(__file__).resolve().parents[1] / "submodules/halo-ps2/tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from halo2ps2 import hp2
    return hp2


@dataclass(frozen=True)
class CtagImage:
    image: bytes
    relocations: tuple[int, ...]
    scenario_tag_index: int

    def materialize(self, base_address: int) -> bytes:
        """Return an image with bounded 32-bit offsets rebased to EE pointers."""
        _validate_image(self.image, self.relocations, self.scenario_tag_index)
        if not 0 < base_address <= 0xFFFFFFFF:
            raise CtagError("base address is outside the 32-bit EE address space")
        end = base_address + len(self.image)
        if end > 0x1_0000_0000:
            raise CtagError("materialized image wraps the 32-bit EE address space")
        result = bytearray(self.image)
        for offset in self.relocations:
            (target,) = struct.unpack_from("<I", result, offset)
            if target == 0:
                continue
            if target >= len(result):
                raise CtagError(f"relocation target {target:#x} is outside image")
            absolute = base_address + target
            if absolute > 0xFFFFFFFF:
                raise CtagError("relocation target overflows the 32-bit EE address space")
            struct.pack_into("<I", result, offset, absolute)
        return bytes(result)


def encode(image: bytes, relocations: list[int] | tuple[int, ...], *,
           scenario_tag_index: int, flags: int = 0) -> bytes:
    """Create a deterministic CTAG v1 payload from a pre-relocation image."""
    if flags != 0:
        raise CtagError("unsupported CTAG flags")
    _validate_image(image, tuple(relocations), scenario_tag_index)
    ordered = tuple(relocations)
    reloc_offset = HEADER_SIZE + len(image)
    header = HEADER.pack(MAGIC, VERSION, flags, len(image), len(ordered),
                         reloc_offset, 0, scenario_tag_index,
                         zlib.crc32(image) & 0xFFFFFFFF, 0, 0, 0, 0)
    return header + image + b"".join(struct.pack("<I", item) for item in ordered)


def decode(payload: bytes, *, max_image_size: int, max_relocations: int = MAX_RELOCS) -> CtagImage:
    """Parse CTAG v1 without allocating from untrusted declared sizes."""
    if len(payload) < HEADER_SIZE:
        raise CtagError("truncated CTAG header")
    (magic, version, flags, image_size, reloc_count, reloc_offset,
     tag_header_offset, scenario_tag_index, checksum, *reserved) = HEADER.unpack_from(payload)
    if magic != MAGIC:
        raise CtagError("bad CTAG magic")
    if version != VERSION:
        raise CtagError(f"unsupported CTAG version {version}")
    if flags != 0:
        raise CtagError("unsupported CTAG flags")
    if any(reserved):
        raise CtagError("nonzero CTAG reserved field")
    if tag_header_offset != 0:
        raise CtagError("CTAG v1 tag header must begin at image offset zero")
    if image_size < IMAGE_HEADER.size or image_size > max_image_size:
        raise CtagError("CTAG image size is outside the configured bound")
    if reloc_count > max_relocations:
        raise CtagError("CTAG relocation count exceeds configured bound")
    image_end = HEADER_SIZE + image_size
    reloc_bytes = reloc_count * 4
    expected_reloc_offset = image_end
    if reloc_offset != expected_reloc_offset:
        raise CtagError("CTAG relocation table is not immediately after the image")
    if image_end > len(payload) or reloc_bytes != len(payload) - image_end:
        raise CtagError("CTAG payload length does not match image and relocation sizes")
    image = payload[HEADER_SIZE:image_end]
    if (zlib.crc32(image) & 0xFFFFFFFF) != checksum:
        raise CtagError("CTAG image checksum mismatch")
    relocations = tuple(struct.unpack_from(f"<{reloc_count}I", payload, image_end)) if reloc_count else ()
    _validate_image(image, relocations, scenario_tag_index)
    return CtagImage(image, relocations, scenario_tag_index)


def pack_hp2(name: str, image: bytes, relocations: list[int] | tuple[int, ...], *,
             scenario_tag_index: int, sections: list[tuple[str, bytes]] | None = None,
             compress: bool = True) -> bytes:
    """Package CTAG with the existing HP2 sections for one converted map.

    ``sections`` may supply BSP/MODL/TEXS/etc. payloads already produced by
    the PS2 converters. CTAG ownership and conversion remain separate from
    those presentation sections.
    """
    others = list(sections or ())
    if any(tag == "CTAG" for tag, _data in others):
        raise CtagError("CTAG section is supplied by the CTAG image arguments")
    payload = encode(image, relocations, scenario_tag_index=scenario_tag_index)
    try:
        return _hp2_module().build(name, [("CTAG", payload), *others], compress=compress)
    except (ValueError, UnicodeError, struct.error) as error:
        raise CtagError(f"cannot build HP2 map pack: {error}") from error


def unpack_hp2(pack_bytes: bytes, *, max_image_size: int,
               max_relocations: int = MAX_RELOCS) -> tuple[str, CtagImage]:
    """Read and CRC-check CTAG from an HP2 pack using the production parser."""
    try:
        pack = _hp2_module().parse(pack_bytes)
        payload = pack.read("CTAG")
    except (ValueError, KeyError) as error:
        raise CtagError(f"cannot read CTAG HP2 section: {error}") from error
    return pack.name, decode(payload, max_image_size=max_image_size,
                              max_relocations=max_relocations)


def _validate_image(image: bytes, relocations: tuple[int, ...], scenario_tag_index: int) -> None:
    if len(image) < IMAGE_HEADER.size:
        raise CtagError("CE tag image is shorter than its header")
    if not 0 <= scenario_tag_index <= 0xFFFFFFFF:
        raise CtagError("scenario tag index is not a u32")
    (_table, image_scenario, _checksum, tag_count, vertex_count, _vertices,
     index_count, _indices, signature) = IMAGE_HEADER.unpack_from(image)
    if signature != TAG_SIGNATURE:
        raise CtagError("bad CE tag-image signature")
    if image_scenario != scenario_tag_index:
        raise CtagError("CTAG scenario index disagrees with the CE tag header")
    if tag_count == 0 or (image_scenario & 0xFFFF) >= tag_count:
        raise CtagError("scenario datum index is outside the tag table")
    table_bytes = tag_count * 32
    if _table < IMAGE_HEADER.size or _table & 3 or _table > len(image) or table_bytes > len(image) - _table:
        raise CtagError("CE tag-instance table is outside image")
    if not relocations or relocations[0] != 0:
        raise CtagError("tag-instance table pointer is missing from relocations")
    required_pointer_fields = {0, 20, 28}
    for tag_index in range(tag_count):
        instance = _table + tag_index * 32
        required_pointer_fields.update((instance + 16, instance + 20))
    if not required_pointer_fields.issubset(relocations):
        raise CtagError("header or tag-instance pointer is missing from relocations")
    if vertex_count and _vertices == 0 or index_count and _indices == 0:
        raise CtagError("nonempty render-buffer table has a null pointer")
    previous = -1
    for offset in relocations:
        if offset <= previous:
            raise CtagError("relocations must be strictly increasing and unique")
        if offset & 3 or offset > len(image) - 4:
            raise CtagError("relocation field is unaligned or outside image")
        (target,) = struct.unpack_from("<I", image, offset)
        if target != 0 and target >= len(image):
            raise CtagError("relocation target is outside image")
        previous = offset
