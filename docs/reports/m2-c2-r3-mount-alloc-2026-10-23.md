# M2 C2 r3 mount-alloc evidence (2026-10-23)

Lane: mount-alloc (C2.4 live path, C2.5). Build dir: `build/m2-c2-r3-mount-alloc/`.
Machine-readable inventory: `docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json`.

## Result

| Requirement | Result | Evidence |
| --- | --- | --- |
| C2.4 CE tag/BSP reads through segment pin, bounded slots, gameplay refs, busy unload | partial | Bound mounts pin per segment; `ui` fixture passes with lease/pin/evict gates. Map service is not yet bound (cross-lane), and source reads from the map file are not segment-pinned. |
| C2.5 post-load allocation verdicts for 22 candidate and 38 unknown sites | partial | 60 of 60 sites have a verdict. 26 are not closed: 9 recurrent-open, 17 unknown-open. 8 are cross-lane-open. |
| Focused tests and EE compiles | pass | See the command list below. |

## Task 1: segment residency on the mount path

Changes in `src/stream/hcu_profile_mount.{c,h}`:

- `hcu_profile_mount_bind_residency()` takes caller-owned entries and a 16-byte-aligned arena of whole 64 KiB slots. It must run before prepare. Prepare copies the binding and rejects an arena that overlaps relocation, scratch or profile spans.
- Bound mounts stream CE and CBSP chunks through `pinned_walk()`. Pass 1 pins and hashes every segment with no sink call. Pass 2 pins each segment, sinks pieces of pinned bytes, marks the segment as a gameplay reference on first CE use, and unpins. A failed pin never reaches the sink.
- Unbound mounts keep the previous direct-read path. This keeps `hcu_map_service.c` and `tests/test_hcu_profile_metadata.py` working. The map service must call bind before prepare; that is a cross-lane change.
- `hcu_profile_mount_unload()` returns BUSY before any teardown while any segment has a pin or lease. It then unmounts the backend, drops gameplay references, evicts every segment, and clears the mount.

Interpretation to review: the requirement says unload refuses while a gameplay reference remains. A reference held by the loaded map would then block unload forever. This implementation treats gameplay references as owned by CE and releases them only after the backend is unpublished. Leases and pins are the refusal gates.

Budget note: for the UI profile, CE retains 13 segments (799,229 bytes) for map lifetime. The test arena is 16 slots (1,048,576 bytes). Production placement must count this arena once inside the map/render backing. The C2 budget owner must account for it. No committed-budget number is changed here.

Test changes in `tests/hcu_profile_mount_main.c`:

- The CE corruption check moved ahead of the first CE read. Residency serves verified bytes after first read, so a later flip would otherwise go unseen.
- New cycle-0 gates: lease makes unload return BUSY with the mount still active. A read still works while leased. Release, then pin, makes unload BUSY again. Unpin, then evict with a gameplay reference returns BUSY. Drop the reference, then evict returns the arena slot. A reread re-pins it.

## Task 2: post-load allocation inventory

`tools/audit_hcu_postload_allocations.py` now contains the phase classifier formerly in `build/m2-c2-chunks-alloc/classify.py`. Each record carries `enclosing_function`, `phase_classification`, `phase_basis`, and, for non-load sites, `verdict` and `verdict_basis`. Verdicts are keyed by `path:line:api`. A drifted line reads as `unverified`, which happened for 6 sites when other lanes edited the shared worktree.

Verdict counts over the 60 non-load sites:

