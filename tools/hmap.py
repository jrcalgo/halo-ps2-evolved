"""HMAP v1 source-identity metadata stored inside a converted map HP2."""
from __future__ import annotations

from dataclasses import dataclass
import re
import struct

MAGIC = b"HMAP"
VERSION = 1
NAME_BYTES = 16
HEADER = struct.Struct("<4s5I32s16s")


class HmapError(ValueError):
    pass


@dataclass(frozen=True)
class MapIdentity:
    map_name: str
    file_length: int
    tag_data_offset: int
    tag_data_size: int
    source_sha256: bytes


def encode(map_name: str, file_length: int, tag_data_offset: int,
           tag_data_size: int, source_sha256: bytes) -> bytes:
    try:
        name = map_name.encode("ascii")
    except UnicodeEncodeError as error:
        raise HmapError("map name must be ASCII") from error
    if not re.fullmatch(rb"[a-z0-9_-]{1,15}", name):
        raise HmapError("map name is not canonical")
    if not 0 < file_length <= 0xFFFFFFFF:
        raise HmapError("file length must be a nonzero u32")
    if (tag_data_offset < 0 or tag_data_size <= 0 or
            tag_data_offset > file_length or
            tag_data_size > file_length - tag_data_offset):
        raise HmapError("tag extent is outside source map")
    if not isinstance(source_sha256, bytes) or len(source_sha256) != 32:
        raise HmapError("source SHA-256 must be exactly 32 bytes")
    return HEADER.pack(MAGIC, VERSION, HEADER.size, file_length,
                       tag_data_offset, tag_data_size, source_sha256,
                       name + bytes(NAME_BYTES - len(name)))


def decode(payload: bytes, *, expected_map_name: str | None = None) -> MapIdentity:
    if len(payload) != HEADER.size:
        raise HmapError("HMAP payload has a noncanonical size")
    (magic, version, record_size, file_length, tag_offset, tag_size,
     source_sha256, name_field) = HEADER.unpack(payload)
    if magic != MAGIC:
        raise HmapError("bad HMAP magic")
    if version != VERSION or record_size != HEADER.size:
        raise HmapError("unsupported HMAP version or record size")
    terminator = name_field.find(b"\0")
    if terminator <= 0 or any(name_field[terminator:]):
        raise HmapError("HMAP name is not canonically terminated")
    try:
        name = name_field[:terminator].decode("ascii")
    except UnicodeDecodeError as error:
        raise HmapError("HMAP name is not ASCII") from error
    if not re.fullmatch(r"[a-z0-9_-]{1,15}", name):
        raise HmapError("HMAP name is not canonical")
    if expected_map_name is not None and name != expected_map_name:
        raise HmapError("HMAP map name does not match resolver")
    # Reuse the writer's bounds and canonical-name checks on untrusted bytes.
    encode(name, file_length, tag_offset, tag_size, source_sha256)
    return MapIdentity(name, file_length, tag_offset, tag_size, source_sha256)
