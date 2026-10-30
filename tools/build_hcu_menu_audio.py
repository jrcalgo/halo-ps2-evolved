#!/usr/bin/env python3
"""Extract a PS2 menu sound bank from a user-owned Halo CE Xbox XISO."""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules" / "halo-ps2" / "tools"))
sys.path.insert(0, str(ROOT / "submodules" / "halo-64"))

from halo2ps2 import mapinfo  # noqa: E402
from halo2ps2.tagcache import CacheMap  # noqa: E402
from tools.n64.xiso import XboxDisc  # noqa: E402
from hcu_sound_bank import (  # noqa: E402
    ENTRY, ENTRY_SIZE, HEADER, MAGIC, VERSION, decode_xbox_adpcm,
    encode_vag, name_hash, sound_permutations, verify_bank,
)

SOUNDS = (
    (r"sound\music\title1\in", 26),
    (r"sound\music\title1\loops", 24),
    (r"sound\sfx\ui\cursor", 1),
    (r"sound\sfx\ui\forward", 1),
    (r"sound\sfx\ui\back", 1),
)


def linked_fragments(cache: CacheMap, tag, limit: int) -> list[dict]:
    """Follow one recording's Halo sound-permutation continuation chain."""
    data = cache.off(tag.data_addr)
    ranges, first_range = cache.reflexive(data, 0x98)
    if ranges < 1:
        raise ValueError(f"sound has no pitch ranges: {tag.path}")
    count, first_perm = cache.reflexive(first_range, 0x3C)
    fragments = []
    index = 0
    seen = set()
    while index != 0xFFFF and len(fragments) < limit:
        if index >= count or index in seen:
            raise ValueError(f"invalid sound continuation chain: {tag.path}")
        seen.add(index)
        base = first_perm + 124 * index
        size, _flags, offset = struct.unpack_from("<III", cache.buf, base + 64)
        if not size or offset + size > len(cache.buf):
            raise ValueError(f"invalid sound fragment: {tag.path}")
        fragments.append({"offset": offset, "size": size})
        index = struct.unpack_from("<H", cache.buf, base + 42)[0]
    if len(fragments) != limit or index != 0xFFFF:
        raise ValueError(f"unexpected sound chain length: {tag.path}")
    return fragments


def build(cache: CacheMap) -> tuple[bytes, list[dict]]:
    entries: list[dict] = []
    data = bytearray()
    for path, count in SOUNDS:
        tag = next(t for t in cache.tags if t.group == "snd!" and t.path == path)
        info, _permutations = sound_permutations(cache, tag)
        if info["compression"] != 1:
            raise ValueError(f"unexpected retail sound layout: {path}")
        permutations = linked_fragments(cache, tag, count)
        pcm: list[int] = []
        for permutation in permutations:
            start = permutation["offset"]
            raw = cache.buf[start:start + permutation["size"]]
            pcm.extend(decode_xbox_adpcm(raw, info["channels"]))
        encoded = encode_vag(pcm)
        offset = len(data)
        data += encoded
        data += b"\0" * (-len(data) % 16)
        entries.append({"path": path, "offset": offset, "bytes": len(encoded),
                        "samples": len(pcm), "rate": info["rate"]})
    entries_off = HEADER.size
    data_off = (entries_off + ENTRY_SIZE * len(entries) + 15) & ~15
    output = bytearray(HEADER.pack(MAGIC, VERSION, len(entries), entries_off,
                                   data_off, 0, len(data), 0))
    for entry in entries:
        output += ENTRY.pack(name_hash(entry["path"]), 0, 1, entry["rate"],
                             entry["samples"], data_off + entry["offset"],
                             entry["bytes"], 1.0, 0, 0)
    output += b"\0" * (data_off - len(output))
    output += data
    struct.pack_into("<I", output, 20, len(output) + 32)
    blob = bytes(output) + hashlib.sha256(output).digest()
    verify_bank(blob)
    return blob, entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hcu-menu-audio-") as folder:
        compressed = Path(folder) / "ui.map"
        decompressed = Path(folder) / "decompressed-ui.map"
        disc = XboxDisc(args.iso)
        try:
            disc.extract("maps/ui.map", compressed)
        finally:
            disc.close()
        mapinfo.decompress(compressed, decompressed)
        blob, entries = build(CacheMap(decompressed.read_bytes()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    for entry in entries:
        print(f"{entry['path']}: {entry['samples'] / entry['rate']:.2f}s, {entry['bytes']} bytes")
    print(f"{args.output}: {len(blob)} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
