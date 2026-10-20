"""Pistol and assault rifle cadence from the Blood Gulch tags and weapons.c."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def required_ticks(rate):
    return 30.0 / rate if rate > 0.0001 else 0.0


def _region(path):
    import struct
    sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools")]
    from halo2ps2 import mapinfo, tagindex
    index = tagindex.TagIndex.read(path)
    header = mapinfo.read_header(path)
    with path.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
    return index, region


def first_person_frames(path):
    """(ready frames, reload-empty frames) from the first-person animation graph."""
    import struct
    index, region = _region(path)
    by_id = {entry.tag_id: entry for entry in index.entries}
    found = {}
    for entry in index.entries:
        if entry.group != "weap":
            continue
        if entry.path not in (
                r"weapons\pistol\pistol",
                r"weapons\assault rifle\assault rifle",
                r"weapons\shotgun\shotgun"):
            continue
        data = entry.data_address - index.base
        antr = by_id[struct.unpack_from("<I", region, data + 0x478)[0]]
        graph = antr.data_address - index.base
        count, address = struct.unpack_from("<II", region, graph + 0x48)
        record = region[address - index.base:address - index.base + 0x1C]
        slots, slot_address = struct.unpack_from("<II", record, 16)
        raw = region[slot_address - index.base:slot_address - index.base + slots * 2]
        anim_count, anim_address = struct.unpack_from("<II", region, graph + 0x74)
        anims = region[anim_address - index.base:anim_address - index.base + anim_count * 180]

        def frames(slot):
            anim = struct.unpack_from("<h", raw, slot * 2)[0]
            return struct.unpack_from("<h", anims, anim * 180 + 34)[0]

        found[entry.path] = (frames(10), frames(7))
    return found


def shotgun_enter_frames(path):
    import struct
    index, region = _region(path)
    by_id = {entry.tag_id: entry for entry in index.entries}
    entry = next(item for item in index.entries if item.path == r"weapons\shotgun\shotgun")
    data = entry.data_address - index.base
    antr = by_id[struct.unpack_from("<I", region, data + 0x478)[0]]
    graph = antr.data_address - index.base
    count, address = struct.unpack_from("<II", region, graph + 0x48)
    record = region[address - index.base:address - index.base + 0x1C]
    slots, slot_address = struct.unpack_from("<II", record, 16)
    raw = region[slot_address - index.base:slot_address - index.base + slots * 2]
    anim = struct.unpack_from("<h", raw, 23 * 2)[0]
    anim_count, anim_address = struct.unpack_from("<II", region, graph + 0x74)
    return struct.unpack_from("<h", region, anim_address - index.base + anim * 180 + 34)[0]


def object_animation_id(path, weapon_path):
    import struct
    index, region = _region(path)
    entry = next(item for item in index.entries if item.path == weapon_path)
    data = entry.data_address - index.base
    tag_id = struct.unpack_from("<I", region, data + 0x44)[0]
    if tag_id == 0xFFFFFFFF:
        return None
    return tag_id


def object_weapon_slots(path, weapon_path, slots):
    import struct
    index, region = _region(path)
    by_id = {entry.tag_id: entry for entry in index.entries}
    entry = next(item for item in index.entries if item.path == weapon_path)
    data = entry.data_address - index.base
    antr = by_id[struct.unpack_from("<I", region, data + 0x44)[0]]
    graph = antr.data_address - index.base
    count, address = struct.unpack_from("<II", region, graph + 0x18)
    record = region[address - index.base:address - index.base + 0x1C]
    slot_count, slot_address = struct.unpack_from("<II", record, 16)
    raw = region[slot_address - index.base:slot_address - index.base + slot_count * 2]
    return tuple(struct.unpack_from("<h", raw, slot * 2)[0] for slot in slots)


def shot_ticks(rate, ticks, idle=127):
    """weapon_trigger_can_fire_again, then idle_ticks increments only on a miss."""
    fired = []
    for tick in range(ticks):
        if idle + 1.0 >= required_ticks(rate):
            fired.append(tick)
            idle = 0
        elif idle < 127:
            idle += 1
    return fired


class Gun(unittest.TestCase):
    def test_retail_rates_and_source_cadence(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools"), str(ROOT / "tools")]
        from audit_weapons import audit_map
        weapons = {item["path"]: item for item in audit_map(MAP)["weapons"]}
        pistol = weapons[r"weapons\pistol\pistol"]
        rifle = weapons[r"weapons\assault rifle\assault rifle"]
        self.assertEqual(pistol["triggers"][0]["rate_initial"], 3.5)
        self.assertEqual(pistol["magazines"][0]["rounds_loaded_max"], 12)
        self.assertEqual(pistol["magazines"][0]["rounds_initial"], 60)
        self.assertEqual(rifle["triggers"][0]["rate_initial"], 15.0)
        self.assertEqual(rifle["magazines"][0]["rounds_loaded_max"], 60)
        self.assertEqual(rifle["magazines"][0]["rounds_initial"], 240)
        self.assertEqual(shot_ticks(15.0, 30), list(range(0, 30, 2)))
        self.assertEqual(shot_ticks(3.5, 30), [0, 9, 18, 27])
        frames = first_person_frames(MAP)
        self.assertEqual(frames[r"weapons\assault rifle\assault rifle"], (29, 87))
        self.assertEqual(frames[r"weapons\pistol\pistol"], (35, 67))
        self.assertEqual(frames[r"weapons\shotgun\shotgun"], (23, 12))
        self.assertEqual(shotgun_enter_frames(MAP), 15)
        shotgun_tag = weapons[r"weapons\shotgun\shotgun"]
        self.assertEqual(shotgun_tag["triggers"][0]["rate_initial"], 1.0)
        self.assertEqual(shotgun_tag["triggers"][0]["projectiles_per_shot"], 15)
        self.assertEqual(shotgun_tag["magazines"][0]["rounds_reloaded"], 1)
        self.assertEqual(shotgun_tag["magazines"][0]["rounds_loaded_max"], 12)
        self.assertIsNone(object_animation_id(MAP, r"weapons\assault rifle\assault rifle"))
        self.assertEqual(object_weapon_slots(MAP, r"weapons\pistol\pistol", (1, 3)), (-1, -1))
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "gun"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/gun_main.c"), str(ROOT / "src/game/gun.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        reports = out.splitlines()
        ar = [line for line in reports if line.startswith("ar shots")][0].split()
        pistol = [line for line in reports if line.startswith("pistol shots")][0].split()
        self.assertEqual(ar[2], "15")
        self.assertEqual(ar[4], "45")
        self.assertEqual(pistol[2], "4")
        self.assertEqual(pistol[4], "8")
        ar_reload = [line for line in reports if line.startswith("ar reload")][0].split()
        pistol_reload = [line for line in reports if line.startswith("pistol reload")][0].split()
        self.assertEqual(ar_reload[2:], ["87", "loaded", "60", "total", "120"])
        self.assertEqual(pistol_reload[2:], ["67", "loaded", "12", "total", "36"])
        self.assertEqual([line for line in reports if line.startswith("ar refire")][0].split()[2], "89")
        self.assertEqual([line for line in reports if line.startswith("pistol refire")][0].split()[2], "69")
        self.assertEqual([line for line in reports if line.startswith("ar ready")][0].split()[2], "28")
        self.assertEqual([line for line in reports if line.startswith("pistol ready")][0].split()[2], "34")
        self.assertEqual([line for line in reports if line.startswith("switch_gap")][0].split()[1], "34")
        self.assertEqual([line for line in reports if line.startswith("overflow")][0].split()[1], "-1")
        shotgun = [line.split() for line in reports if line.startswith("shotgun shots")][0]
        shells = [line.split() for line in reports if line.startswith("shotgun shells")][0]
        held = [line.split() for line in reports if line.startswith("shotgun held")][0]
        self.assertEqual(shotgun[2:], ["2", "pellets", "30", "loaded", "10"])
        self.assertEqual(shells[2:], ["13", "134", "total", "0"])
        self.assertEqual(held[2:], ["16", "pellets", "15", "loaded", "0"])
        flame = [line.split() for line in reports if line.startswith("flame loaded")][0]
        waste = [line.split() for line in reports if line.startswith("flame waste")][0]
        self.assertEqual(flame[2:], ["100", "total", "500"])
        self.assertEqual(waste[2:], ["102", "total", "400"])
        rocket = [line.split() for line in reports if line.startswith("rocket shots")][0]
        sniper = [line.split() for line in reports if line.startswith("sniper shots")][0]
        self.assertEqual(rocket[2:], ["1", "loaded", "1", "idle", "89"])
        self.assertEqual(sniper[2:], ["1", "loaded", "3", "idle", "89"])
        needle = [line.split() for line in reports if line.startswith("needler shots")][0]
        self.assertEqual(needle[2:], ["62", "134", "loaded", "19", "total", "40"])
        gravity = [line.split() for line in reports if line.startswith("gravity shots")][0]
        self.assertEqual(gravity[2:], ["200", "loaded", "0", "idle", "0"])
        fuel = [line.split() for line in reports if line.startswith("fuel shots")][0]
        self.assertEqual(fuel[2:], ["1", "loaded", "4", "idle", "29"])
        scorpion = [line.split() for line in reports if line.startswith("scorpion second")][0]
        self.assertEqual(scorpion[2:], ["123", "loaded", "0", "total", "9997"])
        self.assertEqual([line for line in reports if line.startswith("error shot")][0],
                         "error shot 1 used 0.00000000 next 0.06666667")
        self.assertEqual([line for line in reports if line.startswith("error recover")][0],
                         "error recover used 0.06666667 next 0.00000000")
        self.assertEqual([line for line in reports if line.startswith("charge release")][0],
                         "charge release tick=40 shots=1 heat=0.16")
        self.assertEqual([line for line in reports if line.startswith("single charge start")][0],
                         "single charge start shots=1")
        self.assertEqual([line for line in reports if line.startswith("heat rifle")][0],
                         "heat rifle shots=25 overheat_events=7 heat=0.81")
        self.assertEqual([line for line in reports if line.startswith("underwater trigger")][0],
                         "underwater trigger blocked state=0 idle=127")


if __name__ == "__main__":
    unittest.main()
