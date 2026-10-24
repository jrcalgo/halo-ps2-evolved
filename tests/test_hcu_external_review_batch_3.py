import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"
BATCH = ROOT / "docs/hcu-source-backed-review/batches/batch-3.json"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-3-review.md"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-3-skip.txt"
class _PortC:
    def read_text(self):
        return "\n".join(path.read_text() for path in sorted((HCU / "port/ps2/src").glob("ps2_*.c")))

OWNER = _PortC()
TEST_ID = (
    "tests/test_hcu_external_review_batch_3.py"
    "::test_batch_3_rooted_symbols_are_dispositioned"
)
ALLOWED = {"implemented", "state-adapter", "excluded-proven"}
GENERATED_ZERO = "memset(&result, 0, sizeof(result)); return result;"

CONTRACT_SNIPPETS = {
    "localtime": (
        ROOT / "build/toolchain/sources/ps2toolchain_ee_newlib/newlib/libc/time/lcltime.c",
        "return localtime_r (tim_p, (struct tm *)_REENT_TM(reent));",
    ),
    "memcpy": (
        ROOT / "build/toolchain/sources/ps2toolchain_ee_newlib/newlib/libc/string/memcpy.c",
        "If the regions overlap, the behavior is undefined.",
    ),
    "main_menu_active": (OWNER, "we_are_at_the_main_menu = active;"),
    "main_menu_is_active": (OWNER, "return we_are_at_the_main_menu;"),
    "main_screen_shell_load": (
        OWNER, "input_abstraction_reset_controller_detection_timer();"),
    "menu_tags_loaded": (OWNER, "Do not grow the tag table."),
    "menu_tags_unloaded": (OWNER, "Nothing was allocated in menu_tags_loaded."),
    "mods_enable": (OWNER, "No replacement tags to apply or restore."),
    "mods_list": (OWNER, "PS2 has no mod discovery provider"),
    "mods_reload": (
        OWNER, "Do not replace loaded bitmaps, sounds, or models."),
    "mods_tags_loaded": (OWNER, "Leave map tag bytes unchanged."),
    "mods_tags_unloaded": (OWNER, "Nothing was applied in mods_tags_loaded."),
    "network_distributed_new_game": (OWNER, "update_queues_distributed_reset();"),
    "network_distributed_player_killed": (
        OWNER, "Local score stays in game_engine_player_killed."),
    "network_distributed_player_picked_up": (
        OWNER, "returns unless the connection is a server."),
    "network_distributed_tick": (
        OWNER, "applies remote state when the connection is a client or server."),
    "network_game_abort": (OWNER, "client_started = TRUE;"),
    "network_game_accept_remote_connections": (
        OWNER, "accept_remote_connections = accept;"),
    "network_game_client_end_frame": (
        OWNER, "main_menu_ensure_player_queues_exist();"),
    "network_game_client_request_immediate_start": (
        OWNER, "a client object exists."),
    "network_game_client_start_frame": (OWNER, "main_goto_main_menu();"),
    "network_game_distributed_client": (
        OWNER, "return game_connection() == _game_connection_network_client;"),
    "network_game_server_ban_player": (OWNER, "return FALSE;"),
    "network_game_server_get_game": (OWNER, "return NULL;"),
    "network_game_server_kick_player": (OWNER, "return FALSE;"),
    "network_game_server_matching_player_names": (OWNER, "return 0;"),
    "network_game_server_reset_to_pregame": (OWNER, "return FALSE;"),
    "network_game_server_start_frame": (OWNER, "no network game server"),
    "network_game_server_switch_to_postgame": (OWNER, "(void)server;"),
    "network_game_server_update_ticks": (
        OWNER, "uses update_client_local_ticks for a local connection."),
    "network_votekick_matching_player_names": (OWNER, "return 0;"),
}


def pending_slice():
    return list(json.loads(BATCH.read_text()))


def defined_owner_symbols(source):
    names = []
    for match in re.finditer(
            r"^(?:boolean|void|short|struct \w+ \*)\s*(\w+)\s*\(",
            source, re.M):
        names.append(match.group(1))
    return names


def test_batch_3_rooted_symbols_are_dispositioned():
    assigned = pending_slice()
    assert assigned, "pending slice [96:128] must not be empty"
    rows = json.loads(BATCH.read_text())
    review = REVIEW.read_text()
    owner = OWNER.read_text()
    skip = [line for line in SKIP.read_text().splitlines() if line.strip()]
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    main = (HCU / "source/main/main.c").read_text()
    cseries = (HCU / "source/cseries/cseries.c").read_text()
    errors = (HCU / "source/cseries/errors.c").read_text()

    assert list(rows) == assigned
    assert set(skip) <= set(defined_owner_symbols(owner))
    assert GENERATED_ZERO not in owner
    assert "docs/hcu-source-backed-review/hcu-ps2-batch-3-review.md" in review
    assert "main_screen_shell_begin_fade" in review
    assert "if (ui_main_menu_music_active() == TRUE)" in main
    assert "main_screen_shell_begin_fade(1000);" in main
    assert main.index("if (ui_main_menu_music_active() == TRUE)") < main.index(
        "main_screen_shell_begin_fade(1000);")
    assert "return memcpy(destination, source, size);" in cseries
    assert "localtime(&timeptr)" in errors
    assert "libc_a-memcpy.o" in link_map
    assert "libc_a-lcltime.o" in link_map

    for name in assigned:
        row = rows[name]
        assert row["disposition"] in ALLOWED
        assert row["owner"].strip()
        assert row["reason"].strip()
        assert row["evidence"].strip()
        assert row["test"] == TEST_ID
        assert "hcu-ps2-batch-3-review.md" in row["evidence"]
        assert name in review
        if name == "main_screen_shell_begin_fade":
            assert row["disposition"] == "excluded-proven"
            assert name not in skip
            continue
        if name in {"localtime", "memcpy"}:
            assert row["disposition"] == "implemented"
            assert name not in skip
            path, snippet = CONTRACT_SNIPPETS[name]
            assert snippet in path.read_text()
            continue
        assert name in skip
        assert row["disposition"] in {"implemented", "state-adapter"}
        path, snippet = CONTRACT_SNIPPETS[name]
        assert snippet in path.read_text()
        match = re.search(
            rf"\b{re.escape(name)}\s*\([^{{]*\)\s*\{{",
            owner)
        assert match, f"owner must define {name}"
