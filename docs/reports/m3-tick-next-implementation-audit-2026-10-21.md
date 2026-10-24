# M3 next executable tick-fixture slice

Date: 2026-10-21  
Scope: report-only assessment of M3 Steps 11–12. This does not change CE, PS2, parent runtime code, the shared plan, or existing tests. M2 remains a required runtime dependency for BSP-backed M3 acceptance.

## Finding

The existing host fixtures do not yet execute a CE gameplay subsystem: the extracted `game_tick()` invokes deterministic test callbacks for every phase, and the extracted `game_time_update()` invokes a stub `game_tick()` and stub local-tick queue. The immediate, BSP-independent implementation slice is to keep the actual extracted CE `game_tick()` and replace its `units_update()` callback with the exact CE `units_update()` body, backed by a tiny explicitly initialized unit-global fixture. Then call that integrated tick through the already-extracted scheduler for 0/1/3/7 tick frames and assert the unit timer state at each phase boundary.

This is a real CE phase, not a movement/collision substitute. It can strengthen Step 11’s tick-dispatch and subsystem-order evidence now, without pretending that player movement, loaded actors, collision, or a gameplay BSP has been qualified. In parallel, Step 12 should extend the existing input harness to feed published pad state through the actual `input_frame_begin()` and then through the scheduled real CE tick; until an actual player-control consumer is integrated, assertions must be limited to CE input frame state observed at each tick, not movement output.

## Evidence reviewed

