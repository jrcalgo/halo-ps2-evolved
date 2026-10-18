import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from probe_results import EXPECTED, validate_probe


class ProbeResults(unittest.TestCase):
    def test_positive_requires_host_and_diagnostics(self):
        text = 'expected diagnostic fixture warning\n{"fixture":"integer_math","abi":"ILP32","status":"passed"}\nHALO_PS2_PROBE outcome=passed diagnostics_calls=2'
        self.assertTrue(validate_probe(text, "probe", EXPECTED)["host_equal"])
        for bad in (text.replace("diagnostics_calls=2", "diagnostics_calls=0"), text.replace("expected diagnostic fixture warning", "")):
            with self.assertRaises(RuntimeError):
                validate_probe(bad, "probe", EXPECTED)
        with self.assertRaises(RuntimeError):
            validate_probe(text, "probe", {**EXPECTED, "status": "failed"})

    def test_mutation_and_assertion_require_specific_failures(self):
        text = 'expected diagnostic fixture warning\ncheck failed: !point2d_in_rectangle2d(&a, &point) line=49\nHALO_PS2_PROBE negative_control=rejected diagnostics_calls=2'
        self.assertEqual(validate_probe(text, "probe-negative", EXPECTED)["negative_control"], "rejected")
        self.assertEqual(validate_probe('probe-diagnostics:18 assertion: 0', "probe-assert", EXPECTED)["status"], "expected-failure")
        for scenario in ("probe-negative", "probe-assert"):
            with self.assertRaises(RuntimeError):
                validate_probe('arbitrary crash', scenario, EXPECTED)
            with self.assertRaises(RuntimeError):
                validate_probe(text + '\nHALO_PS2_FAIL', scenario, EXPECTED)

    def test_datum_requires_host_equality_and_specific_stale_rejection(self):
        from test_probe_emulator import datum_result
        expected = {"fixture": "datum", "abi": "ILP32", "slots": 4, "status": "passed"}
        text = '{"fixture":"datum","abi":"ILP32","slots":4,"status":"passed"}\nHALO_PS2_DATUM outcome=passed'
        self.assertTrue(datum_result(text, "datum", expected)["host_equal"])
        with self.assertRaises(RuntimeError):
            datum_result(text, "datum", {**expected, "slots": 5})
        negative = 'datum check failed: datum_try_and_get(pool, stale) == NULL line=82\nHALO_PS2_DATUM negative_control=rejected'
        self.assertEqual(datum_result(negative, "datum-negative", expected)["negative_control"], "rejected")
        for bad in ('arbitrary crash', negative + text):
            with self.assertRaises(RuntimeError):
                datum_result(bad, "datum-negative", expected)
