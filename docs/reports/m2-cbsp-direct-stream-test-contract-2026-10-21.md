# M2 direct-destination CBSP streaming: test contract

Status: independent, report-only test-design audit. This report does not change
an API, implementation, memory budget, or milestone gate. It specifies the
host evidence required before routing the current CE BSP read through a direct
HP2 visitor into the PS2 BSP cache.

## Executive finding

There is already good evidence for each adjacent layer, but no single fixture
currently proves direct section streaming through the real CE load boundary.
`tests/test_world_section_visitor.py` proves visitor bytes match the legacy
whole-section loader and that a sink refusal rewinds visitor scratch.
`tests/test_hcu_scenario_bsp_switch.py` executes CE's real BSP-switch/load
control flow over retail CTAG/CBSP packages and links `ps2_cache.c`,
`ctag_mount.c`, and the HP2 visitor. Its retail backend still uses
`world_load_section_with_scratch` to materialize a CBSP envelope into
`bsp_scratch`, then `ps2_cbsp_materialize` copies/fixes the BSP into the CE
destination. `tests/ctag_mount_main.c` also has a lower-level transport-EOF
retry test, but it asserts the destination remains byte-for-byte unchanged
because the current whole-envelope route does not stream decoded image bytes
into it.

The acceptance fixture must therefore extend, not replace, those oracles. It
must run the full path:

`scenario_switch_structure_bsp` → CE `scenario_structure_bsp_load` →
`cache_file_read` → registered `load_bsp_extent` →
`world_visit_section_with_scratch` → HP2 visitor sink → split CBSP parse/rebase
→ CE BSP-header/schema checks → CE datum/global publication.

If the new sink writes directly into the already-poisoned BSP cache, failures
after the first write cannot honestly promise the destination is unchanged.
For those injections, the contract is: destination can contain only
unpublished candidate bytes (and untouched poison), all CE publication fields
remain at their pre-load values, all streaming scratch and short-lived file
leases return to their marks, and a same-process retry of the same map/BSP
replaces the partial candidate and succeeds. Preserve a separate
pre-first-write failure test that proves the destination is unchanged. This
distinction avoids asserting an impossible rollback property while still
proving no invalid BSP becomes reachable.

## Existing behavior and ownership relevant to tests

1. The parent mount retains decoded CTAG/CRNG/CBIX and a file-backed map source.
   `ctag_mount_hp2_internal` records the owner mark and sets the singleton only
   after backend mount succeeds (`src/stream/ctag_mount.c:112-166`). The
   verified file path opens/maps the resource source, loads HMAP for identity
   preflight, then mounts the CTAG/catalog (`src/stream/ctag_map_source.c:110-184`).
2. The registered parent BSP callback currently releases any old BSP lease,
   marks `bsp_scratch`, decodes the whole named CBSP section using
   `load_section`, calls backend mount, and sets `bsp_active` only after mount
   success (`src/stream/ctag_mount.c:54-104`). The existing ownership rule
   requires returned section bytes to be within the scratch transaction
   (`payload_owned_by_transaction`, lines 14-36). A direct visitor changes
   this ownership shape; its test must prove the destination is not falsely
   considered a parent-arena lease.
3. `world_visit_section_with_scratch` opens the HP2 pack, parses the directory,
   allocates 98,304 bytes of bounded streaming work, invokes a sink through
   `hp2_load_stream`, releases the scratch mark, closes the reader, and reports
   raw size only on success (`submodules/halo-ps2/engine/src/world/section.c:67-77,79-138`).
   The lower-level visitor test already verifies byte equality and a rejected
   sink (`submodules/halo-ps2/engine/tests/test_world_section_visitor.c:21-37,68-111`).
4. The HCU cache adapter distinguishes the BSP read by `tag_index == NONE`
   plus exact physical BSP-cache destination. Today it asks the registered
   callback to load a CBSP envelope, then materializes it via
   `ps2_cbsp_materialize`; completion is set only after materialization and
   the PS2-only vertex/index arrays are canonicalized empty
   (`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:375-448`).
