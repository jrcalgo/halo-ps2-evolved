"""Link the rooted HCU image into an R5900 ELF.

Toolchain symbols are left for the C library. Every other undefined symbol
gets a typed definition. Simulation symbols are not in that set: the closure
already defines them.
"""
from __future__ import annotations

import os
import re
import argparse
import subprocess
import sys
from pathlib import Path

from build_toolchain import ROOT, environment
from hcu_ps2_closure import HCU, classify

OUT = ROOT / "build/hcu-ps2-closure/all"
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
PREPROC = re.compile(r"^\s*#.*?(?<!\\)$", re.M | re.S)
SKIP = {
	"halo_ps2_render_snapshot_begin", "halo_ps2_render_snapshot_commit",
	# The dedicated provider object is linked into both CE and combined parent links.
	"halo_ps2_sound_playback_note", "halo_ps2_sound_playback_bind_sink",
	# C3: weak writer hooks; the parent snapshot bank (src/stream/hcu_snapshot_bank.c) implements them.
	"halo_ps2_frame_snapshot_begin", "halo_ps2_frame_snapshot_commit",
	"halo_ps2_frame_snapshot_intern_object",
	"halo_ps2_frame_snapshot_find_object",
    # Implemented by the real PS2 memory provider. Keep undefined references
    # unresolved in every profile so the provider object must satisfy them.
    "ps2_step8_dynamic_sim_diagnostics",
    "ps2_step8_malloc_phase_begin", "ps2_step8_malloc_phase_end",
    "physical_memory_allocate", "physical_memory_verify", "physical_memory_free",
    "physical_memory_bind_game_state", "physical_memory_bind_tag_cache",
    "physical_memory_bind_structure_bsp_cache", "physical_memory_bind_texture_cache",
    "physical_memory_bind_sound_cache", "physical_memory_bind_malloc_arena",
    "physical_memory_bind_tag_validation_scratch",
    "physical_memory_ready", "physical_memory_get_game_state_size",
    "physical_memory_get_texture_cache_size", "physical_memory_get_sound_cache_size",
    "physical_memory_get_malloc_arena_size",
    "physical_memory_get_game_state_base_address", "physical_memory_get_tag_cache_base_address",
    "physical_memory_get_tag_cache_size",
    "physical_memory_get_structure_bsp_cache_base_address",
    "physical_memory_get_structure_bsp_cache_size",
    "physical_memory_get_texture_cache_base_address", "physical_memory_get_sound_cache_base_address",
    "malloc", "free", "calloc", "realloc",
    "GlobalAlloc", "GlobalReAlloc", "LocalFree",
    "DmWalkLoadedModules", "DmWalkModuleSections", "DmCloseModuleSections",
    "XGetLaunchInfo", "rasterizer_initialize",
    "rasterizer_transparent_geometry_is_enclosure",
    "global_rasterizer_model_ambient_reflection_tint",
    "ui_stop_main_menu_music", "virtual_keyboard_active", "virtual_keyboard_close",
    "halo_screen_width", "DirectSoundCreate",
    "XInputDebugGetKeystroke", "GetFileAttributesA", "GetFileAttributesExA", "CreateDirectoryA",
    "CreateFileA", "ReadFile", "GetFileSize", "SetFilePointer",
    "FindFirstFileA", "FindNextFileA",
    "CreateMutexA", "WaitForSingleObject", "ReleaseMutex", "CloseHandle",
    "GetTickCount", "GetTimerSystemTime", "QueryPerformanceCounter", "QueryPerformanceFrequency",
    "XDEVICE_TYPE_DEBUG_KEYBOARD_TABLE", "XDEVICE_TYPE_GAMEPAD_TABLE",
    "XDEVICE_TYPE_MEMORY_UNIT_TABLE", "XPhysicalFree", "allow_out_of_sync",
    "bink_playback_active", "cheat", "coop_spectating",
    "dispose_global_network_game_client", "dispose_global_network_game_server",
    "game_in_editor", "global_connection_dont_timeout",
    "halo_custom_edition_tag_cache", "halo_interpolation_enabled",
    "halo_keyboard_actions", "halo_linux_mouse_aiming", "halo_linux_mouse_look",
    "halo_linux_touch_aiming", "halo_linux_touch_look", "halo_linux_touch_move",
    "map_share_downloading", "rasterizer_fps_accumulate", "rasterizer_frame_update",
    "rasterizer_model_ambient_reflection_tint",
    "rasterizer_preinitialize__fill_you_up_with_the_devils_cock",
    "rasterizer_screen_effect_set_convolution", "rasterizer_screen_effect_set_filter",
    "rasterizer_screen_effect_set_filter_desaturation_tint",
    "rasterizer_screen_effect_set_video", "rasterizer_screen_effect_start",
    "rasterizer_screen_effect_stop", "rasterizer_script_screen_effect_set_value",
    "rasterizer_set_vblank_callback", "ui_main_menu_music_active",
    "GetSystemTime", "XGetDeviceChanges", "XInputOpen", "XInputClose", "XInputGetState",
    "GetLastError", "SetLastError",
    "render_location_visible", "D3D__RenderState",
    "rasterizer_widget_set_texture",
    "render", "render_contrails_enabled", "render_dispose", "render_dispose_from_old_map",
    "render_effects", "render_fov_vertical", "render_frame", "render_frame_pregame",
    "render_initialize", "render_initialize_for_new_map",
    "render_interpolation_camera", "render_interpolation_fraction",
    "render_interpolation_frame_begin", "render_interpolation_frame_end",
	"render_interpolation_first_person",
	"render_interpolation_object_node_matrices", "render_interpolation_reset",
    "render_interpolation_tick",
	"pal_tags_first_person_fraction",
    "render_particle_systems_enabled", "render_particles_enabled", "render_shadows",
    "render_weather_particle_systems_enabled",
    "reset_last_player1_profile_index",
    "CreateThread",
    "DeleteFileA",
    "GlobalMemoryStatus",
    "SetEndOfFile",
    "Sleep",
    "WriteFile",
    "XCalculateSignatureBegin",
    "XCalculateSignatureEnd",
    "XCalculateSignatureUpdate",
    "XCreateSaveGame",
    "XDeleteSaveGame",
    "XFindClose",
    "XFindFirstSaveGame",
    "XFindNextSaveGame",
    "_control87",
    "_sound_cache_sound_request",
    "_texture_cache_bitmap_get_hardware_format",
    "_vsnwprintf",
    "attract_mode_start",
    "build_sprite",
    "build_sprites_begin",
    "build_sprites_end",
    "config_boolean",
    "config_changes",
    "config_real",
    "config_string",
    "connected_geometry_add_triangle",
    "connected_geometry_delete",
    "connected_geometry_group_coplanar",
    "connected_geometry_new",
    "create_global_network_game_client",
    "create_global_network_game_server",
    "custom_edition_cache_refuse",
    "custom_edition_cache_tags_load",
    "custom_edition_cache_tags_loaded",
    "custom_edition_cache_tags_unload",
    "custom_edition_level_name",
    "custom_edition_maps_description",
    "custom_edition_maps_name",
    "custom_edition_structure_bsp_load",
    "main_menu_active",
    "main_menu_is_active",
    "main_screen_shell_load",
    "menu_tags_loaded",
    "menu_tags_unloaded",
    "mods_enable",
    "mods_list",
    "mods_reload",
    "mods_tags_loaded",
    "mods_tags_unloaded",
    "network_distributed_new_game",
    "network_distributed_player_killed",
    "network_distributed_player_picked_up",
    "network_distributed_tick",
    "network_game_abort",
    "network_game_accept_remote_connections",
    "network_game_client_end_frame",
    "network_game_client_request_immediate_start",
    "network_game_client_start_frame",
    "network_game_distributed_client",
    "network_game_server_ban_player",
    "network_game_server_get_game",
    "network_game_server_kick_player",
    "network_game_server_matching_player_names",
    "network_game_server_reset_to_pregame",
    "network_game_server_start_frame",
    "network_game_server_switch_to_postgame",
    "network_game_server_update_ticks",
    "network_votekick_matching_player_names",
    "rasterizer_dynamic_vertices_new",
    "rasterizer_dynamic_vertices_unlock",
    "rasterizer_frame_begin",
    "rasterizer_globals",
    "rasterizer_initialize_for_new_map",
    "rasterizer_lights_reset_for_new_map",
    "rasterizer_screen_effects_initialize_for_new_map",
    "rasterizer_set_near_clip_distance",

    "custom_edition_vehicle_placement_allowed",
    "custom_edition_vehicles_by_placement",
    "display_error_damaged_media",
    "display_error_deferred",
    "display_scenario_help",
    "distributed_player_to_byte",
    "network_votekick_player_named",
    "pal_tags_first_person_advance",
    "pal_tags_first_person_frames",
    "pal_tags_loaded",
    "pc_menus_screen",
    "powerup_render_bounds_tags_loaded",
    "process_ui_widgets",
    "progress_bar_dispose",
    "progress_bar_initialize",
    "rasterizer_bitmap_delete",
    "rasterizer_debug_options",
    "rasterizer_decal_vertices_delete",
    "rasterizer_decal_vertices_lock",
    "rasterizer_decal_vertices_new",
    "rasterizer_decal_vertices_unlock",
    "rasterizer_decals_dispose",
    "rasterizer_decals_dispose_from_old_map",
    "rasterizer_decals_flush",
    "rasterizer_decals_initialize",
    "rasterizer_decals_initialize_for_new_map",
    "rasterizer_decals_update_function_pointers",
    "rasterizer_dispose",
    "rasterizer_dispose_from_old_map",
    "rasterizer_dynamic_triangles_delete",
    "rasterizer_dynamic_triangles_lock",
    "rasterizer_dynamic_triangles_new",
    "rasterizer_dynamic_triangles_unlock",
    "rasterizer_dynamic_unlit_geometry_draw",
    "rasterizer_dynamic_vertices_delete",
    "rasterizer_dynamic_vertices_lock",
    "sound_cache_close",
    "sound_cache_delete",
    "sound_cache_flush",
    "sound_cache_idle",
    "sound_cache_new",
    "sound_cache_open",
    "sound_cache_sound_finished",
    "structure_bsp_header_deregister_vertex_buffers",
    "structure_bsp_header_register_vertex_buffers",
    "tags_header_deregister_vertex_and_index_buffers",
    "tags_header_register_vertex_and_index_buffers",
    "texture_cache_close",
    "texture_cache_debug_options",
    "texture_cache_flush",
    "texture_cache_open",
    "towlower",
    "transport_dispose",
    "transport_initialize",
    "ui_set_next_level",
    "ui_widget_load_by_name_or_tag",
    "ui_widget_load_progress_widget",
    "ui_widgets_active_for_local_player",
    "ui_widgets_close_all",
    "ui_widgets_disable_pause_game",
    "ui_widgets_dispose",
    "ui_widgets_inhibit_processing",
    "ui_widgets_initialize",
    "ui_widgets_set_fade_value",
    "vswprintf",
    "xbox_set_machine_name",

    "game_end_credits_start",
}


