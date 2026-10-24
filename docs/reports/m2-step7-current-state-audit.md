# M2 Step 7 current-state audit: retail CBSP relocation and BSP acceptance

**Scope:** report-only source/test audit of Step 7 in
[`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md). No
implementation, test, plan, or build files were changed and no test/guest run
was performed for this report. The coordinator supplied a current integration
failure observation; it is identified as supplied runtime evidence below, not
independently reproduced here.

## Bottom line

The schema-directed CBSP pipeline is substantially implemented: it inventories
and normalizes CE-schema pointer fields, distinguishes BSP-local pointers from
cross-image tag-name pointers, encodes both relocation domains, and has
synthetic and retail-artifact C/Python materialization checks. The package-backed
Tier B harness now links the real CE switch/load/unload with real parent HP2 /
CTAG / CBIX selection and the real PS2 CTAG/CBSP cache adapter. It also includes
CE's real `structure_bsp_port_verify()` in the retail-integrated branch.

Step 7 remains **open**. In that Tier B harness, `tag_validate_structure_bsp()`
is still an injected schema-validation stub, there are no direct CE collision,
PVS, sound-cluster, or material/surface query comparisons, and current test
source has no assertion that the PS2 cache adapter normalized the serialized
Xbox vertex/index-buffer handles before CE validation. The coordinator reports
that the running integration fails at CE's bounded cache-header range check
with raw retail `vertex_buffers=0x813bc818` and `index_buffers=0x813bcfa4`,
each with count 161. If those are the exact currently built sources, this
indicates either the PS2 normalization branch did not run / was not in the
executed image or its postcondition is not being asserted. It is not a reason
to bypass CE's range checks.

## BSP header Xbox-buffer fields: consumers and safe handling

The CE serialized structure-BSP cache header is 24 bytes and has fields
`base_address`, vertex-buffer count/pointer, index-buffer count/pointer, and
signature (`source/cache/cache_files.c:187-195`). CE's BSP loader checks the
signature, base pointer, and both count/pointer ranges against the serialized
BSP span before calling `tag_validate_structure_bsp()`
(`source/cache/cache_files.c:1444-1479`). The region helper accepts count zero
without inspecting its address (`:344-363`); that makes `(count=0,pointer=NULL)`
the canonical safe empty representation.

The field consumer audit is unusually clear:

* In common CE cache loading, those four fields are consulted by the range
  checks above. Once published, `cache_files_disable_writes()` accesses these
  fields only in its Xbox `#else`; the `HALO_PS2` branch returns before touching
  them because render geometry comes from the PS2 packs
  (`source/cache/cache_files.c:753-784`).
* CE's Xbox-specific `cache_files_windows.c` registers and blocks on the vertex
  buffer arrays by looping over the counts (`:485-534`); that backend is not the
  PS2 owner.
* The PS2 implementation of `structure_bsp_header_register_vertex_buffers()`
  and deregistration are explicit no-ops (`port/ps2/src/ps2_sound_cache.c:238-248`).
  The PS2 renderer consumes separately converted HP2/VU geometry, as the PS2
  cache adapter documents (`port/ps2/src/ps2_cache.c:47-50`). No other HCU
  `source/` consumer of `cache_file_globals.structure_bsp_header` or these BSP
  buffer-array members appears in a source search; the remaining direct
  references are the validations, lifecycle register/deregister calls, and
  Xbox-only write-protection block.

**Recommendation: normalize, never bypass.** After a CBSP has passed envelope,
CRC, exact-source-extent, relocation-domain, and materialization checks, the
PS2 adapter may set both Xbox-only buffer counts and pointers to zero/null
before completing the CE `cache_file_read()` request. That accurately states
that the PS2 adapter supplies no Xbox renderer buffers, while preserving CE's
existing range checks, schema walk, BSP verifier, collision data, and all
remaining tag fields. Do not skip `cache_file_region_contains()` or accept
arbitrary Xbox virtual addresses: the BSP schema validator separately checks
these same fields with `validate_buffers()` before it walks the `sbsp` root
(`port/linux/game/tag_validate.c:1151-1193,1412-1475`).

Current `ps2_cache.c` contains a PS2-only normalization block after successful
CBSP materialization: it checks signature and currently normalizes all four
fields only if **both** counts are positive (`:429-441`). That condition
handles the reported a30 pair `(161,0x813bc818,161,0x813bcfa4)`, so seeing those
same raw fields rejected means the exact source/ELF/test path must be checked.
There is no current assertion in the combined fixture that observes the
post-read header fields; the only synthetic read explicitly writes zeros
(`tests/hcu_scenario_bsp_switch_main.c:180-205`). Add the assertion at the
actual package-backed cache boundary before interpreting a failed CE load.

For robustness, the more appropriate invariant is unconditional canonicalizing
of the PS2-only buffer metadata on a successfully materialized BSP with a
valid `psbs` signature: set both counts to zero and both pointers to zero.
Optionally reject negative or implausibly large source counts before
normalizing, if source-backed retail inventory shows such values are invalid.
Do not make the branch depend on both positive counts: one-sided, null, or
negative metadata must not escape to later checks as accidental PS2 render
resources. The normalization should happen before both CE's cache containment
checks and `tag_validate_structure_bsp()`; current placement inside
`cache_file_read()` is the correct boundary if compiled and executed.

The coordinator's reported raw bytes are consistent with little-endian `psbs`
at byte 20 and both counts equal to 161. The reported pointer targets are
outside the runtime BSP span and are not among CBSP's schema relocation rows;
therefore they cannot be made valid by the generic relocation mechanism.
They are Xbox renderer handles, not BSP-owned data extents. The source comments
and no-op PS2 register hooks support emptying them, but the harness must prove
that this normalization is occurring in the built path.

## What the current code and evidence establish

### Schema inventory and conversion

`walk_structure_bsp()` roots the actual schema walk at the BSP header's
`base_address`, checks the `psbs` signature, walks the linked `sbsp` schema,
validates nested block/data extents and overlap, and returns separate internal
and external tag-name relocation lists (`tools/ctag_schema_walk.py:129-158,
188-243,244-272,346-367`). The tag-name mapper validates original tag-region
membership, rejects removed render-interval targets, and requires a bounded
NUL terminator (`tools/audit_retail_bsp_schema.py:53-76`).

CBSP v1 stores an image checksum, exact original file extent, and sorted typed
relocation rows. Python encode/decode rejects out-of-image and duplicate fields
and checks source extent and checksum (`tools/cbsp.py:142-203,206-250`). The
R5900 C parser checks format/version, image and row bounds, checksum, sorted and
aligned field positions, and internal pointer targets
(`port/ps2/src/ps2_cbsp.c:62-128`). The materializer validates base alignment,
32-bit bounds, BSP/tag virtual non-overlap, domain-1 string termination, and
source/destination overlap before copying and applying declared relocations
(`ps2_cbsp.c:131-187`). Prior report
[`m2-step7-retail-cbsp-validation.md`](m2-step7-retail-cbsp-validation.md)
records a C/Python byte-for-byte check on Blood Gulch's 1,296,384-byte BSP,
including 463 internal and 93 tag-name pointers. That is real-artifact
materialization evidence, not full CE acceptance.

The all-map audit is still only an offline inventory/projection. It records 24
maps / 82 BSPs, zero CBSP round-trip failures, and 21 raw BSPs larger than the
6,291,456-byte region. The apparent zero-capacity-failure projection depends
on subtracting compressed vertex data; the report explicitly says those bytes
still feed CE material/surface/light queries and are not approved for removal
or charged to a replacement store (`retail-bsp-schema-2fba411b.json:1-5,6-18`).
Preserve these bytes until a real query-equivalent PS2 owner and parity tests
exist.

### Combined Tier B transaction

The package test verifies a30 package/source identity and CBIX B000/B001
extent matches before building the ILP32 fixture; it links real `scenario.c`,
`ps2_cache.c`, `ps2_ctag.c`, `ps2_cbsp.c`, parent `ctag_mount.c`,
`ctag_ps2_backend.c`, `cbsp_catalog.c`, resource-index C, HP2 C, and arena C
(`tests/test_hcu_scenario_bsp_switch.py:73-162`). The fixture materializes the
actual a30 CTAG, uses its real scenario tag/reference table, checks the two
source extents, runs 0→1→0, and injects candidate read, verifier, schema-stub,
and combined rollback failures (`tests/hcu_scenario_bsp_switch_main.c:433-524,
529-585,587-602`). The integrated fixture includes actual
`structure_bsp_definitions.c` through a renamed symbol and wraps its real
`structure_bsp_port_verify()` with a deterministic test failure mask
(`:271-289`).

Important limits:

* `tag_validate_structure_bsp()` remains a stub that only counts calls and
  returns according to `fail_schema_mask`; it is not CE's real schema
  validator (`tests/hcu_scenario_bsp_switch_main.c:159-178`).
* The fixture uses 16 MiB tag and 8 MiB BSP host arrays (as declared earlier in
  that test file), and package a30 B001's source extent is 7,174,144 bytes.
  It proves the bounded host transaction, not fit in PS2's 6 MiB
  `current_bsp` arena. The all-map capacity projection shows why stripping
  compressed vertices cannot be assumed.
* The current fixture source asserts parent scratch release and CE publication
  and exact callback selection, but no explicit assertions for all four
  normalized header fields are present. This leaves the coordinator's
  reported failure difficult to disambiguate from stale object/source
  selection.
* `structure_bsp_port_verify()` only checks collision count, cluster count,
  surface count, cluster PVS byte count, and sound-cluster byte count
  (`source/structures/structure_bsp_definitions.c:26-43`). It does not walk
  graph indices or compare actual collision, PVS, sound, material, or surface
  query results.

### Required Step 7 status

Step 7 requires schema-declared pointer-domain relocation, malicious/boundary
fixtures with no publication on rejection, real `structure_bsp_port_verify`,
and preservation/query evidence for collision, clusters, surfaces, PVS, and
sound clusters (`plans/7.hcu-remake-m2-m4.md:512-514`). Synthetic walker and
CBSP faults already cover several bounds and rollback cases, and Blood Gulch
has real artifact materialization. But existing synthetic schema fixtures do
not replace a target/CE end-to-end negative matrix, and package a30 still has
only the verifier plus a schema-validator stub. No contents are approved for
omission or externalization.

## Most practical next slice

1. **Make the runtime mismatch observable first.** In the a30 package-backed
   fixture, immediately after the real `cache_file_read()` has materialized
   B000/B001 and before `scenario_structure_bsp_load()` continues, assert
   signature `psbs`, `vertex_buffer_count == 0`, `vertex_buffers == 0`,
   `index_buffer_count == 0`, and `index_buffers == 0`. On failure, print
   package hash, selected B-section, whether `ps2_cache.c` normalization was
   reached, raw/normalized header words, and linked symbol/object map evidence.
   This will determine whether the reported rejection uses a stale ELF, misses
   the intended `cache_file_read`, or needs a correction in the adapter.
2. **Make normalization invariant, not conditional on both positive counts.**
   After successful CBSP materialization and signature validation, zero all
   Xbox-only count/pointer pairs; never skip CE's containment checks. Add
   unit cases for both positive, only vertex positive, only index positive,
   zero count with nonzero pointer, negative count, bad signature, malformed
   CBSP, and failing materialization. Assert that rejected CBSP leaves the
   BSP destination and published cache state unchanged. A bad signature must
   fail closed rather than be normalized.
3. **Replace only the schema-validator test stub with production validator.**
   `tag_validate_structure_bsp()` in
   `port/linux/game/tag_validate.c:1412-1475` requires tag validation to have
   initialized its map header, tag instance table, separate BSP span, and
   caller-owned claims bitmap; its APIs are declared in
   `port/linux/game/tag_schema.h:301-344`. Add the narrow schema source
   closure and initialize it from the materialized a30 CTAG once, then call
   the real validator before `structure_bsp_port_verify()`. Keep controlled
   corruption cases for nested block/data pointers, misaligned/overflowing
   targets, tag-name targets outside/unterminated in CTAG, sentinel cases,
   and overlapping claims. Verify failure leaves CE globals unpublished and
   BSP-owner marks rewound. Do not hand-implement a parallel validator.
4. **Add direct CE semantic probes using the resulting real structure.** First
   exercise one collision query and a cluster-PVS/sound-cluster bounds query
   using functions whose interfaces are present in the compiled source; add a
   material/surface lookup only when the required visual payload is explicitly
   available. Compare results with the retail/CE oracle and assert every read
   lands inside the BSP or CTAG spans. Query a second structurally different
   BSP after the a30 integration is stable.
5. **Keep capacity and guest acceptance separate.** The host fixture remains
   overprovisioned. Before enabling/claiming a gameplay map, account for full
   decoded BSP image, CTAG, claims, animation, renderer data, and transient
   CBSP decode bytes in fixed PS2 arenas; Step 8 explicitly requires that
   backing/lifetime proof (`plans/7.hcu-remake-m2-m4.md:516-521`).

This ordering reduces uncertainty quickly: the adapter postcondition explains
the current boundary failure, the production schema validator is the next true
Step 7 gap, and semantic query fixtures determine whether schema-valid retained
bytes behave as CE expects. Do not weaken the M2 gate or mark Step 7 complete
based only on successful CBSP materialization, CE header range acceptance, or
the lightweight port verifier.

## Supplied integration-failure note

The coordinator reports an a30 B000 run that stops before schema validation:
the materialized header had `vertex_buffers=0x813bc818`,
`index_buffers=0x813bcfa4`, and count 161 for each, both outside the BSP span;
those pointer words are not CBSP relocations. Source inspection finds a
normalization branch in `ps2_cache.c:429-441` that should convert exactly that
positive-count case to zero/null, before the CE caller's bounds checks. Because
this report-only turn did not run the fixture or inspect the exact failed ELF,
the cause is unresolved. Next run should bind exact HCU/parent source IDs,
fixture link map and executable hash, and assert both the raw input before
adapter transformation and the postcondition after `cache_file_read()`.
