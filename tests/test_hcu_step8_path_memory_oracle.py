from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c"
PARSER = ROOT / "tools/test_hcu_step7_path_guest.py"


class PathMemoryOracleTests(unittest.TestCase):
    def test_path_state_is_measured_live_then_reclaimed(self):
        text = SOURCE.read_text()
        start = text.index("static boolean step8_mp_run_path_oracle")
        end = text.index("static void hcu_step8_mp_capacity_test_run", start)
        body = text[start:end]
        live = body.index("physical_memory_get_malloc_diagnostics(&memory_live)")
        release = body.index("free(state)", live)
        after = body.index("physical_memory_get_malloc_diagnostics(&memory_after)", release)
        self.assertLess(live, release)
        self.assertLess(release, after)
        self.assertIn("memory_live.used_bytes - memory_before.used_bytes >=", body)
        self.assertIn("memory_after.used_bytes == memory_before.used_bytes", body)
        self.assertIn("memory_live.failed_allocations == memory_before.failed_allocations", body)
        self.assertIn("memory_after.failed_allocations == memory_before.failed_allocations", body)

    def test_guest_parser_checks_live_use_and_after_free_baseline(self):
        text = PARSER.read_text()
        self.assertIn("after_delta=(\\d+)", text)
        self.assertIn("after_delta != 0", text)
        self.assertIn("used_delta < aligned", text)


if __name__ == "__main__":
    unittest.main()