5. CE initializes the BSP destination with `0xCD`, calls `cache_file_read`,
   validates completion/header/contained pointers, runs the schema validator,
   then publishes the CE structure-BSP header and datum base pointer
   (`submodules/halo-ce-universal/source/cache/cache_files.c:1412-1513`).
   This is the key no-publication boundary; a valid-looking header alone is not
   enough to count as a published BSP.
6. `scenario_switch_structure_bsp` unloads the old BSP before trying the new
   one, restores the old BSP after a failed candidate, and only then updates
   global BSP pointers and indices (`submodules/halo-ce-universal/source/scenario/scenario.c:1088-1198`).
   Test both first-load failure (all BSP globals stay absent) and switch
   failure (old BSP is reloaded and republished); their expected globals differ.

## Fixture layout and instrumentation

Extend the existing ILP32 retail integration harness rather than creating a
mock cache reader that bypasses CE. `tests/test_hcu_scenario_bsp_switch.py`
already compiles the real `scenario.c`, HCU `ps2_cache.c`/`ps2_cbsp.c`, parent
`ctag_mount.c` and `section.c`, plus `tests/hcu_scenario_bsp_switch_main.c`.
Keep its pinned source-map/package SHA validation, real retail tags, schema
validation, and `scenario_switch_structure_bsp` root.

Add deterministic counters/hooks at boundaries that do not alter production
semantics:

- visitor open/close and decoder-scratch acquire/release counts/high-water;
- sink callback count, highest written destination offset, and an injectable
  failure at a chosen decompressed-output byte offset;
- relocation parse/rebase pass counters, with fault selectors for row index,
  field offset, target/domain, bad string termination, and final-address range;
- map source descriptor identity plus open/read/close/EOF counters;
- tag-owner, BSP decoder scratch, and any bounded relocation-table workspace
  marks/high-water;
- per-datum base-address publication, cache-file BSP-header pointer,
  `global_structure_bsp`, `global_collision_bsp`, `global_bsp3d`, and both BSP
  indices;
- a BSP-destination canary immediately before/after the assigned span and a
  baseline hash of the full span before each attempt.

Use canaries outside the physical BSP span, not inside it. Initialize the
destination with CE's actual `0xCD` poison immediately before every attempted
load; do not let the harness preinitialize it to a plausible BSP header. On
each failure, assert that the datum base and cache header are unpublished even
if bytes at the destination now differ from poison. On success, compare the
complete BSP image against the existing whole-buffer CBSP Python/C oracle after
applying the same documented PS2 canonicalization of Xbox vertex/index arrays.

When targeting the longest candidate, preserve current opt-in/capacity gates:
the plan's selected split layout must be active and capacity proof must pass.
Do not change default 2 MiB tag allocation or declare broad-map admission from
this test alone. Use Blood Gulch for broad production geometry and the
`Longest` package for the current near-capacity decoded CBSP extent; the
existing retail integration currently uses a30/a50 and does not cover either
size boundary.

## Required test cases

### A. Successful direct stream equals the existing oracle

For at least Blood Gulch B000 and the pinned Longest B000:

- Run the whole-buffer oracle first: decode HP2 section to CBSP envelope,
  validate CBSP, apply relocation against the same mapped tag image, and retain
  the expected bytes. Record package, map, HMAP, CBIX, section, and source
  hashes in test output.
- Run through the actual CE `scenario_structure_bsp_load` path with the direct
  visitor sink and compare every byte in the decoded BSP extent against the
  oracle before CE's allowed PS2 header normalization. Then compare post-
  normalization bytes against a separately normalized oracle.
- Assert the exact requested source `(file_offset,file_size)` matches one
  `CBIX` entry and the exact `Bnnn` section. Assert one complete HP2 visitor
  transaction, sink byte total equals decoded image length (not envelope
  length), all relocations are applied exactly once, and no byte beyond the
  extent changes except separately guarded header normalization.
