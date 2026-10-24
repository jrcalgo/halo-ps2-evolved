import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import hcu_ps2_external_review as review  # noqa: E402


def fixture_report(source_hash="source-a"):
    return {
        "units": {"source/example.c": {"source_sha256": source_hash}},
        "rooted_link": {"live_externals": [{
            "symbol": "example_call", "classification": "ps2-service",
            "caller_sections": [".text.example"],
            "caller_source_candidates": ["source/example.c"],
        }]},
    }


def test_review_refresh_preserves_only_identical_source_backed_dispositions(
        tmp_path, monkeypatch):
    rooted = tmp_path / "rooted.o"
    rooted.write_bytes(b"first")
    ledger = tmp_path / "review.json"
    monkeypatch.setattr(review, "ROOTED", rooted)
    monkeypatch.setattr(review, "LEDGER", ledger)
    review.initialize(fixture_report())
    data = json.loads(ledger.read_text())
    row = data["symbols"]["example_call"]
    row.update(disposition="implemented", owner="parent",
               reason="source call has a machine owner", evidence="source/example.c:1",
               test="test_machine_owner")
    ledger.write_text(json.dumps(data))
    review.check(fixture_report())

    rooted.write_bytes(b"second")
    review.refresh(fixture_report())
    assert json.loads(ledger.read_text())["symbols"]["example_call"]["owner"] == "parent"
    review.check(fixture_report())

    review.refresh(fixture_report("source-b"))
    assert json.loads(ledger.read_text())["symbols"]["example_call"]["disposition"] == "pending"
    with pytest.raises(SystemExit):
        review.check(fixture_report("source-b"))


