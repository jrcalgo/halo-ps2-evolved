#!/usr/bin/env python3
"""Validate and decode the bounded H2ANIMT1 PS2 animation trace stream."""

import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path


MAGIC = b"H2ANIMT1"
HEADER = struct.Struct("<8sHHHHIII")
EVENT = struct.Struct("<IIiiHhhH")
CONTEXT = struct.Struct("<IIIIHHHHBBH")
PAIR_BYTES = EVENT.size + CONTEXT.size
KNOWN_CONTEXT_MASK = 0x80FF
CONTEXT_INSTALLED = 1 << 15
MAX_COUNT = 32767
MAX_CAPTURE_BYTES = HEADER.size + MAX_COUNT * PAIR_BYTES
PHASES = {0: "none", 1: "object_pose", 2: "unit_pose", 3: "first_person_pose"}
SITES = {
    1: "frame_data", 2: "frame_info", 3: "compressed_rotation",
    4: "compressed_translation", 5: "compressed_scale", 6: "default_data",
    7: "frame_info_bulk", 8: "schema_data",
}
PIN_RE = {
    "parent_commit": re.compile(r"^[0-9a-fA-F]{40}$"),
    "hcu_commit": re.compile(r"^[0-9a-fA-F]{40}$"),
    "halo_ps2_commit": re.compile(r"^[0-9a-fA-F]{40}$"),
    "elf_sha256": re.compile(r"^[0-9a-fA-F]{64}$"),
    "source_manifest_sha256": re.compile(r"^[0-9a-fA-F]{64}$"),
}


class TraceError(ValueError):
    pass


def load_provenance(path: Path, elf_path: Path) -> dict:
    try:
        if path.stat().st_size > 1024 * 1024:
            raise TraceError("provenance JSON exceeds 1 MiB limit")
        provenance = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TraceError(f"cannot read provenance JSON: {exc}") from exc
    if not isinstance(provenance, dict):
        raise TraceError("provenance JSON must contain an object")
    for name, pattern in PIN_RE.items():
        value = provenance.get(name)
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise TraceError(f"provenance requires a valid {name}")
    for name in ("build_profile", "toolchain_id"):
        if not isinstance(provenance.get(name), str) or not provenance[name].strip():
            raise TraceError(f"provenance requires non-empty {name}")
    elf_bytes = elf_path.read_bytes()
    if not elf_bytes.startswith(b"\x7fELF"):
        raise TraceError("supplied guest image is not an ELF file")
    digest = hashlib.sha256(elf_bytes).hexdigest()
    if digest.lower() != provenance["elf_sha256"].lower():
        raise TraceError("provenance ELF SHA-256 does not match the supplied ELF")
    provenance["elf_sha256"] = digest
    return provenance


def decode(blob: bytes) -> tuple[dict, list[dict]]:
    if len(blob) < HEADER.size:
        raise TraceError("truncated trace header")
    magic, version, header_size, event_size, context_size, count, dropped, crc = HEADER.unpack_from(blob)
    if magic != MAGIC:
        raise TraceError("bad trace magic")
    if (version, header_size, event_size, context_size) != (1, 28, 24, 28):
        raise TraceError("unsupported trace version or record layout")
    if count > MAX_COUNT:
        raise TraceError("event count exceeds signed context-token range")
    if dropped != 0:
        raise TraceError("capture is incomplete: dropped event count is nonzero")
    expected = HEADER.size + count * PAIR_BYTES
    if len(blob) != expected:
        raise TraceError(f"trace length mismatch: expected {expected}, got {len(blob)}")
    payload = blob[HEADER.size:]
    if zlib.crc32(payload) & 0xFFFFFFFF != crc:
        raise TraceError("payload CRC-32 mismatch")

    rows = []
    offset = HEADER.size
    for row_index in range(count):
        event = EVENT.unpack_from(blob, offset)
        context = CONTEXT.unpack_from(blob, offset + EVENT.size)
        offset += PAIR_BYTES
        animation_ptr, base_ptr, byte_offset, byte_count, site, detail, accepted, token = event
        (map_epoch, datum, tick, render_frame, graph, animation, frame, owner,
         phase, reserved, valid_mask) = context
        if site not in SITES:
            raise TraceError(f"event {row_index}: unknown site {site}")
        if accepted not in (0, 1) or byte_offset < 0 or byte_count < 0:
            raise TraceError(f"event {row_index}: invalid range/admission fields")
        if token < 0 or token > count:
            raise TraceError(f"event {row_index}: context token outside capture")
        if token and token != row_index + 1:
            raise TraceError(f"event {row_index}: context token does not identify its paired row")
        if reserved != 0 or phase not in PHASES or valid_mask & ~KNOWN_CONTEXT_MASK:
            raise TraceError(f"event {row_index}: invalid context encoding")
        if token and not valid_mask & CONTEXT_INSTALLED:
            raise TraceError(f"event {row_index}: token refers to uninstalled context")
        if not token and valid_mask != 0:
            raise TraceError(f"event {row_index}: context data exists without a token")
        context_fields = {
            "map_epoch": map_epoch, "datum": datum, "tick": tick,
            "render_frame": render_frame, "graph": graph,
            "animation": animation, "frame": frame, "owner": owner,
        }
        valid = {
            "map_epoch": bool(valid_mask & (1 << 0)),
            "datum": bool(valid_mask & (1 << 1)),
            "tick": bool(valid_mask & (1 << 2)),
            "render_frame": bool(valid_mask & (1 << 3)),
            "graph": bool(valid_mask & (1 << 4)),
            "animation": bool(valid_mask & (1 << 5)),
            "frame": bool(valid_mask & (1 << 6)),
            "owner": bool(valid_mask & (1 << 7)),
        }
        rows.append({
            "row": row_index,
            "animation_guest_address": f"0x{animation_ptr:08x}",
            "base_guest_address": f"0x{base_ptr:08x}",
            "offset": byte_offset,
            "bytes": byte_count,
            "site": SITES[site],
            "detail": detail,
            "accepted": bool(accepted),
            "context_token": token,
            "context": {
                "phase": PHASES[phase], "fields": context_fields,
                "valid": valid,
            },
        })
    summary = {
        "format": "H2ANIMT1", "version": version, "complete": True,
        "events": count, "dropped": dropped, "payload_crc32": f"{crc:08x}",
    }
    return summary, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="binary H2ANIMT1 capture")
    parser.add_argument("--elf", required=True, type=Path,
                        help="exact guest ELF used to produce the capture")
    parser.add_argument("--provenance", required=True, type=Path,
                        help="JSON with parent/HCU/halo-ps2 commits, source_manifest_sha256, toolchain_id, build_profile, and ELF SHA-256")
    parser.add_argument("--output", type=Path, help="write validated decoded JSON")
    args = parser.parse_args()
    try:
        provenance = load_provenance(args.provenance, args.elf)
        if args.capture.stat().st_size > MAX_CAPTURE_BYTES:
            raise TraceError("capture exceeds fixed 32,767-event format bound")
        summary, rows = decode(args.capture.read_bytes())
    except (OSError, TraceError) as exc:
        print(f"decode_ps2_animation_trace: {exc}", file=sys.stderr)
        return 2
    result = {"summary": summary, "provenance": provenance, "events": rows}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"summary": summary, "provenance": provenance}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
