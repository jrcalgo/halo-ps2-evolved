"""Characterize the CE-to-platform sound request seam on the 13 stock MP maps.

The production PS2 preferences select no sound platform, and the queue call
does not receive a tag datum, owner, or position. This fixture still runs the
real sound_manager path up to that call, with a test-only recorder, and checks
the playback numbers against the raw Xbox tags. It does not implement SPU2.
"""
from pathlib import Path
import hashlib
import re
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/step7-swarm/soundreq"
MAP_DIR = ROOT / "build/retail-maps/decompressed"
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
FLT_MAX_BITS = 0x7F7FFFFF
AUDIO_REGION = 524288


def ff(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def fbits(value):
    return struct.unpack("<I", struct.pack("<f", ff(value)))[0]


def fadd(left, right):
    return ff(ff(left) + ff(right))


def fsub(left, right):
    return ff(ff(left) - ff(right))


def fmul(left, right):
    return ff(ff(left) * ff(right))


def fdiv(left, right):
    return ff(ff(left) / ff(right))


def scale_value(base, lower, upper, scale):
    return fmul(fadd(fmul(fsub(upper, lower), scale), lower), base)


def c_float_token(token):
    return fbits(float(token.strip().rstrip("fF")))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_matching(text, needle):
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return number, line.strip()
    raise AssertionError(needle)


def parse_classes(source):
    rows = re.findall(r"^\tSOUND_CLASS_DEFINITION\(([^)]*)\)", source, re.M)
    names = re.search(
        r"char const \*sound_class_names\[NUMBER_OF_SOUND_CLASSES\] =\s*\{(.*?)\};",
        source, re.S)
    if not names:
        raise AssertionError("sound class names missing")
    name_list = re.findall(r'"([^"]*)"', names.group(1))
    if len(rows) != 51 or len(name_list) != 51:
        raise AssertionError(f"class table {len(rows)} names {len(name_list)}")
    parsed = []
    for row, name in zip(rows, name_list):
        parts = [part.strip() for part in row.split(",")]
        parsed.append({
            "name": name,
            "wet": c_float_token(parts[6]),
            "minimum": c_float_token(parts[7]),
            "disabled": int(parts[11]),
        })
    return parsed


def compile_binaries():
    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    includes = [
        ROOT / "tests/hcu_scenario_host_shim",
        ROOT / "tests/soundreq_host_shim",
        HCU / "source",
        HCU / "source/cseries",
        HCU / "source/sound",
        HCU / "source/math",
        HCU / "source/tag_files",
        HCU / "source/memory",
        HCU / "source/structures",
        HCU / "source/render",
        HCU / "source/rasterizer",
        HCU / "source/objects",
        HCU / "source/game",
        HCU / "source/interface",
        HCU / "source/effects",
        HCU / "source/camera",
        HCU / "source/scenario",
        HCU / "source/cache",
        HCU / "source/saved games",
        HCU / "source/networking",
        HCU / "source/physics",
        HCU / "source/units",
        HCU / "source/models",
        HCU / "source/ai",
        HCU / "source/hs",
        HCU / "source/input",
        HCU / "source/main",
        HCU / "source/rasterizer/common",
        HCU / "port/ps2/include",
        HCU / "port/include",
        HCU / "port/include/xdk",
    ]
    flags = [
        "gcc-13", "-m32", "-std=gnu99", "-fms-extensions", "-fshort-wchar",
        "-fwrapv", "-fno-strict-aliasing", "-ffunction-sections", "-fdata-sections",
        "-fgnu89-inline", "-fcommon", "-w",
        "-include", str(ROOT / "tests/soundreq_host_prefix.h"),
    ]
    flags.extend(item for path in includes for item in ("-I", str(path)))
    objects = []
    units = [
        ROOT / "tests/soundreq_host_stubs.c",
        HCU / "source/memory/data.c",
        HCU / "source/sound/sound_classes.c",
        HCU / "source/sound/sound_definitions.c",
        HCU / "source/sound/sound_environment_definitions.c",
        HCU / "source/math/random_math.c",
    ]
    for unit in units:
        obj = out / (unit.stem + ".o")
        log = out / (unit.stem + ".compile.log")
        result = subprocess.run(flags + ["-c", "-o", str(obj), str(unit)],
                                 capture_output=True, text=True)
        log.write_text(result.stderr)
        if result.returncode != 0:
            raise AssertionError(f"compile failed: {unit}\n{result.stderr[-2000:]}")
        objects.append(obj)
    bridge = ROOT / "tests/hcu_mp_sound_request_bridge.c"
    built = {}
    for name, extra in (("soundreq-drive", []), ("soundreq-ps2", ["-DHALO_PS2"])):
        obj = out / (name + ".o")
        log = out / (name + ".compile.log")
        result = subprocess.run(flags + extra + ["-c", "-o", str(obj), str(bridge)],
                                 capture_output=True, text=True)
        log.write_text(result.stderr)
        if result.returncode != 0:
            raise AssertionError(f"compile failed: {name}\n{result.stderr[-2000:]}")
        exe = out / name
        link = subprocess.run(
            ["gcc-13", "-m32", "-Wl,--gc-sections", "-o", str(exe), str(obj),
             *[str(path) for path in objects], "-lm"],
            capture_output=True, text=True)
        (out / (name + ".link.log")).write_text(link.stderr)
        if link.returncode != 0:
            raise AssertionError(f"link failed: {name}\n{link.stderr[-2000:]}")
        built[name] = exe
    return built


def run_checked(exe, args, log_name):
    result = subprocess.run([str(exe), *args], capture_output=True, text=True)
    (OUT / log_name).write_text(result.stdout)
    (OUT / (log_name + ".err")).write_text(result.stderr)
    if result.returncode < 0 or result.returncode == 31:
        raise AssertionError(f"{exe.name} signal {result.returncode}")
    if result.returncode != 0:
        raise AssertionError(
            f"{exe.name} exit {result.returncode}\n{result.stderr[-2000:]}\n{result.stdout[-2000:]}")
    return result.stdout


def schema_values(text):
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            values[parts[0]] = int(parts[1])
    return values


def load_map(name):
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex

    path = MAP_DIR / f"{name}.map"
    blob = path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != MAP_SHA256[name]:
        raise AssertionError(f"{name} sha256 {digest}")
    header = mapinfo.read_header(path)
    index = tagindex.TagIndex.read(path)
    region = blob[header.tag_data_offset:header.tag_data_offset + header.tag_data_size]
    locations = bsp_tools.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{name} BSP count {len(locations)}")
    location = locations[0]
    image = blob[location.file_offset:location.file_offset + location.size]
    if len(image) != location.size:
        raise AssertionError(f"{name} truncated BSP")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError(f"{name} BSP root leaves the image")
    tags = {entry.tag_id & 0xFFFFFFFF: entry for entry in index.entries}
    return {
        "name": name, "sha256": digest, "blob": blob, "index": index,
        "image": image, "root": root, "bsp_sha256": hashlib.sha256(image).hexdigest(),
        "bsp_path": location.path, "tags": tags,
    }


def read_block(image, root, offset, stride, label):
    count, address = struct.unpack_from("<iI", image, root + offset)
    if count < 0:
        raise AssertionError(f"negative {label}")
    target = address - (struct.unpack_from("<I", image, 0)[0] - root)
    # address is virtual; location.address = virtual_root - file_root, so
    # target = address - location.address = address - (image_virtual - root).
    image_virtual = struct.unpack_from("<I", image, 0)[0]
    location_address = image_virtual - root
    target = address - location_address if address else 0
    if count and (target < 0 or target + count * stride > len(image)):
        raise AssertionError(f"{label} extent leaves the BSP")
    return count, target


def tag_bytes(loaded, datum, size, group):
    entry = loaded["tags"].get(datum & 0xFFFFFFFF)
    if entry is None or entry.group != group:
        raise AssertionError(f"{loaded['name']} datum {datum} is not {group!r}")
    offset = loaded["index"].addr_to_off(entry.data_address)
    body = loaded["blob"][offset:offset + size]
    if len(body) != size:
        raise AssertionError(f"{loaded['name']} {group} truncated")
    return body, entry


def block_bytes(loaded, count, address, stride, label):
    if count == 0:
        return b""
    if count < 0 or count > 4096:
        raise AssertionError(f"{loaded['name']} {label} count {count}")
    offset = loaded["index"].addr_to_off(address)
    body = loaded["blob"][offset:offset + count * stride]
    if len(body) != count * stride:
        raise AssertionError(f"{loaded['name']} {label} leaves the tag region")
    return body


def reference_index(body, offset):
    return struct.unpack_from("<i", body, offset + 12)[0]


def environment_priority(loaded, datum):
    body, _entry = tag_bytes(loaded, datum, 72, "snde")
    return struct.unpack_from("<h", body, 4)[0], body


def select_background(loaded):
    image, root = loaded["image"], loaded["root"]
    cluster_count, clusters = read_block(image, root, 308, 0x68, "clusters")
    background_count, backgrounds = read_block(image, root, 508, 0x74, "background")
    environment_count, environments = read_block(image, root, 520, 0x50, "environment")
    fog_free = None
    for cluster_index in range(cluster_count):
        base = clusters + cluster_index * 0x68
        fog, background_index, environment_index = struct.unpack_from("<hhh", image, base + 2)
        if fog != -1 or not 0 <= environment_index < environment_count:
            continue
        environment_tag = struct.unpack_from(
            "<i", image, environments + environment_index * 0x50 + 0x2C)[0]
        if environment_tag == -1:
            continue
        background_tag = -1
        if 0 <= background_index < background_count:
            background_tag = struct.unpack_from(
                "<i", image, backgrounds + background_index * 0x74 + 0x2C)[0]
        fog_free = {
            "kind": "fog-free", "cluster": cluster_index,
            "background": background_tag, "environment": environment_tag,
            "fog_environment": -1, "fog_datum": -1,
        }
        break
    bounds = struct.unpack_from("<6f", image, root + 200)
    center = tuple(ff((ff(bounds[index * 2]) + ff(bounds[index * 2 + 1])) * ff(0.5))
                   for index in range(3))
    if fog_free:
        fog_free["position"] = center
        fog_free["background_count"] = background_count
        fog_free["environment_count"] = environment_count
        fog_free["cluster_count"] = cluster_count
        return fog_free

    plane_count, planes = read_block(image, root, 376, 0x20, "fog-planes")
    region_count, regions = read_block(image, root, 388, 0x28, "fog-regions")
    palette_count, palette = read_block(image, root, 400, 0x88, "fog-palette")
    chain = None
    for cluster_index in range(cluster_count):
        base = clusters + cluster_index * 0x68
        reference = struct.unpack_from("<h", image, base + 2)[0]
        if reference == -1 or not (reference & 0x8000):
            continue
        plane_index = reference & 0x7FFF
        if plane_index >= plane_count:
            continue
        plane = planes + plane_index * 0x20
        region_index = struct.unpack_from("<h", image, plane)[0]
        if not 0 <= region_index < region_count:
            continue
        region = regions + region_index * 0x28
        fog_palette_index = struct.unpack_from("<h", image, region + 0x24)[0]
        if not 0 <= fog_palette_index < palette_count:
            continue
        fog_datum = struct.unpack_from("<i", image, palette + fog_palette_index * 0x88 + 0x2C)[0]
        if fog_datum == -1:
            continue
        normal = struct.unpack_from("<4f", image, plane + 4)
        chain = {
            "cluster": cluster_index, "fog_datum": fog_datum, "normal": normal,
            "background_index": struct.unpack_from("<h", image, base + 4)[0],
            "environment_index": struct.unpack_from("<h", image, base + 6)[0],
        }
        break
    if chain is None:
        return {
            "kind": "empty", "cluster": -1, "background": -1, "environment": -1,
            "fog_environment": -1, "fog_datum": -1, "position": (0.0, 0.0, 0.0),
            "background_count": background_count, "environment_count": environment_count,
            "cluster_count": cluster_count, "reason": "no-fog-free-or-fog-plane",
        }
    fog_body, _fog = tag_bytes(loaded, chain["fog_datum"], 276, "fog ")
    fog_background = struct.unpack_from("<i", fog_body, 0x100)[0]
    fog_environment = struct.unpack_from("<i", fog_body, 0x110)[0]
    best = -32768
    selected_background = -1
    selected_environment = -1
    winner = "none"
    if fog_environment != -1:
        priority, _body = environment_priority(loaded, fog_environment)
        if priority > best:
            best = priority
            selected_environment = fog_environment
            selected_background = fog_background
            winner = "fog"
    environment_index = chain["environment_index"]
    if 0 <= environment_index < environment_count:
        environment_tag = struct.unpack_from(
            "<i", image, environments + environment_index * 0x50 + 0x2C)[0]
        if environment_tag != -1:
            priority, _body = environment_priority(loaded, environment_tag)
            if priority > best:
                selected_environment = environment_tag
                background_index = chain["background_index"]
                selected_background = -1
                if 0 <= background_index < background_count:
                    selected_background = struct.unpack_from(
                        "<i", image, backgrounds + background_index * 0x74 + 0x2C)[0]
                winner = "cluster"
    normal = chain["normal"]
    norm_squared = sum(component * component for component in normal[:3])
    if norm_squared <= 0:
        raise AssertionError(f"{loaded['name']} fog plane normal is zero")
    scale = (abs(normal[3]) + 1000.0) / norm_squared
    position = tuple(ff(-normal[axis] * scale) for axis in range(3))
    if sum(normal[axis] * position[axis] for axis in range(3)) + normal[3] >= 0:
        raise AssertionError(f"{loaded['name']} fog point is not inside the region")
    return {
        "kind": "fog-plane", "cluster": chain["cluster"],
        "background": selected_background, "environment": selected_environment,
        "fog_environment": fog_environment, "fog_datum": chain["fog_datum"],
        "fog_winner": winner, "position": position,
        "background_count": background_count, "environment_count": environment_count,
        "cluster_count": cluster_count,
    }


def sound_tree(loaded, datum, classes):
    body, entry = tag_bytes(loaded, datum, 164, "snd!")
    count, address = struct.unpack_from("<iI", body, 152)
    ranges = block_bytes(loaded, count, address, 72, "pitch-ranges")
    range_rows = []
    for index in range(count):
        range_body = ranges[index * 72:(index + 1) * 72]
        perm_count, perm_address = struct.unpack_from("<iI", range_body, 60)
        perms = block_bytes(loaded, perm_count, perm_address, 124, "permutations")
        range_rows.append({"body": range_body, "perms": perms, "count": perm_count})
    sound_class = struct.unpack_from("<h", body, 4)[0]
    playable = bool(count) and bool(range_rows and range_rows[0]["count"]) and (
        0 <= sound_class < len(classes) and classes[sound_class]["name"] and
        not classes[sound_class]["disabled"])
    return {"datum": datum, "body": body, "ranges": range_rows, "path": entry.path,
            "class": sound_class, "playable": playable}


def collect_case(loaded, selected, classes):
    case = {"selected": selected, "sounds": {}, "loop": None, "environment": None,
            "playable": False}
    if selected["environment"] != -1:
        body, entry = tag_bytes(loaded, selected["environment"], 72, "snde")
        case["environment"] = {"datum": selected["environment"], "body": body, "path": entry.path}
    if selected["background"] == -1:
        case["empty_reason"] = "background-tag-none"
        return case
    loop_body, loop_entry = tag_bytes(loaded, selected["background"], 84, "lsnd")
    track_count, track_address = struct.unpack_from("<iI", loop_body, 60)
    detail_count, detail_address = struct.unpack_from("<iI", loop_body, 72)
    tracks = block_bytes(loaded, track_count, track_address, 160, "tracks")
    details = block_bytes(loaded, detail_count, detail_address, 104, "details")
    referenced = []
    for index in range(track_count):
        track = tracks[index * 160:(index + 1) * 160]
        for ref_offset in (48, 64, 80, 128, 144):
            datum = reference_index(track, ref_offset)
            if datum != -1:
                referenced.append(datum)
    sounds = {}
    for datum in referenced:
        if datum not in sounds:
            sounds[datum] = sound_tree(loaded, datum, classes)
    loop_datums = []
    for index in range(track_count):
        track = tracks[index * 160:(index + 1) * 160]
        loop_datums.append(reference_index(track, 64))
    case.update({
        "loop": {"body": loop_body, "tracks": tracks, "details": details,
                 "track_count": track_count, "detail_count": detail_count,
                 "path": loop_entry.path},
        "sounds": sounds,
        "playable": any(sounds[datum]["playable"] for datum in loop_datums if datum in sounds),
    })
    if not case["playable"]:
        case["empty_reason"] = "loop-not-playable"
    return case


def pack_case(cases):
    out = bytearray(b"SRQ1")
    out += struct.pack("<i", len(cases))
    for case in cases:
        selected = case["selected"]
        name = case["loaded_name"].encode("ascii")
        out += struct.pack("<I", len(name)) + name
        out += struct.pack("<iii", selected["background"], selected["environment"],
                           selected["background"])
        out += struct.pack("<3f", *selected["position"])
        has_environment = case["environment"] is not None
        has_loop = case["loop"] is not None and selected["background"] != -1
        out += struct.pack("<ii", int(has_environment), int(has_loop))
        if has_environment:
            body = case["environment"]["body"]
            out += struct.pack("<I", len(body)) + body
        if not has_loop:
            continue
        loop = case["loop"]
        out += struct.pack("<I", len(loop["body"])) + loop["body"]
        out += struct.pack("<ii", loop["track_count"], loop["detail_count"])
        out += loop["tracks"] + loop["details"]
        sounds = list(case["sounds"].values())
        out += struct.pack("<i", len(sounds))
        for sound in sounds:
            out += struct.pack("<iI", sound["datum"], len(sound["body"])) + sound["body"]
            out += struct.pack("<i", len(sound["ranges"]))
            out += b"".join(row["body"] for row in sound["ranges"])
            for row in sound["ranges"]:
                out += struct.pack("<i", row["count"]) + row["perms"]
    return bytes(out)


def parse_drive(text):
    maps = {}
    current = None
    for line in text.splitlines():
        if line.startswith("MAP "):
            current = {"name": line[4:], "records": [], "lines": {}}
            maps[current["name"]] = current
            continue
        if current is None:
            continue
        if line.startswith("RECORD "):
            body, name = line[len("RECORD "):].split(" perm_name=")
            fields = dict(part.split("=", 1) for part in body.split())
            fields["perm_name"] = name.strip()
            current["records"].append(fields)
            continue
        if line == "ENDMAP":
            current = None
            continue
        parts = line.split()
        if len(parts) == 2:
            current["lines"][parts[0]] = parts[1]
    return maps


def fade_for(flags, fade_in, sound_type):
    if sound_type != 2 or (flags & 1) == 0:
        return 1.0
    stop = int(fadd(fmul(fade_in, 1000.0), -1.0))
    stop = max(stop, 0)
    return fdiv(fsub(0.0, -1.0), float(stop - (-1)))


def expected_playback(case, record, classes):
    sound = case["sounds"][int(record["ce_tag"])]
    track_index = int(record["ce_track"])
    track = case["loop"]["tracks"][track_index * 160:(track_index + 1) * 160]
    flags = struct.unpack_from("<I", track, 0)[0]
    track_gain = struct.unpack_from("<f", track, 4)[0]
    fade_in = struct.unpack_from("<f", track, 8)[0]
    sound_type = int(record["ce_type"])
    if sound_type == 1:
        expect_datum = reference_index(track, 48)
    elif sound_type == 2:
        expect_datum = reference_index(track, 64)
    else:
        raise AssertionError(f"unexpected sound type {sound_type}")
    body = sound["body"]
    pitch_bits = int(record["ce_pitch"], 16)
    pitch = struct.unpack("<f", struct.pack("<I", pitch_bits))[0]
    lower, upper = struct.unpack_from("<ff", body, 20)
    if ff(lower) == ff(upper) and pitch_bits != fbits(lower):
        raise AssertionError("pitch left an equal raw bound")
    if ff(lower) != ff(upper) and not (min(lower, upper) - 1e-4 <= pitch <= max(lower, upper) + 1e-4):
        raise AssertionError("pitch left the raw bounds")
    range_index = int(record["ce_range"])
    perm_index = int(record["ce_perm"])
    row = sound["ranges"][range_index]
    if not 0 <= perm_index < row["count"]:
        raise AssertionError("permutation index outside the raw range")
    perm = row["perms"][perm_index * 124:(perm_index + 1) * 124]
    playback = struct.unpack_from("<f", row["body"], 48)[0]
    gain_modifier = struct.unpack_from("<f", body, 40)[0]
    zero_gain = struct.unpack_from("<f", body, 64)[0]
    one_gain = struct.unpack_from("<f", body, 88)[0]
    zero_pitch = struct.unpack_from("<f", body, 68)[0]
    one_pitch = struct.unpack_from("<f", body, 92)[0]
    fade = fade_for(flags, fade_in, sound_type)
    scaled_gain = scale_value(gain_modifier, zero_gain, one_gain, 1.0)
    gain = fmul(fmul(fmul(fmul(1.0, track_gain), scaled_gain), 1.0), fade)
    gain = fmul(gain, struct.unpack_from("<f", perm, 36)[0])
    prop_pitch = fmul(scale_value(pitch, zero_pitch, one_pitch, 1.0), playback)
    minimum_bits = struct.unpack_from("<I", body, 8)[0]
    if minimum_bits == 0:
        minimum_bits = classes[sound["class"]]["minimum"]
    return {
        "datum": expect_datum,
        "gain": fbits(gain),
        "pitch": fbits(prop_pitch),
        "minimum": minimum_bits,
        "maximum": FLT_MAX_BITS,
        "inner": struct.unpack_from("<I", body, 28)[0],
        "outer": struct.unpack_from("<I", body, 32)[0],
        "outer_gain": struct.unpack_from("<I", body, 36)[0],
        "reverb": classes[sound["class"]]["wet"],
        "perm_gain": struct.unpack_from("<I", perm, 36)[0],
        "perm_name": perm[:32].hex(),
        "fade_flags": flags,
    }


class SoundRequestSeamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = parse_classes((HCU / "source/sound/sound_classes.c").read_text())
        cls.preferences = (HCU / "source/sound/sound_preferences.c").read_text()
        cls.manager = (HCU / "source/sound/sound_manager.c").read_text()
        cls.binaries = compile_binaries()
        cls.schema = run_checked(cls.binaries["soundreq-drive"], ["--schema"], "schema.log")
        cls.ps2 = run_checked(cls.binaries["soundreq-ps2"], [], "ps2.log")
        cases = []
        cls.raw = {}
        for name in MP_MAPS:
            loaded = load_map(name)
            selected = select_background(loaded)
            case = collect_case(loaded, selected, cls.classes)
            case["loaded_name"] = name
            case["bsp_sha256"] = loaded["bsp_sha256"]
            case["map_sha256"] = loaded["sha256"]
            cases.append(case)
            cls.raw[name] = case
        case_path = OUT / "cases.bin"
        case_path.write_bytes(pack_case(cases))
        cls.drive = run_checked(cls.binaries["soundreq-drive"], ["--drive", str(case_path)],
                                "drive.log")
        cls.driven = parse_drive(cls.drive)

    def test_schema_matches_compiled_layout(self):
        values = schema_values(self.schema)
        expected = {
            "sizeof_sound_definition": 164, "off_sound_class": 4, "off_minimum_distance": 8,
            "off_random_pitch_bounds": 20, "off_inner_cone": 28, "off_gain_modifier": 40,
            "off_zero_gain": 64, "off_zero_pitch": 68, "off_one_gain": 88, "off_one_pitch": 92,
            "off_encoding": 108, "off_compression": 110, "off_pitch_ranges": 152,
            "sizeof_pitch_range": 72, "off_playback_rate": 48, "off_permutations": 60,
            "sizeof_permutation": 124, "off_permutation_gain": 36, "sizeof_looping": 84,
            "off_tracks": 60, "off_details": 72, "sizeof_track": 160, "off_fade_in": 8,
            "off_loop_sound": 64, "sizeof_environment": 72, "off_environment_priority": 4,
            "sizeof_location": 44, "sizeof_properties": 32, "sizeof_bsp": 648,
            "off_clusters": 308, "off_background_palette": 508, "off_environment_palette": 520,
            "off_world_bounds": 200, "sizeof_cluster": 104, "sizeof_fog": 276,
            "off_fog_background": 256, "off_fog_environment": 260,
        }
        for key, value in expected.items():
            self.assertEqual(values[key], value, key)
        live = {}
        for line in self.schema.splitlines():
            if not line.startswith("CLASS "):
                continue
            parts = line.split()
            index = int(parts[1])
            if parts[2] == "empty":
                live[index] = None
            else:
                live[index] = {item.split("=")[0]: int(item.split("=")[1], 16)
                               for item in parts[2:] if "=" in item and item.split("=")[1][:1] in "0123456789abcdef"}
        for index, row in enumerate(self.classes):
            if not row["name"]:
                self.assertIsNone(live[index], index)
                continue
            self.assertEqual(live[index]["wet"], row["wet"], row["name"])
            self.assertEqual(live[index]["min"], row["minimum"], row["name"])

    def test_ps2_preferences_never_reach_the_platform(self):
        lines = dict(line.split(None, 1) for line in self.ps2.splitlines() if " " in line)
        self.assertEqual(lines["preferences_platform"], "-1")
        self.assertEqual(lines["sound_is_active"], "0")
        self.assertEqual(lines["cache_new"], "1")
        self.assertEqual(lines["recorder_initialize"], "0")
        self.assertEqual(lines["recorder_queue"], "0")
        self.assertEqual(lines["recorder_properties"], "0")
        self.assertEqual(lines["recorder_location"], "0")
        self.assertEqual(lines["recorder_listener"], "0")
        self.assertEqual(lines["platform_definition_null"], "1")
        self.assertEqual(lines["platform_slot1_null"], "1")
        for issue in ("ps2-platform-disabled", "initialize-before-vtable",
                      "platform-slot-1-null", "queue-args-lack-tag-owner-position"):
            self.assertIn(f"ISSUE {issue}", self.ps2)

    def test_port_source_has_no_request_adapter(self):
        preference_line, _text = line_matching(self.preferences, "-1,")
        self.assertGreater(preference_line, 0)
        self.assertIn("#ifdef HALO_PS2", self.preferences)
        return_line, _text = line_matching(
            self.manager, "if (platform_code < 0 || platform_code >= 2)")
        self.assertGreater(return_line, 0)
        slot_line, _text = line_matching(self.manager, "\tNULL,")
        self.assertIn("&platform_sound_dsound,", self.manager)
        queue = self.manager.split("queue_sound_to_channel(", 1)[1].split(");", 1)[0]
        self.assertNotIn("definition_index", queue)
        self.assertNotIn("position", queue)
        self.assertNotIn("source_identifier", queue)
        edge = (HCU / "port/ps2/src/ps2_edge.c").read_text()
        cache = (HCU / "port/ps2/src/ps2_sound_cache.c").read_text()
        memory = (HCU / "port/ps2/src/ps2_memory.c").read_text()
        self.assertIn("return (long)0x80004005;", edge)
        self.assertIn("return sound != NULL;", cache)
        self.assertIn("#define PS2_SOUND_BYTES (512 * 1024)", memory)
        port = HCU / "port/ps2"
        for path in port.rglob("*"):
            if path.suffix not in {".c", ".h"}:
                continue
            text = path.read_text(errors="replace")
            self.assertNotIn("struct sound_platform_definition", text, path)
            self.assertNotIn("queue_sound_to_channel", text, path)
        symbols = subprocess.check_output(["nm", "-g", str(self.binaries["soundreq-drive"])],
                                           text=True)
        self.assertNotIn("collision_test_vector", symbols)
        self.assertNotIn("scenario_get_sound_environment", symbols)

    def test_contract_record_fits_audio_region(self):
        self.assertIn("{ 9, 46, 9, 9 }", self.preferences)
        for text in (self.ps2, self.drive):
            lines = dict(line.split(None, 1) for line in text.splitlines()
                         if line.startswith(("contract_", "virtual_", "max_", "audio_")))
            self.assertEqual(lines["virtual_counts"], "9 46 9 9")
            self.assertEqual(int(lines["virtual_sum"]), 73)
            self.assertEqual(int(lines["audio_region"]), AUDIO_REGION)
            self.assertEqual(lines["contract_fit"], "1")
            self.assertLessEqual(int(lines["max_bytes"]), AUDIO_REGION)
            self.assertEqual(int(lines["contract_size"]) * 256, int(lines["max_bytes"]))
            self.assertEqual(int(lines["contract_size"]) * 73, int(lines["virtual_bytes"]))

    def test_each_stock_map_request_record(self):
        self.assertEqual(set(self.driven), set(MP_MAPS))
        for name in MP_MAPS:
            with self.subTest(map=name):
                case = self.raw[name]
                driven = self.driven[name]
                selected = case["selected"]
                self.assertEqual(int(driven["lines"]["background"]), selected["background"])
                self.assertEqual(int(driven["lines"]["owner"]), selected["background"])
                self.assertEqual(driven["lines"]["feedback"], "1")
                self.assertEqual(driven["lines"]["published_bsp"], "0")
                self.assertEqual(driven["lines"]["collision_depth"], "0")
                self.assertEqual(driven["lines"]["location_calls"], "0")
                self.assertEqual(driven["lines"]["listener_calls"], "0")
                self.assertEqual(driven["lines"]["obstruction_calls"], "0")
                if selected["background"] == -1 or case["loop"] is None:
                    self.assertEqual(driven["lines"]["empty"], "1")
                    self.assertEqual(driven["lines"]["requests"], "0")
                    self.assertIn(driven["lines"]["reason"],
                                  {"background-tag-none", "loop-definition-none"})
                    continue
                if not case["playable"]:
                    self.assertEqual(driven["lines"]["requests"], "0", driven["lines"])
                    self.assertEqual(driven["lines"]["empty"], "1")
                    continue
                self.assertGreater(int(driven["lines"]["requests"]), 0, driven["lines"])
                self.assertEqual(driven["lines"]["poison_isolated"], "1")
                self.assertEqual(driven["lines"]["stop_calls"], "0")
                self.assertEqual(driven["lines"]["stereo_positioned"], "0")
                self.assertEqual(driven["lines"]["stereo_unexpected"], "0")
                stereo_records = 0
                for record in driven["records"]:
                    encoding = struct.unpack_from(
                        "<h", case["sounds"][int(record["ce_tag"])]["body"], 108)[0]
                    if encoding != 0:
                        stereo_records += 1
                self.assertEqual(int(driven["lines"]["stereo_calls"]), stereo_records)
                self.assertIn("PLATFORM_OMITS tag owner position",
                              "\n".join(self.drive.splitlines()))
                position_bits = [fbits(component) for component in selected["position"]]
                for record in driven["records"]:
                    self.assertEqual(int(record["ce_owner"]), selected["background"])
                    expected = expected_playback(case, record, self.classes)
                    self.assertEqual(int(record["ce_tag"]), expected["datum"])
                    self.assertEqual(int(record["plat_gain"], 16), expected["gain"])
                    self.assertEqual(int(record["plat_pitch"], 16), expected["pitch"])
                    self.assertEqual(int(record["plat_min"], 16), expected["minimum"])
                    self.assertEqual(int(record["plat_max"], 16), expected["maximum"])
                    self.assertEqual(int(record["plat_in"], 16), expected["inner"])
                    self.assertEqual(int(record["plat_out"], 16), expected["outer"])
                    self.assertEqual(int(record["plat_outgain"], 16), expected["outer_gain"])
                    self.assertEqual(int(record["plat_reverb"], 16), expected["reverb"])
                    self.assertEqual(int(record["perm_gain"], 16), expected["perm_gain"])
                    self.assertEqual(record["perm_name"], expected["perm_name"])
                    got_position = [int(part, 16) for part in record["ce_pos"].split(",")]
                    self.assertEqual(got_position, position_bits)

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "driven"):
            return
        issues = source_issues()
        rows = []
        for name in MP_MAPS:
            case = cls.raw[name]
            driven = cls.driven[name]
            records = driven["records"]
            gain = records[0]["plat_gain"] if records else "-"
            rows.append(
                f"| {name} | {case['selected']['kind']} | {case['selected']['cluster']} | "
                f"{case['selected']['background_count']}/{case['selected']['environment_count']} | "
                f"{driven['lines'].get('requests', '?')} | {driven['lines'].get('reason', '?')} | "
                f"{gain} | {driven['lines'].get('feedback', '?')} |")
        files = [
            ROOT / "tests/test_hcu_mp_sound_request.py",
            ROOT / "tests/hcu_mp_sound_request_bridge.c",
            ROOT / "tests/soundreq_host_stubs.c",
            ROOT / "tests/soundreq_host_prefix.h",
            ROOT / "tests/soundreq_host_shim/xbdm.h",
            OUT / "soundreq-drive",
            OUT / "soundreq-ps2",
            OUT / "schema.log",
            OUT / "ps2.log",
            OUT / "drive.log",
        ]
        hashes = "\n".join(f"- `{path.relative_to(ROOT)}` `{sha256(path)}`" for path in files)
        report = "\n".join([
            "# soundreq",
            "",
            "Status: ISSUES",
            "",
            "Host ILP32 characterization of the CE sound request seam. No PCSX2, GS, VU, or SPU2 output is claimed. The recorder is test-only and is not a port backend.",
            "",
            "## Issues",
            "",
            *issues,
            "",
            "The 524,288-byte figure is `PS2_SOUND_BYTES` in `port/ps2/src/ps2_memory.c`. A contract record built from the real CE tag datum, owner, channel, `sound_location`, obstruction, occlusion, and `platform_sound_channel_properties` is 96 bytes. 96 x 73 virtual channels = 7,008. 96 x 256 = 24,576. Both fit. That region is the sample-cache budget; this run does not place requests there.",
            "",
            "## Maps",
            "",
            "| map | selector | cluster | bg/env palettes | requests | reason | first gain bits | feedback |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
            *rows,
            "",
            "Raw map SHA-256 values matched the stock pins. BSP bytes were read from the decompressed map, not from relocated CE memory. Published BSP bytes and collision depth stayed 0 because this fixture does not publish a BSP or call collision.",
            "",
            "Reproduction: `python3 -m pytest -q tests/test_hcu_mp_sound_request.py`",
            "",
            "## SHA-256",
            "",
            hashes,
            "",
        ])
        (OUT / "report.md").write_text(report)


