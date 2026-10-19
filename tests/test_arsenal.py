"""Every weap path in the supplied maps, through the shared firing rules."""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / "data/retail/weapon-audit-maps"
REPORT = ROOT / "build/combat-m13/all-map-weapons.json"
SPEC = struct.Struct(
    "<64s 9h 4f 2I 14f 9h")


def trunc30(seconds):
    ticks = struct.unpack("<f", struct.pack("<f", seconds * 30.0))[0]
    if ticks <= 0:
        return 0
    return int(ticks)


def required(initial, final, fraction):
    rate = (final - initial) * fraction + initial
    return 30.0 / rate if rate > 0.0001 else 0.0


def model(spec, ticks=90):
    """Independent reading of the same trigger, charge, latch, and heat rules."""
    name = spec["name"]
    loaded = min(spec["initial"], spec["loaded_max"]) if spec["loaded_max"] > 0 else 0
    total = spec["initial"] - loaded if spec["loaded_max"] > 0 else 0
    idle, state, timer = 127, 0, 0
    mag = mag_timer = 0
    fraction = heat = 0.0
    overheated = 0
    released = 1
    fired_ticks = []
    for tick in range(ticks):
        held = not (spec["mode"] == 1 and tick >= 40)
        fired = False
        if heat > 0 and state != 2:
            heat -= spec["heat_loss"] / 30.0
            heat = max(heat, 0.0)
        if heat >= spec["heat_over"] > 0 and not overheated:
            overheated = 1
        if overheated and heat < spec["heat_recover"]:
            overheated = 0
        if mag_timer:
            mag_timer -= 1
        if mag == 3 and mag_timer - 1 <= 0:
            mag = mag_timer = 0
        elif mag == 4:
            mag = 5
        elif mag == 5 and mag_timer == 0:
            mag = 0
        if timer:
            timer -= 1
        if not held:
            released = 1
        if spec["triggers"] == 0:
            continue
        trig = spec["trig"]
        if state == 0:
            ready = idle + 1.0 >= required(trig["ri"], trig["rf"], fraction)
            if trig["flags"] & 8 and not released:
                ready = False
            need = trig["rps"]
            have = trig["mag"] < 0 or need <= 0 or loaded >= need
            if (need > 0 and trig["mag"] >= 0 and loaded < need and total > 0
                    and spec["reload"] > 0 and mag == 0):
                mag = 3
                mag_timer = spec["enter"] if spec["type"] == 1 and spec["enter"] else spec["reload"]
            elif held and mag == 0 and not overheated and ready and have:
                if trig["charge"] > 0:
                    if fraction > 0 and need > 0 and trig["mag"] >= 0:
                        loaded = max(0, loaded - need)
                    if fraction > 0:
                        heat = min(1.0, heat + trig["heat"])
                        idle = 0
                        released = 0
                        fired = True
                    state = 1
                    timer = trunc30(trig["charge"])
                else:
                    if need > 0 and trig["mag"] >= 0:
                        loaded = max(0, loaded - need)
                    if loaded > 0 and spec["mag_flags"] & 2:
                        mag = 4
                    heat = min(1.0, heat + trig["heat"])
                    idle = 0
                    released = 0
                    fired = True
            elif idle < 127:
                idle += 1
        elif state == 1:
            if timer == 0:
                state = 2
                timer = trunc30(trig["charged"])
            elif not held:
                if spec["triggers"] > 1:
                    heat = min(1.0, heat + trig["heat"])
                    idle = 0
                    fired = True
                state = 0
                fraction = 0.0
        elif state == 2:
            need = trig["rps"]
            have = trig["mag"] < 0 or need <= 0 or loaded >= need
            if held and timer == 0:
                if trig["action"] == 2 and have:
                    heat = min(1.0, heat + trig["heat"])
                    idle = 0
                    released = 0
                    fired = True
                state = 0
            elif not held:
                if have:
                    heat = min(1.0, heat + trig["heat"])
                    idle = 0
                    fired = True
                state = 0
                fraction = 0.0
        if fired:
            fired_ticks.append(tick)
        if held:
            fraction = min(1.0, fraction + trig["accel"])
        else:
            fraction = max(0.0, fraction - trig["decel"])
    return {"name": name, "ticks": fired_ticks, "melee": spec["melee"] if spec["triggers"] == 0 else 0.0}


