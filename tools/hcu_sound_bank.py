#!/usr/bin/env python3
"""Build the HCU SPU2 sound bank (HSB1) from a decompressed Xbox cache map.

Retail `snd!` permutations are Xbox ADPCM (36-byte blocks of 64 samples) or 16-bit PCM
inside the map. SPU2 plays only its native VAG ADPCM (16-byte blocks of 28 samples), so
this tool decodes each selected permutation to PCM16 and re-encodes it. The bank holds
decoded-then-encoded samples only; it is derived data and must never be committed.

Layout (little endian, every offset 16-byte aligned):
  header  32 B: magic 'HSB1', version, count, entries_off, data_off, total_bytes, spu_bytes, reserved
  entry   32 B: name_hash, perm_index u16, perm_count u16, rate, samples, offset, vag_bytes, gain f32, near u16, far u16
  data        : per entry the raw VAG blocks (last block is a silent self-looping terminator, flags 7)
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
MIN_POOL_BYTES = 0x40000  # SPU2 RAM the player keeps for paging in a bank with a pinned prefix

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
    ("weapons\\", ("fire", "eject", "dryfire", "overheat", "projectile")),
    ("weapons\\", ("expl",)),
    ("impulse\\impacts\\", ("",)),
    ("impulse\\explosion", ("",)),
    ("impulse\\weapon_drops", ("",)),
    ("weapons\\", ("hit", "spark", "granite", "bounce", "throwgren")),
    ("weapons\\", ("zoom", "nightscope")),
    ("weapons\\", ("ready", "reload")),
    ("impulse\\footsteps", ("",)),
    ("vehicles\\", ("",)),
    ("impulse\\", ("shellcasings", "melee", "bodyfalls", "glass", "material_effects", "coolant")),
    ("weapons\\", ("charge", "melee", "ammo", "pickup")),
    ("\\ui\\", ("",)),
    ("ambience\\", ("",)),
    ("weapons\\", ("",)),
    ("impulse\\", ("",)),
    ("dialog\\", ("",)),
]


# Sample-rate ceiling per TIERS index when a bank is built with low_rate: gunshots, explosions, impacts and drops
# (tiers before this index) keep full rate; reloads, footsteps, vehicles and the rest are band-limited to low_rate.
FULL_RATE_TIERS = 5
TAIL_RATE_TIERS = 10  # shell casings, melee, ui, ambience, dialogue: the quietest, least critical sounds
TAIL_RATE_EXTRA_TIERS = (7, 8)  # reloads, readies and footsteps: short mechanical noises, clear at 11 kHz
LOW_RATE_EXTRA_TIERS = (2,)  # surface impacts: noise-like, band-limited a little further than the rest
IMPACT_RATE = 14000


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


def resample(pcm: list[int], src: int, dst: int) -> list[int]:
    """Band-limited down-sampling from src to dst Hz (windowed-sinc low-pass at 0.45 of dst, then linear interpolation)."""
    if dst >= src or len(pcm) < 64:
        return pcm
    import numpy as np
    x = np.asarray(pcm, dtype=np.float64)
    cutoff = 0.45 * dst / src
    taps = np.arange(-32, 33)
    kernel = np.sinc(2 * cutoff * taps) * np.hamming(65)
    kernel /= kernel.sum()
    x = np.convolve(x, kernel, mode="same")
    count = int(len(pcm) * dst / src)
    pos = np.arange(count) * (src / dst)
    out = np.interp(pos, np.arange(len(pcm)), x)
    return np.clip(np.rint(out), -32768, 32767).astype(int).tolist()


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


VAG_TERMINATOR_FLAGS = 7  # loop start | repeat | end


def encode_vag(pcm: list[int]) -> bytes:
    """Encode mono PCM16 to SPU VAG blocks (one shot). The SPU2 does not reliably stop at an end flag: a voice that
    outlives its sample (the game tick that keys it off can be late) replays the sample from its start as a steady
    tone. The audio therefore ends in a silent terminator block flagged loop-start|repeat|end, which loops on itself."""
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
        flags = 0
        blocks.append((sh & 15) | (filt << 4))
        blocks.append(flags)
        for i in range(0, 28, 2):
            blocks.append(nibbles[i] | (nibbles[i + 1] << 4))
    blocks += bytes([0, VAG_TERMINATOR_FLAGS]) + bytes(14)
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


# Sounds the player keeps resident (pinned) in a paged bank: gunshots first, then explosions, impacts, weapon drops.
PIN_TIERS = [
    ("weapons\\", ("fire", "eject", "dryfire")),
    ("impulse\\explosion", ("",)),
    ("impulse\\impacts\\", ("",)),
    ("impulse\\weapon_drops", ("",)),
]


# Content few maps use (the flamethrower, cut from retail multiplayer): added with the ambience, ahead of the pose
# sounds, vehicle enter/exit animations and dialogue.
UNREACHABLE = ("flamethrower",)  # after everything else but the dialogue, at the tail rate

AMBIENCE_TIER = next(i for i, (prefix, _words) in enumerate(TIERS) if prefix == "ambience\\")

AMBIENT_RATE = 7000  # the ambience and the flamethrower are wind and fire: broadband noise with nothing above 4 kHz worth keeping

# Multiplayer announcer lines (globals multiplayer_information). The speech lives under dialog\multiplayer1\;
# the mode ticks (countdown, respawn, hill move, flag failure, teleporter) live under sfx\ui and the tier fill
# usually keeps them. A map bank always keeps both: speech is appended past the resident prefix and paged in
# on first play, so it does not displace gunshots from SPU2 RAM.
ANNOUNCER_DIALOG = "dialog\\multiplayer1\\"
ANNOUNCER_ALSO = (
    "\\sfx\\ui\\countdown_timer",
    "\\sfx\\ui\\countdown_timer_end",
    "\\sfx\\ui\\countdown_for_respawn",
    "\\sfx\\ui\\teleporter_activate",
    "\\sfx\\ui\\flag_failure",
    "\\sfx\\ui\\hill_move",
    "\\sfx\\ui\\player_respawn",
)


def is_announcer_sound(path: str) -> bool:
    lowered = path.lower()
    if ANNOUNCER_DIALOG in lowered:
        return True
    return any(lowered.endswith(suffix) for suffix in ANNOUNCER_ALSO)


def _tier(path: str) -> int:
    lowered = path.lower()
    if "flamethrower_" in lowered:  # its reload, ready and pose sounds: leftovers like the other weapons' pose sounds
        return len(TIERS) - 2
    if any(word in lowered for word in UNREACHABLE):
        return AMBIENCE_TIER
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
        # permutations past the range's "actual permutation count" continue a long sound (chained by next-permutation index)
        # and are not sounds of their own: playing one by itself is a clipped fragment
        actual = struct.unpack_from("<H", buf, first + 72 * r + 44)[0]
        for p in range(min(count, actual) if actual else count):
            base = pfirst + 124 * p
            flat = len(perms)
            gain = struct.unpack_from("<f", buf, base + 36)[0]
            perm_compression = struct.unpack_from("<h", buf, base + 40)[0]
            size, _flags, offset = struct.unpack_from("<III", buf, base + 64)
            if size and offset + size <= len(buf):
                perms.append({"gain": gain, "compression": perm_compression, "offset": offset, "size": size,
                              "range": r, "flat": flat})
    near, far = struct.unpack_from("<ff", buf, d + 8)
    return {"rate": rate, "channels": 2 if encoding == 1 else 1, "compression": compression,
            "near": near, "far": far}, perms


def select_permutations(perms: list[dict], cap: int) -> list[dict]:
    """Up to `cap` permutations, but always the first of every pitch range: a range is a separate recording (an engine
    at idle, at speed), which the game picks by pitch, so a bank holding only one range plays every pitch from the wrong
    recording. The rest fill up to the cap in tag order."""
    chosen, seen = [], set()
    for perm in perms:
        if perm["range"] not in seen:
            seen.add(perm["range"])
            chosen.append(perm)
    for perm in perms:
        if len(chosen) >= max(cap, len(seen)):
            break
        if perm not in chosen:
            chosen.append(perm)
    return sorted(chosen, key=lambda perm: perm["flat"])


def _dist_units(distance: float) -> int:
    """World units -> 1/64 unit u16; zero, negative or non-finite means 'use the class default'."""
    if not distance > 0.0 or distance != distance:
        return 0
    return min(65535, round(distance * 64))


def _pin_tier(path: str) -> int | None:
    lowered = path.lower()
    for tier, (prefix, words) in enumerate(PIN_TIERS):
        if prefix in lowered and any(word in lowered for word in words):
            return tier
    return None


def build_bank(map_path: Path, budget: int = DEFAULT_BUDGET, max_perms: int = 2,
               pin_bytes: int = 0, pin_perms: int = 2, usage: dict[int, int] | None = None,
               fill_perms: int = 1, low_rate: int = 0, tail_rate: int = 0,
               announcer: bool = False) -> tuple[bytes, list[dict]]:
    """With pin_bytes, the bank opens with a pinned prefix of at most pin_bytes (the PIN_TIERS sounds, pin_perms
    permutations each): header spu_bytes is that prefix's size, the player uploads only it at load and never
    evicts it; everything after is paged through the rest of SPU2 RAM. Without it spu_bytes is the data size.
    With usage (name_hash -> requests measured in play), the sounds the game really asks for come first, most requested
    first, with max_perms permutations each; the rest of the budget is filled by TIERS with fill_perms permutations
    each. A bank within SPU2 RAM is uploaded once at load and never written during play.
    With announcer, every multiplayer announcer line is kept (all of its pitch-range permutations). Speech stays at
    its tag rate. When the lines do not fit in the resident budget, header spu_bytes stops at the gameplay prefix
    (never past SPU2 RAM minus the paging pool) and the lines page in on first play."""
    cache = CacheMap(map_path.read_bytes())
    candidates = []
    announcers = []
    for tag in cache.tags:
        if tag.group != "snd!" or tag.indexed:
            continue
        info, perms = sound_permutations(cache, tag)
        if not (perms and info["compression"] in (0, 1)):
            continue
        row = (_tier(tag.path), tag.path, tag, info, perms)
        # Speech is appended after the gameplay prefix so the tail rate cannot crush it and a tight budget
        # cannot drop it. The UI ticks stay in the tier fill (they already fit a normal map bank) and are
        # appended only when that fill did not keep them.
        if announcer and is_announcer_sound(tag.path):
            announcers.append(row)
        if not (announcer and ANNOUNCER_DIALOG in tag.path.lower()):
            candidates.append(row)
    candidates.sort(key=lambda c: (c[0], c[1]))
    announcers.sort(key=lambda c: c[1])
    entries, data = [], bytearray()
    stored: dict[bytes, int] = {}
    used = 0

    def tier_rate(tier, rate):
        if tail_rate and tier == AMBIENCE_TIER:
            return min(rate, AMBIENT_RATE)
        if tail_rate and (tier >= TAIL_RATE_TIERS or tier in TAIL_RATE_EXTRA_TIERS):
            return min(rate, tail_rate)
        if low_rate and tier in LOW_RATE_EXTRA_TIERS:
            return min(rate, IMPACT_RATE)
        if low_rate and tier >= FULL_RATE_TIERS:
            return min(rate, low_rate)
        return rate

    def add(tier, path, tag, info, perms, cap, limit, rate_override=0):
        """Encodes up to `cap` permutations and appends them when the total stays within `limit`; True when added."""
        nonlocal used
        # Xbox ADPCM and VAG are both ~0.56 byte/sample, so the raw size bounds the encoded cost.
        rate = rate_override or tier_rate(tier, info["rate"])
        scale = min(1.0, rate / info["rate"]) if info["rate"] else 1.0
        picked = select_permutations(perms, cap)
        if used + int(sum(perm["size"] for perm in picked) * 9 // 10 * scale) > limit:
            return False
        encoded = []
        for perm in picked:
            raw = cache.buf[perm["offset"]: perm["offset"] + perm["size"]]
            if info["compression"] == 1:
                pcm = decode_xbox_adpcm(raw, info["channels"])
            else:
                pcm = decode_pcm16(raw, info["channels"])
            if rate < info["rate"]:
                pcm = resample(pcm, info["rate"], rate)
            if len(pcm) < 28:
                continue
            encoded.append((pcm, encode_vag(pcm), perm, rate))
        # identical blocks (the same recording under two tags) are stored once; their entries share the offset
        fresh = {vag for _pcm, vag, _perm, _rate in encoded if vag not in stored}
        cost = sum(len(vag) for vag in fresh)
        if not encoded or used + cost > limit:
            return False
        used += cost
        for index, (pcm, vag, perm, rate) in enumerate(encoded):
            if vag in stored:
                offset = stored[vag]
            else:
                offset = stored[vag] = len(data)
                data.extend(vag)
                data.extend(b"\0" * (-len(data) % 16))
            entries.append({"path": path, "hash": name_hash(path), "perm": perm["flat"], "perm_count": len(encoded),
                            "rate": rate, "samples": len(pcm), "offset": offset, "bytes": len(vag),
                            "gain": perm["gain"] if perm["gain"] > 0 else 1.0, "near": info["near"], "far": info["far"], "tier": tier})
        return True

    pinned_paths = set()
    spu_bytes = None
    if pin_bytes:
        pinned = sorted((c for c in candidates if _pin_tier(c[1]) is not None), key=lambda c: (_pin_tier(c[1]), c[1]))
        for tier, path, tag, info, perms in pinned:
            if add(tier, path, tag, info, perms, pin_perms, pin_bytes):
                pinned_paths.add(path)
        spu_bytes = used
    if usage:
        for tier, path, tag, info, perms in sorted((c for c in candidates if name_hash(c[1]) in usage and c[1] not in pinned_paths),
                                                   key=lambda c: (-usage[name_hash(c[1])], c[1])):
            if add(tier, path, tag, info, perms, max_perms, budget):
                pinned_paths.add(path)
    stored_paths = set(pinned_paths)
    for tier, path, tag, info, perms in candidates:
        if tier >= len(TIERS) or path in stored_paths:
            continue
        if add(tier, path, tag, info, perms, fill_perms if usage else max_perms, budget):
            stored_paths.add(path)
    prefix_used = used
    if announcer:
        # Speech keeps the tag rate (22 kHz). A line the tier fill already stored is not encoded again.
        for tier, path, tag, info, perms in announcers:
            if path in stored_paths:
                continue
            override = info["rate"] if ANNOUNCER_DIALOG in path.lower() else 0
            if add(tier, path, tag, info, perms, max(max_perms, 1), PAGED_BUDGET_LIMIT, override):
                stored_paths.add(path)
    if announcer and spu_bytes is None:
        # Leave the player's paging pool. The resident prefix ends on a sample boundary so a sample is
        # either uploaded whole or paged whole. Announcer lines past the gameplay prefix page in.
        resident_cap = min(budget, SPU_RAM_BYTES - SPU_RESERVED_BYTES - MIN_POOL_BYTES)
        if used <= resident_cap:
            spu_bytes = used
        else:
            spu_bytes = 0
            for entry in entries:
                if entry["offset"] >= prefix_used:
                    continue
                end = entry["offset"] + entry["bytes"]
                if end <= resident_cap:
                    spu_bytes = max(spu_bytes, end)
            if spu_bytes <= 0:
                spu_bytes = min(prefix_used, resident_cap)
    elif spu_bytes is None:
        spu_bytes = used
    entries_off = HEADER.size
    data_off = entries_off + ENTRY_SIZE * len(entries)
    data_off += -data_off % 16
    out = bytearray(HEADER.pack(MAGIC, VERSION, len(entries), entries_off, data_off, 0, spu_bytes, 0))
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
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Map banks include the multiplayer announcer (--no-announcer to omit). "
               "The lines that do not fit the resident budget are paged. "
               "Example: python3 tools/hcu_sound_bank.py MAP OUT --budget 2076656 "
               "--max-perms 1 --low-rate 16000 --tail-rate 11025")
    ap.add_argument("map", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="SPU2 RAM bytes for samples")
    ap.add_argument("--max-perms", type=int, default=2)
    ap.add_argument("--pin-bytes", type=int, default=0,
                    help="paged bank: bytes of PIN_TIERS sounds kept resident and never evicted (header spu_bytes)")
    ap.add_argument("--pin-perms", type=int, default=2, help="permutations per pinned sound")
    ap.add_argument("--usage", type=Path, help="measured requests, one '<sound path or 8-hex name hash> <count>' per line: those sounds go first with every permutation")
    ap.add_argument("--fill-perms", type=int, default=1, help="permutations per sound for the TIERS fill after the usage list")
    ap.add_argument("--low-rate", type=int, default=0,
                    help="band-limit sounds after the gunshot/impact/explosion/drop tiers to this sample rate (e.g. 16000)")
    ap.add_argument("--tail-rate", type=int, default=0,
                    help="sample rate for the least critical tiers (shell casings, melee, ui, ambience, dialogue), e.g. 11025")
    ap.add_argument("--paged", action="store_true",
                    help="allow a bank larger than SPU2 RAM; the player pages samples in on first use")
    ap.add_argument("--announcer", action=argparse.BooleanOptionalAction, default=True,
                    help="keep every multiplayer announcer line, paging any that do not fit the resident budget")
    args = ap.parse_args()
    if args.pin_bytes and (not args.paged or args.pin_bytes > SPU_RAM_BYTES - SPU_RESERVED_BYTES - MIN_POOL_BYTES):
        ap.error("--pin-bytes needs --paged and must leave a paging pool in SPU2 RAM")
    if args.budget > (PAGED_BUDGET_LIMIT if args.paged else SPU_RAM_BYTES - SPU_RESERVED_BYTES):
        ap.error("budget exceeds SPU2 RAM (use --paged for a larger bank)")
    usage = None
    if args.usage:
        usage = {}
        for line in args.usage.read_text().splitlines():
            parts = line.rsplit(None, 1)
            if len(parts) == 2 and parts[1].isdigit():
                key = parts[0].strip()
                h = int(key, 16) if len(key) == 8 and all(c in "0123456789abcdef" for c in key.lower()) else name_hash(key)
                usage[h] = usage.get(h, 0) + int(parts[1])
    blob, entries = build_bank(args.map, args.budget, args.max_perms, args.pin_bytes, args.pin_perms, usage,
                               args.fill_perms, args.low_rate, args.tail_rate, args.announcer)
    info = verify_bank(blob)
    args.output.write_bytes(blob)
    announcer_rows = [e for e in entries if is_announcer_sound(e["path"])]
    paged = sum(1 for e in announcer_rows if e["offset"] >= info["spu_bytes"])
    print(f"{args.output}: {len(entries)} entries, {sum(e['bytes'] for e in entries)} VAG bytes, "
          f"resident {info['spu_bytes']}, announcer {len({e['path'] for e in announcer_rows})} "
          f"({paged} paged), sha256 {hashlib.sha256(blob).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