def top_level(text: str) -> str:
    out = []
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
            out.append(" ")
        elif ch == "}":
            depth -= 1
            out.append(" " if depth else ";")
        else:
            out.append(ch if depth == 0 else (" " if ch != "\n" else "\n"))
    return "".join(out)


def clean(text: str) -> str:
    return " ".join(PREPROC.sub(" ", text).split())


def load_texts() -> dict[Path, str]:
    texts = {}
    for root in (HCU / "source", HCU / "port"):
        for path in root.rglob("*"):
            if path.suffix in {".h", ".c"} and path.is_file():
                texts[path] = COMMENT.sub(" ", path.read_text(encoding="latin-1", errors="replace"))
    return texts


def find_declaration(name: str, texts: dict[Path, str], tops: dict[Path, str]):
    func = re.compile(r"(?:^|;|\n)\s*((?:extern\s+)?[A-Za-z_][\w\s\*]*?[\s\*])" + re.escape(name) +
                      r"\s*\(([^;{}]*?)\)\s*;", re.S)
    data = re.compile(r"(?:^|;|\n)\s*extern\s+([A-Za-z_][\w\s\*]*?[\s\*])" + re.escape(name) +
                      r"\s*((?:\[[^\]]*\])*)\s*;", re.S)
    order = sorted(texts, key=lambda path: (path.suffix != ".h", str(path)))
    for path in order:
        top = tops[path]
        if name not in top:
            continue
        match = func.search(top)
        if match and "typedef" not in match.group(1):
            return "func", path, match.group(1), match.group(2)
        match = data.search(top)
        if match:
            return "data", path, match.group(1), match.group(2)
    return None


