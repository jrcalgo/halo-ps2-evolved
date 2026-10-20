"""Every retail weapon is listed in the play pack, and each mesh is readable."""
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / "data/retail/weapon-audit-maps"
PACK = ROOT / "build/play-objects/bloodgulch.obj.hp2"
TABLE = ROOT / "build/play-objects/weapons.fp"
REC = struct.Struct("<64sIIHH32sI")


def m_shader(otex):
    import sys
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import texconv
    opened = texconv.MapData.open(ROOT / "data/retail/weapon-audit-maps/bloodgulch.map")
    for binding in otex.bindings:
        entry = opened.by_id.get(binding["shader_id"])
        if entry is not None and entry.path == r"sky\clear afternoon\shaders\sky clear blue":
            return binding
    raise AssertionError("clear-blue sky shader missing")


def records():
    blob = TABLE.read_bytes()
    magic, count, size = struct.unpack_from("<4sHH", blob)
    if magic != b"WFP1" or size != REC.size:
        raise AssertionError("bad weapons.fp header")
    out = []
    for index in range(count):
        path, model, anim, idle, shared, hand, _pad = REC.unpack_from(blob, 8 + index * REC.size)
        out.append({
            "path": path.split(b"\0", 1)[0].decode("latin1"),
            "model": model,
            "anim": anim,
            "idle": idle,
            "shared": shared,
            "hand": hand.split(b"\0", 1)[0].decode("latin1"),
        })
    return out


