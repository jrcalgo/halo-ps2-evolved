#!/usr/bin/env python3
"""Pin the stock-MP actor spawn set and run CE's seat/mounted-weapon place path.

Raw Xbox tag bytes are the oracle. The 13 multiplayer maps carry three hollow
actv stubs and vehicle seats whose built-in actor index is NONE. This compiles
the real CE unit_new seat scan and ai_place_pending_mounted_weapons against
relocated Sidewinder vehicle bytes. It does not invent resolved actor/unit
references or claim bot coverage.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CE = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/step8-vehicle-seat-actors"
SOURCE_DIR = Path(os.environ.get(
    "HALO_HCU_MP_MAP_DIR", ROOT / "build/retail-maps/decompressed"))
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
MAP_SHA256 = {
    "beavercreek": "eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a",
    "bloodgulch": "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1",
    "boardingaction": "34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522",
    "carousel": "3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1",
    "chillout": "52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb",
    "damnation": "87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c",
    "hangemhigh": "e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f",
    "longest": "e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9",
    "prisoner": "85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307",
    "putput": "efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243",
    "ratrace": "577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e",
    "sidewinder": "995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc",
    "wizard": "978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb",
}
EXPECTED_ACTV = (
    "vehicles\\warthog\\warthog gunner",
    "vehicles\\ghost\\ghost pilot",
    "vehicles\\scorpion\\scorpion pilot",
)
EXPECTED_VEHI = (
    "vehicles\\warthog\\warthog",
    "vehicles\\ghost\\ghost_mp",
    "vehicles\\scorpion\\scorpion_mp",
)
NONE32 = -1
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")]
from halo2ps2 import mapinfo, tagindex  # noqa: E402


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def extract_function(source: str, signature: str) -> str:
    start = source.rindex(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated CE function: {signature}")


def compile_ce_offsets() -> dict[str, int]:
    clang = shutil.which("clang")
    if not clang:
        raise SystemExit("clang is required for the CE ILP32 offset probe")
    src = r'''
#include "cseries.h"
#include "units/unit_definitions.h"
#include "scenario/scenario_definitions.h"
#include "ai/actor_definitions.h"
unsigned step8_unit_seat = sizeof(struct unit_seat);
unsigned step8_unit_seat_built_in = __builtin_offsetof(struct unit_seat, built_in_actor_reference);
unsigned step8_unit_seat_label = __builtin_offsetof(struct unit_seat, label);
unsigned step8_unit_def = sizeof(struct unit_definition);
unsigned step8_unit_seats = __builtin_offsetof(struct unit_definition, unit.seats);
unsigned step8_unit_spawned = __builtin_offsetof(struct unit_definition, unit.spawned_actor_variant);
unsigned step8_scnr_palette = __builtin_offsetof(struct scenario, ai_actor_palette);
unsigned step8_scnr_encounters = __builtin_offsetof(struct scenario, ai_encounters);
unsigned step8_actv = sizeof(struct actor_variant_definition);
unsigned step8_actv_actor = __builtin_offsetof(struct actor_variant_definition, actor_reference);
unsigned step8_actv_unit = __builtin_offsetof(struct actor_variant_definition, unit_reference);
unsigned step8_actv_ranged = __builtin_offsetof(struct actor_variant_definition, ranged_combat.reference);
unsigned step8_tag_ref = sizeof(struct tag_reference);
unsigned step8_tag_block = sizeof(struct tag_block);
'''
    with tempfile.TemporaryDirectory(prefix="hcu-seat-off-") as directory:
        temp = Path(directory)
        prefix = temp / "halo_step8_ps2_prefix.h"
        prefix_text = (CE / "port/linux/include/halo_linux_prefix.h").read_text()
        linux_capacity = '#include "halo_port_limits.h"'
        if prefix_text.count(linux_capacity) != 1:
            raise SystemExit("unexpected Linux prefix capacity include")
        prefix.write_text(prefix_text.replace(linux_capacity, '#include "halo_ps2_limits.h"'))
        harness = temp / "off.c"
        harness.write_text(src)
        includes = json.loads((CE / "port/linux/port.json").read_text())["game"]["include_dirs"]
        command = [clang, "--target=i686-linux-gnu", "-m32", "-fshort-wchar",
            "-malign-double", "-fcommon", "-fno-pic", "-fno-stack-protector",
            "-fno-builtin", "-D__STRICT_ANSI__", "-DDEBUG", "-Dxbox",
            "-include", str(prefix),
            "-I", str(CE / "port/linux/include"), "-I", str(CE / "port/include/xdk"),
            "-I", str(CE / "port/ps2/include"),
            "-c", str(harness), "-o", str(temp / "off.o")]
        for include in includes:
            command.extend(["-I", str(CE / include)])
        built = subprocess.run(command, capture_output=True, text=True)
        if built.returncode:
            raise SystemExit("ILP32 offset compile failed:\n" + built.stdout + built.stderr)
        obj = (temp / "off.o").read_bytes()
        listing = subprocess.run(
            ["nm", "-n", str(temp / "off.o")], capture_output=True, text=True, check=True).stdout
        e_shoff = struct.unpack_from("<I", obj, 32)[0]
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", obj, 46)
        shstr = struct.unpack_from("<IIIIIIIIII", obj, e_shoff + e_shstrndx * e_shentsize)
        names = obj[shstr[4]:shstr[4] + shstr[5]]
        data = None
        for index in range(e_shnum):
            section = struct.unpack_from("<IIIIIIIIII", obj, e_shoff + index * e_shentsize)
            end = names.find(b"\0", section[0])
            if names[section[0]:end] == b".data":
                data = section
                break
        if data is None:
            raise SystemExit("offset object has no .data")
        payload = obj[data[4]:data[4] + data[5]]
        offsets = {}
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[-1].startswith("step8_"):
                addr = int(parts[0], 16)
                offsets[parts[-1]] = struct.unpack_from("<I", payload, addr - data[3])[0]
        expected = {
            "step8_unit_seat": 284, "step8_unit_seat_built_in": 248,
            "step8_unit_seat_label": 4, "step8_unit_def": 752,
            "step8_unit_seats": 740, "step8_unit_spawned": 588,
            "step8_scnr_palette": 1056, "step8_scnr_encounters": 1068,
            "step8_actv": 568, "step8_actv_actor": 4, "step8_actv_unit": 20,
            "step8_actv_ranged": 100, "step8_tag_ref": 16, "step8_tag_block": 12,
        }
        if offsets != expected:
            raise SystemExit(f"CE ILP32 offsets drifted: {offsets}")
        return offsets


def fourcc(raw: bytes) -> str:
    if raw == b"\xff\xff\xff\xff":
        return "NONE"
    return raw[::-1].decode("ascii", "replace")


def read_ref(region: bytes, off: int) -> dict:
    group, name, nlen, index = struct.unpack_from("<4sIIi", region, off)
    return {"group": fourcc(group), "name_ptr": name, "name_length": nlen, "index": index}


def read_block(region: bytes, off: int) -> tuple[int, int]:
    count, addr, _defn = struct.unpack_from("<iII", region, off)
    return count, addr


def seat_label(region: bytes, off: int) -> str:
    raw = region[off:off + 32]
    end = raw.find(b"\0")
    return raw[:end if end >= 0 else 32].decode("latin1", "replace")


def open_map(path: Path) -> tuple[tagindex.TagIndex, bytes, int]:
    index = tagindex.TagIndex.read(path)
    header = mapinfo.read_header(path)
    with path.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
    if len(region) != header.tag_data_size:
        raise SystemExit(f"{path.name}: truncated tag region")
    return index, region, index.base


def census_map(name: str, offsets: dict[str, int]) -> dict:
    path = SOURCE_DIR / f"{name}.map"
    source_hash = sha256_file(path)
    issues: list[dict] = []
    if source_hash != MAP_SHA256[name]:
        issues.append({"kind": "source-hash", "actual": source_hash, "pinned": MAP_SHA256[name]})
    index, region, base = open_map(path)
    by_group: dict[str, list] = {}
    for entry in index.entries:
        by_group.setdefault(entry.group or "?", []).append(entry)
    actv = by_group.get("actv", [])
    actr = by_group.get("actr", [])
    vehi = by_group.get("vehi", [])
    scnr = by_group.get("scnr", [])
    if len(scnr) != 1:
        issues.append({"kind": "scenario-count", "actual": len(scnr)})
        return {"map": name, "source_sha256": source_hash, "issues": issues}
    scenario_off = scnr[0].data_address - base
    palette_count, palette_addr = read_block(region, scenario_off + offsets["step8_scnr_palette"])
    encounter_count, _ = read_block(region, scenario_off + offsets["step8_scnr_encounters"])
    palette = []
    if palette_count:
        start = palette_addr - base
        for slot in range(palette_count):
            palette.append(read_ref(region, start + slot * offsets["step8_tag_ref"]))
    actv_rows = []
    for entry in actv:
        off = entry.data_address - base
        blob = region[off:off + offsets["step8_actv"]]
        row = {
            "path": entry.path,
            "tag_id": entry.tag_id,
            "sha256": sha256_bytes(blob),
            "actor": read_ref(blob, offsets["step8_actv_actor"]),
            "unit": read_ref(blob, offsets["step8_actv_unit"]),
            "ranged": read_ref(blob, offsets["step8_actv_ranged"]),
        }
        if row["path"] not in EXPECTED_ACTV:
            issues.append({"kind": "unexpected-actv", "path": row["path"]})
        for field in ("actor", "unit", "ranged"):
            if row[field]["index"] != NONE32 or row[field]["name_ptr"] != 0:
                issues.append({"kind": "resolved-actv-ref", "path": row["path"], "field": field})
        actv_rows.append(row)
    if sorted(row["path"] for row in actv_rows) != sorted(EXPECTED_ACTV) or actr:
        issues.append({
            "kind": "actv-actr-census",
            "actv": [row["path"] for row in actv_rows],
            "actr": [entry.path for entry in actr],
        })
    vehicles = []
    wired_seats = 0
    for entry in vehi:
        off = entry.data_address - base
        definition = region[off:off + offsets["step8_unit_def"]]
        spawned = read_ref(definition, offsets["step8_unit_spawned"])
        seat_count, seat_addr = read_block(definition, offsets["step8_unit_seats"])
        seats = []
        start = seat_addr - base
        for slot in range(seat_count):
            seat_off = start + slot * offsets["step8_unit_seat"]
            builtin = read_ref(region, seat_off + offsets["step8_unit_seat_built_in"])
            if builtin["index"] != NONE32:
                wired_seats += 1
                issues.append({
                    "kind": "wired-seat",
                    "vehicle": entry.path,
                    "seat": slot,
                    "index": builtin["index"],
                })
            seats.append({
                "label": seat_label(region, seat_off + offsets["step8_unit_seat_label"]),
                "builtin": builtin,
            })
        if entry.path not in EXPECTED_VEHI:
            issues.append({"kind": "unexpected-vehi", "path": entry.path})
        if spawned["index"] != NONE32:
            issues.append({"kind": "spawned-actor", "vehicle": entry.path, "index": spawned["index"]})
        vehicles.append({
            "path": entry.path,
            "tag_id": entry.tag_id,
            "definition_sha256": sha256_bytes(definition),
            "spawned": spawned,
            "seats": seats,
            "seat_bytes_sha256": sha256_bytes(region[start:start + seat_count * offsets["step8_unit_seat"]]),
        })
    if sorted(row["path"] for row in vehicles) != sorted(EXPECTED_VEHI):
        issues.append({"kind": "vehicle-census", "paths": [row["path"] for row in vehicles]})
    if encounter_count != 0:
        issues.append({"kind": "encounters", "count": encounter_count})
    for slot in palette:
        if slot["index"] != NONE32:
            issues.append({"kind": "palette-resolved", "index": slot["index"]})
    return {
        "map": name,
        "source_sha256": source_hash,
        "actr": 0 if not actr else len(actr),
        "actv": actv_rows,
        "vehicles": vehicles,
        "palette_count": palette_count,
        "palette": palette,
        "encounters": encounter_count,
        "wired_seats": wired_seats,
        "issues": issues,
    }


def c_array(name: str, data: bytes) -> str:
    body = ", ".join(f"0x{byte:02x}" for byte in data)
    return f"static unsigned char {name}[{len(data)}] = {{ {body} }};\n"


def sidewinder_vehicles(offsets: dict[str, int]) -> list[dict]:
    index, region, base = open_map(SOURCE_DIR / "sidewinder.map")
    rows = []
    for entry in index.entries:
        if entry.group != "vehi":
            continue
        off = entry.data_address - base
        definition = region[off:off + offsets["step8_unit_def"]]
        seat_count, seat_addr = read_block(definition, offsets["step8_unit_seats"])
        start = seat_addr - base
        seats = region[start:start + seat_count * offsets["step8_unit_seat"]]
        rows.append({"path": entry.path, "definition": definition, "seats": seats, "count": seat_count})
    rows.sort(key=lambda row: EXPECTED_VEHI.index(row["path"]))
    if [row["path"] for row in rows] != list(EXPECTED_VEHI):
        raise SystemExit("Sidewinder vehicle set drifted")
    return rows


def run_ilp32_fixture(offsets: dict[str, int], vehicles: list[dict]) -> dict:
    clang = shutil.which("clang")
    if not clang:
        raise SystemExit("clang is required for the CE i386 ILP32 fixture")
    actor_source = (CE / "source/ai/actors.c").read_text()
    ai_source = (CE / "source/ai/ai.c").read_text()
    units_source = (CE / "source/units/units.c").read_text()
    data_source = (CE / "source/memory/data.c").read_text()
    seat_scan = extract_function(units_source, "boolean unit_new(")
    if "if (seat->built_in_actor_reference.index!=NONE)" not in seat_scan:
        raise SystemExit("unit_new no longer queues mounted weapons from built-in seat actors")
    if "ai_create_mounted_weapons_for_unit(unit_index);" not in seat_scan:
        raise SystemExit("unit_new no longer calls ai_create_mounted_weapons_for_unit")
    place = extract_function(ai_source, "static void ai_place_pending_mounted_weapons(")
    if "seat->built_in_actor_reference.index != NONE" not in place:
        raise SystemExit("ai_place_pending_mounted_weapons lost its NONE seat guard")
    if "actor_index = actor_place(" not in place:
        raise SystemExit("ai_place_pending_mounted_weapons no longer calls actor_place")
    create = extract_function(ai_source, "void ai_create_mounted_weapons_for_unit(")
    data_functions = "\n\n".join(extract_function(data_source, signature) for signature in (
        "long data_allocation_size(", "void data_initialize(", "static void datum_initialize(",
        "static boolean data_usable(", "void data_verify(",
        "void *datum_get(", "long datum_new(", "void datum_delete(",
        "void data_make_valid(", "void data_make_invalid(", "void data_delete_all(",
    ))
    actor_functions = "\n\n".join(extract_function(actor_source, signature) for signature in (
        "void actors_initialize(", "void actors_initialize_for_new_map(",
        "void actors_dispose_from_old_map(",
    ))
    arrays = "".join(
        c_array(f"xbox_vehicle_{index}", row["definition"]) +
        c_array(f"xbox_seats_{index}", row["seats"])
        for index, row in enumerate(vehicles))
    headers = r'''
#include "cseries.h"
#include "actors.h"
#include "actor_definitions.h"
#include "actor_placement.h"
#include "ai_globals.h"
#include "ai_scenario_definitions.h"
#include "units/unit_definitions.h"
#include "units/units.h"
#include "objects/objects.h"
#include "memory/data.h"
#include "saved games/game_state.h"
#include "halo_ps2_limits.h"
#include "cseries/errors.h"
#undef match_assert
#define match_assert(file, line, expression) ((void)0)
#undef match_vassert
#define match_vassert(file, line, expression, message) ((void)0)
enum { _actor_mode_braindead = 0, _actor_mode_alert = 2 };
enum { MAXIMUM_NUMBER_OF_MOUNTED_WEAPON_UNITS = 8 };
void platform_log(const char *format, ...);
typedef char step8_seat_size_assert[sizeof(struct unit_seat) == 284 ? 1 : -1];
typedef char step8_seat_builtin_assert[
    __builtin_offsetof(struct unit_seat, built_in_actor_reference) == 248 ? 1 : -1];
typedef char step8_unit_def_assert[sizeof(struct unit_definition) == 752 ? 1 : -1];
typedef char step8_unit_seats_assert[
    __builtin_offsetof(struct unit_definition, unit.seats) == 740 ? 1 : -1];
typedef char step8_actv_assert[sizeof(struct actor_variant_definition) == 568 ? 1 : -1];
'''
    adapters = r'''
struct data_array *actor_data, *swarm_data, *swarm_component_data;
struct data_array *prop_data;
struct data_array *encounter_data;
long global_updating_actor_index = NONE;
struct ai_globals fixture_ai_globals;
struct ai_globals *ai_globals = &fixture_ai_globals;
static struct unit_definition fixture_vehicles[3];
static struct unit_datum fixture_units[3];
static unsigned char fixture_game_state[HALO_PORT_GAME_STATE_CPU_SIZE];
static unsigned long fixture_game_state_used, fixture_game_state_peak;
static unsigned long fixture_actor_place_calls;
#define STEP8_ACTOR_ARRAY_BYTES (sizeof(struct data_array) + MAXIMUM_ACTORS * sizeof(struct actor_datum))
#define STEP8_SWARM_ARRAY_BYTES (sizeof(struct data_array) + MAXIMUM_SWARMS * sizeof(struct swarm_datum))
#define STEP8_COMPONENT_ARRAY_BYTES (sizeof(struct data_array) + MAXIMUM_SWARM_COMPONENTS * SWARM_COMPONENT_DATUM_SIZE)
char step8_metric_game_state_peak[STEP8_ACTOR_ARRAY_BYTES + STEP8_SWARM_ARRAY_BYTES + STEP8_COMPONENT_ARRAY_BYTES];
char step8_metric_actor_record[sizeof(struct actor_datum)];

static void bytes_zero(void *target, int value, unsigned long size)
{
    byte *out = (byte *)target;
    unsigned long i;
    for (i = 0; i < size; ++i) out[i] = (byte)value;
}
void *csmemset(void *target, long value, unsigned long size) { bytes_zero(target, (int)value, size); return target; }
void *csmemcpy(void *destination, const void *source, unsigned long size)
{
    byte *out = (byte *)destination;
    const byte *in = (const byte *)source;
    unsigned long i;
    for (i = 0; i < size; ++i) out[i] = in[i];
    return destination;
}
char *csstrncpy(char *destination, const char *source, unsigned long size)
{
    unsigned long index;
    for (index = 0; index < size; ++index)
        destination[index] = source[index] ? source[index] : 0;
    return destination;
}

struct data_array *game_state_data_new(const char *name, short maximum_count, short size)
{
    unsigned long payload;
    struct data_array *array;
    if (!name || maximum_count <= 0 || size <= 0) return NULL;
    payload = (unsigned long)data_allocation_size(maximum_count, size);
    if (fixture_game_state_used + payload > sizeof(fixture_game_state)) return NULL;
    array = (struct data_array *)(fixture_game_state + fixture_game_state_used);
    data_initialize(array, name, maximum_count, size);
    fixture_game_state_used += payload;
    if (fixture_game_state_used > fixture_game_state_peak)
        fixture_game_state_peak = fixture_game_state_used;
    return array;
}

void platform_log(const char *format, ...) { (void)format; }
void actor_types_initialize(void) { }
void actor_type_initialize(long index) { (void)index; }
void error(short type, char const *format, ...) { (void)type; (void)format; }
char *tag_get_name(long index) { (void)index; return "sidewinder\\vehicle"; }
char const *tag_name_strip_path(char const *name) { return name; }
void *tag_get(long group, long index)
{
    (void)group;
    if (index >= 0 && index < 3) return &fixture_vehicles[index];
    return NULL;
}
void *tag_block_get_element_with_size(struct tag_block const *block, long index, long element_size)
{
    (void)block; (void)index; (void)element_size;
    return NULL;
}
void *object_get_and_verify_type(long index, unsigned long flags)
{
    (void)flags;
    if (index >= 0 && index < 3) return &fixture_units[index];
    return NULL;
}
void *object_try_and_get_and_verify_type(long index, unsigned long flags)
{
    return object_get_and_verify_type(index, flags);
}
real_point3d *object_get_origin(long object_index, real_point3d *origin)
{
    origin->x = 0.f; origin->y = 0.f; origin->z = 0.f;
    (void)object_index;
    return origin;
}
long actor_place(
    long actor_variant_definition_index,
    long encounter_index,
    long squad_index,
    struct actor_starting_location *starting_location,
    boolean upgrade_major,
    short initial_variant)
{
    (void)actor_variant_definition_index; (void)encounter_index; (void)squad_index;
    (void)starting_location; (void)upgrade_major; (void)initial_variant;
    fixture_actor_place_calls++;
    return NONE;
}
boolean unit_enter_seat(long unit_index, long target_unit_index, short seat_index)
{
    (void)unit_index; (void)target_unit_index; (void)seat_index;
    return FALSE;
}
void actor_input_update(long actor) { (void)actor; }
'''
    main_body = r'''
static void relocate_vehicle(int slot, unsigned char *definition, unsigned char *seats, int seat_bytes)
{
    csmemcpy(&fixture_vehicles[slot], definition, sizeof(fixture_vehicles[slot]));
    fixture_vehicles[slot].unit.seats.address = seats;
    fixture_vehicles[slot].unit.seats.definition = 0;
    (void)seat_bytes;
    csmemset(&fixture_units[slot], 0, sizeof(fixture_units[slot]));
    fixture_units[slot].definition_index = slot;
    fixture_units[slot].unit.actor_index = NONE;
    fixture_units[slot].unit.swarm_actor_index = NONE;
}

static boolean fixture_unit_new_seat_scan(long unit_index)
{
    short seat_index;
    struct unit_datum *unit = unit_get(unit_index);
    struct unit_definition *unit_definition = unit_definition_get(unit->definition_index);
    for (seat_index = 0;
        seat_index<unit_definition->unit.seats.count;
        seat_index++)
    {
        struct unit_seat *seat = TAG_BLOCK_GET_ELEMENT(
            &unit_definition->unit.seats,
            seat_index,
            struct unit_seat);

        if (seat->built_in_actor_reference.index!=NONE)
        {
            ai_create_mounted_weapons_for_unit(unit_index);
            break;
        }
    }
    return ai_globals->mounted_weapon_unit_count != 0;
}

int fixture_main(void)
{
    unsigned long before;
    short slot;
    if (MAXIMUM_ACTORS != HALO_PORT_MAXIMUM_ACTORS) return 8;
    actors_initialize();
    if (!actor_data || fixture_game_state_peak != sizeof(step8_metric_game_state_peak)) return 1;
    actors_initialize_for_new_map();
    before = fixture_game_state_peak;
    csmemset(&fixture_ai_globals, 0, sizeof(fixture_ai_globals));
    fixture_ai_globals.ai_initialized_for_map = TRUE;
    relocate_vehicle(0, xbox_vehicle_0, xbox_seats_0, (int)sizeof(xbox_seats_0));
    relocate_vehicle(1, xbox_vehicle_1, xbox_seats_1, (int)sizeof(xbox_seats_1));
    relocate_vehicle(2, xbox_vehicle_2, xbox_seats_2, (int)sizeof(xbox_seats_2));
    if (fixture_vehicles[0].unit.seats.count != 3 ||
        fixture_vehicles[1].unit.seats.count != 1 ||
        fixture_vehicles[2].unit.seats.count != 5) return 12;
    for (slot = 0; slot < 3; ++slot)
    {
        if (fixture_unit_new_seat_scan(slot)) return 2;
        if (ai_globals->mounted_weapon_unit_count != 0) return 2;
    }
    for (slot = 0; slot < 3; ++slot)
        ai_create_mounted_weapons_for_unit(slot);
    if (ai_globals->mounted_weapon_unit_count != 3) return 13;
    ai_place_pending_mounted_weapons();
    if (fixture_actor_place_calls != 0) return 3;
    if (ai_globals->mounted_weapon_unit_count != 0) return 14;
    if (actor_data->actual_count != 0) return 4;
    if (fixture_game_state_peak != before) return 5;
    actors_dispose_from_old_map();
    if (actor_data->valid) return 6;
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="hcu-step8-seat-ilp32-") as directory:
        temp = Path(directory)
        prefix = temp / "halo_step8_ps2_prefix.h"
        prefix_text = (CE / "port/linux/include/halo_linux_prefix.h").read_text()
        prefix.write_text(prefix_text.replace('#include "halo_port_limits.h"', '#include "halo_ps2_limits.h"'))
        harness = temp / "seat_fixture.c"
        binary = temp / "seat_fixture"
        harness.write_text(headers + data_functions + adapters + arrays + create + "\n\n" +
            place + "\n\n" + actor_functions + main_body + r'''
void _start(void)
{
    int status = fixture_main();
    if (status == 0) __asm__ volatile("int3");
    if (status == 2) __asm__ volatile("ud2");
    if (status == 3) __asm__ volatile("xorl %ecx, %ecx; movl $1, %eax; divl %ecx");
    if (status == 4) __asm__ volatile("movl $0, %eax; movl (%eax), %eax");
    __asm__ volatile("ud2");
    for (;;) { }
}
''')
        includes = json.loads((CE / "port/linux/port.json").read_text())["game"]["include_dirs"]
        command = [clang, "--target=i686-linux-gnu", "-m32", "-fshort-wchar",
            "-malign-double", "-fcommon", "-fno-pic", "-fno-stack-protector",
            "-fno-builtin", "-Wno-implicit-function-declaration", "-D__STRICT_ANSI__",
            "-DDEBUG", "-Dxbox", "-include", str(prefix),
            "-I", str(CE / "port/linux/include"), "-I", str(CE / "port/include/xdk"),
            "-I", str(CE / "port/ps2/include"), "-nostdlib", "-static", "-Wl,-e,_start",
            "-Wl,--build-id=none", str(harness), "-o", str(binary)]
        for include in includes:
            command.extend(["-I", str(CE / include)])
        built = subprocess.run(command, capture_output=True, text=True)
        if built.returncode:
            raise SystemExit("ILP32 CE seat harness compile failed:\n" + built.stdout + built.stderr)
        OUT.mkdir(parents=True, exist_ok=True)
        for artifact in (harness, binary, prefix):
            shutil.copy2(artifact, OUT / artifact.name)
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode != -5:
            raise SystemExit(
                f"ILP32 CE seat fixture did not report the pass trap (returncode {run.returncode})")
        listing = subprocess.run(
            ["nm", "-S", "--defined-only", str(binary)], capture_output=True, text=True, check=True).stdout
        metrics = {}
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[-1].startswith("step8_metric_"):
                metrics[parts[-1]] = int(parts[1], 16)
        if set(metrics) != {"step8_metric_game_state_peak", "step8_metric_actor_record"}:
            raise SystemExit("missing ILP32 seat fixture size markers")
        return {
            "returncode": run.returncode,
            "executable_sha256": sha256_file(binary),
            "harness_sha256": sha256_file(OUT / "seat_fixture.c"),
            "game_state_high_water": metrics["step8_metric_game_state_peak"],
            "actor_record_bytes": metrics["step8_metric_actor_record"],
            "retained": str(OUT.relative_to(ROOT)),
            "actual_ce_functions": [
                "ai_create_mounted_weapons_for_unit",
                "ai_place_pending_mounted_weapons",
                "actors_initialize",
                "actors_dispose_from_old_map",
            ],
            "actor_place": "call-count-probe-not-entered",
        }


def write_report(payload: dict) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    maps = "\n".join(
        f"| `{row['map']}` | {row['actr']} | {len(row['actv'])} | {row['encounters']} | "
        f"{row['palette_count']} | {row['wired_seats']} | {row['source_sha256'][:12]} |"
        for row in payload["maps"])
    text = f"""# M2 Step 8 stock-MP vehicle-seat actor oracle