- load-only: 6, with a cited chain. Examples: `shell_initialize` -> `real_math_initialize` -> `random_math_initialize` -> `geosphere_new` -> `subdivide_triangle`; `hcu_map_service_preflight` -> `verify_source_hash`; `game_initialize` -> `objects_initialize` -> `object_name_list_allocate`.
- unreachable-selected-build: 20. Callers exist only in excluded trees (`source/networking`, `source/tool`, `bitmaps/bitmap_extract.c`), or none exist in the selected tree. The hashtable chain has no caller from `hashtable_put` onward. Several symbols are absent from the stale baseline link map at `build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.map`. That map is stale, so these are not current-link proofs.
- recurrent-open: 9. Not moved to scoped storage in this lane. Five are in files this lane owns: `hs_compile.c:934` and `:1007` (cheat and console command compile), and `debug_memory.c:499`, `:548`, `:590` (debug heap routes to the PS2 SDK heap). Four are in `memory_pool.c` (`:280`, `:284`) and `objects.c` (`:787`, `:811`), reached from `object_new` (`objects.c:3711`) during gameplay.
- cross-lane-open: 8, in `hcu_main.c`, `hcu_map_service.c:187`. Not owned by this lane.
- unknown-open: 17. Caller chains not traced in this pass. Includes `files.c` `file_read_into_memory`, `game_state_xbox.c` save-read paths, `stack_memory_pool`, `lruv_delete`, `cseries_windows.c`, and `mem.c`.

Remaining work that this lane did not do: move the 9 recurrent sites to preallocated or scoped storage with tests, and trace the 17 unknown chains.

## Task 3: tests and compiles

Commands and outcomes:

- `HCU_C1_PROFILES=build/m2-c2-hcp2-primary HCU_C1_REBUILD=build/m2-c2-hcp2-rebuild HCU_PROFILE_MOUNT_ARTIFACTS=build/m2-c2-r3-mount-alloc/pm python3 -m pytest tests/test_hcu_profile_mount.py -k ui -q` -> `1 passed, 2 deselected`. Run log: `build/m2-c2-r3-mount-alloc/pm/run.log`, which includes `residency=pinned+leases-gate-unload+evict-after-release`.
- `python3 -m pytest tests/test_hcu_asset_residency.py -q` -> `4 passed`.
- `python3 tools/test_hcu_ps2_malloc_diagnostic.py` -> exit 0, `failures=3 free=coalesced-reuse rebind_reset=passed`.
- `python3 tools/test_hcu_ps2_malloc_endless.py` -> exit 0, `ops=2000000 failures=0 fragmentation_failures=0 sdk_fallbacks=0`.
- `python3 tools/test_hcu_mp_production_bind_capacity.py` -> exit 0, `ready=1 candidate_fit=0` for the default binder; recarved and profile-v1 rows ready.
- EE compile with `build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-gcc -std=gnu89 -Os -mabi=n32 -G0 ...`: `hcu_profile_mount.o`, `hcu_asset_profile.o` and `ps2_memory.o` all exit 0 and land in `build/m2-c2-r3-mount-alloc/ee/`. The two owned files compile without warnings. `ps2_memory.c` has pre-existing ISO C90 and xdk warnings only.
- `git diff --check` is clean for the owned repo files and in `submodules/halo-ce-universal`.

Not run or failing:

- `tests/test_hcu_profile_metadata.py` with the default C1 v3 corpus fails with `HCP media chunk exceeds 65536-byte decoded limit` at `tools/hcu_profile_validate.py:205`. That file is modified by another lane. With `HCU_C1_PROFILES=build/m2-c2-hcp2-primary HCU_C1_REBUILD=build/m2-c2-hcp2-rebuild` it passes, 3 of 3.
- The marine-shotgun and mounted-gunner parameters of `test_hcu_profile_mount.py` were not run. Those belong to the selected-packages lane.

## Cross-lane changes needed

1. `src/stream/hcu_map_service.c`: call `hcu_profile_mount_bind_residency()` before `hcu_profile_mount_prepare()` at lines 409 and 522, and size the arena inside the map/render backing.
2. `src/stream/hcu_main.c`: confirm the seven `arena_alloc` sites in `main()` run once at startup, and record that for C2.5.
3. `objects.c` and `memory_pool.c`: move `object_header_block_allocate` and its pool reallocate/free to preallocated storage, since object spawn runs during gameplay.
4. `source/memory/data.c`: no callers in the selected tree, so the sites are unreachable. Record that in the owner's ledger.
5. `tools/hcu_profile_validate.py`: the default C1 v3 corpus no longer validates against the HCP2 rule. Refresh the default corpus pins.
