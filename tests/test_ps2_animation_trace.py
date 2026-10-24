"""Opt-in PS2 animation observer has bounded, resettable record semantics."""
import subprocess
from pathlib import Path
import tempfile
import re
import unittest
import hashlib
import json
import struct
import zlib


class Ps2AnimationTraceTests(unittest.TestCase):
    @staticmethod
    def extract_function(source, name):
        match = re.search(r"(?:byte|void|int)\s*\*?\s*" + re.escape(name) + r"\s*\([^)]*\)\s*\{", source)
        if not match:
            raise AssertionError(f"could not locate function {name}")
        opening = source.find("{", match.start())
        depth = 0
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[match.start():index + 1]
        raise AssertionError(f"unterminated function {name}")

    def test_fixed_recorder_capacity_and_overflow(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        with tempfile.TemporaryDirectory(prefix="ps2-animation-trace-") as temporary:
            for event_first in (False, True):
                exe = Path(temporary) / ("trace-event-first" if event_first else "trace-context-first")
                command = [
                    "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                    "-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
                    "-I", str(hcu / "port/ps2/include"),
                    str(root / "tests/ps2_animation_trace_main.c"),
                    str(hcu / "port/ps2/src/ps2_animation_trace.c"),
                ]
                if event_first:
                    command.append("-DTEST_TRACE_EVENT_BIND_FIRST=1")
                command.extend(["-o", str(exe)])
                subprocess.run(command, check=True)
                capture = subprocess.check_output([str(exe)])
                self.assertEqual(capture[:8], b"H2ANIMT1")
                elf = Path(temporary) / "guest.elf"
                elf.write_bytes(b"\x7fELF-test-image")
                provenance = Path(temporary) / "provenance.json"
                provenance.write_text(json.dumps({
                    "parent_commit": "1" * 40,
                    "hcu_commit": "2" * 40,
                    "halo_ps2_commit": "3" * 40,
                    "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
                    "source_manifest_sha256": "4" * 64,
                    "build_profile": "animation-trace-test",
                    "toolchain_id": "host-c-test",
                }))
                capture_path = Path(temporary) / "capture.bin"
                capture_path.write_bytes(capture)
                decoded = Path(temporary) / "decoded.json"
                decoder = root / "tools/decode_ps2_animation_trace.py"
                result = subprocess.run([
                    "python3", str(decoder), str(capture_path), "--elf", str(elf),
                    "--provenance", str(provenance), "--output", str(decoded),
                ], check=True, capture_output=True, text=True)
                self.assertIn('"events": 8', result.stdout)
                decoded_json = json.loads(decoded.read_text())
                self.assertEqual(decoded_json["summary"]["complete"], True)
                self.assertEqual(decoded_json["events"][0]["context_token"], 0)
                self.assertEqual(decoded_json["events"][5]["context"]["fields"]["datum"], 0x1234)

    def test_decoder_rejects_incomplete_corrupt_tokens_and_wrong_pins(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        decoder = root / "tools/decode_ps2_animation_trace.py"
        with tempfile.TemporaryDirectory(prefix="ps2-animation-decode-negative-") as temporary:
            temp = Path(temporary)
            exe = temp / "trace"
            subprocess.run([
                "cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                "-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
                "-I", str(hcu / "port/ps2/include"),
                str(root / "tests/ps2_animation_trace_main.c"),
                str(hcu / "port/ps2/src/ps2_animation_trace.c"), "-o", str(exe),
            ], check=True)
            valid = subprocess.check_output([str(exe)])
            elf = temp / "guest.elf"
            elf.write_bytes(b"\x7fELF-test-image")
            provenance = temp / "provenance.json"
            pin = {
                "parent_commit": "1" * 40, "hcu_commit": "2" * 40,
                "halo_ps2_commit": "3" * 40,
                "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
                "source_manifest_sha256": "4" * 64,
                "build_profile": "animation-trace-test", "toolchain_id": "host-c-test",
            }
            provenance.write_text(json.dumps(pin))

            def run_capture(name, data, pin_data=pin):
                capture_path = temp / f"{name}.bin"
                capture_path.write_bytes(data)
                provenance.write_text(json.dumps(pin_data))
                return subprocess.run([
                    "python3", str(decoder), str(capture_path), "--elf", str(elf),
                    "--provenance", str(provenance),
                ], capture_output=True, text=True)

            incomplete = bytearray(valid)
            struct.pack_into("<I", incomplete, 20, 1)
            self.assertEqual(run_capture("incomplete", incomplete).returncode, 2)
            self.assertIn("incomplete", run_capture("incomplete-again", incomplete).stderr)

            corrupt = bytearray(valid)
            corrupt[-1] ^= 0x80
            self.assertIn("CRC-32", run_capture("corrupt", corrupt).stderr)
            self.assertIn("length mismatch", run_capture("truncated", valid[:-1]).stderr)

            bad_token = bytearray(valid)
            struct.pack_into("<H", bad_token, 28 + 22, 2)
            struct.pack_into("<I", bad_token, 24, zlib.crc32(bad_token[28:]) & 0xFFFFFFFF)
            self.assertIn("does not identify its paired row", run_capture("token", bad_token).stderr)

            unknown_mask = bytearray(valid)
            struct.pack_into("<H", unknown_mask, 28 + 24 + 26, 0x0100)
            struct.pack_into("<I", unknown_mask, 24, zlib.crc32(unknown_mask[28:]) & 0xFFFFFFFF)
            self.assertIn("invalid context encoding", run_capture("mask", unknown_mask).stderr)

            wrong_pin = dict(pin)
            wrong_pin["elf_sha256"] = "0" * 64
            self.assertIn("does not match", run_capture("wrong-pin", valid, wrong_pin).stderr)

    def test_guest_trace_summary_is_post_load_and_aggregated_not_per_access(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "submodules/halo-ce-universal/source/game/game.c").read_text()
        marker = source.index('printf("HALO_PS2_LOCAL m2-animation-trace count=')
        success = source.rindex("if (scenario_load(options->map_name))", 0, marker)
        self.assertLess(success, marker)
        self.assertIn("ps2_animation_trace_count()", source[marker:marker + 300])
        self.assertIn("ps2_animation_trace_dropped()", source[marker:marker + 300])

    def test_pose_phase_scopes_are_opt_in_and_restore_at_ce_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        objects = (hcu / "source/objects/objects.c").read_text()
        units = (hcu / "source/units/units.c").read_text()
        first_person = (hcu / "source/interface/first_person_weapons.c").read_text()
        object_pose = self.extract_function(objects, "object_compute_node_matrices")
        unit_pose = self.extract_function(units, "unit_preprocess_node_orientations")
        first_person_pose = self.extract_function(first_person, "first_person_weapon_build_node_matrices")
        for function, phase in ((object_pose, "object_pose"), (unit_pose, "unit_pose"),
                                (first_person_pose, "first_person_pose")):
            enter = f"_ps2_animation_trace_phase_{phase}"
            self.assertIn(enter, function)
            self.assertIn("ps2_animation_trace_phase_set(previous_animation_trace_phase)", function)
            self.assertIn("ps2_animation_trace_context_set(&previous_animation_trace_context)", function)
            self.assertLess(function.index(enter), function.rindex("ps2_animation_trace_phase_set(previous_animation_trace_phase)"))
        self.assertIn("animation_get_node_orientations(model, animation, frame_index, node_orientations)", object_pose)
        self.assertIn("overlay_animation_apply(", unit_pose)
        self.assertEqual(first_person_pose.count("animation_get_node_orientations("), 2)
        self.assertIn("_ps2_animation_trace_context_datum", object_pose)
        self.assertIn("_ps2_animation_trace_context_animation", object_pose)
        self.assertIn("_ps2_animation_trace_context_graph", unit_pose)
        self.assertIn("_ps2_animation_trace_context_owner", first_person_pose)

    def test_map_tick_and_render_clocks_come_from_authoritative_owners(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        game = (hcu / "source/game/game.c").read_text()
        render = (hcu / "port/ps2/src/ps2_render.c").read_text()
        map_service = (root / "src/stream/hcu_map_service.c").read_text()
        tick = self.extract_function(game, "game_tick")
        render_advance = self.extract_function(render, "ps2_render_frame_state_advance")
        loader = self.extract_function(map_service, "map_loader")
        unloader = self.extract_function(map_service, "map_unloader")
        self.assertLess(tick.index("game_globals->active"),
                        tick.index("ps2_animation_trace_tick_advance()"))
        self.assertLess(tick.index("ps2_animation_trace_tick_advance()"),
                        tick.index("units_update()"))
        self.assertLess(render_advance.index("render.frame_index++"),
                        render_advance.index("ps2_animation_trace_render_frame_set("))
        self.assertIn("ps2_animation_trace_map_epoch_advance()", loader)
        self.assertIn("ps2_animation_trace_map_epoch_advance()", unloader)

    def test_ce_frame_accessor_hook_preserves_pointer_and_records_bounded_spans(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        source = (hcu / "source/models/model_animation_definitions.c").read_text()
        function = self.extract_function(source, "animation_get_frame_data")
        preamble = r"""
            #include <assert.h>
            #include <stdio.h>
            typedef unsigned char byte;
            typedef int boolean;
            #define TRUE 1
            #define FALSE 0
            #define _animation_compressed_bit 0
            #define TEST_FLAG(value, bit) (((value) & (1U << (bit))) != 0)
            #define match_assert(file, line, condition) ((void)0)
            struct tag_data { long size; void *address; };
            struct animation {
                unsigned int flags;
                short frame_count;
                short frame_size;
                long compressed_data_offset;
                struct tag_data data;
                struct tag_data frame_info;
            };
            static int hs_model_animation_compression_enabled;
            static byte *tag_data_get_pointer(struct tag_data const *data, long offset, long size)
            {
                (void)size;
                return (byte *)data->address + offset;
            }
            #if defined(HALO_PS2_M2_ANIMATION_TRACE)
            #include "ps2_animation_trace.h"
            #endif
        """
        main = r"""
            int main(void)
            {
                byte bytes[32];
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                static struct ps2_animation_trace_event events[PS2_ANIMATION_TRACE_CAPACITY];
                static struct ps2_animation_trace_context contexts[PS2_ANIMATION_TRACE_CAPACITY];
                #endif
                struct animation a;
                byte *result;
                long offsets[4];
                a.flags = 0; a.frame_count = 2; a.frame_size = 4;
                a.compressed_data_offset = 4;
                a.data.size = 12; a.data.address = bytes;
                a.frame_info.size = 0; a.frame_info.address = 0;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_bind(events, PS2_ANIMATION_TRACE_CAPACITY));
                assert(ps2_animation_trace_bind_contexts(contexts, PS2_ANIMATION_TRACE_CAPACITY));
                ps2_animation_trace_reset();
                #endif
                result = animation_get_frame_data(&a, 1);
                offsets[0] = result - bytes;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_count() == 1);
                assert(ps2_animation_trace_events()[0].base_identity == (unsigned long)&a.data);
                assert(ps2_animation_trace_events()[0].offset == 4);
                assert(ps2_animation_trace_events()[0].bytes == 4);
                assert(ps2_animation_trace_events()[0].accepted == 1);
                #endif
                a.frame_size = 8;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                ps2_animation_trace_reset();
                #endif
                result = animation_get_frame_data(&a, 1);
                offsets[1] = result - bytes;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_count() == 1);
                assert(ps2_animation_trace_events()[0].offset == 8);
                assert(ps2_animation_trace_events()[0].bytes == 8);
                assert(ps2_animation_trace_events()[0].accepted == 0);
                #endif
                a.flags = 1U << _animation_compressed_bit;
                a.frame_size = 4;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                hs_model_animation_compression_enabled = 1;
                ps2_animation_trace_reset();
                #endif
                result = animation_get_frame_data(&a, 1);
                offsets[2] = result - bytes;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_events()[0].offset == 4);
                assert(ps2_animation_trace_events()[0].bytes == 8);
                assert(ps2_animation_trace_events()[0].accepted == 1);
                #endif
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                ps2_animation_trace_reset();
                #endif
                /* The assertion is disabled in this fixture. Keep the
                 * returned in-bounds pointer unchanged, but reject the
                 * logically invalid index in the observer contract. */
                a.flags = 0;
                hs_model_animation_compression_enabled = 0;
                result = animation_get_frame_data(&a, 2);
                offsets[3] = result - bytes;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_count() == 1);
                assert(ps2_animation_trace_events()[0].offset == 8);
                assert(ps2_animation_trace_events()[0].accepted == 0);
                #endif
                printf("%ld,%ld,%ld,%ld\n", offsets[0], offsets[1], offsets[2], offsets[3]);
                return 0;
            }
        """
        with tempfile.TemporaryDirectory(prefix="ps2-animation-hook-") as temporary:
            temp = Path(temporary)
            shared = temp / "hook.c"
            shared.write_text(preamble + "\n" + function + "\n" + main)
            outputs = []
            for enabled in (False, True):
                exe = temp / ("trace-on" if enabled else "trace-off")
                command = ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                           "-Wno-unused-parameter", "-I", str(hcu / "port/ps2/include")]
                if enabled:
                    command.extend(["-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
                                    str(hcu / "port/ps2/src/ps2_animation_trace.c")])
                command.extend([str(shared), "-o", str(exe)])
                subprocess.run(command, check=True)
                outputs.append(subprocess.check_output([str(exe)], text=True).strip())
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], "4,8,4,8")

    def test_ce_frame_info_accessor_hook_preserves_valid_and_rejected_behavior(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        source = (hcu / "source/models/model_animation_definitions.c").read_text()
        function = self.extract_function(source, "animation_get_frame_info")
        preamble = r"""
            #include <assert.h>
            #include <stdio.h>
            #include <string.h>
            typedef unsigned char byte;
            typedef float real;
            typedef int boolean;
            #define TRUE 1
            #define FALSE 0
            #define match_assert(file, line, condition) ((void)0)
            struct tag_data { long size; void *address; };
            struct animation {
                short frame_count;
                struct tag_data frame_info;
                char name[32];
            };
            static int model_data_report_once(struct animation const *animation)
            { (void)animation; return 0; }
            static void error(int kind, char const *format, ...)
            { (void)kind; (void)format; }
            #define _error_silent 0
            #define csmemset memset
            static byte *tag_data_get_pointer(struct tag_data const *data,
                long offset, long size)
            { (void)size; return (byte *)data->address + offset; }
            #if defined(HALO_PS2_M2_ANIMATION_TRACE)
            #include "ps2_animation_trace.h"
            #endif
        """
        main = r"""
            int main(void)
            {
                byte bytes[24] = {0};
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                static struct ps2_animation_trace_event events[PS2_ANIMATION_TRACE_CAPACITY];
                static struct ps2_animation_trace_context contexts[PS2_ANIMATION_TRACE_CAPACITY];
                #endif
                struct animation a;
                byte *valid, *invalid, *past_end;
                a.frame_count = 3;
                a.frame_info.size = sizeof bytes;
                a.frame_info.address = bytes;
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_bind(events, PS2_ANIMATION_TRACE_CAPACITY));
                assert(ps2_animation_trace_bind_contexts(contexts, PS2_ANIMATION_TRACE_CAPACITY));
                ps2_animation_trace_reset();
                #endif
                valid = animation_get_frame_info(&a, 2, 4);
                assert(valid == bytes + 8);
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_count() == 1);
                assert(ps2_animation_trace_events()[0].site == _ps2_animation_trace_frame_info);
                assert(ps2_animation_trace_events()[0].base_identity == (unsigned long)&a.frame_info);
                assert(ps2_animation_trace_events()[0].offset == 8);
                assert(ps2_animation_trace_events()[0].bytes == 4);
                assert(ps2_animation_trace_events()[0].accepted == 1);
                ps2_animation_trace_reset();
                #endif
                invalid = animation_get_frame_info(&a, 2, 20);
                assert(invalid != bytes);
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_count() == 1);
                assert(ps2_animation_trace_events()[0].site == _ps2_animation_trace_frame_info);
                assert(ps2_animation_trace_events()[0].offset == 40);
                assert(ps2_animation_trace_events()[0].bytes == 20);
                assert(ps2_animation_trace_events()[0].accepted == 0);
                #endif
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                ps2_animation_trace_reset();
                #endif
                /* An in-range byte extent is still not a valid frame: the
                 * frame index equals frame_count. */
                past_end = animation_get_frame_info(&a, 3, 4);
                assert(past_end == bytes + 12);
                #if defined(HALO_PS2_M2_ANIMATION_TRACE)
                assert(ps2_animation_trace_count() == 1);
                assert(ps2_animation_trace_events()[0].offset == 12);
                assert(ps2_animation_trace_events()[0].accepted == 0);
                #endif
                printf("%ld,%d,%ld\n", valid - bytes,
                    invalid != bytes && invalid[0] == 0, past_end - bytes);
                return 0;
            }
        """
        with tempfile.TemporaryDirectory(prefix="ps2-animation-info-hook-") as temporary:
            temp = Path(temporary)
            shared = temp / "hook.c"
            shared.write_text(preamble + "\n" + function + "\n" + main)
            outputs = []
            for enabled in (False, True):
                exe = temp / ("trace-on" if enabled else "trace-off")
                command = ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                           "-Wno-unused-parameter", "-I", str(hcu / "port/ps2/include")]
                if enabled:
                    command.extend(["-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
                                    str(hcu / "port/ps2/src/ps2_animation_trace.c")])
                command.extend([str(shared), "-o", str(exe)])
                subprocess.run(command, check=True)
                outputs.append(subprocess.check_output([str(exe)], text=True).strip())
            self.assertEqual(outputs, ["8,1,12", "8,1,12"])

    def test_observer_sites_are_inside_the_exact_reader_and_diagnostic_guard(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        checks = (
            ("source/models/model_animation_definitions.c", "animation_get_frame_data",
             "tag_data_get_pointer", "_ps2_animation_trace_frame_data"),
            ("source/models/model_animation_definitions.c", "animation_get_frame_info",
             "tag_data_get_pointer", "_ps2_animation_trace_frame_info"),
            ("source/models/model_animations.c", "animation_get_x_offsets",
             "animation->frame_info.address", "_ps2_animation_trace_frame_info_bulk"),
            ("source/models/model_animations.c", "animation_get_node_orientations",
             "animation_get_default_data", "_ps2_animation_trace_default_data"),
            ("source/models/model_animations.c", "animation_get_keyframe_rotation",
             "tag_data_get_pointer(&animation->data", "_ps2_animation_trace_compressed_rotation"),
            ("source/models/model_animations.c", "animation_get_keyframe_translation",
             "tag_data_get_pointer(&animation->data", "_ps2_animation_trace_compressed_translation"),
            ("source/models/model_animations.c", "animation_get_keyframe_scale",
             "tag_data_get_pointer(&animation->data", "_ps2_animation_trace_compressed_scale"),
        )
        for relative, function_name, access, site in checks:
            function = self.extract_function((hcu / relative).read_text(), function_name)
            self.assertIn(access, function, f"{function_name} lost expected access")
            guard = "#if defined(HALO_PS2) && defined(HALO_PS2_M2_ANIMATION_TRACE)"
            call = "ps2_animation_trace_record(" + site
            self.assertIn(guard, function)
            self.assertIn(call, function)
            guard_at = function.index(guard)
            call_at = function.index(call)
            self.assertLess(guard_at, call_at)
            self.assertLess(call_at, function.index("#endif", call_at))

        # Schema validation uses a non-void helper return type, so extract its
        # body separately while preserving the same guarded-site invariant.
        schema_source = (hcu / "port/linux/game/tag_schema_models.c").read_text()
        schema_name = "animation_data_problem("
        schema_start = schema_source.index(schema_name)
        schema_open = schema_source.index("{", schema_start)
        depth = 0
        schema_end = schema_open
        for schema_end in range(schema_open, len(schema_source)):
            if schema_source[schema_end] == "{":
                depth += 1
            elif schema_source[schema_end] == "}":
                depth -= 1
                if depth == 0:
                    schema_end += 1
                    break
        schema_function = schema_source[schema_start:schema_end]
        schema_guard = "#if defined(HALO_PS2) && defined(HALO_PS2_M2_ANIMATION_TRACE)"
        schema_call = "ps2_animation_trace_record(_ps2_animation_trace_schema_data"
        self.assertIn("animation->data.address", schema_function)
        self.assertIn(schema_guard, schema_function)
        self.assertIn(schema_call, schema_function)
        schema_call_at = schema_function.index(schema_call)
        self.assertLess(schema_function.index(schema_guard), schema_call_at)
        self.assertLess(schema_call_at, schema_function.index("#endif", schema_call_at))

    def test_source_hooks_are_diagnostic_gated(self):
        root = Path(__file__).resolve().parents[1]
        hcu = root / "submodules/halo-ce-universal"
        for relative in (
            "source/models/model_animation_definitions.c",
            "source/models/model_animations.c",
            "port/linux/game/tag_schema_models.c",
        ):
            source = (hcu / relative).read_text()
            self.assertIn("defined(HALO_PS2_M2_ANIMATION_TRACE)", source)
            self.assertTrue("port: diagnostic" in source or "port: schema-phase" in source)
        manifest = (hcu / "port/ps2/port.json").read_text()
        self.assertIn("port/ps2/src/ps2_animation_trace.c", manifest)
        closure = (root / "tools/hcu_ps2_closure.py").read_text()
        self.assertIn("--m2-animation-trace", closure)
        self.assertIn("HALO_PS2_M2_ANIMATION_TRACE", closure)


if __name__ == "__main__":
    unittest.main()