- Assert CE schema validation runs once on the final relocated image and only
  afterwards sets `cache_file_globals.structure_bsp_header` and the tag
  instance's `base_address`. Assert the scenario then publishes global
  structure/collision/BSP pointers and indices. Arena usage returns to its
  mounted baseline; BSP active-lease policy is consistent with design; file
  opens/closes balance for the visitor and map source lifetime is retained
  until map unload.

### B. Failures before the first destination write preserve bytes

Inject one error per boundary before sink output starts:

- HP2 header/table read short/EOF or malformed directory;
- requested section absent, duplicate/inconsistent catalog entry, or extent
  mismatch;
- split CBSP header invalid, bad envelope/image/relocation lengths, source
  extent mismatch, CRC mismatch, or scratch reservation failure;
- decoder read error before the first decompressed output callback.

Seed the destination with an arbitrary pattern in a cache-adapter unit test and
with CE's `0xCD` poison in the integrated fixture. Assert full destination hash
is unchanged, `cache_file_read` completion is false, CE tag base/header remain
unpublished, scenario globals/index remain the expected prior values, visitor
scratch and any temporary relocation workspace rewind, and all opened visitor
handles close exactly once. The retained map source and mounted owner remain
valid if the error is recoverable; verify a same-process same-mount retry passes.

### C. Mid-stream failure leaves a poisoned, unreachable candidate

Fail after a deterministic partial image write (e.g. first output window plus
one byte, and near the image tail). Verify:

- the destination hash may differ from poison, but canary bytes outside its
  declared extent are intact;
- writes are confined to `[destination, destination + decoded_image_size)`;
- no tag datum base, cache header, global structure/collision/BSP pointer, or
  scenario/global index names the attempted candidate;
- completion stays false; the implementation does not loop indefinitely in
  CE's `while (!read_complete)` path (the adapter is synchronous and returns a
  terminal failed flag for this fixture);
- visitor scratch and temporary relocation storage return to pre-call marks,
  the parent mounted map/source survive, and the short-lived HP2 descriptor is
  closed;
- immediate retry on the same mount and same BSP request succeeds and the
  complete destination matches the whole-buffer oracle, proving stale bytes
  from the failed prefix/tail cannot leak into accepted state.

If implementation chooses to restore the `0xCD` poison after a partial write,
assert the entire destination is restored; if it intentionally leaves partial
bytes, require every publication assertion above. Do not accept mixed success
flags, or a candidate image that survives as a live datum.

### D. Relocation failures are atomic with respect to publication

Build/adapt CBSP fixtures that each corrupt exactly one late row so the parser
has already consumed valid prior rows: out-of-bounds aligned field offset,
unaligned field offset, duplicate/out-of-order row, wrong stored target,
invalid source domain, final EE address overflow, and unterminated domain-1
string. For the direct route, choose and document the desired safety contract:

- Preferred: validate the full relocation table and all final addresses before
  writing any fixup, then rebase in one no-fail pass; a validation failure
  preserves streamed image bytes but never publishes them. This gives the
  existing atomic-rebase property without needing a second BSP-sized image.
- Required regardless: no partial relocation set may become CE-visible.
  Assert schema validation and all publication fields remain untouched; retry
  against the uncorrupted same package succeeds in the same process.

Assert non-overlapping image/table destination/workspace ownership, correct
tag/BSP base selection, and all scratch marks/canaries on each failure. A test
that invokes only `ps2_cbsp_rebase_in_place` is necessary but not sufficient;
at least one corrupted late relocation must pass through the real registered
loader and CE cache read, while the larger matrix may use the cache-adapter
fixture.

### E. Downstream CE failures do not publish

After complete bytes have been streamed and rebased, separately reject:

- CE cache header signature / contained-address checks;
- BSP schema validation after structural header checks;
- PS2-specific `structure_bsp_port_verify` after `scenario_structure_bsp_load`
  succeeds.

