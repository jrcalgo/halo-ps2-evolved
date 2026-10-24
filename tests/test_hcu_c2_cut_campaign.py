"""C2.3 cut campaign: refuse any campaign-only cut the C1 actor roster reaches.

The cut lane may remove an actor type only when no roster variant uses it.
This test reads the committed roster and checks the refusal evidence.
The roster covers campaign maps only (a10..d40); it does not cover the multiplayer
survival or bot maps, so it cannot clear any actor type for those profiles.
"""
import collections
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROSTER = ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json"

# Index into actor_type_definitions[] (submodules/halo-ce-universal/source/ai/actor_types.c).
ACTOR_TYPE_NAMES = {
    0: "elite", 1: "jackal", 2: "grunt", 3: "hunter", 4: "engineer",
    5: "elite", 6: "marine", 7: "marine", 8: "crew", 9: "flood",
    10: "infection_form", 11: "carrier_form", 12: "sentinel", 13: "sentinel",
    14: "grunt", 15: "mounted_weapon",
}

# Actor types the attribution's a3 class would cut (submodule source/ai/actor_type_*.c).
A3_CUT_TYPES = {
    "flood": 9, "infection_form": 10, "carrier_form": 11, "hunter": 3,
    "engineer": 4, "crew": 8, "sentinel": 12,
}


class C2CutCampaignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads(ROSTER.read_text())
        cls.variants = data["variants"]
        cls.types_by_map = collections.defaultdict(collections.Counter)
        for variant in cls.variants:
            t = variant.get("actor_type")
            if t is not None:
                cls.types_by_map[t][variant.get("map")] += 1

    def test_roster_reaches_every_a3_actor_type(self):
        # Every type the a3 class would cut is used by at least one roster variant.
        for name, index in A3_CUT_TYPES.items():
            with self.subTest(actor_type=name):
                self.assertGreater(
                    sum(self.types_by_map[index].values()), 0,
                    f"roster has no variant of {name} (index {index}); a cut may be possible")

    def test_roster_has_variants(self):
        self.assertGreater(len(self.variants), 0)
        self.assertGreater(len(self.types_by_map), 0)


if __name__ == "__main__":
    unittest.main()
