import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from hcu_c3_phase_probe import (RING_BYTES, RING_CAPACITY, RING_MAGIC,
                                RING_FIELDS, read_frame_ring)


def ring(frontier):
    raw = bytearray(RING_BYTES)
    struct.pack_into("<6I", raw, 0, 2, RING_MAGIC, 1, RING_CAPACITY,
                     frontier, max(0, frontier - RING_CAPACITY))
    for n in range(max(1, frontier - RING_CAPACITY + 1), frontier + 1):
        offset = 24 + ((n - 1) % RING_CAPACITY) * 4 * len(RING_FIELDS)
        struct.pack_into("<" + "I" * len(RING_FIELDS), raw, offset,
                         n, n + 100, n, 2, *([n] * (len(RING_FIELDS) - 4)))
    return bytes(raw)


class FrameRingTests(unittest.TestCase):
    def test_wrap_reports_loss_and_keeps_each_retained_frame(self):
        raw = ring(150)
        result = read_frame_ring(lambda address, size: raw[address:address + size], 0, 10)
        self.assertEqual(result["lost_since_last_read"], 12)
        self.assertEqual([x["sequence"] for x in result["frames"]], list(range(23, 151)))
        self.assertEqual(result["frames"][-1]["view1_cycles"], 150)

    def test_torn_sequence_retries(self):
        raw = ring(1)
        calls = 0

        def read(address, size):
            nonlocal calls
            calls += 1
            if calls == 2:
                return struct.pack("<I", 4)
            return raw[address:address + size]

        self.assertEqual(read_frame_ring(read, 0)["write_sequence"], 1)
        self.assertEqual(calls, 4)


if __name__ == "__main__":
    unittest.main()
