"""Run CE's lightmap/material search against all 13 stock multiplayer BSPs."""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_mp_lightmap_surface_consumer as audit  # noqa: E402

PUTPUT_UNREFERENCED = [10276, 10277, 10299, 10304]


class LightmapSurfaceConsumerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if audit.PACKAGE_DIR_RESOLVED is None:
            raise unittest.SkipTest(
                "no pin-verified retail HP2 package set: set HALO_HCU_M2_PACKAGE_ROOT or keep "
                "build/mp-fog-selection-*/assets/maps/*.hp2 matching audit.PACKAGE_SHA256")
        cls.payload = audit.run()

    def test_pinned_ce_source_and_synthetic_empty_block(self):
        self.assertEqual(self.payload["hashes"]["ce_source"], audit.CE_SOURCE_SHA256)
        self.assertEqual(self.payload["status"], "PASS")
        self.assertEqual(self.payload["issues"], [])
        self.assertIn("empty found=0", self.payload["empty"])
        self.assertIn("depth=0", self.payload["empty"])
        generated = (audit.OUT / "lightmap_surface_consumer_generated.c").read_text(encoding="utf-8")
        start = generated.index("boolean structure_bsp_find_material_for_surface(")
        end = generated.index("\nstatic uint32_t fnv1a")
        body = generated[start:end].strip()
        self.assertIn(body, audit.CE_SOURCE.read_text(encoding="utf-8"))
        self.assertIn("long surface_index", body)
        self.assertIn("before every material", body)
        report = (audit.OUT / "report.md").read_text(encoding="utf-8")
        self.assertIn("structure_bsp_find_material_for_surface", report)
        self.assertIn("does not authorize stripping", report)
        self.assertIn("10276", report)
        self.assertIn("self-illumination", report)

    def test_map_matrix(self):
        self.assertEqual([row["map"] for row in self.payload["maps"]], list(audit.MP_MAPS))
        for row in self.payload["maps"]:
            with self.subTest(map=row["map"]):
                map_path = audit.SOURCE_DIR / f"{row['map']}.map"
                package_path = audit.PACKAGE_DIR / f"{row['map']}.hp2"
                self.assertEqual(hashlib.sha256(map_path.read_bytes()).hexdigest(), audit.MAP_SHA256[row["map"]])
                self.assertEqual(hashlib.sha256(package_path.read_bytes()).hexdigest(), audit.PACKAGE_SHA256[row["map"]])
                self.assertEqual(row["source_sha256"], audit.MAP_SHA256[row["map"]])
                self.assertFalse(row["raw_empty"])
                self.assertGreater(row["surfaces"], 0)
                self.assertGreater(row["lightmaps"], 0)
                self.assertGreater(row["materials"], 0)
                self.assertEqual(row["queries"], row["surfaces"])
                self.assertGreater(row["endpoint_queries"], 0)
                self.assertEqual(row["endpoint_mismatches"], 0)
                self.assertEqual(row["ce_hits"], row["surfaces"])
                self.assertEqual(row["ce_mismatches"], 0)
                self.assertEqual(row["vertex_faults"], 0)
                self.assertEqual(row["interval_faults"], 0)
                self.assertEqual(row["bsps_shader_mismatches"], 0)
                self.assertEqual(row["cbsp_field_mismatches"], 0)
                self.assertEqual(row["bytes_unchanged"], 1)
                self.assertEqual(row["collision_user_depth_before"], 0)
                self.assertEqual(row["collision_user_depth_after"], 0)
                self.assertTrue(row["package_hash_unchanged"])
                self.assertEqual(row["package_sections"], ["CTAG", "CRNG", "HMAP", "B000", "CBIX"])
                self.assertNotIn("BSPS", row["package_sections"])
                self.assertNotIn("TEXS", row["package_sections"])
                self.assertEqual(row["issues"], [])
                self.assertEqual(row["bsps_dropped"], 0)
                self.assertEqual(row["texs_mismatches"], 0)
                self.assertEqual(row["texs_untextured"], 0)
                probes = {probe["label"]: probe for probe in row["bounds_probes"]}
                self.assertEqual(set(probes), {"before", "after"})
                self.assertEqual(probes["before"]["query"], -1)
                self.assertEqual(probes["after"]["query"], row["surfaces"])
                for probe in probes.values():
                    self.assertEqual(probe["code"], 0)
                    self.assertEqual(probe["found"], 0)
                    self.assertEqual(probe["bytes_unchanged"], 1)
                    self.assertEqual(probe["depth_before"], 0)
                    self.assertEqual(probe["depth_after"], 0)
                if row["map"] == "putput":
                    self.assertEqual(row["bsps_unreferenced"], PUTPUT_UNREFERENCED)
                else:
                    self.assertEqual(row["bsps_unreferenced"], [])


if __name__ == "__main__":
    unittest.main()
