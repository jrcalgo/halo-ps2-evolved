# Step 8: CE local-player workload fixture

This is a test-only bridge from the PS2 Step 8 diagnostic image into CE's real
`main_new_map()` path. The workload-only profile skips the 13 map queries. It
requests Sidewinder, selects CE's Slayer
variant, sets two local player slots, allows CE to run map initialization,
object placement, and local-player creation. It then follows CE's normal local
frame order—three `player_control_update()` / `game_time_update()` pairs, which
produce queued server updates and ticks—plus one `game_frame()`. It checks that
both CE player records resolve to distinct live units, snapshots the separately
owned game-state arena and object pool, disposes old-map state before scenario
unload, and checks that map/tag/BSP state is empty and player/team datum arrays
are invalidated. The cached local-player count remains `2` after disposal and
is reported rather than treated as an active player record. No pool budgets or
allocator behavior are changed.

The fixture is deliberately limited to local split-screen. It does not create
network bots, run a 4-player scenario, or exercise network co-op. In particular,
the scenario-authored AI placement path is not a substitute for bot match
workload. The game-state reservation contains the object pool as a sub-owner;
those two byte counts must not be added. `dynamic_simulation` remains a separate
HCU owner and is not included in either CE snapshot.

## Verification

- R5900 `hcu_ps2_closure.py --layer all --no-bootstrap-memory --m2-ui-lifecycle-test --step8-mp-capacity-diagnostic --step8-mp-workload-only`: passed compilation of all 371 objects (0 failures), profile result `layer-measured/open`.
- R5900 `hcu_parent_link_probe.py --step8-mp-capacity-diagnostic --step8-mp-workload-only`: linked with zero undefined symbols; gameplay ELF file load is 2,050,948 / 2,097,152 bytes, BSS is 2,115,732 bytes. ELF SHA256: `c0f4a93bdfa5d7f2f5fd01254259b0325eb5935cbbeeccac2974c6abf000e6f5`. Compiled `source/main/main.c` SHA256 is `dd73b3755e0828a16f33d36397243b1be42d1558ef0d47403f32f9414db18215`; this image includes the production teardown-order change.
- Host `tools/test_hcu_step8_memory_owners.py`: passed exhaustion/failure/reset checks for both owners; confirms `dynamic_simulation` remains unchanged and separate. Source guards `tests/test_hcu_step8_mp_workload_source.py` and `tests/test_hcu_ps2_map_teardown_order.py` pass (1 and 4 tests respectively), enforcing CE input→game-time order, no direct `game_tick()`/queue internals, and dispose-before-unload sequencing.
- `python3 tools/test_hcu_step8_mp_workload.py --mode interpreter` passed on the workload-only Sidewinder ELF. PCSX2 reported two distinct local players with live units, three ticks, 90 objects / 83 active; game-state arena used/peak 3,107,656 B and 0 failures; nested object pool used/peak 78,104 B and 0 failures. `dynamic_simulation` remains separate and is not summed. Teardown evidence: map unloaded, player/team datum arrays invalidated, tag table empty, scenario/BSP globals unpublished; cached local-player count is retained as 2. Log: `build/hcu-ps2-closure/emulator-m1-interpreter-b235c96154964e648ac76c6d14608df4/emulog.txt` (SHA256 `7239153e2566b4cea37a1cd5001576e25e79d18c68b3f262fa64389b6b227d3b`); guest result: `build/hcu-ps2-closure/emulator-m1-interpreter-b235c96154964e648ac76c6d14608df4/result.json` (SHA256 `1663a3b2c62b9982c2d9d986807945cacc5c15a2a9dea0a09fc0a21e0e92afa7`); runner assertions: `build/hcu-step8-mp-workload/interpreter-result.json` (SHA256 `f00bef062efd473e46796dc770ff3763b7d2f2e3c7ef5561249927de39587667`).
- The normal R5900 build omits `hcu_step8_test_start_local_map`; the diagnostic bridge and owner counters are test-profile-only. The normal `game_state.c.o` and `objects.c.o` contain no Step 8 owner-counter symbols, so the diagnostics add no normal-build BSS or code.

This closes the one-map, two-local-player diagnostic workload slice only. It
does not establish 1–4-player scaling, bot matches, network co-op, campaign,
physical PS2 memory pressure, or arena/guard headroom across all maps. Step 8's
broader capacity gate remains open until those workloads and target-side limits
are measured.

## Reproduction

```sh
python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory --m2-ui-lifecycle-test --step8-mp-capacity-diagnostic --step8-mp-workload-only
python3 tools/test_hcu_step8_memory_owners.py
python3 tools/hcu_parent_link_probe.py --step8-mp-capacity-diagnostic --step8-mp-workload-only
python3 tools/test_hcu_step8_mp_workload.py --mode interpreter
```
