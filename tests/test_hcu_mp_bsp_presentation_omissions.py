"""Raw-BSP presentation-omission audit: deterministic, and never dispositioned strip."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/audit_mp_bsp_presentation_omissions.py"
OUT = ROOT / "build/step7-swarm/omissions"
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tools"))
from hcu_ps2_closure import MANIFEST_PATH, selected_sources  # noqa: E402

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
EXPECTED_DISPOSITION = {
    "unreferenced_surfaces": "retain-bytes",
    "render_nodes": "requires PS2 consumer",
    "cluster_fog_bit15": "requires PS2 consumer",
    "transition_bsp": "retain-bytes",
    "predicted_resources": "requires PS2 consumer",
    "portal_flags": "retain-bytes",
    "mirrors": "retain-bytes",
    "decal_range": "requires PS2 consumer",
    "lens_flare_range": "retain-bytes",
}
EXPECTED_INSTANCES = {
    "unreferenced_surfaces": 4,
    "render_nodes": 57774,
    "cluster_fog_bit15": 51,
    "transition_bsp": 0,
    "predicted_resources": 9490,
    "portal_flags": 0,
    "mirrors": 0,
    "decal_range": 49,
    "lens_flare_range": 54,
}
ALLOWED = {"retain-bytes", "requires PS2 consumer"}


def run_audit() -> tuple[str, dict]:
    completed = subprocess.run(
        [sys.executable, str(TOOL)],
        check=False, capture_output=True, text=True, cwd=ROOT)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout[:500])
    if completed.stderr:
        raise AssertionError(completed.stderr)
    return completed.stdout, json.loads(completed.stdout)


class PresentationOmissionAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first_text, cls.first = run_audit()
        cls.second_text, cls.second = run_audit()
        cls.closure = set(selected_sources(json.loads(MANIFEST_PATH.read_text())))

    def test_two_runs_identical(self):
        self.assertEqual(self.first_text, self.second_text)
        self.assertEqual((OUT / "omissions.json").read_text(), self.second_text)
        self.assertEqual((OUT / "audit.log").read_text(), self.second_text)
        self.assertTrue((OUT / "report.md").is_file())
        self.assertTrue((OUT / "omissions.md").is_file())

    def test_disposition_rule_and_no_strip(self):
        report = self.first
        self.assertTrue(report["ok"])
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["map_count"], 13)
        self.assertEqual([row["map"] for row in report["maps"]], list(MP_MAPS))
        self.assertEqual([item["id"] for item in report["categories"]], list(EXPECTED_DISPOSITION))
        for category in report["categories"]:
            with self.subTest(category=category["id"]):
                self.assertIn(category["disposition"], ALLOWED)
                self.assertNotEqual(category["disposition"], "strip")
                self.assertEqual(category["disposition"], EXPECTED_DISPOSITION[category["id"]])
                self.assertEqual(category["stock_instances"], EXPECTED_INSTANCES[category["id"]])
                expected = (
                    "requires PS2 consumer"
                    if category["stored_read_in_closure"] and category["stock_instances"] >= 1
                    else "retain-bytes")
                self.assertEqual(category["disposition"], expected)
                if category["call_site"] is None:
                    self.assertFalse(category["stored_read_in_closure"])
                    self.assertEqual(category["reads"], [])

    def test_call_sites_match_source_and_closure(self):
        report = self.first
        for category in report["categories"]:
            for read in category["reads"]:
                with self.subTest(category=category["id"], site=f"{read['file']}:{read['line']}"):
                    line = (HCU / read["file"]).read_text().splitlines()[read["line"] - 1]
                    self.assertIn(read["snippet"], line)
                    self.assertEqual(read["in_ps2_closure"], read["file"] in self.closure)
        for reader in report["route_readers"] + report["excluded_surface_walk"]:
            with self.subTest(route=f"{reader['file']}:{reader['line']}"):
                line = (HCU / reader["file"]).read_text().splitlines()[reader["line"] - 1]
                self.assertIn(reader["snippet"], line)
                self.assertEqual(reader["in_ps2_closure"], reader["file"] in self.closure)
                self.assertFalse(reader["consumes_unreferenced_surface"])
        lens = next(item for item in report["categories"] if item["id"] == "lens_flare_range")
        self.assertFalse(lens["stored_read_in_closure"])
        self.assertTrue(any(
            read["file"] == "source/rasterizer/rasterizer_lights.c" and read["consumes_map_bytes"]
            and not read["in_ps2_closure"] for read in lens["reads"]))
        self.assertTrue(any(
            read["file"] == "source/structures/structure_lens_flares.c" and not read["consumes_map_bytes"]
            and read["in_ps2_closure"] for read in lens["reads"]))
        mirrors = next(item for item in report["categories"] if item["id"] == "mirrors")
        self.assertTrue(mirrors["stored_read_in_closure"])
        self.assertEqual(mirrors["stock_instances"], 0)

    def test_empty_results_are_explicit_and_maps_are_pinned(self):
        report = self.first
        self.assertEqual(report["cluster_direct_surface_blocks"], 0)
        putput = next(row for row in report["maps"] if row["map"] == "putput")
        self.assertEqual(putput["bsps"][0]["unreferenced_surface_indices"], [10276, 10277, 10299, 10304])
        for row in report["maps"]:
            self.assertEqual(row["source_map_sha256"], MAP_SHA256[row["map"]])
            self.assertEqual(row["bsp_count"], 1)
            for bsp in row["bsps"]:
                self.assertTrue(all(bsp["checks"].values()))
            for category, cell in row["categories"].items():
                with self.subTest(map=row["map"], category=category):
                    self.assertIsInstance(cell["instances"], int)
                    self.assertEqual(cell["empty"], cell["instances"] == 0)
                    self.assertTrue(cell["proof"])
                    if cell["instances"] == 0:
                        self.assertTrue(
                            "every" in cell["proof"] or "0 cluster portals" in cell["proof"])


if __name__ == "__main__":
    unittest.main()
