"""Host source/tag contract checks for M4's three special weapons.

These checks intentionally do not pretend to run a Halo CE simulation. They
pin reviewed production-source control-flow anchors and the local extracted
retail-tag audit until a linked host combat harness exists.
"""

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal/source"
TAG_AUDIT = ROOT / "build/combat-m13/all-map-weapons.json"
TAG_AUDIT_SHA256 = "3f76909c988d322d48ff51445cf1ce6d580e095a60487614f26914928e5007a0"


def function_body(path: Path, signature: str) -> str:
    """Return one C function body by counting braces after its signature."""
    source = path.read_text(encoding="utf-8", errors="replace")
    start = 0
    opening = -1
    while True:
        start = source.find(signature, start)
        if start < 0:
            break
        brace = source.find("{", start)
        semicolon = source.find(";", start)
        if brace >= 0 and (semicolon < 0 or brace < semicolon):
            opening = brace
            break
        start += len(signature)
    if opening < 0:
        raise AssertionError(f"missing function definition {signature!r} in {path}")
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AssertionError(f"unclosed function body for {signature!r}")


def weapon_record(map_name: str, path: str) -> dict:
    if not TAG_AUDIT.is_file():
        raise AssertionError(
            "tag audit absent; regenerate build/combat-m13/all-map-weapons.json "
            "using the M13 retail weapon audit before running this test"
        )
    raw = TAG_AUDIT.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != TAG_AUDIT_SHA256:
        raise AssertionError(
            f"tag-audit identity changed ({actual}); review and update the "
            "source-backed evidence before accepting changed tag values"
        )
    maps = json.loads(raw)["maps"]
    for weapon in maps[map_name]["weapons"]:
        if weapon["path"].casefold() == path.casefold():
            return weapon
    raise AssertionError(f"no {path!r} record in audited map {map_name!r}")