class PlayWeapons(unittest.TestCase):
    def test_every_weapon_model_is_in_the_pack(self):
        if not any(MAPS.glob("*.map")):
            self.skipTest("decompressed retail maps are not in the tree")
        subprocess.run([sys.executable, str(ROOT / "tools/play_weapons.py")], check=True)
        sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
        from halo2ps2 import animconv, hp2, modelconv, texconv
        weapons = records()
        self.assertEqual(len(weapons), 23)
        self.assertEqual(weapons[0]["path"], r"weapons\pistol\pistol")
        self.assertEqual(weapons[0]["shared"], 1)
        self.assertNotEqual(weapons[0]["model"], 0)
        pack = hp2.parse(PACK.read_bytes())
        modl = modelconv.parse_section(pack.read("MODL"))
        models = {item["tag_id"] for item in modl.models}
        graphs = {item.tag_id for item in animconv.parse_section(pack.read("ANIM")).graphs}
        meshed = [weapon for weapon in weapons if weapon["model"]]
        self.assertGreaterEqual(len(meshed), 14)
        for weapon in meshed:
            self.assertIn(weapon["model"], models)
            if weapon["anim"]:
                self.assertIn(weapon["anim"], graphs)
        self.assertTrue(all(weapon["model"] == 0 for weapon in weapons if weapon["path"].startswith("vehicles\\")))
        self.assertEqual(next(weapon["model"] for weapon in weapons
                              if weapon["path"] == r"characters\sentinel\sentinel"), 0)
        self.assertEqual(next(weapon["model"] for weapon in weapons
                              if weapon["path"] == r"weapons\fuel rod gun\hunter fuel rod"), 0)
        self.assertNotEqual(next(weapon["model"] for weapon in weapons
                                 if weapon["path"] == r"weapons\energy sword\energy sword"), 0)
        self.assertNotEqual(next(weapon["model"] for weapon in weapons
                                 if weapon["path"] == r"weapons\gravity rifle\gravity rifle"), 0)
        blob = TABLE.read_bytes()
        mark = blob.find(b"RMP1")
        self.assertGreater(mark, 0)
        _maps, = struct.unpack_from("<H", blob, mark + 4)
        remap = struct.Struct("<III BBH 64s 64s")
        arms_model, model, graph, arms_n, gun_n, _pad, arms_map, gun_map = remap.unpack_from(blob, mark + 6)
        self.assertEqual(arms_n, 37)
        self.assertEqual(gun_n, 7)
        self.assertEqual(model, weapons[0]["model"])
        self.assertEqual(graph, weapons[0]["anim"])
        self.assertEqual(arms_map[0], 0)
        self.assertNotEqual(arms_model, 0)
        otex = texconv.parse_texs(pack.read("OTEX"))
        sky = m_shader(otex)
        self.assertEqual(sky["uv_scale"], (1.0, 1.0))
        self.assertGreaterEqual(otex.textures[sky["texture"]]["width"], 64)
        by_shader = {item["shader_id"]: item for item in otex.bindings}
        for weapon in weapons:
            if "plasma pistol" not in weapon["path"] and "plasma rifle" not in weapon["path"]:
                continue
            model = next(item for item in modl.models if item["tag_id"] == weapon["model"])
            parts = modl.parts[model["first_part"]:model["first_part"] + model["part_count"]]
            self.assertTrue(parts)
            for part in parts:
                binding = by_shader[part["shader_id"]]
                self.assertNotEqual(binding["texture"], 0xFFFF)

    def test_every_weapon_magazine_matches_the_tags(self):
        if not any(MAPS.glob("*.map")):
            self.skipTest("decompressed retail maps are not in the tree")
        subprocess.run([sys.executable, str(ROOT / "tools/play_weapons.py")], check=True)
        sys.path.insert(0, str(ROOT / "tools"))
        from play_weapons import AMMO, ORDER, magazines
        blob = TABLE.read_bytes()
        at = blob.find(b"AMO1")
        self.assertGreater(at, blob.find(b"RMP1"))
        count, = struct.unpack_from("<H", blob, at + 4)
        self.assertEqual(count, 23)
        rows = magazines(list(ORDER))
        self.assertEqual(len(rows), 23)
        for index, row in enumerate(rows):
            packed = AMMO.unpack_from(blob, at + 6 + index * AMMO.size)
            self.assertEqual(packed, (
                row["loaded_max"], row["initial"], row["reloaded"], row["rounds_per_shot"],
                row["reload_frames"], row["ready_frames"], row["enter_frames"], row["flags"],
                row["pellets"], row["recharge"], row["trigger_count"], row["weapon_type"],
                row["overcharged_action"], 0, row["rate"], row["rate_final"],
                row["accel"], row["decel"], row["chamber"], row["error_accel"],
                row["error_decel"], row["charge"], row["charged"], row["heat_overheat"],
                row["heat_recovery"], row["heat_loss"], row["heat_per_round"]))
        # These are the retail starting magazines, not values derived above.
        by_path = {path: row for path, row in zip(ORDER, rows)}
        self.assertEqual(by_path[r"weapons\pistol\pistol"]["loaded_max"], 12)
        self.assertEqual(by_path[r"weapons\pistol\pistol"]["initial"], 60)
        self.assertEqual(by_path[r"weapons\assault rifle\assault rifle"]["loaded_max"], 60)
        self.assertEqual(by_path[r"weapons\assault rifle\assault rifle"]["initial"], 240)
        self.assertEqual(by_path[r"weapons\shotgun\shotgun"]["initial"], 24)
        self.assertEqual(by_path[r"weapons\shotgun\shotgun"]["enter_frames"], 15)
        self.assertAlmostEqual(by_path[r"weapons\pistol\pistol"]["error_accel"], 0.06666667014360428)
        self.assertAlmostEqual(by_path[r"weapons\pistol\pistol"]["error_decel"], 0.1666666716337204)
        plasma_pistol = by_path[r"weapons\plasma pistol\plasma pistol"]
        self.assertAlmostEqual(plasma_pistol["charge"], 0.6000000238418579)
        self.assertAlmostEqual(plasma_pistol["charged"], 45.0)
        self.assertAlmostEqual(plasma_pistol["heat_per_round"], 0.1599999964237213)
        self.assertEqual(plasma_pistol["trigger_count"], 2)
        plasma_rifle = by_path[r"weapons\plasma rifle\plasma rifle"]
        self.assertEqual(plasma_rifle["charge"], 0.0)
        self.assertAlmostEqual(plasma_rifle["heat_loss"], 0.30000001192092896)
        self.assertAlmostEqual(plasma_rifle["heat_per_round"], 0.07999999821186066)
        self.assertEqual(by_path[r"weapons\sniper rifle\sniper rifle"]["loaded_max"], 4)
        self.assertEqual(by_path[r"weapons\sniper rifle\sniper rifle"]["initial"], 12)
        self.assertEqual(by_path[r"weapons\rocket launcher\rocket launcher"]["loaded_max"], 2)
        self.assertEqual(by_path[r"weapons\rocket launcher\rocket launcher"]["initial"], 4)
        self.assertEqual(by_path[r"weapons\needler\needler"]["loaded_max"], 20)
        self.assertEqual(by_path[r"weapons\needler\needler"]["initial"], 80)
        self.assertEqual(by_path[r"weapons\flamethrower\flamethrower"]["loaded_max"], 100)
        self.assertEqual(by_path[r"weapons\flamethrower\flamethrower"]["initial"], 600)
        self.assertEqual(by_path[r"weapons\flamethrower\flamethrower"]["flags"] & 1, 1)
        self.assertEqual(by_path[r"weapons\fuel rod gun\fuel rod"]["loaded_max"], 4)
        self.assertEqual(by_path[r"weapons\fuel rod gun\fuel rod"]["rounds_per_shot"], 0)
        self.assertEqual(by_path[r"weapons\gravity rifle\gravity rifle"]["loaded_max"], 200)
        self.assertEqual(by_path[r"weapons\plasma pistol\plasma pistol"]["loaded_max"], 0)
        self.assertEqual(by_path[r"weapons\plasma rifle\plasma rifle"]["loaded_max"], 0)
        self.assertEqual(by_path[r"weapons\energy sword\energy sword"]["flags"], 0)
        self.assertEqual(by_path[r"vehicles\ghost\ghost gun"]["loaded_max"], 50)
        self.assertEqual(by_path[r"vehicles\ghost\ghost gun"]["initial"], 300)
        self.assertEqual(by_path[r"vehicles\scorpion\scorpion cannon"]["loaded_max"], 1)
        self.assertEqual(by_path[r"vehicles\scorpion\scorpion cannon"]["initial"], 9999)
        self.assertEqual(by_path[r"vehicles\wraith\wraith mortar"]["loaded_max"], 10)
        self.assertEqual(by_path[r"vehicles\wraith\wraith mortar"]["initial"], 50)
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "ammo"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/ammo_main.c"), str(ROOT / "src/game/gun.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe), str(TABLE)], check=True, capture_output=True, text=True).stdout
        lines = out.splitlines()
        self.assertEqual(len(lines), 48)
        # Pistol starts with 12 in the clip and 48 in reserve.
        self.assertEqual(lines[0], "clip 12 60 12 1 67 35 0 1")
        self.assertEqual(lines[1], "held 12 48 1")
        self.assertEqual(lines[12], "plasma pistol fired_tick=40 shots=1 heat=0.160")
        self.assertTrue(lines[15].startswith("plasma rifle shots="))
        self.assertIn("heat=", lines[15])
        # Fuel rod's tag spends 0 rounds per shot, so the 4|8 magazine stays put.
        fuel = lines[20:22]
        self.assertEqual(fuel[0].split()[1], "4")
        self.assertEqual(fuel[1], "held 4 8 1")
        from play_weapons import PROJ, SPREAD, projectiles, spreads, trigger_projectiles
        shots = projectiles(list(ORDER))
        # Retail XISO-derived Blood Gulch tags use CE response 1 (detonate)
        # on these explosive projectile families; response 1 must not fall
        # through to the port's disappear action.
        for weapon_index, expected in ((4, 32), (9, 30), (14, 30), (18, 33), (20, 32)):
            self.assertEqual(shots[weapon_index]["response"].count(1), expected,
                             ORDER[weapon_index])
        proj_at = blob.find(b"PRJ1")
        self.assertGreater(proj_at, at)
        proj_count, = struct.unpack_from("<H", blob, proj_at + 4)
        self.assertEqual(proj_count, 23)
        for index, shot in enumerate(shots):
            packed = PROJ.unpack_from(blob, proj_at + 6 + index * PROJ.size)
            self.assertEqual(packed[0], shot["velocity"])
            self.assertEqual(packed[1], shot["final_velocity"])
            self.assertEqual(packed[2], shot["deceleration_start"])
            self.assertEqual(packed[3], shot["deceleration_end"])
            self.assertEqual(packed[6], shot["damage_minimum"])
            self.assertEqual(packed[7], shot["damage_lower"])
            self.assertEqual(packed[8], shot["damage_upper"])
            self.assertEqual(packed[9], shot["response"])
            self.assertEqual(packed[10], shot["has"])
            self.assertEqual(packed[11], shot["pellets"])
            self.assertEqual(packed[13], shot["damage_material_21"])
            self.assertEqual(packed[14], shot["damage_material_22"])
            self.assertEqual(packed[15], shot["timer_upper_bound"])
            self.assertEqual(packed[16], shot["minimum_velocity"])
            self.assertEqual(packed[17], shot["maximum_damage_distance"])
            self.assertEqual(packed[18], shot["projectile_flags"])
            self.assertEqual(packed[19], shot["detonation_timer_starts"])
            self.assertEqual(packed[21], shot["timer_lower_bound"])
            self.assertEqual(packed[22:27], (
                shot["attached_damage_minimum"], shot["attached_damage_lower"],
                shot["attached_damage_upper"], shot["attached_damage_material_21"],
                shot["attached_damage_material_22"]))
            self.assertEqual(packed[27:30], (shot["water_gravity_scale"],
                shot["water_damage_range_lower_bound"], shot["water_damage_range_upper_bound"]))
            self.assertEqual(packed[30], shot["guided_angular_velocity"])
            self.assertEqual(packed[31:64], shot["damage_material_modifiers"])
            self.assertEqual(packed[64:97], shot["attached_damage_material_modifiers"])
        friction_at = blob.find(b"PRS1", proj_at)
        self.assertGreater(friction_at, proj_at)
        self.assertEqual(struct.unpack_from("<4sHH", blob, friction_at), (b"PRS1", 23, 33))
        from play_weapons import FRICTION
        for index, shot in enumerate(shots):
            friction = FRICTION.unpack_from(blob, friction_at + 8 + index * FRICTION.size)
            expected = tuple(value for material in range(33) for value in (
                shot["initial_friction"][material], shot["parallel_friction"][material],
                shot["perpendicular_friction"][material], shot["angular_noise"][material],
                shot["velocity_noise"][material]))
            self.assertEqual(friction, expected)
        potential_at = blob.find(b"POT1", friction_at)
        self.assertEqual(struct.unpack_from("<4sHH", blob, potential_at), (b"POT1", 23, 33))
        from play_weapons import POTENTIAL
        for index, shot in enumerate(shots):
            potential = POTENTIAL.unpack_from(blob, potential_at + 8 + index * POTENTIAL.size)
            expected = tuple(value for material in range(33) for value in (
                shot["potential_response"][material], shot["potential_flags"][material],
                shot["potential_skip"][material], shot["potential_angle_lower"][material],
                shot["potential_angle_upper"][material], shot["potential_velocity_lower"][material],
                shot["potential_velocity_upper"][material]))
            self.assertEqual(potential, expected)
        self.assertEqual(shots[9]["potential_response"][29], 1)
        trigger_shots = trigger_projectiles(list(ORDER))
        self.assertEqual(trigger_shots[5][1]["potential_response"][29], 3)
        pistol = shots[0]
        self.assertEqual(pistol["velocity"], 0x41200001)
        self.assertEqual(pistol["range"], 40.0)
        self.assertEqual(pistol["damage_lower"], 25.0)
        self.assertEqual(pistol["damage_minimum"], 25.0)
        self.assertEqual(pistol["damage_material_21"], 1.5)
        self.assertEqual(pistol["damage_material_22"], 1.0)
        self.assertEqual(shots[1]["damage_minimum"], 10.0)
        self.assertEqual(shots[1]["damage_material_21"], 1.0)
        self.assertEqual(shots[1]["damage_material_22"], 1.0)
        self.assertAlmostEqual(shots[1]["initial_friction"][11], 0.7)
        needler = shots[7]
        self.assertAlmostEqual(needler["guided_angular_velocity"], 1.5707963705062866)
        self.assertAlmostEqual(needler["angular_noise"][2], 0.2617993950843811)
        self.assertAlmostEqual(needler["angular_noise"][16], 0.6108652353286743)
        self.assertAlmostEqual(needler["parallel_friction"][5], 0.3)
        self.assertAlmostEqual(needler["perpendicular_friction"][5], 0.3)
        self.assertEqual(needler["projectile_flags"], 0x0b)
        self.assertEqual(needler["detonation_timer_starts"], 2)
        self.assertEqual(needler["timer_lower_bound"], 0.75)
        self.assertEqual((needler["attached_damage_minimum"], needler["attached_damage_lower"],
                          needler["attached_damage_upper"]), (10.0, 10.0, 10.0))
        self.assertEqual((needler["attached_damage_material_21"],
                          needler["attached_damage_material_22"]), (1.0, 1.0))
        fuel_rod = shots[9]
        self.assertAlmostEqual(fuel_rod["deceleration_start"], 0.0)
        self.assertAlmostEqual(fuel_rod["deceleration_end"], 100.0)
        self.assertAlmostEqual(fuel_rod["gravity"], 1.0)
        self.assertAlmostEqual(fuel_rod["water_gravity_scale"], 0.4)
        self.assertAlmostEqual(fuel_rod["water_damage_range_lower_bound"], 0.0)
        self.assertAlmostEqual(fuel_rod["water_damage_range_upper_bound"], 10.0)
        self.assertEqual(pistol["response"][9], 3)
        self.assertEqual(pistol["response"][32], 2)
        self.assertEqual(shots[1]["velocity"], 0x412CCCCD)
        self.assertEqual(shots[2]["pellets"], 15)
        self.assertEqual(shots[2]["has"], 1)
        self.assertEqual(shots[4]["range"], 128.0)
        self.assertEqual(shots[11]["has"], 0)
        cones = spreads(list(ORDER))
        rnd_at = blob.find(b"RND1")
        self.assertGreater(rnd_at, proj_at)
        rnd_count, direction_count = struct.unpack_from("<HH", blob, rnd_at + 4)
        self.assertEqual((rnd_count, direction_count), (23, 1026))
        for index, cone in enumerate(cones):
            packed = SPREAD.unpack_from(blob, rnd_at + 8 + index * SPREAD.size)
            self.assertEqual(packed, (cone["inner"], cone["lower"], cone["upper"], cone["flags"]))
        shotgun_cone = SPREAD.unpack_from(blob, rnd_at + 8 + 2 * SPREAD.size)
        self.assertEqual(shotgun_cone[:3], (0.0, 0.1745329201221466, 0.1745329201221466))
        from halo_random_directions import direction_table
        table_at = rnd_at + 8 + rnd_count * SPREAD.size
        expected_directions = direction_table()
        for index in (0, 1, 2, 3, 4, 5, 6, direction_count - 1):
            self.assertEqual(struct.unpack_from("<3f", blob, table_at + index * 12),
                             expected_directions[index])
        directions_end = table_at + direction_count * 12
        trigger_at = blob.find(b"TRG1", directions_end)
        self.assertGreaterEqual(trigger_at, directions_end)
        self.assertLessEqual(trigger_at - directions_end, 3)
        self.assertEqual(blob[directions_end:trigger_at], bytes(trigger_at - directions_end))
        self.assertEqual(struct.unpack_from("<4sHHHH", blob, trigger_at),
                         (b"TRG1", 23, 2, 256, 1))
        self.assertEqual((trigger_at + 12) % 4, 0)
        from play_weapons import TRIGGER, trigger_records
        pairs = trigger_records(list(ORDER))
        self.assertEqual(len(pairs), 23)
        # weapon_trigger_begin_firing enters charging before its overloading
        # branch. In the supplied tags, every nonzero overloading timer is
        # paired with a nonzero charging timer, so the overloading state is
        # unreachable through ordinary (non-forced) input for these paths.
        for weapon_path, trigger_pair in zip(ORDER, pairs):
            for trigger_index, trigger in enumerate(trigger_pair):
                if trigger["values"][10] > 0.0:
                    self.assertGreater(trigger["values"][8], 0.0,
                        f"{weapon_path} trigger {trigger_index} reaches CE overloading branch")
        magazine_rows = magazines(list(ORDER))
        for weapon_index, pair in enumerate(pairs):
            for trigger_index, trigger in enumerate(pair):
                offset = trigger_at + 12 + (weapon_index * 2 + trigger_index) * TRIGGER.size
                encoded = TRIGGER.pack(
                    trigger["flags"], *trigger["halves"], *trigger["values"],
                    trigger["projectile"].encode("latin1")[:63].ljust(64, b"\0"),
                    trigger["charging_effect"].encode("latin1")[:63].ljust(64, b"\0"),
                    trigger["firing_effect_count"])
                self.assertEqual(blob[offset:offset + TRIGGER.size], encoded)
            primary = pair[0]
            ammo_row = magazine_rows[weapon_index]
            if ammo_row["trigger_count"] == 0:
                self.assertEqual(primary["flags"], 0)
                self.assertEqual(primary["halves"], (0,) * 11)
                self.assertEqual(primary["values"], (0.0,) * 25)
                continue
            self.assertEqual(primary["halves"][0], ammo_row["magazine_index"])
            self.assertEqual(primary["halves"][1], ammo_row["rounds_per_shot"])
            self.assertEqual(primary["halves"][10], ammo_row["pellets"])
            self.assertEqual(primary["values"][0], ammo_row["rate"])
            self.assertEqual(primary["values"][1], ammo_row["rate_final"])
            self.assertEqual(primary["values"][8], ammo_row["charge"])
            self.assertEqual(primary["values"][9], ammo_row["charged"])
            self.assertEqual(primary["values"][16], ammo_row["heat_per_round"])
            self.assertEqual(primary["halves"][8], ammo_row["overcharged_action"])
            self.assertEqual(primary["values"][23], ammo_row["error_accel"])
            self.assertEqual(primary["values"][24], ammo_row["error_decel"])
        plasma = pairs[ORDER.index(r"weapons\plasma pistol\plasma pistol")]
        self.assertAlmostEqual(plasma[0]["values"][8], 0.6)
        self.assertAlmostEqual(plasma[0]["values"][9], 45.0)
        self.assertEqual(plasma[0]["projectile"], r"weapons\plasma pistol\bolt")
        self.assertEqual(plasma[1]["projectile"], r"weapons\plasma rifle\charged bolt")
        scorpion = pairs[ORDER.index(r"vehicles\scorpion\scorpion cannon")]
        self.assertEqual(scorpion[1]["halves"][0], -1)
        self.assertEqual(scorpion[1]["projectile"], r"vehicles\scorpion\bullet")
        prj2_at = trigger_at + 12 + len(pairs) * 2 * TRIGGER.size
        self.assertEqual(prj2_at % 4, 0)
        self.assertEqual(struct.unpack_from("<4sHH", blob, prj2_at), (b"PRJ2", 23, 2))
        from play_weapons import PROJ, trigger_projectiles
        trigger_shots = trigger_projectiles(list(ORDER))
        self.assertEqual(len(trigger_shots), 23)
        self.assertEqual(trigger_shots[ORDER.index(r"weapons\pistol\pistol")][0]["damage_flags"], 0x2)
        self.assertEqual(trigger_shots[ORDER.index(r"weapons\assault rifle\assault rifle")][0]["damage_flags"], 0)
        for weapon_index, pair in enumerate(trigger_shots):
            for trigger_index, shot in enumerate(pair):
                offset = prj2_at + 8 + (weapon_index * 2 + trigger_index) * PROJ.size
                encoded = PROJ.pack(
                    shot["velocity"], shot["final_velocity"], shot["deceleration_start"],
                    shot["deceleration_end"], shot["range"], shot["gravity"],
                    shot["damage_minimum"], shot["damage_lower"], shot["damage_upper"], shot["response"],
                    shot["has"], shot["pellets"],
                    ((shot["attached_damage_flags"] >> 1) & 1) |
                    ((shot["attached_damage_flags"] >> 10) & 2),
                    shot["damage_material_21"], shot["damage_material_22"],
                    shot["timer_upper_bound"], shot["minimum_velocity"], shot["maximum_damage_distance"],
                    shot["projectile_flags"], shot["detonation_timer_starts"],
                    shot["damage_flags"] & 0xFFFF,
                    shot["timer_lower_bound"], shot["attached_damage_minimum"],
                    shot["attached_damage_lower"], shot["attached_damage_upper"],
                    shot["attached_damage_material_21"], shot["attached_damage_material_22"],
                    shot["water_gravity_scale"], shot["water_damage_range_lower_bound"],
                    shot["water_damage_range_upper_bound"], shot["guided_angular_velocity"],
                    *shot["damage_material_modifiers"],
                    *shot["attached_damage_material_modifiers"])
                self.assertEqual(blob[offset:offset + PROJ.size], encoded)
        plasma_shot = trigger_shots[ORDER.index(r"weapons\plasma pistol\plasma pistol")][1]
        self.assertEqual(plasma_shot["has"], 1)
        self.assertEqual(plasma_shot["range"], 40.0)
        scorpion_shot = trigger_shots[ORDER.index(r"vehicles\scorpion\scorpion cannon")][1]
        self.assertEqual(scorpion_shot["has"], 1)
        prj2_friction_at = prj2_at + 8 + len(trigger_shots) * 2 * PROJ.size
        self.assertEqual(struct.unpack_from("<4sHH", blob, prj2_friction_at), (b"PRS2", 23, 33))
        friction2_at = prj2_friction_at + 8
        for weapon_index, pair in enumerate(trigger_shots):
            for trigger_index, shot in enumerate(pair):
                offset = friction2_at + (weapon_index * 2 + trigger_index) * FRICTION.size
                expected = tuple(value for material in range(33) for value in (
                    shot["initial_friction"][material], shot["parallel_friction"][material],
                    shot["perpendicular_friction"][material], shot["angular_noise"][material],
                    shot["velocity_noise"][material]))
                self.assertEqual(FRICTION.unpack_from(blob, offset), expected)
        potential2_at = friction2_at + len(trigger_shots) * 2 * FRICTION.size
        self.assertEqual(struct.unpack_from("<4sHH", blob, potential2_at), (b"POT2", 23, 33))
        mag2_at = potential2_at + 8 + len(trigger_shots) * 2 * POTENTIAL.size
        self.assertEqual(struct.unpack_from("<4sHHHH", blob, mag2_at), (b"MAG2", 23, 2, 28, 0))
        self.assertEqual(mag2_at % 4, 0)
        from play_weapons import MAGAZINE, magazine_records
        magazine_pairs = magazine_records(list(ORDER))
        self.assertEqual(len(magazine_pairs), 23)
        for weapon_index, pair in enumerate(magazine_pairs):
            for magazine_index, magazine in enumerate(pair):
                offset = mag2_at + 12 + (weapon_index * 2 + magazine_index) * MAGAZINE.size
                encoded = MAGAZINE.pack(
                    magazine["flags"], *magazine["values"], magazine["reload"],
                    magazine["rounds_reloaded"], magazine["pad"], magazine["chamber"])
                self.assertEqual(blob[offset:offset + MAGAZINE.size], encoded)
        for weapon_index, magazine in enumerate(magazine_pairs):
            packed_primary = magazine[0]
            expected_primary = magazine_rows[weapon_index]
            self.assertEqual(packed_primary["values"][1], expected_primary["initial"])
            self.assertEqual(packed_primary["values"][3], expected_primary["loaded_max"])
            self.assertEqual(packed_primary["rounds_reloaded"], expected_primary["reloaded"])
        policy_at = mag2_at + 12 + len(magazine_pairs) * 2 * MAGAZINE.size
        self.assertEqual(policy_at % 4, 0)
        self.assertEqual(struct.unpack_from("<4sHHHH", blob, policy_at),
                         (b"WMD1", 23, 24, 0, 0))
        from play_weapons import weapon_trigger_modes
        policies = weapon_trigger_modes(list(ORDER))
        for index, policy in enumerate(policies):
            self.assertEqual(
                blob[policy_at + 12 + index * 24:policy_at + 36 + index * 24],
                struct.pack("<Ihh4f", policy["flags"], policy["mode"], policy["alternate"],
                            policy["age_heat"], policy["age_rate"],
                            policy["misfire_start"], policy["misfire_chance"]))
        scorpion_policy = policies[ORDER.index(r"vehicles\scorpion\scorpion cannon")]
        self.assertEqual(scorpion_policy["flags"] & (1 << 12), 1 << 12)
        self.assertEqual(scorpion_policy["mode"], 0)
        banshee_policy = policies[ORDER.index(r"vehicles\banshee\banshee gun")]
        self.assertEqual(banshee_policy["mode"], 2)
        plasma_rifle_policy = policies[ORDER.index(r"weapons\plasma rifle\plasma rifle")]
        self.assertAlmostEqual(plasma_rifle_policy["age_heat"], 0.2)
        self.assertAlmostEqual(plasma_rifle_policy["age_rate"], 0.2)
        self.assertAlmostEqual(plasma_rifle_policy["misfire_start"], 0.9)
        self.assertAlmostEqual(plasma_rifle_policy["misfire_chance"], 0.5)
        plasma_pistol_policy = policies[ORDER.index(r"weapons\plasma pistol\plasma pistol")]
        self.assertAlmostEqual(plasma_pistol_policy["misfire_start"], 0.9)
        self.assertAlmostEqual(plasma_pistol_policy["misfire_chance"], 0.5)
        effect_at = policy_at + 12 + len(policies) * 24
        from play_weapons import FIRING_EFFECT, firing_effect_records
        self.assertEqual(struct.unpack_from("<4sHHHHHH", blob, effect_at),
                         (b"FEF1", 23, 2, 2, FIRING_EFFECT.size, 1, 0))
        effects = firing_effect_records(list(ORDER))
        self.assertEqual(len(effects), 23)
        for weapon_index, trigger_pair in enumerate(effects):
            for trigger_index, effect_pair in enumerate(trigger_pair):
                for effect_index, item in enumerate(effect_pair):
                    offset = effect_at + 16 + (((weapon_index * 2 + trigger_index) * 2 +
                                                 effect_index) * FIRING_EFFECT.size)
                    encoded = FIRING_EFFECT.pack(
                        item["lower"], item["upper"],
                        *(path.encode("latin1")[:63].ljust(64, b"\0")
                          for path in item["paths"]))
                    self.assertEqual(blob[offset:offset + FIRING_EFFECT.size], encoded)

    def test_runtime_loads_selected_trigger_and_projectile_pair(self):
        if not any(MAPS.glob("*.map")):
            self.skipTest("decompressed retail maps are not in the tree")
        subprocess.run([sys.executable, str(ROOT / "tools/play_weapons.py")], check=True)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            host = temp_path / "host:"
            host.mkdir()
            shutil.copyfile(TABLE, host / "weapons.fp")
            exe = temp_path / "play-fp-trigger"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-ffunction-sections", "-fdata-sections", "-fsanitize=undefined",
                 "-I" + str(ROOT / "src"),
                 "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                 str(ROOT / "tests/play_fp_trigger_main.c"),
                 str(ROOT / "src/game/play_fp.c"), str(ROOT / "src/game/gun.c"),
                 str(ROOT / "src/game/shot.c"), str(ROOT / "src/game/collide.c"),
                 str(ROOT / "src/game/collpack.c"),
                 str(ROOT / "src/game/vital.c"), "-lm",
                 "-Wl,--gc-sections", "-o", str(exe)], check=True, capture_output=True)
            result = subprocess.run([str(exe)], cwd=temp_path,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                             f"exit {result.returncode}: {result.stdout}{result.stderr}")
            self.assertIn("TRG1/PRJ2 lifecycle/MAG2/WMD1/FEF1 traces and CE charge/release verified", result.stdout)
