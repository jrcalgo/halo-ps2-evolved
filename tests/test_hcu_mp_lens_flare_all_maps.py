"""Run CE's real cluster lens-flare selector against all retail MP BSPs.

The companion focused test covers three representative maps. This test reuses
its extracted CE function and ABI fixture, but widens the raw-source matrix to
the complete stock multiplayer map set.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_hcu_mp_lens_flare_consumer as consumer  # noqa: E402

MP_MAPS = {
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


def read_mp_raw(name):
    previous = consumer.MAPS
    consumer.MAPS = MP_MAPS
    try:
        return consumer.read_raw(name)
    finally:
        consumer.MAPS = previous


class AllMultiplayerLensFlareInventory(unittest.TestCase):
    @staticmethod
    def ce_selector():
        ce = consumer.extract_function(
            consumer.LIGHTS.read_text(),
            "void rasterizer_lens_flare_submit_for_cluster(",
        )
        ce = ce.replace(
            "rasterizer_debug_options.draw_lens_flares",
            "rasterizer_debug_options_draw_lens_flares()",
        )
        return ce

    def test_ce_marker_selection_against_all_13_raw_bsp_images(self):
        # Keep the digest check in the shared raw-BSP decoder, but widen its
        # allowlist only within this isolated test.
        ce = self.ce_selector()
        self.assertIn("structure_lens_flare_marker_index>=marker_count", ce)
        self.assertIn("marker->lens_flare_index>=structure_bsp->lens_flares.count", ce)

        rows = []
        with tempfile.TemporaryDirectory(prefix="hcu-mp-lens-flare-all-") as temp:
            for map_name, source_sha in MP_MAPS.items():
                digest, flares, markers, clusters = read_mp_raw(map_name)
                self.assertEqual(digest, source_sha)
                self.assertGreater(len(clusters), 0, map_name)
                source_path = Path(temp) / f"{map_name}.c"
                binary_path = Path(temp) / map_name
                source_path.write_text(consumer.fixture_c(ce, flares, markers, clusters))
                subprocess.run(
                    ["cc", "-std=c99", "-O2", str(source_path), "-o", str(binary_path)],
                    check=True,
                )
                result = subprocess.run(
                    [str(binary_path)], check=True, capture_output=True, text=True,
                )
                values = dict(field.split("=", 1) for field in result.stdout.split())
                observed = [int(value) for value in values["indices"].split(",") if value]
                expected = []
                for cluster in clusters:
                    first, count = struct.unpack_from("<HH", cluster, 0x40)
                    for marker_index in range(first, first + count):
                        if (marker_index < len(markers) and
                                markers[marker_index][15] < len(flares)):
                            expected.append(marker_index)
                self.assertEqual(observed, expected, map_name)
                self.assertEqual(int(values["badref_errors"]), 0, map_name)
                rows.append((map_name, len(clusters), len(markers), len(observed)))

        self.assertEqual(set(name for name, *_ in rows), set(MP_MAPS))
        self.assertGreater(sum(markers for _, _, markers, _ in rows), 0)

    def test_synthetic_bad_indices_screenshot_and_disable_guards(self):
        ce = self.ce_selector()
        _, flares, markers, clusters = read_mp_raw("boardingaction")
        code = consumer.fixture_c(ce, flares, markers, clusters)
        synthetic_main = r'''int main(void) {
 struct structure_cluster cluster; struct structure_lens_flare_marker test_markers[3];
 int before;
 memset(&cluster,0,sizeof(cluster)); memset(test_markers,0,sizeof(test_markers));
 initialize(); bsp.clusters.address=&cluster; bsp.clusters.count=1;
 bsp.lens_flare_markers.address=test_markers; bsp.lens_flare_markers.count=3;
 bsp.lens_flares.count=1; flare_records[0].lens_flare.index=0;
 test_markers[0].lens_flare_index=0; test_markers[1].lens_flare_index=7;
 test_markers[2].lens_flare_index=0;
 cluster.first_lens_flare_marker_index=1; cluster.lens_flare_marker_count=4;
 rasterizer_lens_flare_submit_for_cluster(0);
 if(submit_count!=1 || submitted[0]!=2 || errors!=2) return 11;
 before=submit_count; enabled=0; cluster.first_lens_flare_marker_index=0;
 cluster.lens_flare_marker_count=3; rasterizer_lens_flare_submit_for_cluster(0);
 screenshot=1; enabled=1; rasterizer_lens_flare_submit_for_cluster(0);
 if(submit_count!=before) return 12;
 printf("synthetic valid-after-bad=1 marker-bound-break=1 bad-ref-skip=1 disabled=1 screenshot=1\n");
 return 0;
}
'''
        code = code[:code.index("int main(void) {")] + synthetic_main
        with tempfile.TemporaryDirectory(prefix="hcu-mp-lens-flare-synthetic-") as temp:
            source = Path(temp) / "synthetic.c"
            binary = Path(temp) / "synthetic"
            source.write_text(code)
            subprocess.run(["cc", "-std=c99", "-O2", str(source), "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
        self.assertIn("bad-ref-skip=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
