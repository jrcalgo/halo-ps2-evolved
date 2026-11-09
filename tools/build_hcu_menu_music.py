#!/usr/bin/env python3
"""Extract the retail title music from a user-owned Halo CE Xbox XISO as a stereo stream for the PS2 menu.

The menu plays it from disc through two SPU2 voices (hcu_spu_stream.c) at the retail 44.1 kHz instead of holding it in
SPU2 RAM. File "HMS1" (little endian):

  header  32 bytes: "HMS1", version 1, rate, channels (2), piece count, table offset (32), data offset, file size
  table   16 bytes a piece: file offset of its data, blocks per channel, samples per channel, 0
  data    a piece is slices of SLICE bytes; each slice is the left channel's blocks then the right channel's (the last
          slice holds whatever is left of the piece). Blocks are SPU2 VAG blocks with no flags: the player sets the
          ring's loop flags as it uploads, and a piece's first block is independent of what played before it.

Pieces, in order: the intro, then the three loop recordings (see build_hcu_menu_audio.MUSIC).
"""

from __future__ import annotations

import argparse
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
from build_hcu_menu_audio import MUSIC, chain_starts, linked_fragments  # noqa: E402
from hcu_sound_bank import decode_xbox_adpcm, encode_vag, sound_permutations  # noqa: E402

MAGIC = b"HMS1"
VERSION = 1
HEADER = struct.Struct("<4s7I")
PIECE = struct.Struct("<4I")
SLICE = 16384


def decode_channels(cache: CacheMap, tag, start: int) -> tuple[list[list[int]], int]:
    info, _permutations = sound_permutations(cache, tag)
    if info["compression"] != 1 or info["channels"] != 2:
        raise ValueError(f"unexpected retail music layout: {tag.path}")
    channels: list[list[int]] = [[], []]
    for fragment in linked_fragments(cache, tag, start):
        raw = cache.buf[fragment["offset"]:fragment["offset"] + fragment["size"]]
        left, right = decode_xbox_adpcm(raw, 2, split=True)
        channels[0].extend(left)
        channels[1].extend(right)
    return channels, info["rate"]


def interleave(left: bytes, right: bytes) -> bytes:
    """A piece's data: per slice, the left blocks then the right blocks."""
    out = bytearray()
    for at in range(0, len(left), SLICE):
        out += left[at:at + SLICE]
        out += right[at:at + SLICE]
    return bytes(out)


def build(cache: CacheMap) -> tuple[bytes, list[dict]]:
    by_path = {t.path: t for t in cache.tags if t.group == "snd!"}
    pieces = []
    rate = None
    for source, names in MUSIC:
        tag = by_path[source]
        starts = chain_starts(cache, tag)
        if len(starts) != len(names):
            raise ValueError(f"{source}: {len(starts)} recordings, expected {len(names)}")
        for name, start in zip(names, starts):
            channels, piece_rate = decode_channels(cache, tag, start)
            if rate not in (None, piece_rate):
                raise ValueError("title music recordings differ in sample rate")
            rate = piece_rate
            encoded = [encode_vag(pcm, terminator=False, reset=True) for pcm in channels]
            pieces.append({"name": name, "samples": len(channels[0]), "blocks": len(encoded[0]) // 16,
                           "data": interleave(*encoded)})
    table_off = HEADER.size
    data_off = (table_off + PIECE.size * len(pieces) + 15) & ~15
    body = bytearray()
    table = bytearray()
    for piece in pieces:
        table += PIECE.pack(data_off + len(body), piece["blocks"], piece["samples"], 0)
        body += piece["data"]
    out = bytearray(HEADER.pack(MAGIC, VERSION, rate, 2, len(pieces), table_off, data_off, 0))
    out += table
    out += b"\0" * (data_off - len(out))
    out += body
    struct.pack_into("<I", out, 28, len(out))
    return bytes(out), pieces


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("iso", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hcu-menu-music-") as folder:
        compressed = Path(folder) / "ui.map"
        decompressed = Path(folder) / "decompressed-ui.map"
        disc = XboxDisc(args.iso)
        try:
            disc.extract("maps/ui.map", compressed)
        finally:
            disc.close()
        mapinfo.decompress(compressed, decompressed)
        blob, pieces = build(CacheMap(decompressed.read_bytes()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    for piece in pieces:
        print(f"{piece['name']}: {piece['samples'] / 44100:.2f}s, {piece['blocks'] * 32} bytes")
    print(f"{args.output}: {len(blob)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
