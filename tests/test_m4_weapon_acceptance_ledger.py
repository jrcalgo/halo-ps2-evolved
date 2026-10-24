"""Host-only integrity checks for the source-backed M4 evidence ledger."""

from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/hcu-source-backed-review/m4-weapon-acceptance-ledger.md"

EXPECTED_WEAPONS = {
    r"characters\sentinel\sentinel",
    r"vehicles\banshee\banshee gun",
    r"vehicles\c gun turret\c gun turret gun",
    r"vehicles\c_dropship\cd_gun\cd gun turret gun",
    r"vehicles\ghost\ghost gun",
    r"vehicles\scorpion\scorpion cannon",
    r"vehicles\warthog\warthog gun",
    r"vehicles\wraith\wraith mortar",
    r"weapons\assault rifle\assault rifle",
    r"weapons\ball\ball",
    r"weapons\energy sword\energy sword",
    r"weapons\flag\flag",
    r"weapons\flamethrower\flamethrower",
    r"weapons\fuel rod gun\fuel rod",
    r"weapons\fuel rod gun\hunter fuel rod",
    r"weapons\gravity rifle\gravity rifle",
    r"weapons\needler\needler",
    r"weapons\pistol\pistol",
    r"weapons\plasma pistol\plasma pistol",
    r"weapons\plasma rifle\plasma rifle",
    r"weapons\rocket launcher\rocket launcher",
    r"weapons\shotgun\shotgun",
    r"weapons\sniper rifle\sniper rifle",
}


class M4WeaponLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = REPORT.read_text(encoding="utf-8")

    def test_exact_23_canonical_paths_are_present_once(self):
        section = self.report.split("## Per-tag ledger", 1)[1].split(
            "## Cross-arsenal acceptance matrix", 1
        )[0]
        rows = re.findall(r"^\| `([^`]+)` \|", section, flags=re.MULTILINE)
        self.assertEqual(len(rows), 23)
        self.assertEqual(set(rows), EXPECTED_WEAPONS)
        self.assertEqual(len(set(rows)), len(rows))

        # If the ignored extracted inventory exists, ensure the report remains
        # synchronized with that exact all-map tag-path set too.
        inventory = ROOT / "build/combat-m13/all-map-weapons.json"
        if inventory.exists():
            data = json.loads(inventory.read_text(encoding="utf-8"))
            extracted = {
                weapon["path"].lower()
                for map_data in data["maps"].values()
                for weapon in map_data["weapons"]
            }
            self.assertEqual(extracted, EXPECTED_WEAPONS)

    def test_each_tag_row_explicitly_remains_open_for_hcu_m4(self):
        section = self.report.split("## Per-tag ledger", 1)[1].split(
            "## Cross-arsenal acceptance matrix", 1
        )[0]
        rows = [line for line in section.splitlines() if line.startswith("|")]
        data_rows = [line for line in rows if re.search(r"\| `[^`]+` \|", line)]
        self.assertEqual(len(data_rows), 23)
        for row in data_rows:
            self.assertTrue(row.endswith("| OPEN |"), row)
            self.assertIn("open", row.lower())

    def test_acceptance_dimensions_and_state_distinctions_are_named(self):
        required = (
            "cadence", "reload", "charge", "material", "region", "shield",
            "death", "pool", "simultaneous", "replay", "render",
            "dynamic_simulation", "5,767,168-byte region", "Parent diagnostic only",
            "OPEN", "not added",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), self.report.lower())

    def test_report_cites_real_ce_routines_and_documents_melee_stub(self):
        source_paths = (
            "source/items/weapons.c", "source/items/projectiles.c",
            "source/objects/damage.c",
        )
        for path in source_paths:
            self.assertIn(path, self.report)

        weapons = (ROOT / "submodules/halo-ce-universal/source/items/weapons.c").read_text(
            encoding="utf-8", errors="replace"
        )
        projectiles = (ROOT / "submodules/halo-ce-universal/source/items/projectiles.c").read_text(
            encoding="utf-8", errors="replace"
        )
        damage = (ROOT / "submodules/halo-ce-universal/source/objects/damage.c").read_text(
            encoding="utf-8", errors="replace"
        )
        for symbol, source in (
            ("weapon_new(", weapons),
            ("weapon_trigger_fire(", weapons),
            ("weapon_trigger_begin_firing(", weapons),
            ("weapon_trigger_release_charge(", weapons),
            ("weapon_update(", weapons),
            ("weapon_melee_attack(", weapons),
            ("projectile_new(", projectiles),
            ("projectile_update(", projectiles),
            ("projectile_detonate(", projectiles),
            ("object_cause_damage(", damage),
        ):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, source)
                self.assertIn(symbol.removesuffix("("), self.report)

        melee = weapons[weapons.index("void weapon_melee_attack("):]
        self.assertRegex(melee[:160], r"\{\s*return;\s*\}")

    def test_pool_fixture_is_not_falsely_substituted_by_parent_synthetic_code(self):
        compact = " ".join(self.report.split())
        self.assertIn("fixture is **not added**", compact)
        self.assertIn("valid CE object world", compact)
        self.assertIn("deterministic failure injection", compact)
        self.assertIn("Do not add a test that only exercises the parent", compact)
        self.assertNotIn("tests/combat_main.c", self.report)


if __name__ == "__main__":
    unittest.main()