def load_specs():
    sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools")]
    from halo2ps2 import mapinfo, tagindex
    report = json.loads(REPORT.read_text())
    where = {}
    for stem, item in report["maps"].items():
        for weapon in item["weapons"]:
            where.setdefault(weapon["path"], stem)
    cache = {}

    def region_of(stem):
        if stem not in cache:
            path = MAPS / f"{stem}.map"
            index = tagindex.TagIndex.read(path)
            header = mapinfo.read_header(path)
            with path.open("rb") as handle:
                handle.seek(header.tag_data_offset)
                blob = handle.read(header.tag_data_size)
            cache[stem] = (index, blob, {entry.tag_id: entry for entry in index.entries})
        return cache[stem]

    specs = []
    for path in sorted(where):
        index, region, by_id = region_of(where[path])
        entry = next(item for item in index.entries if item.group == "weap" and item.path == path)
        data = entry.data_address - index.base
        weapon_type = struct.unpack_from("<h", region, data + 0x4E2)[0]
        heat_over, heat_recover = struct.unpack_from("<ff", region, data + 0x308 + 72)
        heat_loss = struct.unpack_from("<f", region, data + 0x308 + 84)[0]
        mag_count, mag_addr = struct.unpack_from("<II", region, data + 0x308 + 488)
        trig_count, trig_addr = struct.unpack_from("<II", region, data + 0x308 + 500)
        loaded_max = initial = reloaded = mag_flags = 0
        if mag_count:
            raw = region[mag_addr - index.base:mag_addr - index.base + 112]
            mag_flags = struct.unpack_from("<I", raw, 0)[0]
            initial, _, loaded_max = struct.unpack_from("<hhh", raw, 6)
            reloaded = struct.unpack_from("<h", raw, 24)[0]
        melee = 0.0
        if trig_count == 0 and "sword" in path:
            melee_id = struct.unpack_from("<I", region, data + 0x308 + 152)[0]
            melee_tag = by_id.get(melee_id)
            if melee_tag and melee_tag.group == "jpt!":
                melee = struct.unpack_from("<f", region, melee_tag.data_address - index.base + 468)[0]
        triggers = []
        for index_trigger in range(min(trig_count, 2)):
            raw = region[trig_addr - index.base + index_trigger * 276:
                         trig_addr - index.base + (index_trigger + 1) * 276]
            flags = struct.unpack_from("<I", raw, 0)[0]
            rate_i, rate_f = struct.unpack_from("<ff", raw, 4)
            charge, charged = struct.unpack_from("<ff", raw, 72)
            action = struct.unpack_from("<h", raw, 80)[0]
            rounds = struct.unpack_from("<h", raw, 34)[0]
            pellets = struct.unpack_from("<h", raw, 110)[0]
            magazine = struct.unpack_from("<h", raw, 32)[0]
            heat = struct.unpack_from("<f", raw, 184)[0]
            accel, decel = struct.unpack_from("<ff", raw, 248)
            triggers.append({"flags": flags, "ri": rate_i, "rf": rate_f, "charge": charge,
                             "charged": charged, "action": action, "rps": rounds,
                             "pellets": pellets, "mag": magazine, "heat": heat,
                             "accel": accel, "decel": decel})
        charge = triggers[0]["charge"] if triggers else 0.0
        charged = triggers[0]["charged"] if triggers else 0.0
        specs.append({
            "name": path, "type": weapon_type, "triggers": trig_count,
            "loaded_max": loaded_max, "initial": initial, "reloaded": reloaded,
            "mag_flags": mag_flags & 0xFFFF, "reload": 0, "enter": 0,
            "heat_over": heat_over, "heat_recover": heat_recover, "heat_loss": heat_loss,
            "melee": melee, "trig": triggers[0] if triggers else None,
            "mode": 1 if charge > 0 and charged > 1.0 else 0,
            "raw_triggers": triggers,
        })
    return specs


