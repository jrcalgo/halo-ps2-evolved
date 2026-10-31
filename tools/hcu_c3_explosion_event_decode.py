"""Decode the bounded asynchronous C3 explosion event ring."""
from __future__ import annotations

import math
import struct

MAGIC = 0x48434531
VERSION = 1
CAPACITY = 16
HEADER = struct.Struct("<5I")
RECORD = struct.Struct("<9I3f")
BLOCK_BYTES = HEADER.size + CAPACITY * RECORD.size
KINDS = {1: "launch", 2: "detonate"}


def decode(raw: bytes) -> dict:
    if len(raw) != BLOCK_BYTES:
        raise ValueError(f"explosion event block must be {BLOCK_BYTES} bytes, got {len(raw)}")
    magic, version, capacity, write_sequence, overflow_count = HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION or capacity != CAPACITY:
        return {"status": "invalid", "magic": magic, "version": version,
                "capacity": capacity, "write_sequence": write_sequence,
                "overflow_count": overflow_count}
    events = []
    seen = set()
    oldest = max(1, write_sequence - CAPACITY + 1)
    for index in range(CAPACITY):
        words = RECORD.unpack_from(raw, HEADER.size + index * RECORD.size)
        seq, phase, kind, tick, projectile, generation, owner, definition, flags, x, y, z = words
        if seq == 0 or seq < oldest or seq > write_sequence:
            continue
        if seq in seen:
            return {"status": "invalid", "reason": "duplicate_sequence", "sequence": seq,
                    "write_sequence": write_sequence, "overflow_count": overflow_count}
        seen.add(seq)
        if kind not in KINDS or not all(math.isfinite(v) for v in (x, y, z)):
            return {"status": "invalid", "reason": "bad_record", "sequence": seq,
                    "write_sequence": write_sequence, "overflow_count": overflow_count}
        events.append({"seq": seq, "phase": phase, "kind": KINDS[kind], "tick": tick,
                       "projectile_index": projectile, "generation": generation,
                       "owner_index": owner, "definition_index": definition, "flags": flags,
                       "position": [x, y, z]})
    events.sort(key=lambda event: event["seq"])
    gap_count = max(0, min(write_sequence, CAPACITY) - len(events))
    return {"status": "coherent" if gap_count == 0 else "invalid",
            "reason": None if gap_count == 0 else "missing_record_sequence",
            "abi": "hcu_c3_explosion_event_ring/v1", "magic": magic,
            "version": version, "capacity": capacity,
            "write_sequence": write_sequence, "overflow_count": overflow_count,
            "events": events, "missing_records_in_window": gap_count}


def capture(read, desc, retries: int = 2) -> dict:
    if not desc:
        return {"status": "not_present"}
    if int(desc.get("type", {}).get("size", 0)) != BLOCK_BYTES:
        return {"status": "invalid", "reason": "layout_size",
                "layout_bytes": desc.get("type", {}).get("size")}
    address = int(desc["address"])
    for _ in range(retries):
        first = read(address, BLOCK_BYTES)
        second = read(address, BLOCK_BYTES)
        if len(first) != BLOCK_BYTES or len(second) != BLOCK_BYTES:
            continue
        if first != second:
            continue
        return decode(second)
    return {"status": "torn", "reason": "double_read_mismatch"}
