"""The private spread table preserves Halo CE's geosphere order."""
import math
import unittest

from tools.halo_random_directions import BASE_VERTICES, VERTEX_COUNT, direction_table


class HaloRandomDirections(unittest.TestCase):
    def test_source_geosphere_count_and_prefix_order(self):
        table = direction_table()
        self.assertEqual(VERTEX_COUNT, 1026)
        self.assertEqual(len(table), 1026)
        self.assertEqual(table[:6], BASE_VERTICES)
        self.assertEqual(table[6], (0.06651900708675385, 0.0, 0.9977850914001465))

    def test_all_entries_are_unit_directions(self):
        for vector in direction_table():
            self.assertTrue(all(math.isfinite(component) for component in vector))
            self.assertAlmostEqual(sum(component * component for component in vector), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
