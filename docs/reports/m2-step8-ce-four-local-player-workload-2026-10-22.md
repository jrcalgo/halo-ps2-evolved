# Step 8 four-local-player CE workload diagnostic

## Result

The isolated Step 8 workload now has two compile-time profiles, 2 local players (the existing baseline) and 4 local players (Halo CE's `MAXIMUM_LOCAL_PLAYERS`). The fixture requires every requested local slot to exist, all player datums to be distinct, each player's unit datum to resolve to a live unit, and all unit indices to be distinct. It records one allocator/object-pool snapshot and normal CE map teardown for either profile. This is local split-screen only: it does not instantiate AI bots or network co-op, and it does not alter production pool budgets, map admission, or runtime policy.

Four-player target behavior is **not yet verified**. Both profiles compile and link for R5900 with zero undefined imports; the runner's host checks pass. The interpreter attempt could not start PCSX2 because the current execution environment could not connect to its X display (`:0.0`; Qt xcb reported `could not connect to display` / missing `xcb-cursor0`). This is a host UI-launch failure before guest execution, not evidence that CE four-player creation succeeds or fails.

## Implementation and source basis

- `submodules/halo-ce-universal/source/game/players.h:23` defines `MAXIMUM_LOCAL_PLAYERS = 4`.
- `submodules/halo-ce-universal/source/main/main.c:1535-1552` bounds the test bridge's requested player total to the CE maximum, sets `player_spawn_count`, and proceeds through CE's `main_new_map()` transaction.
- `submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c` uses CE's frame producer path (`player_control_update()` followed by `game_time_update()`), then checks `local_player_exists()`, distinct player indices, and each player's live unit; it snapshots the existing Step 8 game-state and object-pool owners and checks normal teardown. A diagnostic-only `HALO_PS2_STEP8_MP_WORKLOAD_PLAYERS` define is restricted to 2 or 4.
- `tools/hcu_ps2_closure.py`, `tools/hcu_ps2_link.py`, `tools/hcu_parent_link_probe.py`, and `tools/ee-world.mk` propagate the selected player count only into the opt-in workload test profile. The normal production profile is unchanged.
- `tools/test_hcu_step8_mp_workload.py` accepts `--players 2|4`, parses a variable-length unit-index list, and rejects wrong player/unit counts, NONE handles, duplicate unit identities, failed allocator snapshots, missing teardown, or missing terminal marker. Synthetic runner regression tests exercise both accepted cardinalities and reject duplicated handles.
- Halo-64 is comparison only: `submodules/halo-64/port/n64/NOTES.md:15-20` describes a CE-derived local-player setup using `player_spawn_count`; it is not used as authority for PS2 semantics or capacities.

## Verification evidence

- `python3 tests/test_hcu_step8_mp_workload_source.py` — passed; source guard verifies input→tick order, 2/4 profile bounds, distinct-player requirements, and dispose-before-unload cleanup.
- `python3 tests/test_hcu_step8_mp_workload_runner.py` — passed; synthetic 2P and 4P records accepted, duplicate-unit records rejected.
- `python3 -m py_compile tools/hcu_ps2_closure.py tools/hcu_ps2_link.py tools/hcu_parent_link_probe.py tools/test_hcu_step8_mp_workload.py tests/test_hcu_step8_mp_workload_runner.py` — passed.
- `git diff --check` for the workload/build/test files — passed.
- R5900 full selected closure for each profile: 371 units compiled, 0 failed. Combined parent/HCU gameplay links: 0 undefined symbols. These remain diagnostic links; the existing link report correctly says `acceptance=false` and does not demonstrate the in-guest workload.
- 4P ELF: `build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-4p-tagcache-4477120.elf`, SHA-256 `c159c609f12c28a2532db848e5e699a64538fcdff8b27ee75e0907c47175541b`.
- 2P ELF rebuilt from the same source: `build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-2p-tagcache-4477120.elf`, SHA-256 `c46ab77bca066ff3f6283bb011d8bef94c4cc5de5d0aa8d0dd8cbdf293b010b1`.
- Build report hashes: 4P `af1a132a0b9e1e16af3bae84df626fbb7a191e1bc75a18413963d2a8fda5e738`; 2P `f23210799016b3e4643bf2b22ae9bfe78a1abbc537814713b176822aeb44e8f5`.
- Both link summaries report 2,078,596 (4P) and 2,078,468 (2P) LOAD file bytes against the 2,097,152-byte diagnostic window; both have zero undefined symbols. BSS is not thereby accepted as physically budgeted; this image remains diagnostic.
- Source pins captured by the 4P build: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
- SHA-256: CE diagnostic source `d3f36c62a3915c4565b0ab8b21de05f540a650a6cb1d727636a4fc5ec12a21df`; closure `4aaa2fb86459d77e4a5527b1109558cfcc17190517fa55e9006ba59b7ff59c9b`; linker driver `21188c9068a30a0fb5b4bda3c1ce35902745de51aa48e757c80c9c7ea9f8d6be`; parent probe `459fd20d0ff3f39412d1aae2d63584239d9fc1ffb672e012a657227fe5e3d9e5`; make integration `2b584e9830676e02653420434875d86682ee6025dad8bd23976c92a6f4bc0c9f`; workload runner `b2e7c2a85f2c95da7104d77d0ebdb4821df5c41a53ea486ce8eeb95146179d80`; source test `00297e3d8774b7476802acd807fbabbb41e3958fe99efd3e2eaf725644e83d2a`; runner test `b280778daf06315ed9f51b82ee2e0e43aec71ee342c625a67007ff6a00626658`.

## Follow-up guest result

The four-player image was subsequently run successfully in PCSX2 recompiler and interpreter modes with desktop display access. Commands:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py --mode recompiler \
  --stage m3-memory-ready --success-marker 'step8-mp-workload-complete' \
  --timeout 180 --stable-seconds 2 \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-4p-tagcache-4477120.elf

APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_step8_mp_workload.py \
  --players 4 --mode interpreter --timeout 240 --stable-seconds 2 \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-4p-tagcache-4477120.elf
```

Both runs passed with identical CE workload assertions. Recompiler completed in 46.384 s; interpreter reached its stable marker in 85.704 s. The unchanged ELF SHA-256 is `c159c609f12c28a2532db848e5e699a64538fcdff8b27ee75e0907c47175541b`. CE produced four distinct live player/unit identities, three ticks, 94 objects/88 active, game-state peak 3,107,656 B with zero failures, nested object-pool peak 92,768 B with zero failures, and clean player/team/tag/scenario/BSP/collision teardown. The compatibility `dynamic_simulation` arena is separately owned and not included in those nested totals. Source pins remain parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. Recompiler result/guest-log SHA-256 `f1134c273bce827da8884c8dae80170845fdc8a701436a9fe0a7135076571c72` / `968869907e432bbf81a9c9aef8507298bd3019a3bdccff1f436556b2fc6398f7`; interpreter result/guest-log SHA-256 `706c973eb040696c35c13e9ab813b80005f3650fce15bf8671284b5c6471c529` / `96298193eb2eb8d6db250288e221df2f4f37e080ae20de4c55d9f0a334c076ce`; validated wrapper output SHA-256 `e7ff8da70e9aede4316127a673d9f9db438360d0aec7197bca3d06a2a8cd2389`. These supersede the prior “guest result pending” note above. They verify only one four-player local Sidewinder workload point—not bots, network co-op, combat/effect/animation churn, all-map residency, retail EE timing, or production arena capacity; Step 8 remains open.
