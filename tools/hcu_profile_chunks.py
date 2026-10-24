"""Deterministic HCP1 independently addressable HCU profile chunk envelope."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct

MAGIC = b"HCP1"
VERSION = 1
HEADER = struct.Struct("<4s7I")
RECORD = struct.Struct("<4I32s")
CHUNK_TYPES = {"ce": (1, 0), "media": (2, None), "sound_meta": (3, 0)}
ALIGNMENT = 16
MAX_CHUNKS = 65536


class ProfileError(ValueError):
    pass


def encode(profile_id: int, chunks: dict[str, bytes] | dict[tuple[int, int], bytes]) -> bytes:
    if not 0 < profile_id <= 0xffffffff:
        raise ProfileError("profile id must be a nonzero u32")
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
    if (1, 0) not in normalized or (3, 0) not in normalized or len(normalized) > MAX_CHUNKS:
        raise ProfileError("CE and sound metadata roots are required; at most 65536 chunks")
    ordered = sorted(normalized.items())
    if any((kind not in (1, 2, 3) or not 0 <= kind <= 0xffffffff or
            not 0 <= cid <= 0xffffffff or (kind != 2 and cid != 0))
           for (kind, cid), _data in ordered):
        raise ProfileError("invalid chunk type/id")
    rows = bytearray()
    payload = bytearray()
    dir_offset = HEADER.size
    data_offset = dir_offset + len(ordered) * RECORD.size
    for (kind, chunk_id), raw_blob in ordered:
        blob = bytes(raw_blob)
        if not blob:
            raise ProfileError(f"chunk {kind}:{chunk_id} must be nonempty")
        offset = (data_offset + len(payload) + ALIGNMENT - 1) & ~(ALIGNMENT - 1)
        payload.extend(b"\0" * (offset - data_offset - len(payload)))
        rows.extend(RECORD.pack(kind, chunk_id, offset, len(blob), hashlib.sha256(blob).digest()))
        payload.extend(blob)
    total = data_offset + len(payload)
    header = HEADER.pack(MAGIC, VERSION, HEADER.size, profile_id, len(ordered),
                         dir_offset, len(rows), total)
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
