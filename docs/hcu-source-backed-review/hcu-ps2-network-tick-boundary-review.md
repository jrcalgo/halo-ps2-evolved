# M0 source review: distributed-network helpers on the local tick path

## Scope and disposition

This pass reviewed six rooted symbols: `network_game_distributed_client`, `network_distributed_tick`, `network_distributed_new_game`, `network_distributed_player_killed`, `network_distributed_player_picked_up`, and `distributed_player_to_byte`. They remain **pending**. The names/classification `excluded-feature` do not prove that their generated bodies are harmless: several are called inside authoritative gameplay paths, and some call sites are unconditional for local play. No online feature is implemented by this review.

## Source findings

`network_game_distributed_client` has a real CE implementation in `source/networking/network_game_globals.c:297-301`: it tests whether `game_connection()` is `_game_connection_network_client`. It is a gameplay policy predicate, not merely a networking subsystem query. The rooted closure calls it from AI object placement, unit updates, damage/shield updates, pickup decisions, game-time handling, cheat enforcement, camera selection, and all major objective/score engines. Representative branches include `source/objects/damage.c:160` (`objects_update_shields`), `source/game/players.c:313` (`players_decide_pickups`), CTF in `source/game/game_engine_ctf.c:582`, Slayer in `source/game/game_engine_slayer.c:480`, and the distributed time branch in `source/game/game_time.c:295`. Returning false is correct only while the HCU connection is demonstrably local; if the platform ever selects a client connection, a constant false silently changes authority, shields, pickups, and game-mode logic.

`network_distributed_tick` is invoked after each simulated tick in `source/game/game_time.c:486`, after both `server_time` and `local_time` advance. The source comment calls it distributed-netcode per-tick state, but its current call is unconditional. The selected source tree does not provide its body. Therefore “networking excluded” alone is insufficient to approve the no-op: a local replay/tick test must show the hook is not needed for local state or explicitly guard it by connection mode.

`network_distributed_new_game` is declared at `source/game/game.c:647` and called in the new-map initialization path. Its implementation is absent from the selected source tree. Before approval, a two-map local lifecycle test must check that omission does not retain any distributed state from a prior session/map.

`network_distributed_player_killed` is called from `game_engine_player_killed` with killing-player and killing-object identity (`source/game/game_engine.c:600`). The selected tree has the declaration/call but not its body. The surrounding CE kill path must be traced through score, attribution, and respawn mutation before considering the no-op proven.

`network_distributed_player_picked_up` is called in `source/game/players.c:284-286` around equipment handling and before/after-game player updates. The likely remote-notification interpretation is not enough to approve it; the local path must prove inventory counts, pickup consumption, and equipment state are committed independently.

`distributed_player_to_byte` is called by CTF and Oddball objective/weapon code. It encodes a player identity, so an empty/zero mapping could conflate the local player with “none” or another player. A future local objective fixture needs explicit encode/decode expectations before disposition.

## M0 consequence and required follow-up

Keep these six rows pending in `docs/hcu-ps2-external-review.json`. The current local-only startup boundary needs a test that asserts the connection remains `_game_connection_local`, and then exercises a fixed local tick, death/kill attribution, pickup, and objective identity with the generated platform layer. Until such fixtures exist, do not turn these roots into `excluded-proven` based on classification. Future PS2 networking work must replace or conditionally enable the adapter rather than inherit a constant local value.

The ledger regression test checks that all six rows stay source-annotated and pending, and that the source paths cited above remain in the checkout. This is a review-integrity test, not a behavioral acceptance test for game networking.
