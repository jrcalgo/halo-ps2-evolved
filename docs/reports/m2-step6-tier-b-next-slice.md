# M2 Step 6: next practical Tier B integration slice

## Finding

The next useful increment is a single host fixture that keeps the real CE
`scenario_switch_structure_bsp()` and its real `scenario_structure_bsp_load()` /
`_unload()` bodies, while replacing the fixture's synthetic read/extent/tag
cache with the audited `a30` package, the real parent `ctag_mount` transaction,
the PS2 backend, and HCU's `ps2_cache.c` / `ps2_ctag.c` / `ps2_cbsp.c`. Keep
schema validation controllable for fault injection initially, but use CE's real
`structure_bsp_port_verify()` and real decoded BSP structures. This is the
smallest slice that closes the specific split identified by Step 6: package
selection and adapter rematerialization happen under the same CE switch that
publishes and rolls back the gameplay globals.

This is host integration evidence only. The already-used adapter fixture has
16 MiB tag and 8 MiB BSP arrays, and the Step 6 host fixture has synthetic
1 KiB/4 KiB spans; neither demonstrates an EE memory fit or a visible map.
The a30 scenario BSP extents themselves are 6,199,296 and 7,174,144 bytes in
the source file, so the encoded CBSP sections must be checked by decoded image
size, not mistaken for the reserved runtime BSP-cache capacity.

## What the current real-CE fixture establishes—and does not

The current harness includes the actual HCU `source/cache/cache_files.c`
translation unit (`tests/hcu_scenario_bsp_switch_main.c:1-8`) and invokes its
actual CE load/unload through the real `scenario.c` switch. It therefore
exercises CE's reference bounds/identity validation, BSP header checks,
schema-validation call, cache header publication, tag-instance base
publication, and vertex-buffer register/deregister call sites. The source
flow is visible in `source/cache/cache_files.c:1376-1509` and unload at
`:1512-1534`; the fixture asserts CE indices, globals, reference base,
tag-instance base, and current cache header (`tests/hcu_scenario_bsp_switch_main.c:246-269`).

But the critical inputs remain synthetic:

* `cache_file_read()` manufactures a BSP header and one collision block from
  two hard-coded offsets (`tests/hcu_scenario_bsp_switch_main.c:100-125`).
* `tag_validate_structure_bsp()` and `structure_bsp_port_verify()` are
  controlled stubs (`:93-98`, `:146-152`), so no actual structure invariant is
  checked.
* `reset_fixture()` directly sets private cache flags/header lengths and
  invents a two-record tag table and scenario references (`:197-224`). This
  bypasses CE's real tag publication in `cache_files.c:1310-1329`.
* The test asserts branch counts and rollback state across eight branches
  (`:271-324`), but the read, extents, tag datum identities, physical store,
  and package are not the audited retail ones.

The test runner builds with ILP32, section GC, and roots the real switch
function (`tests/test_hcu_scenario_bsp_switch.py:19-54`). It skips execution
when the sandbox blocks the native ILP32 process with SIGSYS (`:55-59`). This
is a useful control-flow harness, not yet a host pass in every environment.

## Reusable production path

The parent transaction already offers the right seam. `ctag_mount` discovers
the CTAG and CRNG extents, mounts the CTAG through a backend, loads the CBIX,
registers a lazy exact-extent callback, and unwinds owner memory if any stage
fails (`src/stream/ctag_mount.c:112-173`, `:199-235`, `:238-274`). On a BSP
read it finds the exact CBIX `(file_offset,file_size)`, excludes tag and
resource overlaps, releases any previous encoded BSP, loads the selected
section into the BSP scratch arena, mounts it, and retains a release mark
(`:67-104`). Unload releases the active encoded CBSP before unmounting CTAG
and rewinding its owner (`:277-290`).

`ctag_ps2_cache_backend()` directly wires those callbacks to the real
`ps2_cache_mount_ctag_with_file_source`, exact-extent CBSP mount, loader
registration, BSP unmount, and CTAG unmount (`src/stream/ctag_ps2_backend.c:5-52`).
HCU `ps2_cache.c` exposes the needed runtime boundary: it opens CE's cache
header from mounted CTAG metadata (`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:338-355`),
materializes the CTAG to the bound tag image (`:387-398`), selects the lazy
loader for a BSP request (`:358-385`), and materializes the chosen CBSP into
the physical BSP destination (`:399-419`). Exact CBIX extent matching and
tag-overlap/range checks are in `:219-250`; CBIX records are validated and
looked up by exact offset and length in `src/stream/cbsp_catalog.c:23-63,66-88`.

