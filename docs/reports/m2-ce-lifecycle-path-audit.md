# M2 CE scenario lifecycle path audit

**Purpose:** report-only investigation for `plans/7.hcu-remake-m2-m4.md` M2
Steps 2, 8, and 9. This report maps the actual CE unload/load path to the
parent-owned CTAG/HP2 owner, identifies the current evidence boundary, and
specifies the smallest useful guest lifecycle fixture. It does not change
runtime code or claim that the lifecycle fixture has been implemented.

## Finding

The production ordering for a *loaded* map has a deliberate ownership handoff:
CE unloads its map-level tag and cache state, clears scenario/BSP globals, then
calls the PS2 cache-owner release callback. The parent callback unmounts the
CTAG/CBSP owner, closes its source, and rewinds the map arena. The next map load
goes through `game_load()` → `scenario_load()` → `scenario_switch_structure_bsp(0)`;
the PS2 cache callback materializes CTAG and the requested BSP into their
configured fixed regions. This is the right shape for the owner boundary, but
there is not yet an end-to-end test proving that CE globals are null before
release, arena `used` returns to its original baseline, and a new scenario can
load successfully in the same guest process.

There is an important transition constraint in the current code: the parent
preflight rejects a request while the current map is mounted, even though CE's
normal `main_load_ui_scenario()` and local map-change paths call preflight
*before* `game_unload()`. In particular, `hcu_map_service_preflight()` returns
false when `service->mount.active` or `service->source.active` is set
([`hcu_map_service.c:172-187`](../../src/stream/hcu_map_service.c#L172)). The
preflight itself stages full HP2 metadata sections in the shared streaming
arena ([`hcu_map_service.c:200-230`](../../src/stream/hcu_map_service.c#L200)),
which is nearly full while UI is mounted. This currently prevents proving a
preflight-while-old-map-live/rollback transaction. Do not describe that
rollback as implemented. A feasible minimal positive test is an explicit
unload-to-baseline followed by a fresh UI preflight/load in the *same process*;
if that post-unload operation fails, the correct safe result is an explicit
unmounted/menu-or-fatal state with no stale CE pointers, not continued use of
the old map.

## Source path and ownership order

1. `game_unload()` calls `scenario_unload()` only when
   `game_globals->map_loaded` is true, and clears `map_loaded` after the
   scenario call ([`game.c:741-772`](../../submodules/halo-ce-universal/source/game/game.c#L741)).
2. `scenario_unload()` calls `scenario_tags_unload()` first; then resets
   `global_scenario_index`, `global_structure_bsp_index`,
   `scenario_globals->structure_bsp_index`, `global_scenario`,
   `global_structure_bsp`, `global_collision_bsp`, `global_bsp3d`, and
   `global_game_globals`; only after those unpublishes does the `HALO_PS2`
   branch call `ps2_cache_release_map_owner()` and assert success
   ([`scenario.c:364-388`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L364)).
   `scenario_tags_unload()` closes sound/texture caches, closes the cache file,
   deregisters tag buffers, and clears `tags_loaded`, `global_tag_instances`,
   and `global_tag_count` ([`cache_files.c:617-655`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L617)).
3. `ps2_cache_release_map_owner()` is a no-op success if there is no mounted
   payload; otherwise it invokes the registered parent unloader and then
   requires that the cache payload was cleared
   ([`ps2_cache.c:179-185`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L179)).
4. The registered `map_unloader()` calls `ctag_mount_unload()` for an active
   mount, or closes a staged active source, then clears preflight/staged-map
   state ([`hcu_map_service.c:119-130`](../../src/stream/hcu_map_service.c#L119)).
   `ctag_mount_unload()` releases a mounted BSP, unmounts the CE cache before
   releasing backing bytes, closes the file source, and rewinds the owner to
   its saved mark ([`ctag_mount.c:277-290`](../../src/stream/ctag_mount.c#L277)).
5. For load, `game_load()` sets the selected options and calls `scenario_load()`;
   a successful first BSP switch makes `game_globals->map_loaded` true
   ([`game.c:609-645`](../../submodules/halo-ce-universal/source/game/game.c#L609)).
   `scenario_load()` finds the scenario tag and loads BSP 0 before returning
   true ([`scenario.c:1204-1251`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1204)).
6. CE's `main_new_map()` then calls `game_initialize_for_new_map()` and starts
   the local players/time after a successful load
   ([`main.c:1468-1490`](../../submodules/halo-ce-universal/source/main/main.c#L1468)).
   This is the correct production-level reload entry; directly calling only
   `scenario_load()` would not reproduce map-level game initialization and
   would be an insufficient lifecycle acceptance test.
7. The PS2 map-loader callback's integer convention is easy to misread: the
   underlying `ctag_mount_hp2_verified_source_discover()` returns `0` on
   success and `-1` on failure ([`ctag_map_source.c:127-153`](../../src/stream/ctag_map_source.c#L127));
   `map_loader()` translates zero into callback success (`1`) and a nonzero
   mount error into failure (`0`) ([`hcu_map_service.c:83-112`](../../src/stream/hcu_map_service.c#L83)).
   `cache_files_precache_map_begin()` expects a truthy loader result and then
   checks the published cache ([`ps2_cache.c:314-330`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L314)).
   A new fixture should assert this translation explicitly; it is not an
   inversion bug.

## Existing evidence and what it proves

- The retail UI host service fixture loads the actual UI package, validates
  HMAP/CTAG/CRNG/CBIX, materializes the UI CTAG and B000 BSP, and verifies that
  `ps2_cache_release_map_owner()` returns the streaming arena to zero and
  closes the source (`tests/ctag_mount_main.c:286-367`). The wrapper builds
  production parent/PS2 cache sources and the real package
  (`tests/test_retail_ui_ctag_mount.py:11-65`). It proves the parent callback
  and mount-owner path, but not CE `scenario_unload()` ordering, global pointer
  publication, map-level teardown, or a reload.
- `tests/ctag_mount_main.c:360-364` explicitly labels its release as “Match
  scenario_unload's post-unpublication owner release callback.” That is a
  consciously narrow host simulation, not a call into the CE lifecycle.
- The current PCSX2 test stage `m2-ui` is keyed to the single
  `HALO_PS2_LOCAL m2-ui-map-loaded` marker
  ([`test_hcu_boot.py:45-50`](../../tools/test_hcu_boot.py#L45)); the marker is
  emitted on first UI `game_load()` success
  ([`game.c:633-640`](../../submodules/halo-ce-universal/source/game/game.c#L633)).
  `boot_once()` stops PCSX2 after the marker is fault-free for the configured
  stability interval ([`test_hcu_boot.py:202-204`](../../tools/test_hcu_boot.py#L202),
  [`:311-320`](../../tools/test_hcu_boot.py#L311)). The harness does not ask
  the guest to unload, repeat the map load, assert arena baselines, or retain
  one process across cycles. Thus its current green M2 marker proves only the
  first scenario load.
- The current plan accurately leaves this open: Group A Step 2 says no CE
  unload/reload trace exists (plan lines 185-186); Wave 2 Steps 8-9 mark valid
  rebinding and full CE transaction coverage incomplete (plan lines 303-305).

## Smallest useful real integration fixture

The minimum strong fixture should be a diagnostic-only, compile-guarded guest
exercise using the *same combined production objects and map service*, not a
host reimplementation. Run it only after the initial UI `main_new_map()` has
completed, on CE's main/game thread, with UI as the only currently qualified
map. It should issue two unload/reload cycles and produce a structured marker
sequence. Do not invoke it recursively from `main_load_ui_scenario()` itself;
that routine already performs an unload/load transition. Trigger it from a
post-startup safe point or an explicit diagnostic command once the main loop is
running.

For each cycle `i`, the guest diagnostic should:

1. Record a cycle-start baseline: map-arena `used`, `high`, and `cap`; source
   open count or a parent source-open/close counter; mounted/cache-loaded state;
   `game_map_loaded()`; scenario/tag/BSP pointers; and CE tag table count. Keep
   `high` distinct from `used`: arena high-water is monotonic and should not be
   expected to return to baseline.
2. Call the normal `game_unload()` once. Verify and log that the map is no
   longer loaded, `global_scenario_index` and `global_structure_bsp_index` are
   `NONE`, `scenario_globals->structure_bsp_index` is `NONE`, all scenario/BSP
   globals are null, `cache_file_globals.tags_loaded` is false, and tag table
   pointer/count are null/zero. These values are expected after
   `scenario_unload()`'s exact order; only log them after `game_unload()` has
   returned.
3. Verify parent owner teardown: `service.mount.active == 0`,
   `service.source.active == 0`, no cache payload is mounted, and
   `service.map_arena->used == baseline_used`. Require balanced source open and
   close deltas. Log each as named booleans/values instead of one ambiguous
   “unloaded” marker.
4. Call the same production selection/re-entry path used by the menu (or an
   equivalent wrapper with the exact sequence): `ps2_cache_preflight_map()`
   after the old mount is gone; `game_dispose_from_old_map()`; synchronous
   `game_precache_new_map()`; then `main_new_map()` so that `game_load()`,
   scenario/BSP load, map initialization, and local-game setup all run. The
   existing menu path demonstrates those steps and their ordering
   ([`main.c:1918-1950`](../../submodules/halo-ce-universal/source/main/main.c#L1918)).
5. Require the second `game_map_loaded()` and non-null global scenario, BSP,
   collision BSP, and BSP3D pointers, matching UI map identity, CE tag table
   publication, cache-mount state, and a successfully materialized UI B000
   structure-BSP signature. Require no fault or `HALO_PS2_FAIL` after the
   cycle marker, and verify the map owner returns to the same `used` baseline
   at the *next* unload.
6. Repeat exactly once more (three successful loads total including startup)
   to expose stale callbacks, double-close, arena rewind accumulation, or
   single-use mount state. Emit a final marker only after the second reload
   and all checks have passed. On any post-unload error, stop into a specific
   fatal/main-menu diagnostic with all scenario globals null and all owner
   bytes released; never attempt to continue rendering through old pointers.

To reduce perturbation, the diagnostic should store the baseline and assertion
state in static globals allocated in the existing machine image, not in the
map arena. It should not use `malloc`/free after boot. Place canaries around
any newly added diagnostic state only if it has dynamic/arena-backed storage.
The UI package can exercise CE tag/BSP pointer lifetime and the parent owner
path; it cannot establish the larger gameplay-map RAM/high-water budget, which
remains M2 Step 10 and must be tested with the first supported gameplay map.

## Guest runner/harness proposal

The current `tools/test_hcu_boot.py` runner already captures exact ELF hash,
parent/HCU/halo-ps2 pins, PCSX2 mode/settings, guest log, and source asset
manifest (`:202-240`); its `--stage` selection and stable-marker loop are
documented in `:354-396`. Add a distinct stage such as `m2-ui-lifecycle` with a
new terminal guest marker (do not override `--success-marker` on the old
`m2-ui` stage). The test should:

- enable the lifecycle sequence only in a diagnostic HCU/PS2 build flag, or
  use a bounded explicit in-game/test command; never make the retail menu loop
  repeat forever;
- retain the full ordered `scenario-unload-begin`,
  `scenario-unload-published-null`, `map-owner-released`,
  `scenario-load-begin`, `scenario-load-success`, and final-cycle markers in
  the PCSX2 EE log;
- make the Python validator check cycle indices/order, exact baseline equality
  for `arena.used`, null/non-null transitions, mount/source state, balanced
  file handles, map identity, successful CE BSP marker, and absence of
  post-final-marker faults;
- capture a PCSX2 viewport after the final cycle, but classify a black capture
  separately from lifecycle success. Lifecycle evidence is not rendered-scene
  evidence;
- run the exact same ELF in interpreter and recompiler, record each result,
  log, settings, screenshot, host-root package hashes, and source pins. Keep
  one PCSX2 process alive for all cycles within each mode. The runner currently
  terminates the process after stable marker recognition, so a new stage must
  wait for the final lifecycle marker rather than the first UI marker.

The test may first use the host retail UI fixture for fast cleanup/failure
coverage. Keep the evidence labels explicit:

| Layer | Can prove | Cannot prove |
|---|---|---|
| Source/static test | Call/order invariants such as nulling globals before the owner callback; callback is registered; menu sequence invokes unload before reload. | That those code paths execute together or globals have expected values at runtime. |
| Host C integration fixture | Actual package parsing, parent owner/callback behavior, source close and arena rollback; can inject parent-side failures/retry. | CE `scenario_unload`, actual CE datum/tag globals, PS2 address-space effects, PCSX2 guest behavior. |
| PCSX2 combined-image lifecycle test | CE globals and parent owner interact in the real guest process; same-process UI unload/reload and stable arena `used` baseline in both interpreter and recompiler. | Physical PS2 acceptance, gameplay-map RAM fit, or visible scene rendering. |
| Physical PS2 plus qualified gameplay map | Hardware DMA/IOP/DVD behavior, actual game-map capacity and scene path. | Nothing less than the actual acceptance criteria for those claims. |

## Step 8 / Step 9 dependencies and acceptance

- **Step 8:** current evidence rejects late rebinding and does not define a
  post-unload span-change API. This UI lifecycle fixture should keep fixed
  boot-time physical spans; it must not mutate the tag/BSP backing addresses
  between cycles. The same host assertions at
  `tests/hcu_ps2_memory_main.c` can remain as a negative control that changed
  spans are refused. A production solution should define a fixed partition or
  a separately reviewed reconfiguration contract before testing a different
  map class. Rebinding is not needed merely to unload/reload the same UI map.
- **Step 9:** a successful same-process UI repeat test proves one real
  CE→parent teardown/load transaction on a fixed owner. It does not complete
  injected L0–L6 failure coverage or prove restoration of an old map after a
  late error. Test source/preflight rejection *before* unload with the old map
  still intact (host negative control already exercises preservation), and
  separately test deterministic no-map state if a failure occurs after unload.
  Do not claim rollback of the previous map unless a staging/dual-owner design
  can preserve all old CE pointers and bytes through candidate validation.
- Add a source regression asserting exact operation order from
  `scenario_unload()` (`scenario_tags_unload` → globals cleared → owner release),
  plus a guest marker assertion for those runtime states. The source test is a
  guardrail, not the lifecycle pass.
- Keep the catalog's gameplay-map capacity rejection in place. This fixture is
  for UI lifecycle only and does not relax Step 10's capacity qualification.

## Recommended concise acceptance record

For each mode, save ELF/source-pin hashes and a cycle table similar to:

| cycle | before used | after unload used | owner/source inactive | scenario/BSP globals null | reload marker | BSP materialized |
|---|---:|---:|---|---|---|---|
| startup → unload 1 | measured | measured | yes | yes | UI load 2 | yes |
| unload 2 | measured | measured | yes | yes | UI load 3 | yes |
| unload 3 | measured | measured | yes | yes | final stable marker | yes |

Pass requires all `after unload used == initial baseline`, all cleanup state
checks true, every same-process reload complete, zero file handle leak, no
post-marker guest fault, and identical pass criteria in interpreter and
recompiler. Include `arena.high` as a recorded high-water; it should be
nondecreasing and within capacity, not equal to the baseline.

This would close the specific missing lifecycle evidence called out by M2
Group A Step 2 and materially advance Wave 2 Steps 8–9. It does not close M2
overall: Step 10 still needs a supported gameplay-map memory design, measured
region peaks, and a successful guest load of that gameplay map.
