"""Measure one HCU PlayStation 2 compile layer and record live relocations.

The manifest is submodules/halo-ce-universal/port/ps2/port.json. A missing
simulation symbol stays unresolved. This tool does not generate stubs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from build_toolchain import ROOT, environment, save

HCU = ROOT / "submodules/halo-ce-universal"
MANIFEST_PATH = HCU / "port/ps2/port.json"

TOOLCHAIN_RUNTIME = {
    "floor", "fmod", "rint", "scalbn", "sqrt", "strrchr", "memcpy", "memmove", "memset", "memcmp",
    "memchr", "qsort", "rand", "atoi", "atof", "exit", "rewind", "time", "localtime", "strerror",
    "acos", "asin", "atan2", "ceil", "cos", "sin", "tan", "log10", "pow", "tolower", "towlower", "towupper",
    "isalpha", "isspace", "iswalnum", "iswalpha", "iswcntrl", "iswdigit", "iswgraph", "iswlower",
    "iswprint", "iswpunct", "iswspace", "iswupper", "iswxdigit",
    "strchr", "strcmp", "strcpy", "strlen", "strncat", "strncmp", "strncpy", "strstr", "strtok",
    "fputs", "printf", "puts", "gmtime_r",
    "snprintf", "sprintf", "vsnprintf", "vsprintf",
    "fclose", "fdopen", "fflush", "fgets", "fopen", "fprintf", "fputc", "fread", "fscanf", "fseek", "ftell", "fwrite",
    "fgetwc", "fgetws", "fputwc", "fputws", "ungetwc", "vfwprintf", "vswprintf", "vwprintf",
    "wcscat", "wcschr", "wcscmp", "wcscoll", "wcscpy", "wcscspn", "wcslen", "wcsncat", "wcsncmp",
    "wcsncpy", "wcspbrk", "wcsrchr", "wcsspn", "wcsstr", "wcstod", "wcstol", "wcstoul", "wcsxfrm",
    "_ctype_", "_errno", "_impure_ptr", "_snprintf", "_vsnprintf", "_vsnwprintf", "_stricmp", "_strnicmp",
    "_getws", "_putws", "_wasctime", "_wcsicmp", "_wcslwr", "_wcsnicmp", "_wcsupr", "_wctime",
    "_wfdopen", "_wfopen", "_wfreopen", "_wperror", "_wremove", "_wtmpnam", "_wtoi",
    "fast_ftol_C", "_ReadWriteBarrier",
}
PS2_SERVICES = {
    "platform_log", "malloc", "free", "calloc", "realloc",
    "system_malloc", "system_free", "system_calloc", "system_realloc",
    "display_debug_string", "system_milliseconds", "system_seconds",
    "system_unique_identifier_get", "system_unique_identifiers_equal",
    "system_get_user_name", "_control87", "_controlfp", "_clearfp", "_statusfp",
    "halo_ps2_wcstok", "halo_keyboard_actions", "halo_push_to_talk_held",
    "halo_ui_pointer_update", "halo_scoreboard_pointer_update",
    "platform_scoreboard_scroll", "platform_show_message", "remap_sticks_for_local_player",
    "stack_walk", "stack_walk_dispose", "stack_walk_initialize", "stack_walk_with_context",
    "display_error_abort_to_dashboard_deferred", "display_error_damaged_media",
    "display_error_deferred", "display_error_text_when_main_menu_loaded",
    "display_error_when_main_menu_loaded", "display_errors_deferred_until_cinematic_stop",
    "display_scenario_help", "interrupt_result",
    "halo_ps2_render_snapshot_begin", "halo_ps2_render_snapshot_commit",
}
PS2_SERVICE_PREFIXES = (
    "cache_file_", "cache_files_", "texture_cache_", "sound_cache_", "_texture_cache_", "_sound_cache_",
    "physical_memory_", "XInput", "XDEVICE_", "XFind", "XCreate", "XDelete", "XGet", "XInit",
    "XCalculate", "XPhysical", "Create", "Read", "Write", "Find", "Delete", "Move", "Remove",
    "Close", "Wait", "Sleep", "Set", "Get", "Global", "Local", "Virtual", "Query", "Copy",
    "Resume", "Switch", "Output", "Release",
)
EXCLUDED_EXACT = {
    "allow_out_of_sync", "attract_mode_start", "cheat", "config_boolean", "config_changes",
    "config_real", "config_string", "create_global_network_game_client", "create_global_network_game_server",
    "create_mutex", "create_thread", "dispose_global_network_game_client", "dispose_global_network_game_server",
    "dispose_mutex", "dispose_thread", "release_mutex", "take_mutex", "thread_has_exited",
    "distributed_player_from_byte", "distributed_player_ping", "distributed_player_to_byte",
    "game_end_credits_start", "game_in_editor", "global_connection_dont_timeout",
    "halo_custom_edition_tag_cache", "halo_interpolation_enabled", "halo_linux_mouse_aiming",
    "halo_linux_mouse_look", "halo_linux_touch_aiming", "halo_linux_touch_look", "halo_linux_touch_move",
    "halo_screen_width", "initialize_network_game_packets", "main_menu_active", "main_menu_is_active",
    "network_distributed_new_game", "network_distributed_player_killed",
    "network_distributed_player_picked_up", "network_distributed_tick", "network_test_update",
    "pc_menus_screen", "reset_last_player1_profile_index", "timeout_for_endgame_sound",
    "transport_dispose", "transport_initialize", "ui_set_next_level", "xbox_demos_launch",
    "xbox_set_machine_name", "global_ai_debug_string_position", "profile_display", "profile_graph",
}
EXCLUDED_PREFIXES = (
    "IDirect3D", "Direct3D", "D3D", "DirectSound", "IDirectSound", "Bink", "bink_", "XNet", "WSA",
    "custom_edition_", "editor_", "network_coop_", "network_voice_", "network_votekick_",
    "network_game_", "map_share_", "mods_", "menu_tags_", "debug_", "collision_debug", "Dm",
    "telnet_", "virtual_keyboard_", "progress_bar_", "coop_", "dsound_", "d3d_", "tiff_",
    "connected_geometry_", "main_screen_", "ui_main_menu_", "ui_stop_main_menu", "ui_widget",
)
SIMULATION_EXACT = {
    "network_actors_drive", "network_actors_note_control", "network_actors_note_impulse",
    "network_actors_note_leap", "network_actors_note_melee", "network_actors_note_speech",
    "network_actors_note_user_animation", "network_damage_aftermath", "network_damage_deals",
    "network_damage_killer_score", "network_damage_note_grenade", "network_damage_player_effect",
    "network_damage_replaying_kill", "network_objects_client_picked_up_weapon",
    "network_objects_creating_host_object", "network_objects_damage_animation",
    "network_objects_may_delete", "network_objects_new_object_index", "network_objects_placed",
    "object_bounds_cache_invalidate", "object_bounds_cache_out_of_reach", "object_bounds_cache_update",
    "global_network_game_client_get", "global_network_game_server_get", "network_game_is_active",
    "network_coop_active", "network_coop_player_collisions", "network_coop_devices_remote",
    "network_coop_set_players_vitality", "network_coop_player_has_structure_bsp",
    "network_coop_skip_offered", "network_coop_vote_skip", "network_coop_skip_vote_status",
    "network_coop_reverted", "network_coop_skip_done", "network_coop_vehicle_dropped",
    "coop_scripts_any_player_will_do", "coop_scripts_gather_in_volume",
    "coop_scripts_teleport_followers", "coop_scripts_unit_near", "coop_scripts_arrive_at",
    "coop_scripts_suspend_followers", "coop_scripts_exit_followers",
    "coop_scripts_board_followers", "coop_scripts_safe_to_save",
    "coop_scripts_player_add_equipment",
    "coop_enemies_extra_count", "coop_enemies_rider_unseated",
}
SIMULATION_PREFIXES = ("network_damage_", "network_objects_", "network_actors_")
DATA_EXACT = {
    "ai_globals", "contrail_data", "contrail_point_data", "conversation_data", "device_groups_data",
    "effect_data", "error_globals", "game_engine_globals", "game_variant_global", "global_decal_data",
    "global_stage", "global_tag_instances", "particle_data", "prop_data",     "scenario_globals",
}
RENDER_EXACT = {
    "build_sprite", "build_sprite_rotational", "build_sprites_begin", "build_sprites_end",
    "first_person_legs_reset", "hud_hires_button_draw", "hud_hires_sprite_bitmap",
    "hud_hires_tags_loaded", "hud_hires_tags_unloaded", "object_get_cached_render_lighting",
    "pal_tags_first_person_advance", "pal_tags_first_person_fraction", "pal_tags_first_person_frames",
    "pal_tags_loaded", "powerup_render_bounds_tags_loaded", "process_ui_widgets", "render",
    "rendered_cluster_get", "shield_color_colors", "shield_glow_update",
    "structure_bsp_header_deregister_vertex_buffers", "structure_bsp_header_register_vertex_buffers",
    "structure_render_diffuse_light", "structure_render_set_fog_offset", "structure_render_specular_light",
    "tags_header_deregister_vertex_and_index_buffers", "tags_header_register_vertex_and_index_buffers",
    "viewmodel_is_visible", "viewmodel_shield_is_visible",
    "global_rasterizer_model_ambient_reflection_tint", "coop_spectate_camera",
    "coop_spectate_unit", "coop_spectating", "coop_skip_vote_draw", "main_screen_shell_begin_fade",
    "main_screen_shell_load", "menu_tags_loaded", "menu_tags_unloaded",
    "progress_bar_begin", "progress_bar_dispose", "progress_bar_end",
    "progress_bar_initialize", "ui_widget_load_by_name_or_tag",
    "ui_widget_load_progress_widget", "ui_widgets_active_for_local_player",
    "ui_widgets_close_all", "ui_widgets_disable_pause_game", "ui_widgets_dispose",
    "ui_widgets_inhibit_processing", "ui_widgets_initialize",
    "ui_widgets_safe_to_load", "ui_widgets_set_fade_value",
}
SOUND_EXACT = {"ui_main_menu_music_active", "ui_stop_main_menu_music"}
RENDER_PREFIXES = ("rasterizer_", "render_", "draw_", "structure_render_", "build_sprite")

FLAGS = [
    "-std=gnu89", "-Os", "-mabi=n32", "-fms-extensions", "-fshort-wchar", "-fcommon",
    "-fno-strict-aliasing", "-fno-delete-null-pointer-checks", "-ffp-contract=off",
    "-fsigned-char", "-fwrapv", "-ffunction-sections", "-fdata-sections",
    "-G0", "-D_EE", "-D__STRICT_ANSI__", "-w",
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def selected_sources(manifest: dict) -> list[str]:
    exclude_dirs = tuple(manifest["exclude_dirs"])
    exclude_sources = set(manifest["exclude_sources"])
    chosen = []
    for path in sorted((HCU / "source").rglob("*.c")):
        rel = path.relative_to(HCU).as_posix()
        if rel in exclude_sources or rel.startswith(exclude_dirs):
            continue
        chosen.append(rel)
    for extra in manifest["extra_game_sources"]:
        if extra not in chosen:
            chosen.append(extra)
    return chosen


def classify(symbol: str) -> str:
    if symbol.startswith("__") or symbol in TOOLCHAIN_RUNTIME:
        return "toolchain"
    if symbol in SIMULATION_EXACT or symbol.startswith(SIMULATION_PREFIXES):
        return "simulation"
    if symbol in DATA_EXACT or symbol.startswith(("tag_", "data_", "datum_")):
        return "data"
    if symbol in SOUND_EXACT:
        return "sound"
    if symbol in PS2_SERVICES or symbol.startswith(PS2_SERVICE_PREFIXES):
        return "ps2-service"
    if symbol in RENDER_EXACT or symbol.startswith(RENDER_PREFIXES):
        return "render"
    if symbol in EXCLUDED_EXACT or symbol.startswith(EXCLUDED_PREFIXES):
        return "excluded-feature"
    return "unclassified"


def undefined_symbols(nm: Path, obj: Path) -> set[str]:
    output = subprocess.check_output([str(nm), "-u", str(obj)], text=True)
    return {line.split()[-1] for line in output.splitlines() if line.strip()}


def live_external_symbols(nm: Path, objdump: Path, obj: Path) -> list[str]:
    return sorted(live_external_relocations(nm, objdump, obj))


def live_external_relocations(nm: Path, objdump: Path, obj: Path) -> dict[str, list[str]]:
    """Map each undefined symbol with a live relocation to its input section(s)."""
    undefined = undefined_symbols(nm, obj)
    relocations = subprocess.check_output([str(objdump), "-r", str(obj)], text=True)
    current_section = ""
    callers: dict[str, set[str]] = {}
    for line in relocations.splitlines():
        match = re.match(r"RELOCATION RECORDS FOR \[(.+)\]:$", line.strip())
        if match:
            current_section = match.group(1)
            continue
        fields = line.split()
        if len(fields) < 3 or not fields[1].startswith("R_MIPS_"):
            continue
        symbol = fields[2].split("+", 1)[0]
        if symbol in undefined:
            callers.setdefault(symbol, set()).add(current_section)
    return {symbol: sorted(sections) for symbol, sections in sorted(callers.items())}


def section_function(section: str) -> str:
    for prefix in (".text.", ".gnu.linkonce.t."):
        if section.startswith(prefix):
            return section[len(prefix):]
    return ""


def section_data_symbol(section: str) -> str:
    for prefix in (".data.", ".rodata.", ".bss.", ".sdata.", ".sbss."):
        if section.startswith(prefix):
            return section[len(prefix):]
    return ""


def object_symbol_owners(nm: Path, members: list[tuple[str, Path]]) -> dict[str, list[str]]:
    owners: dict[str, set[str]] = {}
    for source, obj in members:
        output = subprocess.check_output(
            [str(nm), "--defined-only", str(obj)], text=True)
        for line in output.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            symbol = fields[-1]
            symbol_type = fields[-2]
            if symbol_type in {"t", "T", "w", "W", "d", "D", "r", "R", "b", "B", "s", "S"}:
                owners.setdefault(symbol, set()).add(source)
    return {symbol: sorted(sources) for symbol, sources in owners.items()}


def section_bytes(size: Path, obj: Path) -> dict[str, int]:
    output = subprocess.check_output([str(size), "-A", str(obj)], text=True)
    found = {".text": 0, ".data": 0, ".bss": 0, ".rodata": 0}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        for key in found:
            if parts[0] == key or parts[0].startswith(key + "."):
                found[key] += int(parts[1])
                break
    return found


def first_error(text: str) -> str:
    for line in text.splitlines():
        if ": error:" in line or ": fatal error:" in line:
            return line
    return ""


def error_key(text: str) -> str:
    marker = ": error:"
    fatal = ": fatal error:"
    if fatal in text:
        return text.split(fatal, 1)[1].strip()
    if marker in text:
        return text.split(marker, 1)[1].strip()
    return text.strip() or "(no diagnostic)"


def compile_unit(compiler: Path, flags: list[str], env: dict, source: Path, obj: Path, extra: list[str]) -> tuple[int, str]:
    run = subprocess.run([str(compiler), *flags, *extra, str(source), "-o", str(obj)],
                         cwd=ROOT, env=env, text=True, capture_output=True)
    return run.returncode, run.stdout + run.stderr


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", default="math-memory",
                        help="a manifest layer name, or 'all' for every selected source")
    parser.add_argument("--no-bootstrap-memory", action="store_true",
                        help="compile the selected layer with caller-owned PS2 memory only")
    parser.add_argument("--m2-ui-lifecycle-test", action="store_true",
                        help="compile the opt-in CE UI unload/reload diagnostic variant")
    parser.add_argument("--step8-mp-capacity-diagnostic", action="store_true",
                        help="compile the isolated target-sized Sidewinder load/query diagnostic")
    parser.add_argument("--step8-mp-workload-only", action="store_true",
                        help="compile only the test-only CE local-player workload, skipping 13 map queries")
    parser.add_argument("--step8-mp-workload-players", type=int, choices=(2, 4), default=2,
                        help="local split-screen players for the workload-only diagnostic (2 or CE maximum 4)")
    parser.add_argument("--m2-animation-trace", action="store_true",
                        help="compile the opt-in bounded animation touch observer")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text())
    if args.layer != "all" and args.layer not in manifest["layers"]:
        raise RuntimeError(f"Unknown layer {args.layer}")
    for name in manifest["rejected_defines"]:
        if any(item.startswith(name) for item in manifest["defines"]):
            raise RuntimeError(f"{name} is set in the PS2 manifest")
    build, prefix, env, jobs = environment()
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    objdump = prefix / "ee/bin/mips64r5900el-ps2-elf-objdump"
    linker = prefix / "ee/bin/mips64r5900el-ps2-elf-ld"
    size = prefix / "ee/bin/mips64r5900el-ps2-elf-size"
    if not compiler.is_file():
        raise RuntimeError("Compiler installation is incomplete; finish make toolchain first")
    profile = "-no-bootstrap-memory" if args.no_bootstrap_memory else ""
    if args.m2_ui_lifecycle_test:
        profile += "-m2-ui-lifecycle"
    if args.step8_mp_capacity_diagnostic:
        if not args.no_bootstrap_memory or not args.m2_ui_lifecycle_test:
            parser.error("--step8-mp-capacity-diagnostic requires --no-bootstrap-memory and --m2-ui-lifecycle-test")
        profile = "-no-bootstrap-memory-step8-mp-capacity"
    if args.step8_mp_workload_only:
        if not args.step8_mp_capacity_diagnostic:
            parser.error("--step8-mp-workload-only requires --step8-mp-capacity-diagnostic")
        profile = f"-no-bootstrap-memory-step8-mp-workload-{args.step8_mp_workload_players}p"
    elif args.step8_mp_workload_players != 2:
        parser.error("--step8-mp-workload-players requires --step8-mp-workload-only")
    if args.m2_animation_trace:
        profile += "-m2-animation-trace"
    output = build / "hcu-ps2-closure" / (args.layer + profile)
    output.mkdir(parents=True, exist_ok=True)
    header = HCU / manifest["prefix"]
    semantics = output / "halo_ps2_msvc_semantics.h"
    subprocess.run(
        [sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
         "--output", str(semantics), "--all-inlines",
         "--tags", str(HCU / "source"),
         "--inlines", str(HCU / "source"),
         "--inlines", str(HCU / "port/include/xdk")],
        cwd=ROOT, check=True)
    includes = ["-I" + str(HCU / item) for item in manifest["include_dirs"]]
    includes.extend(("-I" + str(prefix / "ps2sdk/common/include"),
                     "-I" + str(prefix / "ps2sdk/ee/include")))
    source_flags = [("-Oz" if args.m2_ui_lifecycle_test and flag == "-Os" else flag)
                    for flag in FLAGS]
    flags = [*source_flags, *includes, "-include", str(header), "-include", str(semantics), "-c"]
    members = selected_sources(manifest)
    report = {
        "status": "layer-measured",
        "milestone": "M0",
        "gate": "open",
        "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
        "flags": source_flags,
        "base_flags": FLAGS,
        "prefix": manifest["prefix"],
        "prefix_sha256": digest(header),
        "manifest_sha256": digest(MANIFEST_PATH),
        "hcu_commit": subprocess.check_output(["git", "-C", str(HCU), "rev-parse", "HEAD"], text=True).strip(),
        "selected_source_count": len(members),
        "layer": args.layer,
        "profile_defines": ((["HALO_PS2_NO_BOOTSTRAP_MEMORY"]
                             if args.no_bootstrap_memory else []) +
                            (["HALO_PS2_M2_UI_LIFECYCLE_TEST"]
                             if args.m2_ui_lifecycle_test else []) +
                            (["HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC"]
                             if args.step8_mp_capacity_diagnostic else []) +
                            (["HALO_PS2_TEST", "HALO_PS2_STEP8_MEMORY_DIAGNOSTIC"]
                             if args.step8_mp_capacity_diagnostic else []) +
                            (["HALO_PS2_STEP8_MP_WORKLOAD_ONLY"]
                             if args.step8_mp_workload_only else []) +
                            ([f"HALO_PS2_STEP8_MP_WORKLOAD_PLAYERS={args.step8_mp_workload_players}"]
                             if args.step8_mp_workload_only else []) +
                            (["HALO_PS2_M2_ANIMATION_TRACE"]
                             if args.m2_animation_trace else [])),
        "profile_source_overrides": ({
            "source/main/main.c": ["HALO_PS2_M2_UI_LIFECYCLE_TEST"],
            "source/scenario/scenario.c": ["-Oz"],
            "source/main/ps2_m2_ui_lifecycle_test.c": [
                "HALO_PS2_M2_UI_LIFECYCLE_TEST", "-Oz"],
        } if args.m2_ui_lifecycle_test else {}),
        "limits": "One compile layer. Unresolved symbols are not stubs. Byte totals are the layer's object sections only.",
        "units": {},
    }
    layer_sources = list(members if args.layer == "all" else manifest["layers"][args.layer])
    layer_sources.extend(manifest.get("port_sources", []))
    pending = []
    for relative in layer_sources:
        source = HCU / relative
        obj = output / (relative.replace("/", "_") + ".o")
        extra = manifest["source_flags"].get(relative, "").split()
        if args.no_bootstrap_memory:
            extra.append("-DHALO_PS2_NO_BOOTSTRAP_MEMORY")
        if args.m2_ui_lifecycle_test and relative in (
                "source/main/main.c", "source/scenario/scenario.c",
                "source/main/ps2_m2_ui_lifecycle_test.c"):
            extra.append("-DHALO_PS2_M2_UI_LIFECYCLE_TEST")
        if args.step8_mp_capacity_diagnostic and relative in (
                "source/main/main.c", "source/main/ps2_m2_ui_lifecycle_test.c"):
            extra.append("-DHALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC")
        if args.step8_mp_capacity_diagnostic and relative in (
                "source/main/main.c", "source/main/ps2_m2_ui_lifecycle_test.c"):
            extra.append("-DHALO_PS2_TEST")
        if args.step8_mp_capacity_diagnostic and relative in (
                "source/main/ps2_m2_ui_lifecycle_test.c",
                "source/saved games/game_state.c", "source/objects/objects.c"):
            extra.append("-DHALO_PS2_STEP8_MEMORY_DIAGNOSTIC")
        if args.step8_mp_workload_only and relative == "source/main/ps2_m2_ui_lifecycle_test.c":
            extra.append("-DHALO_PS2_STEP8_MP_WORKLOAD_ONLY")
            extra.append(f"-DHALO_PS2_STEP8_MP_WORKLOAD_PLAYERS={args.step8_mp_workload_players}")
        if args.m2_ui_lifecycle_test and relative in (
                "source/scenario/scenario.c",
                "source/main/ps2_m2_ui_lifecycle_test.c"):
            # Keep diagnostic-only CE trace/orchestration small without
            # changing the optimization profile of production code.
            extra.append("-Oz")
        if args.m2_animation_trace:
            extra.append("-DHALO_PS2_M2_ANIMATION_TRACE")
        pending.append((relative, source, obj, extra))
    objects = []
    compiled_object_sources = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = pool.map(lambda item: compile_unit(compiler, flags, env, item[1], item[2], item[3]), pending)
        for (relative, source, obj, _extra), (code, log_text) in zip(pending, results):
            log = output / (obj.stem + ".log")
            if code:
                log.write_text(log_text)
            unit = {"source_sha256": digest(source), "status": "compiled" if code == 0 else "failed"}
            if code:
                unit["log"] = str(log.relative_to(ROOT))
                unit["first_error"] = first_error(log_text)
            else:
                unit["object_sha256"] = digest(obj)
                unit["sections"] = section_bytes(size, obj)
                objects.append(obj)
                compiled_object_sources.append((relative, obj))
            report["units"][relative] = unit
    groups: dict[str, list[str]] = {}
    for relative, unit in report["units"].items():
        if unit["status"] == "failed":
            groups.setdefault(error_key(unit["first_error"]), []).append(relative)
    report["error_groups"] = {key: paths for key, paths in sorted(groups.items(), key=lambda item: -len(item[1]))}
    compiled = [name for name, unit in report["units"].items() if unit["status"] == "compiled"]
    report["compiled_count"] = len(compiled)
    report["failed_count"] = len(report["units"]) - len(compiled)
    if objects:
        combined = output / "layer.o"
        response = output / "objects.rsp"
        response.write_text("".join(f"\"{path}\"\n" for path in objects))
        link = subprocess.run([str(linker), "-r", f"@{response}", "-o", str(combined)],
                              cwd=ROOT, env=env, text=True, capture_output=True)
        (output / "partial-link.log").write_text(link.stdout + link.stderr)
        if link.returncode:
            report["status"] = "link-failed"
            report["link_log"] = str((output / "partial-link.log").relative_to(ROOT))
        else:
            live = live_external_symbols(nm, objdump, combined)
            classes: dict[str, list[str]] = {}
            for symbol in live:
                classes.setdefault(classify(symbol), []).append(symbol)
            report["partial_link"] = {
                "object_sha256": digest(combined),
                "sections": section_bytes(size, combined),
                "live_external_count": len(live),
                "classes": classes,
            }
            text = report["partial_link"]["sections"].get(".text", 0)
            data = report["partial_link"]["sections"].get(".data", 0)
            bss = report["partial_link"]["sections"].get(".bss", 0)
            rodata = report["partial_link"]["sections"].get(".rodata", 0)
            report["elf_static_account"] = {
                "region": "elf_static",
                "region_bytes": 2097152,
                "layer_text_data_rodata_bss": text + data + rodata + bss,
                "note": "Sum of every compiled section. The rooted link below is the reachable image.",
            }
            rooted = output / "rooted.o"
            roots = ["game_initialize", "game_tick", "halo_shell_main", "actors_update", "hs_update",
                     "ps2_cache_mount_ctag", "ps2_cache_mount_ctag_with_file_source",
				     "ps2_cache_mount_ctag_stream", "ps2_cache_set_ctag_visitor",
				     "ps2_ctag_stream_validator_begin",
				     "ps2_ctag_stream_validator_write",
				     "ps2_ctag_stream_validator_finish",
                     "ps2_cache_mount_cbsp_for_extent", "ps2_cache_set_bsp_loader",
                     "ps2_cache_set_bsp_visitor",
                     "ps2_cache_set_map_loader", "ps2_cache_set_map_preflight",
                     "ps2_cache_preflight_map", "ps2_cache_set_map_unloader",
                     "ps2_cache_release_map_owner", "tag_validate_claims_buffer_ready",
                     "tag_validate_bind_claims_buffer",
                     "tag_validate_release_claims_buffer",
                     "physical_memory_bind_game_state",
                     "physical_memory_bind_tag_cache",
                     "physical_memory_bind_structure_bsp_cache",
                     "physical_memory_bind_texture_cache",
                     "physical_memory_bind_sound_cache",
                     "physical_memory_bind_malloc_arena",
                     "physical_memory_bind_tag_validation_scratch",
                     "ps2_input_poll_devices", "ps2_input_publish_dualshock"]
            if args.m2_animation_trace:
                roots.append("ps2_animation_trace_bind")
                roots.append("ps2_animation_trace_bind_contexts")
            rooted_link = subprocess.run(
                [str(linker), "-r", "--gc-sections", *[arg for name in roots for arg in ("-u", name)],
                 f"@{response}", "-o", str(rooted)],
                cwd=ROOT, env=env, text=True, capture_output=True)
            (output / "rooted-link.log").write_text(rooted_link.stdout + rooted_link.stderr)
            if rooted_link.returncode == 0:
                rooted_sections = section_bytes(size, rooted)
                rooted_code = rooted_sections[".text"] + rooted_sections[".data"] + rooted_sections[".rodata"]
                rooted_relocations = live_external_relocations(nm, objdump, rooted)
                rooted_classes: dict[str, list[str]] = {}
                for symbol in rooted_relocations:
                    rooted_classes.setdefault(classify(symbol), []).append(symbol)
                symbol_owners = object_symbol_owners(nm, compiled_object_sources)
                live_external_rows = []
                for symbol, sections in rooted_relocations.items():
                    functions = sorted({section_function(section) for section in sections
                                        if section_function(section)})
                    data_symbols = sorted({section_data_symbol(section) for section in sections
                                           if section_data_symbol(section)})
                    sources = sorted({source for caller in (*functions, *data_symbols)
                                      for source in symbol_owners.get(caller, [])})
                    live_external_rows.append({
                        "symbol": symbol,
                        "classification": classify(symbol),
                        "caller_sections": sections,
                        "caller_functions": functions,
                        "caller_data_symbols": data_symbols,
                        "caller_source_candidates": sources,
                    })
                report["rooted_link"] = {
                    "roots": roots,
                    "sections": rooted_sections,
                    "code_constants_static_data": rooted_code,
                    "elf_static_bytes": 2097152,
                    "elf_static_spare": 2097152 - rooted_code,
                    "live_external_count": len(live_external_rows),
                    "classes": {name: sorted(symbols)
                                for name, symbols in rooted_classes.items()},
                    "live_externals": live_external_rows,
                }
    else:
        report["status"] = "layer-failed"
    if args.no_bootstrap_memory:
        memory_source = HCU / "port/ps2/src/ps2_memory.c"
        memory_object = output / "ps2_memory_no_bootstrap.o"
        code, log_text = compile_unit(
            compiler, flags, env, memory_source, memory_object,
            ["-DHALO_PS2_NO_BOOTSTRAP_MEMORY"] +
            (["-DHALO_PS2_STEP8_MEMORY_DIAGNOSTIC"]
             if args.step8_mp_capacity_diagnostic else []),
        )
        memory_result = {
            "source_sha256": digest(memory_source),
            "status": "compiled" if code == 0 else "failed",
        }
        if code == 0:
            memory_result["object_sha256"] = digest(memory_object)
            memory_result["sections"] = section_bytes(size, memory_object)
            symbols = subprocess.check_output([str(nm), "-S", str(memory_object)], text=True)
            symbol_names = {line.split()[-1] for line in symbols.splitlines() if line.split()}
            forbidden = {"game_state", "tag_cache", "texture_cache", "sound_cache", "malloc_arena"}
            memory_result["bootstrap_storage_symbols"] = sorted(symbol_names & forbidden)
            if memory_result["bootstrap_storage_symbols"]:
                memory_result["status"] = "unexpected-bootstrap-storage"
        else:
            memory_result["diagnostic"] = log_text
        report["external_memory_provider"] = memory_result
    save(output / "result.json", report)
    print(output / "result.json")
    if report["failed_count"] or (args.no_bootstrap_memory and
            report["external_memory_provider"]["status"] != "compiled"):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"HCU PS2 closure failed: {error}")