class SpecialWeaponSourceContractTests(unittest.TestCase):
    def test_fuel_rod_tag_charge_zero_cost_magazine_and_projectile(self):
        weapon = weapon_record("c40", r"weapons\fuel rod gun\fuel rod")
        self.assertEqual(len(weapon["triggers"]), 1)
        trigger = weapon["triggers"][0]
        self.assertEqual(trigger["charging_time"], 1.25)
        self.assertEqual(trigger["rate_initial"], 10.0)
        self.assertEqual(trigger["rate_final"], 10.0)
        self.assertEqual(trigger["rounds_per_shot"], 0)
        self.assertEqual(trigger["projectiles_per_shot"], 1)
        self.assertEqual(trigger["projectile"], r"weapons\fuel rod gun\fuel rod")
        self.assertEqual(trigger["magazine_index"], 0)
        magazine = weapon["magazines"][0]
        self.assertEqual(
            (magazine["rounds_initial"], magazine["rounds_loaded_max"],
             magazine["rounds_reloaded"], magazine["rounds_total_max"]),
            (12, 4, 4, 24),
        )
        self.assertEqual(magazine["reload_seconds_tag"], 5.0)

    def test_fuel_rod_generic_fire_and_charge_preserve_tagged_ammo_cost(self):
        weapons_c = HCU / "items/weapons.c"
        fire = function_body(weapons_c, "static void weapon_trigger_fire(")
        begin = function_body(weapons_c, "static void weapon_trigger_begin_firing(")
        self.assertIn("weapon_trigger_magazine_valid", fire)
        self.assertRegex(fire, r"magazine->rounds_loaded\s*-=?\s*trigger_definition->rounds_per_shot")
        self.assertIn("trigger_definition->charging_time>0.0f", begin)
        self.assertIn("_trigger_charging", begin)
        self.assertIn("weapon_trigger_fire(weapon_index, trigger_index)", begin)
        self.assertNotIn("fuel rod", fire.lower())

    def test_fuel_rod_projectile_uses_owner_media_and_collision_effect_routes(self):
        projectiles = HCU / "items/projectiles.c"
        new = function_body(projectiles, "boolean projectile_new(")
        deceleration = function_body(projectiles, "static void projectile_calculate_deceleration(")
        detonate = function_body(projectiles, "static void projectile_detonate(")
        collision = function_body(projectiles, "static void projectile_collision(")
        self.assertIn("object_get_ultimate_parent(projectile->object.owner_object_index)", new)
        self.assertIn("_object_wholly_under_media_bit", deceleration)
        self.assertIn("water_damage_range_upper_bound", deceleration)
        self.assertIn("air_damage_range_upper_bound", deceleration)
        self.assertIn("projectile->object.owner_object_index", detonate)
        self.assertIn("material_response->detonation_effect.index", detonate)
        self.assertIn("collision->material_type", collision)
        self.assertRegex(
            collision,
            r"collision->type\s*==\s*_collision_result_object\s*&&\s*\n?\s*"
            r"definition->projectile.impact_damage.index\s*!=\s*NONE",
        )

    def test_energy_sword_tag_is_melee_only_and_source_arbitrates_player_attack(self):
        sword = weapon_record("c40", r"weapons\energy sword\energy sword")
        self.assertEqual(sword["triggers"], [])
        self.assertEqual(sword["magazines"], [])
        biped = function_body(HCU / "units/bipeds.c", "boolean biped_update(")
        melee = function_body(HCU / "units/units.c", "void unit_cause_player_melee_damage(")
        self.assertIn("!weapon_prevents_melee_attack(weapon_index)", biped)
        self.assertIn("current_zoom_level==NONE", biped)
        self.assertIn("_first_person_weapon_animation_melee", biped)
        self.assertIn("player_melee_attack_tick", biped)
        self.assertIn("collision_test_vector", melee)
        self.assertIn("outer_count = 5", melee)
        self.assertIn("inner_count = 5", melee)
        self.assertIn("best_object_fraction>collision.t", melee)
        self.assertIn("melee_attack_damage.index", melee)
        self.assertIn("owner_object_index", melee)
        self.assertIn("owner_team_index", melee)

    def test_empty_weapon_melee_entry_is_not_mistaken_for_sword_lunge(self):
        melee_entry = function_body(HCU / "items/weapons.c", "void weapon_melee_attack(")
        self.assertRegex(melee_entry, r"return\s*;")
        self.assertNotRegex(melee_entry, r"unit_cause_player_melee_damage|lunge")
        # This sentinel prevents a future source change from silently making
        # this report's key gap claim stale; a real implementation must revise
        # both the report and the corresponding tests.
        source_paths = [HCU / "units/bipeds.c", HCU / "units/units.c", HCU / "items/weapons.c"]
        lunge_mentions = sum(
            len(re.findall(r"\blunge\b", path.read_text(encoding="utf-8", errors="replace"), re.I))
            for path in source_paths
        )
        self.assertEqual(lunge_mentions, 0, "review lunge source evidence before retaining this gap claim")

    def test_gravity_rifle_uses_flame_route_but_distinct_trigger_profile(self):
        gravity = weapon_record("bloodgulch", r"weapons\gravity rifle\gravity rifle")
        flame = weapon_record("bloodgulch", r"weapons\flamethrower\flamethrower")
        g_trigger = gravity["triggers"][0]
        f_trigger = flame["triggers"][0]
        self.assertEqual(g_trigger["projectile"], r"weapons\flamethrower\flame")
        self.assertEqual(f_trigger["projectile"], g_trigger["projectile"])
        self.assertEqual((g_trigger["rate_initial"], g_trigger["rate_final"], g_trigger["rounds_per_shot"]), (30.0, 30.0, 1))
        self.assertEqual((f_trigger["rate_initial"], f_trigger["rate_final"], f_trigger["rounds_per_shot"]), (15.0, 15.0, 1))
        self.assertEqual(g_trigger["flags"], 0)
        self.assertEqual(f_trigger["flags"], 2048)
        self.assertEqual(
            (gravity["magazines"][0]["rounds_initial"], gravity["magazines"][0]["rounds_loaded_max"], gravity["magazines"][0]["rounds_total_max"]),
            (200, 200, 400),
        )
        self.assertEqual(
            (flame["magazines"][0]["rounds_initial"], flame["magazines"][0]["rounds_loaded_max"], flame["magazines"][0]["rounds_total_max"]),
            (600, 100, 1200),
        )


if __name__ == "__main__":
    unittest.main()