def source_issues():
    preferences = (HCU / "source/sound/sound_preferences.c").read_text()
    manager = (HCU / "source/sound/sound_manager.c").read_text()
    edge = (HCU / "port/ps2/src/ps2_edge.c").read_text()
    cache = (HCU / "port/ps2/src/ps2_sound_cache.c").read_text()
    found = [
        ("source/sound/sound_preferences.c",) + line_matching(preferences, "-1,"),
        ("source/sound/sound_manager.c",) + line_matching(
            manager, "if (platform_code < 0 || platform_code >= 2)"),
        ("source/sound/sound_manager.c",) + line_matching(manager, "\tNULL,"),
        ("source/sound/sound_manager.c",) + line_matching(
            manager, "platform_definition->queue_sound_to_channel("),
        ("port/ps2/src/ps2_edge.c",) + line_matching(edge, "return (long)0x80004005;"),
        ("port/ps2/src/ps2_sound_cache.c",) + line_matching(cache, "return sound != NULL;"),
    ]
    text = []
    descriptions = [
        "HALO_PS2 sets the sound platform to -1. There is no SPU2 request backend.",
        "`sound_initialize` returns before selecting a platform, creating sound datums, or calling `initialize`.",
        "`platform_definitions[1]` is NULL. Only the Xbox DirectSound slot is filled, and the PS2 build never selects it.",
        "`queue_sound_to_channel` receives a channel index and a permutation pointer. Tag datum, owner, and position are not arguments. `set_channel_location` is the later position call and did not run for these unspatialized background sounds.",
        "`DirectSoundCreate` returns `0x80004005` and clears the device pointer.",
        "`_sound_cache_sound_request` ignores block, load, and reference and returns whether the permutation pointer is non-NULL. That is not a playback request record.",
    ]
    for (path, number, line), description in zip(found, descriptions):
        text.append(f"- `{path}:{number}` `{line}` — {description}")
    text.append("- No file under `port/ps2` defines `sound_platform_definition` or `queue_sound_to_channel`.")
    stereo_number, stereo_line = line_matching(
        (HCU / "source/sound/sound_manager.c").read_text(),
        "dsound_port_set_channel_stereo_position(channel_index, FALSE")
    text.append(
        f"- `source/sound/sound_manager.c:{stereo_number}` `{stereo_line}` — "
        "unspatialized stereo channels call the DirectSound helper with positioned false and zero pan, distance, and minimum distance. The source position is not an argument.")
    return text


if __name__ == "__main__":
    unittest.main()
