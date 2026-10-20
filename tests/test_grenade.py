"""Frag and plasma grenades, and the cyborg melee effect, from Blood Gulch."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def read_map():
    sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools")]
    from halo2ps2 import mapinfo, tagindex
    index = tagindex.TagIndex.read(MAP)
    header = mapinfo.read_header(MAP)
    with MAP.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
    cyborg = next(item for item in index.entries
                  if item.group == "bipd" and item.path == r"characters\cyborg_mp\cyborg_mp")
    data = cyborg.data_address - index.base
    grenade_eye = struct.unpack_from("<f", region, data + 0x400)[0]
    velocity = struct.unpack_from("<f", region, data + 0x2C0)[0]
    kind, count = struct.unpack_from("<hh", region, data + 0x2C4)
    melee_id = struct.unpack_from("<I", region, data + 0x294)[0]
    melee = next(item for item in index.entries if item.tag_id == melee_id)
    melee_damage = struct.unpack_from("<f", region, melee.data_address - index.base + 468)[0]
    blasts = {}
    blast_materials = {}
    for name in (r"weapons\frag grenade\explosion", r"weapons\plasma grenade\explosion"):
        effect = next(item for item in index.entries if item.group == "jpt!" and item.path == name)
        point = effect.data_address - index.base
        falloff, cutoff = struct.unpack_from("<ff", region, point)
        damage_flags = struct.unpack_from("<I", region, point + 456)[0]
        core_radius = struct.unpack_from("<f", region, point + 460)[0]
        minimum, lower, upper = struct.unpack_from("<fff", region, point + 464)
        blasts[name] = (falloff, cutoff, damage_flags, core_radius, minimum, lower, upper)
        blast_materials[name] = (struct.unpack_from("<f", region, point + 512 + 21 * 4)[0],
                                 struct.unpack_from("<f", region, point + 512 + 22 * 4)[0])
    fuses = {}
    materials = {}
    for name in (r"weapons\frag grenade\frag grenade", r"weapons\plasma grenade\plasma grenade"):
        projectile = next(item for item in index.entries if item.group == "proj" and item.path == name)
        base = projectile.data_address - index.base + 0x17C
        fuses[name] = struct.unpack_from("<f", region, base + 64)[0]
        response_count, response_address = struct.unpack_from("<II", region, base + 196)
        rows = []
        for i in range(response_count):
            at = response_address - index.base + i * 160
            default = struct.unpack_from("<h", region, at + 2)[0]
            potential, flags = struct.unpack_from("<hH", region, at + 36)
            skip, angle_lower, angle_upper, velocity_lower, velocity_upper = struct.unpack_from("<5f", region, at + 40)
            parallel, perpendicular = struct.unpack_from("<ff", region, at + 152)
            rows.append((default, potential, flags, skip, angle_lower, angle_upper,
                         velocity_lower, velocity_upper, parallel, perpendicular))
        materials[name] = rows
    return velocity, kind, count, melee_damage, blasts, blast_materials, fuses, materials, grenade_eye


class Grenade(unittest.TestCase):
    def test_ce_style_blast_registry_target(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "grenade-blast"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                 str(ROOT / "tests/grenade_blast_main.c"), str(ROOT / "src/game/grenade_blast.c"),
                 str(ROOT / "src/game/grenade.c"), str(ROOT / "src/game/collide.c"),
                 str(ROOT / "src/game/vital.c"), "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        self.assertIn("falloff distance=1.00 damage=120.0 body=0.600", out)
        self.assertIn("owner immunity, self-damage, and direct/core-radius LOS passed", out)

    def test_throw_fuse_and_blast(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        velocity, kind, count, melee_damage, blasts, blast_materials, fuses, materials, grenade_eye = read_map()
        self.assertEqual((velocity, kind, count, melee_damage), (10.0, 0, 4, 1000.0))
        self.assertEqual(fuses[r"weapons\frag grenade\frag grenade"], 0.5)
        self.assertEqual(fuses[r"weapons\plasma grenade\plasma grenade"], 2.0)
        self.assertEqual(blasts[r"weapons\frag grenade\explosion"][:3], (1.5, 2.5, 0x20))
        self.assertAlmostEqual(blasts[r"weapons\frag grenade\explosion"][3], 0.4, places=6)
        self.assertEqual(blasts[r"weapons\frag grenade\explosion"][4:], (80.0, 120.0, 120.0))
        self.assertEqual(blasts[r"weapons\plasma grenade\explosion"][:3], (0.5, 2.0, 0x20))
        self.assertAlmostEqual(blasts[r"weapons\plasma grenade\explosion"][3], 0.4, places=6)
        self.assertEqual(blasts[r"weapons\plasma grenade\explosion"][4:], (80.0, 120.0, 120.0))
        self.assertEqual(blast_materials[r"weapons\frag grenade\explosion"], (1.0, 1.0))
        self.assertEqual(blast_materials[r"weapons\plasma grenade\explosion"], (1.0, 1.0))
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "grenade"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/grenade_main.c"), str(ROOT / "src/game/grenade.c"),
                 str(ROOT / "src/game/collide.c"), str(ROOT / "src/game/vital.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        rows = {line.split()[0]: line.split() for line in out.splitlines()}
        material_lines = [line.split() for line in out.splitlines() if line.startswith("material ")]
        self.assertEqual(len(material_lines), 66)
        names = (r"weapons\frag grenade\frag grenade", r"weapons\plasma grenade\plasma grenade")
        for line in material_lines:
            plasma, index = map(int, line[1:3])
            source = materials[names[plasma]][index]
            self.assertEqual(tuple(map(int, line[3:6])), source[:3])
            expected = source[3:]
            for actual, expected in zip(map(float, line[6:]), expected):
                self.assertAlmostEqual(actual, expected, places=6,
                                       msg=f"grenade material {plasma}:{index}")
        self.assertEqual(rows["throw"][1], "3")
        self.assertAlmostEqual(float(rows["throw"][2]), 10.0 / 30.0, places=6)
        self.assertAlmostEqual(float(rows["throw"][3]), 1.0 - 0.0035651792 / 2.0, places=5)
        self.assertEqual(rows["throw"][4], "75432777")
        self.assertEqual(rows["air"][1], "0")
        self.assertEqual(rows["frag_fuse"][1], "15")
        self.assertEqual(rows["plasma_fuse"][1], "61")
        self.assertEqual(rows["blast_material"][1:], ["1.0", "1.0", "1.0", "1.0"])
        self.assertEqual(rows["blast0"][1], "120.0")
        self.assertEqual(rows["blast_seed"][1], "75432777")
        self.assertEqual(rows["blast2"][1], "100.0")
        self.assertEqual(rows["blast_far"][1], "0.0")
        self.assertAlmostEqual(float(rows["blast_body"][1]), 0.4, places=4)
        self.assertEqual(rows["blast_body"][2], "0")
        self.assertEqual(rows["blast_second"][1], "1")
        self.assertEqual(rows["empty"][1:], ["0", "0"])
        self.assertEqual(rows["frag_rest"][1:4], ["34", "2", "8.2088"])
        self.assertEqual(rows["frag_rest"][6], "84de0e9b")
        self.assertEqual(rows["frag_after"][1], "15")
        self.assertEqual(rows["plasma_rest"][1:4], ["29", "2", "7.9716"])
        self.assertEqual(rows["plasma_rest"][6], "4b5c952c")
        self.assertEqual(rows["plasma_after"][1], "61")
        self.assertEqual(rows["stick_rest"][1:3], ["3", "1"])
        self.assertEqual(rows["stick_rest"][6], "25dbfac1")
        self.assertEqual(rows["stick_after"][1], "61")
        self.assertEqual(rows["simultaneous"],
                         ["simultaneous", "8", "15", "0", "0.000", "-1.200", "1", "42eeeef6"])
        sys.path.insert(0, str(ROOT / "tools"))
        from convert_collision import collision_payload
        payload, _tags = collision_payload(MAP)
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "bloodgulch-collision.bin"
            fixture.write_bytes(payload + struct.pack("<f", grenade_eye))
            exe = Path(temp) / "grenade-bsp"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/grenade_bsp_main.c"),
                 str(ROOT / "src/game/grenade.c"), str(ROOT / "src/game/collide.c"),
                 "-lm", "-o", str(exe)], check=True, capture_output=True)
            result = subprocess.run([str(exe), str(fixture)], check=False,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("hit=1 bounces=1 alive=1", result.stdout)
        self.assertIn("retail_throw_exploded=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
