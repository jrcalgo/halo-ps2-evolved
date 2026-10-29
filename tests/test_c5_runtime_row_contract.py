"""Contract checks for the C5 runtime-row mode and the live-owner refusal log line.

Static (text) checks: the log line is printed exactly once, inside the live-owner branch of
hcu_map_service_preflight_impl and not inside fail_preflight_for_entry. Build-mode checks import tools/c5_build.py
and confirm the default (bootstrap) make variables are unchanged and the runtime-row variables are set only when a
row is requested."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_SERVICE = ROOT / "src/stream/hcu_map_service.c"
LINE = 'printf("HALO_PS2_LOCAL map-preflight rejected map=%s reason=live-owner-mounted\\n"'


class LiveOwnerLogLineTest(unittest.TestCase):
    def test_line_printed_once_in_live_owner_branch(self) -> None:
        text = MAP_SERVICE.read_text()
        self.assertEqual(text.count(LINE), 1)
        at = text.index(LINE)
        branch = text.index("if (service->mount.active || service->source.active) {")
        self.assertLess(branch, at)
        self.assertLess(at, text.index("fail_preflight_for_entry(service, entry);", at))

    def test_line_not_inside_fail_preflight_helper(self) -> None:
        text = MAP_SERVICE.read_text()
        start = text.index("fail_preflight_for_entry(hcu_map_service")  if "fail_preflight_for_entry(hcu_map_service" in text \
            else text.index("static void fail_preflight_for_entry(")
        end = text.index("\n}\n", start)
        self.assertNotIn("map-preflight rejected", text[start:end])


class RuntimeRowModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        import c5_build  # noqa: E402
        cls.c5 = c5_build

    def setUp(self) -> None:
        self.saved = self.c5.RUNTIME_ROW

    def tearDown(self) -> None:
        self.c5.RUNTIME_ROW = self.saved

    def test_default_variables_are_bootstrap(self) -> None:
        self.c5.RUNTIME_ROW = ""
        variables = self.c5.gameplay_make_vars()
        self.assertIn("WORLD_HCU_PARTITION_PROFILE=", variables)
        self.assertIn("WORLD_HCU_HEADLESS_RUNTIME_GUEST=0", variables)
        self.assertEqual(variables, list(self.c5.GAMEPLAY_MAKE_VARS))

    def test_runtime_row_sets_partition_and_headless(self) -> None:
        row = "sidewinder_marine_shotgun_4p4bot"
        self.c5.RUNTIME_ROW = row
        variables = self.c5.gameplay_make_vars()
        self.assertIn(f"WORLD_HCU_PARTITION_PROFILE={row}", variables)
        self.assertIn("WORLD_HCU_HEADLESS_RUNTIME_GUEST=1", variables)
        self.assertNotIn("WORLD_HCU_HEADLESS_RUNTIME_GUEST=0", variables)

    def test_bots_sidewinder_is_not_a_runtime_row(self) -> None:
        self.assertNotIn("bots_sidewinder", self.c5.RUNTIME_ROWS)


if __name__ == "__main__":
    unittest.main()