TYPE_WORDS = {
    "void", "int", "long", "short", "char", "float", "double", "signed", "unsigned",
    "const", "volatile", "struct", "union", "enum", "boolean", "real", "byte", "word",
    "DWORD", "HRESULT", "BOOL", "HANDLE", "LPVOID", "LPCSTR", "LPSTR",
}


def name_params(params: str) -> str:
    if not params or params.strip() == "void":
        return "void"
    parts = []
    depth = 0
    current = []
    for ch in params:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    named = []
    for index, raw in enumerate(parts):
        piece = clean(raw)
        if not piece or piece == "void":
            continue
        if piece.endswith("..."):
            named.append(piece)
            continue
        pointer = re.sub(r"\(\s*(?:__\w+\s*)?\*\s*\)", f"(*p{index})", piece, count=1)
        if pointer != piece:
            named.append(pointer)
            continue
        tokens = piece.split()
        if tokens[-1] in TYPE_WORDS or tokens[-1].endswith("*"):
            named.append(piece + f" p{index}")
        else:
            named.append(piece)
    return ", ".join(named) or "void"


def emit(names: list[str], weak_names: set[str] | None = None) -> tuple[str, list[str]]:
    weak_names = weak_names or set()
    texts = load_texts()
    tops = {path: top_level(text) for path, text in texts.items()}
    lines = [
        "/* Typed definitions for symbols the reachable CE image still calls. */",
        '#include "cseries.h"',
        '#include "math/integer_math.h"',
        '#include "math/real_math.h"',
        '#include "rasterizer/rasterizer.h"',
        '#include "rasterizer/rasterizer_console_vars.h"',
        '#include "render/render.h"',
        '#include "game/cheats.h"',
        "#include <xtl.h>",
        "#include <xbdm.h>",
        "#include <string.h>",
        "",
    ]
    missing = []
    for name in names:
        if name == "fast_ftol_C":
            # Xbox FISTP helper behind cseries.h fast_ftol: round to nearest,
            # ties to even. Not a libc symbol, so it cannot be left to the
            # C library; implemented without libm because the link has no -lm.
            # NaN and out-of-range inputs (including values that round to
            # 2^31 or -2^31-1) return the x87 integer indefinite 0x80000000.
            # The range test happens before any (long) cast, so no UB.
            lines.append(
                "long fast_ftol_C(real x) { double d = (double)x; long i; double r;"
                " if (!(d > -2147483649.0 && d < 2147483648.0)) return (long)0x80000000UL;"
                " i = (long)d; r = d - (double)i;"
                " if (r > 0.5 || (r == 0.5 && (i & 1))) {"
                " if (i == 2147483647L) return (long)0x80000000UL; i++; }"
                " else if (r < -0.5 || (r == -0.5 && (i & 1))) {"
                " if (i == -2147483647L - 1) return (long)0x80000000UL; i--; }"
                " return i; }")
            continue
        if name in SKIP or name in {"render_location_visible", "D3D__RenderState"} or name.startswith("__") or classify(name) == "toolchain":
            continue
        if name == "platform_log":
            lines.append("void platform_log(const char *format, ...) {}")
            continue
        found = find_declaration(name, texts, tops)
        if not found:
            missing.append(name)
            continue
        kind, path, rtype, rest = found
        rtype = clean(rtype).replace("extern ", "")
        rtype = re.sub(r"\b(static|__inline|_inline|__forceinline|__cdecl|__stdcall|__fastcall|WINAPI)\b", "", rtype)
        rtype = " ".join(rtype.split())
        if kind == "data":
            if name == "dsound_globals":
                lines.append("unsigned char dsound_globals[30924];")
                continue
            dims = rest.replace("[]", "[4]")
            dims = re.sub(r"\[[A-Z_][A-Z0-9_]*\]", "[32]", dims)
            lines.append(f"{rtype} {name}{dims};")
            continue
        rest = re.sub(r"__attribute__\s*\(\(.*?\)\)", "", rest)
        params = name_params(rest)
        params = re.sub(r"\[[A-Z_][A-Z0-9_]*\]", "[32]", params)
        if rtype == "void":
            body = ""
        else:
            body = f"{rtype} result; memset(&result, 0, sizeof(result)); return result;"
        linkage = "__attribute__((weak)) " if name in weak_names else ""
        lines.append(f"{linkage}{rtype} {name}({params}) {{ {body} }}")
    return "\n".join(lines) + "\n", missing


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-bootstrap-memory", action="store_true",
                        help="link the external-only memory provider profile")
    parser.add_argument("--m2-ui-lifecycle-test", action="store_true",
                        help="link the opt-in CE UI lifecycle diagnostic closure")
    parser.add_argument("--step8-mp-capacity-diagnostic", action="store_true",
                        help="link the isolated target-sized Sidewinder load/query diagnostic")
    parser.add_argument("--step8-mp-workload-only", action="store_true",
                        help="link the Step 8 CE local-player workload-only image")
    parser.add_argument("--step8-mp-workload-players", type=int, choices=(2, 4), default=2,
                        help="local split-screen players for workload-only image (2 or CE maximum 4)")
    parser.add_argument("--m2-animation-trace", action="store_true",
                        help="link the opt-in CE animation trace diagnostic closure")
    parser.add_argument("--production-runtime-guest", action="store_true",
                        help="link the selected-map production guest closure")
    args = parser.parse_args()
    if args.no_bootstrap_memory:
        OUT = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory"
    if args.m2_ui_lifecycle_test:
        if not args.no_bootstrap_memory:
            parser.error("--m2-ui-lifecycle-test requires --no-bootstrap-memory")
        OUT = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory-m2-ui-lifecycle"
    if args.step8_mp_capacity_diagnostic:
        if not args.no_bootstrap_memory or not args.m2_ui_lifecycle_test:
            parser.error("--step8-mp-capacity-diagnostic requires --no-bootstrap-memory and --m2-ui-lifecycle-test")
        OUT = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory-step8-mp-capacity"
    if args.step8_mp_workload_only:
        if not args.step8_mp_capacity_diagnostic:
            parser.error("--step8-mp-workload-only requires --step8-mp-capacity-diagnostic")
        OUT = ROOT / f"build/hcu-ps2-closure/all-no-bootstrap-memory-step8-mp-workload-{args.step8_mp_workload_players}p"
    elif args.step8_mp_workload_players != 2:
        parser.error("--step8-mp-workload-players requires --step8-mp-workload-only")
    if args.m2_animation_trace:
        if not args.no_bootstrap_memory or args.m2_ui_lifecycle_test:
            parser.error("--m2-animation-trace requires --no-bootstrap-memory and is separate from lifecycle test")
        OUT = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory-m2-animation-trace"
    if args.production_runtime_guest:
        if not args.no_bootstrap_memory or args.m2_ui_lifecycle_test:
            parser.error("--production-runtime-guest requires --no-bootstrap-memory and is separate from diagnostics")
        OUT = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory-production-runtime-guest"
    if os.environ.get("HCU_C3") == "1":
        # C3 (opt-in) closure lives beside, never inside, the default closure directory.
        OUT = OUT.with_name(OUT.name + "-hcu-c3")
        if os.environ.get("HCU_C3_TELEMETRY") == "1":
            # Same directory name as hcu_ps2_closure.py and hcu_parent_link_probe.py.
            OUT = OUT.with_name(OUT.name + "-telemetry")
        if os.environ.get("HCU_C3_REALTIME_SCHEDULER") == "1":
            OUT = OUT.with_name(OUT.name + "-realtime")
        if os.environ.get("HCU_C3_SNAPSHOT_INDEX") == "1":
            OUT = OUT.with_name(OUT.name + "-snapshot-index")
        if os.environ.get("HCU_C3_MOVEMENT_TRACE") == "1":
            OUT = OUT.with_name(OUT.name + "-movement-trace")
    build, prefix, env, _jobs = environment()
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    size = prefix / "ee/bin/mips64r5900el-ps2-elf-size"
    linkfile = prefix / "ps2sdk/ee/startup/linkfile"
    header = HCU / "port/ps2/include/halo_ps2_prefix.h"
    flags = [
        "-std=gnu89", "-Os", "-mabi=n32", "-G0", "-fms-extensions", "-fshort-wchar",
        "-fcommon", "-ffp-contract=off", "-fsigned-char", "-fwrapv", "-D_EE",
        "-D__STRICT_ANSI__", "-w", "-I" + str(HCU / "port/ps2/include"),
        "-I" + str(HCU / "source"), "-I" + str(HCU / "source/cseries"),
        "-I" + str(HCU / "source/cache"), "-I" + str(HCU / "source/tag_files"),
        "-I" + str(HCU / "source/memory"),
        "-I" + str(HCU / "source/math"),
        "-I" + str(HCU / "source/rasterizer"),
        "-I" + str(HCU / "source/render"),
        "-I" + str(HCU / "source/game"),
        "-I" + str(HCU / "source/sound"),
        "-I" + str(HCU / "port/include"),
        "-I" + str(HCU / "port/include/xdk"),
        "-I" + str(prefix / "ps2sdk/common/include"),
        "-I" + str(prefix / "ps2sdk/ee/include"),
        "-include", str(header),
        "-include", str(OUT / "halo_ps2_msvc_semantics.h"),
    ]
    units = [
        HCU / "port/ps2/src/ps2_main.c",
        HCU / "port/ps2/src/ps2_abi.c",
        HCU / "port/ps2/src/ps2_memory.c",
        HCU / "port/ps2/src/ps2_crt.c",
        HCU / "port/ps2/src/ps2_edge.c",
        HCU / "port/ps2/src/ps2_sound_playback_bind.c",
    ]
    objects = []
    for source in units:
        obj = OUT / (source.stem + ".o")
        extra = []
        if args.no_bootstrap_memory and source.name == "ps2_memory.c":
            extra.append("-DHALO_PS2_NO_BOOTSTRAP_MEMORY")
        if args.production_runtime_guest and source.name == "ps2_memory.c":
            extra.append("-DHALO_PS2_C2_PRODUCTION_RUNTIME_GUEST")
        if args.step8_mp_capacity_diagnostic and source.name == "ps2_memory.c":
            extra.append("-DHALO_PS2_STEP8_MEMORY_DIAGNOSTIC")
        run = subprocess.run([str(compiler), *flags, *extra, "-c", str(source), "-o", str(obj)],
                             cwd=ROOT, env=env, text=True, capture_output=True)
        if run.returncode:
            sys.exit(run.stderr or run.stdout)
        objects.append(obj)
    undefined = sorted({line.split()[-1] for line in subprocess.check_output(
        [str(nm), "-u", str(OUT / "rooted.o")], text=True).splitlines() if line.strip()})
    excluded = ({"hcu_map_service_lifecycle_trace",
                 "hcu_map_service_lifecycle_fail_preflight_once",
                 "hcu_map_service_lifecycle_arm_deferred_failure_once",
                 "hcu_map_service_lifecycle_consume_deferred_failure",
                 "halo_ps2_step8_mp_candidate_guards_intact"}
                if args.m2_ui_lifecycle_test else set())
    if args.step8_mp_capacity_diagnostic:
        excluded.add("physical_memory_get_malloc_diagnostics")
    generated, missing = emit(undefined, excluded)
    platform = OUT / "ps2_platform.c"
    platform.write_text(generated)
    (OUT / "ps2_platform_missing.txt").write_text("\n".join(missing) + ("\n" if missing else ""))
    platform_obj = OUT / "ps2_platform.o"
    run = subprocess.run([str(compiler), *flags, "-c", str(platform), "-o", str(platform_obj)],
                         cwd=ROOT, env=env, text=True, capture_output=True)
    (OUT / "ps2_platform.log").write_text(run.stdout + run.stderr)
    if run.returncode:
        sys.exit(f"platform compile failed; see {OUT / 'ps2_platform.log'}")
    elf = OUT / "halo-local.elf"
    map_file = OUT / "halo-local.map"
    link = subprocess.run(
        [str(compiler), "-mabi=n32", "-G0", "-T", str(linkfile),
         "-Wl,--gc-sections", "-Wl,--wrap,malloc", "-Wl,--wrap,free",
         "-Wl,--wrap,calloc", "-Wl,--wrap,realloc",
         "-Wl,-Map," + str(map_file),
         "-o", str(elf), *[str(obj) for obj in objects], str(platform_obj), str(OUT / "rooted.o")],
        cwd=ROOT, env=env, text=True, capture_output=True)
    (OUT / "elf-link.log").write_text(link.stdout + link.stderr)
    if link.returncode:
        sys.exit(f"ELF link failed; see {OUT / 'elf-link.log'}")
    print(subprocess.check_output([str(size), str(elf)], text=True))
    print(elf)


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"HCU PS2 link failed: {error}")
