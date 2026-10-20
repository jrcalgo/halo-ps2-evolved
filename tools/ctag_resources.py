"""CRNG v1 exact byte-range allowlist for one decompressed retail map file."""
from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib

MAGIC = b"CRNG"
VERSION = 1
HEADER = struct.Struct("<4s8I")
RECORD = struct.Struct("<II")
MAX_INTERVALS = 1_000_000


class ResourceIndexError(ValueError):
    pass


@dataclass(frozen=True)
class ResourceIndex:
    file_length: int
    tag_data_offset: int
    tag_data_size: int
    intervals: tuple[tuple[int, int], ...]

    def allows(self, offset: int, size: int) -> bool:
        """True only if a nonempty request is wholly covered by one indexed range."""
        if not isinstance(offset, int) or not isinstance(size, int):
            return False
        if offset < 0 or size <= 0 or offset > self.file_length or size > self.file_length - offset:
            return False
        lo, hi = 0, len(self.intervals)
        while lo < hi:
            mid = lo + (hi - lo) // 2
            start, end = self.intervals[mid]
            if offset < start:
                hi = mid
            elif offset >= end:
                lo = mid + 1
            else:
                return offset + size <= end
        return False


def _validate(file_length: int, tag_data_offset: int, tag_data_size: int,
              intervals: tuple[tuple[int, int], ...]) -> None:
    if not 0 < file_length <= 0xFFFFFFFF:
        raise ResourceIndexError("file length must be a nonzero u32")
    if (tag_data_offset < 0 or tag_data_size < 0 or tag_data_offset > file_length or
            tag_data_size > file_length - tag_data_offset):
        raise ResourceIndexError("tag-data extent is outside the source file")
    if len(intervals) > MAX_INTERVALS:
        raise ResourceIndexError("too many resource intervals")
    previous_end = -1
    tag_end = tag_data_offset + tag_data_size
    for offset, size in intervals:
        if (offset < 0 or size <= 0 or offset > file_length or
                size > file_length - offset):
            raise ResourceIndexError("resource interval is outside the source file")
        end = offset + size
        if offset <= previous_end:
            raise ResourceIndexError("resource intervals overlap, touch, or are not sorted")
        if offset < tag_end and tag_data_offset < end:
            raise ResourceIndexError("resource interval overlaps original tag-data extent")
        previous_end = end


def encode(file_length: int, tag_data_offset: int, tag_data_size: int,
           intervals: list[tuple[int, int]] | tuple[tuple[int, int], ...]) -> bytes:
    """Encode canonical (offset, size) rows with CRC and source/tag bounds."""
    rows = tuple((int(offset), int(size)) for offset, size in intervals)
    _validate(file_length, tag_data_offset, tag_data_size, rows)
    body = b"".join(RECORD.pack(offset, size) for offset, size in rows)
    return HEADER.pack(MAGIC, VERSION, len(rows), file_length, tag_data_offset,
                       tag_data_size, HEADER.size, zlib.crc32(body) & 0xFFFFFFFF,
                       0) + body


def decode(payload: bytes, *, expected_file_length: int,
           expected_tag_data_offset: int, expected_tag_data_size: int) -> ResourceIndex:
    if len(payload) < HEADER.size:
        raise ResourceIndexError("truncated CRNG header")
    (magic, version, count, file_length, tag_offset, tag_size,
     records_offset, checksum, reserved) = HEADER.unpack_from(payload)
    if magic != MAGIC:
        raise ResourceIndexError("bad CRNG magic")
    if version != VERSION or reserved != 0:
        raise ResourceIndexError("unsupported CRNG version or nonzero reserved field")
    if count > MAX_INTERVALS or records_offset != HEADER.size:
        raise ResourceIndexError("invalid CRNG interval table")
    if count > (len(payload) - HEADER.size) // RECORD.size or len(payload) != HEADER.size + count * RECORD.size:
        raise ResourceIndexError("CRNG payload length does not match interval count")
    if (file_length != expected_file_length or tag_offset != expected_tag_data_offset or
            tag_size != expected_tag_data_size):
        raise ResourceIndexError("CRNG source file or tag extent identity mismatch")
    body = payload[HEADER.size:]
    if zlib.crc32(body) & 0xFFFFFFFF != checksum:
        raise ResourceIndexError("CRNG interval checksum mismatch")
    encoded_rows = tuple(RECORD.unpack_from(body, i * RECORD.size) for i in range(count))
    _validate(file_length, tag_offset, tag_size, encoded_rows)
    intervals = tuple((offset, offset + size) for offset, size in encoded_rows)
    return ResourceIndex(file_length, tag_offset, tag_size, intervals)


def from_audit(map_audit: dict) -> bytes:
    """Create CRNG bytes from one row of audit_ctag_retail_maps output."""
    resources = map_audit["map_file_resources"]
    sources = map_audit["resource_interval_index"]
    if set(sources) != {"map"}:
        raise ResourceIndexError("CRNG v1 supports exactly the decompressed map source")
    intervals = [(start, end - start) for start, end in sources["map"]["intervals"]]
    return encode(map_audit["file_size"], map_audit["tag_data_offset"],
                  map_audit["tag_data_size"],
                  intervals)
