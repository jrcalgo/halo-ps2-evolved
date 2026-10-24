"""Exercise CE's real Prisoner breakable-surface damage state machine.

The broad 13-map fixture owns package conversion/loading and collision goldens.
This focused driver instruments only its generated host harness, links the CE
breakable implementation, and leaves CE particles/audio out of this state test.
"""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def _effectless_ce_breakable_source(output):
    source_path = HCU / "source/physics/breakable_surfaces.c"
    text = source_path.read_text()
    signature = (
        "static void breakable_surface_effect(\n"
        "\tshort breakable_surface_index,\n"
        "\tconst struct damage_data *damage_data,\n"
        "\tlong seed_surface_index)\n{")
    start = text.rfind(signature)
    if start < 0:
        raise AssertionError("could not locate CE breakable effect implementation")
    # It is the final function in this translation unit. Replace only its
    # body so its particle/audio geometry dependencies do not enter this
    # isolated state-machine test; public CE damage/reset code remains verbatim.
    replacement = (
        "static void breakable_surface_effect(\n"
        "\tshort breakable_surface_index,\n"
        "\tconst struct damage_data *damage_data,\n"
        "\tlong seed_surface_index)\n{\n"
        "\t(void)breakable_surface_index;\n"
        "\t(void)damage_data;\n"
        "\t(void)seed_surface_index;\n"
        "}\n")
    text = text[:start] + replacement
    text = text.replace("static __inline real breakable_surface_plane_distance(",
                        "__inline real breakable_surface_plane_distance(")
    output.write_text(text)
    return source_path


def _production_fixture_source(text):
    declaration = "static byte retail_breakable_surface_flags[MAXIMUM_BREAKABLE_SURFACES_PER_MAP / 8];"
    if text.count(declaration) != 1:
        raise AssertionError("fixture breakable bitmap declaration changed")
    text = text.replace(declaration, "static byte *retail_breakable_surface_flags;")
    adapter_start = text.index("/* This transaction fixture has no gameplay tick or breakable-surface damage.")
    adapter_end = text.index("short global_current_collision_user_depth", adapter_start)
    text = text[:adapter_start] + text[adapter_end:]
    old_memset = (
        "memset(retail_breakable_surface_flags, 0xFF,\n"
        "\t\tsizeof(retail_breakable_surface_flags));")
    if old_memset not in text:
        raise AssertionError("fixture pre-load breakable memset changed")
    text = text.replace(old_memset, "/* CE breakable globals initialize the bitmap. */")
    text = text.replace("sizeof(retail_breakable_surface_flags)",
                        "(MAXIMUM_BREAKABLE_SURFACES_PER_MAP / 8)")
    return text


def _instrumented_mp_main(text):
    text = text.replace(
        "void hcu_test_mp_sound_environment_query(unsigned map_id,",
        "void hcu_test_breakable_runtime_begin_map(void);\n"
        "void hcu_test_prisoner_breakable_runtime(void);\n"
        "void hcu_test_mp_sound_environment_query(unsigned map_id,")
    bind = "\t\t\tassert(scenario_load(scenario));\n"
    if text.count(bind) != 1:
        raise AssertionError("scenario-load insertion point changed")
    text = text.replace(bind, bind +
        "\t\t\thcu_test_breakable_runtime_begin_map();\n"
        "\t\t\tretail_breakable_surface_flags = breakable_surface_flags_get();\n")
    begin = "\tscenario_globals->structure_bsp_index = NONE;\n"
    if text.count(begin) != 1:
        raise AssertionError("initial scenario state insertion point changed")
    text = text.replace(begin, begin + "\thcu_test_breakable_runtime_begin_map();\n")
    breakable = "\t\tassert(breakable->breakable_index == 1);\n"
    if text.count(breakable) != 1:
        raise AssertionError("Prisoner breakable insertion point changed")
    text = text.replace(breakable, breakable +
        "\t\thcu_test_prisoner_breakable_runtime();\n")
    old_breakable_setup = (
        "\t\tmemcpy(flags_before, retail_breakable_surface_flags, sizeof(flags_before));\n"
        "\t\tbreakable_bit = (byte)(1u << (breakable->breakable_index & 7));\n"
        "\t\tassert((flags_before[breakable->breakable_index >> 3] & breakable_bit) == 0);")
    new_breakable_setup = (
        "\t\tbreakable_bit = (byte)(1u << (breakable->breakable_index & 7));\n"
        "\t\tretail_breakable_surface_flags[breakable->breakable_index >> 3] &=\n"
        "\t\t\t(byte)~breakable_bit;\n"
        "\t\tmemcpy(flags_before, retail_breakable_surface_flags, sizeof(flags_before));\n"
        "\t\tassert((flags_before[breakable->breakable_index >> 3] & breakable_bit) == 0);")
    if text.count(old_breakable_setup) != 1:
        raise AssertionError("Prisoner legacy breakable-query setup changed")
    text = text.replace(old_breakable_setup, new_breakable_setup)
    return text


class PrisonerBreakableRuntime(unittest.TestCase):
    def test_ce_damage_break_collision_and_reset(self):
        capacity_path = ROOT / "tests/test_hcu_mp_capacity.py"
        spec = importlib.util.spec_from_file_location("hcu_mp_capacity_for_breakable", capacity_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        original_read_text = Path.read_text
        original_run = subprocess.run
        with tempfile.TemporaryDirectory(prefix="hcu-prisoner-breakable-") as temp_name:
            temp = Path(temp_name)
            generated_effectless = temp / "breakable_surfaces_state_only.c"
            _effectless_ce_breakable_source(generated_effectless)

            def patched_read_text(path, *args, **kwargs):
                resolved = path.resolve() if path.exists() else path
                if resolved == ROOT / "tests/hcu_scenario_bsp_switch_main.c":
                    return _production_fixture_source(original_read_text(path, *args, **kwargs))
                return original_read_text(path, *args, **kwargs)

            def patched_run(command, *args, **kwargs):
                if (isinstance(command, (list, tuple)) and command and
                        Path(str(command[0])).name == "gcc" and
                        "-o" in command and
                        any("mp-capacity" in str(part) for part in command)):
                    command = list(command)
                    output_index = command.index("-o") + 1
                    build_temp = Path(command[output_index]).parent
                    main_source = ROOT / "tests/hcu_mp_capacity_main.c"
                    generated_main = build_temp / "hcu_mp_capacity_breakable_main.c"
                    generated_main.write_text(_instrumented_mp_main(main_source.read_text()))
                    command[command.index(str(main_source))] = str(generated_main)
                    command.extend([
                        "-Wl,--wrap=tag_get",
                        "-Wl,--wrap=tag_index_is_group",
                        str(generated_effectless),
                        str(ROOT / "tests/hcu_mp_breakable_runtime_host32.c"),
                    ])
                return original_run(command, *args, **kwargs)

            Path.read_text = patched_read_text
            subprocess.run = patched_run
            try:
                case = module.MultiplayerHostCollisionMatrix(
                    "test_host_sized_13_map_lifecycle_and_collision")
                result = unittest.TestResult()
                case.run(result)
            finally:
                Path.read_text = original_read_text
                subprocess.run = original_run

        if result.skipped:
            self.skipTest(result.skipped[0][1])
        self.assertEqual(result.errors, [], "\n".join(error for _test, error in result.errors))
        self.assertEqual(result.failures, [], "\n".join(failure for _test, failure in result.failures))
        self.assertEqual(result.testsRun, 1)


if __name__ == "__main__":
    unittest.main()