For the first two, assert the tag datum base and cache header remain unpublished
because CE's cache loader has not reached the publication assignments. For the
last, CE's cache loader may have set the datum base before the scenario layer
rejects it; assert the unload path clears that datum and releases any owned
state before returning failure. In all cases, the first load leaves global BSP
pointers null/indices `NONE`; a failed second-BSP switch reloads and restores
the old BSP as the real CE switch implementation requires. Compare old BSP
snapshots and exact ownership marks, not just return values.

### F. Resource/lease balance, unload, and retry matrix

Run the following sequences without process restart:

1. successful mount → successful BSP load → unload map;
2. mount → pre-write fault → retry success → unload;
3. mount → mid-stream fault → retry success → unload;
4. mount → late relocation fault → repair asset → retry success → unload;
5. load BSP A → attempt failing BSP B → CE reloads/restores A → successful B
   retry → switch back to A → unload.

At every boundary assert owner `used` returns to the correct mount baseline on
BSP release and to the original mark on map unload; decoder scratch/relocation
leases return to entry marks on both success and failure; visitor file open and
close counts are equal after each request; the retained source descriptor stays
open for the mounted map and closes once at unload; no descriptor, arena high
water, or memory usage grows with repeated retries. Account for `high` as a
high-water metric that does not rewind; compare `used` for balance and verify
`high <= cap` separately.

## Suggested fixture organization

- Keep `test_world_section_visitor.py` as the generic HP2 visitor/oracle test;
  add direct-sink fault offsets there only if the sink remains generic and does
  not duplicate CE state assertions.
- Extend `test_hcu_scenario_bsp_switch.py` and `hcu_scenario_bsp_switch_main.c`
  for the retail-backed, real-CE no-publication/publication/retry path. Add
  explicit command modes or deterministic injected fault descriptors rather
  than inferring test case identity from package names.
- Add a focused `test_ps2_cache_cbsp_stream.py` / `ps2_cache_cbsp_stream_main.c`
  only for adapter-level checks that are awkward to expose through the real CE
  fixture: arbitrary destination sentinel preservation, invalid call tuples,
  bounds, and fault-before-first-write.
- Preserve `test_ctag_mount.py` for mount ownership/CRC/transport behavior. Its
  existing fault coverage is useful but should not be mistaken for direct BSP
  destination coverage.
- Keep tests deterministic: every package and source-map input should be
  verified against committed/pinned SHA values; every injected byte offset or
  relocation row should be printed in the fixture's concise success line.

## Exit checklist for this test contract

The direct-stream slice is test-qualified only when all of these are true:

- Whole-buffer and visitor/direct-destination outputs are byte-identical after
  documented PS2-only BSP header normalization on at least the longest enabled
  candidate and a retail gameplay BSP.
- Pre-write and mid-stream faults distinguish unchanged from partially written
  but unpublished destination state; no test makes an unsupported all-or-nothing
  claim for a direct output sink.
- CE datum/cache-header/scenario global publication occurs only on complete,
  validated images; every failure-path state is asserted explicitly.
- HP2 CRC, CBSP CRC/shape, relocation validity, CE header containment, schema,
  and PS2 structure limits each have a failure case at the owning layer.
- Same-process retry, failed second-BSP switch restoration, map unload, arena
  lease balance, visitor descriptor balance, and persistent source lifetime are
  covered.
- Tests compile/link the production visitor/cache/mount/CE control-flow sources;
  source-text checks or isolated parser tests alone do not close the gate.

`Halo-64` is a useful comparative resource for separating simulation-facing
state from a renderer-only path (its port notes call out frame/camera/first-
person state despite removed Xbox drawing: `submodules/halo-64/port/n64/NOTES.md:33`).
It does not define this port's BSP transaction or replace the CE publication
tests above. REA is not the right tool for this particular test-design audit:
the question is a source-level host integration contract and the authoritative
subjects are the pinned source functions and fixture behavior, not an opaque
shipped binary.
