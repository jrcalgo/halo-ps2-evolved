# M0 source review: network session frame and abort hooks

## Scope

This review covers five rooted interfaces: `network_game_abort`, `network_game_client_start_frame`, `network_game_client_end_frame`, `network_game_server_start_frame`, and `network_game_server_update_ticks`. They remain pending. The PS2 M1 product profile is local-game, but the CE call sites and state transitions show these are not interchangeable generic no-op callbacks.

## Findings

In `source/main/main.c:3583-3605`, start-frame services are selected by the active connection. A network client calls `network_game_client_start_frame`; a network server calls the client frame service and then `network_game_server_start_frame`. A failed client/server service emits CE error state and requests `network_game_abort`. In the local branch none of these start-frame functions is called. This is a viable exclusion boundary only if HCU startup and all menu/new-game transitions hold `main_globals.connection == _game_connection_local` for the product path; the generated return value does not enforce that invariant.

`network_game_client_start_frame` in `source/networking/network_game_globals.c:485-573` polls client state, reports searching/joining/pregame/ingame/postgame transitions, handles the client-started teardown path, and changes connection/menu state on error. It is only safe to omit while the CE main loop cannot select a network connection.

`network_game_client_end_frame` is called from `source/main/main.c:3645-3651` only for connection values above local through network-server. The implementation (`network_game_globals.c:588-680`) sends client update messages in the ingame state; when no client object exists it repairs local player queues and resets connection state. Thus its reachability invariant and “client absent” fallback deserve separate treatment.

`network_game_server_start_frame` runs only in the server branch. Its caller treats a false result as a host-down error. A generated false body is therefore not a harmless substitute if any path can enter server connection mode.

`network_game_server_update_ticks` is selected in `source/game/game_time.c:450-458` only for `_game_connection_network_server`, while local mode uses `update_client_local_ticks`. The implementation in `source/networking/network_server_manager.c:2525-2585` releases map fetchers and emits update messages/tick numbers. It is outside local play only under the same connection invariant.

The related `network_game_abort` has a second caller in the local game-engine postgame path (`source/game/game_engine.c:5225-5238`). Its implementation at `network_game_globals.c:747-751` sets `client_started`; the next client-start-frame call consumes that flag to reset connection state, dispose client/server state, and return to the main menu. Although that second transition is normally relevant to a network session, it means the function's persistent state and postgame caller cannot be ruled out solely from the main-loop network failure path.

## Required M0 evidence

Keep the five ledger rows pending until an integrated local startup/menu/game/postgame fixture proves the selected connection remains local and checks the postgame abort input cannot poison a subsequent local map start. If networking becomes in-scope, implement the actual client/server owner rather than broadening a constant adapter. The regression-integrity test added with this report verifies source anchors and pending dispositions; it does not claim to exercise live network behavior.