def test_pinned_toolchain_helpers_have_source_backed_individual_owners():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    symbols = ledger["symbols"]
    helpers = {
        "__adddf3", "__divdf3", "__divdi3", "__extendsfdf2", "__fixdfsi",
        "__floatdidf", "__floatdisf", "__floatsidf", "__gtdf2", "__ltdf2",
        "__moddi3", "__muldf3", "__muldi3", "__subdf3", "__truncdfsf2",
        "__udivdi3",
    }
    assert len(helpers) == 16
    for name in helpers:
        row = symbols[name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "Pinned PS2 EE GCC 15.2.0 libgcc"
        assert ("hcu-ps2-toolchain-runtime-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert "M6" in row["reason"] and "M6" in row["test"]


def test_pinned_newlib_memory_helpers_have_source_backed_individual_owners():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    symbols = ledger["symbols"]
    helpers = {"memchr", "memcmp", "memmove", "memset"}
    for name in helpers:
        row = symbols[name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "Pinned PS2 EE Newlib 4.6.0 libc"
        assert ("hcu-ps2-libc-memory-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert symbols["memcpy"]["disposition"] in {"pending", "implemented"}
    if symbols["memcpy"]["disposition"] != "pending":
        assert "hcu-ps2-batch-" in symbols["memcpy"]["evidence"]
    assert "memcpy" in (ROOT / "docs/hcu-ps2-libc-memory-review.md").read_text()


def test_xbdm_shell_walk_terminates_on_empty_ps2_module_set():
    shell = (ROOT / "submodules/halo-ce-universal/source/shell/shell_xbox.c").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    assert "fuck_code_in_the_eye();" in shell
    assert "while (DmWalkLoadedModules(&walk_modules, &module_load) != XBDM_ENDOFLIST)" in shell
    assert "while (DmWalkModuleSections(&walk_modsect, module_load.Name, &section_load) != XBDM_ENDOFLIST)" in shell
    expected = {
        "DmWalkLoadedModules": "XBDM_ENDOFLIST",
        "DmWalkModuleSections": "XBDM_ENDOFLIST",
        "DmCloseModuleSections": "XBDM_NOERR",
    }
    for name, result in expected.items():
        match = re.search(
            rf"HRESULT __stdcall {name}\([^{{]+\)\s*\{{(.*?)\n\}}", edge, re.S)
        assert match, f"PS2 edge must own {name}"
        assert f"return {result};" in match.group(1)

    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    for name in expected:
        row = ledger["symbols"][name]
        assert row["disposition"] == "state-adapter"
        assert row["owner"] == "HCU PS2 edge: empty Xbox debug-monitor module set"
        assert ("hcu-ps2-shell-xbdm-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    protect = ledger["symbols"]["VirtualProtect"]
    assert protect["disposition"] == "excluded-proven"
    assert protect["owner"] == "HCU PS2 edge: empty Xbox debug-monitor module set"
    assert "VirtualProtect" in shell and "hcu-ps2-shell-xbdm-review.md" in protect["evidence"]


def test_ctf_debug_string_is_diagnostic_only():
    ctf = (ROOT / "submodules/halo-ce-universal/source/game/game_engine_ctf.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    assert 'object_set_automatic_deactivation(weapon_index, FALSE);\n\tOutputDebugString("created a flag");' in ctf
    assert "void OutputDebugStringA(const char * p0) {  }" in generated

    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    row = ledger["symbols"]["OutputDebugStringA"]
    assert row["caller_sources"] == {
        "source/game/game_engine_ctf.c":
            "f3b95cc41873a7adf16ae8c367ce0e1f1c585b825e28fb601975c8a12b69042f"
    }
    assert row["disposition"] == "excluded-proven"
    assert ("hcu-ps2-ctf-debug-string-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])


def test_xinput_debug_keyboard_queue_terminates_without_affecting_pad_path():
    input_xbox = (ROOT / "submodules/halo-ce-universal/source/input/input_xbox.c").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    bridge = (ROOT / "src/stream/hcu_input_bridge.c").read_text()
    assert "while (XInputDebugGetKeystroke(&keystroke) == ERROR_SUCCESS)" in input_xbox
    match = re.search(
        r"unsigned long __stdcall XInputDebugGetKeystroke\([^)]*\)\s*\{(.*?)\n\}",
        edge, re.S)
    assert match and "return 38;" in match.group(1)
    assert "ps2_input_publish_dualshock" in bridge

    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    row = ledger["symbols"]["XInputDebugGetKeystroke"]
    assert row["disposition"] == "state-adapter"
    assert row["owner"] == "HCU PS2 edge: unsupported XDK debug-keyboard queue"
    assert ("hcu-ps2-debug-keyboard-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])


def test_physical_memory_accessors_are_backed_by_the_ps2_provider_contract():
    provider = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_memory.c").read_text()
    report = (ROOT / "docs/hcu-ps2-physical-memory-api-review.md").read_text()
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    approved = {
        "physical_memory_allocate",
        "physical_memory_get_game_state_base_address",
        "physical_memory_get_sound_cache_base_address",
        "physical_memory_get_structure_bsp_cache_base_address",
        "physical_memory_get_structure_bsp_cache_size",
        "physical_memory_get_tag_cache_base_address",
        "physical_memory_get_tag_cache_size",
    }
    for name in approved:
        match = re.search(rf"\b{name}\s*\([^)]*\)\s*\{{(.*?)\n\}}", provider, re.S)
        assert match, f"PS2 provider must implement {name}"
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "HCU PS2 fixed-memory provider"
        assert ("hcu-ps2-physical-memory-api-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert "test_ps2_memory_binder_tracks_caller_owned_capacity" in row["test"]
    assert len(approved) == 7
    assert "physical_memory_verify" in report
    row = ledger["symbols"]["physical_memory_verify"]
    assert row["disposition"] == "state-adapter"
    assert row["owner"] == "HCU PS2 startup readiness gate"
    shell = (ROOT / "submodules/halo-ce-universal/source/shell/shell.c").read_text()
    main = (ROOT / "src/stream/hcu_main.c").read_text()
    assert "shell_platform_verify();" in shell
    assert main.index("if (!physical_memory_ready())") < main.index("result = halo_shell_main();")
    verify = re.search(r"void physical_memory_verify\s*\([^)]*\)\s*\{(.*?)\n\}", provider, re.S)
    assert verify and not verify.group(1).strip()
    for name in ("GlobalAlloc", "LocalFree"):
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "HCU PS2 fixed-memory provider"
        assert ("hcu-ps2-physical-memory-api-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert ledger["symbols"]["GlobalReAlloc"]["disposition"] in {"pending", "implemented"}


def test_xinput_device_type_tokens_match_the_ps2_provider_contract():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    symbols = ledger["symbols"]
    names = {
        "XDEVICE_TYPE_DEBUG_KEYBOARD_TABLE",
        "XDEVICE_TYPE_GAMEPAD_TABLE",
        "XDEVICE_TYPE_MEMORY_UNIT_TABLE",
    }
    for name in names:
        row = symbols[name]
        assert row["disposition"] == "state-adapter"
        assert row["owner"] == "HCU PS2 input device-type tokens"
        assert ("hcu-ps2-input-device-type-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])


def test_ps2_timer_external_resolves_to_the_pinned_kernel_service():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    row = ledger["symbols"]["GetTimerSystemTime"]
    assert row["disposition"] == "implemented"
    assert row["owner"] == "Pinned PS2SDK EE libkernel timer service"
    assert ("hcu-ps2-timer-api-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    sdk_source = (ROOT / "submodules/ps2sdk/ee/kernel/src/timer.c").read_text()
    assert "u64 GetTimerSystemTime(void)" in sdk_source
    assert "oldintr = DIntr();" in sdk_source
    assert "ret = iGetTimerSystemTime();" in sdk_source
    assert "submodules/ps2sdk" in (ROOT / "config/dependencies.json").read_text()
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    assert "libkernel.a(GetTimerSystemTime.o)" in link_map


def test_pinned_newlib_string_helpers_resolve_to_exact_archive_members():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    report = (ROOT / "docs/hcu-ps2-libc-string-review.md").read_text()
    helpers = {
        "strchr", "strcmp", "strcpy", "strlen", "strncat", "strncmp",
        "strncpy", "strrchr", "strstr", "wcscmp", "wcslen", "wcsncpy",
    }
    for name in helpers:
        assert f"libc.a(libc_a-{name}.o)" in link_map
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "Pinned PS2 EE Newlib 4.6.0 libc"
        assert ("hcu-ps2-libc-string-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert len(helpers) == 12
    assert "strtok` remains pending" in report
    assert ledger["symbols"]["strtok"]["disposition"] in {"pending", "implemented"}


def test_pinned_newlib_ascii_ctype_resolves_to_exact_archive_members():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    report = (ROOT / "docs/hcu-ps2-libc-ascii-ctype-review.md").read_text()
    for name in ("_ctype_", "isalpha", "isspace"):
        member = "ctype_" if name == "_ctype_" else name
        assert f"libc.a(libc_a-{member}.o)" in link_map
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert ("hcu-ps2-libc-ascii-ctype-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "`tolower` call" in report and "ASCII-only" in report
    assert ledger["symbols"]["tolower"]["disposition"] == "implemented"
    assert ledger["symbols"]["towlower"]["disposition"] in {"pending", "implemented"}


def test_pinned_newlib_tolower_has_only_ascii_hs_completion_callers():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    console = (ROOT / "submodules/halo-ce-universal/source/main/console.c").read_text()
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    report = (ROOT / "docs/hcu-ps2-ascii-tolower-review.md").read_text()
    row = ledger["symbols"]["tolower"]
    assert set(row["caller_sources"]) == {"source/main/console.c"}
    assert "hs_tokens_enumerate" in console and "tolower(matching_items[token_num][0])" in console
    assert "libc.a(libc_a-tolower.o)" in link_map
    assert row["disposition"] == "implemented"
    assert row["owner"] == "Pinned PS2 EE Newlib 4.6.0 ctype"
    assert ("hcu-ps2-ascii-tolower-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "towlower`" in report and "remains pending" in report


def test_xphysicalfree_does_not_release_parent_owned_game_state_arena():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    game_state = (ROOT / "submodules/halo-ce-universal/source/saved games/game_state_xbox.c").read_text()
    parent_bind = (ROOT / "src/stream/hcu_memory_bind.c").read_text()
    provider = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_memory.c").read_text()
    report = (ROOT / "docs/hcu-ps2-xphysicalfree-review.md").read_text()
    row = ledger["symbols"]["XPhysicalFree"]
    assert set(row["caller_sources"]) == {"source/saved games/game_state_xbox.c"}
    assert "physical_memory_get_game_state_base_address()" in game_state
    assert "XPhysicalFree(xbox_game_state_globals.buffer)" in game_state
    assert "#ifdef HALO_PS2" in game_state
    assert "physical_memory_bind_game_state" in parent_bind
    assert "physical_memory_free(void)" in provider
    assert row["disposition"] == "state-adapter"
    assert row["owner"] == "HCU PS2 physical-memory span owner"
    assert "not call the C heap or unbind the shared memory\nspan" in report


def test_xgetlaunchinfo_failure_selects_normal_local_shell_boot():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    shell = (ROOT / "submodules/halo-ce-universal/source/shell/shell_xbox.c").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    report = (ROOT / "docs/hcu-ps2-xgetlaunchinfo-review.md").read_text()
    row = ledger["symbols"]["XGetLaunchInfo"]
    assert set(row["caller_sources"]) == {"source/shell/shell_xbox.c"}
    assert "if (!XGetLaunchInfo(&launch_data_type, &launch_data)" in shell
    assert "return 1;" in edge[edge.index("unsigned long __stdcall XGetLaunchInfo"):]
    assert "return TRUE;" in shell[shell.index("boolean shell_platform_initialize"):]
    assert row["disposition"] == "state-adapter"
    assert row["owner"] == "HALO_PS2 local shell startup adapter"
    assert "Short-circuit" in report


def test_ps2_last_error_is_global_across_file_and_input_domains_and_remains_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    input_port = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_input.c").read_text()
    files = (ROOT / "submodules/halo-ce-universal/source/tag_files/files_windows.c").read_text()
    report = (ROOT / "docs/hcu-ps2-last-error-threading-review.md").read_text()
    for symbol in ("GetLastError", "SetLastError"):
        assert ledger["symbols"][symbol]["disposition"] in {"pending", "implemented", "state-adapter"}
        assert ledger["symbols"][symbol]["reason"]
        assert "source/tag_files/files_windows.c" in ledger["symbols"][symbol]["caller_sources"]
    assert "source/input/input_xbox.c" in ledger["symbols"]["GetLastError"]["caller_sources"]
    assert "port/ps2/src/ps2_input.c" in ledger["symbols"]["SetLastError"]["caller_sources"]
    assert "static unsigned long ps2_last_error" in edge
    assert "return ps2_last_error;" in edge
    assert "ps2_last_error = code;" in edge
    assert "SetLastError(ERROR_DEVICE_NOT_CONNECTED)" in input_port
    assert "GetLastError()" in files
    assert "process-global" in report and "belongs to the calling thread" in report


def test_ps2_binary_semaphore_is_not_approved_as_win32_mutex():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    ce = (ROOT / "submodules/halo-ce-universal/source/bungie_net/common/thread_win32.c").read_text()
    ps2 = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    report = (ROOT / "docs/hcu-ps2-mutex-semaphore-review.md").read_text()
    assert "WAIT_ABANDONED" in ce and "CreateMutexA(NULL, FALSE" in ce
    assert "int __stdcall ReleaseMutex" in ps2 and "SignalSema(handle->semaphore_id)" in ps2
    assert "WaitSemaEx(handle->semaphore_id" in ps2
    for symbol in ("CreateMutexA", "WaitForSingleObject", "ReleaseMutex"):
        row = ledger["symbols"][symbol]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert "source/bungie_net/common/thread_win32.c" in row["caller_sources"]
        assert row["reason"] and row["evidence"] and row["test"]
    assert "no owning-thread" in report


def test_attract_mode_noop_loses_ce_countdown_state_and_remains_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    attract = (ROOT / "submodules/halo-ce-universal/source/interface/attract_mode.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-attract-mode-review.md").read_text()
    row = ledger["symbols"]["attract_mode_start"]
    assert set(row["caller_sources"]) == {"source/hs/hs.c"}
    start = attract[attract.index("void attract_mode_start("):attract.index("void game_end_credits_start(")]
    assert "ui_stop_main_menu_music()" in start
    assert "bink_playback_start(" in start
    assert "attract_mode_countdown_timer = system_milliseconds()" in start
    assert "void attract_mode_start(void) {  }" in generated
    assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
    assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "") and row["reason"] and row["evidence"]
    assert "loses that transition" in report


def test_xbox_save_apis_remain_pending_without_ps2_storage_contract():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    saved_games = (ROOT / "submodules/halo-ce-universal/source/saved games/saved_game_files.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-xbox-save-api-review.md").read_text()
    names = (
        "XCalculateSignatureBegin", "XCalculateSignatureUpdate", "XCalculateSignatureEnd",
        "XCreateSaveGame", "XDeleteSaveGame", "XFindFirstSaveGame",
        "XFindNextSaveGame", "XFindClose",
    )
    for symbol in names:
        row = ledger["symbols"][symbol]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert "source/saved games/saved_game_files.c" in row["caller_sources"]
    assert "saved_game_file_generate_checksum" in saved_games
    assert "saved_game_files_delete_all_custom_profiles" in saved_games
    assert "saved_game_file_name_unique" in saved_games
    assert "XCalculateSignatureUpdate" in generated and "memset(&result, 0, sizeof(result)); return result;" in generated
    assert "success-shaped" in report


def test_stack_walk_is_diagnostic_only_and_does_not_replace_error_control_flow():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    cseries = (ROOT / "submodules/halo-ce-universal/source/cseries/cseries.c").read_text()
    errors = (ROOT / "submodules/halo-ce-universal/source/cseries/errors.c").read_text()
    stack = (ROOT / "submodules/halo-ce-universal/source/cseries/stack_walk_windows.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-stack-walk-review.md").read_text()
    for symbol in ("stack_walk", "stack_walk_initialize", "stack_walk_dispose"):
        assert ledger["symbols"][symbol]["disposition"] == "excluded-proven"
        assert ledger["symbols"][symbol]["evidence"]
    assert "stack_walk(0); error(_error_silent" in cseries
    assert "system_exit(-1);" in cseries
    assert "stack_walk_initialize();" in errors and "stack_walk_dispose();" in errors
    assert "load_symbol_table(" in stack and "free_symbol_table(&stack_walk_globals.symbol_table)" in stack
    for signature in (
        "void stack_walk(short levels_to_ignore) {  }",
        "void stack_walk_dispose(void) {  }",
        "void stack_walk_initialize(void) {  }",
    ):
        assert signature in generated
    assert "does not suppress the error" in report


def test_zero_keyboard_actions_preserve_gamepad_state_in_pad_only_profile():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    abstraction = (ROOT / "submodules/halo-ce-universal/source/input/input_abstraction.c").read_text()
    ps2_input = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_input.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-keyboard-actions-review.md").read_text()
    row = ledger["symbols"]["halo_keyboard_actions"]
    assert set(row["caller_sources"]) == {"source/input/input_abstraction.c"}
    update = abstraction[abstraction.index("void input_abstraction_update("):abstraction.index("/* ---------- private code */")]
    assert update.index("state->buttons[control_index] =") < update.index("keyboard_controls_update(controller_index, state)")
    assert "MAX(state->buttons[control_index]," in abstraction
    assert "if (x || y)" in abstraction
    assert "ps2_input_publish_state" in ps2_input
    assert "unsigned long halo_keyboard_actions(short controller_index) { unsigned long result; memset(&result, 0, sizeof(result)); return result; }" in generated
    assert row["disposition"] == "state-adapter"
    assert "zero keyboard-action mask" in report


def test_ui_error_entry_points_are_stateful_and_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    widget = (ROOT / "submodules/halo-ce-universal/source/interface/ui_widget.c").read_text()
    input_abstraction = (ROOT / "submodules/halo-ce-universal/source/input/input_abstraction.c").read_text()
    cache_files = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    game = (ROOT / "submodules/halo-ce-universal/source/game/game.c").read_text()
    hs = (ROOT / "submodules/halo-ce-universal/source/hs/hs.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-ui-error-state-review.md").read_text()
    names = (
        "display_error_deferred", "display_error_when_main_menu_loaded",
        "display_errors_deferred_until_cinematic_stop", "display_error_damaged_media",
        "display_scenario_help",
    )
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert "void " + name in generated
    assert "pause_game_time = pause_game_time" in widget
    assert "display_error_deferred(error_code, error_controller, pause_game, pause_game)" in input_abstraction
    assert "main_menu_deferred_error_code = error_code" in widget
    assert "deferred_error->error_code = NONE" in widget
    assert "main_loop_of_death()" in widget
    assert "display_error_damaged_media()" in cache_files and "display_error_damaged_media()" in game
    assert "widget_name = \"ui\\\\shell\\\\solo_game\\\\player_help" in widget
    assert '"display_scenario_help"' in hs
    assert "not approved as harmless" in report


def test_ce_texture_cache_roots_are_stateful_and_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    cache_files = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    texture_cache = (ROOT / "submodules/halo-ce-universal/source/cache/xbox_texture_cache.c").read_text()
    hs_globals = (ROOT / "submodules/halo-ce-universal/source/hs/hs_globals_external.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-texture-cache-review.md").read_text()
    names = (
        "texture_cache_open", "texture_cache_close", "texture_cache_flush",
        "texture_cache_debug_options", "_texture_cache_bitmap_get_hardware_format",
    )
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
    assert "texture_cache_open();" in cache_files and "texture_cache_close();" in cache_files
    assert "data_make_valid(xbox_texture_cache_globals.textures)" in texture_cache
    assert "texture_cache_flush();" in texture_cache and "data_make_invalid(xbox_texture_cache_globals.textures)" in texture_cache
    assert "IDirect3DDevice8_KickPushBuffer" in texture_cache and "lruv_flush" in texture_cache
    assert '"texture_cache_graph"' in hs_globals and '"texture_cache_list"' in hs_globals
    assert "struct texture_cache_debug_options" in texture_cache
    assert "void * _texture_cache_bitmap_get_hardware_format" in generated
    assert "void texture_cache_open(void) {  }" in generated
    assert "void texture_cache_close(void) {  }" in generated
    assert "parent GS cache\nflush" in report


def test_ce_sound_cache_roots_carry_runtime_state_and_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    sound_cache = (ROOT / "submodules/halo-ce-universal/source/cache/xbox_sound_cache.c").read_text()
    manager = (ROOT / "submodules/halo-ce-universal/source/sound/sound_manager.c").read_text()
    cache_files = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-sound-cache-review.md").read_text()
    names = (
        "_sound_cache_sound_request", "sound_cache_close", "sound_cache_delete",
        "sound_cache_flush", "sound_cache_idle", "sound_cache_new",
        "sound_cache_open", "sound_cache_sound_finished",
    )
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
    assert "sound_cache_close();" in cache_files and "sound_cache_open();" in cache_files
    assert "data_dispose(xbox_sound_cache_globals.cache_sounds)" in sound_cache
    assert "physical_memory_get_sound_cache_base_address()" in sound_cache
    assert "sound->cache_block_index == NONE && load" in sound_cache
    assert "cache_sound->software_reference_count++" in sound_cache
    assert "cache_sound->software_reference_count--" in sound_cache
    assert "if (!_sound_cache_sound_request(" in manager
    for name in names:
        assert name in generated
    assert "boolean _sound_cache_sound_request" in generated and "memset(&result, 0" in generated
    assert "SPU2 playback does not itself prove" in report


def test_platform_log_only_emits_diagnostics_after_caller_state_decisions():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    data = (ROOT / "submodules/halo-ce-universal/source/memory/data.c").read_text()
    game_state = (ROOT / "submodules/halo-ce-universal/source/saved games/game_state.c").read_text()
    lights = (ROOT / "submodules/halo-ce-universal/source/objects/object_lights.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-platform-log-review.md").read_text()
    row = ledger["symbols"]["platform_log"]
    assert set(row["caller_sources"]) == {
        "source/memory/data.c", "source/saved games/game_state.c", "source/objects/object_lights.c"
    }
    usable = data[data.rindex("static boolean data_usable("):data.rindex("static void datum_initialize(")]
    assert usable.index("platform_log(") < usable.rindex("return FALSE;")
    checked = game_state[game_state.rindex("void game_state_check_data_arrays("):game_state.rindex("struct memory_pool *game_state_memory_pool_new(")]
    assert checked.index("platform_log(") < checked.index("error(_error_silent")
    recover = lights[lights.rindex("boolean lights_port_recover("):lights.rindex("boolean lights_enable(")]
    assert recover.index("platform_log(") > recover.index("object->object.attachment_indices[attachment_index] = NONE")
    assert "return TRUE;" in recover
    assert "void platform_log(const char *format, ...) {}" in generated
    assert row["disposition"] == "excluded-proven" and "log text omitted" in row["owner"]
    assert "return behavior" in report


def test_control87_rounding_requirement_is_not_proven_by_zero_stub():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    real_math = (ROOT / "submodules/halo-ce-universal/source/math/real_math.c").read_text()
    game = (ROOT / "submodules/halo-ce-universal/source/game/game.c").read_text()
    ps2_float = (ROOT / "submodules/halo-ce-universal/port/ps2/include/float.h").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-control87-review.md").read_text()
    row = ledger["symbols"]["_control87"]
    assert "_control87(CW_DEFAULT, 0xFFFFF)" in real_math
    assert game.count("real_math_reset_precision();") >= 3
    assert "_RC_NEAR 0x00000000" in ps2_float and "_PC_53" in ps2_float
    assert "unsigned int _control87(" in (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_crt.c").read_text()
    assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
    assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "") and row["reason"] and row["evidence"] and row["test"]
    assert "FCR rounding control" in report and "Keep `_control87` pending" in report


def test_globalrealloc_copy_extent_and_bump_arena_retention_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    windows = (ROOT / "submodules/halo-ce-universal/source/cseries/cseries_windows.c").read_text()
    debug = (ROOT / "submodules/halo-ce-universal/source/cseries/debug_memory.c").read_text()
    memory = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_memory.c").read_text()
    report = (ROOT / "docs/hcu-ps2-globalrealloc-review.md").read_text()
    row = ledger["symbols"]["GlobalReAlloc"]
    assert set(row["caller_sources"]) == {"source/cseries/cseries_windows.c"}
    assert "return GlobalReAlloc(pointer, size, GMEM_MOVEABLE)" in windows
    assert "header = system_realloc(" in debug and "old_size = header->size" in debug
    realloc = memory[memory.index("void *__stdcall GlobalReAlloc("):]
    assert "copy = old_bytes < size ? old_bytes : size;" in realloc
    assert "copy = old_bytes < size ? old_bytes : size;" in memory
    assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
    assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "") and row["reason"] and row["evidence"] and row["test"]
    assert "past the old block" in report and "bump allocator" in report


def test_ps2_thread_api_stubs_force_fallback_but_do_not_implement_thread_contract():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    threads = (ROOT / "submodules/halo-ce-universal/source/bungie_net/common/thread_win32.c").read_text()
    widget = (ROOT / "submodules/halo-ce-universal/source/interface/ui_widget.c").read_text()
    player = (ROOT / "submodules/halo-ce-universal/source/saved games/player_profile.c").read_text()
    playlist = (ROOT / "submodules/halo-ce-universal/source/saved games/playlist_profile.c").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-thread-api-review.md").read_text()
    names = ("CreateThread", "GetExitCodeThread", "ResumeThread", "SetThreadPriority", "CloseHandle")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
    creator = threads[threads.index("boolean create_thread("):threads.index("boolean thread_has_exited(")]
    assert "CREATE_SUSPENDED" in creator and "SetThreadPriority(" in creator and "ResumeThread(" in creator
    assert "GetExitCodeThread(thread_reference->handle, &exit_code)" in threads
    assert "failed to spawn thread for filesystem checks - running synchronously" in widget
    assert "create_thread(" in player and "create_thread(" in playlist
    assert "CreateThread(void * p0" in generated and "return result; }" in generated
    assert "GetExitCodeThread(void * p0" in generated
    assert "ResumeThread(void * p0" in generated and "SetThreadPriority(void * p0" in generated
    assert "struct ps2_thread_handle" not in edge
    assert "thread-handle" in report and "`CloseHandle`" in report


def test_rooted_file_mutations_remain_pending_without_writable_storage_contract():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    bridge = (ROOT / "src/stream/hcu_file_bridge.c").read_text()
    files = (ROOT / "submodules/halo-ce-universal/source/tag_files/files_windows.c").read_text()
    saves = (ROOT / "submodules/halo-ce-universal/source/saved games/game_state_xbox.c").read_text()
    metadata = (ROOT / "submodules/halo-ce-universal/source/saved games/saved_game_files.c").read_text()
    report = (ROOT / "docs/hcu-ps2-file-mutation-review.md").read_text()
    pending = ("CopyFileA", "CreateDirectoryA", "CreateFileA", "DeleteFileA",
               "FindFirstFileA", "FindNextFileA", "GetFileAttributesA",
               "GetFileAttributesExA", "GetFileSize", "ReadFile",
               "SetEndOfFile", "SetFilePointer", "WriteFile")
    for name in pending:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-file-mutation-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "enum { HCU_FILE_SLOT_COUNT = 16 }" in bridge
    assert "file_reader_read_at(&slot->reader, slot->position, buffer, amount)" in bridge
    assert "desired_access != GENERIC_READ || creation_disposition != OPEN_EXISTING" in edge
    assert "hcu_file_bridge_stat(path, &size, &is_directory)" in edge
    attrs = edge[edge.index("int __stdcall GetFileAttributesExA("):edge.index("/* The PS2 file facade")]
    assert "data->dwFileAttributes" in attrs and "data->nFileSizeLow" in attrs
    assert "ftLastWriteTime" not in attrs
    assert "FindFirstFileA(full_path" in files and "FindNextFileA(handle" in files
    assert "if (bytes_read == count)" in files and "bytes_written == count" in files
    assert "CreateFileA(\"z:\\\\savegame.bin\"" in saves
    assert "DeleteFileA(path)" in saves and "CopyFileA(" in metadata
    assert "uninitialized timestamp" in report and "Keep all reviewed symbols pending" in report


def test_wall_clock_apis_are_separate_from_monotonic_timer_and_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    time_port = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_time.c").read_text()
    windows = (ROOT / "submodules/halo-ce-universal/source/cseries/cseries_windows.c").read_text()
    errors = (ROOT / "submodules/halo-ce-universal/source/cseries/errors.c").read_text()
    rtc = (ROOT / "submodules/ps2sdk/ee/libcglue/src/rtc.c").read_text()
    timer = (ROOT / "docs/hcu-ps2-timer-api-review.md").read_text()
    report = (ROOT / "docs/hcu-ps2-wall-clock-review.md").read_text()
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    for name in ("time", "gmtime_r", "localtime"):
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-wall-clock-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "return time(NULL);" in windows
    assert "time(&timeptr);" in errors and "localtime(&timeptr)" in errors
    assert "now = time(NULL);" in time_port and "gmtime_r(&now, &utc)" in time_port
    assert "system_time->wYear" in time_port and "system_time->wMilliseconds = 0" in time_port
    assert "ps2time(NULL)" in rtc and "_ps2sdk_rtc_offset_from_busclk" in rtc
    assert "GetTimerSystemTime" in timer
    assert "libc_a-gmtime_r.o" in link_map and "localtime_r" in link_map
    assert "not frame timing" in report and "Keep `time`, `gmtime_r`, and `localtime` pending" in report


def test_render_interpolation_placeholders_are_not_camera_or_state_safe():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    game = (ROOT / "submodules/halo-ce-universal/source/game/game.c").read_text()
    game_time = (ROOT / "submodules/halo-ce-universal/source/game/game_time.c").read_text()
    objects = (ROOT / "submodules/halo-ce-universal/source/objects/objects.c").read_text()
    antenna = (ROOT / "submodules/halo-ce-universal/source/objects/widgets/antenna.c").read_text()
    interpolation = (ROOT / "submodules/halo-ce-universal/port/linux/game/render_interpolation.c").read_text()
    fov = (ROOT / "submodules/halo-ce-universal/port/linux/game/view_fov.c").read_text()
    batch = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c").read_text()
    report = (ROOT / "docs/hcu-ps2-render-interpolation-review.md").read_text()
    names = ("halo_interpolation_enabled",)
    closed = ("render_fov_vertical",
              "render_interpolation_camera", "render_interpolation_fraction",
              "render_interpolation_frame_begin", "render_interpolation_frame_end",
              "render_interpolation_object_node_matrices", "render_interpolation_reset",
              "render_interpolation_tick")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-render-interpolation-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    for name in closed:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"implemented", "state-adapter", "excluded-proven"}
        assert ("hcu-ps2-batch-6-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    body = main[main.index("static void main_game_render("):main.index("static boolean main_loop_iteration(void);")]
    assert "observer = observer_get_camera" in body
    assert "observer = render_interpolation_camera" in body
    assert "set_window_camera_values(window, observer)" in body
    blended = interpolation[interpolation.index("static struct observer_result const *render_interpolation_blended_camera(", interpolation.index("static struct observer_result const *render_interpolation_blended_camera(") + 1):]
    assert "if (!interpolation_rendering || !observer)" in blended and "return observer;" in blended
    assert "return interpolation_rendering ? interpolation_fraction : 1.0f" in interpolation
    assert "render_interpolation_reset();" in game and "render_interpolation_tick();" in game_time
    assert "render_interpolation_frame_begin();" in game_time and "render_interpolation_frame_end();" in game_time
    assert "if (interpolated)" in objects and "object_header_block_get(object_index" in objects
    assert "render_interpolation_fraction()" in antenna
    assert "return adjusted;" in fov
    assert "return observer;" in batch[batch.index("struct observer_result const *render_interpolation_camera("):]
    assert "return 1.0f;" in batch[batch.index("float render_interpolation_fraction("):]
    assert "identity observer/FOV" in report and "no-post-map-malloc" in report


def test_render_lifecycle_stubs_have_game_state_ownership_and_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    game = (ROOT / "submodules/halo-ce-universal/source/game/game.c").read_text()
    render = (ROOT / "submodules/halo-ce-universal/source/render/render.c").read_text()
    objects = (ROOT / "submodules/halo-ce-universal/source/render/render_objects.c").read_text()
    hs = (ROOT / "submodules/halo-ce-universal/source/hs/hs.c").read_text()
    particles = (ROOT / "submodules/halo-ce-universal/source/effects/particle_systems.c").read_text()
    weather = (ROOT / "submodules/halo-ce-universal/source/effects/weather_particle_systems.c").read_text()
    report = (ROOT / "docs/hcu-ps2-render-lifecycle-review.md").read_text()
    names = ("render_dispose", "render_dispose_from_old_map", "render_effects",
             "render_initialize", "render_initialize_for_new_map")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-batch-6-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "render_initialize();" in game and "render_initialize_for_new_map();" in game
    assert "render_dispose_from_old_map();" in game and "render_dispose();" in game
    assert "render_objects_initialize();" in render
    assert "render_objects_initialize_for_new_map();" in render
    assert "game_state_data_new(" in objects
    assert "data_make_valid(cached_object_render_states)" in objects
    assert "data_make_invalid(cached_object_render_states)" in objects
    assert "cached_object_render_states = NULL;" in objects
    assert "HS_EVALUATE_VOID_BOOLEAN(render_effects_evaluate, render_effects)" in hs
    for flag in ("render_weather_particle_systems_enabled", "render_particle_systems_enabled",
                 "render_particles_enabled", "render_contrails_enabled"):
        assert f"{flag} = enable" in render
    assert "if (render_particle_systems_enabled)" in particles
    assert "if (render_particle_systems_enabled && weather)" in weather
    assert "not interchangeable with `render_frame`" in report


def test_rasterizer_frame_and_map_boundary_remains_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    game = (ROOT / "submodules/halo-ce-universal/source/game/game.c").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    common = (ROOT / "submodules/halo-ce-universal/source/rasterizer/common/rasterizer_common.c").read_text()
    retail = (ROOT / "submodules/halo-ce-universal/source/rasterizer/rasterizer.c").read_text()
    shell = (ROOT / "submodules/halo-ce-universal/source/shell/shell.c").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    report = (ROOT / "docs/hcu-ps2-rasterizer-boundary-review.md").read_text()
    names = ("rasterizer_dispose", "rasterizer_dispose_from_old_map",
             "rasterizer_frame_begin", "rasterizer_frame_end", "rasterizer_frame_update",
             "rasterizer_initialize", "rasterizer_initialize_for_new_map", "rasterizer_present",
             "rasterizer_window_begin", "rasterizer_window_end", "rasterizer_windows_begin",
             "rasterizer_windows_end")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-rasterizer-boundary-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "rasterizer_initialize_for_new_map();" in game
    assert "rasterizer_dispose_from_old_map();" in game
    assert "rasterizer_frame_update(frame_dt);" in game
    common_body = common[common.index("void rasterizer_initialize_for_new_map("):common.index("void rasterizer_dispose_from_old_map(")]
    assert "scenario_get_game_globals()" in common_body
    assert "rasterizer_lights_reset_for_new_map()" in common_body
    assert "rasterizer_screen_effects_initialize_for_new_map()" in common_body
    assert "global_frame_parameters.dt = dt;" in common
    assert "game_state_malloc(" in retail and "global_rasterizer_model_ambient_reflection_tint" in retail
    assert "rasterizer_initialized = rasterizer_initialize();" in shell
    assert "ps2_rasterizer_calculate_bounds" in edge
    order = ("rasterizer_frame_begin(&frame_parameters);", "rasterizer_windows_begin();",
             "rasterizer_window_begin(&window_parameters);", "rasterizer_window_end();",
             "rasterizer_windows_end();", "rasterizer_frame_end();", "rasterizer_present(NULL, NULL);")
    start = main.index(order[0])
    offsets = [main.index(item, start) for item in order]
    assert offsets == sorted(offsets)
    assert "camera, frustum, viewport, fog" in report and "pending" in report


def test_rasterizer_state_globals_and_script_controls_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    rasterizer = (ROOT / "submodules/halo-ce-universal/source/rasterizer/rasterizer.c").read_text()
    common = (ROOT / "submodules/halo-ce-universal/source/rasterizer/common/rasterizer_common.c").read_text()
    lights = (ROOT / "submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c").read_text()
    cinematics = (ROOT / "submodules/halo-ce-universal/source/rasterizer/rasterizer_cinematics.c").read_text()
    cinematic_game = (ROOT / "submodules/halo-ce-universal/source/cutscene/cinematics.c").read_text()
    model = (ROOT / "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_models.c").read_text()
    hs = (ROOT / "submodules/halo-ce-universal/source/hs/hs.c").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    report = (ROOT / "docs/hcu-ps2-rasterizer-state-review.md").read_text()
    names = ("global_rasterizer_model_ambient_reflection_tint", "rasterizer_globals",
             "rasterizer_lights_reset_for_new_map", "rasterizer_model_ambient_reflection_tint",
             "rasterizer_set_near_clip_distance")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-rasterizer-state-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "struct rasterizer_globals_definition rasterizer_globals =" in rasterizer
    assert "0.0625f" in rasterizer and "1024.f" in rasterizer
    initializer = edge[edge.index("boolean rasterizer_initialize(void)"):edge.index("/* No DirectSound device exists")]
    assert "ps2_rasterizer_calculate_bounds" in initializer
    assert "global_rasterizer_model_ambient_reflection_tint = game_state_malloc" in rasterizer
    assert "global_rasterizer_model_ambient_reflection_tint->alpha = alpha" in model
    assert "rasterizer_set_near_clip_distance(arguments->value)" in hs
    assert "cinematic_screen_effect_globals->near_clip_distance = near_clip_distance" in cinematics
    assert "memset(local_lens_flare_occlusion_test_results2" in lights
    assert "memset(global_rasterizer_model_ambient_reflection_tint" in common
    assert "Keep all five pending" in report


def test_collision_debug_symbols_are_diagnostic_only_and_unlinked():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    debug = (ROOT / "submodules/halo-ce-universal/source/physics/collision_debug.c").read_text()
    header = (ROOT / "submodules/halo-ce-universal/source/physics/collision_debug.h").read_text()
    biped = (ROOT / "submodules/halo-ce-universal/source/units/bipeds.c").read_text()
    hs = (ROOT / "submodules/halo-ce-universal/source/hs/hs_globals_external.c").read_text()
    collision = (ROOT / "submodules/halo-ce-universal/source/physics/collisions.c").read_text()
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    report = (ROOT / "docs/hcu-ps2-collision-debug-review.md").read_text()
    names = tuple(name for name in ledger["symbols"]
                  if name.startswith("collision_debug") and ledger["symbols"][name]["disposition"] == "excluded-proven")
    assert len(names) == 22
    for name in names:
        row = ledger["symbols"][name]
        assert row["owner"] and row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-collision-debug-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "void collision_debug_render(" in debug and "collision_debug_spray" in debug
    assert "collision_debug_point" in header and "collision_debug_vector" in header
    branch_start = biped.index("if (debug_biped_physics &&")
    branch_end = biped.index("SET_FLAG(physics->out_flags", branch_start)
    debug_branch = biped[branch_start:branch_end]
    assert "collision_debug_repeat = TRUE;" in debug_branch
    assert "collision_debug_point = position;" in debug_branch
    assert "collision_debug_vector = velocity;" in debug_branch
    assert "collision_move_pill(" in biped and debug_branch.startswith("if (debug_biped_physics")
    assert '"collision_debug_flag_use_vehicle_physics"' in hs
    assert "collision_debug.c" not in link_map
    assert "collision_debug" not in collision
    assert "not a collision-engine omission" in report


def test_platform_config_hooks_include_gameplay_animation_parity_and_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    units = (ROOT / "submodules/halo-ce-universal/source/units/units.c").read_text()
    biped = (ROOT / "submodules/halo-ce-universal/source/units/bipeds.c").read_text()
    sound = (ROOT / "submodules/halo-ce-universal/source/sound/sound_manager.c").read_text()
    terminal = (ROOT / "submodules/halo-ce-universal/source/interface/terminal.c").read_text()
    config = (ROOT / "submodules/halo-ce-universal/port/linux/src/port_config.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-config-hook-review.md").read_text()
    expected_callers = {
        "config_boolean": {"source/units/units.c"},
        "config_changes": {"source/sound/sound_manager.c", "source/units/units.c"},
        "config_real": {"source/sound/sound_manager.c"},
        "config_string": {"source/interface/terminal.c"},
    }
    for name in ("config_boolean", "config_changes", "config_real", "config_string"):
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-config-hook-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert set(row["caller_sources"]) == expected_callers[name]
    animation = units[units.index("boolean unit_animation_enhanced("):units.index("void unit_animation_")]
    assert "static boolean enhanced = TRUE" in animation
    assert 'config_boolean("game.enhanced_animations") != 0' in animation
    assert "unit_animation_enhanced(biped_index)" in biped
    assert "audio.music_volume" in sound and "audio.effects_volume" in sound
    assert "config_real(" in sound and "sound_manager_port_volume" in sound
    assert 'config_string("game.console_log")' in terminal
    assert "level = _terminal_message_important" in terminal
    assert "config_changes(void)" in config and "config_boolean(" in config
    assert "int config_boolean(const char *name) { int result; memset(&result, 0, sizeof(result)); return result; }" in generated
    assert "unsigned long config_changes(void) { unsigned long result; memset(&result, 0, sizeof(result)); return result; }" in generated
    assert "double config_real(const char *name) { double result; memset(&result, 0, sizeof(result)); return result; }" in generated
    assert "const char * config_string(const char *name) { const char * result; memset(&result, 0, sizeof(result)); return result; }" in generated
    assert "disables this enhanced-animation behavior" in report


def test_custom_edition_cache_and_bsp_hooks_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    cache = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    tag_groups = (ROOT / "submodules/halo-ce-universal/source/tag_files/tag_groups.c").read_text()
    objects = (ROOT / "submodules/halo-ce-universal/source/objects/object_types.c").read_text()
    game_engine = (ROOT / "submodules/halo-ce-universal/source/game/game_engine.c").read_text()
    cache_port = (ROOT / "submodules/halo-ce-universal/port/linux/game/custom_edition_cache.c").read_text()
    object_port = (ROOT / "submodules/halo-ce-universal/port/linux/game/custom_edition_objects.c").read_text()
    geometry = (ROOT / "submodules/halo-ce-universal/port/linux/game/custom_edition_geometry.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-custom-edition-boundary-review.md").read_text()
    names = ("custom_edition_cache_refuse", "custom_edition_cache_tags_load",
             "custom_edition_cache_tags_loaded", "custom_edition_cache_tags_unload",
             "custom_edition_level_name", "custom_edition_maps_description",
             "custom_edition_maps_name", "custom_edition_structure_bsp_load",
             "custom_edition_structure_bsp_reference_valid", "custom_edition_structure_bsp_unload",
             "custom_edition_vehicle_placement_allowed", "custom_edition_vehicles_by_placement",
             "halo_custom_edition_tag_cache")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-custom-edition-boundary-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "custom_edition_cache_refuse(header, header->build, scenario_name)" in cache
    assert "custom_edition_level_name(scenario_name)" in cache
    assert "custom_edition_cache_tags_load(" in cache
    assert "custom_edition_cache_tags_loaded()" in tag_groups
    assert "custom_edition_structure_bsp_reference_valid(reference)" in cache
    assert "custom_edition_structure_bsp_load(structure_bsp_header->base_address)" in cache
    place = objects[objects.index("if (object_type == _object_type_vehicle &&"):]
    assert "!custom_edition_vehicle_placement_allowed(scenario_object)" in place
    assert "continue;" in place[:place.index("object_new_from_scenario")]
    assert "return !custom_edition_vehicles_by_placement()" in object_port
    assert "if (custom_edition_vehicles_by_placement())" in game_engine
    assert "globals->tags_loaded = TRUE" in cache_port
    assert "custom_edition_cache_globals.tags_loaded = FALSE" in cache_port
    assert "reference->file_size > top - address" in cache_port
    assert "boolean custom_edition_vehicle_placement_allowed(struct scenario_object_datum const *placement) { boolean result; memset(&result, 0, sizeof(result)); return result; }" in generated
    assert "struct cache_file_tag_header * custom_edition_cache_tags_load" in generated
    assert "stock-parity defect" in report and "suppresses ordinary stock vehicle placements too" in report


def test_pinned_newlib_libm_helpers_resolve_to_exact_archive_members():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    helpers = {
        "acos": "w_acos", "asin": "w_asin", "atan2": "w_atan2",
        "ceil": "s_ceil", "cos": "s_cos", "floor": "s_floor",
        "fmod": "w_fmod", "log10": "w_log10", "pow": "w_pow",
        "sin": "s_sin", "sqrt": "w_sqrt", "tan": "s_tan",
    }
    for name, member in helpers.items():
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "Pinned PS2 EE Newlib 4.6.0 libm"
        assert ("hcu-ps2-libm-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert f"libm.a(libm_a-{member}.o)" in link_map
    assert "libm.a(libm_a-w_acos.o)" in link_map
    assert "libm.a(libm_a-s_tan.o)" in link_map
    assert ledger["symbols"]["rint"]["disposition"] == "implemented"
    assert ("hcu-ps2-batch-6-review.md" in ledger["symbols"]["rint"]["evidence"] or "hcu-ps2-batch-" in ledger["symbols"]["rint"]["evidence"])
    assert ledger["symbols"]["rand"]["disposition"] in {"pending", "implemented"}


def test_pinned_newlib_reent_pointer_has_initialized_archive_owner():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    row = ledger["symbols"]["_impure_ptr"]
    source = (ROOT / "build/toolchain/sources/ps2toolchain_ee_newlib/newlib/libc/reent/impure.c").read_text()
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    assert "_impure_ptr = &_impure_data" in source
    assert "libc.a(libc_a-impure.o)" in link_map
    assert row["disposition"] == "implemented"
    assert row["owner"] == "Pinned PS2 EE Newlib 4.6.0 reentrancy runtime"
    assert ("hcu-ps2-libc-reent-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert ledger["symbols"]["strtok"]["disposition"] in {"pending", "implemented"}


def test_pinned_newlib_stdout_helpers_use_ps2_tty():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    guest_log = (ROOT / "build/hcu-ps2-closure/emulator-m1-recompiler-851ca4b279b3408ba3c3cd6db2be0aff/emulog.txt").read_text()
    sdk_fdman = (ROOT / "submodules/ps2sdk/ee/libcglue/src/fdman.c").read_text()
    sdk_stdio = (ROOT / "submodules/ps2sdk/ee/libcglue/src/ps2sdkapi.c").read_text()
    sdk_glue = (ROOT / "submodules/ps2sdk/ee/libcglue/src/glue.c").read_text()
    assert "libc.a(libc_a-printf.o)" in link_map
    assert "libc.a(libc_a-puts.o)" in link_map
    assert "__libcglue_init_stdio(&(__descriptormap[STDOUT_FILENO]->info), 1)" in sdk_fdman
    assert 'const char *tty0_str = "tty0:"' in sdk_stdio
    assert "int _write(int fd, const void *buf, size_t nbytes)" in sdk_glue
    assert "HALO_PS2_LOCAL game-initialize-done" in guest_log
    assert "HALO_PS2_LOCAL m1-ui-map-request" in guest_log
    for name in ("printf", "puts"):
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "Pinned PS2 EE Newlib stdout via PS2SDK tty0"
        assert ("hcu-ps2-libc-stdout-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    for name in ("fprintf", "fopen", "fclose"):
        assert ledger["symbols"][name]["disposition"] in {"pending", "implemented"}


def test_memory_query_and_scheduler_stubs_remain_explicitly_unapproved():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-memory-and-scheduling-external-review.md").read_text()
    debug_memory = (ROOT / "submodules/halo-ce-universal/source/cseries/debug_memory.c").read_text()
    scenario = (ROOT / "submodules/halo-ce-universal/source/scenario/scenario.c").read_text()
    cache = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    assert "GlobalMemoryStatus(&status);" in debug_memory
    assert "memory_status->minimum_available_memory" in debug_memory
    assert 'check_memory_status(scenario_memory_status_attributed, "scenario_load")' in scenario
    assert "while (!read_complete)" in cache and "SwitchToThread();" in cache
    assert "Sleep(33 - milliseconds_elapsed)" in main and "Sleep(1);" in main
    assert "void GlobalMemoryStatus(struct _MEMORYSTATUS * p0) {  }" in generated
    for name in ("GlobalMemoryStatus", "SwitchToThread", "Sleep"):
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert ("hcu-ps2-memory-and-scheduling-external-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert row["reason"]
    assert "do not stub as success" in report


def test_ps2_sound_platform_disabled_before_directsound_dispatch():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    preferences = (ROOT / "submodules/halo-ce-universal/source/sound/sound_preferences.c").read_text()
    manager = (ROOT / "submodules/halo-ce-universal/source/sound/sound_manager.c").read_text()
    report = (ROOT / "docs/hcu-ps2-directsound-exclusion-review.md").read_text()
    names = {
        "DirectSoundCreate", "DirectSoundDoWork", "DirectSoundGetStreamVoiceStatus",
        "DirectSoundStopStream", "DirectSoundUseFullHRTF", "IDirectSoundBuffer_Play",
        "IDirectSoundBuffer_Release", "IDirectSoundBuffer_SetBufferData",
        "IDirectSoundStream_SetConeAngles", "IDirectSoundStream_SetConeOrientation",
        "IDirectSoundStream_SetConeOutsideVolume", "IDirectSoundStream_SetFrequency",
        "IDirectSoundStream_SetI3DL2Source", "IDirectSoundStream_SetMaxDistance",
        "IDirectSoundStream_SetMinDistance", "IDirectSoundStream_SetMixBinVolumes",
        "IDirectSoundStream_SetMixBins", "IDirectSoundStream_SetMode",
        "IDirectSoundStream_SetPosition", "IDirectSoundStream_SetVelocity",
        "IDirectSoundStream_SetVolume", "IDirectSound_CommitDeferredSettings",
        "IDirectSound_CreateSoundBuffer", "IDirectSound_CreateSoundStream",
        "IDirectSound_DownloadEffectsImage", "IDirectSound_GetCaps",
        "IDirectSound_GetSpeakerConfig", "IDirectSound_Release",
        "IDirectSound_SetDistanceFactor", "IDirectSound_SetI3DL2Listener",
        "IDirectSound_SetMixBinHeadroom", "IDirectSound_SetOrientation",
        "IDirectSound_SetPosition", "IDirectSound_SetRolloffFactor",
        "IDirectSound_SetVelocity", "dsound_sdl_stream_set_stereo_position",
        "interrupt_result", "sound_cache_sound_hardware_lock",
        "sound_cache_sound_hardware_unlock", "vsprintf",
    }
    assert len(names) == 40
    assert "#ifdef HALO_PS2\n\t-1," in preferences
    assert "if (platform_code < 0 || platform_code >= 2)" in manager
    assert "sound_manager_globals.initialized = FALSE;" in manager
    assert "platform_definitions[2]" in manager and "\tNULL," in manager
    assert "M14" in report
    for name in names:
        row = ledger["symbols"][name]
        assert row["caller_sources"] == {"source/sound/sound_dsound_xbox.c": row["caller_sources"]["source/sound/sound_dsound_xbox.c"]}
        assert row["disposition"] == "excluded-proven"
        assert row["owner"] == "HCU PS2 M1 sound platform selection: no DirectSound backend"
        assert ("hcu-ps2-directsound-exclusion-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])


def test_bink_playback_is_a_nonactive_m1_feature():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-bink-exclusion-review.md").read_text()
    assert any("source/bink" in value for key in ("exclude_dirs", "exclude_sources")
               for value in manifest[key])
    assert "boolean bink_playback_active(void) { boolean result; memset(&result, 0, sizeof(result)); return result; }" in generated
    for name in ("bink_playback_initialize", "bink_playback_dispose", "bink_playback_stop", "bink_playback_update"):
        assert f"void {name}(void) {{  }}" in generated
        row = ledger["symbols"][name]
        assert row["disposition"] == "excluded-proven"
        assert row["owner"] == "HCU PS2 M1 feature boundary: Bink video excluded"
        assert ("hcu-ps2-bink-exclusion-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    active = ledger["symbols"]["bink_playback_active"]
    assert active["disposition"] == "state-adapter"
    assert active["owner"] == "HCU PS2 M1 feature boundary: Bink inactive state"
    assert "hcu-ps2-bink-exclusion-review.md" in active["evidence"]
    assert "evidence that a campaign movie plays" in report


def test_pinned_newlib_numeric_format_helpers_resolve_to_exact_archive_members():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    newlib = ROOT / "build/toolchain/sources/ps2toolchain_ee_newlib/newlib/libc"
    report = (ROOT / "docs/hcu-ps2-libc-numeric-format-review.md").read_text()
    members = {
        "atoi": "atoi", "atof": "atof", "sprintf": "sprintf",
        "snprintf": "snprintf", "vsnprintf": "vsnprintf",
    }
    for name, member in members.items():
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "Pinned PS2 EE Newlib 4.6.0 libc"
        assert ("hcu-ps2-libc-numeric-format-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert f"libc.a(libc_a-{member}.o)" in link_map
        assert (newlib / ("stdlib" if name in ("atoi", "atof") else "stdio") /
                f"{name}.c").is_file()
    assert "strtol (s, NULL, 10)" in (newlib / "stdlib/atoi.c").read_text()
    assert "strtod" in (newlib / "stdlib/atof.c").read_text()
    for name in ("_snprintf", "_vsnprintf", "_vsnwprintf", "vswprintf"):
        row = ledger["symbols"][name]
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row["evidence"]
    assert "claim that every CE format specifier" in report


def test_hcu_ps2_crt_ascii_compare():
    subprocess.run([
        "cc", "-std=c11", "-fno-builtin", "-include", "stddef.h",
        "-DHCU_HOST_CRT_COMPARE",
        "-Wall", "-Wextra", "-Werror", "-Wno-builtin-declaration-mismatch",
        str(ROOT / "tests/hcu_ps2_crt_compare_main.c"),
        str(ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_crt.c"),
        "-o", str(ROOT / "build/hcu-ps2-crt-compare-test"),
    ], check=True, capture_output=True, text=True)
    subprocess.run([str(ROOT / "build/hcu-ps2-crt-compare-test")], check=True)
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    for name in ("_stricmp", "_strnicmp"):
        row = ledger["symbols"][name]
        assert row["disposition"] == "implemented"
        assert row["owner"] == "HCU PS2 CRT ASCII identifier comparison"
        assert ("hcu-ps2-ascii-compare-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert ledger["symbols"]["qsort"]["disposition"] in {"pending", "implemented"}


def test_m1_menu_music_state_does_not_block_map_change():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    preferences = (ROOT / "submodules/halo-ce-universal/source/sound/sound_preferences.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-ui-music-state-review.md").read_text()
    assert main.count("ui_main_menu_music_active()") >= 1
    assert "if (ui_main_menu_music_active() == TRUE)" in main
    assert "ui_stop_main_menu_music();" in main
    assert "#ifdef HALO_PS2\n\t-1," in preferences
    assert "boolean ui_main_menu_music_active(void) { boolean result; memset(&result, 0, sizeof(result)); return result; }" in generated
    assert "void ui_stop_main_menu_music(void) {  }" in generated
    for name, disposition in (("ui_main_menu_music_active", "state-adapter"),
                              ("ui_stop_main_menu_music", "excluded-proven")):
        row = ledger["symbols"][name]
        assert row["caller_sources"] == {
            "source/main/main.c": row["caller_sources"]["source/main/main.c"]}
        assert row["disposition"] == disposition
        assert ("hcu-ps2-ui-music-state-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "does not approve music-start/play/query" in report


def test_hcu_cheat_state_is_owned_writable_ce_gameplay_state():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    header = (ROOT / "submodules/halo-ce-universal/source/game/cheats.h").read_text()
    cheats = (ROOT / "submodules/halo-ce-universal/source/game/cheats.c").read_text()
    weapons = (ROOT / "submodules/halo-ce-universal/source/items/weapons.c").read_text()
    damage = (ROOT / "submodules/halo-ce-universal/source/objects/damage.c").read_text()
    hs = (ROOT / "submodules/halo-ce-universal/source/hs/hs_globals_external.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    report = (ROOT / "docs/hcu-ps2-cheat-state-review.md").read_text()
    assert "struct cheat_globals" in header and "extern struct cheat_globals cheat;" in header
    assert "cheat.infinite_ammo" in weapons and "cheat.bottomless_clip" in weapons
    assert "cheat.deathless_player" in damage
    assert "&cheat.infinite_ammo" in hs and "&cheat.jetpack" in hs
    assert "csmemset(&cheat, 0, sizeof(cheat));" in cheats
    assert "struct cheat_globals cheat;" in generated
    row = ledger["symbols"]["cheat"]
    assert row["disposition"] == "implemented"
    assert row["owner"] == "HCU PS2 CE global-state storage"
    assert ("hcu-ps2-cheat-state-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "must therefore retain its normal global lifetime" in report


def test_allow_out_of_sync_retains_ce_false_local_default():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    network = (ROOT / "submodules/halo-ce-universal/source/networking/network_client_manager.c").read_text()
    hs = (ROOT / "submodules/halo-ce-universal/source/hs/hs_globals_external.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    assert "boolean allow_out_of_sync = FALSE;" in network
    assert '"allow_out_of_sync", _hs_type_boolean, 0, &allow_out_of_sync' in hs
    assert "boolean allow_out_of_sync;" in generated
    row = ledger["symbols"]["allow_out_of_sync"]
    assert row["disposition"] == "state-adapter"
    assert row["owner"] == "HCU PS2 CE global storage: local network flag"
    assert ("hcu-ps2-network-script-flag-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])


def test_file_backed_newlib_stdio_stays_pending_until_device_contract():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    report = (ROOT / "docs/hcu-ps2-libc-file-stdio-review.md").read_text()
    expected_sources = {
        "fopen": {"source/camera/director.c", "source/cseries/debug_memory.c",
                  "source/cseries/errors.c", "source/game/cheats.c",
                  "source/hs/hs.c", "source/main/console.c", "source/main/main.c",
                  "source/objects/objects.c", "source/saved games/game_state.c"},
        "fclose": {"source/camera/director.c", "source/cseries/debug_memory.c",
                   "source/cseries/errors.c", "source/game/cheats.c", "source/hs/hs.c",
                   "source/main/console.c", "source/main/main.c", "source/objects/objects.c"},
        "fflush": {"source/cseries/errors.c", "source/main/main.c",
                   "source/saved games/game_state.c", "source/structures/structure_lens_flares.c"},
        "fgets": {"source/game/cheats.c", "source/main/console.c"},
        "fprintf": {"source/camera/director.c", "source/cseries/debug_memory.c",
                    "source/cseries/errors.c", "source/hs/hs.c", "source/main/main.c",
                    "source/objects/objects.c", "source/saved games/game_state.c"},
        "fputc": {"source/objects/objects.c"},
        "fputs": {"source/objects/objects.c", "source/structures/structure_lens_flares.c"},
        "fread": {"source/main/main.c"},
        "fscanf": {"source/camera/director.c"},
    }
    for name, callers in expected_sources.items():
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert set(row["caller_sources"]) == callers
        assert f"libc.a(libc_a-{name}.o)" in link_map
        assert ("hcu-ps2-libc-file-stdio-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "Stdout is a separate" in report


def test_network_player_replication_helpers_remain_pending_until_local_mode_contract():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-network-tick-boundary-review.md").read_text()
    sources = {
        "network_game_distributed_client": "source/networking/network_game_globals.c",
        "network_distributed_tick": "source/game/game_time.c",
        "network_distributed_new_game": "source/game/game.c",
        "network_distributed_player_killed": "source/game/game_engine.c",
        "network_distributed_player_picked_up": "source/game/players.c",
        "distributed_player_to_byte": "source/game/game_engine_ctf.c",
    }
    for name, source in sources.items():
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert source in row["evidence"]
        assert ("hcu-ps2-network-tick-boundary-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    network = (ROOT / "submodules/halo-ce-universal/source/networking/network_game_globals.c").read_text()
    game_time = (ROOT / "submodules/halo-ce-universal/source/game/game_time.c").read_text()
    damage = (ROOT / "submodules/halo-ce-universal/source/objects/damage.c").read_text()
    players = (ROOT / "submodules/halo-ce-universal/source/game/players.c").read_text()
    assert "return game_connection() == _game_connection_network_client;" in network
    assert "network_distributed_tick();" in game_time
    assert "#define objects_update_shields() (!network_game_distributed_client())" in damage
    assert "#define players_decide_pickups() (!network_game_distributed_client())" in players
    assert "remain **pending**" in report


def test_network_session_lifecycle_helpers_remain_pending_until_connection_fixture():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-network-session-boundary-review.md").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    game_time = (ROOT / "submodules/halo-ce-universal/source/game/game_time.c").read_text()
    globals_c = (ROOT / "submodules/halo-ce-universal/source/networking/network_game_globals.c").read_text()
    expected = {
        "network_game_abort": "source/game/game_engine.c",
        "network_game_client_start_frame": "source/main/main.c",
        "network_game_client_end_frame": "source/main/main.c",
        "network_game_server_start_frame": "source/main/main.c",
        "network_game_server_update_ticks": "source/game/game_time.c",
    }
    for name, source in expected.items():
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert source in row["evidence"]
        assert ("hcu-ps2-network-session-boundary-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "connection==_game_connection_network_client" in main
    assert "connection==_game_connection_network_server" in main
    assert "connection>_game_connection_local" in main
    assert "case _game_connection_network_server:" in game_time
    assert "bss_004566dc.client_started = TRUE;" in globals_c
    assert "remain pending" in report


def test_network_bootstrap_helpers_remain_pending_until_local_use_is_proven():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-network-bootstrap-review.md").read_text()
    game = (ROOT / "submodules/halo-ce-universal/source/game/game.c").read_text()
    messages = (ROOT / "submodules/halo-ce-universal/source/networking/network_messages.c").read_text()
    transport = (ROOT / "submodules/halo-ce-universal/source/bungie_net/network/transport_endpoint_set_winsock.c").read_text()
    expected = {
        "transport_initialize": "source/game/game.c",
        "transport_dispose": "source/game/game.c",
        "initialize_network_game_packets": "source/game/game.c",
    }
    for name, source in expected.items():
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert source in row["evidence"]
        assert ("hcu-ps2-network-bootstrap-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "transport_initialize();" in game and "transport_dispose();" in game
    assert "initialize_network_game_packets();" in game
    assert "data_packet_group_initialize(&data_0030aa68.group);" in messages
    assert "XNetStartup(&startup_params)" in transport
    assert "XNetCleanup();" in transport
    assert "remain pending" in report


def test_obstacle_path_diagnostic_globals_are_excluded_only_from_ai_decisions():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-obstacle-debug-review.md").read_text()
    source = (ROOT / "submodules/halo-ce-universal/source/ai/path_obstacle_avoidance.c").read_text()
    names = (
        "debug_ignore_broken_surfaces", "debug_obstacle_path_finishing",
        "debug_obstacle_path_goal_point", "debug_obstacle_path_goal_surface_index",
        "debug_obstacle_path_radius", "debug_obstacle_path_start_point",
        "debug_obstacle_path_start_surface_index",
    )
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] == "excluded-proven"
        assert row["owner"] == "HCU PS2 omission: obstacle-path diagnostic replay state only"
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-obstacle-debug-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    failure_capture = source[source.index("if (debug_obstacle_path_on_failure)"):source.index("result= FALSE;", source.index("if (debug_obstacle_path_on_failure)"))]
    diagnostic_replay = source[source.index("void render_debug_obstacle_path("):]
    for name in names:
        assert name in failure_capture
        assert name in diagnostic_replay
    assert "path_new(" in diagnostic_replay
    assert "return result;" in source
    assert "diagnostic snapshots" in report


def test_object_debug_toggles_are_render_only_and_do_not_change_simulation():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-object-debug-review.md").read_text()
    objects = (ROOT / "submodules/halo-ce-universal/source/objects/object_types.c").read_text()
    bipeds = (ROOT / "submodules/halo-ce-universal/source/units/bipeds.c").read_text()
    devices = (ROOT / "submodules/halo-ce-universal/source/devices/devices.c").read_text()
    vehicles = (ROOT / "submodules/halo-ce-universal/source/units/vehicles.c").read_text()
    expected = {
        "debug_objects_biped_autoaim_pills": "biped_render_debug",
        "debug_objects_biped_physics_pills": "biped_render_debug",
        "debug_objects_devices": "device_render_debug",
        "debug_objects_vehicle_powered_mass_points": "vehicle_render_debug",
    }
    for name, function in expected.items():
        row = ledger["symbols"][name]
        assert row["disposition"] == "excluded-proven"
        assert row["owner"] == "HCU PS2 omission: object debug drawing, outside simulation"
        assert row["reason"] and row["evidence"] and row["test"]
        assert f"hcu-ps2-object-debug-review.md" in row["evidence"]
        assert function in report
    assert "biped_render_debug," in objects and "vehicle_render_debug," in objects
    assert "device_render_debug," in objects
    biped_body = bipeds[bipeds.index("void biped_render_debug("):bipeds.index("void biped_build_flying_axes(")]
    vehicle_body = vehicles[vehicles.index("void vehicle_render_debug("):vehicles.index("boolean vehicle_stuck(")]
    device_body = devices[devices.index("void device_render_debug("):devices.index("void device_render_debug(") + 2500]
    assert "render_debug_pill(" in biped_body and "render_debug_sphere(" in biped_body
    assert "vehicle->object.angular_velocity" not in vehicle_body
    assert "render_debug_string_at_point(" in device_body
    assert "source call graph" in report


def test_render_debug_globals_are_diagnostic_only():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-render-debug-globals-review.md").read_text()
    expected = {
        "debug_bink": "source/bink/bink_playback.c",
        "debug_bsp": "source/render/render_debug.c",
        "debug_camera": "source/render/render_debug.c",
        "debug_inactive_objects": "source/render/render_objects.c",
        "debug_input": "source/render/render_debug.c",
        "debug_leaf_index": "source/structures/structure_render.c",
        "debug_leaf_portal_index": "source/structures/structure_render.c",
        "debug_leaf_portals": "source/structures/structure_render.c",
        "debug_objects": "source/render/render_objects.c",
        "debug_permanent_decals": "source/render/render_debug.c",
        "debug_player": "source/render/render_debug.c",
        "debug_sound_cache": "source/cache/xbox_sound_cache.c",
        "debug_sound_environment": "source/scenario/scenario.c",
        "debug_sprites": "source/render/render_sprite.c",
        "debug_structure": "source/render/render_debug.c",
        "debug_texture_cache": "source/cache/xbox_texture_cache.c",
    }
    for name, source in expected.items():
        row = ledger["symbols"][name]
        assert row["disposition"] == "excluded-proven"
        assert row["reason"] and row["evidence"] and row["test"]
        assert source in row["evidence"]
        assert ("hcu-ps2-render-debug-globals-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert "HCU PS2 omission:" in row["owner"]
    texture_cache = (ROOT / "submodules/halo-ce-universal/source/cache/xbox_texture_cache.c").read_text()
    scenario = (ROOT / "submodules/halo-ce-universal/source/scenario/scenario.c").read_text()
    sprite = (ROOT / "submodules/halo-ce-universal/source/render/render_sprite.c").read_text()
    texture_slice = texture_cache[texture_cache.index("if (debug_texture_cache)"):texture_cache.index("cache_file_promote_read(texture->read_request_handle)")]
    assert "console_warning(" in texture_slice
    assert "cache_file_promote_read(texture->read_request_handle);" in texture_cache
    scenario_slice = scenario[scenario.index("if (debug_sound_environment)"):scenario.index("current = &scenario_globals->sound_environment;")]
    assert "render_debug_string(FALSE, temporary);" in scenario_slice
    assert "*current = *definition;" in scenario
    sprite_stats = sprite[sprite.index("coverage: %.1f big sprites"):sprite.index("build_sprite_globals.screen_coverage = 0.f")]
    assert "render_debug_string(FALSE, string);" in sprite_stats
    build_sprite = sprite[sprite.index("void build_sprite("):sprite.index("void build_sprite_rotational(")]
    assert build_sprite.index("if (coverage>0.5f && build_sprite_globals.big_sprite_count++>10)") < build_sprite.index("if (debug_sprites)")
    assert "optional diagnostic controls" in report


def test_render_debug_primitives_have_no_simulation_side_effects():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-render-debug-primitives-review.md").read_text()
    expected = {
        "render_debug_line": {"source/objects/objects.c", "source/physics/collision_bsp.c"},
        "render_debug_matrix": {"source/objects/objects.c"},
        "render_debug_pill": {"source/units/bipeds.c"},
        "render_debug_point": {"source/physics/point_physics.c", "source/units/units.c"},
        "render_debug_sphere": {"source/effects/material_effects.c", "source/objects/objects.c",
                                "source/physics/physics.c", "source/sound/sound_manager.c",
                                "source/units/bipeds.c"},
        "render_debug_string": {"source/scenario/scenario.c", "source/sound/sound_dsound_xbox.c"},
        "render_debug_string_at_point": {"source/devices/devices.c", "source/objects/objects.c",
                                          "source/sound/sound_manager.c", "source/units/units.c"},
        "render_debug_vector": {"source/objects/objects.c", "source/units/units.c"},
        "render_debug_vectors": {"source/physics/physics.c"},
    }
    for name, callers in expected.items():
        row = ledger["symbols"][name]
        assert row["disposition"] == "excluded-proven"
        assert set(row["caller_sources"]) == callers
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-render-debug-primitives-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    point_physics = (ROOT / "submodules/halo-ce-universal/source/physics/point_physics.c").read_text()
    point_step = point_physics[point_physics.index("unsigned long point_physics_update("):point_physics.index("struct point_physics_definition *point_physics_definition_interpolate(")]
    material = (ROOT / "submodules/halo-ce-universal/source/effects/material_effects.c").read_text()
    scenario = (ROOT / "submodules/halo-ce-universal/source/scenario/scenario.c").read_text()
    assert "if (debug_point_physics)" in point_step
    assert point_step.index("position->z = collision.plane.n.k * offset + collision.point.z;") < point_step.index("if (debug_point_physics)")
    assert "if (debug_material_effects)" in material
    assert "if (debug_sound_environment)" in scenario
    assert "they do not advance camera, object, damage, collision, audio selection, or effects state" in report


def test_model_debug_controls_change_diagnostics_not_model_state():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-model-debug-controls-review.md").read_text()
    models = (ROOT / "submodules/halo-ce-universal/source/models/models.c").read_text()
    hs = (ROOT / "submodules/halo-ce-universal/source/hs/hs_globals_external.c").read_text()
    names = ("render_model_index_counts", "render_model_markers", "render_model_no_geometry",
             "render_model_nodes", "render_model_vertex_counts")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] == "excluded-proven"
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-model-debug-controls-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    geometry_gate = models[models.index("if (!render_model_no_geometry && geometry_index!=NONE)"):models.index("if (!render_model_no_geometry && geometry_index!=NONE)") + 180]
    assert "model->geometries" in geometry_gate
    assert "FALSE, /* render_model_no_geometry */" in hs
    assert "render_debug_matrix(TRUE, &node_matrices[node_index], 0.05f);" in models
    assert "render_debug_matrix(FALSE, &marker_matrix, 0.05f);" in models
    assert "render_debug_string_at_point(FALSE, &point, string, color);" in models
    assert "Neither changes the palette, nodes, markers, or object transform" in report


def test_effect_render_switches_remain_pending_until_ps2_adapter_contract():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-effect-render-switches-review.md").read_text()
    render = (ROOT / "submodules/halo-ce-universal/source/render/render.c").read_text()
    particles = (ROOT / "submodules/halo-ce-universal/source/render/render_particles.c").read_text()
    systems = (ROOT / "submodules/halo-ce-universal/source/effects/particle_systems.c").read_text()
    weather = (ROOT / "submodules/halo-ce-universal/source/effects/weather_particle_systems.c").read_text()
    contrails = (ROOT / "submodules/halo-ce-universal/source/render/render_contrails.c").read_text()
    objects = (ROOT / "submodules/halo-ce-universal/source/render/render_objects.c").read_text()
    names = ("render_contrails_enabled", "render_particles_enabled", "render_particle_systems_enabled",
             "render_weather_particle_systems_enabled", "render_shadows")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] == "state-adapter"
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-batch-6-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert render.count("= TRUE;") >= 4
    assert "render_weather_particle_systems_enabled = enable;" in render
    assert "if (render_particles_enabled)" in particles
    assert "if (render_particle_systems_enabled)" in systems
    weather_body = weather[weather.index("void weather_particle_systems_render("):]
    assert "if (render_particle_systems_enabled && weather)" in weather_body
    assert "system->location.cluster_index = render.cluster_index;" in weather_body
    assert "system->under_water = scenario_location_underwater" in weather_body
    assert "weather_particle_system_delete(render.local_player_index);" in weather_body
    assert "weather_particle_system_new(render.local_player_index" in weather_body
    assert "if (render_contrails_enabled)" in contrails
    assert "if (render_shadows)" in objects
    assert "does **not** test this variable" in report


def test_connected_geometry_lens_flare_path_remains_pending_until_owner_is_proven():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-connected-geometry-review.md").read_text()
    lens = (ROOT / "submodules/halo-ce-universal/source/structures/structure_lens_flares.c").read_text()
    connected = (ROOT / "submodules/halo-ce-universal/source/tool/connected_geometry.c").read_text()
    expected = ("connected_geometry_new", "connected_geometry_add_triangle",
                "connected_geometry_group_coplanar", "connected_geometry_delete")
    for name in expected:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert row["caller_sources"] == {
            "source/structures/structure_lens_flares.c": row["caller_sources"]["source/structures/structure_lens_flares.c"]}
        assert ("hcu-ps2-connected-geometry-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "connected_geometry_new(&geometry);" in lens
    assert "connected_geometry_group_coplanar(&geometry)" in lens
    assert "tag_block_resize(&structure_bsp->lens_flares, 0)" in lens
    assert "tag_block_resize(&structure_bsp->lens_flare_markers, 0)" in lens
    assert "connected_geometry_delete(&geometry);" in lens
    assert "dynamic_array_new(&geometry->edges" in connected
    assert "dynamic_array_delete(&geometry->edges" in connected
    assert "connected_geometry_group_recursive" in connected
    assert "only rooted caller is CE's structure-lens-flare builder" in report


def test_coop_spectating_is_unreachable_only_in_current_local_profile():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-coop-spectating-review.md").read_text()
    ps2_coop = (ROOT / "submodules/halo-ce-universal/port/ps2/game/ps2_coop.c").read_text()
    linux_spectate = (ROOT / "submodules/halo-ce-universal/port/linux/game/coop_spectate.c").read_text()
    director = (ROOT / "submodules/halo-ce-universal/source/camera/director.c").read_text()
    hud = (ROOT / "submodules/halo-ce-universal/source/interface/hud.c").read_text()
    expected = {"coop_spectating": "state-adapter", "coop_spectate_unit": "excluded-proven",
                "coop_spectate_camera": "excluded-proven"}
    for name, disposition in expected.items():
        row = ledger["symbols"][name]
        assert row["disposition"] == disposition
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-coop-spectating-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert "M5" in row["owner"] or "M5" in row["reason"]
    assert "boolean network_coop_active(" in ps2_coop
    assert "return FALSE;" in ps2_coop[ps2_coop.index("boolean network_coop_active("):ps2_coop.index("boolean network_coop_player_collisions(")]
    assert "return network_coop_active();" in linux_spectate
    assert "coop_spectating() ? coop_spectate_unit(local_player_index) : NONE" in director
    assert "if (watched_unit_index != NONE)\n\t\t\t\t\tcoop_spectate_camera" in director
    assert "player->unit_index == NONE && coop_spectating()" in hud
    assert "mutates dead-camera yaw, pitch, follow distance, and FOV" in report


def test_editor_lifecycle_stubs_match_local_non_editor_profile():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-editor-boundary-review.md").read_text()
    manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    source_stubs = (ROOT / "submodules/halo-ce-universal/source/editor/editor_stubs.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    lifecycle = {
        "editor_initialize": ("void editor_initialize(\n\tvoid)\n{\n\treturn;", "void editor_initialize(void) {  }"),
        "editor_dispose": ("void editor_dispose(\n\tvoid)\n{\n\treturn;", "void editor_dispose(void) {  }"),
        "editor_update": ("void editor_update(\n\tvoid)\n{\n\treturn;", "void editor_update(void) {  }"),
        "editor_initialize_for_new_map": ("void editor_initialize_for_new_map(\n\tvoid)\n{\n\treturn;", "void editor_initialize_for_new_map(void) {  }"),
        "editor_dispose_from_old_map": ("void editor_dispose_from_old_map(\n\tvoid)\n{\n\treturn;", "void editor_dispose_from_old_map(void) {  }"),
        "editor_should_exit": ("boolean editor_should_exit(\n\tvoid)\n{\n\treturn FALSE;", "boolean editor_should_exit(void) { boolean result; memset(&result, 0, sizeof(result)); return result; }"),
    }
    assert "source/editor/" in manifest["exclude_dirs"]
    for name, (source_body, generated_body) in lifecycle.items():
        row = ledger["symbols"][name]
        assert row["disposition"] == "excluded-proven"
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-editor-boundary-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert source_body in source_stubs
        assert generated_body in generated
    game_in_editor = ledger["symbols"]["game_in_editor"]
    assert game_in_editor["disposition"] in {"pending", "state-adapter", "implemented"}
    assert "ai_place();" in (ROOT / "submodules/halo-ce-universal/source/game/game.c").read_text()
    assert "if (!game_in_editor())" in (ROOT / "submodules/halo-ce-universal/source/objects/object_types.c").read_text()
    assert "game_in_editor()" in (ROOT / "submodules/halo-ce-universal/source/ai/encounters.c").read_text()
    assert "remains **pending**" in report


def test_game_in_editor_remains_pending_as_cross_gameplay_state():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    row = ledger["symbols"]["game_in_editor"]
    assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
    assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
    assert row["reason"] and row["evidence"] and row["test"]
    assert "AI" in row["reason"] and "object placement" in row["reason"]
    assert ("hcu-ps2-editor-boundary-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])


def test_build_sprite_api_remains_pending_for_ps2_geometry_adapter():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-build-sprites-review.md").read_text()
    sprite = (ROOT / "submodules/halo-ce-universal/source/render/render_sprite.c").read_text()
    antenna = (ROOT / "submodules/halo-ce-universal/source/objects/widgets/antenna.c").read_text()
    glow = (ROOT / "submodules/halo-ce-universal/source/objects/widgets/glow.c").read_text()
    for name in ("build_sprites_begin", "build_sprite", "build_sprites_end"):
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-build-sprites-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
        assert set(row["caller_sources"]) == {
            "source/objects/widgets/antenna.c", "source/objects/widgets/glow.c"}
    assert "viewmodel_projection_begin();" in sprite
    assert "viewmodel_projection_end();" in sprite
    assert "rasterizer_dynamic_vertices_lock" in sprite
    assert "rasterizer_dynamic_unlit_geometry_draw" in sprite
    assert "rasterizer_dynamic_vertices_delete" in sprite
    assert "real one_over_sprite_count = 1.f / data->sprite_count;" in sprite
    assert "build_sprites_begin(" in antenna and "build_sprites_end(&sprite_data);" in antenna
    assert "build_sprites_begin(" in glow and "build_sprites_end(&sprite_data);" in glow
    assert "may receive an empty particle chain" in report


def test_map_tag_load_hooks_remain_pending_until_profile_and_lifecycle_are_proven():
    ledger = json.loads((ROOT / "docs/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-ps2-tag-load-hooks-review.md").read_text()
    cache = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    names = (
        "hud_hires_tags_loaded", "hud_hires_tags_unloaded", "menu_tags_loaded",
        "menu_tags_unloaded", "pal_tags_loaded", "powerup_render_bounds_tags_loaded",
    )
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-tag-load-hooks-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert cache.index("hud_hires_tags_unloaded();") < cache.index("texture_cache_close();")
    assert cache.index("texture_cache_close();") < cache.index("menu_tags_unloaded();")
    assert cache.index("tags_header_register_vertex_and_index_buffers(cache_file_globals.tag_header);") < cache.index("pal_tags_loaded(cache_file_globals.header.build);")
    assert "rewrites biped/global/weapon/projectile/Warthog tag values" in report
    assert "synthesizes tags/widgets" in report


def test_ui_widget_lifecycle_roots_keep_stateful_owners_pending():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-ui-widget-lifecycle-review.md").read_text()
    source = (ROOT / "submodules/halo-ce-universal/source/interface/ui_widget.c").read_text()
    manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    names = (
        "ui_widgets_initialize", "ui_widgets_dispose", "ui_widgets_close_all",
        "ui_widget_load_by_name_or_tag", "ui_widgets_active_for_local_player",
        "ui_widgets_inhibit_processing", "ui_widgets_disable_pause_game",
        "ui_widgets_set_fade_value", "ui_widget_load_progress_widget",
    )
    assert "source/interface/ui_widget.c" in manifest["exclude_sources"]
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-ui-widget-lifecycle-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    safe = ledger["symbols"]["ui_widgets_safe_to_load"]
    assert safe["disposition"] == "excluded-proven"
    body = source[source.index("void ui_widgets_safe_to_load("):source.index("void ui_widgets_inhibit_processing(")]
    body = body.split("{", 1)[1]
    assert "return;" in body and "safe" not in body
    assert "exact empty function" in safe["owner"]
    assert "processing_inhibited = inhibit" in source
    assert "pause_disabled_ticks = duration_ticks" in source
    assert "widget_globals.fade_to_black = value" in source
    assert "bounded widget-pool implementation" in report


def test_dynamic_geometry_roots_require_bounded_ps2_renderer_owner():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-dynamic-geometry-review.md").read_text()
    xbox = (ROOT / "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c").read_text()
    flags = (ROOT / "submodules/halo-ce-universal/source/objects/widgets/flags.c").read_text()
    lightning = (ROOT / "submodules/halo-ce-universal/source/objects/widgets/lightning.c").read_text()
    names = (
        "rasterizer_dynamic_triangles_new", "rasterizer_dynamic_triangles_lock",
        "rasterizer_dynamic_triangles_unlock", "rasterizer_dynamic_triangles_delete",
        "rasterizer_dynamic_vertices_new", "rasterizer_dynamic_vertices_lock",
        "rasterizer_dynamic_vertices_unlock", "rasterizer_dynamic_vertices_delete",
        "rasterizer_dynamic_unlit_geometry_draw",
    )
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-dynamic-geometry-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "dynamic_triangles.triangle_count<RASTERIZER_MAXIMUM_DYNAMIC_TRIANGLES-count" in xbox
    assert "dynamic_vertices.buffer_count<RASTERIZER_MAXIMUM_DYNAMIC_VERTEX_BUFFERS-1" in xbox
    assert "dynamic_triangle_buffer->triangles" in xbox and "dynamic_vertex_buffer->vertices" in xbox
    assert "rasterizer_dynamic_triangles_new" in flags and "rasterizer_dynamic_vertices_new" in flags
    assert "rasterizer_dynamic_unlit_geometry_draw" in lightning
    assert "bounded dynamic geometry arena" in report


def test_mod_hooks_remain_pending_until_ps2_resource_mod_scope_is_decided():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-mods-hooks-review.md").read_text()
    mods = (ROOT / "submodules/halo-ce-universal/port/linux/game/mods.c").read_text()
    cache = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    names = ("mods_enable", "mods_list", "mods_reload", "mods_tags_loaded", "mods_tags_unloaded")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-mods-hooks-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert all("mods.c" not in source for source in manifest.get("port_sources", []))
    assert "mod_sounds_tags_unloaded();" in mods
    assert "mod_bitmaps_tags_unloaded();" in mods
    assert "mod_models_tags_unloaded(give_back);" in mods
    assert cache.index("texture_cache_close();") < cache.index("mods_tags_unloaded();")
    assert cache.index("mods_tags_unloaded();") < cache.index("cache_file_close();")
    assert "Custom Edition campaign/tag cache" in report


def test_main_menu_ui_roots_remain_pending_for_ps2_state_owner():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-main-menu-ui-review.md").read_text()
    ui = (ROOT / "submodules/halo-ce-universal/source/interface/ui_widget.c").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    input_source = (ROOT / "submodules/halo-ce-universal/source/input/input_abstraction.c").read_text()
    names = ("main_menu_active", "main_menu_is_active", "main_screen_shell_begin_fade", "main_screen_shell_load", "process_ui_widgets")
    for name in names:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-main-menu-ui-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    assert "we_are_at_the_main_menu = active" in ui
    assert "return we_are_at_the_main_menu" in ui
    assert "auto_close_fade_time = fade_duration_milliseconds" in ui
    assert "ui_widgets_close_all();" in ui[ui.index("void main_screen_shell_load("):]
    assert "process_ui_widgets();" in main
    assert "main_menu_is_active()" in input_source
    assert "controller-disconnect" in report


def test_virtual_keyboard_is_inactive_only_for_current_rooted_pad_profile():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-virtual-keyboard-boundary-review.md").read_text()
    manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    input_source = (ROOT / "submodules/halo-ce-universal/source/input/input_abstraction.c").read_text()
    keyboard = (ROOT / "submodules/halo-ce-universal/source/interface/virtual_keyboard.c").read_text()
    closure = json.loads((ROOT / "build/hcu-ps2-closure/all/result.json").read_text())
    active = ledger["symbols"]["virtual_keyboard_active"]
    close = ledger["symbols"]["virtual_keyboard_close"]
    assert active["disposition"] == "state-adapter" and active["owner"] and active["reason"] and active["test"]
    assert close["disposition"] == "excluded-proven" and close["owner"] and close["reason"] and close["test"]
    assert "source/interface/virtual_keyboard.c" in manifest["exclude_sources"]
    assert "source/interface/ui_widget.c" in manifest["exclude_sources"]
    assert "virtual_keyboard_launch" not in {row["symbol"] for row in closure["rooted_link"]["live_externals"]}
    caller = input_source[input_source.index("if (virtual_keyboard_active())"):input_source.index("display_error_deferred(error_code", input_source.index("if (virtual_keyboard_active())"))]
    assert caller.index("virtual_keyboard_active()") < caller.index("virtual_keyboard_close();")
    assert "return virtual_keyboard_globals.active" in keyboard
    assert "virtual_keyboard_cancel();" in keyboard[keyboard.index("void virtual_keyboard_close("):]
    assert "Re-open before implementing" in report


def test_toolchain_remainder_records_provider_and_caller_contracts():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-toolchain-remainder-review.md").read_text()
    crt = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_crt.c").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    unicode = (ROOT / "submodules/halo-ce-universal/source/text/unicode.c").read_text()
    cseries = (ROOT / "submodules/halo-ce-universal/source/cseries/cseries.c").read_text()
    header = (ROOT / "submodules/halo-ce-universal/source/cseries/cseries.h").read_text()
    random_math = (ROOT / "submodules/halo-ce-universal/source/math/random_math.c").read_text()
    aim = (ROOT / "submodules/halo-ce-universal/source/game/aim_assist.c").read_text()
    pixels = (ROOT / "submodules/halo-ce-universal/source/bitmaps/bitmaps_inlines.h").read_text()
    pending = (
        "_snprintf", "_vsnprintf", "_vsnwprintf", "vswprintf",
        "memcpy", "qsort", "strtok", "rand", "towlower",
    )
    for name in pending:
        row = ledger["symbols"][name]
        assert row["disposition"] in {"pending", "implemented", "state-adapter", "excluded-proven"}
        assert row["disposition"] == "pending" or "hcu-ps2-batch-" in row.get("evidence", "")
        assert row["reason"] and row["evidence"] and row["test"]
        assert ("hcu-ps2-toolchain-remainder-review.md" in row["evidence"] or "hcu-ps2-batch-" in row["evidence"])
    exit_row = ledger["symbols"]["exit"]
    assert exit_row["disposition"] == "implemented"
    assert exit_row["owner"] and exit_row["reason"] and exit_row["evidence"] and exit_row["test"]
    assert "return vsnprintf(buffer, count, format, args);" in crt
    wide = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_crt.c").read_text()
    assert "return truncated ? -1 : (int)used;" in wide[wide.index("int _vsnwprintf("):]
    assert "result = vswprintf(string, format, arglist);" in unicode
    assert "return _vsnwprintf(string, size, format, arglist);" in unicode
    assert "exit(0);" in main[main.index("void halt_and_catch_fire("):main.index("void main_loop_of_death(")]
    assert "return strtok(s1, s2);" in cseries
    assert "c1 = towlower(*s1);" in cseries
    assert "return memcpy(destination, source, size);" in cseries
    assert "__builtin_rint((double)value)" in header
    assert "__builtin_rint((double)color->blue * scale)" in pixels
    assert "system_seconds()^system_milliseconds()^rand()" in random_math
    assert "qsort(targets, target_count, sizeof(struct aim_assist_target), compare_targets);" in aim
    assert "ignores the argument list" in report


def _assert_reviewed(ledger, names, disposition, evidence_name):
    for name in names:
        row = ledger["symbols"][name]
        assert row["reason"] and row["evidence"] and row["test"]
        if "hcu-ps2-batch-" in row["evidence"]:
            assert row["disposition"] in {"implemented", "state-adapter", "excluded-proven"}, name
            continue
        assert row["disposition"] == disposition, name
        assert evidence_name in row["evidence"]
        if disposition != "pending":
            assert row["owner"]


def test_fatal_debug_surface_separates_halt_draws_from_debug_options():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-fatal-debug-surface-review.md").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    telnet = (ROOT / "submodules/halo-ce-universal/source/networking/telnet_console.c").read_text()
    ui = (ROOT / "submodules/halo-ce-universal/source/interface/ui_widget.c").read_text()
    rasterizer = (ROOT / "submodules/halo-ce-universal/source/rasterizer/rasterizer.c").read_text()
    manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    halt = main[main.index("void halt_and_catch_fire("):main.index("void main_loop_of_death(")]
    _assert_reviewed(ledger, (
        "rasterizer_debug_draw", "rasterizer_draw_string", "rasterizer_reset_state",
        "rasterizer_transparent_geometry_draw", "ui_widget_debug_show_path",
        "telnet_console_initialize", "telnet_console_dispose", "telnet_console_print",
        "telnet_console_process", "tiff_export", "d3d_find_flipcount",
    ), "excluded-proven", "hcu-ps2-fatal-debug-surface-review.md")
    _assert_reviewed(ledger, ("halo_screen_width", "rasterizer_debug_options"),
                     "pending", "hcu-ps2-fatal-debug-surface-review.md")
    assert "rasterizer_reset_state();" in halt
    assert "rasterizer_draw_string(" in halt
    assert "rasterizer_transparent_geometry_draw(TRUE);" in halt
    assert "rasterizer_debug_draw();" in halt
    assert "(short)halo_screen_width();" in halt
    assert "if (telnet_console_globals.initialized)" in telnet
    assert "widget_globals.debug_show_path = show;" in ui
    assert "char const *error_message = tiff_export(file, screen);" in main
    assert "if (!main_globals.d3d_flip_count)" in main
    assert "source/bitmaps/tiff_file.c" in manifest["exclude_sources"]
    assert "TRUE, /* draw_models */" in rasterizer
    assert "not that width" in report


def test_linux_input_overlays_stay_false_on_the_pad_path():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-linux-input-overlay-review.md").read_text()
    control = (ROOT / "submodules/halo-ce-universal/source/game/player_control.c").read_text()
    abstraction = (ROOT / "submodules/halo-ce-universal/source/input/input_abstraction.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    names = (
        "halo_linux_mouse_aiming", "halo_linux_mouse_look", "halo_linux_touch_aiming",
        "halo_linux_touch_look", "halo_linux_touch_move",
    )
    _assert_reviewed(ledger, names, "state-adapter", "hcu-ps2-linux-input-overlay-review.md")
    assert "if (halo_linux_touch_look(gamepad_index, &touch_yaw, &touch_pitch, &gyro_yaw, &gyro_pitch) &&" in control
    assert "if (halo_linux_mouse_aiming(gamepad_index) || halo_linux_touch_aiming(gamepad_index))" in control
    assert "if (halo_linux_mouse_look(gamepad_index, &mouse_yaw, &mouse_pitch))" in control
    assert "if (halo_linux_touch_move((short)controller_index, &forward, &strafe))" in abstraction
    for name in names:
        assert "return result;" in generated[generated.index(f"int {name}("):generated.index(f"int {name}(") + 220]
    assert "leaves the DualShock" in report


def test_platform_leftovers_keep_campaign_and_sound_state_pending():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-platform-leftover-review.md").read_text()
    cache = (ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c").read_text()
    engine = (ROOT / "submodules/halo-ce-universal/source/game/game_engine.c").read_text()
    demos = (ROOT / "submodules/halo-ce-universal/source/interface/marketing_and_strategic_business_development.c").read_text()
    ui = (ROOT / "submodules/halo-ce-universal/source/interface/ui_widget.c").read_text()
    _assert_reviewed(ledger, ("map_share_downloading",), "state-adapter", "hcu-ps2-platform-leftover-review.md")
    _assert_reviewed(ledger, ("map_share_update", "timeout_for_endgame_sound", "xbox_demos_launch"),
                     "excluded-proven", "hcu-ps2-platform-leftover-review.md")
    _assert_reviewed(ledger, (
        "dsound_globals", "pc_menus_screen",
        "ui_set_next_level", "xbox_set_machine_name",
    ), "pending", "hcu-ps2-platform-leftover-review.md")
    assert ledger["symbols"]["reset_last_player1_profile_index"]["disposition"] == "implemented"
    assert "if (map_share_downloading(map_name))" in cache
    assert "timeout_for_endgame_sound = 0;" in engine
    assert 'XLaunchNewImageA("d:\\\\XDemos\\\\XDemos.xbe", &launch_data);' in demos
    assert "main_set_map_name(main_get_solo_level_name(level));" in ui
    assert "event_handler_functions.last_player1_profile_index = NONE;" in (
        ROOT / "submodules/halo-ce-universal/source/interface/ui_widget_event_handler_functions.c").read_text()
    assert "next-level transition" in report


def test_network_client_server_roots_stay_local_until_a_session_exists():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-network-client-server-review.md").read_text()
    engine = (ROOT / "submodules/halo-ce-universal/source/game/game_engine.c").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    game_time = (ROOT / "submodules/halo-ce-universal/source/game/game_time.c").read_text()
    connection = (ROOT / "submodules/halo-ce-universal/source/networking/network_connection.c").read_text()
    _assert_reviewed(ledger, ("global_connection_dont_timeout",), "state-adapter",
                     "hcu-ps2-network-client-server-review.md")
    _assert_reviewed(ledger, (
        "network_game_get_game", "network_game_server_port_cooperative_won",
        "network_game_client_server_has_started_game", "network_test_update",
        "network_voice_update",
    ), "excluded-proven", "hcu-ps2-network-client-server-review.md")
    for name in (
        "create_global_network_game_client", "create_global_network_game_server",
        "dispose_global_network_game_client", "dispose_global_network_game_server",
        "network_game_accept_remote_connections", "network_game_client_request_immediate_start",
        "network_game_server_ban_player", "network_game_server_kick_player",
        "network_game_server_matching_player_names", "network_votekick_matching_player_names",
        "network_votekick_player_named", "network_game_server_get_game",
        "network_game_server_switch_to_postgame", "network_game_server_reset_to_pregame",
    ):
        row = ledger["symbols"][name]
        if "hcu-ps2-batch-" in row["evidence"]:
            assert row["disposition"] in {"implemented", "state-adapter", "excluded-proven"}
        else:
            assert row["disposition"] == "pending"
    friendly = engine[engine.index("short game_engine_friendly_damage("):]
    assert friendly.index("if (network_coop_active())") < friendly.index("network_game_get_game()")
    won = main[main.index("static void main_won_map_private("):main.index("void main_set_map_name(")]
    assert "network_coop_active()" in won
    assert won.index("network_game_server_port_cooperative_won(") < won.index("ui_set_next_level(level);")
    assert "if (game_connection() != _game_connection_network_client)" in game_time
    assert "boolean global_connection_dont_timeout = FALSE;" in connection
    assert "if (global_connection_dont_timeout)" in connection
    assert "fast_setup_network_server" in report


def test_render_submission_roots_remain_pending():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    report = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-render-submission-review.md").read_text()
    main = (ROOT / "submodules/halo-ce-universal/source/main/main.c").read_text()
    game_state = (ROOT / "submodules/halo-ce-universal/source/saved games/game_state.c").read_text()
    weapons = (ROOT / "submodules/halo-ce-universal/source/interface/first_person_weapons.c").read_text()
    pal = (ROOT / "submodules/halo-ce-universal/port/linux/game/pal_tags.c").read_text()
    names = (
        "rasterizer_set_vblank_callback", "rasterizer_preinitialize__fill_you_up_with_the_devils_cock",
        "rasterizer_model_begin", "rasterizer_model_draw", "rasterizer_model_end",
        "rasterizer_model_transparent_geometry_submit", "rasterizer_models_begin",
        "rasterizer_models_end", "rasterizer_profile_enable",
        "rasterizer_widget_begin", "rasterizer_widget_batch_sprites",
        "rasterizer_decal_vertices_new", "rasterizer_decal_vertices_lock",
        "rasterizer_decal_vertices_unlock", "rasterizer_decal_vertices_delete",
        "rasterizer_decals_initialize", "rasterizer_decals_dispose",
        "rasterizer_decals_initialize_for_new_map", "rasterizer_decals_dispose_from_old_map",
        "rasterizer_decals_flush", "rasterizer_decals_update_function_pointers",
        "rasterizer_bitmap_delete",
        "rasterizer_screen_effect_set_convolution", "rasterizer_screen_effect_set_filter",
        "rasterizer_screen_effect_set_filter_desaturation_tint", "rasterizer_screen_effect_set_video",
        "rasterizer_screen_effect_start", "rasterizer_screen_effect_stop",
        "rasterizer_screen_effects_initialize_for_new_map", "rasterizer_script_screen_effect_set_value",
        "rasterizer_fps_accumulate",
        "structure_bsp_header_register_vertex_buffers", "structure_bsp_header_deregister_vertex_buffers",
        "tags_header_register_vertex_and_index_buffers", "tags_header_deregister_vertex_and_index_buffers",
        "progress_bar_initialize", "progress_bar_dispose", "first_person_legs_reset",
        "pal_tags_first_person_advance", "pal_tags_first_person_frames",
    )
    _assert_reviewed(ledger, names, "pending", "hcu-ps2-render-submission-review.md")
    assert "render_frame(" in main
    assert "rasterizer_set_vblank_callback(main_vertical_blank_interrupt_handler);" in main
    assert "rasterizer_decals_update_function_pointers," in game_state
    advance = weapons[weapons.index("if (!pal_tags_first_person_advance("):]
    assert "animation_update_render_only(" in advance
    assert "return TRUE;" in pal[pal.index("boolean pal_tags_first_person_advance("):]
    assert "generated FALSE" in report


def test_post_split_closure_externals_are_reviewed():
    ledger = json.loads((ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json").read_text())
    review = (ROOT / "docs/hcu-source-backed-review/hcu-ps2-post-split-external-review.md").read_text()
    edge = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
    memory = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_memory.c").read_text()
    profile = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_local_profile.c").read_text()
    raster = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_rasterizer.c").read_text()
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    symbols = ledger["symbols"]
    assert symbols
    assert all(row["disposition"] in {"implemented", "state-adapter", "excluded-proven"} for row in symbols.values())
    assert all(row["owner"] and row["reason"] and row["evidence"] and row["test"] for row in symbols.values())
    notes = [name for name in symbols if name.startswith("network_coop_note_")]
    assert len(notes) == 15
    assert "GetTimerSystemTime" not in generated
    assert "void telnet_console_process(void) {  }" in generated
    assert symbols["telnet_console_process"]["disposition"] == "excluded-proven"
    assert "return NULL;" in edge[edge.index("void *__stdcall CreateThread("):]
    assert "copy = old_bytes < size ? old_bytes : size;" in memory
    assert "boolean game_in_editor(void)" in profile
    assert "return FALSE;" in raster[raster.index("boolean rasterizer_transparent_geometry_is_enclosure("):]
    assert "`GetTimerSystemTime`" in review
    assert "`telnet_console_process`" in review
