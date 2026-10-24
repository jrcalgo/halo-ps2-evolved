"""Guard PS2 source closure classifications against unsafe co-op stubbing."""
from pathlib import Path
import json
import re
import shutil
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tools"))
from hcu_ps2_closure import (  # noqa: E402
    PRODUCTION_BITMAP_ROOTS,
    classify,
    rooted_symbol_definition_counts,
    selected_sources,
)
from hcu_ps2_memory_audit import (  # noqa: E402
    apply_region_candidates,
    attach_owners,
    parse_load_accounting,
    parse_file_backed_allocated_bytes,
    parse_map,
    parse_nm,
)
from hcu_ps2_link import SKIP, emit  # noqa: E402
from build_toolchain import environment  # noqa: E402
from hcu_ps2_closure import undefined_symbols  # noqa: E402
from host_abi32 import flags as host_abi32_flags  # noqa: E402


class HcuPs2ClosureClassification(unittest.TestCase):
    def test_production_bitmap_providers_are_explicit_roots_and_unique(self):
        closure = (ROOT / "tools/hcu_ps2_closure.py").read_text()
        parent_probe = (ROOT / "tools/hcu_parent_link_probe.py").read_text()
        for symbol in PRODUCTION_BITMAP_ROOTS:
            self.assertIn(f'"{symbol}"', closure)
        self.assertIn("roots.extend(PRODUCTION_BITMAP_ROOTS)", closure)
        self.assertIn("count != 1", closure)
        self.assertIn("production_bitmap_provider_definition_counts", parent_probe)

        sample_nm = """\
00100000 T halo_ps2_bitmap_requests_init
00100080 T halo_ps2_bitmap_requests_end
00100100 T halo_ps2_bitmap_requests_register_consumer
00100180 T halo_ps2_bitmap_requests_clear_consumer
00100200 T halo_ps2_bitmap_requests_acquire
00100280 T halo_ps2_bitmap_requests_release
00100300 T halo_ps2_bitmap_frame_consumer_register
00100380 T halo_ps2_bitmap_frame_consumer_clear
00100400 T halo_ps2_bitmap_frame_is_active
00200000 D halo_ps2_real_producer_descriptor_instance
00100500 T interface_draw_screen
"""
        counts = rooted_symbol_definition_counts(sample_nm, PRODUCTION_BITMAP_ROOTS)
        self.assertEqual(counts, {symbol: 1 for symbol in PRODUCTION_BITMAP_ROOTS})
        duplicate = sample_nm + "00100600 T interface_draw_screen\n"
        self.assertEqual(rooted_symbol_definition_counts(
            duplicate, PRODUCTION_BITMAP_ROOTS)["interface_draw_screen"], 2)

    def test_ps2_memory_diagnostics_are_owned_by_real_provider(self):
        symbols = (
            "ps2_step8_dynamic_sim_diagnostics",
            "ps2_step8_malloc_phase_begin",
            "ps2_step8_malloc_phase_end",
        )
        generated, missing = emit(list(symbols))
        self.assertEqual(missing, [])
        for symbol in symbols:
            self.assertNotIn(symbol + "(", generated)
            self.assertIn(symbol, SKIP)

    def test_ce_validator_claims_scratch_bounds_and_rebind(self):
        compiler = shutil.which("gcc")
        if not compiler:
            self.skipTest("GCC unavailable for the ILP32 validator fixture")
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "validator-scratch-test"
            hcu = HCU
            source = hcu / "port/linux/game/tag_validate.c"
            includes = [
                hcu / "port/ps2/include", hcu / "source", hcu / "source/cseries",
                hcu / "source/cache", hcu / "source/tag_files", hcu / "source/memory",
                hcu / "source/math", hcu / "source/rasterizer", hcu / "source/render",
                hcu / "source/game", hcu / "source/sound", hcu / "port/include",
                hcu / "port/include/xdk", hcu / "port/linux/game", Path("/usr/include"),
            ]
            command = [compiler, *host_abi32_flags(), "-fshort-wchar", "-std=gnu89"]
            command.extend("-I" + str(path) for path in includes)
            command.extend([
                "-include", str(ROOT / "tests/hcu_validator_host32_prefix.h"),
                str(source), str(ROOT / "tests/hcu_validator_scratch_main.c"),
                "-o", str(executable),
            ])
            subprocess.run(command, check=True, capture_output=True, text=True)
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            if run.returncode == -31:
                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_ps2_memory_binder_tracks_caller_owned_capacity(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            shim = ROOT / "tests/hcu_ps2_memory_shim"
            source = HCU / "port/ps2/src/ps2_memory.c"
            test_main = ROOT / "tests/hcu_ps2_memory_main.c"
            parent_engine = ROOT / "submodules/halo-ps2/engine/src"
            parent_glue = ROOT / "src/stream/hcu_memory_bind.c"
            for suffix, flags in (("bootstrap", []),
                                  ("external-only", ["-DHALO_PS2_NO_BOOTSTRAP_MEMORY"])):
                executable = Path(temporary) / ("memory-test-" + suffix)
                subprocess.run(
                    [compiler, "-std=gnu99", *flags, "-I", str(shim), "-I",
                     str(parent_engine), "-I", str(HCU / "port/ps2/include"),
                     "-I", str(ROOT / "src"), str(source),
                     str(parent_glue), str(test_main),
                     str(parent_engine / "core/mem.c"), "-o", str(executable)],
                    check=True, capture_output=True, text=True,
                )
                subprocess.run([str(executable)], check=True)

    def test_tag_cache_bounds_follow_the_bound_physical_extent(self):
        cache_source = (HCU / "source/cache/cache_files.c").read_text()
        memory_source = (HCU / "port/ps2/src/ps2_memory.c").read_text()
        validator_source = (HCU / "port/linux/game/tag_validate.c").read_text()
        validator_header = (HCU / "port/linux/game/tag_schema.h").read_text()
        memory_header = (HCU / "source/cache/physical_memory_map.h").read_text()
        self.assertNotIn("TAG_CACHE_SIZE", cache_source)
        self.assertGreaterEqual(cache_source.count("physical_memory_get_tag_cache_size()"), 7)
        self.assertIn("physical_memory_bind_tag_cache", memory_source)
        self.assertIn("configured[_ps2_memory_tag_cache].bytes", memory_source)
        self.assertIn("PS2_TAG_CACHE_BYTES", memory_source)
        self.assertIn("tag_validate_bind_claims_buffer", validator_source)
        self.assertIn("tag_validate_claims_buffer_size", validator_source)
        self.assertIn("tag_validate_release_claims_buffer", validator_source)
        self.assertIn("claims_cover", validator_source)
        self.assertIn("physical_memory_get_tag_cache_size()", validator_source)
        self.assertIn("tag_validate_bind_claims_buffer", validator_header)
        self.assertIn("tag_validate_claims_buffer_size", validator_header)
        self.assertIn("tag_validate_claims_buffer_ready", validator_source)
        self.assertIn("tag_validate_claims_buffer_ready", validator_header)
        self.assertIn("tag_validate_claims_buffer_ready()", memory_source)
        self.assertIn("physical_memory_bind_tag_validation_scratch", memory_header)
        self.assertIn("physical_memory_bind_tag_validation_scratch", memory_source)
        self.assertIn("validator_claims.base", memory_source)
        self.assertIn("tag_validate_release_claims_buffer()", memory_source)
        memory_fixture = (ROOT / "tests/hcu_ps2_memory_main.c").read_text()
        self.assertIn("!physical_memory_bind_tag_cache(tag, TEST_TAG_BYTES)", memory_fixture)
        validator_fixture = (ROOT / "tests/hcu_validator_scratch_main.c").read_text()
        self.assertIn("10UL * 1024UL * 1024UL", validator_fixture)
    def test_local_campaign_coop_helpers_are_simulation(self):
        symbols = (
            "coop_scripts_gather_in_volume",
            "coop_scripts_teleport_followers",
            "coop_enemies_extra_count",
            "coop_enemies_rider_unseated",
            "network_coop_active",
            "network_coop_player_collisions",
            "network_coop_set_players_vitality",
            "network_coop_skip_offered",
            "network_coop_vehicle_dropped",
        )
        for symbol in symbols:
            with self.subTest(symbol=symbol):
                self.assertEqual(classify(symbol), "simulation")

    def test_only_coop_event_replication_is_excluded_by_prefix(self):
        self.assertEqual(classify("network_coop_note_effect"), "excluded-feature")
        self.assertEqual(classify("network_coop_note_unit_animation"), "excluded-feature")

    def test_network_coop_note_stubs_are_noops_in_local_mode(self):
        notes = (
            "network_coop_note_attach", "network_coop_note_detach",
            "network_coop_note_device_snap", "network_coop_note_effect",
            "network_coop_note_hud", "network_coop_note_nav_point",
            "network_coop_note_object_effect", "network_coop_note_player_effect",
            "network_coop_note_scenery_animation", "network_coop_note_sound",
            "network_coop_note_surface_broken", "network_coop_note_title",
            "network_coop_note_unit_animation", "network_coop_note_unit_animation_frame",
            "network_coop_note_unit_open",
        )
        coop_source = (HCU / "port/ps2/game/ps2_coop.c").read_text()
        active = re.search(r"boolean network_coop_active\s*\(\s*void\s*\)\s*\{([^}]*)\}", coop_source)
        self.assertIsNotNone(active)
        self.assertRegex(active.group(1), r"return\s+FALSE\s*;")

        generated, missing = emit(list(notes))
        self.assertEqual(missing, [])
        for name in notes:
            with self.subTest(symbol=name):
                self.assertEqual(classify(name), "excluded-feature")
                self.assertRegex(generated,
                    rf"void\s+{re.escape(name)}\s*\([^)]*\)\s*\{{\s*\}}")

    def test_large_ce_globals_have_source_backed_memory_owners(self):
        manifest = json.loads((HCU / "port/ps2/port.json").read_text())
        chosen = set(selected_sources(manifest))
        self.assertIn("source/ai/ai_debug.c", chosen)
        render_source = (HCU / "port/ps2/src/ps2_render.c").read_text()
        self.assertIn("struct render_globals render;", render_source)
        generated, missing = emit(["render"])
        self.assertEqual(missing, [])
        self.assertNotIn("struct render_globals render;", generated)

        # These toggles are read by the AI decision/movement paths; dropping
        # ai_debug as merely visual/debug storage would change CE behavior.
        encounters = (HCU / "source/ai/encounters.c").read_text()
        moving = (HCU / "source/ai/actor_moving.c").read_text()
        self.assertIn("ai_debug.force_all_active", encounters)
        self.assertIn("ai_debug.force_crouch", moving)
        self.assertIn("ai_debug.oversteer_disable", moving)

        audit = json.loads((ROOT / "docs/hcu-ps2-memory-audit.json").read_text())
        symbols = {symbol["name"]: symbol for symbol in audit["symbols"]}
        expected = {
            "render": (201364, "resident_gameplay"),
            "ai_debug": (547628, "resident_gameplay"),
            "sound_cache": (524288, "audio"),
            "validator_claims": (8, "resident_gameplay"),
        }
        for name, (size, region) in expected.items():
            with self.subTest(symbol=name):
                self.assertEqual(symbols[name]["bytes"], size)
                self.assertEqual(symbols[name]["candidate_region"], region)

    def test_memory_provider_bind_apis_are_not_generated_as_zero_stubs(self):
        symbol = "physical_memory_bind_tag_validation_scratch"
        self.assertIn(symbol, SKIP)
        generated, missing = emit([symbol])
        self.assertEqual(missing, [])
        self.assertNotIn(f"{symbol}(", generated)

    def test_coop_spectator_presentation_is_render(self):
        self.assertEqual(classify("coop_spectate_camera"), "render")
        self.assertEqual(classify("coop_spectate_unit"), "render")
        self.assertEqual(classify("coop_spectating"), "render")
        self.assertEqual(classify("coop_skip_vote_draw"), "render")

    def test_prefix_false_positives_keep_local_state_and_decisions_reviewable(self):
        # These share broad network_/coop_/ui_widget prefixes with excluded
        # paths, but their return values or lifecycle calls feed local state.
        self.assertEqual(classify("network_coop_active"), "simulation")
        self.assertEqual(classify("network_coop_note_effect"), "excluded-feature")
        self.assertEqual(classify("coop_spectating"), "render")
        for symbol in ("ui_widgets_active_for_local_player",
                       "ui_widgets_safe_to_load",
                       "ui_widget_load_by_name_or_tag"):
            with self.subTest(symbol=symbol):
                self.assertEqual(classify(symbol), "render")
        self.assertEqual(classify("ui_main_menu_music_active"), "sound")
        self.assertEqual(classify("ui_stop_main_menu_music"), "sound")

    def test_local_adapter_is_in_the_ps2_compile_closure(self):
        manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
        self.assertIn("port/ps2/game/ps2_coop.c", manifest["port_sources"])
        source = ROOT / "submodules/halo-ce-universal/port/ps2/game/ps2_coop.c"
        self.assertTrue(source.is_file())

    def test_ps2_uses_the_ce_tag_validator_instead_of_permissive_stubs(self):
        manifest = json.loads((HCU / "port/ps2/port.json").read_text())
        required = {
            "port/linux/game/tag_validate.c",
            "port/linux/game/tag_validate_report.c",
            "port/linux/game/tag_schema_groups.c",
            "port/linux/game/tag_schema_collision.c",
            "port/linux/game/tag_schema_models.c",
            "port/linux/game/tag_schema_objects.c",
            "port/linux/game/tag_schema_render.c",
            "port/linux/game/tag_schema_effects.c",
            "port/linux/game/tag_schema_scenario.c",
        }
        self.assertTrue(required.issubset(set(manifest["port_sources"])))
        ps2_data = (HCU / "port/ps2/game/ps2_data.c").read_text()
        self.assertNotIn("boolean tag_validate_tags(\n", ps2_data)
        self.assertNotIn("boolean tag_validate_structure_bsp(\n", ps2_data)
        schema = (HCU / "port/linux/game/tag_schema.h").read_text()
        self.assertIn("#ifdef HALO_PS2\n\tTAG_VALIDATE_MAXIMUM_TAG_CACHE_SIZE = HALO_PORT_TAG_CACHE_SIZE,", schema)

    def test_ps2_ctag_decoder_is_selected_and_compiled(self):
        manifest = json.loads((HCU / "port/ps2/port.json").read_text())
        source_path = "port/ps2/src/ps2_ctag.c"
        self.assertIn(source_path, manifest["port_sources"])
        self.assertTrue((HCU / source_path).is_file())
        result_path = ROOT / "build/hcu-ps2-closure/all/result.json"
        if result_path.is_file():
            result = json.loads(result_path.read_text())
            self.assertEqual(result["units"][source_path]["status"], "compiled")

    def test_ps2_clock_services_are_owned_by_the_timer_adapter(self):
        source = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_time.c").read_text()
        self.assertIn("QueryPerformanceCounter(union _LARGE_INTEGER *counter)", source)
        self.assertIn("QueryPerformanceFrequency(union _LARGE_INTEGER *frequency)", source)
        self.assertIn("GetTimerSystemTime()", source)
        self.assertIn("kBUSCLK", source)
        self.assertIn("QueryPerformanceCounter", SKIP)
        self.assertIn("QueryPerformanceFrequency", SKIP)
        self.assertIn("GetSystemTime(struct _SYSTEMTIME *system_time)", source)
        self.assertIn("gmtime_r(&now, &utc)", source)
        self.assertIn("GetSystemTime", SKIP)

    def test_custom_map_directory_creation_is_explicitly_fail_closed(self):
        source = (HCU / "port/ps2/src/ps2_edge.c").read_text()
        self.assertIn("int __stdcall CreateDirectoryA(const char *path", source)
        self.assertIn("ps2_last_error = path && path[0] ? ERROR_ACCESS_DENIED", source)
        self.assertIn("CreateDirectoryA", SKIP)
        generated = ROOT / "build/hcu-ps2-closure/all/ps2_platform.c"
        if generated.is_file():
            self.assertNotIn("CreateDirectoryA(", generated.read_text())

    def test_unmounted_ps2_file_facade_calls_fail_closed(self):
        source = (HCU / "port/ps2/src/ps2_edge.c").read_text()
        generated = ROOT / "build/hcu-ps2-closure/all/ps2_platform.c"
        generated_text = generated.read_text() if generated.is_file() else ""
        for symbol in ("CreateFileA", "ReadFile", "GetFileSize", "SetFilePointer",
                       "FindFirstFileA", "FindNextFileA", "CloseHandle"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, source)
                self.assertIn(symbol, SKIP)
                self.assertNotIn(symbol + "(", generated_text)

    def test_ps2_startup_does_not_initialize_xbox_directsound(self):
        source = (ROOT / "submodules/halo-ce-universal/source/sound/sound_preferences.c").read_text()
        self.assertIn("#ifdef HALO_PS2\n\t-1,\n#else\n\t0,", source)
        self.assertIn("M1 has no DirectSound or SPU2 request backend", source)

    def test_ps2_xinput_semantics_are_implemented_and_not_stubbed(self):
        manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
        source_path = "port/ps2/src/ps2_input.c"
        source = ROOT / "submodules/halo-ce-universal" / source_path
        self.assertIn(source_path, manifest["port_sources"])
        self.assertTrue(source.is_file())
        implementation = source.read_text()
        for symbol in ("XGetDeviceChanges", "XInputOpen", "XInputClose", "XInputGetState"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, implementation)
                self.assertIn(symbol, SKIP)  # exclude it from generated stand-ins
        self.assertIn("ps2_input_publish_state", implementation)
        self.assertIn("ps2_input_publish_dualshock", implementation)
        self.assertIn("stick_axis(ly, 1)", implementation)
        self.assertIn("gamepad.bAnalogButtons, analog", implementation)
        self.assertIn("PS2_INPUT_PORTS 4", implementation)

    def test_ps2_input_does_not_depend_on_xbox_keyboard_rumble_worker(self):
        source = (HCU / "source/input/input_xbox.c").read_text()
        self.assertIn("#ifdef HALO_PS2\n\t/* port: the machine polls DualShock", source)
        self.assertIn("input_globals.update_event_handle = NULL", source)
        self.assertIn("input_globals.update_thread_handle = NULL", source)
        self.assertIn("#ifndef HALO_PS2\n\tif (!input_globals.update_thread_started)", source)
        generated = ROOT / "build/hcu-ps2-closure/all/ps2_platform.c"
        if generated.is_file():
            generated_text = generated.read_text()
            self.assertNotIn("CreateEventA(", generated_text)
            self.assertNotIn("SetEvent(", generated_text)

    def test_ui_filesystem_worker_has_synchronous_fallback(self):
        source = (HCU / "source/interface/ui_widget.c").read_text()
        start = source.index("static void perform_filesystem_initialization(\n\tvoid)\n{")
        end = source.index("\n}\n", start)
        body = source[start:end]
        self.assertIn("if (!create_thread(", body)
        self.assertIn("filesystem_initialization_thread_proc(NULL)", body)

    def test_boot_stage_markers_are_beyond_initialization_and_map_loaded(self):
        source = (HCU / "source/main/main.c").read_text()
        start = source.index("void main_load_ui_scenario(\n\tboolean precache_resources)\n{")
        end = source.index("\n}\n", start)
        body = source[start:end]
        m1 = body.index("HALO_PS2_LOCAL m1-ui-map-request")
        first_request = body.index('game_precache_new_map("levels\\\\ui\\\\ui", TRUE)')
        self.assertLess(m1, first_request)
        game_source = (HCU / "source/game/game.c").read_text()
        load_start = game_source.index("boolean game_load(\n\tstruct game_options *options)\n{")
        load_end = game_source.index("\n}\n", load_start)
        game_load = game_source[load_start:load_end]
        scenario_success = game_load.index("if (scenario_load(options->map_name))")
        m2 = game_load.index("HALO_PS2_LOCAL m2-ui-map-loaded")
        self.assertLess(scenario_success, m2)
        self.assertIn('strcmp(options->map_name, "levels\\\\ui\\\\ui") == 0', game_load)
        self.assertIn('parser.add_argument("--stage", choices=tuple(STAGE_MARKERS), default="playable"',
                      (ROOT / "tools/test_hcu_boot.py").read_text())
        self.assertIn('"m1-boundary": "HALO_PS2_LOCAL m1-ui-map-request"',
                      (ROOT / "tools/test_hcu_boot.py").read_text())

    def test_m2_ui_lifecycle_diagnostic_is_opt_in_and_uses_normal_menu_path(self):
        main = (HCU / "source/main/main.c").read_text()
        loop = main[main.index("void main_loop(\n\tvoid)\n{"):]
        setup = loop.index("main_setup_connection();")
        initialized = loop.index("main_initialize_time();", setup)
        diagnostic = loop.index("HALO_PS2_M2_UI_LIFECYCLE_TEST", initialized)
        steady_loop = loop.index("while (TRUE)", diagnostic)
        self.assertLess(setup, initialized)
        self.assertLess(initialized, diagnostic)
        self.assertLess(diagnostic, steady_loop)
        self.assertIn("hcu_m2_ui_lifecycle_test_run();", loop[diagnostic:steady_loop])
        self.assertNotIn("main_menu_unload();", loop[diagnostic:steady_loop])
        self.assertNotIn("main_menu_load();", loop[diagnostic:steady_loop])
        scenario = (HCU / "source/scenario/scenario.c").read_text()
        unload = scenario[scenario.index("void scenario_unload("):]
        self.assertLess(unload.index("global_scenario = NULL;"),
                        unload.index('scenario_m2_ui_lifecycle_trace("ce-unpublished")'))
        self.assertLess(unload.index('scenario_m2_ui_lifecycle_trace("ce-unpublished")'),
                        unload.index("ps2_cache_release_map_owner()"))
        closure = (ROOT / "tools/hcu_ps2_closure.py").read_text()
        self.assertIn('parser.add_argument("--m2-ui-lifecycle-test"', closure)
        self.assertIn('WORLD_HCU_M2_UI_LIFECYCLE_TEST=',
                      (ROOT / "tools/hcu_parent_link_probe.py").read_text())
        lifecycle = (HCU / "source/main/ps2_m2_ui_lifecycle_test.c").read_text()
        self.assertIn("hcu_map_service_lifecycle_fail_preflight_once();", lifecycle)
        self.assertIn("hcu_map_service_lifecycle_arm_deferred_failure_once();",
                      lifecycle)
        self.assertIn("main_load_ui_scenario(FALSE);", lifecycle)
        self.assertIn("main_menu_load();", lifecycle)
        self.assertIn("global_collision_bsp", lifecycle)
        self.assertIn("global_bsp3d", lifecycle)
        self.assertIn("global_game_globals", lifecycle)
        self.assertIn("cache_files_tag_instances(&tag_count)", lifecycle)
        self.assertNotIn("hcu_map_service_lifecycle_consume_deferred_failure",
                         lifecycle)
        self.assertIn("m2-ui-lifecycle-injected preflight-after-unload",
                      (ROOT / "src/stream/hcu_map_service.c").read_text())
        self.assertIn('"source/scenario/scenario.c": ["-Oz"]', closure)
        self.assertIn('"source/main/ps2_m2_ui_lifecycle_test.c": [', closure)
        self.assertIn('"source/main/main.c", "source/scenario/scenario.c"', closure)
        self.assertIn('"m2-ui-lifecycle": "HALO_PS2_LOCAL m2-ui-lifecycle-complete cycles=2"',
                      (ROOT / "tools/test_hcu_boot.py").read_text())
        generated, missing = emit(
            ["hcu_map_service_lifecycle_trace"],
            {"hcu_map_service_lifecycle_trace"})
        self.assertFalse(missing)
        self.assertRegex(generated,
                         r"__attribute__\(\(weak\)\)\s+void hcu_map_service_lifecycle_trace\(")
        generated, missing = emit(
            ["hcu_map_service_lifecycle_fail_preflight_once",
             "hcu_map_service_lifecycle_arm_deferred_failure_once"],
            {"hcu_map_service_lifecycle_fail_preflight_once",
             "hcu_map_service_lifecycle_arm_deferred_failure_once"})
        self.assertFalse(missing)
        self.assertEqual(generated.count("__attribute__((weak))"), 2)

    def test_manifest_replacement_entries_point_to_real_implementations(self):
        manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
        replacements = {row["path"]: row for row in manifest["replaced_xbox_files"]}
        for source_path, row in replacements.items():
            with self.subTest(source=source_path):
                if row["status"] == "implemented":
                    self.assertIsNotNone(row["replacement"])
                    self.assertTrue((ROOT / "submodules/halo-ce-universal" / row["replacement"]).is_file())
                else:
                    self.assertEqual(row["status"], "planned")
                    self.assertIsNone(row["replacement"])
        physical = replacements["source/cache/physical_memory_map.c"]
        self.assertEqual(physical["status"], "implemented")
        self.assertTrue((ROOT / "submodules/halo-ce-universal" / physical["replacement"]).is_file())
        cache = replacements["source/cache/cache_files_windows.c"]
        self.assertEqual(cache["status"], "implemented")
        self.assertEqual(cache["replacement"], "port/ps2/src/ps2_cache.c")
        self.assertIn(cache["path"], manifest["exclude_sources"])
        self.assertIn(cache["replacement"], manifest["port_sources"])


class HcuPs2Cache(unittest.TestCase):
    def test_unsupported_xbox_cache_fails_synchronously(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hcu-ps2-cache"
            include_dirs = (ROOT / "tests/hcu_ps2_cache_shim",
                            HCU / "port/ps2/include")
            command = ["cc", "-std=c89", "-Wall", "-Wextra", "-Werror"]
            for directory in include_dirs:
                command.extend(("-I", str(directory)))
            command.extend((str(ROOT / "tests/hcu_ps2_cache_main.c"),
                            str(HCU / "port/ps2/src/ps2_cache.c"),
                            str(HCU / "port/ps2/src/ps2_ctag.c"),
                            str(HCU / "port/ps2/src/ps2_cbsp.c"), "-o", str(exe)))
            subprocess.run(command, check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


class HcuPs2MemoryAudit(unittest.TestCase):
    def test_load_accounting_separates_file_bytes_from_nobits(self):
        headers = """
  LOAD 0x000080 0x00100000 0x00100000 0x225704 0x3dfbc4 RWE 0x80
"""
        self.assertEqual(parse_load_accounting(headers), {
            "load_segments": [{"filesz": 2250500, "memsz": 4062148,
                               "nobits": 1811648}],
            "file_backed_load_bytes": 2250500,
            "nobits_load_bytes": 1811648,
        })

    def test_map_ignores_aggregate_and_keeps_input_section_ranges(self):
        ranges = parse_map("""
.bss 0x1000 0x3000
 .bss 0x1000 0x1000 /build/rooted.o
 .bss.render
                0x1000 0x0200 /build/platform.o
 COMMON 0x2000 0x0100 /build/platform.o
 *fill* 0x2100 0x0004
""")
        self.assertEqual([row["bytes"] for row in ranges], [0x1000, 0x200, 0x100, 4])
        self.assertEqual(ranges[-1]["owner"], "linker-fill")

    def test_symbols_use_narrowest_matching_map_owner(self):
        ranges = parse_map("""
 .bss 0x1000 0x1000 /build/rooted.o
 .bss.render 0x1000 0x0200 /build/platform.o
""")
        symbols = parse_nm("""
00001000 00000100 B render
00001200 00000004 b unrelated
00002000 00000008 D initialized
""")
        attach_owners(symbols, ranges)
        self.assertEqual(symbols[0]["owner"], "platform.o")
        self.assertEqual(symbols[1]["owner"], "rooted.o")
        self.assertEqual(len(symbols), 2)

    def test_candidate_regions_split_memory_provider_and_reconcile_bytes(self):
        ranges = [
            {"owner": "ps2_memory.o", "section": ".bss", "start": 0x1000,
             "end": 0x1030, "bytes": 0x30},
            {"owner": "rooted.o", "section": ".bss.state", "start": 0x2000,
             "end": 0x2010, "bytes": 0x10},
            {"owner": "linker-fill", "section": "*fill*", "start": 0x2010,
             "end": 0x2014, "bytes": 4},
        ]
        symbols = [
            {"owner": "ps2_memory.o", "address": 0x1000, "bytes": 0x10,
             "name": "game_state"},
            {"owner": "ps2_memory.o", "address": 0x1020, "bytes": 0x10,
             "name": "tag_cache"},
        ]
        config = {
            "owner_regions": {"rooted.o": "resident_gameplay"},
            "system_runtime_owner_contains": [],
            "symbol_regions": {"game_state": "resident_gameplay", "tag_cache": "current_bsp"},
            "unassigned_region": "unassigned",
        }
        result = apply_region_candidates(ranges, symbols, config)
        self.assertEqual(result["candidate_bss_bytes_by_region"], {
            "current_bsp": 16, "resident_gameplay": 52,
        })
        self.assertEqual(result["unassigned_owners"], [])

    def test_documented_bss_region_rows_reconcile_with_current_elf(self):
        report = (ROOT / "docs/hcu-ps2-closure.md").read_text()
        start = report.index("| Candidate region | Bytes | Basis |")
        end = report.index("\n\nThe ELF's full `.bss` is ", start)
        rows = report[start:end].splitlines()[2:]
        byte_total = 0
        for row in rows:
            fields = [field.strip() for field in row.strip().strip("|").split("|")]
            self.assertEqual(len(fields), 3, row)
            byte_total += int(fields[1].replace(",", ""))
        self.assertEqual(byte_total, 9_639_408)

    def test_file_backed_allocated_sections_exclude_nobits(self):
        text = """
  [ 1] .text PROGBITS 00100000 010000 001000 00 AX 0 0 16
  [ 2] .bss NOBITS 00200000 020000 000800 00 WA 0 0 64
"""
        total, sections = parse_file_backed_allocated_bytes(text)
        self.assertEqual(total, 0x1000)
        self.assertEqual([row["name"] for row in sections], [".text"])


class HcuPs2BuildArtifactGate(unittest.TestCase):
    """Exercise the generated closure artifact, not only classifier examples."""

    @classmethod
    def setUpClass(cls):
        cls.output = ROOT / "build/hcu-ps2-closure/all"
        result_path = cls.output / "result.json"
        if not result_path.is_file():
            raise AssertionError(
                "run HALO_BUILD_JOBS=4 python3 tools/hcu_ps2_closure.py --layer all first")
        cls.report = json.loads(result_path.read_text())

    def test_result_json_has_complete_compilation_and_safe_classification(self):
        report = self.report
        self.assertEqual(report["status"], "layer-measured")
        self.assertEqual(report["failed_count"], 0)
        self.assertEqual(report["compiled_count"], len(report["units"]))
        manifest = json.loads((HCU / "port/ps2/port.json").read_text())
        self.assertEqual(
            report["compiled_count"],
            report["selected_source_count"] + len(manifest["port_sources"]),
        )

        partial = report["partial_link"]
        classes = partial["classes"]
        for forbidden in ("simulation", "data", "unclassified"):
            with self.subTest(classification=forbidden):
                self.assertEqual(classes.get(forbidden, []), [])
        self.assertEqual(
            partial["live_external_count"],
            sum(len(symbols) for symbols in classes.values()),
        )

    def test_rooted_externals_have_exact_symbols_and_relocation_callers(self):
        rooted = self.report["rooted_link"]
        rows = rooted["live_externals"]
        self.assertEqual(rooted["live_external_count"], len(rows))
        self.assertEqual(len({row["symbol"] for row in rows}), len(rows))
        self.assertEqual(rooted["live_external_count"],
                         sum(len(symbols) for symbols in rooted["classes"].values()))
        for row in rows:
            with self.subTest(symbol=row["symbol"]):
                self.assertTrue(row["caller_sections"])
                self.assertTrue(row["caller_source_candidates"])
                self.assertEqual(row["classification"], classify(row["symbol"]))
        self.assertNotIn("allow_out_of_sync", {row["symbol"] for row in rows})
        profile = (HCU / "port/ps2/src/ps2_local_profile.c").read_text()
        self.assertIn("boolean allow_out_of_sync;", profile)
        script = (HCU / "source/hs/hs_globals_external.c").read_text()
        self.assertIn("allow_out_of_sync", script)

    def test_real_tag_validator_is_compiled_and_rooted(self):
        self.assertIn("port/linux/game/tag_validate.c", set(self.report["units"]))
        _build, prefix, _env, _jobs = environment()
        nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
        output = subprocess.run([str(nm), "-g", "--defined-only", str(self.output / "rooted.o")],
                                check=True, capture_output=True, text=True).stdout
        defined = {line.split()[-1] for line in output.splitlines() if line.split()}
        self.assertIn("tag_validate_tags", defined)
        self.assertIn("tag_validate_structure_bsp", defined)

    def test_rooted_symbols_and_final_elf_pass_the_linker_gate(self):
        build, prefix, _env, _jobs = environment()
        rooted = self.output / "rooted.o"
        elf = self.output / "halo-local.elf"
        self.assertTrue(rooted.is_file(), "closure build must produce rooted.o")
        self.assertTrue(elf.is_file(), "run python3 tools/hcu_ps2_link.py first")

        nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
        unresolved = undefined_symbols(nm, rooted)
        forbidden = {
            symbol: classify(symbol)
            for symbol in unresolved
            if classify(symbol) in {"simulation", "data", "unclassified"}
        }
        self.assertEqual(forbidden, {})
        self.assertEqual(undefined_symbols(nm, elf), set())

    def test_ctag_mount_entrypoint_is_a_rooted_machine_boundary(self):
        result = json.loads((ROOT / "build/hcu-ps2-closure/all/result.json").read_text())
        self.assertIn("ps2_cache_mount_ctag", result["rooted_link"]["roots"])
        link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
        self.assertIn("ps2_cache_mount_ctag", link_map)
        self.assertIn("ps2_ctag_open", link_map)

    def test_streamed_ctag_adapter_boundaries_are_rooted_for_parent_link(self):
        result = json.loads((ROOT /
            "build/hcu-ps2-closure/all-no-bootstrap-memory/result.json").read_text())
        roots = result["rooted_link"]["roots"]
        for symbol in ("ps2_cache_mount_ctag_stream",
                       "ps2_cache_set_ctag_visitor",
                       "ps2_ctag_stream_validator_begin",
                       "ps2_ctag_stream_validator_write",
                       "ps2_ctag_stream_validator_finish"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, roots)
        link_map = (ROOT /
            "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.map").read_text()
        self.assertIn("ps2_cache_mount_ctag_stream", link_map)
        self.assertIn("ps2_cache_set_ctag_visitor", link_map)
        for symbol in ("ps2_ctag_stream_validator_begin",
                       "ps2_ctag_stream_validator_write",
                       "ps2_ctag_stream_validator_finish"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, link_map)

    def test_validator_readiness_is_a_rooted_startup_boundary(self):
        result = json.loads((ROOT / "build/hcu-ps2-closure/all/result.json").read_text())
        self.assertIn("tag_validate_claims_buffer_ready", result["rooted_link"]["roots"])
        link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
        self.assertIn("tag_validate_claims_buffer_ready", link_map)

    def test_validator_scratch_owner_api_is_linked(self):
        result = json.loads((ROOT / "build/hcu-ps2-closure/all/result.json").read_text())
        symbols = (
            "tag_validate_bind_claims_buffer",
            "tag_validate_release_claims_buffer",
            "physical_memory_bind_game_state",
            "physical_memory_bind_tag_cache",
            "physical_memory_bind_structure_bsp_cache",
            "physical_memory_bind_texture_cache",
            "physical_memory_bind_sound_cache",
            "physical_memory_bind_malloc_arena",
            "physical_memory_bind_tag_validation_scratch",
        )
        link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
        for symbol in symbols:
            self.assertIn(symbol, result["rooted_link"]["roots"])
            self.assertIn(symbol, link_map)


if __name__ == "__main__":
    unittest.main()
