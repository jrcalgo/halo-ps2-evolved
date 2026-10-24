# HCU cache-loader contract for the PS2 tag image

**Status:** end-to-end guest map loading remains unimplemented. The current
PS2 closure links HCU's real `tag_validate.c` and schema groups instead of the
former permissive validation stubs. Its static claim bitmap remains the 2 MiB
bootstrap fallback; `tag_validate_bind_claims_buffer` permits a caller-owned,
aligned scratch span sized for the combined tag-cache and separately-bound BSP
extents. The optional parent-owned `hcu_main` now binds a 2 MiB UI/bootstrap
cache and claims scratch before CE allocation, but no production map loader
selects and binds full retail-map spans or runs in the guest. On PS2 the claims bitmap uses a
logical address space (tag bytes followed by BSP bytes), allowing BSP schema
validation without clearing claims for already-validated tag roots and names.
An ILP32 host fixture validates a synthetic tag table and separately-bound BSP
and checks this preservation behavior. The fixture passes in an escalated
native-ILP32 run; normal sandbox execution returns SIGSYS and skips it. CE cache consumers query
provider-reported capacity; the PS2 provider remains at the 2 MiB default.
`tag_validate_release_claims_buffer` restores the bootstrap
bitmap after the owner has unpublished tags/BSPs and before it releases the
external scratch span; rebind is required for the next map. A host-side CTAG
v1 envelope/relocator and HP2
section packager exist in [`tools/ctag.py`](../tools/ctag.py). The manifest
selects allocation-free [`ps2_ctag.c`](../submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c),
and `ps2_cache.c` now exposes a mount/materialize seam that calls its decoder.
An extended mount accepts the original virtual cache's `tag_data_offset`,
`file_length`, and a caller-owned bounded `read_at` callback; CE cache reads
outside the CTAG image are synchronously delegated through that callback. The
adapter bounds requests, rejects reads that overlap the substituted tag image,
and marks completion only after bytes have been written. Nonblocking CE reads
are synchronous at this seam, which is a correctness fallback that still needs
DVD/EE timing qualification.

The exact resource authorization contract now has a portable `CRNG` v1 table:
[`tools/ctag_resources.py`](../tools/ctag_resources.py) creates it from the audit,
and [`ctag_resource_index.c`](../src/stream/ctag_resource_index.c) validates it
and performs bounded interval lookup in parent code. The header binds the table
to the source file length and original retail tag offset/size; rows are sorted,
nonempty, non-touching map-file intervals with a CRC. A request must fit wholly
inside one row, so valid bitmap/sample ranges are served while gaps and the
larger original tag region fail closed. The parent EE object list compiles this
validator. Python/C parity tests include the Blood Gulch resource corpus.
Current scope is intentionally map-file-only because all 24 audited maps report
that source; separate `bitmaps.map`/`sounds.map` sources require explicit corpus
support before the format is extended. `ctag_mount_hp2` now requires CRNG beside
CTAG, validates source identity, and passes a wrapper to the HCU cache backend;
the wrapper denies gaps before invoking the injected platform reader. Its
composite host regression proves that denial through CE's actual
`cache_file_read` call and that a corrupt CRNG causes transactional rollback.
[`tools/pack_retail_ctag_hp2.py`](../tools/pack_retail_ctag_hp2.py) now emits a
deterministic HP2 container with CTAG and CRNG, accepts optional already-built
PS2 sections, and reopens the result with the HP2 parser before writing. A
Blood Gulch fixture verifies both sections, all 1,200 intervals, and repeatable
output bytes. This package still does not embed the decompressed retail map
resource source, generate the required BSP/scenario/render sections, or provide
the production PS2 filesystem callback.