## Status

**{payload['status']}.** All 13 stock multiplayer maps were walked with
compiler-derived CE offsets. Each map has zero `actr` tags, zero encounters,
three hollow `actv` stubs, and zero vehicle seats whose
`built_in_actor_reference.index` is not `NONE`. Sidewinder's single actor
palette slot is also unresolved. The freestanding ILP32 fixture relocates the
three Sidewinder vehicle definitions and runs the real CE `unit_new` seat scan
plus `ai_place_pending_mounted_weapons`. Both paths leave the actor datum array
empty and never enter `actor_place`.

This is not bot coverage. Stock MP maps do not contain a resolved actor/unit
pair that CE can place. Do not fill those references synthetically and call
that the retail spawn path.

## Census

| map | actr | actv | encounters | palette | wired seats | map SHA |
|---|---:|---:|---:|---:|---:|---|
{maps}

The three `actv` paths on every map are `{EXPECTED_ACTV[0]}`,
`{EXPECTED_ACTV[1]}`, and `{EXPECTED_ACTV[2]}`. Their actor, unit, and ranged
weapon references have `index == NONE` and a null name pointer. Vehicle seats
keep labels (`W-gunner`, `G-driver`, `scorpion-driver`, ...) but the built-in
actor index is `NONE`, so `unit_new` never calls
`ai_create_mounted_weapons_for_unit`.

