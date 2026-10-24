import random
import unittest

from tools.hcu_claim_interval_experiment import CapacityError, Intervals


class IntervalClaimsTest(unittest.TestCase):
    def test_differential_byte_bitmap(self):
        rng = random.Random(7318)
        interval = Intervals(1024)
        bitmap = bytearray(4096)
        for _ in range(12000):
            first = rng.randrange(len(bitmap))
            size = rng.randrange(min(100, len(bitmap) - first) + 1)
            operation = rng.randrange(3)
            if operation == 0:
                expected = True
                pos = first
                while pos < first + size:
                    width = 32 if pos % 32 == 0 and first + size - pos >= 32 else 1
                    if any(bitmap[pos:pos + width]):
                        expected = False
                        break
                    bitmap[pos:pos + width] = bytes([1]) * width
                    pos += width
                self.assertEqual(interval.claim(first, size), expected)
            elif operation == 1:
                bitmap[first:first + size] = bytes(size)
                interval.clear(first, size)
            else:
                self.assertEqual(interval.any(first, size), any(bitmap[first:first + size]))
            if _ % 100 == 0:
                self.assertEqual([interval.any(pos, 1) for pos in range(len(bitmap))],
                                 list(map(bool, bitmap)))

    def test_atomic_exhaustion_and_split(self):
        interval = Intervals(1)
        interval.claim(10, 10)
        with self.assertRaises(CapacityError):
            interval.claim(30, 10)
        self.assertEqual(interval.ranges, [(10, 20)])
        with self.assertRaises(CapacityError):
            interval.clear(14, 2)
        self.assertEqual(interval.ranges, [(10, 20)])
        interval.clear(10, 5)
        self.assertEqual(interval.ranges, [(15, 20)])

    def test_adjacent_and_partial_failed_claim(self):
        interval = Intervals()
        interval.claim(20, 10)
        self.assertFalse(interval.claim(10, 15))
        self.assertEqual(interval.ranges, [(10, 30)])
        self.assertTrue(interval.claim(30, 10))
        self.assertEqual(interval.ranges, [(10, 40)])
        self.assertFalse(interval.claim(15, 1))
        self.assertTrue(interval.claim(200, 0))

    def test_overflow_rejected_without_mutation(self):
        interval = Intervals()
        interval.claim(0, 4)
        for first, size in ((-1, 1), (0, -1), (0xffffffff, 1), (0x100000000, 0)):
            for operation in (interval.any, interval.claim, interval.clear):
                with self.assertRaises(ValueError):
                    operation(first, size)
                self.assertEqual(interval.ranges, [(0, 4)])

    def test_ce_word_failure_prefix(self):
        for occupied, start, end, expected in ((1, 0, 64, [(1, 2)]),
                                               (31, 0, 64, [(31, 32)]),
                                               (40, 0, 64, [(0, 32), (40, 41)]),
                                               (40, 1, 64, [(1, 32), (40, 41)]),
                                               (40, 33, 64, [(33, 41)]),
                                               (40, 0, 48, [(0, 41)])):
            interval = Intervals()
            interval.claim(occupied, 1)
            self.assertFalse(interval.claim(start, end - start))
            self.assertEqual(interval.ranges, expected)


if __name__ == "__main__":
    unittest.main()
