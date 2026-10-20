"""Pistol and assault rifle bullets from the Blood Gulch projectile tags."""
from pathlib import Path
import math
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def bullet(path, name):
    sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools")]
    from halo2ps2 import mapinfo, tagindex
    index = tagindex.TagIndex.read(path)
    header = mapinfo.read_header(path)
    with path.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
    entry = next(item for item in index.entries if item.group == "proj" and item.path == name)
    data = entry.data_address - index.base
    base = data + 0x17C
    velocity = struct.unpack_from("<I", region, base + 104)[0]
    maximum_range = struct.unpack_from("<f", region, base + 76)[0]
    count, address = struct.unpack_from("<II", region, base + 196)
    responses = [struct.unpack_from("<h", region, address - index.base + i * 160 + 2)[0]
                 for i in range(count)]
    material_profiles = []
    for i in range(count):
        at = address - index.base + i * 160
        potential, flags = struct.unpack_from("<hH", region, at + 36)
        potential_bounds = struct.unpack_from("<5f", region, at + 40)
        angular_noise, velocity_noise = struct.unpack_from("<2f", region, at + 96)
        parallel_friction, perpendicular_friction = struct.unpack_from("<2f", region, at + 152)
        material_profiles.append((potential, flags, *potential_bounds, angular_noise,
                                  velocity_noise, parallel_friction, perpendicular_friction))
    damage_id = struct.unpack_from("<I", region, base + 180)[0]
    damage = next(item for item in index.entries if item.tag_id == damage_id)
    point = damage.data_address - index.base
    minimum, lower, upper = struct.unpack_from("<fff", region, point + 464)
    return velocity, maximum_range, responses, material_profiles, lower, upper, minimum


