# M2 Step 7: feasibility of real CE BSP schema validation in the a30 fixture

**Scope:** report-only feasibility audit. No implementation, test, or shared
plan files were changed, and no compile/test/guest run was performed here.
The recommended next addition is to replace the fixture's
`tag_validate_structure_bsp()` decision stub with HCU's real validator, using
the already materialized a30 CTAG to establish validator state first.

## Conclusion

This is practical without inventing a validator API, but it is not simply a
one-file link change. `tag_validate_structure_bsp()` has no standalone
initializer. The public path that populates its required hidden state is
`tag_validate_tags()`: it calls `validation_begin()`, stores the current tag
header/size and separate BSP span, clears the claims bitmap, then validates
the actual tag table (`port/linux/game/tag_validate.c:1294-1369`). A faithful
fixture must therefore:

1. Bind a claims bitmap sized from the fixture's tag-cache plus BSP-cache
   capacities before the first validator call.
2. Run real `tag_validate_tags()` on the a30 CTAG materialized at the fixture's
   tag base. It both validates and may apply CE-defined corrections, just as
   production does.
3. Publish CE cache/tag globals only after that call succeeds, then invoke the
   real `tag_validate_structure_bsp()` indirectly through the current actual
   `scenario_structure_bsp_load()` path.
4. Keep the full production schema-group registry if the goal is representative
   a30 validation. `schemas_fit()` checks every registered group and
   `validate_tag_table()` walks every table instance, not just the `sbsp`
   record (`tag_validate.c:1093-1121,1124-1135,1328-1369`).

The exact production source list is already explicit in the HCU PS2 manifest:
`tag_validate.c`, `tag_validate_report.c`, `tag_schema_groups.c`, and the six
schema sources `tag_schema_collision.c`, `tag_schema_models.c`,
`tag_schema_objects.c`, `tag_schema_render.c`, `tag_schema_effects.c`, and
`tag_schema_scenario.c` (`port/ps2/port.json:35-43`). Reusing that list is
safer than guessing a reduced link set. A reduced test-only schema registry
could be a useful diagnostic for one BSP, but would not be production-closure
or all-a30-tags evidence.

## Exact state and initialization contract

### Required hidden state

`tag_validate_structure_bsp()` reads four pieces of state that the current
Tier B fixture does not establish through the production initializer:

* `tag_validate_globals.header`, tag image/cache sizes, and the separate BSP
  base/capacity, established by `validation_begin()`
  (`tag_validate.c:1294-1325`).
* The cached CE tag instance table and a live `sbsp` datum with the correct
  group tag; these are read by `instance_get()` / `schema_group_get()` and
  checked before BSP traversal (`:1417-1444`).
* A claims bitmap large enough for the combined logical address space
  `[tag cache][BSP cache]`; PS2 maps the distinct BSP span immediately after
  the tag span for bitmap purposes (`:207-219,244-254,432-473`).

The current validator scratch API is purpose-built for this contract:

* `tag_validate_claims_buffer_size()` computes a rounded per-byte bitmap size
  from the configured tag + BSP capacities using `CLAIM_BITS == 32`
  (`tag_validate.c:237-255,272-284`).
* `tag_validate_bind_claims_buffer()` requires non-null, non-empty 16-byte
  aligned caller storage, enough capacity, and that validation has not started
  (`:257-269`).
* `tag_validate_release_claims_buffer()` clears validator state and resets
  back to the bootstrap bitmap; it must only be called once all tag/BSP
  consumers are unpublished (`:292-299`; contract in `tag_schema.h:307-322`).
* Production binds the claims span before the one boot allocation via
  `physical_memory_bind_tag_validation_scratch()`; that function rejects
  overlap with the CE's configured fixed regions and delegates to the validator
  bind API (`port/ps2/src/ps2_memory.c:176-192`). Parent M2 memory binding
  derives the byte count after tag and BSP spans are configured and reserves
  it from `resident_gameplay` (`src/stream/hcu_memory_bind.c:65-71`).