The separate package fixture already proves the materializer path against
real a30 CBSP payloads. It calls real PS2 cache/CTAG/CBSP C, mounts real CTAG,
loads BSP 0, then BSP 1 into the same destination, verifies the old BSP can
be re-materialized byte-identically, and counts release callbacks
(`tests/ps2_cache_cbsp_retail_main.c:70-129`; runner and package hash checks in
`tests/test_cbsp.py:253-315`). The audited package and source identities are
`ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` and
`287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`;
CBIX `B000` is `(2048, 6199296)` and `B001` is `(6201344, 7174144)`
(`docs/reports/retail-scenario-bsp-reference-audit-2fba411b.json:117-147`).
The fixture's explicit disclaimer correctly says it does not run CE switch
control flow (`tests/test_cbsp.py:253-258`). Combining it with the current CE
fixture is the next step; do not treat either in isolation as that combination.

## Minimal integration seam and test-only closure

Keep production files unchanged for the first integration pass. Extend the
existing host fixture/test pair, or create a new uniquely named Tier B test
pair if its compilation environment cannot support both closure sets. The
minimal conceptual link closure is:

1. **CE transaction:** `source/scenario/scenario.c` rooted at
   `scenario_switch_structure_bsp()` plus the already-included real
   `source/cache/cache_files.c`. Keep the existing lifecycle/disconnect
   callbacks as counters. Add `source/structures/structure_bsp_definitions.c`
   so `structure_bsp_port_verify()` is real; it requires a valid collision
   BSP, a nonempty bounded cluster block, bounded surfaces, and enough cluster
   PVS/sound-cluster data (`structure_bsp_definitions.c:26-43`). Avoid rooting
   general drawing or gameplay modules by preserving `--gc-sections` and
   providing narrow test leaf shims.
2. **PS2 cache image:** compile `port/ps2/src/ps2_cache.c`, `ps2_ctag.c`, and
   `ps2_cbsp.c` with the existing cache test shim (`tests/hcu_ps2_cache_shim/`);
   provide the CE physical-memory accessors over bounded host arrays. The
   existing package test already demonstrates these three files compile and
   run together (`tests/test_cbsp.py:298-315`).
3. **Parent package ownership:** compile `src/stream/ctag_mount.c`,
   `ctag_ps2_backend.c`, `cbsp_catalog.c`, and the HP2/package reader required
   by the selected loader callback. Provide two disjoint bounded test arenas,
   an `a30.hp2` section loader, and a read-at source callback. For a deterministic
   first pass, load the package bytes into the test process and use the
   production HP2 open/find/load routines; do not depend on FileXio or the
   runtime map-service singleton. Ensure the section loader returns each
   decoded section within the arena mark passed to it, as `ctag_mount` rejects
   results it cannot prove are transaction-owned (`ctag_mount.c:128-150,216-223,258-261`).
4. **CE tag-table state:** remove direct writes to `cache_file_globals.tags_loaded`,
   `header`, `global_tag_count`, and the standalone `tag_instances` array.
   After mount, call actual HCU `cache_file_open()` and actual CTAG
   `cache_file_read()` into the fixture's tag-cache span. Initialize/publish
   CE cache state from the materialized tag header and tag instances using a
   narrowly scoped test helper at the same state boundary as CE's
   `scenario_tags_load()` publication (`cache_files.c:1310-1329`). The helper
   must validate header signature, scenario datum range, and tag-table extent;
   it must not synthesize reference extents. First establish that the
   materialized header's `tag_instances` pointer/index representation matches
   the ILP32 host address model. If the package materializer's address rebasing
   prevents a host pointer view, adapt only the test boundary by decoding the
   CE tag-instance records into host-addressable records while retaining real
   file offsets, file sizes, datum identities, and group tags from package CTAG.
   Record this as a host adapter, not as target-execution evidence.
5. **Scenario references:** populate the actual CE reference objects from
   package-derived CTAG scenario data and verify each's datum/tag path and
   exact offset/size against CBIX before calling the CE switch. Prefer parsing
   the materialized scenario tag with production tag structures. If that
   requires too much schema closure, a fixture decoder may project the exact
   fields from the package after checking them against the independent audit;
   such a decoder is an explicit test shim and must not replace the source of
   truth with a hand-written constants table. The two audited records and
   section tags are in the report lines cited above.
6. **Fault points:** retain `tag_validate_structure_bsp()` as a controlled
   schema-validation leaf for this slice, but make it fail based on the
   materialized BSP datum and assert call inputs. Inject read/decode failure
   through the section loader, CBSP mount/materialization failure through
   corrupt candidate bytes, real `structure_bsp_port_verify()` rejection
   through an invalid-but-bounded BSP fixture or a narrow wrapper, and old
   reference reload failure through the loader. Do not fake `cache_file_read`
   or the parent `load_bsp_extent` path.