def pack_spec(spec):
    name = spec["name"].encode("latin1")[:63]
    trig = spec["raw_triggers"]
    def trig_at(index, key, default=0):
        if index >= len(trig):
            return default
        return trig[index][key]
    floats = []
    for key in ("ri", "rf", "charge", "charged", "heat", "accel", "decel"):
        floats.extend([trig_at(0, key, 0.0), trig_at(1, key, 0.0)])
    shorts = []
    for key in ("rps", "pellets", "mag", "action"):
        shorts.extend([trig_at(0, key, 0), trig_at(1, key, -1 if key == "mag" else 0)])
    shorts.append(spec["mode"])
    return SPEC.pack(
        name, spec["type"], spec["triggers"], spec["loaded_max"], spec["initial"],
        spec["reloaded"], spec["mag_flags"], 0, spec["reload"], spec["enter"],
        spec["heat_over"], spec["heat_recover"], spec["heat_loss"], spec["melee"],
        trig_at(0, "flags", 0), trig_at(1, "flags", 0), *floats, *shorts)


class Arsenal(unittest.TestCase):
    def test_every_weapon_path(self):
        if not REPORT.is_file() or not MAPS.is_dir():
            self.skipTest("weapon audit maps are not in the tree")
        specs = load_specs()
        self.assertEqual(len(specs), 23)
        by_name = {item["name"]: model(item) for item in specs}
        self.assertEqual(by_name[r"weapons\pistol\pistol"]["ticks"], list(range(0, 90, 9)))
        self.assertEqual(by_name[r"weapons\assault rifle\assault rifle"]["ticks"], list(range(0, 90, 2)))
        self.assertEqual(by_name[r"weapons\shotgun\shotgun"]["ticks"], [0, 30, 60])
        self.assertEqual(by_name[r"weapons\rocket launcher\rocket launcher"]["ticks"], [0])
        self.assertEqual(by_name[r"weapons\sniper rifle\sniper rifle"]["ticks"], [0])
        self.assertEqual(by_name[r"weapons\gravity rifle\gravity rifle"]["ticks"], list(range(90)))
        self.assertEqual(by_name[r"weapons\fuel rod gun\fuel rod"]["ticks"], [38])
        self.assertEqual(by_name[r"weapons\plasma pistol\plasma pistol"]["ticks"], [40])
        self.assertEqual(by_name[r"weapons\flag\flag"]["ticks"], [])
        self.assertEqual(by_name[r"weapons\ball\ball"]["ticks"], [])
        self.assertGreater(by_name[r"weapons\energy sword\energy sword"]["melee"], 0.0)
        self.assertLess(by_name[r"weapons\needler\needler"]["ticks"][1], 10)
        self.assertEqual(len(by_name[r"weapons\needler\needler"]["ticks"]), 20)
        self.assertEqual(by_name[r"weapons\energy sword\energy sword"]["melee"], 151.0)
        with tempfile.TemporaryDirectory() as temp:
            blob = Path(temp) / "specs"
            blob.write_bytes(struct.pack("<i", len(specs)) + b"".join(pack_spec(item) for item in specs))
            exe = Path(temp) / "arsenal"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/arsenal_main.c"), str(ROOT / "src/game/arsenal.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe), str(blob)], check=True, capture_output=True, text=True).stdout
        seen = set()
        for line in out.splitlines():
            self.assertTrue(line.startswith("RESULT "))
            head, tick_text = line[len("RESULT "):].rsplit(" ticks", 1)
            name = head.split(" shots ", 1)[0]
            seen.add(name)
            ticks = [int(item) for item in tick_text.split()]
            self.assertEqual(ticks, by_name[name]["ticks"], name)
        self.assertEqual(seen, set(by_name))


if __name__ == "__main__":
    unittest.main()