For the current retail transaction fixture's 16 MiB tag span plus 8 MiB BSP
span (constants in `tests/hcu_scenario_bsp_switch_main.c:20-26`), the formula
requires 24 MiB / 32 = 786,432 bytes when compiled ILP32 (`unsigned long` =
4 bytes). The fixture should calculate this via the API, not duplicate the
constant. A static 16-byte-aligned host array of that returned size avoids
heap/lifetime ambiguity. The actual PS2 production image must keep using the
arena-bound storage; the host array is not RAM-fit evidence.

### Recommended call order in the fixture

Use a fresh executable per test case as the pytest currently does, or perform
the complete reset/rebind sequence below for each in-process case:

1. Initialize `physical_memory_get_tag_cache_base_address/size` and
   `physical_memory_get_structure_bsp_cache_base_address/size` to the actual
   fixture spans. Initialize cache/parent package mount as currently done.
2. Call `tag_validate_release_claims_buffer()` while nothing is published,
   then `bytes = tag_validate_claims_buffer_size()`, allocate/assign aligned
   caller storage, and require `tag_validate_bind_claims_buffer(storage,
   bytes)` and `tag_validate_claims_buffer_ready()` to succeed.
3. Use real `cache_file_open()` and `cache_file_read()` to materialize CTAG.
   Apply only source-backed PS2 normalization needed for Xbox-only cache
   header fields before validating them. Then call
   `tag_validate_tags(tag_header, opened_header.tag_data_size,
   opened_header.file_length, "a30")` and require success. This call is the
   production validator-state initializer, not a test-only shortcut.
4. Follow CE's publication order: set `cache_file_globals.tag_header`,
   `global_tag_instances`, `global_tag_count`, and `tags_loaded` only after
   validation returns true, matching `cache_files.c:1286-1329`. Then resolve
   the scenario/reference records and call the existing switch transaction.
5. During BSP load, allow real PS2 `cache_file_read()` to materialize and
   normalize the BSP cache header. CE's ordinary bounds check runs first
   (`cache_files.c:1442-1475`); then real `tag_validate_structure_bsp()` checks
   the header buffers, claims the BSP, traverses the linked `sbsp` schema, and
   runs collision/BSP checks (`tag_validate.c:1412-1478`). The existing
   `structure_bsp_port_verify()` follows and remains a separate check.
6. On a normal BSP switch, do not release the claims bitmap: the validator
   unclaims the previous separate-BSP span before claiming the replacement
   (`tag_validate.c:1446-1453`). On whole-map teardown/retry, first unpublish
   CE BSP/tag references and unmount the parent cache/package; then release the
   claims binding and rewind its owner. `tag_schema.h:320-322` explicitly
   orders release after map/BSP unpublication.

There is no need for production code to expose `validation_begin()`. Calling
it directly would create a test-only back door and would skip full map-tag
validation; do not do that.

## Source and link closure

### Faithful closure (recommended)

Add the full manifest validator/schema closure to the current ILP32 package
fixture build in `tests/test_hcu_scenario_bsp_switch.py:129-153`:

1. `submodules/halo-ce-universal/port/linux/game/tag_validate.c`
2. `.../tag_validate_report.c` (or retain the fixture's existing report/error
   shim, but then say diagnostics are adapted)
3. `.../tag_schema_groups.c`
4. `.../tag_schema_collision.c`
5. `.../tag_schema_models.c`
6. `.../tag_schema_objects.c`
7. `.../tag_schema_render.c`
8. `.../tag_schema_effects.c`
9. `.../tag_schema_scenario.c`

The schema group list references all six arrays
(`tag_schema_groups.c:14-23`). `tag_validate_tags()` calls `schemas_fit()`,
which loops through custom-edition groups and every group list
(`tag_validate.c:1093-1121`). Then `validate_tag_table()` walks each known tag
group (`:1124-1135,1262-1291`). Linking just collision schema while retaining
the full registry will therefore leave unresolved schema arrays/check
procedures; replacing the group list with a collision-only array would
under-test the actual a30 CTAG and must be marked diagnostic-only.