- [`game_tick()`](../../submodules/halo-ce-universal/source/game/game.c#L331) has a stable local-mode phase order. `units_update()` is called once immediately after allegiance and before AI/player pre-update at lines 355–366. It derives the effect/antenna step at lines 368–377, brackets first-person weapon update with the global RNG lock at lines 378–382, then calls game engine, scripts, objects, players-after, HUD and player effects through lines 383–397.
- CE [`units_update()`](../../submodules/halo-ce-universal/source/units/units.c#L1106) is self-contained: it rolls `highest_timer` into `next_timer`, clears `highest_timer`, and clears `used_time`. The exact state fields are `short`, `short`, and `boolean` in `struct unit_globals` at lines 789–795. `units_initialize()` allocates this record through CE game-state allocation (lines 1022–1028), but a focused host fixture can provide the exact record layout and a pointer to a fixture-owned instance without initializing a map or BSP.
- The current [`test_hcu_game_tick_fixture.py`](../../tests/test_hcu_game_tick_fixture.py) compiles the extracted real tick body but all phase routines—including `units_update()`—are event-only stubs (lines 64–85). It verifies ordering, deltas and repeatability, not an actual phase’s state transition.
- The current [`test_hcu_game_time_scheduler.py`](../../tests/test_hcu_game_time_scheduler.py) compiles the extracted scheduler body and covers 0/1/3/7 ticks, but `game_tick()` is a stub (HARNESS_SUFFIX). It verifies scheduling arithmetic and per-tick callback ordering, not the effect of a CE phase on state.
- The real [`game_time_update()`](../../submodules/halo-ce-universal/source/game/game_time.c#L379) samples local elapsed time, clamps local scheduling to seven ticks (lines 419–440), invokes `update_client_local_ticks()` (lines 451–460), and runs `game_tick()` once per server update (lines 473–487). This is the sound path for integrating the phase fixture; do not replace its once-per-frame scheduling with one input poll per simulation tick.
- CE’s [`input_frame_begin()`](../../submodules/halo-ce-universal/source/input/input_xbox.c) polls the PS2 adapter before device-state snapshotting, while the bridge is [`hcu_input_bridge.c`](../../src/stream/hcu_input_bridge.c). The existing Step 12 tests already prove bridge/frame-boundary semantics, but not a tick consuming the published state.
- The PS2 render adapter’s [`render_frame()`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L120) advances frame/presentation state and copies CE object/matrix data into a snapshot; it is deliberately not the gameplay tick. This boundary is important for a future render-schedule-invariance fixture.
- Halo-64 provides a useful adapter comparison, not a PS2 implementation template: [`n64_render_game.c`](../../submodules/halo-64/port/n64/game/n64_render_game.c) supplies game-facing render globals/frame calls while leaving drawing to its N64 renderer; its [`NOTES.md`](../../submodules/halo-64/port/n64/NOTES.md#L33) explicitly lists state the game still needs when rasterizer drawing is excluded. This supports keeping CE simulation authoritative and testing PS2 presentation independently; N64 pools/ABI/tick cuts do not transfer to the EE.

## Recommended executable slice (no resident BSP)

1. In a new isolated test (or an additive test in the fixture owner’s write set), extract the exact `struct unit_globals` definition and exact `units_update()` implementation from `source/units/units.c`. Do not hand-reimplement its three assignments. Define the same `unit_globals` identifier as a fixture pointer to a local instance; because the CE source declares it `static`, the extraction harness should explicitly remove only that storage-class token from the extracted declaration or wrap the function and definition in one generated translation unit. Assert the struct’s source layout/field types in the harness and reset it per case.
2. Modify only the extracted `game_tick()` harness’s `units_update()` stub into the extracted CE body. Before each tick seed `next_timer`, `highest_timer`, and `used_time`; assert after the phase that `next_timer == prior highest_timer`, `highest_timer == 0`, and `used_time == FALSE`. Also log the timer tuple at the immediately-before/after phase boundaries and prove surrounding phase event order is unchanged. No BSP/tag data is required.
3. Integrate that tick harness into the actual extracted `game_time_update()` harness: have scheduler `game_tick()` invoke the same real-tick harness routine (not merely append event 1), and preserve the existing 0/1/3/7 frame cases. Seed `highest_timer` differently before each tick through a deterministic test-only preceding phase; prove each tick rolls exactly its own timer state and scheduler executes the expected number of phase transitions. Keep `update_client_local_ticks()` a scheduler observation stub initially, clearly marking it as such.
4. Add one small input integration case: invoke production-extracted `input_frame_begin()` once to publish a sample; run 0/1/3 tick scheduling with the CE input globals held; record `(frame_id, tick_index, pressed, held, released, device_present)` at the entry to the tick. Prove zero ticks do not consume/duplicate edges, multi-tick frames do not repoll or synthesize repeated pressed edges, and a subsequent frame transitions to held/released according to CE input semantics. This is an input-to-tick fixture, not player movement parity.
5. Keep explicit fixture boundaries in output: `actual_ce_game_tick_body=true`, `actual_ce_units_update_body=true`, `actual_ce_game_time_update_body=true`, `actual_player_control=false`, `resident_bsp=false`, `collision=false`, `guest=false`. These markers prevent the thin executable slice from being misrepresented as the M3 exit.

## Tests and acceptance boundary

Run the current baseline first:

```sh
PYTHONPATH=. python3 -m pytest -q \
  tests/test_hcu_game_tick_fixture.py \
  tests/test_hcu_game_time_scheduler.py \
  tests/test_hcu_ps2_input.py \
  tests/test_hcu_render_frame_invariance.py
```

Observed in this audit: **2 passed, 1 skipped** for tick fixture, scheduler fixture, and render invariance fixture; the input suite was not included in that command. The skip is the expected sandbox restriction on native ILP32 execution; record it, do not count it as executed evidence.

After implementation, require these tests plus negative checks for an incorrect timer carry, duplicate `units_update()` in a tick, skipped tick at a scheduled step, and repeated poll within a frame. Verify source-extraction uniqueness (fail if the function/struct definition is absent or ambiguous), exact local tick phase order, deterministic repeat-run state hashes, and a clean `git diff --check`.

This slice may close only the corresponding host-fixture substep under M3 Step 11 and advance the Step 12 input-to-tick contract. It cannot close Step 11 as written, M3 overall, M2, collision ownership, or Step 16: no player/unit movement behavior is exercised, `players_update_before_game()` remains stubbed, and CE collision still needs a resident gameplay collision BSP. The next substantive M3 slice after this one is to execute the real CE player-control/movement path against a bounded synthetic CE collision-BSP datum (not the parent COLL pack), then compare identical input/state against the parent oracle. That synthetic fixture can be developed early, but retail-map residency and guest qualification still wait on M2.

