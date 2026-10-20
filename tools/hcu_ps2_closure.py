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
    "fputs",
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
}
PS2_SERVICE_PREFIXES = (
    "cache_file_", "cache_files_", "texture_cache_", "sound_cache_", "_texture_cache_", "_sound_cache_",
    "physical_memory_", "XInput", "XDEVICE_", "XFind", "XCreate", "XDelete", "XGet", "XInit",
    "XCalculate", "XPhysical", "Create", "Read", "Write", "Find", "Delete", "Move", "Remove",
    "Close", "Wait", "Sleep", "Set", "Get", "Global", "Local", "Virtual", "Query", "Copy",
    "Resume", "Switch", "Output",
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
    "global_rasterizer_model_ambient_reflection_tint",
}
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
    if symbol in PS2_SERVICES or symbol.startswith(PS2_SERVICE_PREFIXES):
        return "ps2-service"
    if symbol in EXCLUDED_EXACT or symbol.startswith(EXCLUDED_PREFIXES):
        return "excluded-feature"
    if symbol in RENDER_EXACT or symbol.startswith(RENDER_PREFIXES):
        return "render"
    return "unclassified"


def undefined_symbols(nm: Path, obj: Path) -> set[str]:
    output = subprocess.check_output([str(nm), "-u", str(obj)], text=True)
    return {line.split()[-1] for line in output.splitlines() if line.strip()}


def live_external_symbols(nm: Path, objdump: Path, obj: Path) -> list[str]:
    undefined = undefined_symbols(nm, obj)
    relocations = subprocess.check_output([str(objdump), "-r", str(obj)], text=True)
    referenced = {line.split()[-1].split("+")[0] for line in relocations.splitlines() if "R_MIPS_" in line}
    return sorted(undefined & referenced)


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
    output = build / "hcu-ps2-closure" / args.layer
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
    flags = [*FLAGS, *includes, "-include", str(header), "-include", str(semantics), "-c"]
    members = selected_sources(manifest)
    report = {
        "status": "layer-measured",
        "milestone": "M0",
        "gate": "open",
        "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
        "flags": FLAGS,
        "prefix": manifest["prefix"],
        "prefix_sha256": digest(header),
        "manifest_sha256": digest(MANIFEST_PATH),
        "hcu_commit": subprocess.check_output(["git", "-C", str(HCU), "rev-parse", "HEAD"], text=True).strip(),
        "selected_source_count": len(members),
        "layer": args.layer,
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
        pending.append((relative, source, obj, extra))
    objects = []
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
            roots = ["game_initialize", "game_tick", "halo_shell_main", "actors_update", "hs_update"]
            rooted_link = subprocess.run(
                [str(linker), "-r", "--gc-sections", *[arg for name in roots for arg in ("-u", name)],
                 f"@{response}", "-o", str(rooted)],
                cwd=ROOT, env=env, text=True, capture_output=True)
            (output / "rooted-link.log").write_text(rooted_link.stdout + rooted_link.stderr)
            if rooted_link.returncode == 0:
                rooted_sections = section_bytes(size, rooted)
                rooted_code = rooted_sections[".text"] + rooted_sections[".data"] + rooted_sections[".rodata"]
                report["rooted_link"] = {
                    "roots": roots,
                    "sections": rooted_sections,
                    "code_constants_static_data": rooted_code,
                    "elf_static_bytes": 2097152,
                    "elf_static_spare": 2097152 - rooted_code,
                }
    else:
        report["status"] = "layer-failed"
    save(output / "result.json", report)
    print(output / "result.json")
    if report["failed_count"]:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"HCU PS2 closure failed: {error}")
