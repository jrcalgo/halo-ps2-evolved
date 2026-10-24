"""Guard CE/PS2 map teardown ordering against CTAG owner lifetime regressions.

This is deliberately a source-contract test: the existing host lifecycle fixture
executes scenario load/unload and the parent CTAG owner, but does not link the
large CE game.c/main.c teardown call graph. See the test docstring for scope.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MAIN = HCU / "source/main/main.c"
GAME = HCU / "source/game/game.c"
SCENARIO = HCU / "source/scenario/scenario.c"
LIFECYCLE_DIAGNOSTIC = HCU / "source/main/ps2_m2_ui_lifecycle_test.c"


def c_function_body(source: str, signature: str) -> str:
    """Return one C function body by balanced-brace extraction."""
    matches = list(re.finditer(signature, source))
    if not matches:
        raise AssertionError(f"function signature not found: {signature}")
    opening = None
    # C implementations frequently have a prototype before the body. Select
    # the occurrence whose closing parameter-list is followed by '{', not ';'.
    for match in matches:
        close_paren = source.find(")", match.end())
        if close_paren < 0:
            continue
        brace = source.find("{", close_paren)
        semicolon = source.find(";", close_paren)
        if brace >= 0 and (semicolon < 0 or brace < semicolon):
            opening = brace
            break
    if opening is None:
        raise AssertionError(f"function body not found: {signature}")
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    raise AssertionError(f"unbalanced function body: {signature}")


def assert_order(test: unittest.TestCase, body: str, *needles: str) -> None:
    positions = [body.find(needle) for needle in needles]
    test.assertTrue(all(position >= 0 for position in positions),
                    f"missing lifecycle operation in order contract: {needles}")
    test.assertEqual(positions, sorted(positions),
                     f"lifecycle operations are out of order: {needles}")


class HcuPs2MapTeardownOrderTests(unittest.TestCase):
    def test_ps2_replacement_paths_dispose_before_owner_release(self):
        """The CE disposal call must precede the map-unloading call in PS2 paths."""
        main = MAIN.read_text()
        paths = (
            ("main_change_map_name",
             r"static void main_change_map_name\s*\(", True),
            ("main_load_ui_scenario",
             r"void main_load_ui_scenario\s*\(", True),
            ("main_setup_connection",
             r"static void main_setup_connection\s*\(", True),
            ("hcu_step8_test_start_local_map",
             r"int hcu_step8_test_start_local_map\s*\(", False),
        )
        for name, signature, has_inner_ps2_guard in paths:
            with self.subTest(path=name):
                body = c_function_body(main, signature)
                # The source has an explicit HALO_PS2 branch. We assert the first
                # pair in that function (the PS2 pair precedes the CE-only #else
                # pair where present) and ensure successor tag load comes later.
                assert_order(self, body,
                             "game_dispose_from_old_map();",
                             "game_unload();",
                             "game_precache_new_map(")
                if has_inner_ps2_guard:
                    self.assertIn("#ifdef HALO_PS2", body,
                                  f"{name} lost its explicit PS2 ownership branch")

    def test_ce_unload_releases_owner_only_after_scenario_unpublication(self):
        """Source call graph defines the owner-lifetime events checked above."""
        game = GAME.read_text()
        dispose = c_function_body(
            game, r"void game_dispose_from_old_map\s*\(")
        self.assertIn("scenario_dispose_from_old_map();", dispose)
        self.assertNotIn("scenario_unload();", dispose)
        self.assertNotIn("ps2_cache_release_map_owner", dispose)

        unload = c_function_body(game, r"void game_unload\s*\(")
        assert_order(self, unload,
                     "if (game_globals->map_loaded)",
                     "scenario_unload();",
                     "game_globals->map_loaded = FALSE;")

        scenario = c_function_body(
            SCENARIO.read_text(), r"void scenario_unload\s*\(")
        assert_order(self, scenario,
                     "scenario_tags_unload();",
                     "global_scenario = NULL;",
                     "global_structure_bsp = NULL;",
                     "ps2_cache_release_map_owner()")
        self.assertIn("match_assert", scenario)

    def test_map_diagnostic_entry_paths_preserve_the_same_order(self):
        """Test-only UI→map and UI lifecycle transitions use the real contract."""
        source = LIFECYCLE_DIAGNOSTIC.read_text()
        for name, signature in (
            ("capacity diagnostic UI teardown",
             r"static void hcu_step8_mp_capacity_test_run\s*\("),
            ("injected UI lifecycle teardown",
             r"void hcu_m2_ui_lifecycle_test_run\s*\("),
        ):
            with self.subTest(path=name):
                body = c_function_body(source, signature)
                assert_order(self, body,
                             "game_dispose_from_old_map();",
                             "game_unload();")

    def test_step8_cleanup_uses_the_contract_order(self):
        """The successful workload cleanup remains dispose-then-unload."""
        test_source = (HCU / "source/main/ps2_m2_ui_lifecycle_test.c").read_text()
        cleanup = c_function_body(
            test_source, r"static boolean step8_workload_cleanup\s*\(")
        assert_order(self, cleanup,
                     "game_dispose_from_old_map();",
                     "game_unload();")
        self.assertIn("CE tears down map-derived state while tags are still owned",
                      cleanup)


if __name__ == "__main__":
    unittest.main()