class Shot(unittest.TestCase):
    def test_actor_mesh_hit_preserves_ce_node_and_resistance_indices(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "shot-actor"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"), str(ROOT / "tests/shot_actor_main.c"),
                 str(ROOT / "src/game/shot.c"), str(ROOT / "src/game/collpack.c"),
                 str(ROOT / "src/game/collide.c"), "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            output = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        self.assertIn("actor shot node=0 region=0 part=2 resistance=2 damage=25.0", output)
        self.assertIn("actor penetration impacts=2 objects=13,14", output)

    def test_weapon_replay_independent_of_presentation_work(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "weapon-replay"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"), str(ROOT / "tests/weapon_replay_main.c"),
                 str(ROOT / "src/game/gun.c"), str(ROOT / "src/game/shot.c"),
                 str(ROOT / "src/game/collpack.c"),
                 str(ROOT / "src/game/collide.c"), str(ROOT / "src/game/vital.c"),
                 str(ROOT / "src/game/grenade.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True, text=True)
            runs = [subprocess.run([str(exe), str(presents)], check=True,
                                   capture_output=True, text=True).stdout.split()
                    for presents in (0, 1, 4)]
        self.assertEqual([row[0] for row in runs], [runs[0][0]] * 3)
        self.assertEqual(len({row[1] for row in runs}), 3)
        for row in runs:
            self.assertIn("dead=1", row)
            self.assertEqual(row[3].split("=")[1], row[4].split("=")[1])
            self.assertIn("frag=1", row)

    def test_pistol_gun_projectile_and_vitality_integration(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "weapon-damage"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"), str(ROOT / "tests/weapon_damage_main.c"),
                 str(ROOT / "src/game/gun.c"), str(ROOT / "src/game/shot.c"),
                 str(ROOT / "src/game/collpack.c"),
                 str(ROOT / "src/game/collide.c"), str(ROOT / "src/game/vital.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True, text=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
        self.assertIn("pistol-unit ticks=", result.stdout)
        values = result.stdout.split()
        self.assertEqual(values[2].split("=")[1], values[3].split("=")[1])
        self.assertIn("dead=1", result.stdout)
        needler = next(line.split() for line in result.stdout.splitlines()
                       if line.startswith("needler-attach "))
        self.assertEqual(needler[1], "fuse_ticks=23")
        self.assertEqual(needler[2], "damage=10.0")
        self.assertAlmostEqual(float(needler[3].split("=")[1]), 0.867, places=3)
        self.assertEqual(needler[4], "body=1.0")

    def test_fixed_seed_shotgun_cone_uses_packed_ce_table(self):
        subprocess.run([sys.executable, str(ROOT / "tools/play_weapons.py")], check=True,
                       capture_output=True, text=True)
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "shot-cone"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-ffp-contract=off",
                 "-I" + str(ROOT / "src"), str(ROOT / "tests/shot_cone_pack_main.c"),
                 str(ROOT / "src/game/shot.c"), str(ROOT / "src/game/collpack.c"),
                 str(ROOT / "src/game/collide.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            command = [str(exe), str(ROOT / "build/play-objects/weapons.fp")]
            first = subprocess.run(command, check=True, capture_output=True, text=True).stdout
            second = subprocess.run(command, check=True, capture_output=True, text=True).stdout
        self.assertEqual(first, second)
        rows = [line.split() for line in first.splitlines()]
        self.assertEqual(len(rows), 15)
        self.assertEqual(rows[0][1:], ["0.997923851", "-0.059197418", "0.025370322", "5e8885db"])
        self.assertEqual(rows[-1][-1], "c03b4ad7")
        for row in rows:
            vector = tuple(map(float, row[1:4]))
            self.assertAlmostEqual(sum(component * component for component in vector), 1.0, places=5)
            self.assertGreaterEqual(vector[0], math.cos(math.radians(10.0001)))

    def test_bullet_flight_hit_and_damage(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        pistol = bullet(MAP, r"weapons\pistol\bullet")
        rifle = bullet(MAP, r"weapons\assault rifle\bullet")
        self.assertEqual(pistol[0], 0x41200001)
        self.assertEqual(rifle[0], 0x412CCCCD)
        self.assertEqual(pistol[1], 40.0)
        self.assertEqual(rifle[1], 40.0)
        self.assertEqual((pistol[4], pistol[5]), (25.0, 25.0))
        self.assertEqual((rifle[4], rifle[5]), (10.0, 10.0))
        self.assertEqual((pistol[6], rifle[6]), (25.0, 10.0))
        self.assertEqual((pistol[2][0], pistol[2][9], pistol[2][32]), (0, 3, 2))
        self.assertEqual((rifle[2][0], rifle[2][9], rifle[2][32]), (0, 3, 2))

        for name, projectile in (("pistol", pistol), ("rifle", rifle)):
            self.assertEqual(len(projectile[3]), 33)
            self.assertTrue(set(projectile[2]).issubset({0, 2, 3}),
                            f"{name} uses a response not handled by the bounded shot path")
            for material, profile in enumerate(projectile[3]):
                self.assertEqual(profile[:2], (0, 0), f"{name} potential response {material}")
                self.assertEqual(profile[2:7], (0.0,) * 5, f"{name} potential bounds {material}")
                self.assertEqual(profile[7:9], (0.0, 0.0), f"{name} impact noise {material}")
                self.assertEqual(profile[9:11], (0.0, 0.0), f"{name} reflection friction {material}")
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "shot"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/shot_main.c"), str(ROOT / "src/game/shot.c"),
                 str(ROOT / "src/game/collpack.c"),
                 str(ROOT / "src/game/collide.c"), "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        reports = out.splitlines()
        first = [line.split() for line in reports if line.startswith("pistol first")][0]
        self.assertAlmostEqual(float(first[2]), 10.000000954, places=6)
        self.assertAlmostEqual(float(first[3]), -0.0035651792 / 2, places=6)
        self.assertAlmostEqual(float(first[5]), -0.0035651792, places=6)
        range_line = [line.split() for line in reports if line.startswith("pistol range")][0]
        self.assertEqual(range_line[2], "3")
        self.assertAlmostEqual(float(range_line[3]), 40.0, places=3)
        self.assertEqual(range_line[4], "2")
        stop = [line.split() for line in reports if line.startswith("pistol_stop")][0]
        self.assertEqual(stop[2:5], ["0", "1", "5.0000"])
        self.assertEqual(stop[7], "cd305e6a")
        through = [line.split() for line in reports if line.startswith("pistol_through")][0]
        self.assertEqual(through[2:5], ["0", "2", "5.0000"])
        bounce = [line.split() for line in reports if line.startswith("pistol_bounce")][0]
        self.assertEqual(bounce[2], "1")
        self.assertAlmostEqual(float(bounce[4]), 0.0, places=3)
        self.assertAlmostEqual(float(bounce[5]), -10.0, places=3)
        self.assertAlmostEqual(float(bounce[6]), -0.0035651792, places=4)
        body = [line.split() for line in reports if line.startswith("pistol body")][0]
        rifle_body = [line.split() for line in reports if line.startswith("rifle body")][0]
        self.assertEqual(body[3], "25.0")
        self.assertEqual(rifle_body[3], "10.0")
        self.assertEqual(body[5], "25dbfac1")
        self.assertAlmostEqual(float(body[4]), 4.5, places=3)
        spread = [line.split() for line in reports if line.startswith("spread")][0]
        self.assertAlmostEqual(float(spread[1]), 0.997923851, places=7)
        self.assertAlmostEqual(float(spread[2]), 0.064404875, places=7)
        self.assertAlmostEqual(float(spread[3]), 0.0, places=7)
        self.assertEqual(spread[4], "5e8885db")
        error_angle = [line.split() for line in reports if line.startswith("error_angle ")][0]
        lower_angle, upper_angle = map(float, error_angle[1:3])
        self.assertGreater(lower_angle, 0.0)
        self.assertLess(lower_angle, 5.0)
        self.assertGreater(upper_angle, lower_angle)
        self.assertLess(upper_angle, 10.0)
        self.assertEqual(error_angle[3], error_angle[4])
        pierced = [line.split() for line in reports if line.startswith("pierce_friction ")][0]
        self.assertEqual(pierced[1:4], ["1", "1", "1"])
        self.assertAlmostEqual(float(pierced[4]), 9.9, places=4,
                               msg="after object friction CE restores a sub-final speed to 0.99 final velocity")
        self.assertAlmostEqual(float(pierced[5]), 6.39, places=3,
                               msg="the remaining within-tick travel still reflects the 0.7 material friction")
        pool = [line.split() for line in reports if line.startswith("pool ")][0]
        self.assertEqual(pool, ["pool", "0", "1", "-1", "-1"])
        saturated = [line.split() for line in reports if line.startswith("saturated ")][0]
        self.assertEqual(saturated[1:4], ["1", "3", "1"])
        self.assertEqual(saturated[4], saturated[5], "dropped pellets still consume CE cone RNG")
        for actual, expected in zip(map(float, saturated[6:9]), map(float, saturated[9:12])):
            self.assertAlmostEqual(actual, expected, places=5,
                                   msg="identical-error pellets retain first sampled direction")
        fan = [line.split() for line in reports if line.startswith("fan ")][0]
        self.assertEqual(fan[1:4], ["4", "0", "388b95df"],
                         "each allocated projectile consumes its CE timer-range draw")
        expected_angles = (-5.0, 5.0, 5.0, -5.0)
        for i, angle in enumerate(expected_angles):
            self.assertAlmostEqual(float(fan[4 + i * 2]), 10.0 * math.cos(math.radians(angle)), places=5)
            self.assertAlmostEqual(float(fan[5 + i * 2]), 10.0 * math.sin(math.radians(angle)), places=5)
        scaled = [line.split() for line in reports if line.startswith("scaled_damage ")][0]
        self.assertEqual(scaled[1], "7.000",
                         "CE interpolates damage minimum to random bounds by impact-speed scale")
        air = next(line.split() for line in reports if line.startswith("fuel_air_first "))
        self.assertAlmostEqual(float(air[1]), 0.46571669, places=7)
        self.assertAlmostEqual(float(air[2]), 0.46619171, places=7)
        self.assertAlmostEqual(float(air[3]), -0.00356518, places=7)
        self.assertAlmostEqual(float(air[4]), -0.00178259, places=7)
        water = next(line.split() for line in reports if line.startswith("fuel_water_first "))
        self.assertAlmostEqual(float(water[1]), 0.45716670, places=7)
        self.assertAlmostEqual(float(water[2]), 0.46191669, places=7)
        self.assertAlmostEqual(float(water[3]), -0.00142607, places=7)
        self.assertAlmostEqual(float(water[4]), -0.00071304, places=7)
        water_end = next(line.split() for line in reports if line.startswith("fuel_water_end "))
        self.assertEqual(water_end[1], "33")
        self.assertEqual(water_end[3], "1", "water trajectory reaches CE no-lifetime disappearance")
        transition = next(line.split() for line in reports if line.startswith("fuel_transition "))
        self.assertEqual(transition[1:3], ["1", "1"])
        self.assertAlmostEqual(float(transition[3]), 0.44770283, places=7)
        crossing = [line.split() for line in reports if line.startswith("decel_cross ")][0]
        self.assertAlmostEqual(float(crossing[1]), 8.0356, places=3,
                               msg="CE integrates the within-tick final-speed crossing fraction")
        self.assertAlmostEqual(float(crossing[2]), 7.92, places=3,
                               msg="CE leaves a 0.99 final-speed factor after crossing")
        floor = [line.split() for line in reports if line.startswith("decel_floor ")][0]
        self.assertAlmostEqual(float(floor[1]), 15.9556, places=3)
        self.assertAlmostEqual(float(floor[2]), 7.92, places=3,
                               msg="CE restores a sub-final velocity to the 0.99 floor")
        no_lifetime = [line.split() for line in reports if line.startswith("decel_no_lifetime ")][0]
        self.assertEqual(no_lifetime[1:3], ["0", "1"],
                         "CE disappears a decelerating projectile with no timer or range at the final-speed floor")
        self.assertAlmostEqual(float(no_lifetime[3]), 8.0356, places=3,
                               msg="the disappear action occurs before another movement/collision segment")

    def test_pistol_hits_the_spawn_floor(self):
        map_path = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"
        if not map_path.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        sys.path[:0] = [str(ROOT / "tools")]
        from convert_collision import build_pack
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "collision.hp2"
            fixture.write_bytes(build_pack(map_path))
            exe = Path(temp) / "playshot"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/play_shot_main.c"),
                 str(ROOT / "src/game/collpack.c"), str(ROOT / "src/game/collide.c"),
                 str(ROOT / "src/game/move.c"), str(ROOT / "src/game/pill.c"),
                 str(ROOT / "src/game/gun.c"), str(ROOT / "src/game/shot.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe), str(fixture)], check=True, capture_output=True, text=True).stdout
        rows = {row.split()[0]: row.split() for row in out.splitlines()}
        vital = rows["vital_profile"]
        self.assertEqual(vital[1:5], ["75.0", "75.0", "6.0", "120"])
        self.assertAlmostEqual(float(vital[5]), 1.0 / 120.0, places=8)
        self.assertEqual(vital[6:10], ["21", "22", "0.0", "1.0"])
        self.assertEqual(float(vital[10]), 1.0)
        line = rows["pistol_world"]
        self.assertEqual(line[1], "hit")
        self.assertEqual(line[5], "11")
        self.assertEqual(line[6], "material")
        self.assertEqual(line[7], "7", "surface material index must map to CE runtime type before response lookup")
        self.assertEqual(line[8], "gap")
        self.assertGreater(float(line[9]), 0.4)
        self.assertLess(float(line[9]), 1.2)

    def test_ce_detonate_material_response_is_not_disappearance(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "shot"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/shot_main.c"), str(ROOT / "src/game/shot.c"),
                 str(ROOT / "src/game/collpack.c"),
                 str(ROOT / "src/game/collide.c"), "-lm", "-o", str(exe)], check=True)
            output = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        row = next(line.split() for line in output.splitlines() if line.startswith("detonate_response "))
        self.assertEqual(row[2:4], ["0", "2"])  # dead shot, SHOT_DETONATE
        nonunit = next(line.split() for line in output.splitlines() if line.startswith("potential_nonunit "))
        self.assertEqual(nonunit[1:3], ["1", "0"], "unit-only potential response cannot select on a non-unit object")
        self.assertEqual(nonunit[3], "70275607", "damage and two impact-noise draws precede the unit gate")
        unit = next(line.split() for line in output.splitlines() if line.startswith("potential_unit "))
        self.assertEqual(unit[1:3], ["0", "2"], "unit-only potential response selects on a unit object")
        self.assertEqual(unit[3], "01641bba", "the conditional skip roll is consumed only for a unit hit")
        guided = next(line.split() for line in output.splitlines() if line.startswith("guided_near "))
        self.assertAlmostEqual(float(guided[1]), 9.986295, places=5)
        self.assertAlmostEqual(float(guided[2]), 0.523360, places=5)
        self.assertAlmostEqual(float(guided[3]), 10.0, places=5,
                               msg="CE displacement uses the pre-steering average velocity")
        wander = next(line.split() for line in output.splitlines() if line.startswith("guided_wander_open "))
        self.assertEqual(wander[1:], ["10.000000", "0.000000"],
                         "the implemented exact steering subcase excludes CE's nonzero wander region")
        reflection = next(line.split() for line in output.splitlines()
                          if line.startswith("material_reflect "))
        self.assertEqual(reflection[1:3], ["1", "0"])
        self.assertAlmostEqual(float(reflection[3]), 0.9998, places=3,
                               msg="material reflection friction affects the remaining same-tick travel")
        self.assertAlmostEqual((float(reflection[4]) ** 2 + float(reflection[5]) ** 2) ** 0.5,
                               9.9, places=3,
                               msg="the next CE projectile update restores the sub-final speed floor")
        self.assertNotEqual(float(reflection[5]), 0.0,
                            "material angular noise rotates a reflected projectile")
        self.assertEqual(next(line.split() for line in output.splitlines()
                              if line.startswith("runtime_material "))[1:],
                         ["7", "-1", "-1", "-1", "-1"],
                         "BSP surface material lookup preserves CE NONE fallback for invalid records")
        seed = 0x12345678
        for _ in range(5):
            seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
        self.assertEqual(reflection[6], f"{seed:08x}")


if __name__ == "__main__":
    unittest.main()