The existing test already uses generated MSVC semantic shims, HCU's PS2
prefix, ILP32 compiler flags, `-fshort-wchar`, `-ffunction-sections`,
`-fdata-sections`, and `--gc-sections` (`tests/test_hcu_scenario_bsp_switch.py:109-153`).
Retain that profile. Include the same HCU source/include roots required by the
production closure, especially `port/linux/game`, `source`, `port/include`,
and XDK compatibility headers. The build manifest says little-endian, 32-bit
pointer/long, 16-bit wchar, and `HALO_PS2`; do not use native host LP64
(`port/ps2/port.json:3-13`). `-no-pie` is worth retaining for a deterministic
32-bit pointer environment, but it does not model EE physical placement.

### Smaller diagnostic option (not M2 acceptance)

For a quick, narrow first experiment, define a test-only `tag_schema_group_lists`
whose only group list is the real `tag_schema_collision_groups`, plus an empty
custom-edition list. Compile real `tag_validate.c` and real
`tag_schema_collision.c`, then run `tag_validate_tags()` and the BSP validator
on the real a30 CTAG. This retains the production validator algorithm and full
`sbsp` definition/check callback, but it causes non-collision tags to have no
linked group definitions. It cannot be called full-map production validation,
cannot establish that all a30 tag schemas pass, and must not replace the
faithful closure in final evidence. If this diagnostic reveals a BSP issue,
continue with the faithful manifest registry rather than adding local schema
stubs around it.

## ABI, layout, and behavior pitfalls

1. **32-bit `long` matters in the claim formula and records.** The validator
   stores pointers and counts in CE ILP32 records and uses 32-bit `unsigned
   long` masks. A host LP64 build will calculate a different claims-buffer
   size and layout; the current test correctly obtains `host_abi32_flags()`
   (`tests/test_hcu_scenario_bsp_switch.py:129-135`).
2. **Schema group arrays are runtime data, not just compile-time layout.**
   The current fixture uses the actual a30 tag-table `group_tag`s and
   `tag_index`s before switching (`tests/hcu_scenario_bsp_switch_main.c:482-507`).
   The production validator expects the same instance structure and group
   identities and may correct invalid fields in place. Any such correction
   must be accounted for in deterministic hashes/snapshots.
3. **BSP header normalization is a prerequisite, not an exception.** The
   validator calls `validate_buffers()` on both BSP header array pairs
   (`tag_validate.c:1455-1463`); its helper rejects negative/excess counts or
   positive counts whose 12-byte descriptors are outside the region
   (`:1151-1193`). Xbox buffer pointers cannot be passed through. Normalize
   the unsupported PS2 fields to `(0,NULL)` before CE bounds/schema checks;
   do not bypass those checks.
4. **Tag-header buffers may be an earlier obstacle.** `tag_validate_tags()`
   itself calls `validate_buffers()` on the CTAG cache header
   (`tag_validate.c:1358-1368`). Before attempting the full validator, assert
   that the a30 materialized tag header's vertex/index counts and addresses
   are valid in the compact CTAG span or normalize them using the same
   source-backed Xbox-resource ownership rule. Do not assume the BSP-header
   fix proves the tag-header case.
5. **Separate physical spans have one logical claim map.** `claim_address_offset()`
   maps `[tag cache]` and `[BSP cache]` into adjacent bitmap offsets while the
   physical arrays can be disjoint (`tag_validate.c:432-473`). The test's
   accessors must return the same stable array bases used by `ps2_cache.c`
   and `tag_validate.c` throughout the case; moving the BSP array invalidates
   both relocation addresses and claims.
6. **Validation is mutating and stateful.** `tag_validate_tags()` clears and
   populates the caller bitmap, can correct invalid fields, sets
   `tag_validate_has_started`, and thereby prevents rebinding until
   `tag_validate_release_claims_buffer()` (`:263-269,1294-1323`). Do not run
   multiple independent maps against one validator state without full
   unpublish/release/rebind. To test corrupted candidates, make controlled
   copies or reseal package sections; retain exact failure bytes and report
   whether validation mutated the candidate.
7. **Failure does not mean “unchanged candidate bytes.”** Validator correction
   procedures may edit fields, and BSP claims may be partly written before a
   rejected field/schema check. The CE transaction's safety guarantee should
   be tested on ownership/publication and successful old-BSP rematerialization,
   not assumed byte-atomicity of a rejected candidate. If the whole map is
   abandoned, release the validator only after CE pointers are cleared.
