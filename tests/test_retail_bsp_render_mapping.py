"""Source-surface correspondence probe for one over-budget retail BSP."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


class RetailBspRenderMappingTests(unittest.TestCase):
	def test_d20_hangar_source_surfaces_match_ps2_batches(self):
		root = Path(__file__).resolve().parents[1]
		map_path = root / "build/retail-maps/decompressed/d20.map"
		if not map_path.is_file():
			self.skipTest("decompressed retail d20.map is unavailable")
		run = subprocess.run([
			sys.executable, str(root / "tools/audit_bsp_render_mapping.py"),
			str(map_path), "--bsp", "3",
		], check=True, capture_output=True, text=True)
		report = json.loads(run.stdout)
		self.assertEqual(report["map_sha256"],
			"30d8fc02bcd209a7ce03174d8cf6cf771dd3621837d9a2d02111718dcc5e792c")
		self.assertEqual(report["source_block_sha256"],
			"a8e8174997a793831bd0504484582172e3802688a51d6b32a61e30c5962001ab")
		self.assertEqual(report["bsps_sha256"],
			"1442a7da4494a6be9ff45753e65a0fc72c8eb03e75ee94aeda2b80786c67c3bb")
		self.assertEqual(report["bsp_path"], "levels\\d20\\d20_hangar")
		self.assertEqual(report["ce_surface_count"], 49859)
		self.assertEqual(report["bsps_triangles"], 49859)
		self.assertEqual(report["rendered_source_surfaces_mapped"], 49859)
		self.assertEqual(report["source_surfaces_missing_cluster_route"], 0)
		self.assertEqual(report["position_corner_comparisons"], 149577)
		self.assertLess(report["maximum_euclidean_position_error"], 0.002)
		self.assertEqual(report["maximum_absolute_lightmap_uv_error"], 0.0)
		self.assertEqual(report["diffuse_uv_components_over_sane_limit_or_nonfinite"], 6)
		self.assertGreater(report["maximum_absolute_diffuse_uv_error"], 512.0)
		self.assertEqual(
			report["candidate_lookup_bytes_u16_batch_u8_triangle_u8_flags"],
			49859 * 4)
		self.assertIn("not CE collision", report["note"])


if __name__ == "__main__":
	unittest.main()
