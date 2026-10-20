# CE roots from `localtime` through `network_votekick_matching_player_names`

Status: the pending slice `[96:128]` is closed. `localtime` and `memcpy` keep their pinned Newlib owners. The main-menu flag, the new-map queue reset, and the local connection predicate are implemented from CE. Generated zeros that would abort a missing session, inject PC-menu or mod tags, or invent a host game record are replaced by the minimum contracts in `port/ps2/src/ps2_m0_batch_3.c`. `main_screen_shell_begin_fade` is unreachable while `ui_main_menu_music_active` is the false M1 adapter.

## Evidence and boundary

`source/interface/ui_widget.c` and `source/networking/` are excluded from the PS2 manifest (`port/ps2/port.json:39-61`). The rooted image still calls the menu flag, the menu shell, the Linux-port tag hooks, and the distributed-netcode helpers. `port/ps2/game/ps2_local.c` already returns a null server and client. `main_setup_connection` writes `_game_connection_local` (`source/main/main.c:2861`). HaloScript can still name the setup, ban, kick, and start commands.

The generated bodies in `build/hcu-ps2-closure/all/ps2_platform.c` are empty voids or `memset`-zero returns. Those zeros change player spawn when `main_menu_is_active` stays false, skip `update_queues_distributed_reset` on a new map, and treat `network_game_client_start_frame` as a failed host.

## Disposition rationale

| Root | Caller file:line | Effect | Disposition |
|---|---|---|---|
| `localtime` | `source/cseries/errors.c:162` | Formats the error-log prefix. NULL already becomes `"<TIME UNAVAILABLE>"`. | `implemented` — Newlib `libc_a-lcltime.o` |
| `main_menu_active` | `source/main/main.c:1122,1546,1952` | Writes `we_are_at_the_main_menu`. | `implemented` |
| `main_menu_is_active` | `source/input/input_abstraction.c:768`; `source/game/player_queues_new.c:951`; `source/game/players.c:4824` | Controller-unplug policy, queue errors, and local spawn. | `implemented` |
| `main_screen_shell_begin_fade` | `source/main/main.c:1519-1523` | Only runs when `ui_main_menu_music_active()` is TRUE. | `excluded-proven` |
| `main_screen_shell_load` | `source/main/main.c:1132` | First load resets the controller-detection timer. Bink and widget roots stay excluded. | `state-adapter` |
| `memcpy` | `source/cseries/cseries.c:605` plus implicit struct copies | Newlib copy; overlap is undefined. `csmemcpy` asserts non-overlap. | `implemented` — Newlib `libc_a-memcpy.o` |
| `menu_tags_loaded` / `menu_tags_unloaded` | `source/cache/cache_files.c:1245,1347,641` | Linux PC-menu injection. Xbox CE does not grow the tag table. | `state-adapter` |
| `mods_tags_loaded` / `mods_tags_unloaded` | `source/cache/cache_files.c:1251,1362,633` | Linux resource-pack apply/release. No PS2 provider, so no pointers to drop. | `state-adapter` |
| `mods_enable` / `mods_reload` / `mods_list` | `source/hs/hs.c:11711-11713` | Script-visible. Empty list must not invent an empty mods folder. | `state-adapter` |
| `network_distributed_new_game` | `source/game/game.c:679` | Linux clears port tables and calls `update_queues_distributed_reset`. Local play still uses those latch bits. | `implemented` |
| `network_distributed_player_killed` | `source/game/game_engine.c:5001` | Linux rewrites killer identity only for a client or server. Local bookkeeping stays in the caller. | `state-adapter` |
| `network_distributed_player_picked_up` | `source/game/players.c:306` | Linux records a pickup only on a server. The macro also skips local players. | `state-adapter` |
| `network_distributed_tick` | `source/game/game_time.c:486` | Unconditional call. Linux sends or applies remote state only for a client or server. | `state-adapter` |
| `network_game_distributed_client` | 28 gameplay sections | CE is `game_connection() == _game_connection_network_client`. | `implemented` |
| `network_game_abort` | `source/game/game_engine.c:5237` | Postgame B sets `client_started`. | `implemented` |
| `network_game_accept_remote_connections` | `source/interface/player_ui.c:672,682` | CE stores the accept flag. Widget load and server create already fail on PS2. | `implemented` |
| `network_game_client_start_frame` / `network_game_client_end_frame` | `source/main/main.c:3586,3595,3647` | Gated on a network connection. Generated FALSE would display a host-down error. The no-client CE branch returns TRUE. | `state-adapter` |
| `network_game_client_request_immediate_start` | `source/hs/hs.c:14230` | CE writes a start-time change only when a client object exists. | `state-adapter` |
| `network_game_server_start_frame` | `source/main/main.c:3601` | CE returns TRUE when no server object exists. Generated FALSE would abort. | `state-adapter` |
| `network_game_server_update_ticks` | `source/game/game_time.c:458` | Only the network-server `game_time_update` case. Local uses `update_client_local_ticks`. | `state-adapter` |
| `network_game_server_get_game` | `source/game/game_engine.c:5072` | Caller already null-checks `global_network_game_server_get()`. | `state-adapter` |
| `network_game_server_ban_player` / `network_game_server_kick_player` | `source/hs/hs.c:15489` | No host. FALSE is a failed command, not success. | `state-adapter` |
| `network_game_server_matching_player_names` / `network_votekick_matching_player_names` | `source/main/console.c:322-324` | CE returns 0 with no server or no votekick. | `state-adapter` |
| `network_game_server_reset_to_pregame` / `network_game_server_switch_to_postgame` | `source/game/game_engine.c:5231-5233,4911-4913` | Both run only when a server pointer exists. | `state-adapter` |

