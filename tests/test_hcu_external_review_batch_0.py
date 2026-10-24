import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "docs/hcu-source-backed-review/batches/batch-0.json"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-0-skip.txt"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-0-review.md"
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"
class _PortC:
    def read_text(self):
        root = ROOT / "submodules/halo-ce-universal/port/ps2/src"
        return "\n".join(path.read_text() for path in sorted(root.glob("ps2_*.c")))

BATCH_C = _PortC()
EDGE = ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c"
CACHE = ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_cache.c"
THREAD = ROOT / "submodules/halo-ce-universal/source/bungie_net/common/thread_win32.c"
FILES = ROOT / "submodules/halo-ce-universal/source/tag_files/files_windows.c"
SAVES = ROOT / "submodules/halo-ce-universal/source/saved games/saved_game_files.c"
GAME_STATE = ROOT / "submodules/halo-ce-universal/source/saved games/game_state_xbox.c"
DEBUG_MEMORY = ROOT / "submodules/halo-ce-universal/source/cseries/debug_memory.c"
MAIN = ROOT / "submodules/halo-ce-universal/source/main/main.c"
CACHE_FILES = ROOT / "submodules/halo-ce-universal/source/cache/cache_files.c"
CACHE_H = ROOT / "submodules/halo-ce-universal/source/cache/cache_files.h"
HAT = ROOT / "submodules/halo-ce-universal/source/input/HaloAutoTest.c"
INPUT = ROOT / "submodules/halo-ce-universal/source/input/input_xbox.c"
PS2_INPUT = ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_input.c"
TEST_ID = (
    "tests/test_hcu_external_review_batch_0.py::"
    "test_batch_0_rooted_symbols_are_dispositioned"
)
ALLOWED = {"implemented", "state-adapter", "excluded-proven"}


def pending_slice():
    return sorted(json.loads(BATCH.read_text()))


def function_body(source, name):
    match = re.search(
        rf"(?m)^(?:[\w*]+\s+)*{re.escape(name)}\s*\([^;{{]*\)\s*\{{",
        source,
    )
    assert match, f"missing definition for {name}"
    start = match.end() - 1
    depth = 0
    index = start
    while index < len(source):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
        index += 1
    raise AssertionError(f"unclosed body for {name}")


