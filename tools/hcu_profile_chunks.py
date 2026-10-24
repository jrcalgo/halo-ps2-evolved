"""Deterministic HCP1/HCP2 HCU profile chunk envelope writers."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct

MAGIC_V1 = b"HCP1"
MAGIC = b"HCP2"
VERSION_V1 = 1
VERSION = 2
HEADER = struct.Struct("<4s7I")
V1_RECORD = struct.Struct("<4I32s")
V2_RECORD = struct.Struct("<8I32s32s")
RECORD = V2_RECORD
CHUNK_TYPES = {"ce": (1, 0), "media": (2, None), "sound_meta": (3, 0)}
# C3 render chunks (opt-in). Keyed by the selected BSP index so each BSPS, TEXS
# and LMn triple is addressable per structure BSP. Kinds 1 and 3 are unkeyed.
CHUNK_BSPS, CHUNK_TEXS, CHUNK_LIGHTMAP = 4, 5, 6
KEYED_KINDS = frozenset({2, CHUNK_BSPS, CHUNK_TEXS, CHUNK_LIGHTMAP})
KNOWN_KINDS = frozenset({1, 2, 3}) | frozenset({CHUNK_BSPS, CHUNK_TEXS, CHUNK_LIGHTMAP})


def chunk_kind_valid(kind: int, chunk_id: int) -> bool:
    """Mirror of hcu_asset_chunk_id_valid: known kind, id zero unless keyed."""
    if kind not in KNOWN_KINDS:
        return False
    return kind in KEYED_KINDS or chunk_id == 0
ALIGNMENT = 16
MAX_CHUNKS = 65536
MAX_MEDIA_CHUNK_BYTES = 65536
MAX_SEGMENT_BYTES = 65536


class ProfileError(ValueError):
    pass


def _normalize(chunks):
    normalized = {}
    if all(isinstance(key, str) for key in chunks):
        if not {"ce", "media", "sound_meta"}.issubset(chunks):
            raise ProfileError("ce, media, and sound_meta root chunks are required")
        normalized[(1, 0)] = chunks["ce"]
        normalized[(3, 0)] = chunks["sound_meta"]
        media = chunks["media"]
        if isinstance(media, dict):
            normalized.update({(2, int(k)): v for k, v in media.items()})
        else:
            normalized[(2, 0)] = media
    else:
        normalized = {(int(kind), int(cid)): data for (kind, cid), data in chunks.items()}
    if (1, 0) not in normalized or (3, 0) not in normalized:
        raise ProfileError("CE and sound metadata roots are required")
    ordered = sorted(normalized.items())
    if any(not chunk_kind_valid(kind, cid) or not 0 <= kind <= 0xffffffff or
           not 0 <= cid <= 0xffffffff
           for (kind, cid), _data in ordered):
        raise ProfileError("invalid chunk type/id")
    if len(ordered) > MAX_CHUNKS:
        raise ProfileError("at most 65536 logical chunks")
    result = []
    for (kind, cid), raw in ordered:
        blob = bytes(raw)
        if not blob:
            raise ProfileError(f"chunk {kind}:{cid} must be nonempty")
        result.append(((kind, cid), blob))
    return result


def encode(profile_id: int, chunks: dict[str, bytes] | dict[tuple[int, int], bytes], *, version: int = 2) -> bytes:
    if not 0 < profile_id <= 0xffffffff:
        raise ProfileError("profile id must be a nonzero u32")
    if version not in (1, 2):
        raise ProfileError("version must be 1 or 2")
    logical = _normalize(chunks)
    rows, payload = bytearray(), bytearray()
    directory_offset = HEADER.size
    if version == 1:
        if any(kind == 2 and len(blob) > MAX_MEDIA_CHUNK_BYTES for ((kind, _), blob) in logical):
            raise ProfileError(f"HCP1 media chunks cannot exceed {MAX_MEDIA_CHUNK_BYTES} bytes")
        data_offset = directory_offset + len(logical) * V1_RECORD.size
        for (kind, cid), blob in logical:
            offset = (data_offset + len(payload) + ALIGNMENT - 1) & ~(ALIGNMENT - 1)
            payload.extend(b"\0" * (offset - data_offset - len(payload)))
            rows.extend(V1_RECORD.pack(kind, cid, offset, len(blob), hashlib.sha256(blob).digest()))
            payload.extend(blob)
        header = HEADER.pack(MAGIC_V1, 1, HEADER.size, profile_id, len(logical), directory_offset,
                             len(rows), data_offset + len(payload))
        return header + rows + payload
    segments = []
    for (kind, cid), blob in logical:
        count = (len(blob) + MAX_SEGMENT_BYTES - 1) // MAX_SEGMENT_BYTES
        whole_digest = hashlib.sha256(blob).digest()
        for index in range(count):
            part = blob[index * MAX_SEGMENT_BYTES:(index + 1) * MAX_SEGMENT_BYTES]
            segments.append((kind, cid, index, count, len(blob), index * MAX_SEGMENT_BYTES,
                             part, hashlib.sha256(part).digest(), whole_digest))
    if len(segments) > MAX_CHUNKS:
        raise ProfileError("at most 65536 physical segments")
    data_offset = directory_offset + len(segments) * V2_RECORD.size
    for kind, cid, index, count, logical_size, logical_offset, blob, seg_sha, whole_sha in segments:
        offset = (data_offset + len(payload) + ALIGNMENT - 1) & ~(ALIGNMENT - 1)
        payload.extend(b"\0" * (offset - data_offset - len(payload)))
        rows.extend(V2_RECORD.pack(kind, cid, offset, len(blob), logical_offset, logical_size,
                                   index, count, seg_sha, whole_sha))
        payload.extend(blob)
    header = HEADER.pack(MAGIC, VERSION, HEADER.size, profile_id, len(segments), directory_offset,
                         len(rows), data_offset + len(payload))
    return header + rows + payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile_id", type=lambda x: int(x, 0))
    parser.add_argument("ce", type=Path)
    parser.add_argument("media", type=Path)
    parser.add_argument("sound_meta", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(encode(args.profile_id, {
        "ce": args.ce.read_bytes(), "media": args.media.read_bytes(),
        "sound_meta": args.sound_meta.read_bytes()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