Re-open the menu-shell adapter before restoring CE widgets, Bink intro, or menu music. Re-open the network adapters before any client or server connection. Re-open the mod and menu-tag adapters before a resource-pack or PC-menu provider.

## Regression

`tests/test_hcu_external_review_batch_3.py::test_batch_3_rooted_symbols_are_dispositioned` checks the slice membership, every disposition field, the skip list against `ps2_m0_batch_3.c`, and one real source snippet for each approved contract.

## Sources

- `submodules/halo-ce-universal/source/main/main.c:1122,1132,1519-1523,1546,1952,2861,3583-3605,3647`
- `submodules/halo-ce-universal/source/interface/ui_widget.c:1940-1952,3001-3024,4909-4963`
- `submodules/halo-ce-universal/source/input/input_abstraction.c:768`
- `submodules/halo-ce-universal/source/game/player_queues_new.c:951-963,976-982`
- `submodules/halo-ce-universal/source/game/players.c:306,4824`
- `submodules/halo-ce-universal/source/game/game.c:679`
- `submodules/halo-ce-universal/source/game/game_engine.c:5001,5071-5080,4911-4913,5231-5237`
- `submodules/halo-ce-universal/source/game/game_time.c:452-458,486`
- `submodules/halo-ce-universal/source/cache/cache_files.c:631-641,1243-1362`
- `submodules/halo-ce-universal/source/hs/hs.c:11707-11713,14230,15489`
- `submodules/halo-ce-universal/source/main/console.c:322-324`
- `submodules/halo-ce-universal/source/cseries/errors.c:161-176`
- `submodules/halo-ce-universal/source/cseries/cseries.c:596-605`
- `submodules/halo-ce-universal/source/networking/network_game_globals.c:297-301,379-384,434-447,521-529,598-601,747-751,763-772`
- `submodules/halo-ce-universal/port/linux/game/network_distributed.c:2919-3025,3293-3370,3373-3438`
- `submodules/halo-ce-universal/port/linux/game/menu_tags.c:2070-2220`
- `submodules/halo-ce-universal/port/linux/game/mods.c:238-400`
- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_3.c`
- `build/hcu-ps2-closure/all/ps2_platform.c`
- `docs/hcu-source-backed-review/hcu-ps2-batch-3-review.md`
- `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