The critical initialization detail is CE's real load path calls
`cache_file_structure_bsp_reference_verify()` when custom-edition cache mode
is false (`cache_files.c:1401-1405`), then `cache_get_tag_instance()` and
expects an empty base pointer and `STRUCTURE_BSP_TAG` before publishing
(`cache_files.c:1497-1508`). Therefore the tag header/table and the scenario
reference indices must agree. Setting `tags_loaded=TRUE` plus two ad hoc
records, as the current fixture does, bypasses precisely the real identity
and ownership setup Tier B must now validate.

## Required transaction assertions

Run at least these states with the package and all three ownership layers in
the same process:

1. Mount a30; open its CE cache header; materialize CTAG; assert header image
   size, scenario datum, tag count/table bounds, and source/package hashes.
2. Load real reference 0 (`B000`) through CE. Assert the parent's CBIX callback
   selected only `(2048,6199296)`, the cache adapter materialized into the
   stable BSP span, CE's cache BSP header and tag-instance base point into that
   span, and CE globals/index identify BSP 0.
3. Switch 0→1. Assert the old cache/tag base was unpublished before shared
   storage overwrite, the callback selected only `(6201344,7174144)`, the
   adapter released B000's encoded scratch exactly once, B001 is published,
   owner/scratch marks are consistent, and `structure_bsp_port_verify()` was
   invoked on the decoded B001 data.
4. Inject each failure class after old unload: missing CBIX extent; HP2 section
   decode failure; malformed CBSP header/CRC/offset; materialization failure;
   BSP schema reject; real port verifier reject; and B000 reload failure.
   For successful rollback, assert exact B000 content digest and CE globals
   return to BSP 0. For rollback failure, assert the explicit safe-null state,
   cache header/tag bases cleared, parent cache callback has no live encoded
   BSP, and no stale BSP pointer survives.
5. After every failure, compare owner and scratch cursors to their expected
   marks, assert zero open source handles, exactly balanced mount/unmount and
   BSP release callbacks, and immediately mount/reload a30 again in the same
   process. Preserve same-index and invalid-index no-mutation checks from the
   Tier A fixture.

Use byte digests or invariant fields from decoded B000/B001 to distinguish
the two BSPs: CE keeps one fixed BSP-cache address, so pointer identity alone
cannot establish that rollback restored the old contents. Also explicitly
assert CE unpublishes the old object before the adapter overwrites the shared
span; this is the ownership invariant that makes one-BSP residency safe.

## Risks and boundaries

* **Host pointer rebasing:** CE's tag image is materialized at a 32-bit PS2
  target address in production (`ps2_cache.c:387-393,399-409`). A normal host
  process address may not be representable in CE's ILP32 tag pointer fields.
  Keep the actual R5900 address semantics in the package/adapter layer, and
  use a narrow validated host projection only for CE control-flow testing;
  never silently truncate host pointers.
* **Schema closure:** adding the actual BSP verifier is a narrow and desirable
  source closure. Pulling all tag validation or geometry readers could make
  this test broad and brittle. Keep schema rejection explicitly fault-injected
  for this increment; Step 7 will separately validate full relocation and
  pointer domains (plan lines 510-514).
* **Package decoder capacity:** the retail CBSP envelope can be larger than
  its decoded image. Keep test owner/scratch overprovisioned and report peak
  decoded bytes; production `frame_scratch` and `current_bsp` acceptance must
  wait for the measured capacity and fixed-span decisions in Step 8
  (`plans/7.hcu-remake-m2-m4.md:516-521`).
* **One global adapter:** HCU cache state and the PS2 adapter are singletons;
  tests must serialize fixtures and fully unmount/reset state between cases.
  The parent mount itself enforces one active mount (`ctag_mount.c:123-127`)
  and documents that restriction in `ctag_mount.h:57-65`.
* **Not guest proof:** no host fixture substitutes for PCSX2 or real hardware.
  The guest switch requires a capacity-qualified map and the same fixed spans;
  Step 6's guest lifecycle remains pending after this slice.

## Acceptance boundary and handoff

This slice is complete when an auditable two-BSP retail package drives the
same real CE switch transaction, with actual parent/PS2 package selection and
materialization, actual CE cache load/unload/publication, and real BSP port
verification; rollback/failure assertions cover both successful restore and
safe-null restore failure; package SHA, source SHA, exact extents, arena marks,
and callback counts are part of the deterministic test output. Record separately
which host pointer/schema seams remain adapted.

It still does **not** complete M2 Step 6 unless the exact guest image also
performs and logs load→switch→failure→rollback at the fixed PS2 backing spans,
with target memory/high-water evidence. This report recommends the integration
slice only; it changes neither the shared plan nor implementation files.