def test_batch_0_rooted_symbols_are_dispositioned():
    assigned = json.loads(BATCH.read_text())
    slice_names = pending_slice()
    assert slice_names == sorted(assigned)
    assert len(assigned) == 32

    review = REVIEW.read_text()
    batch_c = BATCH_C.read_text()
    edge = EDGE.read_text()
    cache = CACHE.read_text()
    thread = THREAD.read_text()
    files = FILES.read_text()
    saves = SAVES.read_text()
    game_state = GAME_STATE.read_text()
    debug_memory = DEBUG_MEMORY.read_text()
    main = MAIN.read_text()
    cache_files = CACHE_FILES.read_text()
    cache_h = CACHE_H.read_text()
    hat = HAT.read_text()
    input_xbox = INPUT.read_text()
    ps2_input = PS2_INPUT.read_text()
    skip = [line.strip() for line in SKIP.read_text().splitlines() if line.strip()]

    assert skip == [
        "CreateThread",
        "DeleteFileA",
        "GlobalMemoryStatus",
        "GlobalReAlloc",
        "SetEndOfFile",
        "Sleep",
        "WriteFile",
        "XCalculateSignatureBegin",
        "XCalculateSignatureEnd",
        "XCalculateSignatureUpdate",
        "XCreateSaveGame",
        "XDeleteSaveGame",
    ]
    for name in skip:
        body = function_body(batch_c, name)
        assert "memset(&result, 0, sizeof(result)); return result;" not in body
        assert body.strip() != "{}"

    contracts = {
        "CloseHandle": (edge, "ps2_file_handle_get(opaque)", "DeleteSema"),
        "CreateDirectoryA": (edge, "ERROR_ACCESS_DENIED", "return 0;"),
        "CreateFileA": (edge, "GENERIC_READ", "OPEN_EXISTING"),
        "CreateMutexA": (edge, "CreateSema", "initial_owner"),
        "CreateThread": (batch_c, "ERROR_NOT_ENOUGH_MEMORY", "return NULL;"),
        "DeleteFileA": (batch_c, "ps2_m0_deny_mutation", "ERROR_ACCESS_DENIED"),
        "FindFirstFileA": (edge, "ERROR_FILE_NOT_FOUND", "INVALID_HANDLE_VALUE"),
        "FindNextFileA": (edge, "ERROR_NO_MORE_FILES", "return 0;"),
        "GetFileAttributesA": (edge, "hcu_file_bridge_stat", "FILE_ATTRIBUTE_DIRECTORY"),
        "GetFileAttributesExA": (edge, "nFileSizeLow", "nFileSizeHigh"),
        "GetFileSize": (edge, "hcu_file_bridge_size", "INVALID_FILE_SIZE"),
        "GetLastError": (edge, "return ps2_last_error;", "static unsigned long ps2_last_error"),
        "GlobalMemoryStatus": (batch_c, "dwAvailPhys", "PS2_M0_EE_RAM_BYTES"),
        "GlobalReAlloc": (batch_c, "PS2_M0_DEBUG_SIZE_OFFSET", "old_bytes < size"),
        "ReadFile": (edge, "hcu_file_bridge_read", "bytes_read"),
        "ReleaseMutex": (edge, "SignalSema", "PS2_MUTEX_MAGIC"),
        "SetEndOfFile": (batch_c, "ps2_m0_deny_mutation", "ERROR_ACCESS_DENIED"),
        "SetFilePointer": (edge, "hcu_file_bridge_seek", "FILE_END"),
        "SetLastError": (edge, "ps2_last_error = code;", "void __stdcall SetLastError"),
        "Sleep": (batch_c, "GetTimerSystemTime()", "MSec2TimerBusClock"),
        "WaitForSingleObject": (edge, "WaitSemaEx", "PS2_WAIT_OBJECT_0"),
        "WriteFile": (batch_c, "*bytes_written = 0", "ps2_m0_deny_mutation"),
        "XCalculateSignatureBegin": (batch_c, "INVALID_HANDLE_VALUE", "ERROR_ACCESS_DENIED"),
        "XCalculateSignatureEnd": (batch_c, "ERROR_INVALID_HANDLE", "return ERROR_INVALID_HANDLE;"),
        "XCalculateSignatureUpdate": (batch_c, "ERROR_INVALID_HANDLE", "return ERROR_INVALID_HANDLE;"),
        "XCreateSaveGame": (batch_c, "ERROR_ACCESS_DENIED", "return ERROR_ACCESS_DENIED;"),
        "XDeleteSaveGame": (batch_c, "ERROR_ACCESS_DENIED", "return ERROR_ACCESS_DENIED;"),
    }
    gates = {
        "CopyFileA": (saves, 'if (!XCreateSaveGame(', "CopyFileA(file.path, new_path, TRUE)"),
        "GetExitCodeThread": (thread, "GetExitCodeThread(thread_reference->handle, &exit_code)", "CreateThread("),
        "ResumeThread": (thread, "ResumeThread(reference->handle)!=-1", "CreateThread("),
        "SetThreadPriority": (thread, "SetThreadPriority(reference->handle, priority)", "CreateThread("),
        "SwitchToThread": (cache_files, "while (!read_complete)", "SwitchToThread();"),
    }

    for name, row in assigned.items():
        assert row["disposition"] in ALLOWED, name
        assert row["owner"].strip(), name
        assert row["reason"].strip(), name
        assert row["evidence"].strip(), name
        assert "hcu-ps2-batch-0-review.md" in row["evidence"], name
        assert row["test"] == TEST_ID, name
        assert name in review, name
        if name in contracts:
            source, first, second = contracts[name]
            assert first in source, name
            assert second in source, name
            if name in skip:
                body = function_body(batch_c, name)
                assert first in body or second in body, name
        else:
            source, first, second = gates[name]
            assert first in source, name
            assert second in source, name

    assert "desired_access != GENERIC_READ || creation_disposition != OPEN_EXISTING" in edge
    assert "INVALID_HANDLE_VALUE" in hat or 'GetFileAttributesA("d:\\\\write.xts")' in hat
    assert 'GetFileAttributesA("d:\\\\write.xts")' in hat
    assert "file_open = TRUE" in game_state
    assert "HALO_PS2" in game_state
    assert "*size = attribute_data.nFileSizeLow" in files
    assert "dwAvailPhys" in debug_memory
    assert "Sleep(33 - milliseconds_elapsed)" in main
    assert "Sleep(1);" in main
    assert "_cache_file_read_failed = 2" in cache_h
    assert "*completion_flag_reference = _cache_file_read_failed" in cache
    assert "GetLastError()" in input_xbox
    assert "SetLastError(ERROR_DEVICE_NOT_CONNECTED)" in ps2_input
    assert "signature != INVALID_HANDLE_VALUE" in saves
    assert "if (XCalculateSignatureUpdate(signature, buffer, buffer_size))" in saves
    assert "XDeleteSaveGame(" in saves
    create_thread = function_body(thread, "create_thread")
    assert "CREATE_SUSPENDED" in create_thread
    assert "SetThreadPriority(reference->handle, priority)" in create_thread
    realloc = function_body(batch_c, "GlobalReAlloc")
    assert "for (index = 0; index < copy; index++)" in realloc
    assert "for (i = 0; i < size; i++)" not in realloc
