# D20 CE gameplay-oracle first-slice recommendation

Date: 2026-10-21  
Scope: source/build-closure review only. No production source, test source, or milestone plan was changed for this report.

## Recommendation

The smallest useful *executable* next slice is a new host-only test target that performs the real CE process initialization and the real `game_load("levels\\d20\\d20")` transition, then unloads cleanly. It should be separate from `test_hcu_ce_d20_oracle.py`, retain that passing scenario/BSP oracle unchanged, and use explicit host-owned memory and machine-service adapters. It must not jump directly from the current `scenario_load()` fixture into `game_initialize_for_new_map()` or hand-build CE globals: `game_initialize()` is a large ordered initializer for the engine's subsystems, and `game_load()` owns the authoritative `map_loaded` state.

This first slice is a prerequisite gate, not completion of the gameplay oracle. The immediate follow-on adds real map-dependent initialization and authored object/AI placement; only after that succeeds should the test create a local player, tick the real engine, and demand a real pose. This staging isolates whether the integration problem is initial HCU system setup, D20 data/schema, map-dependent CE setup, or actual actor/player/tick code, while maintaining the requested end state of a real CE gameplay workload.

## Current baseline and exact gap

The existing D20 executable calls `scenario_load()` directly, verifies scenario/tag/BSP publication, tests B001 partial-write rollback, switches B001–B004, and unloads. Its compile command links `scenario.c`, tag files and schema, PS2 cache/CTAG/CBSP, parent map-service/HP2 readers, but not CE `game.c`, `players.c`, `objects.c`, `ai.c`, `units.c`, or the model-animation decoder ([`test_hcu_ce_d20_oracle.py:61-103`](../../tests/test_hcu_ce_d20_oracle.py#L61), [`hcu_ce_map_lifecycle_main.c:431-536`](../../tests/hcu_ce_map_lifecycle_main.c#L431)). Its test-only `HCU_M2_D20_HOST_ORACLE` gate is distinct from the default production admission path ([`hcu_map_service.c:305-317`](../../src/stream/hcu_map_service.c#L305)).

An existing CE tick test extracts the retail `game_tick()` body but replaces nearly all phase behavior with callbacks that only append events ([`test_hcu_game_tick_fixture.py:55-155`](../../tests/test_hcu_game_tick_fixture.py#L55)). It is useful for ordering but cannot validate an actor, player, movement, AI, object, animation, damage or state transition.

The authoritative CE order is:

```text
process game_initialize()
  -> game_load(options) -> scenario_load() -> game_globals->map_loaded
  -> game_initialize_for_new_map()
     -> map-dependent system initialization -> objects_place() -> ai_place()
  -> player_new()/local slot -> game_time_start() -> game_initial_pulse()
  -> game_tick() -> real unit/AI/player/object/animation updates
```

`game_initialize()` allocates `game_globals` and calls the subsystem initializers in source order ([`game.c:281-331`](../../submodules/halo-ce-universal/source/game/game.c#L281)); `game_load()` validates options, calls `scenario_load()`, and only then marks the map loaded ([`game.c:616-657`](../../submodules/halo-ce-universal/source/game/game.c#L616)). CE's actual main transition then runs `game_initialize_for_new_map()`, local-player creation, game-time start and initial pulse ([`main.c:1475-1497`](../../submodules/halo-ce-universal/source/main/main.c#L1475)). Map initialization invokes all map subsystem initializers before activating the game and calling `objects_place()` and `ai_place()` ([`game.c:663-733`](../../submodules/halo-ce-universal/source/game/game.c#L663)). A `player_datum` is created by `player_new()` ([`players.c:1225-1272`](../../submodules/halo-ce-universal/source/game/players.c#L1225)); the authored biped is later spawned from the scenario start during `players_update_before_game()`'s tick path ([`players.c:1417-1488`](../../submodules/halo-ce-universal/source/game/players.c#L1417), [`players.c:4802-4850`](../../submodules/halo-ce-universal/source/game/players.c#L4802)).

## Why the first slice should stop after `game_load()`

`game_initialize()` itself is not a tiny seam. It owns game state and invokes game time/engine, allegiance, interface, scenario, director/observer/render, objects, structures/collision, players, effects/particles, sound, AI, editor, HaloScript, cinematics, input, and UI initialization. Replacing these calls with event-only stand-ins would simply recreate the current tick-fixture limitation at startup. The right initial test should keep the actual CE initializer and diagnose its dependency closure; adapters should be restricted to platform boundaries and explicitly observed.

The machine memory path also has a concrete requirement: CE's `game_state_initialize()` requests its CPU/GPU game-state buffer through `game_state_allocate_buffer()` and then starts allocating persistent game data ([`game_state.c:1043-1053`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L1043), [`game_state.c:549-567`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L549)). The PS2 implementation obtains these stores through bound physical-memory regions (`ps2_memory.c:91-175`, `:233-295`); the existing D20 lifecycle harness instead owns only its map and scratch arenas. Therefore the new executable must explicitly bind aligned, disjoint, overprovisioned host spans before `game_initialize()` and report their high-water. It must not rely on bootstrap arrays, Linux `malloc` as untracked gameplay storage, or a guessed EE budget.

If the first executable cannot link without dozens of unrelated host substitutions, do not generate blanket zero-return stubs. Keep the `game_initialize()` closure real, classify each unresolved external by call-site/semantic role, then add only narrow observable machine/UI/audio/network-local adapters where the PS2 product path truly owns that behavior. Required system initialization, object/player/game-state/tag code remain real. This is consistent with the current PS2 port manifest's intent to compile the campaign gameplay sources rather than N64-cutting AI/HS (`port.json` lists `source/ai`, `source/hs`, `source/objects`, and `source/game`; [manifest](../../submodules/halo-ce-universal/port/ps2/port.json#L1)).

## Proposed first executable/test slice

### Target and inputs

1. Add a new uniquely named fixture and test, e.g. `tests/hcu_ce_d20_gameplay_main.c` plus `tests/test_hcu_ce_d20_gameplay_init.py`. Reuse the existing D20 source map/package, schema artifact generation, source pin/dirty-state manifest, host ILP32+short-wchar profile and parent map-service composition. Do not mutate the existing D20 lifecycle test or its output artifacts.
2. Build from the current PS2 HCU source manifest and capture the generated object manifest, retained rooted link map, unresolved externals before adapters, and final ELF. Prefer the manifest's full selected source list with `--gc-sections`; compare it with the currently 369/0-compilation-failure production closure before claiming that the host target has equivalent CE source coverage. A curated test list is acceptable only when every omitted unit is demonstrated unreachable from the requested roots.
3. Freeze source commit IDs **and dirty worktree diffs/hashes**, test sources, generated MSVC semantics prefix, compiler/sysroot/flags, current schema ELF/manifest, D20 HP2/map hashes, run log, map and ELF hashes. Dirty submodules mean commit IDs alone are insufficient.

### Host memory and adapters

4. Before calling CE, allocate aligned guard-wrapped test spans for game state, tag cache, active BSP, validator claims, and any required PS2-owned texture/sound/compatibility stores. Bind through the real `physical_memory_bind_*` APIs and verify readiness/non-overlap; keep host span sizes separately labeled from the R5900 `HALO_PORT_*` capacities. Place canaries and a byte high-water ledger around each owned span. Do not bind overlaps between the map service's current CTAG/BSP arenas and CE cache destinations; resolve ownership explicitly.
5. Preserve actual `ps2_memory.c`, game-state allocator, CE cache/tag services, scenario and tag-data consumers. If a platform operation prevents host execution, implement a narrow test adapter for that external interface and log every invocation/arguments/result. Fail on unlisted call sites, impossible waits, uninitialized handle success, I/O failure hidden as success, or attempted platform drawing; avoid replacing an entire CE subsystem.
6. Use a local, neutral input boundary only for startup; no movement/player assertions are needed in this first slice. Track that `game_initialize()` and `game_load()` did not create test-invented player/object/actor state.

### Workload and assertions

7. Call actual `game_initialize()` exactly once. Assert a valid `game_globals`, valid game-state backing and allocation ledger, initialized subsystem sentinels as available from public CE APIs, zero allocation overrun, and unchanged span guards.
8. Construct options using `game_options_new()`, set the exact `map_name = "levels\\d20\\d20"`, ensure difficulty/seed are deterministic and valid, then call actual `game_load(&options)` exactly once. Do **not** call `scenario_load()` separately. Assert `game_map_loaded()`, matching game options/map string, valid `global_scenario`, initial B000 collision/scenario globals and mounted owner. Verify failure injection leaves `map_loaded == FALSE` and no published scenario/owner after cleanup; verify one fresh retry succeeds in the same process.
9. Call actual `game_unload()` (which owns the `scenario_unload()` and CE `map_loaded` transition) and assert map-loaded false, scenario/tag/BSP globals cleared, map/CTAG/BSP owner released, and game-state allocation/base state remains valid if CE semantics retain it until process shutdown. Do not call `scenario_unload()` directly as the only teardown, and do not free the game-state arena while CE globals can still point into it ([`game.c:754-788`](../../submodules/halo-ce-universal/source/game/game.c#L754)).
10. Build a second fixture executable without the D20-only admission macro and prove the default production map service rejects D20 before opening files, just as the existing map oracle does. Assert the host-only define is absent from all R5900 manifests/build rules.

### Gate and transition to real gameplay

11. First-slice pass means only: real CE `game_initialize()` + real CE `game_load()` + D20 scenario/B000 assertions + deterministic failure/retry/unload + bounded host ownership + reproducible source/build tuple + production D20 rejection. It is **not** evidence of `game_initialize_for_new_map`, object/actor/player creation, `game_tick`, animation, target capacity, PS2 map support or rendering.
12. For the next slice, add real `game_initialize_for_new_map()` without adding local-player creation yet. Keep object/AI/HaloScript map initialization real; assert the actual D20 initial placed-object and authored encounter-derived actor counts, and preserve detailed failure if unsupported/missing tags prevent completion. Audit the scenario data to select a genuinely initially created actor/variant before coding expectations.
13. Only after map initialization passes, add CE player creation following `main_new_map()` order, then call `game_time_start()` and `game_initial_pulse()`. Run the actual `game_tick()` once; require a player datum **and** its spawned player biped/unit/object identity chain, plus an authored AI actor's actor↔unit↔object/encounter identity. Advance deterministic neutral and movement inputs in separate replay cases.
14. Finally prove CPU pose by reaching actual unit animation update, `object_compute_node_matrices()` and `animation_get_node_orientations()` / `animation_get_frame_data()` with tag-data bounds. Assert frame progression and finite pose matrices, with trace on/off state-hash equality. This is simulation pose evidence only; missing render vertex payload and no GS/VU presentation remain explicit.

## Closure and integration risks to resolve while implementing

| Risk | Why it matters | Required treatment |
|---|---|---|
| Initializer closure is broad | `game_initialize()` invokes many source systems, unlike the map-only target; section-GC may keep their initializers and static data alive. | Generate and inspect a rooted host link map; inventory undefined names by semantic call-site before writing adapters. Do not use a blanket regenerated stub set. |
| Host ILP32 execution is environment-sensitive | Existing tests may compile under sandbox then receive SIGSYS at native ILP32 runtime; a compile/skip is not execution evidence. | Preserve binary and exact command; run elevated when needed and distinguish skipped from passed. |
| Memory ownership differs across test layers | The map lifecycle harness uses explicit host owner/scratch arenas; PS2 game state relies on separately bound fixed stores. | Bind one disjoint host topology through actual APIs, instrument every owner, retain guards; no inference to PS2 fit. |
| Fixture-only D20 admission | D20 remains blocked in production. | Give gameplay fixture a separate define, assert absence from production profiles, and retain a no-define rejection executable. |
| Retail render payload is stripped | The converted CTAG intentionally excludes render vertices; a successful game/tick or pose is not a visible scene. | Keep render assertion out of this oracle; later produce/use parent HP2 render resources and a real GS/VU submit test. |
| D20 actor may not spawn immediately | `encounters_create_for_new_map()` filters encounter flags and actor variants; authored presence is not live actor proof. | Walk and record scenario→encounter→squad/platoon→variant→actor/unit/object tags before selecting acceptance IDs. |
| Tick smoke can be misleading | Existing extracted tick test stubs all gameplay phases. | The gameplay executable must retain real `game_tick`, units, AI, player, objects, and pose functions; adapters only at explicit machine services. |
| Single HCU pin is not a reproducible input | Parent/HCU/halo-ps2 trees have dirty and untracked work. | Hash dirty diffs and all build inputs; do not conflate evidence from distinct trees or ELF hashes. |

## Halo-64 comparison boundary

Halo-64 demonstrates useful architectural separation: its machine/game adapter owns console-facing render/presentation work (`submodules/halo-64/port/n64/game/n64_render_game.c`) and its notes identify state that must still advance when drawing is absent (`submodules/halo-64/port/n64/NOTES.md:14`, [`HISTORY.md:817`](../../submodules/halo-64/port/n64/HISTORY.md#L817)). Its generated no-op bodies are not a template for CE gameplay coverage: the N64 source carries explicit AI/script/effect cuts, e.g. `n64_stubs_generated.c` contains no-op editor and network-facing functions (`submodules/halo-64/port/n64/game/n64_stubs_generated.c:122-128`). For this PS2 target, retain HCU's real AI/HS/effects/object/gameplay code; borrow only the explicit boundary/adaptor and evidence separation pattern, and make every host adapter individually reviewed. The PS2 budget and product scope do not justify silently importing the N64 cuts.

## Suggested immediate work order

1. Source-walk the actual HCU PS2 build manifest and root only `game_initialize`, `game_load`, `scenario_unload` plus required shutdown; generate the host unresolved-symbol and link-map inventory before writing the harness.
2. Add/bind the host spans and implement only reviewed platform-boundary adapters; compile and record failures without weakening the CE call path.
3. Execute the fixture outside the sandbox as needed, capture exact ELF/map/log hashes, and verify one D20 load, induced failure/retry, unload, and production rejection.
4. If this gate passes, extend the separate fixture with real `game_initialize_for_new_map()` and authored object/AI placement. Do not bundle player/tick/pose in the first patch; that would make a broad failure hard to localize. The full oracle remains the end condition, not this initial gate.

## Source references

- D20 lifecycle host test and exact linked source list: [`tests/test_hcu_ce_d20_oracle.py:20-180`](../../tests/test_hcu_ce_d20_oracle.py#L20).
- Current real scenario/BSP oracle body: [`tests/hcu_ce_map_lifecycle_main.c:431-536`](../../tests/hcu_ce_map_lifecycle_main.c#L431).
- CE startup, map load, initialization, tick, and new-map behavior: [`game.c:281-410`](../../submodules/halo-ce-universal/source/game/game.c#L281), [`game.c:616-733`](../../submodules/halo-ce-universal/source/game/game.c#L616).
- CE-owned map unload transition: [`game.c:754-788`](../../submodules/halo-ce-universal/source/game/game.c#L754).
- CE retail map/player startup sequence: [`main.c:788-872`](../../submodules/halo-ce-universal/source/main/main.c#L788), [`main.c:1475-1497`](../../submodules/halo-ce-universal/source/main/main.c#L1475).
- Player datum and authored player-spawn paths: [`players.c:1225-1272`](../../submodules/halo-ce-universal/source/game/players.c#L1225), [`players.c:1417-1488`](../../submodules/halo-ce-universal/source/game/players.c#L1417), [`players.c:4802-4850`](../../submodules/halo-ce-universal/source/game/players.c#L4802).
- CE game-state allocator and PS2 memory binding: [`game_state.c:549-567`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L549), [`game_state.c:1043-1053`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L1043), [`ps2_memory.c:91-175`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L91).
- Production map-service D20 guard: [`hcu_map_service.c:305-317`](../../src/stream/hcu_map_service.c#L305).
- HCU PS2 selected-source manifest: [`port.json`](../../submodules/halo-ce-universal/port/ps2/port.json#L1).
- Halo-64 architecture/caveat references: [`n64_render_game.c`](../../submodules/halo-64/port/n64/game/n64_render_game.c), [`NOTES.md`](../../submodules/halo-64/port/n64/NOTES.md#L14), [`n64_stubs_generated.c:122-128`](../../submodules/halo-64/port/n64/game/n64_stubs_generated.c#L122).
