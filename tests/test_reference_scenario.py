"""The integer-math host scenario repeats with identical canonical results."""
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from memory_budget import canonical_json
from run_reference_scenario import load_scenario, observe, repeat


class ReferenceScenario(unittest.TestCase):
    def test_configuration_records_the_source_boundary(self):
        scenario = load_scenario("integer-math-host")
        self.assertIsNone(scenario["map"])
        self.assertIsNone(scenario["camera"])
        self.assertEqual(scenario["player_actions"], [])
        self.assertIn("does not prove retail behavior", scenario["limits"])

    def test_two_runs_match(self):
        root = Path(__file__).resolve().parents[1]
        binary = root / "build/gameplay-host32/integer-math"
        if not binary.is_file():
            subprocess.run([sys.executable, str(root / "tools/test_gameplay_host32.py")], cwd=root, check=True)
        first = repeat("integer-math-host", binary)
        second = repeat("integer-math-host", binary)
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertEqual(first["outcome"], "passed")
        self.assertEqual(first["seed"], 1)
        self.assertEqual(first["tick_count"], 0)
        with self.assertRaisesRegex(RuntimeError, "differs"):
            observe(load_scenario("integer-math-host"),
                    {"fixture": "integer_math", "abi": "ILP32", "status": "failed"})


if __name__ == "__main__":
    unittest.main()
