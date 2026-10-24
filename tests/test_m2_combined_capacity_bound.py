"""Keep the optimistic M2 animation/BSP capacity bound reproducible."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_MAPS = {
    "a10", "a30", "a50", "b30", "b40",
    "c10", "c20", "c40", "d20", "d40",
}
EXPECTED_ALIGNED_PAIRS = {
    "a10": 10_550_832,
    "a30": 11_525_120,
    "a50": 10_977_888,
    "b30": 10_616_560,
    "b40": 11_382_816,
    "c10": 10_892_784,
    "c20": 9_168_640,
    "c40": 10_748_240,
    "d20": 10_762_768,
    "d40": 10_194_960,
}


def load_report(name):
    return json.loads((ROOT / "docs/reports" / name).read_text())


def align16(value):
    return (value + 15) & ~15


class CombinedCapacityBoundTests(unittest.TestCase):
    def test_optimistic_animation_and_bsp_subtractions_still_exceed_map_owner(self):
        working = load_report("retail-map-working-set-2fba411b.json")
        animation = load_report("retail-animation-ranges-2fba411b.json")
        bsp = load_report("retail-bsp-schema-2fba411b.json")
        budget = json.loads((ROOT / "config/memory-budget.json").read_text())

        self.assertEqual(working["schema_elf_sha256"],
                         animation["schema_elf_sha256"])
        self.assertEqual(working["schema_elf_sha256"],
                         bsp["schema_elf_sha256"])
        self.assertEqual(working["schema_elf_sha256"],
                         "2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa")

        work_rows = {row["map"]: row for row in working["maps"]}
        animation_rows = {row["map"]: row for row in animation["maps"]}
        bsp_rows = {row["map"]: row for row in bsp["maps"]}
        self.assertEqual(set(work_rows) & CAMPAIGN_MAPS, CAMPAIGN_MAPS)
        self.assertEqual(set(animation_rows) & CAMPAIGN_MAPS, CAMPAIGN_MAPS)
        self.assertEqual(set(bsp_rows) & CAMPAIGN_MAPS, CAMPAIGN_MAPS)

        regions = {region["name"]: region["bytes"]
                   for region in budget["regions"]}
        bsp_capacity = regions["current_bsp"]
        candidates = {}
        for name in sorted(CAMPAIGN_MAPS):
            work_row = work_rows[name]
            animation_row = animation_rows[name]
            bsp_row = bsp_rows[name]
            self.assertEqual(animation_row["source_sha256"],
                             bsp_row["source_sha256"], name)
            self.assertEqual(work_row["animation_data_bytes_candidate_externalization"],
                             animation_row["payload_bytes_sum"], name)

            # Deliberately grant zero EE cost to both candidate replacements.
            # The BSP value is the largest independently referenced BSP after
            # subtracting compressed vertices, not a sum over all BSPs.
            tag_bytes = work_row["tag_image_bytes_after_animation_data_externalization"]
            projected_bsp_bytes = max(
                record["bytes_if_compressed_vertices_externalized"]
                for record in bsp_row["structure_bsps"])
            pair_bytes = align16(tag_bytes) + align16(projected_bsp_bytes)
            candidates[name] = pair_bytes
            self.assertGreater(pair_bytes, bsp_capacity, name)

        self.assertEqual(min(candidates.values()), 9_168_640)  # c20
        self.assertEqual(max(candidates.values()), 11_525_120)  # a30
        self.assertEqual(candidates, EXPECTED_ALIGNED_PAIRS)


if __name__ == "__main__":
    unittest.main()
