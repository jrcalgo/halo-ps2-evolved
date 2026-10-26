"""Run CE's cluster lens-flare selector on production-relocated BSP pointers.

The raw-source fixture records marker indices from Xbox BSP bytes copied into
host arrays. This fixture materializes each stock multiplayer map's CBSP with
ps2_cache_mount_cbsp_for_extent and cache_file_read (ps2_cbsp_materialize),
then calls the extracted CE function on that published structure. The expected
submission sequence is read again from the raw Xbox map, not from the
relocated image.
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
LIGHTS = HCU / "source/rasterizer/rasterizer_lights.c"
OUT = ROOT / "build/step7-swarm/lensflare"
MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
EMPTY_MAPS = (
    "beavercreek", "bloodgulch", "carousel", "chillout", "hangemhigh",
    "longest", "prisoner", "ratrace", "sidewinder", "wizard",
)
PINNED_SUBMISSIONS = {"boardingaction": 207, "damnation": 22, "putput": 892}
SOURCE_SHA256 = {
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
PACKAGE_SHA256 = {
    "beavercreek": "4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc",
    "bloodgulch": "ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011",
    "boardingaction": "2c12e7c0cf555698b837397666b1f343a6864fe16deeffb0b0d4a007e869acd0",
    "carousel": "e24191ed1e660dfb3c9c9bcd88abcff61c366690f6d903f3b0622eb2c2e751b4",
    "chillout": "727abc7401a530892f1136f082a6254544915e0d85f2a068f63d9530189b1bf0",
    "damnation": "ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d",
    "hangemhigh": "1e2a4df7a5ba17d0742bd30484fcfe63db011e6c47a87ac0f2d06ac6f5cab58f",
    "longest": "6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b",
    "prisoner": "3bb10f06c785da93fe0f7257be9f06519b7ccb6c155801a7a04a5e6d56352136",
    "putput": "6d66e4ecf9c51b3ae417d85356de9ff66c14bc9fc19dd4a2bd2a2954f6b4f3bd",
    "ratrace": "a735d4a5bef86cc7277ae888a1ef9da25f28f0ab6e45dff010da53dc41e685da",
    "sidewinder": "968ab65ea7ae6fbd15925ed28eb0f8eafc267c78f53150b59b4cc1dea2d017f5",
    "wizard": "00bf468d4d8c96e234ef21e5bfb59b410cac7c3e8c9f4f848ea20fbfacf01c57",
}
# Pin-verified package root (env var, historical /tmp dir, then
# build/mp-fog-selection-*/assets/maps); None when no verified set exists.
PACKAGES = None
# CE rasterizer_lens_flare_submit_for_cluster refuses marker indices at or
# above SHORT_MAX+1-MAXIMUM_QUEUED_LENS_FLARES. That is the sprite-request bound.
SPRITE_BOUND = 32767 + 1 - 8
FRAME_BOUND = 1024
RECORD_PREFIX = struct.Struct("<HIII4BIIIIiI")
RECORD_NAME_LEN = struct.Struct("<H")
REC_RE = re.compile(
    r"REC c=([0-9a-f]+) m=([0-9a-f]+) x=([0-9a-f]+) y=([0-9a-f]+) z=([0-9a-f]+) "
    r"di=([0-9a-f]+) dj=([0-9a-f]+) dk=([0-9a-f]+) "
    r"dfi=([0-9a-f]+) dfj=([0-9a-f]+) dfk=([0-9a-f]+) "
    r"pal=([0-9a-f]+) group=([0-9a-f]+) nlen=([0-9a-f]+) datum=([0-9a-f]+) "
    r"name=([0-9a-f]*)$")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import bsp, hp2, mapinfo, tagindex  # noqa: E402
from host_abi32 import flags  # noqa: E402
from hcu_package_root import resolve_package_dir  # noqa: E402
import cbsp  # noqa: E402
import ctag  # noqa: E402
import hmap  # noqa: E402
from tools.ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def extract_function(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated CE function: {marker}")


def direction_bits(byte):
    signed = byte - 256 if byte >= 128 else byte
    scale = struct.unpack("<f", struct.pack("<f", 1.0 / 127.0))[0]
    return struct.unpack("<I", struct.pack("<f", float(signed) * scale))[0]


def pack_record(record):
    name = record["name"]
    name_length = record["name_length"]
    if name_length < 0:
        name_length += 1 << 32
    prefix = RECORD_PREFIX.pack(
        record["marker"] & 0xFFFF,
        record["x"] & 0xFFFFFFFF,
        record["y"] & 0xFFFFFFFF,
        record["z"] & 0xFFFFFFFF,
        record["di"] & 0xFF,
        record["dj"] & 0xFF,
        record["dk"] & 0xFF,
        record["palette"] & 0xFF,
        record["dfi"] & 0xFFFFFFFF,
        record["dfj"] & 0xFFFFFFFF,
        record["dfk"] & 0xFFFFFFFF,
        record["group"] & 0xFFFFFFFF,
        name_length & 0xFFFFFFFF,
        record["datum"] & 0xFFFFFFFF,
    )
    return prefix + RECORD_NAME_LEN.pack(len(name) & 0xFFFF) + name


def raw_oracle(map_name):
    """Submission sequence from the decompressed Xbox map, not relocated memory."""
    path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    mapped = path.read_bytes()
    digest = sha256_bytes(mapped)
    if digest != SOURCE_SHA256[map_name]:
        raise AssertionError(f"{map_name} source map changed: {digest}")
    index = tagindex.TagIndex.read(path)
    region, _tag_base, _source = read_xbox_tag_region(path)
    locations = bsp.locate(index, region, mapinfo.read_header(path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{map_name}: expected one stock-MP BSP")
    location = locations[0]
    image = mapped[location.file_offset:location.file_offset + location.size]
    if len(image) != location.size:
        raise AssertionError(f"{map_name}: truncated raw BSP")
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError(f"{map_name}: BSP root leaves the raw image")

    def rows(field, stride, label):
        count, address = struct.unpack_from("<iI", image, root + field)
        data = address - location.address if address else 0
        if count < 0 or data < 0 or data + count * stride > len(image):
            raise AssertionError(f"{map_name}: invalid raw {label} extent")
        return [image[data + item * stride:data + (item + 1) * stride]
                for item in range(count)]

    flares = rows(0x11C, 0x10, "lens flare palette")
    markers = rows(0x11C + 12, 0x10, "lens flare markers")
    clusters = rows(0x11C + 24, 0x68, "clusters")
    tags = {entry.tag_id: entry for entry in index.entries}
    palette = []
    for flare in flares:
        group, _name_pointer, name_length, datum = struct.unpack_from("<IiiI", flare, 0)
        tag = tags.get(datum)
        if tag is None or tag.group != "lens":
            raise AssertionError(f"{map_name}: palette datum {datum:#x} is not a lens tag")
        palette.append({
            "group": group,
            "name_length": name_length,
            "datum": datum & 0xFFFFFFFF,
            "name": tag.path.encode("latin1"),
        })
    cap = min(len(markers), SPRITE_BOUND)
    records = []
    errors = 0
    per_cluster = []
    for cluster_index, cluster in enumerate(clusters):
        first, count = struct.unpack_from("<HH", cluster, 0x40)
        produced = 0
        for step in range(count):
            marker_index = first + step
            if marker_index >= cap:
                errors += 1
                break
            marker = markers[marker_index]
            palette_index = marker[15]
            if palette_index >= len(flares):
                errors += 1
                continue
            flare = palette[palette_index]
            x_bits, y_bits, z_bits = struct.unpack_from("<III", marker, 0)
            records.append({
                "cluster": cluster_index,
                "marker": marker_index,
                "x": x_bits,
                "y": y_bits,
                "z": z_bits,
                "di": marker[12],
                "dj": marker[13],
                "dk": marker[14],
                "palette": palette_index,
                "dfi": direction_bits(marker[12]),
                "dfj": direction_bits(marker[13]),
                "dfk": direction_bits(marker[14]),
                "group": flare["group"],
                "name_length": flare["name_length"],
                "datum": flare["datum"],
                "name": flare["name"],
            })
            produced += 1
        per_cluster.append(produced)
    return {
        "map": map_name,
        "source_sha256": digest,
        "clusters": len(clusters),
        "markers": len(markers),
        "flares": len(flares),
        "errors": errors,
        "records": records,
        "per_cluster": per_cluster,
    }


def package_inputs(map_name, payload_dir):
    global PACKAGES
    if PACKAGES is None:
        PACKAGES = resolve_package_dir(PACKAGE_SHA256)
    if PACKAGES is None:
        raise unittest.SkipTest(
            "no pin-verified retail HP2 package set: set HALO_HCU_M2_PACKAGE_ROOT or keep "
            "build/mp-fog-selection-*/assets/maps/*.hp2 matching PACKAGE_SHA256")
    package_path = PACKAGES / f"{map_name}.hp2"
    package = package_path.read_bytes()
    digest = sha256_bytes(package)
    if digest != PACKAGE_SHA256[map_name]:
        raise AssertionError(f"{map_name} package changed: {digest}")
    parsed = hp2.parse(package)
    identity = hmap.decode(parsed.read("HMAP"))
    if identity.map_name != map_name:
        raise AssertionError(f"{map_name}: HMAP name is {identity.map_name}")
    catalog = cbsp.decode_catalog(parsed.read("CBIX"),
                                  expected_file_length=identity.file_length)
    if tuple(entry.section_tag for entry in catalog) != ("B000",):
        raise AssertionError(f"{map_name}: stock MP package does not have one CBSP")
    entry = catalog[0]
    ctag_wire = parsed.read("CTAG")
    cbsp_wire = parsed.read("B000")
    decoded_tags = ctag.decode(ctag_wire, max_image_size=16 * 1024 * 1024)
    decoded_bsp = cbsp.decode(cbsp_wire, max_image_size=8 * 1024 * 1024)
    if (decoded_bsp.source_file_offset, decoded_bsp.source_file_size) != (
            entry.file_offset, entry.file_size):
        raise AssertionError(f"{map_name}: CBIX extent does not match CBSP")
    if decoded_bsp.source_file_size != len(decoded_bsp.image):
        raise AssertionError(f"{map_name}: CBSP source size is not the image size")
    ctag_path = payload_dir / f"{map_name}.ctag"
    cbsp_path = payload_dir / f"{map_name}.cbsp"
    ctag_path.write_bytes(ctag_wire)
    cbsp_path.write_bytes(cbsp_wire)
    return {
        "ctag": ctag_path,
        "cbsp": cbsp_path,
        "bsp_offset": entry.file_offset,
        "bsp_size": entry.file_size,
        "tag_offset": identity.tag_data_offset,
        "tag_image_size": len(decoded_tags.image),
        "file_length": identity.file_length,
        "package_sha256": digest,
    }


def hex_u32(text):
    return int(text, 16) & 0xFFFFFFFF


def signed_from_hex(text):
    value = hex_u32(text)
    return value - (1 << 32) if value >= 0x80000000 else value


def parse_output(text):
    observed = {}
    current = None
    for line in text.splitlines():
        if line.startswith("MAP "):
            fields = dict(part.split("=", 1) for part in line.split()[1:])
            current = fields["name"]
            observed[current] = fields
            observed[current]["records"] = []
        elif line.startswith("REC "):
            match = REC_RE.match(line)
            if not match or current is None:
                raise AssertionError(f"unparsed selector record: {line}")
            keys = ("cluster", "marker", "x", "y", "z", "di", "dj", "dk",
                    "dfi", "dfj", "dfk", "palette", "group", "name_length", "datum")
            values = [hex_u32(item) for item in match.groups()[:-1]]
            record = dict(zip(keys, values))
            record["name_length"] = signed_from_hex(match.group(14))
            record["name"] = bytes.fromhex(match.group(16))
            observed[current]["records"].append(record)
        elif line.startswith("ENDMAP "):
            if line.split()[1] != current:
                raise AssertionError(f"map terminator mismatch: {line}")
            current = None
        elif line.startswith("RESULT "):
            if current is not None:
                raise AssertionError("result arrived inside a map")
    if set(observed) != set(MAPS):
        raise AssertionError(f"selector maps were {sorted(observed)}")
    return observed


def sprite_digest(records):
    return sha256_bytes(b"".join(pack_record(record) for record in records))


def total_digest(records_by_map):
    blob = bytearray()
    for name in MAPS:
        records = records_by_map[name]
        blob += struct.pack("<H", len(records))
        for record in records:
            blob += pack_record(record)
    return sha256_bytes(blob)


def selector_body():
    render = (HCU / "source/render/render.h").read_text()
    rasterizer = (HCU / "source/rasterizer/rasterizer.h").read_text()
    cseries = (HCU / "source/cseries/cseries.h").read_text()
    if "MAXIMUM_QUEUED_LENS_FLARES = 8" not in render:
        raise AssertionError("CE queued lens-flare bound changed")
    if "MAXIMUM_LENS_FLARES_PER_FRAME = 1024" not in rasterizer:
        raise AssertionError("CE per-frame lens-flare bound changed")
    if "SHORT_MAX = 32767" not in cseries:
        raise AssertionError("CE SHORT_MAX changed")
    if RECORD_PREFIX.size != 42:
        raise AssertionError("sprite record prefix size drifted")
    source = LIGHTS.read_text()
    if source.count("void rasterizer_lens_flare_submit_for_cluster(") != 1:
        raise AssertionError("CE selector is not a single definition")
    body = extract_function(source, "void rasterizer_lens_flare_submit_for_cluster(")
    if body.count("rasterizer_debug_options.draw_lens_flares") != 1:
        raise AssertionError("CE selector debug predicate changed")
    body = body.replace(
        "rasterizer_debug_options.draw_lens_flares",
        "lensflare_draw_lens_flares()",
        1,
    )
    required = (
        "SHORT_MAX+1-MAXIMUM_QUEUED_LENS_FLARES",
        "marker->lens_flare_index>=structure_bsp->lens_flares.count",
        "marker->i_direction*(1.0f/127.0f)",
        "lens_flare_definition_get(structure_lens_flare->lens_flare.index)",
        "parameters.position= marker->position",
        "parameters.lens_flare_index= (short)structure_lens_flare_marker_index",
    )
    for snippet in required:
        if snippet not in body:
            raise AssertionError(f"extracted selector lost {snippet}")
    return body


def compile_harness(selector_path):
    executable = OUT / "lensflare_relocated"
    command = [
        "gcc", *flags(), "-std=gnu99", "-fno-strict-aliasing", "-fwrapv", "-O2",
        "-I" + str(ROOT / "tests"),
        "-I" + str(ROOT / "tests/hcu_ps2_cache_shim"),
        "-I" + str(HCU / "port/ps2/include"),
        "-I" + str(ROOT / "src"),
        str(ROOT / "tests/lensflare_relocated_main.c"),
        str(selector_path),
        str(HCU / "port/ps2/src/ps2_cache.c"),
        str(HCU / "port/ps2/src/ps2_ctag.c"),
        str(HCU / "port/ps2/src/ps2_cbsp.c"),
        str(ROOT / "src/stream/sha256.c"),
        "-o", str(executable),
    ]
    built = subprocess.run(command, capture_output=True, text=True)
    if built.returncode != 0:
        raise AssertionError(built.stdout + built.stderr)
    return executable, command


def write_report(status, rows, total_count, total_hash, problem):
    lines = [
        "# Step 7 swarm — relocated lens-flare selector",
        "",
        f"Status: **{status}**",
        "",
        "CE `rasterizer_lens_flare_submit_for_cluster()` was extracted from",
        "`source/rasterizer/rasterizer_lights.c` and run on each stock multiplayer",
        "map after `ps2_cache_mount_cbsp_for_extent` / `cache_file_read`",
        "(`ps2_cbsp_materialize`). Expected marker index, position, scaled direction,",
        "and lens-flare tag come from the raw Xbox BSP and tag index.",
        "",
        f"Sprite-request bound: `{SPRITE_BOUND}` "
        "(`SHORT_MAX+1-MAXIMUM_QUEUED_LENS_FLARES`). "
        f"Per-cluster submissions also fit `{FRAME_BOUND}` "
        "(`MAXIMUM_LENS_FLARES_PER_FRAME`). "
        f"Inventory count `{total_count}`, digest `{total_hash}`.",
        "",
        "| Map | Clusters | Markers | Flares | Calls | Submissions | Empty | Sprite SHA-256 |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['map']} | {row['clusters']} | {row['markers']} | {row['flares']} | "
            f"{row['calls']} | {row['submissions']} | {row['empty']} | `{row['sprite']}` |"
        )
    lines.extend([
        "",
        "The ten maps other than Boarding Action, Damnation, and Putput have raw",
        "palette and marker counts of zero and submit nothing. Disabled and screenshot",
        "passes submit nothing further. Published BSP and tag-cache bytes, and the",
        "collision-user depth sentinel, are unchanged after submission.",
        "",
        "No VU1, GS, or PCSX2 output is claimed. `normalize3d`, `perpendicular3d`,",
        "and `compress_real_vector3d_to_int32_clamp` are host stubs. The compared",
        "direction is the scaled marker component the real selector passes into that",
        "math. `lens_flare_definition_get` records the tag datum and does not load",
        "the definition body. Host caches are 16 MiB (tags) and 8 MiB (BSP), which",
        "is not a PlayStation 2 arena measurement. The collision-user globals share",
        "CE's names but this binary does not link `collision_usage.c`.",
        "",
    ])
    if problem:
        lines.extend(["Failure:", "", "```", problem, "```", ""])
    (OUT / "report.md").write_text("\n".join(lines))


class RelocatedLensFlareTest(unittest.TestCase):
    def test_relocated_submissions_match_raw_oracle(self):
        self.assertEqual(RECORD_PREFIX.size, 42)
        self.assertEqual(SPRITE_BOUND, 32760)
        rows = []
        status = "ISSUES"
        problem = ""
        total_count = 0
        total_hash = ""
        try:
            OUT.mkdir(parents=True, exist_ok=True)
            payload_dir = OUT / "payloads"
            payload_dir.mkdir(exist_ok=True)
            body = selector_body()
            selector_path = OUT / "lensflare_ce_selector.c"
            selector_path.write_text('#include "lensflare_relocated.h"\n' + body + "\n")
            executable, _command = compile_harness(selector_path)
            manifest = OUT / "manifest.txt"
            expected = {}
            manifest_lines = []
            for name in MAPS:
                oracle = raw_oracle(name)
                pinned = PINNED_SUBMISSIONS.get(name, 0)
                self.assertEqual(len(oracle["records"]), pinned, name)
                self.assertEqual(oracle["errors"], 0, name)
                self.assertGreater(oracle["clusters"], 0, name)
                self.assertTrue(all(count <= FRAME_BOUND for count in oracle["per_cluster"]), name)
                if name in EMPTY_MAPS:
                    self.assertEqual((oracle["markers"], oracle["flares"], pinned), (0, 0, 0), name)
                else:
                    self.assertGreater(oracle["markers"], 0, name)
                    self.assertGreater(oracle["flares"], 0, name)
                inputs = package_inputs(name, payload_dir)
                expected[name] = oracle
                manifest_lines.append(" ".join(str(part) for part in (
                    name, inputs["ctag"], inputs["cbsp"], inputs["bsp_offset"],
                    inputs["bsp_size"], inputs["tag_offset"], inputs["tag_image_size"],
                    inputs["file_length"])))
            manifest.write_text("\n".join(manifest_lines) + "\n")
            run = subprocess.run([str(executable), str(manifest)],
                                 capture_output=True, text=True)
            log = OUT / "run.log"
            log.write_text(run.stdout + run.stderr)
            if run.returncode in (-31, 159):
                raise AssertionError(
                    "sandbox blocks native ILP32 execution with SIGSYS; rerun this "
                    "pytest command with sandbox disabled")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            observed = parse_output(run.stdout)
            for name in MAPS:
                with self.subTest(map=name):
                    oracle = expected[name]
                    got = observed[name]
                    self.assertEqual(int(got["clusters"]), oracle["clusters"], name)
                    self.assertEqual(int(got["markers"]), oracle["markers"], name)
                    self.assertEqual(int(got["flares"]), oracle["flares"], name)
                    self.assertEqual(int(got["calls"]), oracle["clusters"], name)
                    self.assertEqual(int(got["submissions"]), len(oracle["records"]), name)
                    self.assertEqual(int(got["errors"]), 0, name)
                    self.assertEqual(got["bsp_sha256"], got["bsp_sha256_after"], name)
                    self.assertEqual(int(got["collision_depth"]), 1, name)
                    self.assertEqual(int(got["collision_user"]), 19, name)
                    self.assertEqual(int(got["sprite_bound"]), SPRITE_BOUND, name)
                    self.assertEqual(got["guards"], "1", name)
                    self.assertEqual(got["vertex_cleared"], "1", name)
                    self.assertEqual(got["status"], "passed", name)
                    self.assertLessEqual(int(got["sprite_count"]), SPRITE_BOUND, name)
                    self.assertEqual(got["records"], oracle["records"], name)
                    self.assertEqual(got["sprite_sha256"], sprite_digest(got["records"]), name)
                    self.assertEqual(got["sprite_sha256"], sprite_digest(oracle["records"]), name)
                    if name in EMPTY_MAPS:
                        self.assertEqual(got["empty"], "1", name)
                        self.assertEqual(got["records"], [], name)
                    else:
                        self.assertEqual(got["empty"], "0", name)
                    clusters = {}
                    previous = -1
                    for record in got["records"]:
                        self.assertGreaterEqual(record["cluster"], previous, name)
                        previous = record["cluster"]
                        clusters[record["cluster"]] = clusters.get(record["cluster"], 0) + 1
                    self.assertTrue(all(count <= FRAME_BOUND for count in clusters.values()), name)
                    rows.append({
                        "map": name,
                        "clusters": oracle["clusters"],
                        "markers": oracle["markers"],
                        "flares": oracle["flares"],
                        "calls": int(got["calls"]),
                        "submissions": len(got["records"]),
                        "empty": got["empty"],
                        "sprite": got["sprite_sha256"],
                    })
            total_count = sum(row["submissions"] for row in rows)
            self.assertEqual(total_count, 1121)
            self.assertEqual(sum(PINNED_SUBMISSIONS.values()), 1121)
            self.assertLessEqual(total_count, SPRITE_BOUND)
            total_hash = total_digest({name: observed[name]["records"] for name in MAPS})
            self.assertEqual(total_hash, total_digest(
                {name: expected[name]["records"] for name in MAPS}))
            with log.open("a") as stream:
                stream.write(
                    f"TOTAL submissions={total_count} sprite_sha256={total_hash} "
                    f"sprite_bound={SPRITE_BOUND}\n")
            status = "PASS"
        except AssertionError as error:
            problem = str(error)
            raise
        finally:
            write_report(status, rows, total_count, total_hash, problem)


if __name__ == "__main__":
    unittest.main()
