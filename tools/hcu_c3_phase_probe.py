"""Decode the opt-in, fixed-width HCU C3 phase-probe block."""
from __future__ import annotations

import struct

MAGIC = 0x50484333
VERSION = 1
FIELDS = (
    "seq", "magic", "version", "frame", "hud_emit_cycles", "close_frame_cycles",
    "setup_packet_cycles", "setup_gif_wait_cycles", "upload_submit_cycles",
    "upload_gif_wait_cycles", "vif_submit_cycles", "submit_hook_cycles", "upload_qw",
    "view_camera_setup_cycles", "view_visibility_cycles", "view_clip_gather_group_cycles",
    "view_clip_gather_cycles", "view_clip_group_cycles", "clip_batches_in", "clip_polys_out",
    "clip_vertices_out", "view_material_group_sort_cycles", "view_sky_cycles",
    "view_world_emit_cycles", "view_object_hook_cycles", "view_inline_hud_cycles",
    "view_overlay_cycles", "view_other_cycles", "view_total_cycles", "view_count",
    "clear_view_count",
)
_BLOCK = struct.Struct("<" + "I" * len(FIELDS))
_WORD = struct.Struct("<I")
RING_MAGIC = 0x52463343
RING_CAPACITY = 128
RING_FIELDS = ("sequence", "frame", "tick", "view_count", "view0_cycles",
               "view1_cycles", "view2_cycles", "view3_cycles", "build_cycles",
               "gs_wait_cycles", "video_wait_cycles", "present_cycles",
               "submit_cycles", "total_cycles", "frame_interval_cycles",
               "publication_cycles")
_RING_HEADER = struct.Struct("<6I")
_RING_FRAME = struct.Struct("<" + "I" * len(RING_FIELDS))
RING_BYTES = _RING_HEADER.size + RING_CAPACITY * _RING_FRAME.size


def read_frame_ring(read_bytes, address: int, last_sequence: int = 0,
                    retries: int = 3) -> dict:
    """Return every retained frame since last_sequence and explicit loss counts."""
    for _ in range(retries):
        raw = read_bytes(address, RING_BYTES)
        if len(raw) != RING_BYTES:
            continue
        seq, magic, version, capacity, frontier, overwrites = _RING_HEADER.unpack_from(raw)
        if seq & 1:
            continue
        after = read_bytes(address, 4)
        if len(after) != 4 or _WORD.unpack(after)[0] != seq:
            continue
        if magic != RING_MAGIC or version != 1 or capacity != RING_CAPACITY:
            raise ValueError("unsupported C3 frame ring")
        delta = (frontier - last_sequence) & 0xffffffff
        retained = min(delta, capacity)
        first = (frontier - retained + 1) & 0xffffffff
        frames = []
        for i in range(retained):
            n = (first + i) & 0xffffffff
            offset = _RING_HEADER.size + ((n - 1) % capacity) * _RING_FRAME.size
            frame = dict(zip(RING_FIELDS, _RING_FRAME.unpack_from(raw, offset)))
            if frame["sequence"] != n:
                raise ValueError("C3 frame ring slot sequence mismatch")
            frames.append(frame)
        return {"write_sequence": frontier, "overwrites": overwrites,
                "lost_since_last_read": delta - retained, "frames": frames}
    raise TimeoutError("could not read a coherent C3 frame ring")


def decode(raw: bytes) -> dict[str, int]:
    if len(raw) != _BLOCK.size:
        raise ValueError(f"phase-probe block must be {_BLOCK.size} bytes, got {len(raw)}")
    values = dict(zip(FIELDS, _BLOCK.unpack(raw)))
    if values["seq"] & 1:
        raise ValueError("phase-probe writer was active")
    if values["magic"] != MAGIC or values["version"] != VERSION:
        raise ValueError("unsupported phase-probe magic/version")
    return values


def read_coherent(read_bytes, address: int, retries: int = 3) -> dict[str, int]:
    """Read one block and verify its leading sequence did not change afterward.

    `read_bytes(address, size)` must return exactly that many raw bytes.
    """
    for _ in range(retries):
        raw = read_bytes(address, _BLOCK.size)
        if len(raw) != _BLOCK.size:
            continue
        seq_before = _WORD.unpack_from(raw)[0]
        if seq_before & 1:
            continue
        seq_after_bytes = read_bytes(address, _WORD.size)
        if len(seq_after_bytes) != _WORD.size:
            continue
        seq_after = _WORD.unpack(seq_after_bytes)[0]
        if seq_before != seq_after:
            continue
        try:
            return decode(raw)
        except ValueError as exc:
            if "writer was active" not in str(exc):
                raise
    raise TimeoutError("could not read a coherent phase-probe block")
