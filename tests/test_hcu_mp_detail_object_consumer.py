"""Run the verbatim HCU detail-object CPU selector against bounded fixtures.

Retail stock MP maps currently carry empty detail-object roots, so those cases
verify the actual CE no-draw gate. A separate synthetic fixture reaches the CE
camera-cell/layer selection path without pretending it came from a retail map.
"""
from pathlib import Path
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
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
HCU_SOURCE_SHA256 = "471e7a77c5f92bcd8587ffccd9f3cffe7cf7cabec94189f02e0a0231b2314a5a"
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from tools.ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def extract_function(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    prototype_end = source.find(";", start, opening)
    if prototype_end >= 0:
        start = source.index(marker, prototype_end + 1)
        opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise AssertionError(f"unterminated HCU function {marker}")


def map_detail_root(map_name: str) -> tuple[str, int, tuple[int, int, int, int]]:
    """Read the retail BSP field using raw Xbox pointers and schema strides."""
    path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    map_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    header = mapinfo.read_header(path)
    index = tagindex.TagIndex.read(path)
    region, _tag_base, _ = read_xbox_tag_region(path)
    locations = bsp.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{map_name}: expected one stock multiplayer BSP")
    location = locations[0]
    image = path.read_bytes()[location.file_offset:location.file_offset + location.size]
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError(f"{map_name}: structure-BSP root outside source BSP")
    # structure_bsp.detail_object_data is field offset 588 in the pinned CE
    # structure definition (the CE BSP root is 648 bytes).
    root_count, root_address = struct.unpack_from("<iI", image, root + 588)
    if root_count != 1 or root_address < location.address:
        raise AssertionError(f"{map_name}: unexpected detail_object_data root")
    data_offset = root_address - location.address
    if data_offset < 0 or data_offset + 64 > len(image):
        raise AssertionError(f"{map_name}: detail-object root leaves BSP extent")
    blocks = tuple(struct.unpack_from("<iI", image, data_offset + member * 12)
                   for member in range(4))
    for count, address in blocks:
        if count != 0 or address != 0:
            raise AssertionError(
                f"{map_name}: retail detail-object payload is not empty: {blocks}")
    valid = image[data_offset + 48]
    if valid != 0:
        raise AssertionError(f"{map_name}: detail-object root is marked valid ({valid})")
    return map_hash, valid, tuple(count for count, _ in blocks)


class MultiplayerDetailObjectConsumerTest(unittest.TestCase):
    def test_actual_ce_selector_and_all_stock_mp_empty_roots(self):
        source_path = HCU / "source/structures/structure_detail_objects.c"
        source_bytes = source_path.read_bytes()
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), HCU_SOURCE_SHA256)
        source = source_bytes.decode("utf-8")
        # Keep extraction markers explicit because the two comparator bodies
        # are static booleans and the remaining helpers have distinct types.
        markers = (
            "static boolean key_compare_cells_lower_bound(",
            "static boolean key_compare_cells_upper_bound(",
            "static struct detail_object_cell_definition *get_lower_bound_cell(",
            "static struct detail_object_cell_definition *get_upper_bound_cell(",
            "static struct detail_object_runtime_data *get_local_player_datum(",
            "static long structure_detail_objects_port_count(",
            "void structure_render_detail_objects(",
        )
        function_bodies = "\n\n".join(extract_function(source, marker) for marker in markers)
        # Xbox/EE are ILP32; use explicit fixed-width spellings in this native
        # harness rather than allowing the host LP64 ABI to widen CE longs.
        function_bodies = function_bodies.replace("unsigned long", "uint32_t")
        function_bodies = function_bodies.replace("long", "int32_t")
        template = (ROOT / "tests/hcu_mp_detail_object_consumer_main.c").read_text()
        with tempfile.TemporaryDirectory(prefix="hcu-mp-detail-object-") as temporary:
            temp = Path(temporary)
            runner = temp / "hcu_mp_detail_object_consumer_main.c"
            runner.write_text(template.replace("/* CE_DETAIL_OBJECT_FUNCTIONS */", function_bodies))
            executable = temp / "detail-object-consumer"
            compile_result = subprocess.run(
                [os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra", "-Werror",
                 "-Wno-missing-field-initializers",
                 str(runner), "-lm", "-o", str(executable)],
                capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            synthetic = subprocess.run([str(executable), "synthetic"],
                                       capture_output=True, text=True)
            self.assertEqual(synthetic.returncode, 0, synthetic.stdout + synthetic.stderr)
            self.assertIn("synthetic camera-cell selection passed", synthetic.stdout)
            self.assertIn("empty valid detail data passed", synthetic.stdout)
            for map_id, map_name in enumerate(MP_MAPS, start=101):
                with self.subTest(map=map_name):
                    source_hash, valid, counts = map_detail_root(map_name)
                    self.assertEqual(source_hash, MAP_SHA256[map_name])
                    self.assertEqual(counts, (0, 0, 0, 0))
                    result = subprocess.run(
                        [str(executable), "retail", str(map_id), str(valid)],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(
                        f"retail map={map_id} detail_valid=0 cells=0 counts=0 "
                        "objects=0 zrefs=0 draw_calls=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