## ILP32 fixture

Command: `python3 tools/audit_mp_vehicle_seat_actors.py`

- actual CE functions: {", ".join(payload["fixture"]["actual_ce_functions"])}
- `actor_place`: {payload["fixture"]["actor_place"]}
- actor record: {payload["fixture"]["actor_record_bytes"]} B
- game-state high-water: {payload["fixture"]["game_state_high_water"]} B of the 3,162,112-B CPU arena
- executable SHA-256: `{payload["fixture"]["executable_sha256"]}`
- retained: `{payload["fixture"]["retained"]}`

The fixture force-queues all three Sidewinder vehicles after the seat scan
reports zero, then runs `ai_place_pending_mounted_weapons` so the NONE seat
guard is executed against relocated Xbox seat bytes. `actor_place` is a
call-count probe because the retail seats never reach it; calling the real
body with a hollow `actv` would dereference `actor_definition_get(NONE)`.

## Limits

No infantry encounters, no resolved vehicle-seat gunners, no actor-owned
objects/weapons, no AI tick, and no PCSX2/EE measurement. Bots remain in
product scope and still need a sourced spawn path that is not present in these
13 cache files. Step 7/8 stay open. Arenas and the reserve are unchanged.
"""
    report = OUT / "report.md"
    report.write_text(text)
    return sha256_file(report)


def run() -> dict:
    offsets = compile_ce_offsets()
    maps = [census_map(name, offsets) for name in MP_MAPS]
    vehicles = sidewinder_vehicles(offsets)
    fixture = run_ilp32_fixture(offsets, vehicles)
    issues = [issue for row in maps for issue in row["issues"]]
    payload = {
        "status": "PASS" if not issues and len(maps) == len(MP_MAPS) else "ISSUES",
        "issues": issues,
        "offsets": offsets,
        "maps": maps,
        "fixture": fixture,
        "hashes": {
            "units_c": sha256_file(CE / "source/units/units.c"),
            "ai_c": sha256_file(CE / "source/ai/ai.c"),
            "actors_c": sha256_file(CE / "source/ai/actors.c"),
            "actor_definitions_h": sha256_file(CE / "source/ai/actor_definitions.h"),
            "unit_definitions_h": sha256_file(CE / "source/units/unit_definitions.h"),
        },
    }
    payload["report_sha256"] = write_report(payload)
    (OUT / "result.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> int:
    payload = run()
    print(
        "step8-mp-vehicle-seat-actors "
        f"status={payload['status']} maps={len(payload['maps'])} "
        f"actr=0 actv=3 encounters=0 wired_seats=0 "
        f"actor_place={payload['fixture']['actor_place']} "
        f"game_state_high_water={payload['fixture']['game_state_high_water']} "
        f"executable_sha256={payload['fixture']['executable_sha256']} "
        f"report_sha256={payload['report_sha256']}")
    if payload["status"] != "PASS":
        raise SystemExit(json.dumps(payload["issues"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