8. **The real collision/BSP schema is semantic, not merely pointer walking.**
   `tag_schema_collision.c` declares the full `structure_bsp` blocks and data,
   including collision BSP, surfaces, lightmaps, clusters/PVS, pathfinding,
   and sound (`:936-983`); its `structure_bsp_check` traverses linked
   collision/surface/cluster relations (`:1583-1714`). This is stronger than
   `structure_bsp_port_verify()`, but still does not itself compare runtime
   physics/query outputs against a parity oracle.

## Smallest faithful test sequence

1. Add a separate validator-focused execution mode to the existing a30 test,
   preserving the current stubbed transaction mode until that mode passes.
   Reuse the already validated package identity, real CTAG, B000/B001 payloads,
   host pointer ABI, and current source selection.
2. Compile and root the manifest schema closure above. Put the executable map
   in the linker file and assert the real `tag_validate_tags`,
   `tag_validate_structure_bsp`, `structure_bsp_check`, and `scenario_switch_structure_bsp`
   are retained. Record exact compiler command and HCU schema/source hashes.
3. Bind claims storage and run full `tag_validate_tags()` against a30 CTAG.
   First assert the tag header's own buffer fields; if those are absent, fail
   with the raw tuple rather than mutate policy silently. Require the validator
   to accept the real tag image and record its corrections count.
4. Run one CE switch to B000 and one B000→B001→B000 switch. Ensure the actual
   `cache_file_read()` postcondition is `(vertex count=0, vertex pointer=NULL,
   index count=0, index pointer=NULL)` on each BSP before the cache range check.
   Verify actual schema call success, actual `structure_bsp_port_verify()`
   success, globals/tag bases, and rematerialized B000 digest.
5. Add targeted mutated CBSP candidates: one internal pointer out of bounds,
   one CTAG string pointer to a nonterminated range, one nested block overlap,
   one count beyond schema maximum, and one invalid structure-BSP cross-index.
   Parser/decoder rejection should happen before CE publication where
   possible; schema rejection must leave globals unpublished and switching
   must either restore B000 or enter the existing safe-null/menu state.
6. Verify the bitmap is sufficient and stays in the same owner for all three
   switches. After unload, release validator state; then rerun a30 in the same
   process and verify a fresh bind and full tag validation succeed. Keep host
   scratch/claims high-water separate from target PS2 arena accounting.
7. Once host acceptance is stable, run the exact R5900 compile/link closure;
   only after a capacity-qualified map exists should PCSX2 attempt the matching
   BSP and query sequence. The current a30 B001 7,174,144-byte retail extent
   exceeds the 6 MiB `current_bsp` region before any proposed data externalization,
   so this host fixture cannot itself be the guest target acceptance map.

## Current reusable evidence and limits

`tests/hcu_validator_scratch_main.c:16-42,62-173` already exercises the real
`tag_validate.c` claims-buffer APIs, aligned/undersized binding, ready-state,
release/rebind, two-region logical claims, and one small synthetic structure
BSP. Its `test_ce_validator_claims_scratch_bounds_and_rebind` builds that
fixture ILP32 and runs it (`tests/test_hcu_ps2_closure.py:28-55`). But that
fixture supplies tiny hand-written `scnr` and `sbsp` schema groups
(`hcu_validator_scratch_main.c:23-38`), a 96 KiB tag array and 4 KiB BSP span,
and never traverses the a30 production `sbsp` schema. It proves the stateful
claims API is reusable, not the retail closure or validation result.

The Tier B package fixture already has the correct source-level insertion
point: after the real CTAG read and before manually publishing CE tag state
(`tests/hcu_scenario_bsp_switch_main.c:475-507`). It currently copies the
opened header and sets `tags_loaded` itself, while its validation function is
the stub in `:159-178`. Replace that seam only after the PS2-only BSP header
fields are asserted empty; retain the current controlled failure mask by
wrapping the real validator result rather than replacing its implementation.

No conclusion about M2 Step 7, memory fit, target performance, or rendered
gameplay follows until this exact-schema fixture runs and semantic query/
capacity gates are addressed.
