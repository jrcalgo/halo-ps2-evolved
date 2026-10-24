# M2 Step 7 — next host-side CE consumer review

## Recommendation

The highest-value remaining host-only, source-backed consumer slice is **CE player combined-PVS aggregation**: execute the real static `players_compute_combined_pvs()` against the already published, hash-bound `a30`/`a50` BSPs and compare the aggregate bit vector to an independent oracle assembled from the original Xbox player cluster records and raw PVS rows. This is distinct from the completed per-cluster visible/hidden-pair oracle. It tests the gameplay-side operation which combines several players' viewpoints, local-player filtering, missing-cluster handling, and the optional activating cluster. It needs no new Step 8 arena or map-capacity claim and need not invoke renderer traversal or draw callbacks.

The fixture is feasible in principle, but it should be admitted only after an exact link-closure probe. `players_compute_combined_pvs()` is `static`, so a small test translation unit can include the pinned `players.c` and expose a test wrapper that calls that exact function; compile with function/data sections and inspect the final map after section GC. Avoid a copied reimplementation of the CE loop. For the first bounded case, use actual CE player datums whose `unit_index == NONE`, so the helper consumes each datum's already-populated `cluster_index` and does not enter the separate object-root refresh branch. Use CE's actual data-array iterator and PVS accessor/OR routine where possible. The local-game-only variant and activation path should be covered only where a real state source is available; do not silently replace CE logic with an adapter that manufactures an answer.

## Current coverage checked

