import unittest
import hashlib
import json
from pathlib import Path

from tools.generate_hcu_step7_step8_closure import (
    _json_pointer_value,
    _markdown_table_measurements,
    evidence_rows,
)


ROOT = Path(__file__).resolve().parents[1]


class CoreReportMeasurementTests(unittest.TestCase):
    def test_json_pointer_handles_nested_keys_arrays_and_escaped_tokens(self):
        source = {"a/b": {"~value": [3, {"count": 7}]}}
        self.assertEqual(_json_pointer_value(source, "/a~1b/~0value/1/count"), 7)

    def test_exact_json_metrics_are_bound_for_available_core_artifacts(self):
        rows = {row["subcheck"]: row for row in evidence_rows()}
        expected = {
            "relocation-materialization": {"materialized_bsp_bytes", "internal_relocation_fields",
                                           "typed_ctag_name_relocations", "python_ps2_materializer_parity"},
            "binder": {"candidate_bsp_bytes", "candidate_tag_bytes", "candidate_texture_bytes",
                       "candidate_total_bytes"},
            "local-players-4": {"local_player_count", "spawned_unit_count", "game_ticks",
                                "game_state_high_water", "game_state_failed_allocations",
                                "object_pool_high_water"},
            "reserve": {"reserve_bytes"},
        }
        for subcheck, names in expected.items():
            row = rows[subcheck]
            values = row["measurements"]["values"]
            selected = [item for item in values if item["name"] in names]
            self.assertEqual({item["name"] for item in selected}, names)
            for item in selected:
                artifact = ROOT / item["source_artifact"]
                self.assertTrue(artifact.is_file(), item)
                self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(),
                                 item["source_artifact_sha256"], item)
                self.assertIsNotNone(_json_pointer_value(json.loads(artifact.read_text()),
                                                        item["source_pointer"]))
                self.assertTrue(item["unit"])
        self.assertIn("not establish broader acceptance", rows["binder"]["measurements"]["limitation"])
        self.assertIn("not a physical placement measurement",
                      next(item["derivation"] for item in rows["reserve"]["measurements"]["values"]
                           if item["name"] == "reserve_bytes"))

    def test_render_stress_explicit_units_normalize_with_source_bindings(self):
        report = ROOT / "docs/reports/mp-step8-live-render-cache-stress-2026-10-22.md"
        values = _markdown_table_measurements(report, report.read_text())
        self.assertTrue(values)
        owner = [value for value in values
                 if value["entity"] == "Blood Gulch"
                 and value["name"].startswith("owner_high_water_cap_bytes")]
        self.assertEqual([(value["name"].split("_high_water_cap_bytes_")[-1], value["value"], value["unit"])
                          for value in owner],
                         [("high_water", 3954720, "bytes"), ("capacity", 4014928, "bytes")])
        for value in values:
            self.assertEqual(value["source_report"], str(report.relative_to(ROOT)))
            self.assertEqual(value["source_report_sha256"], __import__("hashlib").sha256(report.read_bytes()).hexdigest())
            self.assertGreater(value["source_line"], 0)
            self.assertTrue(value["source_column"])

    def test_does_not_infer_units_for_unlabeled_or_hash_columns(self):
        report = ROOT / "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.md"
        values = _markdown_table_measurements(report, report.read_text())
        result_hashes = [value for value in values if "sha" in value["name"]]
        self.assertFalse(result_hashes)
        query_rows = [value for value in values if value["name"] == "query_rows_value"]
        self.assertEqual([value["value"] for value in query_rows], [13, 13])
        self.assertTrue(all(value["unit"] == "rows" for value in query_rows))

    def test_free_form_numbers_are_not_normalized(self):
        report = ROOT / "docs/reports/m2-step7-retail-cbsp-validation.md"
        values = _markdown_table_measurements(report, report.read_text())
        self.assertEqual(values, [])

    def test_generated_core_normalized_values_have_hash_and_location_binding(self):
        ledger_path = ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
        ledger = json.loads(ledger_path.read_text())
        core_rows = [row for row in ledger["evidence"]
                     if not row["subcheck"].startswith(("swarm-", "report-"))]
        normalized = [value for row in core_rows
                      for value in row.get("measurements", {}).get("values", [])
                      if isinstance(value, dict) and {"name", "value", "unit"} <= value.keys()]
        self.assertTrue(normalized)
        for value in normalized:
            artifact = value.get("source_artifact") or value.get("source_report")
            expected_hash = value.get("source_artifact_sha256") or value.get("source_report_sha256")
            self.assertTrue(artifact, value)
            source = ROOT / artifact
            self.assertTrue(source.is_file(), value)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash, value)
            self.assertTrue(value.get("source_pointer") or
                            (value.get("source_line") and value.get("source_column")), value)


if __name__ == "__main__":
    unittest.main()
