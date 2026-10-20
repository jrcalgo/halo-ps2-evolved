# Network client and server roots

Status: the don't-timeout default, the co-op game pointer, the co-op level-won call, the client time-hold query, and the port test/voice updates are closed for the current local profile. Script-reachable server setup and postgame transitions stay pending.

The local connection is not a network client or server. `network_coop_active()` is already the false local adapter. A call that the compiler still emits is not approved unless every live caller is inside one of those predicates. HaloScript can still invoke several of these names, so a local boot is not proof that the function is unreachable.

## Closed rows

`global_connection_dont_timeout` is the boolean at `source/networking/network_connection.c:337`, initialized FALSE. The rooted section `.data.global_connection_dont_timeout_definition` is the HaloScript global that points at it (`source/hs/hs_globals_external.c:1942`). `network_connection_idle` refreshes the keep-alive instead of dropping the connection only when the flag is true (`network_connection.c:1659-1665`). The generated object is a zero `boolean`, which is that FALSE default. A script can set it later; the initial value matches CE.

`network_game_get_game` is called from `game_engine_friendly_damage` only inside `network_coop_active()` (`source/game/game_engine.c:7667-7669`) and from `main_won_map_private` only inside `game_connection() == network_server && network_coop_active()` (`source/main/main.c:2388-2390`). Both are unreachable while the local co-op adapter is false. Re-open with co-op.

`network_game_server_port_cooperative_won` is in that same won-map branch (`main.c:2395-2396`). It does not run for a local campaign win. The local win calls `ui_set_next_level` instead, which is a separate pending row.

`network_game_client_server_has_started_game` is reached from `game_time_held` only after `game_connection() == network_client` (`source/game/game_time.c:333-341`). The local connection returns FALSE before the call. A false stub would hold time if a client connection were later enabled. Re-open before any client connection.

`network_test_update` and `network_voice_update` are port frame hooks in `main_loop` (`main.c:3576-3579`). Both are void. The loop does not branch on them. They are the Linux automated-test and voice-chat updates, not the CE local tick.

## Pending rows

`player_ui_fast_setup_network_server` is a HaloScript command (`source/hs/hs.c:11512-11518,14228`). It always closes widgets, disposes any server and client, and sets the local connection (`source/interface/player_ui.c:651-657`) before `pc_menus_screen` and `create_global_network_game_server` / `create_global_network_game_client` (`662-685`). The generated creates return false, so the success path that would set `network_server` does not run, and the function reports a failed server. That is not an approval of the dispose calls or of a false create: a script still enters this sequence. Keep these pending:

- `create_global_network_game_client`
- `create_global_network_game_server`
- `dispose_global_network_game_client` (also `main_exit` for a network server, `main.c:2432-2436`)
- `dispose_global_network_game_server`
- `network_game_accept_remote_connections`

`network_game_client_request_immediate_start`, `network_game_server_ban_player`, `network_game_server_kick_player`, and `network_votekick_player_named` are HaloScript evaluators. `network_game_server_matching_player_names` and `network_votekick_matching_player_names` feed console completion. Empty or false results change command behavior. They are not local-boot no-ops.

`network_game_server_switch_to_postgame` runs from `game_engine_update` when `global_network_game_server_get()` is non-NULL (`game_engine.c:4910-4913`). `network_game_server_reset_to_pregame` runs from postgame input under the same getter (`5231-5233`). `network_game_server_get_game` is used after a local team change when that server pointer exists (`5071-5080`). A null stub skips the host record while the local team index was already changed. Keep them pending until the local profile proves the server pointer stays NULL, including after the script setup above.

## Regression

`tests/test_hcu_external_review.py::test_network_client_server_roots_stay_local_until_a_session_exists` checks the co-op and client gates, the FALSE don't-timeout initializer, and the pending script setup names.
