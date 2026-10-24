"""Compare CE sound-scenery placement/lifecycle against pinned stock MP tags."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
PACK_ORDER = (
    "longest", "bloodgulch", "beavercreek", "prisoner", "boardingaction",
    "carousel", "chillout", "damnation", "hangemhigh", "putput",
    "ratrace", "sidewinder", "wizard")


def _source_sound_scenery(map_path, source_sha256):
    """Read the stock Xbox scenario placement and palette blocks independently."""
    sys_path = str(ROOT / "submodules/halo-ps2/tools")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from halo2ps2 import tagindex
    from tools.ctag_schema_walk import read_xbox_tag_region

    if hashlib.sha256(map_path.read_bytes()).hexdigest() != source_sha256:
        raise AssertionError(f"pinned source map hash changed: {map_path}")
    index = tagindex.TagIndex.read(map_path)
    image, base, _info = read_xbox_tag_region(map_path)
    scenario = index.scenario
    root = scenario.data_address - base
    if root < 0 or root + 0x2F4 > len(image):
        raise AssertionError(f"scenario root leaves source tag image: {map_path.name}")

    # Cross-check these two offsets and the placement stride against CE's
    # sound_scenery_data_definition in object_types.c below.
    placements_count, placements_address = struct.unpack_from("<iI", image, root + 0x2DC)
    palette_count, palette_address = struct.unpack_from("<iI", image, root + 0x2E8)
    if not (0 <= placements_count <= 32767 and 0 <= palette_count <= 32767):
        raise AssertionError(f"invalid sound-scenery block counts in {map_path.name}")
    placements_offset = placements_address - base if placements_count else 0
    palette_offset = palette_address - base if palette_count else 0
    for count, offset, stride, label in (
            (placements_count, placements_offset, 0x28, "placements"),
            (palette_count, palette_offset, 0x30, "palette")):
        if count and (offset < 0 or offset + count * stride > len(image)):
            raise AssertionError(f"sound-scenery {label} extent leaves {map_path.name}")

    placements = []
    for i in range(placements_count):
        off = placements_offset + i * 0x28
        words = struct.unpack_from("<10I", image, off)
        name_index = struct.unpack_from("<h", image, off + 2)[0]
        palette_index = struct.unpack_from("<h", image, off)[0]
        if name_index != -1:
            raise AssertionError(
                f"named sound scenery needs CE object-name pool setup in {map_path.name}")
        if not 0 <= palette_index < palette_count:
            raise AssertionError(f"invalid sound-scenery palette index in {map_path.name}")
        placements.append({"index": i, "raw_words": words,
                           "palette_index": palette_index})

    palettes = []
    entries_by_id = {entry.tag_id: entry for entry in index.entries}
    for i in range(palette_count):
        off = palette_offset + i * 0x30
        group_bytes = image[off:off + 4]
        group_tag = int.from_bytes(group_bytes, "little")
        reference_index = struct.unpack_from("<I", image, off + 12)[0]
        if group_bytes != b"ecss":
            raise AssertionError(f"sound-scenery palette has group {group_bytes!r}")
        if reference_index != 0xFFFFFFFF:
            target = entries_by_id.get(reference_index)
            if target is None or target.group != "ssce":
                raise AssertionError(
                    f"palette reference {reference_index:#x} is not a sound-scenery tag")
        palettes.append({"index": i, "group_tag": group_tag,
                         "reference_index": reference_index})
    return {"map": map_path.stem, "source_sha256": source_sha256,
            "scenario_datum": scenario.tag_id, "placements": placements,
            "palette": palettes}


def _write_golden_header(path, map_ids, raw):
    maps = []
    placements = []
    palettes = []
    for name in PACK_ORDER:
        map_id = map_ids[name]
        record = raw[name]
        maps.append((map_id, len(record["placements"]), len(record["palette"])))
        for item in record["placements"]:
            placements.append((map_id, item["index"], item["raw_words"]))
        for item in record["palette"]:
            palettes.append((map_id, item["index"], item["group_tag"],
                             item["reference_index"]))

    lines = [
        "#ifndef HCU_MP_SOUND_SCENERY_GOLDEN_H",
        "#define HCU_MP_SOUND_SCENERY_GOLDEN_H",
        "#include <stdint.h>",
        "struct hcu_mp_sound_scenery_map_golden { unsigned map_id, placement_count, palette_count; };",
        "struct hcu_mp_sound_scenery_placement_golden { unsigned map_id, placement_index; uint32_t raw_words[10]; };",
        "struct hcu_mp_sound_scenery_palette_golden { unsigned map_id, palette_index, group_tag; uint32_t reference_index; };",
        f"#define HCU_MP_SOUND_SCENERY_MAP_COUNT {len(maps)}u",
        f"#define HCU_MP_SOUND_SCENERY_PLACEMENT_COUNT {len(placements)}u",
        f"#define HCU_MP_SOUND_SCENERY_PALETTE_COUNT {len(palettes)}u",
        "static const struct hcu_mp_sound_scenery_map_golden hcu_mp_sound_scenery_maps[] = {",
    ]
    lines += [f"\t{{ {m}, {p}, {a} }}," for m, p, a in maps]
    lines += ["};", "static const struct hcu_mp_sound_scenery_placement_golden hcu_mp_sound_scenery_placements[] = {"]
    lines += ["\t{ %d, %d, { %s } }," % (m, i, ", ".join(f"0x{x:08x}u" for x in words))
              for m, i, words in placements]
    lines += ["};", "static const struct hcu_mp_sound_scenery_palette_golden hcu_mp_sound_scenery_palettes[] = {"]
    lines += [f"\t{{ {m}, {i}, 0x{g:08x}u, 0x{r:08x}u }}," for m, i, g, r in palettes]
    lines += ["};", "#endif", ""]
    path.write_text("\n".join(lines))


def _instrumented_main(text):
    declaration = "void hcu_test_mp_sound_environment_query(unsigned map_id,"
    if text.count(declaration) != 1:
        raise AssertionError("MP capacity harness declaration insertion point changed")
    text = text.replace(declaration,
        "void hcu_test_mp_sound_scenery_initialize(void);\n"
        "void hcu_test_mp_sound_scenery_placements(unsigned map_id);\n" + declaration)
    initial = "\tscenario_globals->structure_bsp_index = NONE;\n"
    if text.count(initial) != 1:
        raise AssertionError("MP initial-state insertion point changed")
    text = text.replace(initial, initial +
        "\thcu_test_mp_sound_scenery_initialize();\n")
    load = "\t\t\tassert(scenario_load(scenario));\n"
    if text.count(load) != 1:
        raise AssertionError("MP scenario-load insertion point changed")
    return text.replace(load, load +
        "\t\t\thcu_test_mp_sound_scenery_placements(101u + map);\n")


def _extract_function(source, signature):
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing CE math function: {signature}")
    brace = source.find("{", start)
    depth = 0
    for offset in range(brace, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise AssertionError(f"unterminated CE function body: {signature}")


class MpSoundSceneryPlacementRuntime(unittest.TestCase):
    def test_ce_placement_and_callbacks_match_all_pinned_mp_scenarios(self):
        capacity_path = ROOT / "tests/test_hcu_mp_capacity.py"
        spec = importlib.util.spec_from_file_location("hcu_mp_capacity_for_sound_scenery", capacity_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        # Source-code assertions bind our raw block parser to CE's registered
        # sound-scenery block offsets, type group, datum size, and callbacks.
        definitions = (HCU / "source/objects/object_types.c").read_text()
        expected_definition = (
            '"sound_scenery", \'ssce\', 0x1A8, 0x2DC, 0x2E8, 0x28,')
        self.assertIn(expected_definition, definitions)
        callback_source = (HCU / "source/sound/sound_scenery.c").read_text()
        self.assertIn("sound_scenery_new", callback_source)
        self.assertIn("sound_scenery_delete", callback_source)

        map_ids = {name: 101 + i for i, name in enumerate(PACK_ORDER)}
        raw = {
            name: _source_sound_scenery(
                ROOT / f"build/retail-maps/decompressed/{name}.map",
                module.MP_SOURCE_SHA256[name])
            for name in PACK_ORDER
        }
        self.assertEqual(sum(len(item["placements"]) for item in raw.values()), 13)
        self.assertEqual({name for name, item in raw.items() if item["placements"]},
                         {"beavercreek", "bloodgulch", "damnation"})

        original_read_text = Path.read_text
        original_run = subprocess.run
        with tempfile.TemporaryDirectory(prefix="hcu-mp-sound-scenery-") as temp_name:
            temp = Path(temp_name)
            _write_golden_header(temp / "hcu_mp_sound_scenery_golden.h", map_ids, raw)

            ce_objects = (HCU / "source/objects/objects.c").read_text()
            declaration = "static struct object_globals *object_globals = NULL;"
            if ce_objects.count(declaration) != 1:
                raise AssertionError("CE object-global test seam insertion point changed")
            ce_objects = ce_objects.replace(declaration,
                declaration + "\nstatic struct object_globals hcu_test_object_globals;\n"
                "void hcu_test_mp_sound_scenery_initialize(void)\n{\n"
                "\tmemset(&hcu_test_object_globals, 0, sizeof(hcu_test_object_globals));\n"
                "\tobject_globals = &hcu_test_object_globals;\n}\n")
            helper_prototype = (
                "long hcu_test_object_new(struct object_placement_data *data);\n"
                "void hcu_test_object_placement_data_new("
                "struct object_placement_data *data, long definition_index, "
                "long owner_object_index);\n")
            ce_objects = ce_objects.replace(declaration,
                helper_prototype + declaration, 1)
            old_placement = "object_placement_data_new(&placement_data, definition_index, NONE);"
            old_new = "result = object_new(&placement_data);"
            if ce_objects.count(old_placement) != 1 or ce_objects.count(old_new) != 1:
                raise AssertionError("CE scenario placement allocation seams changed")
            ce_objects = ce_objects.replace(old_placement,
                "hcu_test_object_placement_data_new(&placement_data, definition_index, NONE);")
            ce_objects = ce_objects.replace(old_new,
                "result = hcu_test_object_new(&placement_data);")
            generated_objects = temp / "objects_sound_scenery_runtime.c"
            generated_objects.write_text(ce_objects)
            object_wrapper = (ROOT / "tests/hcu_objects_host32.c").read_text()
            include = '#include "../submodules/halo-ce-universal/source/objects/objects.c"'
            if object_wrapper.count(include) != 1:
                raise AssertionError("CE object source wrapper include changed")
            object_wrapper = object_wrapper.replace(include,
                f'#include "{generated_objects}"')
            generated_object_wrapper = temp / "hcu_objects_sound_scenery_host32.c"
            generated_object_wrapper.write_text(
                "#define halo_ce_random hcu_wind_objects_halo_ce_random\n" + object_wrapper)
            matrix_source = (HCU / "source/math/matrix_math.c").read_text()
            matrix_functions = [
                _extract_function(matrix_source,
                    "void matrix4x3_rotation_from_angles("),
                _extract_function(matrix_source,
                    "void\nmatrix4x3_to_point_and_vectors("),
            ]
            generated_matrix = temp / "ce_sound_scenery_orientation_math.c"
            generated_matrix.write_text(
                '#include "cseries.h"\n#include "math/real_math.h"\n' +
                "\n\n".join(matrix_functions) + "\n")

            def patched_read_text(path, *args, **kwargs):
                text = original_read_text(path, *args, **kwargs)
                resolved = path.resolve() if path.exists() else path
                if resolved == ROOT / "tests/hcu_scenario_bsp_switch_main.c":
                    signature = (
                        "void *object_get_and_verify_type(long object_index, "
                        "unsigned long valid_type_flags)\n{\n")
                    if text.count(signature) != 1:
                        raise AssertionError("host object-lookup fixture seam changed")
                    insertion = (
                        "\textern long hcu_test_mp_sound_scenery_current_object;\n"
                        "\textern struct object_datum hcu_test_mp_sound_scenery_object;\n"
                        "\textern unsigned hcu_test_mp_sound_scenery_type_lookup_calls;\n"
                        "\tif (object_index == hcu_test_mp_sound_scenery_current_object) {\n"
                        "\t\tassert(valid_type_flags == _object_mask_sound_scenery);\n"
                        "\t\thcu_test_mp_sound_scenery_type_lookup_calls++;\n"
                        "\t\treturn &hcu_test_mp_sound_scenery_object;\n"
                        "\t}\n")
                    text = text.replace(signature, signature + insertion)
                return text

            def patched_run(command, *args, **kwargs):
                if (isinstance(command, (list, tuple)) and command and
                        Path(str(command[0])).name == "gcc" and
                        "-o" in command and
                        any("mp-capacity" in str(part) for part in command)):
                    command = list(command)
                    build_temp = Path(command[command.index("-o") + 1]).parent
                    (build_temp / "hcu_mp_sound_scenery_golden.h").write_text(
                        (temp / "hcu_mp_sound_scenery_golden.h").read_text())
                    main_source = ROOT / "tests/hcu_mp_capacity_main.c"
                    generated_main = build_temp / "hcu_mp_sound_scenery_main.c"
                    generated_main.write_text(_instrumented_main(original_read_text(main_source)))
                    command[command.index(str(main_source))] = str(generated_main)
                    object_source_index = next((i for i, item in enumerate(command)
                        if Path(str(item)).name == "matrix_hcu_objects_host32.c"), None)
                    if object_source_index is None:
                        raise AssertionError("compiled MP fixture no longer includes CE object host TU: " +
                            " ".join(str(item) for item in command))
                    command[object_source_index] = str(generated_object_wrapper)
                    command.extend([
                        "-Wl,--wrap=object_type_place",
                        str(HCU / "source/sound/sound_scenery.c"),
                        str(ROOT / "tests/hcu_mp_sound_scenery_runtime_host32.c"),
                        str(generated_matrix),
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

        retained_relative = Path(os.environ.get(
            "HCU_MP_CAPACITY_RETENTION_DIR", "build/m2-mp-weather-wind-13"))
        retained = ROOT / retained_relative
        output = (retained / "run.log").read_text()
        rows = re.findall(
            r"^mp-sound-scenery map=(\d+) placements=(\d+) palette=(\d+) "
            r"ce_created=(\d+) callback_cycles=(\d+) status=passed$",
            output, re.MULTILINE)
        expected = {
            (map_ids[name], len(raw[name]["placements"]), len(raw[name]["palette"]))
            for name in PACK_ORDER
        }
        self.assertEqual(len(rows), 2 * len(PACK_ORDER))
        self.assertEqual({(int(row[0]), int(row[1]), int(row[2])) for row in rows}, expected)
        self.assertEqual(sum(int(row[1]) for row in rows), 2 * 13)
        self.assertEqual(sum(int(row[3]) for row in rows), 2 * 13)
        self.assertEqual(sum(int(row[4]) for row in rows), 2 * 13)


if __name__ == "__main__":
    unittest.main()