1. The retail transaction currently makes successful CE scenario/BSP publication for `a30` and `a50`, and its source oracle derives specific visible and hidden non-self PVS pairs directly from raw map BSP extents. The C fixture calls `structure_bsp_get_cluster_pvs()` and `BIT_VECTOR_TEST_FLAG()` and compares the selected pairs against the independent oracle ([`test_hcu_scenario_bsp_switch.py:21-105`](../../tests/test_hcu_scenario_bsp_switch.py#L21), [`hcu_scenario_bsp_switch_main.c:653-740`](../../tests/hcu_scenario_bsp_switch_main.c#L653)). This proves selected row/bit preservation, not aggregate player behavior.
2. The test already invokes CE `compute_sound_obstruction()` for its missing-cluster, unreachable `0xFF`, and reachable hidden-PVS cases. Its report explicitly excludes audible playback and the visible-PVS collision branch ([`m2-step7-ce-sound-obstruction-qualification-2026-10-21.md`](m2-step7-ce-sound-obstruction-qualification-2026-10-21.md)).
3. The same publication seam now queries CE `scenario_location_underwater()` and compares weather selection for source-derived unfogged clusters ([`hcu_scenario_bsp_switch_main.c:975-1006`](../../tests/hcu_scenario_bsp_switch_main.c#L975)). The recently completed collision slice adds raw-derived miss and reverse-face tests; the owner-exhaustion slice checks transaction cleanup. Neither covers player PVS combination.
4. The current environment-query coverage does not imply fog-plane, fog-region, water, wind simulation, or sound-palette coverage; a future deeper environment test remains a credible second candidate, but requires a valid raw fog-plane/region/fog-tag chain. By comparison, combined player PVS can reuse the current published BSP and raw-PVS oracle with fewer new asset prerequisites.

## CE source contract and required fixture behavior

The CE implementation is [`players.c:1789-1877`](../../submodules/halo-ce-universal/source/game/players.c#L1789). In its ordinary game branch it:

- clears exactly `0x40` bytes of output;
- iterates `player_data` and, when `local_player_only` is true, excludes players whose `local_player_index == NONE`;
- refreshes a player's cluster from its ultimate-parent object only when `unit_index != NONE` and that object's cluster is valid;
- ORs the selected player's cluster PVS rows into the combined vector;
- finally ORs an optional activating-cluster PVS row.

Both aggregate outputs are part of the CE `players_globals` layout: `combined_pvs` begins at `0x30`, `combined_pvs_local` at `0x70`, and the full structure is `0xB0` ([`players.h:129-160`](../../submodules/halo-ce-universal/source/game/players.h#L129)). CE calls this helper for the two aggregates at the end of `players_update_before_game()` ([`players.c:4959-4960`](../../submodules/halo-ce-universal/source/game/players.c#L4959)); another call feeds the coop respawn effect path at `players.c:2193`.

The first fixture should operate after existing CE/PS2 package publication, initialize a real `player_data` array containing at least two players with different valid clusters, one non-local player, and a player with `cluster_index == NONE`; use `unit_index == NONE` in this bounded slice. Call CE's helper twice, once for all players and once local-only. Independently OR the selected raw-source PVS rows, with the same explicit 64-byte CE output width and a zero-filled tail, and compare all output words—not only a representative bit. Assert the input player cluster values remain unchanged. For the activating-cluster subcase, exercise the actual owner of activation state and provide a hash-derived cluster; if that owner cannot be initialized without substituting gameplay semantics, document the narrower omission rather than returning a fabricated test value.

Use compile-time ABI assertions for `player_datum` size (`0xD4`), `players_globals` size (`0xB0`) and both combined-PVS offsets; assert the 32-bit `unsigned long` assumptions in the host ILP32 target. Source-oracle rows must bind parent/HCU/halo-ps2 pins, raw source map hashes, package manifest, HP2 hashes, CBIX BSP identity, source-derived cluster list, and exact output vector. Snapshot the published BSP bytes, CE scenario/BSP publication pointers/indices, and collision-user stack around the query as the existing consumer fixture does. A repeated query after BSP switch/rollback/retry must match the corresponding newly published BSP's oracle rather than stale prior output.

## Closure and safety conditions

The test should keep the CE helper's semantics intact and keep external services narrow:

- Include the real pinned `players.c` only in a dedicated host fixture TU, exposing the static helper without editing the engine source.
- Initially restrict player `unit_index` to `NONE` so the fixture does not call object lookup with dummy object records. This still tests real iteration, filtering, per-player cluster selection and bitwise aggregation.
- Prefer the real `data_iterator_new()` / `data_iterator_next()` and `bit_vector_or()` implementations. If they enlarge the closure, record every retained symbol and test adapter in the link map; do not substitute a second loop or OR implementation as the semantic oracle.
- The ordinary branch depends on `game_in_editor()` and `objects_get_activating_cluster_index()`. Use a real normal-game mode/accessor state if its globals can be initialized through actual CE APIs. If deterministic adapters are necessary, constrain them to environment/state inputs (editor=false, activation=NONE) and label the result as excluding that behavior. Do not stub collision, rendering, objects, players, simulation ticks, or effects to make the test pass.
- Do not invoke `players_update_before_game()` just to reach the helper: its full gameplay updates have many unrelated dependencies. The helper itself is the source-backed unit under test. Do not root `structure_visibility`'s portal/frustum traversal in this fixture; this is game-side aggregation only, not screen-visibility evidence.
- Run the existing hash-bound `a30`/`a50` native ILP32 package case through its approved route, retain executable and map, and compare their actual source/pin/package hashes. Sandbox SIGSYS skips are not execution evidence.

This is host CE behavior evidence only. `a50`'s largest referenced BSP exceeds the production 6 MiB `current_bsp` arena, and all host fixtures are overprovisioned; do not make a PS2 capacity, PCSX2 gameplay, frame-rate, or rendering claim. Step 8 remains the gate for lawful target residency.

## Comparative-source and REA disposition

Halo-64 is useful only as an architectural comparator: its notes distinguish retained game-side CPU state (camera/frame/first-person/HUD) from platform rendering and warn that omitted rendering cannot justify omitting state advancement ([`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)). It is not authority for PS2 player limits, PVS semantics, budgets, or N64 feature cuts. HCU CE source and hash-bound retail Xbox BSP bytes are the behavior oracle here. REA is not applicable: the candidate is inspectable CE C and decompressed retail source data, not opaque shipped-binary behavior. Use REA only if a remaining exact binary-only behavior cannot be resolved through source/data inspection or runtime tests.

## Acceptance boundary

A passing fixture would close only CE player-PVS aggregation/filtering for the tested source-derived player/cluster cases over published host materializations. It would not close object-root cluster refresh, the editor camera/leaf fallback, all activation modes, portal/frustum traversal, full BSP-consumer coverage, Step 8 capacity, target execution, gameplay-map loading, or rendering. Step 7 and M2 remain partial.
