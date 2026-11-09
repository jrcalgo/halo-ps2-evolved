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
    encode_vag, name_hash, resample, sound_permutations, verify_bank,
)

# Every piece of the retail title music (ui.map: looping sound sound\music\title1\title1 = start `in`, loop `loops`).
# A sound is several recordings: the permutations nobody names as their "next" each start a chain of fragments. `in` is
# one chain; `loops` holds three (the game picks one each time the loop comes round), which the bank carries as
# `loops`, `loops2` and `loops3` in tag order. The UI clicks are one fragment each.
MUSIC = (
    (r"sound\music\title1\in", (r"sound\music\title1\in",)),
    (r"sound\music\title1\loops",
     (r"sound\music\title1\loops", r"sound\music\title1\loops2", r"sound\music\title1\loops3")),
)
EFFECTS = (r"sound\sfx\ui\cursor", r"sound\sfx\ui\forward", r"sound\sfx\ui\back")
# SPU2 RAM this bank can fill (HCU_SPU_RAM_END - HCU_SPU_RAM_BASE less the 64 KB at the top that the music stream's
# rings use, HCU_STREAM_RESERVED_BYTES). The menu plays the music from disc (tools/build_hcu_menu_music.py) at the
# retail rate; this bank's copy is only the fallback when the stream file cannot be opened, so it is resampled to the
# highest rate that leaves room: the three loops alone are about 4 MB at the retail 44.1 kHz.
SPU_CAPACITY = 0x200000 - 0x5010 - 0x10000
RATE_STEP = 50


def chain_starts(cache: CacheMap, tag) -> list[int]:
    """Permutations no other permutation continues into: the first fragment of each recording, in tag order."""
    data = cache.off(tag.data_addr)
    _ranges, first_range = cache.reflexive(data, 0x98)
    count, first_perm = cache.reflexive(first_range, 0x3C)
    followed = set()
    for index in range(count):
        following = struct.unpack_from("<H", cache.buf, first_perm + 124 * index + 42)[0]
        if following != 0xFFFF:
            followed.add(following)
    return [index for index in range(count) if index not in followed]


def linked_fragments(cache: CacheMap, tag, start: int = 0) -> list[dict]:
    """Follow one recording's Halo sound-permutation continuation chain to its end."""
    data = cache.off(tag.data_addr)
    ranges, first_range = cache.reflexive(data, 0x98)
    if ranges < 1:
        raise ValueError(f"sound has no pitch ranges: {tag.path}")
    count, first_perm = cache.reflexive(first_range, 0x3C)
    fragments = []
    index = start
    seen = set()
    while index != 0xFFFF:
        if index >= count or index in seen:
            raise ValueError(f"invalid sound continuation chain: {tag.path}")
        seen.add(index)
        base = first_perm + 124 * index
        size, _flags, offset = struct.unpack_from("<III", cache.buf, base + 64)
        if not size or offset + size > len(cache.buf):
            raise ValueError(f"invalid sound fragment: {tag.path}")
        fragments.append({"offset": offset, "size": size})
        index = struct.unpack_from("<H", cache.buf, base + 42)[0]
    return fragments


def decode_recording(cache: CacheMap, tag, start: int) -> tuple[list[int], int]:
    info, _permutations = sound_permutations(cache, tag)
    if info["compression"] != 1:
        raise ValueError(f"unexpected retail sound layout: {tag.path}")
    pcm: list[int] = []
    for fragment in linked_fragments(cache, tag, start):
        raw = cache.buf[fragment["offset"]:fragment["offset"] + fragment["size"]]
        pcm.extend(decode_xbox_adpcm(raw, info["channels"]))
    return pcm, info["rate"]


def vag_bytes(samples: int) -> int:
    """Encoded size: one 16-byte block per 28 samples and the silent terminator block, kept 16-byte aligned."""
    return ((samples + 27) // 28 + 1) * 16


def fit_rate(recordings: list[tuple[int, int]], reserved: int) -> int:
    """The highest rate (a multiple of RATE_STEP, at most each source's own) at which every recording fits."""
    top = min(rate for _samples, rate in recordings)
    best = RATE_STEP
    for rate in range(RATE_STEP, top + 1, RATE_STEP):
        total = reserved + sum(vag_bytes(int(samples * min(rate, source) / source)) for samples, source in recordings)
        if total <= SPU_CAPACITY:
            best = rate
    return best


def build(cache: CacheMap) -> tuple[bytes, list[dict]]:
    by_path = {t.path: t for t in cache.tags if t.group == "snd!"}
    music: list[tuple[str, list[int], int]] = []
    for source, names in MUSIC:
        tag = by_path[source]
        starts = chain_starts(cache, tag)
        if len(starts) != len(names):
            raise ValueError(f"{source}: {len(starts)} recordings, expected {len(names)}")
        for name, start in zip(names, starts):
            pcm, rate = decode_recording(cache, by_path[source], start)
            music.append((name, pcm, rate))
    effects = []
    for path in EFFECTS:
        pcm, rate = decode_recording(cache, by_path[path], 0)
        effects.append((path, pcm, rate))
    reserved = sum(vag_bytes(len(pcm)) for _path, pcm, _rate in effects)
    target = fit_rate([(len(pcm), rate) for _name, pcm, rate in music], reserved)
    entries: list[dict] = []
    data = bytearray()
    for path, pcm, rate in music + effects:
        out_rate = min(target, rate) if (path, pcm, rate) in music else rate
        if out_rate < rate:
            pcm = resample(pcm, rate, out_rate)
        encoded = encode_vag(pcm)
        offset = len(data)
        data += encoded
        data += b"\0" * (-len(data) % 16)
        entries.append({"path": path, "offset": offset, "bytes": len(encoded),
                        "samples": len(pcm), "rate": out_rate})
    if len(data) > SPU_CAPACITY:
        raise ValueError(f"menu audio is {len(data)} bytes, SPU2 RAM holds {SPU_CAPACITY}")
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
