#!/usr/bin/env python3
"""Build the HCU SPU2 sound bank (HSB1) from a decompressed Xbox cache map.

Retail `snd!` permutations are Xbox ADPCM (36-byte blocks of 64 samples) or 16-bit PCM
inside the map. SPU2 plays only its native VAG ADPCM (16-byte blocks of 28 samples), so
this tool decodes each selected permutation to PCM16 and re-encodes it. The bank holds
decoded-then-encoded samples only; it is derived data and must never be committed.

Layout (little endian, every offset 16-byte aligned):
  header  32 B: magic 'HSB1', version, count, entries_off, data_off, total_bytes, spu_bytes, reserved
  entry   32 B: name_hash, perm_index u16, perm_count u16, rate, samples, offset, vag_bytes, gain f32, near u16, far u16
  data        : per entry the raw VAG blocks (last block carries the end flag)
  trailer 32 B: SHA-256 of every preceding byte
near/far are the sound tag's minimum/maximum distance in 1/64 world unit (0 = tag left it to the sound class).
name_hash is FNV-1a over the lower-cased tag path with path separators removed, so the runtime can
derive it from tag_get_name() whichever separator the build prints.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2.tagcache import CacheMap  # noqa: E402

MAGIC = b"HSB1"
VERSION = 2
HEADER = struct.Struct("<4s7I")
ENTRY = struct.Struct("<IHHIIIIfHH")
ENTRY_SIZE = 32
SPU_RAM_BYTES = 2 * 1024 * 1024
SPU_RESERVED_BYTES = 0x5010
DEFAULT_BUDGET = 1_500_000
PAGED_BUDGET_LIMIT = 24 * 1024 * 1024

STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
        73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408,
        449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
        2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
        9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
        32767]
INDEX_ADJUST = [-1, -1, -1, -1, 2, 4, 6, 8]
VAG_FILTERS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]
SAMPLE_RATES = {0: 22050, 1: 44100}
SPU_BASE_RATE = 48000

# Selection tiers: lower is kept first when the SPU2 RAM budget is tight.
TIERS = [
    ("weapons\\", ("fire", "eject", "dryfire", "ready", "reload", "overheat")),
    ("impulse\\impacts\\", ("",)),
    ("impulse\\explosion", ("",)),
    ("impulse\\weapon_drops", ("",)),
    ("weapons\\", ("charge", "melee", "ammo", "pickup")),
    ("weapons\\", ("",)),
    ("impulse\\", ("",)),
    ("vehicles\\", ("",)),
    ("\\ui\\", ("",)),
    ("ambience\\", ("",)),
    ("dialog\\", ("",)),
]


def name_hash(path: str) -> int:
    value = 0x811C9DC5
    for ch in path.lower():
        if ch in "\\/":
            continue
        value = ((value ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
    return value


def clamp16(value: int) -> int:
    return -32768 if value < -32768 else 32767 if value > 32767 else value


def _ima_nibble(pred: int, index: int, nib: int) -> tuple[int, int]:
    step = STEP[index]
    diff = step >> 3
    if nib & 1:
        diff += step >> 2
    if nib & 2:
        diff += step >> 1
    if nib & 4:
        diff += step
    pred = clamp16(pred - diff if nib & 8 else pred + diff)
    return pred, max(0, min(88, index + INDEX_ADJUST[nib & 7]))


def decode_xbox_adpcm(raw: bytes, channels: int = 1) -> list[int]:
    """Xbox ADPCM, 64 output samples per channel per block: the header sample plus the first 63 of 64 nibbles.

    Mono is one 36-byte block (int16 predictor, step index, pad, 32 nibble bytes). Stereo is the standard IMA
    layout: a 72-byte block with both 4-byte channel headers first, then the nibble data in alternating 4-byte
    groups, left then right. Decoding stereo as two consecutive mono blocks produces loud noise."""
    if channels not in (1, 2):
        raise ValueError("Xbox ADPCM sounds have one or two channels")
    stride = 36 * channels
    out: list[list[int]] = [[] for _ in range(channels)]
    for base in range(0, len(raw) - stride + 1, stride):
        block = raw[base: base + stride]
        state = []
        for ch in range(channels):
            pred, index = struct.unpack_from("<hB", block, ch * 4)
            state.append([pred, min(index, 88)])
            out[ch].append(pred)
        data = block[4 * channels:]
        count = [1] * channels
        for group in range(len(data) // (4 * channels)):
            for ch in range(channels):
                chunk = data[(group * channels + ch) * 4: (group * channels + ch) * 4 + 4]
                pred, index = state[ch]
                for byte in chunk:
                    for nib in (byte & 15, byte >> 4):
                        pred, index = _ima_nibble(pred, index, nib)
                        if count[ch] < 64:
                            out[ch].append(pred)
                        count[ch] += 1
                state[ch] = [pred, index]
    if channels == 1:
        return out[0]
    return [sum(frame) // channels for frame in zip(*out)]


def decode_pcm16(raw: bytes, channels: int = 1, big_endian: bool = True) -> list[int]:
    count = len(raw) // 2
    values = struct.unpack((">" if big_endian else "<") + "h" * count, raw[:count * 2])
    if channels == 1:
        return list(values)
    return [sum(values[i:i + channels]) // channels for i in range(0, len(values) - channels + 1, channels)]


def _vag_block(chunk: list[int], h1: int, h2: int, filt: int, shift: int):
    k1, k2 = VAG_FILTERS[filt]
    step = 1 << (12 - shift)
    nibbles, err, clipped = [], 0, False
    for x in chunk:
        pred = (h1 * k1 + h2 * k2 + 32) >> 6
        q = round((x - pred) / step)
        if q > 7 or q < -8:
            clipped = True
            q = max(-8, min(7, q))
        rec = clamp16(q * step + pred)
        err += (x - rec) ** 2
        nibbles.append(q & 15)
        h2, h1 = h1, rec
    return nibbles, err, clipped, h1, h2


def encode_vag(pcm: list[int]) -> bytes:
    """Encode mono PCM16 to SPU VAG blocks; the final block carries the end flag (one shot)."""
    blocks = bytearray()
    h1 = h2 = 0
    total = (len(pcm) + 27) // 28
    for index in range(total):
        chunk = pcm[index * 28:(index + 1) * 28]
        chunk = chunk + [0] * (28 - len(chunk))
        best = None
        for filt in range(len(VAG_FILTERS)):
            k1, k2 = VAG_FILTERS[filt]
            peak = 0
            p1, p2 = h1, h2
            for x in chunk:
                pred = (p1 * k1 + p2 * k2 + 32) >> 6
                peak = max(peak, abs(x - pred))
                p2, p1 = p1, x
            shift = 12
            while shift > 0 and peak / (1 << (12 - shift)) > 7.5:
                shift -= 1
            for sh in {shift, max(0, shift - 1)}:
                nibbles, err, clipped, n1, n2 = _vag_block(chunk, h1, h2, filt, sh)
                key = (clipped, err)
                if best is None or key < best[0]:
                    best = (key, filt, sh, nibbles, n1, n2)
        _key, filt, sh, nibbles, h1, h2 = best
        flags = 1 if index == total - 1 else 0
        blocks.append((sh & 15) | (filt << 4))
        blocks.append(flags)
        for i in range(0, 28, 2):
            blocks.append(nibbles[i] | (nibbles[i + 1] << 4))
    return bytes(blocks)


def decode_vag(blob: bytes) -> list[int]:
    """Reference decoder for the SPU2 VAG format (used by tests and sanity checks)."""
    h1 = h2 = 0
    out = []
    for base in range(0, len(blob) - 15, 16):
        shift, filt = blob[base] & 15, blob[base] >> 4
        k1, k2 = VAG_FILTERS[min(filt, 4)]
        for byte in blob[base + 2: base + 16]:
            for nib in (byte & 15, byte >> 4):
                signed = nib - 16 if nib & 8 else nib
                sample = clamp16((signed << (12 - shift)) + ((h1 * k1 + h2 * k2 + 32) >> 6))
                out.append(sample)
                h2, h1 = h1, sample
    return out


def _tier(path: str) -> int:
    lowered = path.lower()
    for tier, (prefix, words) in enumerate(TIERS):
        if prefix in lowered and any(word in lowered for word in words):
            return tier
    return len(TIERS)


def sound_permutations(cache: CacheMap, tag) -> tuple[dict, list[dict]]:
    """Return (definition summary, permutations) with raw sample file offsets."""
    d = cache.off(tag.data_addr)
    buf = cache.buf
    rate = SAMPLE_RATES.get(struct.unpack_from("<H", buf, d + 6)[0], 22050)
    encoding, compression = struct.unpack_from("<HH", buf, d + 0x6C)
    perms = []
    ranges, first = cache.reflexive(d, 0x98)
    for r in range(ranges):
        count, pfirst = cache.reflexive(first + 72 * r, 0x3C)
        for p in range(count):
            base = pfirst + 124 * p
            gain = struct.unpack_from("<f", buf, base + 36)[0]
            perm_compression = struct.unpack_from("<h", buf, base + 40)[0]
            size, _flags, offset = struct.unpack_from("<III", buf, base + 64)
            if size and offset + size <= len(buf):
                perms.append({"gain": gain, "compression": perm_compression, "offset": offset, "size": size})
    near, far = struct.unpack_from("<ff", buf, d + 8)
    return {"rate": rate, "channels": 2 if encoding == 1 else 1, "compression": compression,
            "near": near, "far": far}, perms


def _dist_units(distance: float) -> int:
    """World units -> 1/64 unit u16; zero, negative or non-finite means 'use the class default'."""
    if not distance > 0.0 or distance != distance:
        return 0
    return min(65535, round(distance * 64))


def build_bank(map_path: Path, budget: int = DEFAULT_BUDGET, max_perms: int = 2) -> tuple[bytes, list[dict]]:
    cache = CacheMap(map_path.read_bytes())
    candidates = []
    for tag in cache.tags:
        if tag.group != "snd!" or tag.indexed:
            continue
        info, perms = sound_permutations(cache, tag)
        if perms and info["compression"] in (0, 1):
            candidates.append((_tier(tag.path), tag.path, tag, info, perms))
    candidates.sort(key=lambda c: (c[0], c[1]))
    entries, data, used = [], bytearray(), 0
    for tier, path, tag, info, perms in candidates:
        if tier >= len(TIERS):
            continue
        # Xbox ADPCM and VAG are both ~0.56 byte/sample, so the raw size bounds the encoded cost.
        if used + sum(perm["size"] for perm in perms[:max_perms]) * 9 // 10 > budget:
            continue
        encoded = []
        for perm in perms[:max_perms]:
            raw = cache.buf[perm["offset"]: perm["offset"] + perm["size"]]
            if info["compression"] == 1:
                pcm = decode_xbox_adpcm(raw, info["channels"])
            else:
                pcm = decode_pcm16(raw, info["channels"])
            if len(pcm) < 28:
                continue
            encoded.append((pcm, encode_vag(pcm), perm))
        cost = sum(len(vag) for _pcm, vag, _perm in encoded)
        if not encoded or used + cost > budget:
            continue
        used += cost
        for index, (pcm, vag, perm) in enumerate(encoded):
            offset = len(data)
            data += vag
            data += b"\0" * (-len(data) % 16)
            entries.append({"path": path, "hash": name_hash(path), "perm": index, "perm_count": len(encoded),
                            "rate": info["rate"], "samples": len(pcm), "offset": offset, "bytes": len(vag),
                            "gain": perm["gain"] if perm["gain"] > 0 else 1.0, "near": info["near"], "far": info["far"], "tier": tier})
    entries_off = HEADER.size
    data_off = entries_off + ENTRY_SIZE * len(entries)
    data_off += -data_off % 16
    out = bytearray(HEADER.pack(MAGIC, VERSION, len(entries), entries_off, data_off, 0, used, 0))
    for e in entries:
        out += ENTRY.pack(e["hash"], e["perm"], e["perm_count"], e["rate"], e["samples"],
                          data_off + e["offset"], e["bytes"], e["gain"], _dist_units(e["near"]), _dist_units(e["far"]))
    out += b"\0" * (data_off - len(out))
    out += data
    struct.pack_into("<I", out, 20, len(out) + 32)
    return bytes(out) + hashlib.sha256(bytes(out)).digest(), entries


def verify_bank(blob: bytes) -> dict:
    if len(blob) < HEADER.size + 32 or hashlib.sha256(blob[:-32]).digest() != blob[-32:]:
        raise ValueError("bank digest mismatch")
    magic, version, count, entries_off, data_off, total, spu_bytes, _ = HEADER.unpack_from(blob, 0)
    if magic != MAGIC or version != VERSION or total != len(blob):
        raise ValueError("bad bank header")
    rows = []
    for i in range(count):
        h, perm, perm_count, rate, samples, off, nbytes, gain, near, far = ENTRY.unpack_from(blob, entries_off + ENTRY_SIZE * i)
        if off % 16 or nbytes % 16 or off + nbytes > len(blob) - 32 or blob[off + nbytes - 15] & 1 == 0:
            raise ValueError(f"bad bank entry {i}")
        rows.append({"hash": h, "perm": perm, "perm_count": perm_count, "rate": rate, "samples": samples,
                     "offset": off, "bytes": nbytes, "gain": gain, "near": near, "far": far})
    return {"count": count, "spu_bytes": spu_bytes, "entries": rows}


def spu_pitch(rate: int) -> int:
    return round(0x1000 * rate / SPU_BASE_RATE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="SPU2 RAM bytes for samples")
    ap.add_argument("--max-perms", type=int, default=2)
    ap.add_argument("--paged", action="store_true",
                    help="allow a bank larger than SPU2 RAM; the player pages samples in on first use")
    args = ap.parse_args()
    if args.budget > (PAGED_BUDGET_LIMIT if args.paged else SPU_RAM_BYTES - SPU_RESERVED_BYTES):
        ap.error("budget exceeds SPU2 RAM (use --paged for a larger bank)")
    blob, entries = build_bank(args.map, args.budget, args.max_perms)
    verify_bank(blob)
    args.output.write_bytes(blob)
    print(f"{args.output}: {len(entries)} entries, {sum(e['bytes'] for e in entries)} VAG bytes, "
          f"sha256 {hashlib.sha256(blob).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
