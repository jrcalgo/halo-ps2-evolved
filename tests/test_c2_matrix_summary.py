"""Host tests for tools/c2_profile_boot_matrix.py summary merging and C3 render checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_profile_boot_matrix as matrix  # noqa: E402


class SummaryMerge(unittest.TestCase):
    def test_partial_run_keeps_other_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = matrix.MATRIX
            matrix.MATRIX = Path(tmp)
            try:
                rows = matrix.profile_rows()[:3]
                for name in rows:
                    (Path(tmp) / name).mkdir()
                    (Path(tmp) / name / "result.json").write_text(
                        json.dumps({"row": name, "pass": True, "reasons": []}))
                # a stale one-row summary, as the old tool left behind
                (Path(tmp) / "summary.json").write_text(json.dumps({"rows": [{"row": rows[0], "pass": True, "reasons": []}]}))
                matrix.write_summary([{"row": rows[1], "pass": False, "reasons": ["x"]}])
                data = json.loads((Path(tmp) / "summary.json").read_text())["rows"]
                self.assertEqual([r["row"] for r in data], rows)
                self.assertEqual([r["pass"] for r in data], [True, False, True])
            finally:
                matrix.MATRIX = old

    def test_render_checks(self):
        good = [
            "HALO_PS2_LOCAL c3-render-ready map=bloodgulch views=2",
            "HALO_PS2_LOCAL c3-frame kind=final frame=300 views=2 overflow=0 frames=300 idle-violations=0 emit-failures=0",
            "HALO_PS2_LOCAL c3-render-held views=2 frames=300",
            "HALO_PS2_LOCAL production-ce-ticks result=1 map=bloodgulch",
            "HALO_PS2_LOCAL c3-render-teardown order=x world-unbind=0 readers-before=1 readers-after=0 frames=300 overflow=0 media-loaded=0",
        ]
        result = matrix.render_checks(good, 2, 300)
        self.assertTrue(all(result["checks"].values()), result["checks"])
        bad = [good[0], good[1].replace("overflow=0 frames", "overflow=1 frames"), good[3]]
        result = matrix.render_checks(bad, 2, 300)
        self.assertFalse(result["checks"]["render_overflow_zero"])
        self.assertFalse(result["checks"]["render_teardown"])

    def test_three_views_count_the_clear_quadrant(self):
        lines = [
            "HALO_PS2_LOCAL c3-render-ready map=bloodgulch views=3",
            "HALO_PS2_LOCAL c3-frame kind=final frame=300 views=4 overflow=0 frames=300 idle-violations=0 emit-failures=0",
        ]
        self.assertTrue(matrix.render_checks(lines, 3, 300)["checks"]["render_views"])


if __name__ == "__main__":
    unittest.main()
