# M2 cache publication, BSP ownership, and retry audit

Audit date: 2026-10-21  
Scope: report-only trace of CE tag/scenario publication, the PS2 cache adapter,
the parent HP2/CTAG map service, failure/retry boundaries, and targeted
host/guest fixture gaps. This report does not change implementation or the
authoritative M2/M4 plan.

## Executive result

The normal PS2 local-map path has a deliberate safe reuse order: main requests
and preflights a map; for an already loaded map it calls `game_unload()` and
`game_dispose_from_old_map()`; `scenario_unload()` first tears down tag-dependent
CE systems, clears CE scenario/BSP globals, then asks the PS2 cache owner to
unmount; only afterward does the next cache request invoke the parent map
loader. The map service refuses to read/stage over an active different owner,
and same-map preflight records only a deferred reload request, without touching
the active arena. These properties are source-visible in
[`main.c`](../../submodules/halo-ce-universal/source/main/main.c#L2867),
[`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370),
[`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L230), and
[`ctag_mount.c`](../../src/stream/ctag_mount.c#L277).

The latest host integration fixture exercises a useful but narrow post-unload
failure: it injects a one-byte-then-EOF fault while the parent is re-reading the
HP2/HMAP section during deferred preflight, before a new mount or cache image is
published, then proves a same-process preflight/load/unload retry. It does not
test CE's tag/BSP cache-read failure path. The source contract appears designed
to terminate correctly: `cache_file_read()` initializes completion to
`_cache_file_read_failed` (numeric value 2), which is nonzero but not `TRUE`, so
CE's `while (!read_complete)` exits and the subsequent `read_complete != TRUE`
check rejects the map. The M2 gap is therefore a missing runtime/fixture proof
of that sentinel behavior (including the PS2 compiler ABI), not evidence of an
infinite wait. See
[`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1261)
and [`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375).

There is also one teardown detail the lifecycle fixture should explicitly
classify: `scenario_tags_unload()` clears `tags_loaded`, `global_tag_instances`,
and `global_tag_count`, but does not clear `cache_file_globals.tag_header`;
after parent release that field can still point into the tag arena which is
eligible for overwrite. Current tag accessors mostly gate on `tags_loaded`, but
the retained pointer is a stale internal reference and should be audited or
cleared before the arena-reuse contract is called complete. The fixture currently
checks the public globals and tag-loaded bit, not this field.

## Ownership and publication layers

There are four distinct lifetimes; treating “map loaded” as one boolean obscures
important failure boundaries.

1. **Preflight/staged request (private, not published).**
   `hcu_map_service_preflight()` looks up the catalog entry, enforces the current
   UI-only capacity gate, opens a source reader, temporarily allocates/decodes
   HMAP/CTAG/CRNG/CBIX into the streaming map arena, validates the identity,
   extents, CTAG envelope and full source hash, then rewinds the arena to its
   mark. It retains only the source/identity and staged-map flags on success;
   the temporary package sections are not the mounted cache owner. Failure
   closes the reader and clears staged identity. `load_section()` also has a
   local arena mark for rejecting an invalid CBIX result.
   Source: [`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L230),
   especially lines 268–322.

2. **Mounted parent owner (CTAG bytes plus resource-reader callback).**
   After CE requests a cache map, `map_loader()` consumes the staged entry and
   calls `ctag_mount_hp2_verified_source_discover()`. The mount transaction
   loads CTAG and CRNG into the owner arena, registers the PS2 backend and
   resource callback, then loads CBIX and registers the BSP loader. Payloads
   must be within the arena transaction. Any failure unwinds the transaction;
   successful mount retains the map arena range and source reader for later
   resource reads. The HCU map service then closes/clears its preflight source
   bookkeeping only according to the mount result; in this verified-source
   path, the mount owns the callback context until unmount.
   Sources: [`ctag_mount.c`](../../src/stream/ctag_mount.c#L112),
   [`ctag_mount.c`](../../src/stream/ctag_mount.c#L199),
   [`ctag_map_source.c`](../../src/stream/ctag_map_source.c#L127), and
   [`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L95).

3. **CE tag-cache image and published tag table.**
   `cache_files_precache_map_begin()` calls the registered loader only when no
   payload is mounted, and reports success only if the loader's success result
   is followed by `cache_files_precache_map_loaded(map_name)`. `cache_file_open()`
   constructs the CE-compatible header over the mounted CTAG metadata. In
   `scenario_tags_load()`, CE validates that header, poisons the destination tag
   arena with `0xCD`, synchronously materializes CTAG into that fixed tag-cache
   address, checks the tag header and schema, and only then publishes
   `cache_file_globals.tag_header`, `global_tag_instances`, `global_tag_count`,
   and `tags_loaded=TRUE`. Source:
   [`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L331)
   and [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1214).

4. **CE scenario/BSP pointers.**
   `scenario_load()` obtains the scenario definition from the published tag
   table and invokes `scenario_switch_structure_bsp(0)`. The BSP cache is
   poisoned, materialized in the separate structure-BSP arena, CE validates its
   signature/ranges/schema and port fixed-array capacity, then `scenario_switch`
   publishes the structure, collision and BSP3D globals and indices. The BSP
   tag instance's `base_address` is installed after CE BSP validation; the
   global BSP pointers are installed after the loader and capacity gate succeed.
   Sources: [`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230),
   [`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1088),
   [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1376).

## Exact sequencing and when storage may be overwritten

### Initial or new-map startup

The local startup path first runs `ps2_cache_preflight_map(options.map_name)`.
On failure it reports an error and returns before unloading the current map.
On success it calls `game_unload()` and `game_dispose_from_old_map()` before
`game_precache_new_map()` and `main_new_map()`. The main startup path is at
[`main.c`](../../submodules/halo-ce-universal/source/main/main.c#L2867); the
corresponding existing-game transition is at
[`main.c`](../../submodules/halo-ce-universal/source/main/main.c#L1557).

For a currently loaded game, `game_unload()` calls `scenario_unload()` and then
clears `game_globals->map_loaded`. `scenario_unload()` calls
`scenario_tags_unload()` first. That closes sound and texture caches and their
tag consumers, clears `tags_loaded` and the public tag table/count, then
`scenario_unload()` clears scenario/BSP/collision/BSP3D/game-global pointers
and indices. Only after this unpublication does the PS2 path call
`ps2_cache_release_map_owner()`. The parent unloader releases any mounted BSP,
unmounts the PS2 cache backend, closes the map source, rewinds the owner arena
to the mount transaction mark, and clears the mount record.
Sources: [`game.c`](../../submodules/halo-ce-universal/source/game/game.c#L741),
[`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L617),
[`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370),
[`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L158), and
[`ctag_mount.c`](../../src/stream/ctag_mount.c#L277).

Therefore the intended overwrite permission is not merely “the preflight
returned success.” The old mounted CTAG/CRNG/CBIX and reader may be overwritten
or closed only after `scenario_unload()` has removed every CE consumer and
`ps2_cache_release_map_owner()` has completed successfully. The BSP scratch
extent is separately reusable after CE disconnects/unloads the old BSP and the
mount's BSP-release callback clears its encoded CBSP staging. The tag-cache
destination may be overwritten only once CE has unloaded all tag users. In the
PS2 startup transition, the release call is the sequencing barrier between CE
unpublication and parent storage reclamation.

### Same-map reload (the particularly important case)

`ps2_cache_preflight_map()` invokes the parent preflight callback. If the exact
same map remains mounted, `hcu_map_service_preflight()` does **not** load sections
or read into the live owner arena: it stores the catalog entry/name and sets
`reload_pending`, then returns success. The subsequent `scenario_unload()`
releases the previous map while preserving that staged reload intent. The later
cache-loader callback rejects reload if either mount/source is still active;
after release, it repeats full preflight checks before it creates a new mount.
This prevents a “same map is already mounted” shortcut from bypassing post-
unload validation. Sources:
[`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L254),
[`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L95), and
[`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L158).

For a different map while an owner is active, current preflight rejects rather
than overwriting or trying to reuse it. This is consistent with the single
mounted CE tag image/parent map owner design, but means transitions must follow
the explicit unload barrier.

## Callback and completion semantics

### CE precache callbacks

`cache_files_give_time_to_precache()` is not a success value for its first
request: when nothing is loaded, it calls `cache_files_precache_map_begin()` and
returns the local `result`, which remains false. The caller polls again; once
`cache_files_precache_map_loaded()` is true, it returns true. The PS2 adapter is
synchronous: `cache_files_precache_in_progress()` always returns false, and
`cache_files_precache_map_begin()` calls the parent loader directly. It treats
the loader's integer as a success boolean, then independently checks that the
requested name is mounted. The HCU `map_loader()` currently maps the mount API's
`0 == success` convention to callback `1 == success`; on mount failure it
returns `0`. This inversion should remain explicit in tests to avoid an easy
success/failure polarity regression.
Sources: [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1164),
[`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L293),
[`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L331),
[`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L129).

### `cache_file_read()` callback contract

The adapter is synchronous even though it uses CE's historical completion
pointer API. It first writes `_cache_file_read_failed` (value 2) to the
completion flag, performs a bounded synchronous CTAG/CBSP materialization or
resource-source read, and sets completion to `TRUE` (value 1) only on success.
Because CE `boolean` is an unsigned byte and 2 is nonzero, its wait loop stops
for failure, while its explicit `!= TRUE` check distinguishes failure from
success. It returns `NONE` in both the success and failure cases; the completion
flag is the only result signal.
For a CBSP request, it loads the one exact catalog extent via the registered
callback, materializes it in current-BSP memory, releases the encoded scratch
payload, and sets completion true on success. A failed BSP loader/materializer
leaves completion false.
Source: [`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375).

CE's `scenario_tags_load()` and `scenario_structure_bsp_load()` both call
`cache_file_read(..., blocking=TRUE)` and then busy-wait while completion is
false. The distinct value 2 exits that loop, and the later `read_complete !=
TRUE` branch rejects the failed read. Tag failure closes the cache file and
returns `NONE` before publishing the new tag table. BSP failure returns false
before setting the BSP tag instance's `base_address` or cache-global BSP header.
The call sequence is therefore source-consistent with a bounded failure; the
unproven points are target ABI behavior, whether every failure branch preserves
this sentinel, and arena/pointer cleanup during the ensuing same-process retry.
Sources: [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1263)
and [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1423).

No interface redesign is recommended from source inspection alone: the existing
`_cache_file_read_failed=2` convention is explicitly documented in
[`cache_files.h`](../../submodules/halo-ce-universal/source/cache/cache_files.h#L24)
as nonzero so the wait ends, but not `TRUE` so callers can reject it. Preserve
this distinction and add execution assertions on both host ILP32 and R5900.

## Publication rollback and no-map/retry state

### Failures before new mount publication

The current tested post-unload fault happens in parent deferred preflight while
reloading HMAP after a one-byte read. `hcu_map_service_preflight()` releases its
temporary map-arena allocations, closes the source reader, clears staged map
identity, and returns false. The CE pre-cache flow observes the failed begin and
calls the damaged-media callback. Because CE already unloaded the previous map,
there should be no active scenario/BSP globals, no mounted cache payload, no
active mount/source reader, and no arena owner bytes. The same-process fixture
then runs fresh preflight and load successfully. This is an important recovery
case: the prior map is intentionally not restored after an unload has already
completed; the safe result is “no map published,” not stale old pointers.

The production service also unwinds later mount-time failures: transaction
allocations are released, backend mount state is cleared if mount fails, and a
catalog/register failure calls `ctag_mount_unload()` to reverse the backend and
owner allocations. BSP section loading uses a separate scratch arena and releases
the preceding staged BSP before loading the next; failure releases the new
scratch mark. Sources: [`ctag_mount.c`](../../src/stream/ctag_mount.c#L54),
[`ctag_mount.c`](../../src/stream/ctag_mount.c#L67),
[`ctag_mount.c`](../../src/stream/ctag_mount.c#L123), and
[`ctag_mount.c`](../../src/stream/ctag_mount.c#L238).

### Failure after bytes were written into the CE tag/BSP destination

The loader/materializer itself writes only into fixed tag-cache/current-BSP
destinations after preflight/mount. The destination is poisoned before loading;
the tag table/tag-loaded flag and BSP tag `base_address`/global structure
pointers are published after validation. Thus a failure can leave junk or
partial bytes in a destination without making them a valid CE map, provided the
read callback terminates and no earlier pointer was published. `scenario_load`
returns false if tag loading fails or BSP 0 cannot be loaded; `game_load` only
sets `game_globals->map_loaded` after `scenario_load` returns true. The caller
must still keep the start/menu transition on an explicit no-map failure path.
Sources: [`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230),
[`game.c`](../../submodules/halo-ce-universal/source/game/game.c#L609), and
[`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1477).

The host fixture's successful retry proves only the *preflight* failure/retry
case. Do not cite it as proof that post-unload CE tag-read, post-unload BSP-read,
tag-schema failure, or BSP-schema failure can recover, even though the source
uses a terminal sentinel to make those paths return rather than wait forever.

### Stale header pointer nuance

`scenario_tags_unload()` calls all tag consumers' unload hooks, closes the cache,
then sets `cache_file_globals.tags_loaded=FALSE`, `global_tag_instances=NULL`,
and `global_tag_count=0`; it does not set `cache_file_globals.tag_header=NULL`.
`scenario_unload()` subsequently clears the scenario globals before parent
release. On reload, the old `tag_header` can therefore still alias tag-cache
memory once it is eligible for overwrite, until a later successful load assigns
the field again. The normal tag-table lookup path gates on `tags_loaded`, and
tag-groups checksum asserts `tags_loaded`, but the pointer is not mechanically
cleared at the ownership boundary. This should either be fixed with a clear on
unload or explicitly proven safe for every rooted use; a fixture should assert
the chosen contract. Sources:
[`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L617),
[`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L696),
[`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L378).

## Halo-64 comparison (limited relevance)

Halo-64 demonstrates a different adapter contract rather than a direct template
for this ownership protocol: its `cache_files_precache_map_loaded()` and
`cache_file_open()` are unconditional success stubs, and its `cache_file_read()`
sets completion true without copying data. The actual map bytes are owned by
`n64_map_load()` and `n64_cache_file_tag_header()` in the N64-specific game
layer. Those choices suit that port's altered map/capacity path and cannot
validate HCU PS2's bounded CTAG/CBSP source, callback lifetime, or recoverable
read failures. Use Halo-64 only as evidence that a platform adapter may
explicitly define its completion semantics; do not port its unconditional
success behavior. Source:
[`n64_game.c`](../../submodules/halo-64/port/n64/game/n64_game.c#L1239).

## Existing evidence and explicit limits

`tests/test_hcu_ce_map_lifecycle.py` links the production CE
`scenario_load()/scenario_unload()`, tag file support, PS2 cache adapter,
production parent map service/catalog/CTAG mount/source, and halo-ps2 HP2/file
readers. It retains a host ILP32 executable, linker map, runtime log, and a
manifest with source pins and hashes. Its paired C fixture wraps the exact
`ps2_cache_release_map_owner()` boundary and asserts that CE scenario/BSP
globals, indices, `tags_loaded`, tag table pointer and count are cleared before
the parent release. It also verifies that same-map preflight leaves the old
owner and published CE pointers unchanged, injects a post-unload one-byte/EOF
failure during HMAP preflight, asserts clean owner/source/cache state, and
successfully retries in the same process. See
[`test_hcu_ce_map_lifecycle.py`](../../tests/test_hcu_ce_map_lifecycle.py#L17)
and [`hcu_ce_map_lifecycle_main.c`](../../tests/hcu_ce_map_lifecycle_main.c#L23).

The retained manifest is under `build/m2-ce-map-lifecycle-host/manifest.json`;
the test's report and status should be cross-checked against the exact current
manifest before quoting hashes because this worktree and both submodules are
dirty. The test explicitly labels itself as host-capacity/lifecycle semantics,
not a PS2-memory assertion.

Still absent from this proof:

- a terminal failure injected through **CE `cache_file_read()` for tag data**;
- a terminal failure injected through the exact **CBSP loader/materialization**
  path, including arena cleanup and no tag/global publication;
- tag-header/schema rejection after destination overwrite, followed by same-
  process retry;
- BSP signature/range/schema/capacity rejection, then retry and proof of clean
  `cache_file_globals.structure_bsp_header` and tag-instance `base_address`;
- tests for all callback result polarities (mount success/failure, loaded map
  check, sync read success/failure, BSP load/release) and descriptor lifetime;
- guest/PCSX2 evidence for the actual post-unload read paths and useful failure
  diagnostics. Existing guest memory-ready evidence does not prove a CE map
  read or rendered scene.

## Concrete next fixtures and acceptance criteria

1. **Tag read terminal-failure fixture.** Wrap the mounted source read callback
   used by `cache_file_read()` and fail/short-read the tag extent. After adding a
   terminal synchronous failure status, assert CE returns from
   `scenario_tags_load()`/`scenario_load()` (no unbounded loop), leaves
   `tags_loaded==FALSE`, public tag globals cleared, no `game_globals->map_loaded`,
   and no mounted/active owner leak. Retry with fault disabled and load the
   same map successfully.
2. **BSP failure fixture.** Independently fail the CBSP section read, then
   corrupt the materialized BSP signature, then force tag/BSP schema or port
   capacity rejection. Assert no global BSP/collision/BSP3D publication, no
   BSP tag `base_address`, scratch/owner marks returned to expected values, and
   bounded no-map return. Retry the valid same extent in-process.
3. **Owner-boundary assertions.** At the wrapped release seam, assert both
   public CE pointers and relevant internal cache bookkeeping are either NULL
   or explicitly documented as non-dereferenceable. In particular decide and
   test `cache_file_globals.tag_header`; verify cache close state and
   `cache_file_globals.structure_bsp_header` behavior.
4. **Allocator overwrite sentinel.** Fill former CTAG/CBIX and BSP scratch
   allocations with sentinels, unload, then mount a different valid package
   that reuses the exact spans. Assert reuse occurs only after CE unpublication,
   the new structures validate, and no held prior pointer is dereferenced.
5. **Guest boundary.** Run the same profile on the exact current production ELF
   in PCSX2 interpreter and recompiler. Record source pins/ELF/asset hashes;
   require deterministic no-map behavior and a useful failure log for injected
   file fault, then successful retry. A normal successful map-load and render
   remain separate M2/M3 acceptance gates.

The current host lifecycle test should continue to be reported as a meaningful
positive result, but M2 map-failure handling must remain open until the failed-
completion sentinel is exercised through real CE tag and BSP read paths and the
tag/BSP rollback/retry fixtures pass.
