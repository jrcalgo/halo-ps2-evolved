import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EightUnmappedExactLayoutTests(unittest.TestCase):
    def test_r5900_compiler_accepts_every_gap_layout_assertion(self):
        run = subprocess.run(
            [sys.executable, str(ROOT / "tools/probe_step7_eight_unmapped_exact_layout.py")],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        evidence = json.loads(run.stdout)
        self.assertEqual(evidence["status"], "passed", evidence["diagnostics"])
        self.assertEqual(evidence["compiler"].split()[0], "mips64r5900el-ps2-elf-gcc")
        self.assertTrue(evidence["probe_object_sha256"])
        self.assertEqual(len(evidence["assertion_sets"]), 8)
        self.assertEqual(evidence["assertion_sets"]["detail_object_cell"]["members"]["unused14"],
                         {"offset": 20, "size": 12})
        self.assertEqual(evidence["assertion_sets"]["structure_mirror"]["members"]["unused"],
                         {"offset": 16, "size": 20})
        self.assertEqual(evidence["assertion_sets"]["structure_subcluster"]["members"]["world_bounds"],
                         {"offset": 0, "size": 24})


if __name__ == "__main__":
    unittest.main()