The parent file layer now has a persistent descriptor reader using PS2SDK's
POSIX/newlib `open`/`lseek`/`read`/`close` path, replacing its former per-read
`fopen`/`fseek`/`fread` pattern. Relative paths use a configurable root
(default `host:/`; production may set `cdrom0:/` or a mounted device), while
explicit device paths pass through. [`ctag_map_source.c`](../src/stream/ctag_map_source.c)
keeps the decompressed retail map open, checks its exact length, and provides
the source callback consumed by the CRNG gate. The composite host fixture now
uses the actual file and descriptor reader all the way from CE
`cache_file_read` through the CRNG interval wrapper, rather than a memory-only
callback. This compiles in the R5900 parent ELF. It still does not prove that
CDVDMAN is present under the target boot path, that OPL exposes the selected
device path, that any map-selection code sets the root and opens this source,
or that synchronous DVD reads meet the tick/streaming budget. More importantly,
the POSIX path is not yet proven compatible with the final fixed-memory policy:
PS2SDK's `__fioOpenHelper` allocates per-descriptor filename metadata
([source](../submodules/ps2sdk/ee/libcglue/src/ps2sdkapi.c#L66)), and its close
path frees that record ([source](../submodules/ps2sdk/ee/libcglue/src/ps2sdkapi.c#L145)).
HCU currently wraps `free` as a no-op ([source](../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L201)),
so linking this path into the HCU runtime would leak each descriptor's metadata.
The HCU link explicitly wraps allocator calls ([linker flags](../tools/hcu_ps2_link.py#L242)).
Thus the host/R5900 compile proves API compatibility only; a target file backend
must avoid unbounded libcglue descriptor allocations and verify its IOP service
startup before this counts as machine I/O.

An opt-in direct FileXio backend now exists in the parent reader
([implementation](../submodules/halo-ps2/engine/src/stream/file.c)); it gates
opens until `file_reader_filexio_init()` succeeds and avoids newlib's per-open
metadata allocation. Host API-fake coverage checks bounds and lifecycle
([test](../tests/test_file_reader_filexio.py)), and `WORLD_FILEXIO=1` compiles
and links the R5900 parent renderer with `-lfileXio`. This is not yet enabled by
the HCU gameplay link or called by machine startup. The IOP module loading,
OPL-compatible service ownership, device availability, and actual guest reads
remain unverified; the optional renderer build is not a production boot path.

The composite `ctag_mount_hp2_file_with_bsp_catalog` integration fixture now
also compiles the `HALO_FILE_USE_FILEXIO` branch and supplies fake FileXio
operations backed by host files. It drives HP2 section loading, persistent map
source open, CRNG-authorized resource reads through HCU `cache_file_read`,
failed-mount cleanup, BSP section dispatch, and source close after cache
unpublication ([fixture](../tests/ctag_mount_main.c),
[build/run](../tests/test_ctag_mount.py)). This closes a test-composition gap
between the reader branch and the loader seam; it does not change the runtime
status above. Actual IOP startup, real device paths, synchronous read latency,
and a guest map load remain unproven.

The local retail `ui.map` bootstrap case now has a second, asset-backed host
fixture ([test](../tests/test_retail_ui_ctag_mount.py)). It loads the actual
converted `build/retail-ui-component.hp2` CTAG/CRNG sections with the real
parent HP2 reader into the 1,572,864-byte streaming region and uses the real
HCU cache backend to open the virtual cache and materialize the complete
1,510,628-byte tag image into a 2 MiB cache. The fixture also issues a
CRNG-authorized resource read against the original 33,582,080-byte decompressed
map and compares it byte-for-byte with a direct source read, then verifies
unmount closes the descriptor and restores the arena baseline. With separate
frame scratch, measured high-water is 1,550,356 bytes in streaming and 275,491
bytes in the 393,216-byte scratch span. This is a host integration result for
the UI-only package, not PS2 IOP/FileXio startup, CE `scenario_load`, a guest
UI load, or proof that gameplay maps fit.

The file-backed path is composed by `ctag_mount_hp2_file`: it opens and
size-checks the source before mounting CTAG/CRNG, closes the descriptor if any
HP2/index/backend step fails, and binds descriptor cleanup to mount unload so
the cache backend is unpublished first. The composite test exercises failed
HP2 decode, corrupt CRNG, insufficient cache capacity, successful bounded
resource reads, and source closure on unload. This proves descriptor lifetime
ordering at the host integration seam; it does not prove the application has
selected the right retail map path, mounted the target device, or avoided
target-side libcglue allocation.
Closure tooling force-roots `ps2_cache_mount_ctag` so it appears in the measured
ELF; there is still no boot-path HP2/DVD caller. The seam takes a raw CTAG
payload that the caller must keep alive; in the current runtime it remains
limited to the 2 MiB default because no parent arena binds a larger span. The
parent now has [`ctag_mount_hp2`](../src/stream/ctag_mount.c#L10), which loads
the HP2 CTAG section into a caller arena, mounts it through an injected backend,
retains the payload while mounted, and unmounts before rolling the arena back.
It now requires the complete payload range to be allocated after that mount's
entry mark; merely pointing at another live allocation inside the same arena is
rejected, so unload cannot release storage owned by an earlier transaction.
It is part of the parent EE object list, and the complete parent `world.elf`
target links with it. Current `play_ee`/HCU startup does not call it and no
production backend/read-at owner is wired into the guest path. The composite
host fixture compiles the real parent HP2 section reader,
arena, mount owner, and HCU PS2 cache adapter; it verifies HP2 CRC and cache
capacity failures restore the arena mark, external and pre-existing in-arena
payload pointers are rejected while preserving prior allocations, successful
mount serves a bounded resource read, and unload unmounts before release
([test](../tests/test_ctag_mount.py)).
This does not load BSP data, bind larger CE tag/claims/BSP spans, connect the
separate retail map resource file to a production PS2 read service, establish
full-map rollback, or demonstrate guest map loading. The normal build wrapper still refuses a
reported build because the existing `halo-ps2` worktree is modified; a direct
EE target build verified compile/link only. Host tests also compile the C decoder/cache adapter and compare relocation
output with Python. A separate integration test compiles the production
[`hp2.c`](../submodules/halo-ps2/engine/src/stream/hp2.c) reader and checks
synthetic CTAG/SCEN/BSP0 lookup, decode, byte equality, and CRC failure. These
fixtures prove synthetic format/cache boundaries only; there is a retail
schema-aware offline converter, but no production arena-backed map load,
whole-map rollback/unload proof, or guest map-load evidence. This contract
records the assumptions those pieces must preserve.

The existing parent `world_load_section` HP2 consumer now has a host regression
for its per-section arena transaction: a failed stored-payload read, scratch
allocation exhaustion, or CRC/decode failure restores the arena to its entry
mark and leaves `raw_size` zero; on success it retains only the decoded section
and releases stored-byte scratch. This protects one HP2 section read. It does
not provide whole-map L0–L6 rollback or connect HP2/DVD acquisition to HCU's
cache mount path.

The HP2 C reader and Python reference parser now reject duplicate or malformed
section tags, metadata/payload overlap, overlapping nonempty section extents,
nonzero reserved fields, unsupported codecs or alignment values, and stored
size mismatches before section lookup. This is an L1 container-structure
hardening step; CTAG relocations, schema validity, allocation rollback, and
runtime ownership remain separate loader gates.

## What the current CE loader assumes

The HCU `scenario_tags_load` path opens one cache file, reads
`header.tag_data_size` bytes to the address returned by
`physical_memory_get_tag_cache_base_address()`, then treats the first byte as a
`cache_file_tag_header`. It checks the tag table, vertex/index buffer tables,
scenario datum, and every non-null tag base pointer against that single
contiguous region before exposing `global_tag_instances`; it also runs
`tag_validate_tags` over every tag using the group schemas. See
[`cache_files.c`](../submodules/halo-ce-universal/source/cache/cache_files.c#L1189)
and its verification helpers ([header check](../submodules/halo-ce-universal/source/cache/cache_files.c#L388),
[map-header check](../submodules/halo-ce-universal/source/cache/cache_files.c#L920)).

The load is not merely a table of offsets: the tag instances carry direct
`base_address` and `name` pointers, group schemas walk direct tag-block/data
pointers, and `tag_get` returns the instance's base pointer
([tag access](../submodules/halo-ce-universal/source/cache/cache_files.c#L1503),
[tag-block structures](../submodules/halo-ce-universal/source/tag_files/tag_groups.h#L64)).
Therefore, a converted image must either materialize those fields as valid EE
pointers into the loaded storage or change the HCU access layer consistently
to resolve bounded offsets. Updating only the top-level tag table is unsafe.

Structure BSPs are a second, separately loaded extent. A scenario reference
contains file offset, size, and base address; HCU checks the aligned read and
then reads the BSP directly to `reference->base_address`
([reference layout](../submodules/halo-ce-universal/source/scenario/scenario_definitions.h#L147),
[BSP load](../submodules/halo-ce-universal/source/cache/cache_files.c#L1350)).
The stock Xbox path places BSP bytes after the tag region in the tag cache, but
the implementation and its `TAG_CACHE_SIZE` bounds assume that cache is
contiguous. The PS2 validator now accepts only the exact base/extent supplied by
the separate BSP provider and bounds claims against that range. This does not
relocate the retail BSP header or nested schema pointers: the cache verifier
still replaces the scenario reference's Xbox base before those internal
pointers are translated. No production parent binds the BSP provider or loads
BSP bytes from HP2/DVD. The PS2 design must make ownership/maximum explicit and
complete schema-aware rebasing; separate validator support alone is not a BSP
loader.

The BSP capacity audit must distinguish collision data from presentation data.
`structure_test_vector()` gets a CE collision result, then
`structure_render_surface_from_point_and_leaf()` uses BSP leaf/surface
references and compressed triangle positions to recover the exact surface,
lightmap material, and barycentric UV coordinates
([surface query](../submodules/halo-ce-universal/source/structures/structures.c#L517),
[collision-to-query path](../submodules/halo-ce-universal/source/structures/structures.c#L838)).
The call-site audit finds `structure_test_vector()` used by object/particle
lighting and render debugging; those consumers sample diffuse/lightmap data or
display a material name, rather than decide movement or weapon collisions
([lighting consumers](../submodules/halo-ce-universal/source/objects/object_lights.c#L1411),
[debug consumer](../submodules/halo-ce-universal/source/render/render_debug.c#L1277)).
Therefore `structure_material.compressed_vertex_data` is presentation-critical
for CE-like lighting/debug output, but it is not itself collision authority.
It may be externalized or omitted from the CE BSP only after the PS2 path has a
bounded equivalent surface/material/UV query and parity evidence for retained
visual behavior. The schema/capacity projection ([report](reports/retail-bsp-schema-capacity-projection.json),
[reproducer](../tools/audit_retail_bsp_schema.py)) finds this field alone occupies
3,585,552 bytes in `c20_3`. Across 82 BSPs, 21 raw blocks exceed 6 MiB; if and
only if this field's bytes were externalized, all 82 projected BSP extents fit,
with the largest at 5,575,320 bytes (`a30_b`). This projection does not charge
the moved bytes to their destination region and does not establish pointer,
schema, or visual-query validity. Neither the existing `BSPS` pack nor a
replacement query is yet proven equivalent.

The current PS2 `BSPS` section is not that equivalent query. Its per-material
record retains shader ID/lightmap page, while the triangle data is reordered
into batches and VIF packets; the format does not retain a source BSP surface
ID for each emitted triangle. The packet carries quantized positions, texture
and lightmap UVs, and vertex colour, but not CE's per-vertex normal/tangent
fields or lightmap incident-radiosity values ([encoder](../submodules/halo-ps2/tools/halo2ps2/bspconv.py#L232),
[format](../submodules/halo-ps2/docs/08-bsp-section.md#L89)). Therefore direct
reuse requires a versioned lookup extension keyed by CE lightmap/material/
surface (and a defined source-to-packed triangle mapping), with explicit
position precision and lighting-field parity tests. Merely pointing CE's
`compressed_vertex_data` at the existing VIF batch bytes is invalid: layout,
ordering, attributes, and interpretation differ.

## What the existing PS2 pack reader provides—and does not

HP2 is a bounds-checked, little-endian, checksummed section container; sections
are independently loaded and decoded, including one section at a time from DVD
([format](../submodules/halo-ps2/docs/07-hp2-format.md),
[reader API](../submodules/halo-ps2/engine/src/stream/hp2.h#L25)). The existing
converters emit typed presentation/resource sections such as `SCEN`, `MODL`,
`ANIM`, `BSP*`, and `TEXS`; for example, `scenconv.py` parses selected tag
fields and writes a compact runtime-specific representation
([converter](../submodules/halo-ps2/tools/halo2ps2/scenconv.py#L1)). This is
not a generic schema-preserving CE tag serializer, relocation builder, or
replacement for HCU `tag_validate_tags`.

The retail resource audit now emits a source-separated merged interval index
for every audited map ([report](reports/retail-resource-interval-index.json),
[generator](../tools/audit_ctag_retail_maps.py)). It is pinned to the linked
schema ELF and records exact byte ranges used by typed bitmap payloads and
schema file-data, rather than treating every offset below `file_length` as an
authorized resource. The 24-map corpus currently uses only the map file source;
the `read_at` API still carries a tag index and raw file offset but has no
production range-index verifier. This artifact makes an allowlist-based reader
testable, but is not yet the runtime index, does not identify a deployed DVD
path, and does not satisfy streaming-latency requirements.

The retail inventory is decisive against the current fixed allocation: 24 maps
have 6.71–16.21 MiB raw tag regions; even subtracting only model vertex/index
buffers leaves 3.93–10.96 MiB of tag-structure bytes. See
[`tag-index.md`](reports/tag-index.md). Thus the 2 MiB staging array cannot
hold every map, while simply enlarging it would exceed `current_bsp` on large
maps and would still duplicate payloads already owned by PS2 packs.

The validator integration is not a workaround for this limit. Its bootstrap
claim array is 262,144 bytes and only supports the bootstrap cache. The binding
interface rejects a span too small for the current cache, and validation fails
closed if claims capacity is insufficient. Gameplay-sized CTAG images require
the loader to reserve and bind scratch from a bounded arena before the first
tag validation. Do not raise the static macro to retail size: the prior CE-wide
23 MiB cap made the static claim bitmap roughly 2.9 MiB and pushed the
candidate resident region over budget.

### Animation payload working-set hypothesis (not yet qualified)

The retail range audit records exact non-overlapping source extents for every
schema-owned `animation.data` field ([range report](reports/retail-animation-data-ranges-v1.json),
[reproducer](../tools/audit_animation_data_ranges.py)). The largest field is
167,560 bytes in the 24-map corpus. Source inspection narrows the access shape:
`animation_get_frame_data()` obtains the start of one `animation.data` extent,
and its callers keep frame pointers locally while computing orientations
([definition](../submodules/halo-ce-universal/source/models/model_animation_definitions.c#L500),
[four-frame orientation sample](../submodules/halo-ce-universal/source/models/model_animations.c#L1876)).
Those four yaw/pitch samples are offsets in the same animation record, not four
independent records. Object pose updates and first-person pose updates each call
`animation_get_node_orientations()` ([object update](../submodules/halo-ce-universal/source/objects/objects.c#L2507),
[first-person update](../submodules/halo-ce-universal/source/interface/first_person_weapons.c#L1191)).
This makes one aligned buffer sized for the largest record a plausible
single-call staging primitive, provided the loaded bytes remain stable until
the caller finishes using every returned pointer. `default_data` is a separate
in-image field and is read directly by `animation_get_default_data()`; it must
remain resident or receive its own explicitly pinned lifetime
([definition](../submodules/halo-ce-universal/source/models/model_animation_definitions.h#L62)).

This is not evidence that one buffer is sufficient for the game. It does not
cover cache thrash among distinct active graphs, read-ahead deadlines, animation
state changes, reentrancy/interrupt readers, compressed-data random access,
simultaneous object/first-person work, or worst-case DVD seek latency. A valid
implementation must first instrument the PS2 CE tick to record each requested
animation tag/record, whether its source extent was already resident, bytes
read, cache eviction, and blocking time across campaign, multiplayer, and
split-screen fixtures. Then choose and test a measured pinned-record/cache
policy; demonstrate no returned pointer is invalidated before use ends, no
synchronous DVD miss breaches the 33.3 ms simulation budget, and the worst-case
cache plus read scratch fits its named region while map load/unload returns to
baseline. Until that evidence exists, treat 167,560 bytes as a corpus maximum
for one field—not as a complete animation working-set budget or permission to
externalize the field.

The complete source pointer inventory is recorded in the
[animation-data pointer audit](reports/animation-data-pointer-audit.md) and
locked by [`test_animation_data_direct_pointer_uses_match_the_audit`](../tests/test_animation_data_ranges.py).
It adds an important validation constraint to the hypothesis: CE declares
`animation.data` as `TAG_SCHEMA_DATA`, not `TAG_SCHEMA_FILE_DATA`, in
[`tag_schema_models.c`](../submodules/halo-ce-universal/port/linux/game/tag_schema_models.c#L1208).
The former is validated as an in-image data extent, while the latter is checked
against the source file ([validator](../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L934)).
Changing the schema kind would therefore be a semantic change, not just a PS2
storage optimization. Moreover, the schema callback itself reads
`animation->data.address + compressed_data_offset` and walks the compressed
record's header, defaults, node headers, keyframes, and frame indices
([callback](../submodules/halo-ce-universal/port/linux/game/tag_schema_models.c#L862));
externalizing bytes without a validator-side typed range contract would make
tag validation read outside the resident image. In addition to
`animation_get_frame_data()`, compressed
rotation, translation, and scale paths directly call
`tag_data_get_pointer(&animation->data, ...)`
([rotation](../submodules/halo-ce-universal/source/models/model_animations.c#L2152),
[translation](../submodules/halo-ce-universal/source/models/model_animations.c#L2296),
[scale](../submodules/halo-ce-universal/source/models/model_animations.c#L2431)).
The schema check also compares compressed offsets and extents against
`animation->data.size` ([bounds helper](../submodules/halo-ce-universal/source/models/model_animations.c#L2583)).
The four yaw/pitch frame views acquired by one orientation calculation refer
to the same animation record, but all four remain live until decoding finishes
([call site](../submodules/halo-ce-universal/source/models/model_animations.c#L1867));
a one-buffer staging design therefore needs one acquisition spanning that
whole operation, not a fresh replacement buffer per accessor call. `frame_info`
is another distinct in-image payload consumed directly for movement/root
offsets ([call site](../submodules/halo-ce-universal/source/models/model_animations.c#L395)),
and is not part of the `animation.data` extraction candidate. Thus any PS2
external-data implementation must retain the CE validation contract through a
typed auxiliary range/remap, route the schema callback and every runtime direct
access, and preserve all live views; wrapping only
`animation_get_frame_data()` is incomplete.

## Required M2 design decisions and tests

Before writing the runtime image loader, specify and version:

1. The serialized tag table and stable datum-index/generation mapping, including
   group/inheritance tags, names, scenario index, and empty-tag behavior.
2. Every pointer-like field's representation: direct EE pointer after load or a
   typed offset resolved by HCU accessors. Identify all consumers and validators
   before choosing the latter; do not mix the two models.
3. The distinction among permanent tag structures, transient/current-BSP
   collision structures, vertex/index/render payloads, bitmaps, sound, and
   temporary converter/streaming buffers. Each gets exactly one owner and a
   measured peak-overlap charge against the v2 regions and separate GS/IOP/SPU2
   stores.
4. How the converter emits and validates cross-tag references and per-tag
   schemas, including unsupported groups/fields and Xbox absolute addresses.
5. How the BSP reference's location is translated to a bounded load target,
   including multi-BSP maps, alignment, unload/reload, and rollback on a failed
   section read.

Host fixtures must reject bad count/stride/address arithmetic, out-of-range tag
indices, malformed or cyclic relocation records, duplicate ownership of a
payload, truncated sections, CRC errors, and region exhaustion. A retail-map
fixture must then prove byte-stable conversion, schema validation, datum
identity, correct scenario/BSP access, unload baseline, and peak memory. No
current code or report passes those gates.
