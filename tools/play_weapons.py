"""Add every retail weapon mesh to the Blood Gulch play object pack.

The converted scenario has the cyborg arms and no weapon model: multiplayer
profiles are empty, and several weapons are only tags, not placements. This
reads each of the 23 weapon tags, converts the first-person model when the
tag has one and the world model otherwise, and merges that geometry into a
play-only object pack under build/play-objects/. Vehicle guns, the sentinel
gun, and the hunter fuel rod have no model tag; they are listed so the view
can name them, and they draw the arms alone.

The pack is gitignored. It does not replace the hashed reference packs.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import animconv, hp2, modelconv, texconv  # noqa: E402
from halo2ps2.scenconv import (  # noqa: E402
    NO_ANIM, OBJ_MODEL, WEAPON_FP_ANIM, WEAPON_FP_MODEL, Region,
    first_person_idle, graph_nodes, model_nodes,
)

STAMP = "7"
BUDGET = 6815744  # resident_gameplay in config/memory-budget.json
OUT = ROOT / "build/play-objects"
MAPS = ROOT / "data/retail/weapon-audit-maps"
BASE_PACK = ROOT / "data/retail/convert/bloodgulch/run-a/bloodgulch.obj.hp2"
REPORT = ROOT / "build/combat-m13/all-map-weapons.json"
REC = struct.Struct("<64sIIHH32sI")
REMAP = struct.Struct("<III BBH 64s 64s")
# Clip, reserve, and the primary trigger, packed for play_fp.c.
# flags: waste, chamber, partial, latch, magazine, trigger.
AMMO = struct.Struct("<10h5f")
PROJ = struct.Struct("<I7f 33s BBB")
assert REC.size == 112 and REMAP.size == 144 and AMMO.size == 40 and PROJ.size == 68
_ANIM_PROBE = struct.pack(animconv.ANIM_FMT, b"x", 1, 2, 3, 4, 5, 6, 7, 1.5, 11, 12, 13, 14)
assert struct.unpack_from("<I", _ANIM_PROBE, 68)[0] == 11
assert struct.unpack_from("<I", _ANIM_PROBE, 80)[0] == 14

# Meshes first, then weapons whose tags reference no model.
ORDER = (
    r"weapons\pistol\pistol",
    r"weapons\assault rifle\assault rifle",
    r"weapons\shotgun\shotgun",
    r"weapons\sniper rifle\sniper rifle",
    r"weapons\rocket launcher\rocket launcher",
    r"weapons\plasma pistol\plasma pistol",
    r"weapons\plasma rifle\plasma rifle",
    r"weapons\needler\needler",
    r"weapons\flamethrower\flamethrower",
    r"weapons\fuel rod gun\fuel rod",
    r"weapons\gravity rifle\gravity rifle",
    r"weapons\energy sword\energy sword",
    r"weapons\flag\flag",
    r"weapons\ball\ball",
    r"weapons\fuel rod gun\hunter fuel rod",
    r"characters\sentinel\sentinel",
    r"vehicles\warthog\warthog gun",
    r"vehicles\ghost\ghost gun",
    r"vehicles\scorpion\scorpion cannon",
    r"vehicles\banshee\banshee gun",
    r"vehicles\wraith\wraith mortar",
    r"vehicles\c gun turret\c gun turret gun",
    r"vehicles\c_dropship\cd_gun\cd gun turret gun",
)


@dataclass
class Weapon:
    path: str
    source: Path | None = None
    model_tag: int = 0
    anim_tag: int = 0
    idle: int = NO_ANIM
    shared: int = 0
    hand: str = ""
    model_name: str = ""
    arms_model: int = 0
    arms_map: list[int] = field(default_factory=list)
    gun_map: list[int] = field(default_factory=list)


@dataclass
class Batch:
    modl: bytes
    otex: bytes
    anim: bytes | None
    weapons: list[Weapon] = field(default_factory=list)


def _z(text: str, size: int) -> bytes:
    raw = text.encode("latin1", "replace")[: size - 1]
    return raw.ljust(size, b"\0")


def _clip_frames(region: Region, graph: int, slot: int) -> int:
    """Frame count of one first-person weapon animation. 0 when the slot is empty."""
    count, addr = region.u("<II", graph + 0x48)
    if count <= 0 or slot < 0:
        return 0
    slots, slot_addr = region.u("<II", addr - region.base + 16)
    if slot >= slots:
        return 0
    anim = region.u("<h", slot_addr - region.base + slot * 2)[0]
    if anim < 0:
        return 0
    anim_count, anim_addr = region.u("<II", graph + 0x74)
    if anim >= anim_count:
        return 0
    return region.u("<h", anim_addr - region.base + anim * 180 + 34)[0]


def magazines(paths: list[str]) -> list[dict]:
    """Retail magazine and primary trigger for each weapon path.

    Starting rounds follow weapon_new: the clip is min(initial, loaded max)
    and the reserve is the rest of the initial total. Reload time is the
    first-person reload-empty frame count, which is 0 when that graph is
    absent. The tag's reload seconds are not the timer.
    """
    maps = sorted(MAPS.glob("*.map"), key=lambda path: (path.stem != "bloodgulch", path.stem))
    if not maps:
        raise RuntimeError("decompressed weapon maps are missing")
    found: dict[str, dict] = {}
    for map_path in maps:
        wanted = [path for path in paths if path not in found]
        if not wanted:
            break
        data = texconv.MapData.open(map_path)
        region = Region(data)
        by_path = {entry.path: entry for entry in data.index.entries if entry.group == "weap"}
        for path in wanted:
            entry = by_path.get(path)
            if entry is None:
                continue
            block = region.block(entry)
            mag_count, mag_at = region.reflexive(block + 0x308 + 488, 112, 8)
            trig_count, trig_at = region.reflexive(block + 0x308 + 500, 276, 8)
            weapon_type = region.u("<h", block + 0x4E2)[0]
            loaded_max = initial = reloaded = recharge = mag_flags = 0
            chamber = 0.0
            if mag_count:
                mag_flags = region.u("<I", mag_at)[0]
                recharge = region.u("<h", mag_at + 4)[0]
                initial, _total_max, loaded_max = region.u("<hhh", mag_at + 6)
                reloaded = region.u("<h", mag_at + 24)[0]
                chamber = region.u("<f", mag_at + 28)[0]
            rate = rate_final = accel = decel = 0.0
            rps = pellets = trig_flags = 0
            magazine_index = -1
            if trig_count:
                trig_flags = region.u("<I", trig_at)[0]
                rate, rate_final = region.u("<ff", trig_at + 4)
                magazine_index, rps, _minimum = region.u("<hhh", trig_at + 32)
                pellets = region.u("<h", trig_at + 110)[0]
                accel, decel = region.u("<ff", trig_at + 248)
            ready = reload = enter = 0
            anim_group, anim_id = region.tagref(block + WEAPON_FP_ANIM)
            if anim_group == "antr" and region.entry(anim_id):
                graph = region.block(region.entry(anim_id))
                reload = _clip_frames(region, graph, 7)
                ready = _clip_frames(region, graph, 10)
                if weapon_type == 1:
                    enter = _clip_frames(region, graph, 23)
            uses_magazine = mag_count > 0 and loaded_max > 0 and magazine_index >= 0
            flags = 0
            if mag_flags & 1:
                flags |= 1
            if mag_flags & 2:
                flags |= 2
            if trig_flags & 4:
                flags |= 4
            if trig_flags & 8:
                flags |= 8
            if uses_magazine:
                flags |= 16
            if trig_count:
                flags |= 32
            found[path] = {
                "loaded_max": loaded_max, "initial": initial, "reloaded": reloaded,
                "rounds_per_shot": rps, "reload_frames": reload, "ready_frames": ready,
                "enter_frames": enter, "flags": flags, "pellets": pellets,
                "recharge": recharge, "rate": rate, "rate_final": rate_final,
                "accel": accel, "decel": decel, "chamber": chamber,
            }
    missing = [path for path in paths if path not in found]
    if missing:
        raise RuntimeError("weapons not in any map: " + ", ".join(missing))
    return [found[path] for path in paths]


def _paths_in(blob: bytes) -> list[str]:
    magic, count, size = struct.unpack_from("<4sHH", blob)
    if magic != b"WFP1" or size != REC.size or count <= 0 or count > 32:
        raise RuntimeError("weapons.fp has no weapon table")
    paths = []
    for index in range(count):
        raw = blob[8 + index * size:8 + index * size + 64]
        paths.append(raw.split(b"\0", 1)[0].decode("latin1"))
    return paths


def projectiles(paths: list[str]) -> list[dict]:
    """Primary projectile for each weapon: velocity, range, gravity, impact, responses.

    Distribution on every retail trigger is the point function, so a shot
    leaves along the aim. Shotgun pellets share that aim; their cone is the
    random direction table, which this record does not include.
    """
    maps = sorted(MAPS.glob("*.map"), key=lambda path: (path.stem != "bloodgulch", path.stem))
    if not maps:
        raise RuntimeError("decompressed weapon maps are missing")
    found: dict[str, dict] = {}
    for map_path in maps:
        wanted = [path for path in paths if path not in found]
        if not wanted:
            break
        data = texconv.MapData.open(map_path)
        region = Region(data)
        by_path = {entry.path: entry for entry in data.index.entries if entry.group == "weap"}
        for path in wanted:
            entry = by_path.get(path)
            if entry is None:
                continue
            block = region.block(entry)
            trig_count, trig_at = region.reflexive(block + 0x308 + 500, 276, 8)
            empty = {
                "velocity": 0, "final_velocity": 0.0, "deceleration_start": 0.0,
                "deceleration_end": 0.0, "range": 0.0, "gravity": 0.0,
                "damage_lower": 0.0, "damage_upper": 0.0,
                "response": bytes(33), "has": 0, "pellets": 0,
            }
            if trig_count <= 0:
                found[path] = empty
                continue
            proj_id = region.u("<I", trig_at + 160)[0]
            pellets = region.u("<h", trig_at + 110)[0]
            proj = region.entry(proj_id)
            if proj is None or proj.group != "proj":
                empty["pellets"] = max(pellets, 0)
                found[path] = empty
                continue
            base = region.block(proj) + 0x17C
            velocity = region.u("<I", base + 104)[0]
            maximum_range, gravity = region.u("<ff", base + 76)
            final_velocity = region.u("<f", base + 108)[0]
            deceleration_start, deceleration_end = region.u("<ff", base + 84)
            count, addr = region.u("<II", base + 196)
            response = bytearray(33)
            if count and addr:
                origin = addr - region.base
                for index in range(min(count, 33)):
                    value = region.u("<h", origin + index * 160 + 2)[0]
                    if 0 <= value <= 255:
                        response[index] = value
            damage_id = region.u("<I", base + 180)[0]
            lower = upper = 0.0
            damage = region.entry(damage_id)
            if damage is not None:
                lower, upper = region.u("<ff", region.block(damage) + 468)
            found[path] = {
                "velocity": velocity, "final_velocity": final_velocity,
                "deceleration_start": deceleration_start,
                "deceleration_end": deceleration_end,
                "range": maximum_range, "gravity": gravity,
                "damage_lower": lower, "damage_upper": upper,
                "response": bytes(response), "has": 1, "pellets": max(pellets, 0),
            }
    missing = [path for path in paths if path not in found]
    if missing:
        raise RuntimeError("weapons not in any map: " + ", ".join(missing))
    return [found[path] for path in paths]


def attach_ammo(blob: bytes) -> bytes:
    """Replace the magazine and projectile tails, in weapon-table order."""
    cuts = [index for index in (blob.find(b"AMO1"), blob.find(b"PRJ1")) if index >= 0]
    if cuts:
        blob = blob[:min(cuts)]
    paths = _paths_in(blob)
    rows = magazines(paths)
    shots = projectiles(paths)
    out = bytearray(blob)
    out += struct.pack("<4sH", b"AMO1", len(rows))
    for row in rows:
        out += AMMO.pack(
            row["loaded_max"], row["initial"], row["reloaded"], row["rounds_per_shot"],
            row["reload_frames"], row["ready_frames"], row["enter_frames"], row["flags"],
            row["pellets"], row["recharge"], row["rate"], row["rate_final"],
            row["accel"], row["decel"], row["chamber"])
    out += struct.pack("<4sH", b"PRJ1", len(shots))
    for shot in shots:
        out += PROJ.pack(
            shot["velocity"], shot["final_velocity"], shot["deceleration_start"],
            shot["deceleration_end"], shot["range"], shot["gravity"],
            shot["damage_lower"], shot["damage_upper"], shot["response"],
            shot["has"], shot["pellets"], 0)
    return bytes(out)


def _weapon_paths() -> list[str]:
    found = []
    if REPORT.is_file():
        report = json.loads(REPORT.read_text())
        seen = set()
        for info in report["maps"].values():
            for weapon in info["weapons"]:
                if weapon["path"] not in seen:
                    seen.add(weapon["path"])
                    found.append(weapon["path"])
    ordered = [path for path in ORDER if path in found or not found]
    for path in found:
        if path not in ordered:
            ordered.append(path)
    if len(ordered) < 23:
        raise RuntimeError(f"expected 23 weapons, found {len(ordered)}")
    return ordered


def collect(paths: list[str]) -> list[Weapon]:
    maps = sorted(MAPS.glob("*.map"), key=lambda path: (path.stem != "bloodgulch", path.stem))
    if not maps:
        raise RuntimeError("decompressed weapon maps are missing")
    found: dict[str, Weapon] = {}
    arms_nodes: list[str] = []
    arms_tag = 0
    for map_path in maps:
        wanted = [path for path in paths if path not in found]
        if not wanted:
            break
        data = texconv.MapData.open(map_path)
        region = Region(data)
        by_path = {entry.path: entry for entry in data.index.entries if entry.group == "weap"}
        if not arms_nodes:
            arms = next((entry for entry in data.index.entries
                         if entry.group == "mode" and entry.path == r"characters\cyborg\fp\fp"), None)
            if arms is not None:
                arms_nodes = model_nodes(region, region.block(arms))
                arms_tag = arms.tag_id
        for path in wanted:
            entry = by_path.get(path)
            if entry is None:
                continue
            weapon = Weapon(path, map_path)
            block = region.block(entry)
            world_group, world_id = region.tagref(block + OBJ_MODEL)
            fp_group, fp_id = region.tagref(block + WEAPON_FP_MODEL)
            anim_group, anim_id = region.tagref(block + WEAPON_FP_ANIM)
            model_entry = None
            if fp_group == "mode" and region.entry(fp_id):
                weapon.model_tag = fp_id
                model_entry = region.entry(fp_id)
            elif world_group == "mode" and region.entry(world_id):
                weapon.model_tag = world_id
                model_entry = region.entry(world_id)
            if model_entry is not None:
                weapon.model_name = model_entry.path
            if (model_entry is not None and fp_group == "mode" and anim_group == "antr"
                    and region.entry(anim_id)):
                weapon.anim_tag = anim_id
                graph = region.block(region.entry(anim_id))
                weapon.idle = first_person_idle(region, graph)
                gun_nodes = model_nodes(region, region.block(model_entry))
                graph_list = graph_nodes(region, graph)
                names = [name for name, _parent in graph_list]
                if (arms_nodes and gun_nodes and len(graph_list) == len(arms_nodes) + len(gun_nodes)
                        and set(arms_nodes) | set(gun_nodes) <= set(names)):
                    weapon.shared = 1
                    weapon.arms_model = arms_tag
                    weapon.arms_map = [names.index(name) for name in arms_nodes]
                    weapon.gun_map = [names.index(name) for name in gun_nodes]
                    parent = graph_list[names.index(gun_nodes[0])][1]
                    if 0 <= parent < len(graph_list) and graph_list[parent][0] in arms_nodes:
                        weapon.hand = graph_list[parent][0]
            found[path] = weapon
    missing = [path for path in paths if path not in found]
    if missing:
        raise RuntimeError("weapons not in any map: " + ", ".join(missing))
    return [found[path] for path in paths]


def _modl_tables(data: bytes) -> tuple[dict[str, bytearray], dict[str, int]]:
    tables, counts = {}, {}
    for index, name in enumerate(modelconv.TABLES):
        offset, count = struct.unpack_from("<II", data, modelconv.DIR_AT + 8 * index)
        size = count * modelconv.REC_SIZES[name]
        tables[name] = bytearray(data[offset:offset + size])
        counts[name] = count
    return tables, counts


def _build_modl(tables: dict[str, bytearray], counts: dict[str, int]) -> bytes:
    triangles = 0
    part = modelconv.REC_SIZES["parts"]
    for index in range(counts["parts"]):
        triangles += struct.unpack_from("<H", tables["parts"], index * part + 8)[0]
    out = bytearray(modelconv.HEADER_SIZE)
    directory = {}
    for name in modelconv.TABLES:
        directory[name] = (len(out), counts[name])
        blob = bytes(tables[name])
        out += blob + bytes(-len(blob) % 16)
    struct.pack_into("<4sHHII", out, 0, modelconv.MAGIC, modelconv.VERSION, 0, len(out), triangles)
    for index, name in enumerate(modelconv.TABLES):
        struct.pack_into("<II", out, modelconv.DIR_AT + 8 * index, *directory[name])
    modelconv.parse_section(bytes(out))
    return bytes(out)


def _add_u16(value: int, delta: int, what: str) -> int:
    total = value + delta
    if total > 0xFFFF:
        raise RuntimeError(f"{what} exceeds 65535")
    return total


def merge_models(base: bytes, extra: bytes, tag_start: int) -> tuple[bytes, dict[int, int], int]:
    """Append extra's models after base. New tag ids start at tag_start and stay sorted."""
    left, left_n = _modl_tables(base)
    right, right_n = _modl_tables(extra)
    mapping: dict[int, int] = {}
    model_rec = modelconv.REC_SIZES["models"]
    next_id = tag_start
    for index in range(right_n["models"]):
        old = struct.unpack_from("<I", right["models"], index * model_rec)[0]
        mapping[old] = next_id
        struct.pack_into("<I", right["models"], index * model_rec, next_id)
        for field, delta in ((12, left_n["nodes"]), (16, left_n["markers"]),
                             (20, left_n["perms"]), (64, left_n["parts"])):
            value = struct.unpack_from("<I", right["models"], index * model_rec + field)[0]
            struct.pack_into("<I", right["models"], index * model_rec + field, value + delta)
        next_id += 1
    perm_rec = modelconv.REC_SIZES["perms"]
    for index in range(right_n["perms"]):
        for lod in range(modelconv.MODEL_LODS):
            at = index * perm_rec + 36 + 4 * lod
            first = struct.unpack_from("<H", right["perms"], at)[0]
            struct.pack_into("<H", right["perms"], at, _add_u16(first, left_n["parts"], "permutation"))
    part_rec = modelconv.REC_SIZES["parts"]
    for index in range(right_n["parts"]):
        at = index * part_rec + 4
        first = struct.unpack_from("<H", right["parts"], at)[0]
        struct.pack_into("<H", right["parts"], at, _add_u16(first, left_n["batches"], "part batch"))
    batch_rec = modelconv.REC_SIZES["batches"]
    for index in range(right_n["batches"]):
        at = index * batch_rec
        part = struct.unpack_from("<H", right["batches"], at)[0]
        vif = struct.unpack_from("<I", right["batches"], at + 8)[0]
        struct.pack_into("<H", right["batches"], at, _add_u16(part, left_n["parts"], "batch part"))
        struct.pack_into("<I", right["batches"], at + 8, vif + left_n["vif"])
    merged, counts = {}, {}
    for name in modelconv.TABLES:
        merged[name] = left[name] + right[name]
        counts[name] = left_n[name] + right_n[name]
    return _build_modl(merged, counts), mapping, next_id


