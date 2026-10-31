#!/usr/bin/env python3
"""Collect the optional C3 frame ring without requiring the session-trace ABI."""
import argparse
import json
import subprocess
import time
from pathlib import Path

from collect_native_fixture import Pine
from hcu_c3_phase_probe import (RING_BYTES, RING_MAGIC, RING_VERSION,
                               RING_CAPACITY, _RING_HEADER, read_frame_ring)

ROOT = Path(__file__).resolve().parents[1]
NM = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-nm"


def ring_address(elf):
    output = subprocess.check_output([str(NM), "-S", str(elf)], text=True)
    matches = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] == "g_hcu_c3_frame_probe_ring":
            address, size = int(parts[0], 16), int(parts[1], 16)
            if size != RING_BYTES:
                raise ValueError(f"C3 ring ABI size {size} differs from decoder {RING_BYTES}")
            matches.append(address)
    if len(matches) != 1:
        raise ValueError("expected one C3 frame ring symbol")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=120)
    parser.add_argument("--interval", type=float, default=.1)
    args = parser.parse_args()
    address = ring_address(args.elf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pine = Pine(args.socket)
    frontier = 0
    deadline = time.monotonic() + args.duration
    with args.out.open("w") as out:
        while time.monotonic() < deadline:
            try:
                # The guest often boots after the collector. An all-zero ring is
                # an expected pre-render state, so wait quietly for its ABI header
                # instead of filling the capture with repeated startup errors.
                header = pine.read(address, _RING_HEADER.size)
                if len(header) == _RING_HEADER.size:
                    _seq, magic, version, capacity, _frontier, _overwrites = _RING_HEADER.unpack(header)
                    if magic == 0:
                        time.sleep(args.interval)
                        continue
                    if (magic, version, capacity) != (RING_MAGIC, RING_VERSION, RING_CAPACITY):
                        raise ValueError("unsupported C3 frame ring header")
                result = read_frame_ring(pine.read, address, frontier)
            except (FileNotFoundError, ConnectionRefusedError, TimeoutError, ValueError, RuntimeError) as error:
                pine.close()
                out.write(json.dumps({"kind": "collector_status", "error": str(error),
                                      "mono_ns": time.monotonic_ns()}) + "\n")
                out.flush()
                time.sleep(args.interval)
                continue
            if result["write_sequence"] != frontier:
                for frame in result["frames"]:
                    out.write(json.dumps({"kind": "c3_frame_probe", "probe": frame,
                                          "ring_write_sequence": result["write_sequence"],
                                          "ring_overwrites": result["overwrites"],
                                          "lost_since_last_read": result["lost_since_last_read"],
                                          "mono_ns": time.monotonic_ns()}) + "\n")
                out.flush()
                frontier = result["write_sequence"]
            time.sleep(args.interval)
    pine.close()


if __name__ == "__main__":
    main()
