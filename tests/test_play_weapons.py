"""Every retail weapon is listed in the play pack, and each mesh is readable."""
from pathlib import Path
import struct
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
                row["pellets"], row["recharge"], row["rate"], row["rate_final"],
                row["accel"], row["decel"], row["chamber"]))
        # These are the retail starting magazines, not values derived above.
        by_path = {path: row for path, row in zip(ORDER, rows)}
        self.assertEqual(by_path[r"weapons\pistol\pistol"]["loaded_max"], 12)
        self.assertEqual(by_path[r"weapons\pistol\pistol"]["initial"], 60)
        self.assertEqual(by_path[r"weapons\assault rifle\assault rifle"]["loaded_max"], 60)
        self.assertEqual(by_path[r"weapons\assault rifle\assault rifle"]["initial"], 240)
        self.assertEqual(by_path[r"weapons\shotgun\shotgun"]["initial"], 24)
        self.assertEqual(by_path[r"weapons\shotgun\shotgun"]["enter_frames"], 15)
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
        self.assertEqual(len(lines), 46)
        # Pistol starts with 12 in the clip and 48 in reserve.
        self.assertEqual(lines[0], "clip 12 60 12 1 67 35 0 1")
        self.assertEqual(lines[1], "held 12 48 1")
        # Fuel rod's tag spends 0 rounds per shot, so the 4|8 magazine stays put.
        fuel = lines[18:20]
        self.assertEqual(fuel[0].split()[1], "4")
        self.assertEqual(fuel[1], "held 4 8 1")
        from play_weapons import PROJ, projectiles
        shots = projectiles(list(ORDER))
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
            self.assertEqual(packed[8], shot["response"])
            self.assertEqual(packed[9], shot["has"])
            self.assertEqual(packed[10], shot["pellets"])
        pistol = shots[0]
        self.assertEqual(pistol["velocity"], 0x41200001)
        self.assertEqual(pistol["range"], 40.0)
        self.assertEqual(pistol["damage_lower"], 25.0)
        self.assertEqual(pistol["response"][9], 3)
        self.assertEqual(pistol["response"][32], 2)
        self.assertEqual(shots[1]["velocity"], 0x412CCCCD)
        self.assertEqual(shots[2]["pellets"], 15)
        self.assertEqual(shots[2]["has"], 1)
        self.assertEqual(shots[4]["range"], 128.0)
        self.assertEqual(shots[11]["has"], 0)