def _shader_ids(data: bytes) -> list[int]:
    _magic, _ver, _res, _nt, nb, _to, bind_off, _do, _total, _un = struct.unpack_from(
        texconv.TEXS_HEADER, data)
    return [struct.unpack_from("<I", data, bind_off + index * texconv.BINDING_REC)[0]
            for index in range(nb)]


def _rewrite_shaders(modl: bytes, mapping: dict[int, int]) -> bytes:
    if not mapping:
        return modl
    tables, counts = _modl_tables(modl)
    part_rec = modelconv.REC_SIZES["parts"]
    for index in range(counts["parts"]):
        at = index * part_rec
        shader = struct.unpack_from("<I", tables["parts"], at)[0]
        if shader in mapping:
            struct.pack_into("<I", tables["parts"], at, mapping[shader])
        elif shader != 0xFFFFFFFF:
            raise RuntimeError(f"part shader {shader:#x} has no texture binding")
    return _build_modl(tables, counts)


def merge_textures(base: bytes, extra: bytes, shader_start: int) -> tuple[bytes, dict[int, int], int]:
    def view(data: bytes):
        header = struct.unpack_from(texconv.TEXS_HEADER, data)
        _magic, _ver, _res, nt, nb, tex_off, bind_off, data_off, total, _un = header
        return nt, nb, tex_off, bind_off, data_off, data[data_off:total]

    left_n, left_b, left_tex_at, left_bind_at, left_data_at, left_pixels = view(base)
    right_n, right_b, right_tex_at, right_bind_at, right_data_at, right_pixels = view(extra)
    mapping: dict[int, int] = {}
    next_id = shader_start
    binds = bytearray()
    for index in range(right_b):
        rec = bytearray(extra[right_bind_at + index * texconv.BINDING_REC:
                              right_bind_at + (index + 1) * texconv.BINDING_REC])
        shader, texture = struct.unpack_from("<IH", rec)
        mapping[shader] = next_id
        if texture != texconv.NO_TEXTURE:
            texture = _add_u16(texture, left_n, "texture index")
        struct.pack_into("<IH", rec, 0, next_id, texture)
        binds += rec
        next_id += 1
    left_textures = bytearray(base[left_tex_at:left_tex_at + left_n * texconv.TEXTURE_REC])
    right_textures = bytearray(extra[right_tex_at:right_tex_at + right_n * texconv.TEXTURE_REC])
    old_binds = base[left_bind_at:left_bind_at + left_b * texconv.BINDING_REC]
    tex_off = texconv.HEADER_SIZE
    bind_off = tex_off + len(left_textures) + len(right_textures)
    data_off = bind_off + len(old_binds) + len(binds)
    pixels = left_pixels + right_pixels

    def shift(records: bytearray, count: int, source_data: int, pixel_at: int) -> None:
        for index in range(count):
            at = index * texconv.TEXTURE_REC
            clut, pixel = struct.unpack_from("<II", records, at + 12)
            struct.pack_into("<II", records, at + 12,
                             data_off + pixel_at + (clut - source_data),
                             data_off + pixel_at + (pixel - source_data))

    shift(left_textures, left_n, left_data_at, 0)
    shift(right_textures, right_n, right_data_at, len(left_pixels))
    textures = left_textures + right_textures
    untextured = 0
    for blob in (old_binds, binds):
        for index in range(len(blob) // texconv.BINDING_REC):
            _shader, texture = struct.unpack_from("<IH", blob, index * texconv.BINDING_REC)
            if texture == texconv.NO_TEXTURE:
                untextured += 1
    total = data_off + len(pixels)
    head = struct.pack(texconv.TEXS_HEADER, texconv.TEXS_MAGIC, texconv.VERSION, 0,
                       left_n + right_n, left_b + right_b, tex_off, bind_off, data_off, total, untextured)
    blob = head + bytes(textures) + old_binds + bytes(binds) + pixels
    texconv.parse_texs(blob)
    return blob, mapping, next_id


def _pool_of(data: bytes) -> tuple[int, int, int, int, bytes]:
    _magic, _version, _flags, graphs, anims, graph_at, anim_at, pool_at, total = struct.unpack_from(
        "<4sHHIIIIII", data)
    return graphs, anims, graph_at, anim_at, data[pool_at:total]


def merge_anims(base: bytes, extra: bytes | None, tag_start: int) -> tuple[bytes, dict[int, int], int]:
    if not extra:
        return base, {}, tag_start
    left_g, left_a, left_graph_at, left_anim_at, left_pool = _pool_of(base)
    right_g, right_a, right_graph_at, right_anim_at, right_pool = _pool_of(extra)
    if right_g == 0:
        return base, {}, tag_start
    mapping: dict[int, int] = {}
    next_id = tag_start
    graphs = bytearray(base[left_graph_at:left_graph_at + left_g * animconv.GRAPH_REC])
    anims = bytearray(base[left_anim_at:left_anim_at + left_a * animconv.ANIM_REC])
    for index in range(right_g):
        rec = bytearray(extra[right_graph_at + index * animconv.GRAPH_REC:
                              right_graph_at + (index + 1) * animconv.GRAPH_REC])
        tag, nodes, count, first, default, model = struct.unpack_from("<IHHIII", rec)
        mapping[tag] = next_id
        first += left_a
        if default:
            default += len(left_pool)
        struct.pack_into("<IHHIII", rec, 0, next_id, nodes, count, first, default, model)
        graphs += rec
        next_id += 1
    for index in range(right_a):
        rec = bytearray(extra[right_anim_at + index * animconv.ANIM_REC:
                              right_anim_at + (index + 1) * animconv.ANIM_REC])
        for at in (68, 76, 80):
            value = struct.unpack_from("<I", rec, at)[0]
            if value:
                struct.pack_into("<I", rec, at, value + len(left_pool))
        anims += rec
    graph_at = animconv.HEADER_SIZE
    anim_at = graph_at + len(graphs)
    pool_at = (anim_at + len(anims) + 15) & ~15
    pool = left_pool + right_pool
    body = bytes(graphs) + bytes(anims) + bytes(pool_at - graph_at - len(graphs) - len(anims)) + pool
    total = animconv.HEADER_SIZE + len(body)
    total_padded = (total + 15) & ~15
    body += bytes(total_padded - total)
    head = struct.pack("<4sHHIIIIII32x", animconv.MAGIC, animconv.VERSION, 0,
                       left_g + right_g, left_a + right_a, graph_at, anim_at, pool_at, total_padded)
    blob = head + body
    _validate_anim(blob)
    return blob, mapping, next_id


def _validate_anim(data: bytes) -> None:
    animconv.parse_section(data)
    graphs, anims, graph_at, anim_at, pool = _pool_of(data)
    if len(pool) < 16:
        raise RuntimeError("animation pool is shorter than its reserved prefix")
    covered = 0
    previous = 0
    for index in range(graphs):
        tag, nodes, count, first, default, _model = struct.unpack_from(
            "<IHHIII", data, graph_at + index * animconv.GRAPH_REC)
        if index and tag <= previous:
            raise RuntimeError("animation graphs are not sorted")
        previous = tag
        if first != covered or nodes < 1 or default < 16 or default + nodes * 32 > len(pool):
            raise RuntimeError(f"animation graph {index} is outside the pool")
        for anim in range(count):
            rec = data[anim_at + (first + anim) * animconv.ANIM_REC:
                       anim_at + (first + anim + 1) * animconv.ANIM_REC]
            data_off, data_bytes, root_off, rest = struct.unpack_from("<IIII", rec, 68)
            root_type = struct.unpack_from("<H", rec, 58)[0]
            frames = struct.unpack_from("<H", rec, 50)[0]
            if rest != default or data_off < 16 or data_off % 16 or data_off + data_bytes > len(pool):
                raise RuntimeError(f"animation {first + anim} data is outside the pool")
            if root_type == 0:
                if root_off:
                    raise RuntimeError(f"animation {first + anim} has an unexpected root")
            else:
                root_bytes = _root_bytes(root_type, frames)
                if root_off < 16 or root_off % 16 or root_off + root_bytes > len(pool):
                    raise RuntimeError(f"animation {first + anim} root is outside the pool")
        covered += count
    if covered != anims:
        raise RuntimeError("animation records are not exactly covered by the graphs")


def _root_bytes(root_type: int, frames: int) -> int:
    return 16 + ((2 * (root_type + 1) * frames + 3) & ~3)


def keep_idle(data: bytes, idle_of: dict[int, int]) -> bytes:
    """One animation per graph: the first-person idle. Drops graphs with no idle."""
    graphs, _anims, graph_at, anim_at, pool = _pool_of(data)
    new_pool = bytearray(16)
    graph_recs = []
    anim_recs = []

    def add(blob: bytes) -> int:
        while len(new_pool) % 16:
            new_pool.append(0)
        offset = len(new_pool)
        new_pool += blob
        return offset

    for index in range(graphs):
        tag, nodes, count, first, default, model = struct.unpack_from(
            "<IHHIII", data, graph_at + index * animconv.GRAPH_REC)
        idle = idle_of.get(tag, NO_ANIM)
        if idle == NO_ANIM or idle >= count:
            continue
        rest = pool[default:default + nodes * 32]
        default_off = add(rest)
        rec = bytearray(data[anim_at + (first + idle) * animconv.ANIM_REC:
                             anim_at + (first + idle + 1) * animconv.ANIM_REC])
        data_off, data_bytes, root_off, rest_off = struct.unpack_from("<IIII", rec, 68)
        frames, root_type = struct.unpack_from("<HH", rec, 50)[0], struct.unpack_from("<H", rec, 58)[0]
        struct.pack_into("<I", rec, 68, add(pool[data_off:data_off + data_bytes]))
        if root_off:
            struct.pack_into("<I", rec, 76, add(pool[root_off:root_off + _root_bytes(root_type, frames)]))
        else:
            struct.pack_into("<I", rec, 76, 0)
        struct.pack_into("<I", rec, 80, default_off)
        graph_recs.append(struct.pack("<IHHIII12x", tag, nodes, 1, len(anim_recs), default_off, model))
        anim_recs.append(bytes(rec))
    if not graph_recs:
        return b""
    graph_at = animconv.HEADER_SIZE
    graphs_blob = b"".join(graph_recs)
    anims_blob = b"".join(anim_recs)
    anim_at = graph_at + len(graphs_blob)
    pool_at = (anim_at + len(anims_blob) + 15) & ~15
    body = graphs_blob + anims_blob + bytes(pool_at - graph_at - len(graphs_blob) - len(anims_blob))
    body += bytes(new_pool)
    total = (animconv.HEADER_SIZE + len(body) + 15) & ~15
    body += bytes(total - animconv.HEADER_SIZE - len(body))
    head = struct.pack("<4sHHIIIIII32x", animconv.MAGIC, animconv.VERSION, 0,
                       len(graph_recs), len(anim_recs), graph_at, anim_at, pool_at, total)
    blob = head + body
    _validate_anim(blob)
    return blob


def _last_model_tag(data: bytes) -> int:
    _tables, counts = _modl_tables(data)
    if counts["models"] == 0:
        return 0
    offset = struct.unpack_from("<II", data, modelconv.DIR_AT)[0]
    return struct.unpack_from("<I", data, offset + (counts["models"] - 1) * modelconv.MODEL_REC)[0]


def _last_shader(data: bytes) -> int:
    ids = _shader_ids(data)
    return ids[-1] if ids else 0


def _last_anim(data: bytes) -> int:
    graphs, _anims, graph_at, _anim_at, _pool = _pool_of(data)
    if graphs == 0:
        return 0
    return struct.unpack_from("<I", data, graph_at + (graphs - 1) * animconv.GRAPH_REC)[0]


def absorb(base_modl: bytes, base_tex: bytes, base_anim: bytes, batch: Batch,
           ids: dict[str, int]) -> tuple[bytes, bytes, bytes]:
    shader_map: dict[int, int] = {}
    next_shader = ids["shader"]
    if _shader_ids(batch.otex):
        base_tex, shader_map, next_shader = merge_textures(base_tex, batch.otex, ids["shader"])
    patched = _rewrite_shaders(batch.modl, shader_map)
    base_modl, model_map, next_model = merge_models(base_modl, patched, ids["model"])
    base_anim, anim_map, next_anim = merge_anims(base_anim, batch.anim, ids["anim"])
    ids["shader"], ids["model"], ids["anim"] = next_shader, next_model, next_anim
    for weapon in batch.weapons:
        weapon.model_tag = model_map.get(weapon.model_tag, 0)
        weapon.anim_tag = anim_map.get(weapon.anim_tag, 0)
    return base_modl, base_tex, base_anim


def attach_meters(map_path: Path, data: bytes) -> bytes:
    """Give plasma gauge quads their meter bitmap.

    ``smet`` shaders are left untextured by the object converter, so the
    gauge is a flat grey square. The bitmap reference is at +0x4C. The fill
    still does not track the ammo count.
    """
    opened = texconv.MapData.open(map_path)
    _magic, _ver, _res, tex_count, bind_count, tex_at, bind_at, _data_at, _total, _un = struct.unpack_from(
        texconv.TEXS_HEADER, data)
    jobs = []
    for index in range(bind_count):
        shader, texture = struct.unpack_from("<IH", data, bind_at + index * texconv.BINDING_REC)
        if texture != texconv.NO_TEXTURE:
            continue
        entry = opened.by_id.get(shader)
        if entry is None or entry.group != "smet":
            continue
        block = opened.tag_off(entry)
        bitmap = texconv._bitmap_ref(opened, block, 0x4C)
        if bitmap is None:
            continue
        images = opened.images(bitmap)
        if not images or not images[0].decodable:
            continue
        jobs.append((index, obj_meter(opened, images[0], bitmap, meter_color(entry.path))))
        print(f"meter {entry.path}", flush=True)
    if not jobs:
        return data
    return _replace_bindings(data, jobs)


def meter_color(path: str) -> tuple[int, int, int]:
    if "plasma rifle" in path:
        return (255, 120, 32)
    if "plasma" in path:
        return (120, 190, 255)
    return (255, 176, 48)


def obj_meter(opened, image, bitmap: int, color: tuple[int, int, int]):
    """The retail meter map is a grey mask. The shader paints it; we bake one colour."""
    from halo2ps2 import bitmaps
    w, h, rgba = bitmaps.decode_level(image, opened.pixels(image), 0)
    tinted = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        lum = max(rgba[i], rgba[i + 1], rgba[i + 2])
        tinted[i] = color[0] * lum // 255
        tinted[i + 1] = color[1] * lum // 255
        tinted[i + 2] = color[2] * lum // 255
        tinted[i + 3] = lum
    tw, th = w, h
    while tw > 128 or th > 128:
        tw, th = max(8, tw // 2), max(8, th // 2)
    pixels = bytes(tinted)
    if (tw, th) != (w, h):
        pixels = texconv.resample_rgba(pixels, w, h, tw, th, True)
    return texconv.convert_rgba(bitmap, pixels, tw, th, texconv.CLASS_BLEND)


def _replace_bindings(data: bytes, jobs: list[tuple[int, object]]) -> bytes:
    """Append textures and point the given bindings at them. ``jobs`` is (binding index, Ps2Texture)."""
    _magic, _ver, _res, tex_count, bind_count, tex_at, bind_at, _data_at, _total, _un = struct.unpack_from(
        texconv.TEXS_HEADER, data)
    pixels = bytearray()
    records = bytearray()
    new_tex = tex_count + len(jobs)
    new_data = texconv.HEADER_SIZE + new_tex * texconv.TEXTURE_REC + bind_count * texconv.BINDING_REC

    def take(blob: bytes) -> int:
        at = new_data + len(pixels)
        pixels.extend(blob)
        return at

    for index in range(tex_count):
        at = tex_at + index * texconv.TEXTURE_REC
        source, width, height, psm, mips, flags, clut, pixel, pixel_bytes, entries, _pad, average = struct.unpack_from(
            texconv.TEXTURE_FMT, data, at)
        clut_at = take(data[clut:clut + entries * 4])
        pixel_at = take(data[pixel:pixel + pixel_bytes])
        records += struct.pack(texconv.TEXTURE_FMT, source, width, height, psm, mips, flags,
                               clut_at, pixel_at, pixel_bytes, entries, 0, average)
    new_index = {}
    baked = {}
    for bind_index, texture in jobs:
        clut_at = take(texture.clut)
        pixel_at = take(b"".join(texture.mips))
        new_index[bind_index] = tex_count + len(new_index)
        baked[bind_index] = texture
        records += struct.pack(texconv.TEXTURE_FMT, texture.source_id, texture.width, texture.height, texture.psm,
                               len(texture.mips), texture.flags, clut_at, pixel_at, texture.pixel_bytes,
                               texture.clut_entries, 0, texture.avg_rgba)
    binds = bytearray()
    untextured = 0
    for index in range(bind_count):
        rec = bytearray(data[bind_at + index * texconv.BINDING_REC:
                             bind_at + (index + 1) * texconv.BINDING_REC])
        if index in new_index:
            flags = struct.unpack_from("<H", rec, 6)[0] & ~8
            struct.pack_into("<H", rec, 4, new_index[index])
            struct.pack_into("<H", rec, 6, flags)
            struct.pack_into("<B", rec, 8, 2)
            struct.pack_into("<ff", rec, 12, 1.0, 1.0)
            struct.pack_into("<I", rec, 20, baked[index].avg_rgba)
        if struct.unpack_from("<H", rec, 4)[0] == texconv.NO_TEXTURE:
            untextured += 1
        binds += rec
    tex_off = texconv.HEADER_SIZE
    bind_off = tex_off + len(records)
    data_off = bind_off + len(binds)
    if data_off != new_data:
        raise RuntimeError("texture table does not meet the pixel data")
    head = struct.pack(texconv.TEXS_HEADER, texconv.TEXS_MAGIC, texconv.VERSION, 0,
                       new_tex, bind_count, tex_off, bind_off, data_off, data_off + len(pixels), untextured)
    blob = head + bytes(records) + bytes(binds) + bytes(pixels)
    texconv.parse_texs(blob)
    return blob


def convert_groups(weapons: list[Weapon]) -> list[Batch]:
    groups: dict[Path, list[Weapon]] = {}
    for weapon in weapons:
        if weapon.model_tag and weapon.source is not None:
            groups.setdefault(weapon.source, []).append(weapon)
    batches = []
    for source in sorted(groups, key=lambda path: (path.stem != "bloodgulch", str(path))):
        group = groups[source]
        print(f"convert {source.stem}: {len(group)} models", flush=True)
        converted = modelconv.convert_map(source, [weapon.model_tag for weapon in group],
                                          tex_budget=1024 * 1024)
        if converted.skipped:
            raise RuntimeError("model tags missing from " + source.name)
        anim_ids = sorted({weapon.anim_tag for weapon in group if weapon.anim_tag})
        anim = animconv.build_section(source, anim_ids) if anim_ids else None
        batches.append(Batch(converted.modl, attach_meters(source, converted.otex), anim, group))
        print(f"  MODL {len(converted.modl)}  OTEX {len(converted.otex)}  "
              f"ANIM {0 if anim is None else len(anim)}  parts {converted.parts}", flush=True)
    return batches


def _assign(base_modl: bytes, base_tex: bytes, base_anim: bytes,
            batches: list[Batch]) -> tuple[bytes, bytes, bytes]:
    ids = {"model": _last_model_tag(base_modl) + 1,
           "shader": _last_shader(base_tex) + 1,
           "anim": _last_anim(base_anim) + 1}
    for batch in batches:
        base_modl, base_tex, base_anim = absorb(base_modl, base_tex, base_anim, batch, ids)
    return base_modl, base_tex, base_anim


def rebake_sky(data: bytes, map_path: Path) -> bytes:
    """Replace a Chicago sky that fell back to its star-noise layer.

    The clear-afternoon dome kept the 32x32 twinkle map, tiled twelve times,
    instead of the baked blue sky. The bake samples every stage into one image
    and the mesh then uses that image once.
    """
    from halo2ps2.objtex import bake_static_chicago
    opened = texconv.MapData.open(map_path)
    header = struct.unpack_from(texconv.TEXS_HEADER, data)
    _magic, _ver, _res, tex_count, bind_count, tex_at, bind_at, data_at, total, _un = header
    jobs = []
    for index in range(bind_count):
        shader, texture, _flags, _blend, _group, _pad, su, sv, _flat = struct.unpack_from(
            texconv.BINDING_FMT, data, bind_at + index * texconv.BINDING_REC)
        entry = opened.by_id.get(shader)
        if entry is None or entry.group != "schi" or not str(entry.path).startswith("sky\\"):
            continue
        if texture == texconv.NO_TEXTURE:
            continue
        width = struct.unpack_from("<H", data, tex_at + texture * texconv.TEXTURE_REC + 4)[0]
        if (su, sv) == (1.0, 1.0) and width >= 64:
            continue
        image = bake_static_chicago(opened, shader, 256)
        if image is None:
            continue
        info = texconv.resolve_shader(opened, shader)
        klass = min(texconv.klass_cap_for(info), texconv.alpha_class(image.pixels))
        jobs.append((index, texconv.convert_rgba(shader, image.pixels, image.width, image.height, klass)))
        print(f"sky bake {entry.path} {image.width}x{image.height}", flush=True)
    if not jobs:
        return data
    pixels = bytearray()
    records = bytearray()
    new_tex = tex_count + len(jobs)
    new_data = texconv.HEADER_SIZE + new_tex * texconv.TEXTURE_REC + bind_count * texconv.BINDING_REC

    def take(blob: bytes) -> tuple[int, int]:
        clut_at = new_data + len(pixels)
        pixels.extend(blob)
        return clut_at, len(blob)

    for index in range(tex_count):
        at = tex_at + index * texconv.TEXTURE_REC
        source, width, height, psm, mips, flags, clut, pixel, pixel_bytes, entries, _pad, average = struct.unpack_from(
            texconv.TEXTURE_FMT, data, at)
        clut_at, _clut_n = take(data[clut:clut + entries * 4])
        pixel_at, _pixel_n = take(data[pixel:pixel + pixel_bytes])
        records += struct.pack(texconv.TEXTURE_FMT, source, width, height, psm, mips, flags,
                               clut_at, pixel_at, pixel_bytes, entries, 0, average)
    new_index = {}
    baked = {}
    for bind_index, texture in jobs:
        clut_at, _clut_n = take(texture.clut)
        pixel_at, _pixel_n = take(b"".join(texture.mips))
        new_index[bind_index] = tex_count + len(new_index)
        baked[bind_index] = texture
        records += struct.pack(texconv.TEXTURE_FMT, texture.source_id, texture.width, texture.height, texture.psm,
                               len(texture.mips), texture.flags, clut_at, pixel_at, texture.pixel_bytes,
                               texture.clut_entries, 0, texture.avg_rgba)
    binds = bytearray()
    untextured = 0
    for index in range(bind_count):
        rec = bytearray(data[bind_at + index * texconv.BINDING_REC:
                             bind_at + (index + 1) * texconv.BINDING_REC])
        if index in new_index:
            struct.pack_into("<H", rec, 4, new_index[index])
            struct.pack_into("<ff", rec, 12, 1.0, 1.0)
            struct.pack_into("<I", rec, 20, baked[index].avg_rgba)
        texture = struct.unpack_from("<H", rec, 4)[0]
        if texture == texconv.NO_TEXTURE:
            untextured += 1
        binds += rec
    tex_off = texconv.HEADER_SIZE
    bind_off = tex_off + len(records)
    data_off = bind_off + len(binds)
    if data_off != new_data:
        raise RuntimeError("sky texture table does not meet the pixel data")
    head = struct.pack(texconv.TEXS_HEADER, texconv.TEXS_MAGIC, texconv.VERSION, 0,
                       new_tex, bind_count, tex_off, bind_off, data_off, data_off + len(pixels), untextured)
    blob = head + bytes(records) + bytes(binds) + bytes(pixels)
    texconv.parse_texs(blob)
    return blob


def _snapshot(weapons: list[Weapon]) -> list[tuple]:
    return [(w.path, w.model_tag, w.anim_tag, w.idle, w.shared, w.hand, w.model_name, str(w.source))
            for w in weapons]


def _restore(weapons: list[Weapon], snapshot: list[tuple]) -> None:
    for weapon, item in zip(weapons, snapshot):
        weapon.model_tag, weapon.anim_tag, weapon.idle = item[1], item[2], item[3]
        weapon.shared, weapon.hand, weapon.model_name = item[4], item[5], item[6]


def build(force: bool = False) -> None:
    manifest = OUT / "manifest.json"
    table = OUT / "weapons.fp"
    if not force and manifest.is_file() and table.is_file() and (OUT / "bloodgulch.obj.hp2").is_file():
        current = json.loads(manifest.read_text())
        blob = table.read_bytes()
        if current.get("stamp") == STAMP and b"AMO1" in blob and b"PRJ1" in blob:
            print(f"play weapon pack is current ({current['models']} models)", flush=True)
            return
        if b"WFP1" in blob and b"RMP1" in blob:
            table.write_bytes(attach_ammo(blob))
            current["stamp"] = STAMP
            current["ammo"] = "retail magazines and projectiles"
            manifest.write_text(json.dumps(current, indent=2) + "\n")
            print(f"wrote retail magazines and projectiles for {current['weapons']} weapons", flush=True)
            return
    if not BASE_PACK.is_file():
        raise RuntimeError("Blood Gulch object pack is missing")
    weapons = collect(_weapon_paths())
    snapshot = _snapshot(weapons)
    batches = convert_groups(weapons)
    _restore(weapons, snapshot)
    pack = hp2.parse(BASE_PACK.read_bytes())
    sections = {item.tag: pack.read(item.tag) for item in pack.sections}
    modl, tex, anim = _assign(sections["MODL"], sections["OTEX"], sections["ANIM"], batches)
    total = len(modl) + len(tex) + len(anim) + len(sections["SCEN"]) + len(sections["SKY0"])
    print(f"merged object bytes {total}", flush=True)
    if total > BUDGET:
        print("full animation graphs exceed the resident object budget; keeping idle clips", flush=True)
        _restore(weapons, snapshot)
        for batch in batches:
            if not batch.anim:
                continue
            batch.anim = keep_idle(batch.anim, {weapon.anim_tag: weapon.idle
                                                for weapon in batch.weapons if weapon.anim_tag}) or None
        for weapon in weapons:
            if weapon.anim_tag and weapon.idle != NO_ANIM:
                weapon.idle = 0
            else:
                weapon.anim_tag = 0
                weapon.idle = NO_ANIM
                weapon.arms_map = []
                weapon.gun_map = []
        modl, tex, anim = _assign(sections["MODL"], sections["OTEX"], sections["ANIM"], batches)
        total = len(modl) + len(tex) + len(anim) + len(sections["SCEN"]) + len(sections["SKY0"])
        print(f"idle-only object bytes {total}", flush=True)
        if total > BUDGET:
            raise RuntimeError(f"weapon models need {total} bytes; the object region holds {BUDGET}")
    tex = rebake_sky(tex, MAPS / "bloodgulch.map")
    total = len(modl) + len(tex) + len(anim) + len(sections["SCEN"]) + len(sections["SKY0"])
    if total > BUDGET:
        raise RuntimeError(f"weapon models need {total} bytes; the object region holds {BUDGET}")
    sections["MODL"], sections["OTEX"], sections["ANIM"] = modl, tex, anim
    ordered = [(item.tag, sections[item.tag]) for item in pack.sections]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bloodgulch.obj.hp2").write_bytes(hp2.build("bloodgulch", ordered))
    blob = bytearray(struct.pack("<4sHH", b"WFP1", len(weapons), REC.size))
    models = 0
    for weapon in weapons:
        if weapon.model_tag:
            models += 1
        blob += REC.pack(_z(weapon.path, 64), weapon.model_tag, weapon.anim_tag, weapon.idle,
                         weapon.shared, _z(weapon.hand, 32), 0)
        mesh = weapon.model_name or "no model"
        print(f"  {weapon.path}  {mesh}  shared {weapon.shared}  idle {weapon.idle}", flush=True)
    blob += struct.pack("<4sH", b"RMP1", len(weapons))
    for weapon in weapons:
        if len(weapon.arms_map) > 64 or len(weapon.gun_map) > 64:
            raise RuntimeError(f"{weapon.path} has more nodes than the pose table")
        blob += REMAP.pack(weapon.arms_model, weapon.model_tag, weapon.anim_tag,
                           len(weapon.arms_map), len(weapon.gun_map), 0,
                           bytes(weapon.arms_map).ljust(64, b"\xff"),
                           bytes(weapon.gun_map).ljust(64, b"\xff"))
    blob = attach_ammo(bytes(blob))
    (OUT / "weapons.fp").write_bytes(blob)
    manifest.write_text(json.dumps({
        "stamp": STAMP, "weapons": len(weapons), "models": models, "bytes": total,
        "ammo": "retail magazines",
        "note": "Play object pack. Reference packs under data/retail are unchanged.",
    }, indent=2) + "\n")
    print(f"wrote {models} weapon models of {len(weapons)} weapons", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        build(args.force)
    except (OSError, RuntimeError, modelconv.ConvertError, animconv.ConvertError, texconv.TexError) as error:
        sys.exit(f"Weapon pack failed: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
