# Step 8 multiplayer workload fixture feasibility

Date: 2026-10-22  
Decision: the existing map-capacity diagnostic cannot yet be promoted into a multiplayer workload/high-water fixture by adding counters alone. Its current control flow deliberately stops before CE map-game initialization and simulation. The real CE entry points are known, but the diagnostic profile lacks a test-only bridge to them and no explicit bot-spawn workload is wired in. Keep Step 8 open; do not change any pool size or production owner budget from this inspection.

## Exact current boundary

The target diagnostic runs after global `game_initialize()` and connection setup ([`main.c:3461-3477`](../../submodules/halo-ce-universal/source/main/main.c#L3461)). That global initializer does create the fixed CE owners once—objects, players, particles/effects, and AI among them ([`game.c:281-325`](../../submodules/halo-ce-universal/source/game/game.c#L281)). The opt-in hook then calls the lifecycle test, and the UI diagnostic profile intentionally enters an infinite loop rather than the ordinary main/game frame loop.

Inside that hook, the current 13-map test preflights and calls `scenario_load()` directly, reads PVS/collision, then calls `scenario_unload()` ([`ps2_m2_ui_lifecycle_test.c:52-63`](../../submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c#L52), [`:76-141`](../../submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c#L76)). It does **not** call `game_initialize_for_new_map()`, create local player datums, call `objects_place()`/`ai_place()`, or run a game tick. Its completion marker is explicitly `query_only=1`. Therefore it measures map/tag/BSP owners and selected query state, not live object, player, weapon, projectile, effect, or bot occupancy.

## CE source path available for a future fixture

The normal path is concrete: `main_new_map()` in `main.c` calls `game_load()`, then `game_initialize_for_new_map()`, creates local players, starts game time, and issues an initial pulse ([`main.c:1478-1505`](../../submodules/halo-ce-universal/source/main/main.c#L1478)). It is `static`, so the separate test translation unit cannot call it today. During `game_initialize_for_new_map()`, CE initializes per-map subsystems, marks the game active, places scenario objects, and calls `ai_place()` ([`game.c:663-729`](../../submodules/halo-ce-universal/source/game/game.c#L663)). `ai_place()` delegates to `encounters_create_for_new_map()`, which iterates scenario-authored encounters and creates those not marked “not initially created” ([`ai.c:548-553`](../../submodules/halo-ce-universal/source/ai/ai.c#L548), [`encounters.c:1730-1753`](../../submodules/halo-ce-universal/source/ai/encounters.c#L1730)). This can measure actual scenario placement/AI work; it does not by itself create an arbitrary configured MP bot population.

Player control is also not equivalent to setting a counter. The CE `create_local_players()` helper is static and assigns each local player a controller before calling `player_new()` ([`main.c:792-867`](../../submodules/halo-ce-universal/source/main/main.c#L792)). CE has four local-player slots ([`players.h:20-26`](../../submodules/halo-ce-universal/source/game/players.h#L20)); the UI co-op initializer chooses two ([`ui_widget_event_handler_functions.c:2039-2045`](../../submodules/halo-ce-universal/source/interface/ui_widget_event_handler_functions.c#L2039)), while the split-screen path creates the local network server/client and changes connection mode ([`ui_widget_event_handler_functions.c:2632-2659`](../../submodules/halo-ce-universal/source/interface/ui_widget_event_handler_functions.c#L2632)). The PS2 `ps2_coop.c` extension intentionally reports network co-op inactive; it preserves the ordinary local CE path, not network co-op behavior ([header/source](../../submodules/halo-ce-universal/port/ps2/game/ps2_coop.c#L1)). These distinctions must be reflected in a test label: 4 CE player records, 4 active local controllers, split-screen rendering, local two-player co-op, and network co-op are different claims.

The test-only path should therefore be a separate `STEP8_MP_WORKLOAD` profile—not an extension of the query-only marker—with a small bridge in `main.c` to invoke the real `main_new_map()` path. It must explicitly set and verify the selected connection/player mode, populate local player records through CE's helper, run deterministic frame/tick inputs, snapshot the already opt-in game-state/object-pool counters plus the distinct compatibility-malloc counters, and use normal per-map teardown before checking current usage/guards. The player fixture must assert spawned player/unit counts rather than trusting `player_spawn_count` alone. Object/weapon/effect churn must exercise the real CE calls and source tags; constructing arbitrary pool records by hand would not establish gameplay ownership.

**Bot gate:** the source path found here creates map-authored AI encounters via `ai_place()`; it does not expose a diagnostic “spawn N multiplayer bots” call. The PS2 co-op adapter disables network-co-op extension state, and the candidate diagnostic does not exercise it. Before calling a fixture a bot test, define whether a bot is (a) a scenario-authored AI biped, (b) a new synthetic MP bot, or (c) a network-co-op remote player. Then implement or identify the genuine CE spawn path, assert live actor/player counts, and account its weapon/effect/projectile load. Do not turn the scenario encounter loop into a claimed configurable bot population.

## Capacity/evidence implications

The measured candidate layout remains a test-only 10 MiB map+texture recarve, not a gameplay budget or a new owner allocation. HCU's current game-state diagnostic reports its fixed CPU cursor; the CE object payload pool is nested in that cursor, and the PS2 compatibility arena is separate. The 32 MiB budget already assigns fixed capacities, including 3,162,112 B game-state CPU, 1,048,576 B object payload pool within that backing, and 2,621,440 B dynamic simulation; don't resize or double-charge these owners to make a fixture pass ([PS2 constants](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L18), [budget](../../config/memory-budget.json#L1), [owner telemetry report](m2-step8-game-state-object-pool-telemetry-2026-10-22.md#L1)). Retained tag/model/texture sections, decode/source overlap, DMA staging and GS residency are still separate owners/lifetimes.

Existing evidence classes remain narrower:

- The provider-bound host matrix performs 13-map load/query/unload and selected section loading, not a match simulation ([rerun report](mp-step8-provider-bound-combined-rerun-2026-10-22.md#L1)).
- PCSX2 Blood Gulch and Sidewinder probes load/query/unload one map at a time; Sidewinder's measured BSP margin is 24 B. Their `query_only=1` completion is not a player, renderer, AI, weapon, or effect workload ([Blood Gulch](step8-mp-bloodgulch-pcsx2-query-2026-10-22.md#L1), [Sidewinder](step8-mp-sidewinder-pcsx2-query-2026-10-22.md#L1)).
- The all-13 content closure inventories tag references and offline converted sections; its own interpretation limits say bot count, effect peak, DMA staging and simultaneous runtime residency are not measured ([content closure](m2-step8-mp-match-time-content-closure-2026-10-22.md#L1)).
- halo-ps2's “no heap after load” arenas/fixed pools describe its distinct converted-pack engine ([`03-engine-architecture.md`](../../submodules/halo-ps2/docs/03-engine-architecture.md#L90)). Halo-64 demonstrates why real target pressure measurements matter, but N64 arena cuts/update throttles are not HCU PS2 policy.

## Build check and limits

Ran `python3 tools/hcu_parent_link_probe.py --step8-mp-capacity-diagnostic`. The R5900 build linked with zero undefined imports; the linked gameplay machine is SHA-256 `beee81293b9059ca2f51c04e6b49897e607e332750fe7f14fa201c2077258bf0`, and its memory-audit JSON is `a72f7632c7afa9bdb5ec5688b25d1f56926961f46feeb0191c9475f579159876`. The report remains `acceptance=false`; it explicitly states that no guest execution/map transaction was observed and only the UI/bootstrap callback is implemented. The separate earlier PCSX2 query reports are not reruns of a gameplay workload. No new PCSX2 gameplay run was made because no workload path was added.

Next implementation order: (1) add the isolated workload profile and a test-only bridge to CE `main_new_map()`; (2) first run one map/one local player and prove player/unit spawn, object placement, simulation ticks, per-owner snapshots, unload/reset and canaries; (3) extend to the actual supported local-player modes and 13 maps; (4) only then define and exercise a genuine bot workload, including asset closure, and run both PCSX2 CPU modes plus retail R5900. Keep all HCU capacities, guards and the 5,767,168-byte reserve unchanged until measured evidence justifies a separately reviewed budget change. This memo establishes feasibility boundaries only; Step 8 remains open.

## Evidence identity

The current inspected source hashes are:

| File | SHA-256 |
|---|---|
| [`ps2_m2_ui_lifecycle_test.c`](../../submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c) | `cfe4d4bfb5afa3bda46e955be762d590968f0de787666b684a682f517558c956` |
| [`main.c`](../../submodules/halo-ce-universal/source/main/main.c) | `dc5951b3282e9d71311aa553eed89a233e0303b77d6a4c04107299be985f4ab0` |
| [`game.c`](../../submodules/halo-ce-universal/source/game/game.c) | `941e187aa0bfb1278cab7c5a94ae688808f702742d68e92802e7489a491a2dad` |
| [`ai.c`](../../submodules/halo-ce-universal/source/ai/ai.c) | `9049813558d719d56017a7db70f7a4bf7561fabba89674ecdc42d7b3ad5d0e3c` |
| [`encounters.c`](../../submodules/halo-ce-universal/source/ai/encounters.c) | `5463fcb9d7e7e313b286c37a630ea228936019c12daaef1293f08bce323ac5e8` |
| [`ps2_coop.c`](../../submodules/halo-ce-universal/port/ps2/game/ps2_coop.c) | `0af40aada57653f2cc99f4c239d46eaa5f774bc57ca51b79e33b950bdd9a3639` |
| [`hcu_parent_link_probe.py`](../../tools/hcu_parent_link_probe.py) | `2067a4a150d9bd9d226f3926a06a87a9975c35a9b02abbb93a94e607b399a9a1` |

No source/test code was changed for this feasibility slice. The R5900 build artifact is a linked diagnostic only; no claim of 4-player, bot, co-op, playable-map, renderer residency, or capacity acceptance follows.
