"""Guard the C2.3 diagnostic gates: production PS2 must not keep diagnostic-only storage."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def read(path):
    return path.read_text(encoding="ascii")


class HcuC2DiagnosticGate(unittest.TestCase):
    def test_path_obstacle_replay_storage_is_gated(self):
        source = read(HCU / "source/ai/path_obstacle_avoidance.c")
        self.assertIn("#if defined(HALO_PS2) && !defined(HCU_AI_DEBUG_DIAGNOSTICS)\n#define PATH_OBSTACLE_DEBUG_STUB", source)
        self.assertRegex(source, r"#ifndef PATH_OBSTACLE_DEBUG_STUB\nstatic struct obstacle_path debug_path;\nstatic struct obstacles debug_obstacles;\n#endif")
        self.assertRegex(source, r"#ifndef PATH_OBSTACLE_DEBUG_STUB\n\t\t\t\tdebug_obstacles= \*obstacles;")
        self.assertRegex(source, r"void render_debug_obstacle_path\(\n\tvoid\)\n\{\n#ifndef PATH_OBSTACLE_DEBUG_STUB")

    def test_cheat_strings_are_gated(self):
        source = read(HCU / "source/game/cheats.c")
        self.assertIn("#if defined(HALO_PS2) && !defined(HCU_DEBUG_DIAGNOSTICS)\n#define CHEATS_DEBUG_STUB", source)
        self.assertRegex(source, r"#ifndef CHEATS_DEBUG_STUB\nstatic char cheat_strings\[")
        self.assertRegex(source, r"#ifndef CHEATS_DEBUG_STUB\n\tif \(cheat\.controller_enabled\)")
        self.assertRegex(source, r"void cheats_load\(\n\tvoid\)\n\{\n#ifdef CHEATS_DEBUG_STUB\n\treturn;\n#else")

    def test_console_history_is_gated(self):
        source = read(HCU / "source/main/console.c")
        self.assertIn("#if defined(HALO_PS2) && !defined(HCU_DEBUG_DIAGNOSTICS)\n#define CONSOLE_DEBUG_STUB", source)
        self.assertIn("#ifdef CONSOLE_DEBUG_STUB\n\tMAXIMUM_NUMBER_OF_PREVIOUS_COMMANDS = 1,", source)

    def test_profile_graph_values_are_gated(self):
        source = read(HCU / "source/interface/interface.c")
        self.assertIn("#if defined(HALO_PS2) && !defined(HCU_DEBUG_DIAGNOSTICS)\n#define PROFILE_GRAPH_DEBUG_STUB", source)
        self.assertIn("#ifdef PROFILE_GRAPH_DEBUG_STUB\nshort profile_graph_value_count = 0;\nstruct profile_value profile_graph_values[1] =", source)
        self.assertRegex(source, r"\{ \"dt\", \"dt\", &global_real_argb_grey, NONE, NONE, FALSE, TRUE \},\n\};\n#endif")

    def test_ai_profile_is_not_shrunk_without_ai_cross_lane_change(self):
        # ai.c keeps January offset asserts for the 0x88 meter layout; shrinking
        # the meter history here breaks them, so ai_profile stays ungated.
        self.assertNotIn("AI_PROFILE_DEBUG_STUB", read(HCU / "source/ai/ai_profile.h"))
        self.assertIn("AI_METER_HISTORY_TICKS = 60", read(HCU / "source/ai/ai_profile.h"))


if __name__ == "__main__":
    unittest.main()
