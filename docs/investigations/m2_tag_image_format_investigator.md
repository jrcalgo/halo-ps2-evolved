# m2_tag_image_format_investigator

## Mission

Define a **versioned, relocatable runtime tag-image contract** for M2 that lets HCU `scenario_tags_load` / `tag_get` and schema validation behave like retail CE loads, while respecting PS2 memory ownership (partitioned regions, HP2 transport, stripped render/audio payloads). Resolve explicitly whether the loaded image uses **materialized EE pointers** (post-relocation) or **bounded in-image offsets** resolved by accessors—and forbid mixing the two in one map.

## Inputs examined

| Area | Path / symbol |
|------|----------------|
| Loader contract (parent audit) | `docs/hcu-tag-loader-contract.md` |
| M2 plan and inventory gates | `plans/5.hcu-remake.md` (M2), `docs/reports/tag-index.md`, `docs/reports/tag-payload-inventory.md` |
| CE load + verify + `tag_get` | `submodules/halo-ce-universal/source/cache/cache_files.c` (`scenario_tags_load` ~1189, `cache_file_tag_header_verify` ~388, `scenario_structure_bsp_load` ~1351, `tag_get` ~1503) |
| Tag table / reflexive layouts | `submodules/halo-ce-universal/source/cache/cache_files.c` (`struct cache_file_tag_instance` ~164, `struct cache_file_tag_header` ~174), `submodules/halo-ce-universal/source/tag_files/tag_groups.h` (`struct tag_block`, `struct tag_reference`, `struct tag_data`) |
| BSP reference | `submodules/halo-ce-universal/source/scenario/scenario_definitions.h` (`struct scenario_structure_bsp_reference` ~147) |
| Schema validator (Linux port) | `submodules/halo-ce-universal/port/linux/game/tag_validate.c` |
| PS2 stubs (current gap) | `submodules/halo-ce-universal/port/ps2/game/ps2_data.c` (`tag_validate_tags` ~31) |
| PS2 tag cache cap / memory | `submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h` (`HALO_PORT_TAG_CACHE_SIZE`), `submodules/halo-ce-universal/port/ps2/src/ps2_memory.c`, `submodules/halo-ce-universal/source/cache/physical_memory_map.h` |
| Retail tag layout reference | `submodules/halo-ps2/tools/halo2ps2/tagindex.py`, `submodules/halo-ps2/docs/05-halo-ce-data.md` |
| HP2 section transport | `submodules/halo-ps2/engine/src/stream/hp2.h` |
| CE→runtime relocation precedent | `submodules/halo-ce-universal/port/linux/game/cache_file_formats.c` (`element_relocate` ~1394), `custom_edition_cache.c` (`custom_edition_cache_tags_load` ~946) |
| Repack + relocation precedent (N64) | `submodules/halo-64/tools/n64/repack.py`, `submodules/halo-64/tools/n64/convert.py`, `submodules/halo-64/port/n64/game/n64_game.c` (`n64_map_load` ~980) |
| EE budget regions | `config/memory-budget.json` |
| Prompt contract | `docs/investigations/_prompt_contract.md` |

Evidence baseline (Round 1): parent HEAD `a2575e957feefbdff27febedabf60590401e6bcc`, HCU HEAD `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`.

### Current implementation delta (2026-10-20)

The PS2 manifest now compiles this report's CE `tag_validate.c`, all six
`tag_schema_*` group files, and the report sink; the former permissive
`tag_validate_tags` / `tag_validate_structure_bsp` stubs were removed from
`port/ps2/game/ps2_data.c`. Host tests confirm both validator entry points are
rooted in the linked ELF. To stay within the current candidate memory account,
`HALO_PS2` sets `TAG_VALIDATE_MAXIMUM_TAG_CACHE_SIZE` to the 2 MiB bootstrap
tag-cache limit, making `tag_validate_claims` 262,144 bytes. This only handles
the existing small UI-sized image; it is not a gameplay-map solution. The
rooted `resident_gameplay` candidate after linking this validator is
6,493,464 / 6,815,744 bytes and remains logical accounting, not proven arena
routing. A host-only CTAG v1 payload parser/relocator, HP2 section packer, and
synthetic corruption/HP2-integrity tests now exist in the parent
(`tools/ctag.py`, `tests/test_ctag.py`), but no schema-aware retail converter
or runtime HP2/arena loader exists. Therefore
the report's design choices remain guidance, and its M2 acceptance gates remain
open.

## Findings

### 1. What HCU actually consumes after `scenario_tags_load`

**Load sequence (stock Xbox / OpenCE path, not Custom Edition):**

1. Read `header.tag_data_size` bytes from the cache file into `physical_memory_get_tag_cache_base_address()` (`cache_files.c` ~1235–1245).
2. Treat byte 0 of that buffer as `struct cache_file_tag_header` in place (`cache_files.c` ~1285–1302).
3. `cache_file_tag_header_verify` checks signature `'tags'`, tag table pointer, vertex/index buffer tables, scenario datum, and **every non-null** `tag_instances[i].base_address` lies in `[tag_header, tag_header + TAG_CACHE_SIZE)` (`cache_files.c` ~388–457). Note the upper bound is **`TAG_CACHE_SIZE`**, not `tag_data_size`.
4. `tag_validate_tags` walks every tag via group schemas: all `tag_block.address`, `tag_data.address`, string/`tag_reference.name` pointers, and header vertex/index buffer **nested** `void*` at offset +4 must lie in the validation region and must not overlap (`tag_validate.c` ~582–659, ~1029–1068, ~1076–1165).
5. Publish `global_tag_instances` / `global_tag_count`; register Xbox vertex/index buffers (`tags_header_register_vertex_and_index_buffers`, `cache_files.c` ~1303).
6. `tag_get(group, tag_index)` returns `tag_instance->base_address` directly after group/inheritance and non-null checks (`cache_files.c` ~1503–1542). Empty or wrong-group indices redirect to a static empty tag (`cache_files.c` ~317–321, ~1534–1539).

**Implication:** After load, the game holds **live 32-bit pointers** into the tag allocation. `TAG_BLOCK_GET_ELEMENT` and `tag_block_get_element_fast` add indices to `block->address` (`tag_groups.h` ~134–144). There is no indirection layer in the hot path.

**BSP (second phase):** `scenario_structure_bsp_load` reads `reference->file_size` bytes from `reference->file_offset` **directly into `reference->base_address`** (`cache_files.c` ~1392–1396). Pre-check requires that destination lies in `tag_cache_base + tag_data_size` .. `tag_cache_base + TAG_CACHE_SIZE` (`cache_file_structure_bsp_reference_verify`, `cache_files.c` ~487–525). After read, BSP header pointers must lie inside the BSP extent (`cache_files.c` ~1410–1430). The structure BSP tag instance starts with `base_address == NULL` and is patched to `structure_bsp_header->base_address` on success (`cache_files.c` ~1464–1473).

**Custom Edition path** already performs **load-time pointer materialization** from file-relative layouts via `element_relocate` (offsets → `item_address + offset`, definition pointers cleared) before the same validator runs (`cache_file_formats.c` ~1390–1458, `custom_edition_cache.c` ~1024–1043).

**PS2 today:** `tag_validate_tags` / `tag_validate_structure_bsp` in `ps2_data.c` are **stubs** that only check non-null pointers (~31–47). Stock `cache_files.c` still runs `cache_file_tag_header_verify` and calls the stubs—so **no schema or overlap guarantees** on PS2 until the Linux validator is linked or an equivalent runs in the loader.

### 2. In-memory layout the contract must preserve (CE compatibility)

**Tag header (36 bytes at image base)** — matches Xbox index + CE `cache_file_tag_header` tail:

| Offset | Field | CE / Xbox role |
|--------|--------|----------------|
| +0x00 | `tag_instances` | Pointer to tag table |
| +0x04 | `scenario_tag_index` | Datum index (salt \| index) |
| +0x08 | `checksum` | Map tag checksum |
| +0x0C | `tag_count` | Number of instances |
| +0x10 | `vertex_buffer_count` | D3D resource descriptors |
| +0x14 | `vertex_buffers` | Pointer to count × 12-byte entries |
| +0x18 | `index_buffer_count` | |
| +0x1C | `index_buffers` | |
| +0x20 | `signature` | `'tags'` |

Retail maps place the tag array at **base + 0x24** inside the tag region (`tagindex.py` ~8–18, `docs/reports/tag-index.md`).

**Tag instance (32 / 0x20 bytes)** — `cache_file_tag_instance`:

| Offset | Field |
|--------|--------|
| +0x00 | `group_tag` |
| +0x08 | `parent_group_tags[2]` |
| +0x10 | `tag_index` (generation in high 16 bits) |
| +0x14 | `name` → NUL-terminated path string in image |
| +0x18 | `base_address` → tag root struct (NULL for unloaded `sbsp`) |
| +0x1C | `unused[2]` |

**Datum identity:** `cache_get_tag_instance` requires `(tag_index & 0xFFFF0000)` to match `tag_instance->tag_index` when generation is set (`cache_files.c` ~306–311). Converter must **preserve absolute table index and datum salt** for kept tags; dropped tags should match N64 behavior (instance present, `group_tag == NONE`, null data) if indices must remain stable (`repack.py` ~7–10, `convert.py` ~407–418).

**Reflexive fields** (must be valid pointers after load, not file offsets):

- `struct tag_block`: `count`, `address`, `definition` (validator nulls `definition`; CE runtime may use it from linked schemas).
- `struct tag_reference`: `group_tag`, `name`, `name_length`, `index`.
- `struct tag_data`: `size`, `file_offset`, `address`, `definition`.

**Scenario BSP reference** (`scenario_structure_bsp_reference`, 0x20 bytes): `file_offset`, `file_size`, `base_address`, `structure_bsp` tag reference (`scenario_definitions.h` ~147–154). For PS2, `file_offset`/`file_size` may describe an HP2 section payload rather than Xbox cache offsets, but **`base_address` must still be a valid EE pointer** at collision load time.

### 3. Size and ownership facts (why “bigger 2 MiB” is not a format)

From `docs/reports/tag-index.md` (24 retail maps):

- Raw Xbox tag regions: **6.71–16.21 MiB** (non-UI); tag-structure bytes after removing model vertex/index only: **3.93–10.96 MiB**.
- `HALO_PORT_TAG_CACHE_SIZE` is **0x200000 (2 MiB)** (`halo_ps2_limits.h` ~24).
- Budget v2 assigns **`current_bsp` 6 MiB** and **`resident_gameplay` 6.5 MiB** separately (`config/memory-budget.json`); `ps2_memory.c` currently backs the tag cache with a **static 2 MiB array**, not those named parent arenas (~4–22).

M2 must **strip or externalize** model vertex/index buffers (to HP2 `MODL`/render path), bitmap pixels, and sound samples (`docs/hcu-tag-loader-contract.md` ~38–56, `05-halo-ce-data.md` ~49–55) and still fit **simultaneous** tag bytes + active BSP + streaming overlap. The format definition is independent of the 2 MiB bootstrap cap, but **load verification must use the real owner region size**, not a placeholder.

### 4. Contiguous EE pointers vs bounded offsets (decision)

| Criterion | Materialized EE pointers (after bounded reloc) | Bounded offsets + accessor refactor |
|-----------|-----------------------------------------------|-------------------------------------|
| `tag_get` / `TAG_BLOCK_GET_ELEMENT` | Unchanged | Must wrap or replace hundreds of call sites |
| `tag_validate.c` | Reuse Linux validator as-is on loaded buffer | Validator must resolve offsets or duplicate logic |
| Xbox/CE map on disk | Absolute `0x803A6000`-relative addresses | N/A |
| On-disk / in HP2 | **Offsets** + relocation directory (safe on disc) | Offsets only; runtime never materializes |
| Load step | `dst + reloc[i] += (uint32_t)dst` (N64 pattern) | Every read adds base in accessor |
| Precedent | N64 `H64M` + `n64_map_load` (`n64_game.c` ~1074–1093); CE `element_relocate` | Not used in any shipped HCU port |

**Recommendation:** Adopt a **two-layer contract**:

1. **Wire format (HP2 payload / file):** little-endian, **pointer fields store offsets** from a declared `image_base` (or section start); a **sorted, bounded relocation table** lists byte offsets of every pointer field (same role as N64 `image.relocs`, `repack.py` ~38–65). Optional typed relocation entries (future) must remain fail-closed parseable; unknown types reject load (`hcu-tag-loader-contract.md` ~78–79).

2. **Runtime image (EE, before gameplay):** after decode into the owning arena, the loader **materializes** pointers (`*(uint32_t*)(base + reloc_off) += (uint32_t)base` for 32-bit fields; null stays 0). The buffer then matches what `cache_file_tag_header_verify` and `tag_validate_tags` expect.

Do **not** ship a runtime image that still contains Xbox VA `0x803A6000` addresses or uncorrected file offsets. Do **not** mix materialized and offset forms in the same loaded map.

**Why not offset-only in HCU sources:** `tag_get` returns `void*` (`cache_files.c` ~1541); physics, AI, render, and HS read nested pointers without a base register. An offset-only design is a **cross-cutting M2–M5 refactor**, not a converter-only task (`docs/hcu-tag-loader-contract.md` ~19–26).

### 5. Proposed wire format: `CTAG` (version 1) — specification sketch

*Name is provisional; must be registered in HP2 section tag table and versioned. Not implemented in tree.*

**HP2 envelope:** one section per map (e.g. tag `CTAG`) decoded into a caller-provided buffer capped by `cap >= raw_size`; `hp2_load` CRC failure aborts (`hp2.h` ~50–51). Section is independent of `SCEN`/`BSP*`/`TEXS` presentation sections (`hcu-tag-loader-contract.md` ~40–49).

**Logical layout (little-endian):**

```
struct ctag_header {
    char     magic[4];          /* 'CTAG' */
    uint32_t version;           /* 1 */
    uint32_t flags;
    uint32_t image_size;        /* bytes of image following this header */
    uint32_t reloc_count;
    uint32_t reloc_offset;      /* from start of section payload */
    uint32_t tag_header_offset; /* always 0 if image starts with cache_file_tag_header */
    uint32_t scenario_abs_index;/* redundant check vs tag header */
    uint32_t image_checksum;    /* CRC32 of image pre-reloc application */
    uint32_t reserved[4];
};
/* image: contiguous bytes laid out as post-load CE tag cache (header, paths, structs) */
/* relocs: reloc_count × uint32_t byte offsets into image of pointer fields */
```

**Converter obligations:**

- Emit `cache_file_tag_header` + instances compatible with `cache_files.c` layouts (sizes asserted in `cache_files.c` ~223–227, `tag_validate.c` ~156–162).
- Preserve tag index order and `tag_index` datum values for kept tags.
- Set `vertex_buffer_count` / pointers to **empty or PS2-specific stubs** if Xbox geometry buffers are stripped; any non-zero buffer must pass `validate_buffers` or loader must zero counts before validation. **Unknown:** exact PS2 policy for `tags_header_register_vertex_and_index_buffers` when geometry lives only in HP2—requires `m2_map_conversion_auditor` / render owner alignment.
- Rewrite `scenario_structure_bsp_reference` so `file_offset`/`file_size` refer to **BSP HP2 section** (or embedded payload), and `base_address` is the **precomputed EE address** in the `current_bsp` (or tag-cache tail) region where the runtime will read the BSP.
- Record cross-tag edges only as pointer fields in the relocation set; reject duplicate reloc offsets, reloc past `image_size`, or relocs pointing outside image.
- Strip groups per PS2 policy (compare N64 `DROPPED_GROUPS` in `convert.py` ~73–77) only when indices and scenario scripts remain valid; campaign maps require full script nodes (`tag-payload-inventory.md` ~53–55).

**Loader obligations (PS2 adapter, not stock `cache_file_read`):**

1. Bound-check `image_size` against assigned **tag owner** region (not necessarily `HALO_PORT_TAG_CACHE_SIZE` once budget routing is real).
2. Decode HP2 → image buffer; verify `image_checksum`.
3. Apply relocations; optional second pass for BSP section if not in image.
4. Run `cache_file_tag_header_verify` with `tag_data_size == image_size` (or split accounting if BSP tail is separate—then verification regions must be updated consistently; **open**).
5. Run full `tag_validate_tags` (link Linux `tag_validate.c` on PS2, or host-equivalent)—**replace `ps2_data.c` stubs**.
6. Set `global_tag_instances` and return `scenario_tag_index` like `scenario_tags_load` (~1301–1339).

**N64 differences to respect on PS2:** N64 uses big-endian image + `H64M` (`convert.py` ~7–13); PS2 CTAG stays **little-endian** to match EE and `ps2_abi.c` tag layout checks. N64 drops many tag groups; PS2 M5 scope keeps AI/HS/sound tags—converter closure is **superset** of N64, not a copy.

### 6. Region ownership matrix (single owner per byte)

| Payload | Xbox | M2 owner (target) | In CTAG image? | Pointer materialization base |
|---------|------|-------------------|----------------|------------------------------|
| Tag structs, strings, scripts | Tag region | `resident_gameplay` and/or dedicated **permanent tag** sub-arena | Yes | That arena’s base |
| Model vertex/index pools | Tag region | HP2 / render; stripped from CTAG | No (counts zero or external) | N/A |
| Structure BSP collision + loaded BSP header | Tag tail / separate read | `current_bsp` (6 MiB budget) | BSP bytes via HP2 `BSPn`; reference in scenario | `reference->base_address` in BSP region |
| Bitmap pixels | Map file offsets | GS / texture cache / IOP | No; `tag_data.file_offset` → pack | Validator `tag_validate_file_contains` needs **file range table** like CE (`tag_validate.c` ~639–645) |
| Sound samples | Map file | IOP / `audio` staging | No | Same file-range contract as CE custom edition |
| Menu/mod overlay tags | Added after load | Separate allocations (`menu_tags.c`) | Out of scope for CTAG | EE pointers into overlay buffers |

Peak overlap (tags + current BSP + stream buffers) must be measured before M2 gate (`plans/5.hcu-remake.md` ~134–136).

### 7. Failure modes (fail closed)

Aligned with `hcu-tag-loader-contract.md` ~78–83 and existing CE checks:

| Failure | Detection |
|---------|-----------|
| Truncated HP2 / CTAG | `HP2_ERR_TRUNCATED`, `image_size` vs buffer cap |
| Bad CRC | `HP2_ERR_CRC`, `image_checksum` |
| Reloc overflow / duplicate | `reloc_offset + 4*count <= section_size`, sorted unique offsets |
| Pointer after reloc points outside owner | `cache_file_region_contains`, `tag_validate` refuse |
| Overlapping tag blocks | `tag_validate` claim bitmap |
| Invalid tag index / generation | `validate_tag_table`, `cache_get_tag_instance` |
| BSP load destination outside allowed span | `cache_file_structure_bsp_reference_verify` pattern |
| Budget exhaustion | Pre-decode `raw_size` vs region free list |

### 8. Gaps and conflicts in current tree

- **No CTAG / PS2 retail tag converter or runtime loader** (`port/ps2/port.json`, `plans/5.hcu-remake.md` M2 row); host-side envelope, relocator, and HP2 pack helper exist, but they do not traverse or convert retail CE schemas.
- **The former PS2 validator stubs are removed** in the current tree, but validator scratch remains statically sized to the 2 MiB bootstrap ceiling; arena-sized scratch and tag-image bounds are still required for M2.
- **`cache_files.c` still assumes Xbox cache I/O** on non–Custom-Edition path; PS2 placeholders for `cache_file_open` / `cache_file_read` (`docs/hcu-ps2-platform-placeholder-audit.md`).
- **Region naming drift:** comments in `ps2_memory.c` associate tag cache with `current_bsp` (~7–8) but array is 2 MiB tag staging only.
- Parent `tools/convert_collision.py` **`TAGS` collpack** is a **minimal movement/collision float block**, not a CE tag image (`src/game/collpack.h`, `tools/convert_collision.py`); do not conflate with CTAG.

## Interface contracts for the main agent

### Contract A — Runtime invariant (post-load, pre-`tag_get`)

After successful map tag load, for owner region `R` with base `B` and size `S`:

1. `cache_file_globals.tag_header` points at `B`; `signature == 'tags'`.
2. ∀ instances: `name` and non-null `base_address` ∈ `[B, B+S)`; `sbsp` may have null `base_address` until BSP load.
3. ∀ schema-reachable `tag_block.address`, `tag_data.address`, reference names, and header buffer nested pointers ∈ `[B, B+S)` (or registered file ranges for externalized `tag_data`).
4. `tag_get` returns the same addresses validators walked.
5. BSP load places bytes at `reference->base_address` in the **BSP owner** region; patches matching `sbsp` instance `base_address`.

### Contract B — On-disk / HP2 (`CTAG` v1)

1. Little-endian; magic `CTAG`, version `1`.
2. `image` bytes are a **pre-relocation** byte image: pointer fields hold **offsets** relative to `B` (image base), not Xbox VA.
3. `reloc_count` offsets, each pointing to a 4-byte field; applying `field += B` yields Contract A.
4. `image_checksum` covers image **before** relocation apply (deterministic converter output).
5. HP2 `raw_size` / `stored_size` bounds enforced by `hp2_load`; reject on mismatch.

### Contract C — Explicit non-goals

- Do not require retail `.map` bytes in git.
- Do not increase `HALO_PORT_TAG_CACHE_SIZE` to 16 MiB without budget version bump and overlap proof.
- Do not emit schema-opaque HP2 sections (e.g. `SCEN` only) as a substitute for CTAG if HCU simulation tags are required (`hcu-tag-loader-contract.md` ~48–49).

### Contract D — PS2 loader integration point

Replace or shadow the body of `scenario_tags_load` for `HALO_PS2`: instead of `cache_file_read(..., tag_data_offset, tag_data_size, tag_cache_base_address, ...)`, **HP2 decode → CTAG parse → reloc apply → verify → validate**. `scenario_tags_unload` must zero/release the same owner regions and BSP state (`cache_files.c` ~592–627).

## Recommended tests / fixtures

1. **Synthetic CTAG minimal map** (2–3 tags: `scnr`, `weap`, `bitm` stub): round-trip converter golden hash; reloc apply; `tag_validate_tags` pass on host via `tools/map_validate.c` pattern.
2. **Corrupt fixtures:** bad reloc count, reloc pointing to middle of `u32`, cyclic block graph (validator refuse), truncated HP2 payload (`HP2_ERR_*`).
3. **Datum identity:** `tag_index` with non-zero salt; `tag_get` and network-style `tag_index_is_group` (`cache_files.c` ~1548+).
4. **BSP reference:** load/unload sets `sbsp` `base_address` null/non-null (`cache_files.c` ~1464–1497).
5. **Blood Gulch (supplied map):** byte-stable converter output hash; measured image size vs stripped inventory row (`docs/reports/tag-index.md` bloodgulch: ~4.14 MiB tag structs); **peak** tag + BSP + scratch in v2 regions—assigned to `m2_arena_capacity_auditor`.
6. **Regression:** link PS2 ELF with real `tag_validate.c` (not stub) on one synthetic fixture before retail map.

## Dependencies on other investigators

| Investigator | Dependency |
|--------------|------------|
| `m2_map_conversion_auditor` | Which tag groups/fields are stripped vs verbatim; vertex/index header policy; BSP HP2 binding to `scenario_structure_bsp_reference`. |
| `m2_arena_capacity_auditor` | Which EE region owns CTAG image vs BSP tail; whether `TAG_CACHE_SIZE` macro tracks that owner size. |
| `m2_loader_failure_auditor` | Map precache / `cache_file_read` replacement, async completion, unload baseline. |
| `m1_abi_layout_auditor` | Confirms `cache_file_tag_instance` / `tag_reference` sizes under R5900 (already partially in `ps2_abi.c`). |

## Open questions

1. **Single vs split region for verify:** Can `cache_file_tag_header_verify` keep using one `tag_header` pointer as region base while BSP lives only in `current_bsp`, or must verification split into tag-image + BSP regions (today Xbox assumes contiguous tag cache tail, `cache_files.c` ~509–515)?
2. **Vertex/index header on PS2:** If all model geometry is external, must `vertex_buffer_count` be zero, or do collision/render paths still register buffers from a stub header?
3. **File-range table for externalized `tag_data`:** Replicate `tag_validate_file_range` from Custom Edition for bitmap/sound offsets into HP2 packs?
4. **Section tag name and versioning:** Final HP2 fourCC (`CTAG` vs `TAGS`) and whether v1 bundles relocation table inside section or as a sibling `CREL` section.
5. **Menu/mod tags:** Loaded after map tags (`scenario_tags_load` ~1318–1337); CTAG contract covers map-only—overlay ordering unchanged.
6. **Absolute index stability when dropping tags:** Full retail parity vs N64-style `NONE` group holes for stripped groups.

## Handoff summary

**Choose materialized EE pointers at runtime**, produced by applying a **bounded relocation table** to a **little-endian CTAG image** delivered inside HP2—not raw Xbox VAs, not offset-only access without an HCU-wide accessor refactor. The loaded byte layout must match `cache_file_tag_header` / `cache_file_tag_instance` and pass the **real** `tag_validate_tags` (now linked on PS2, but still capped at 2 MiB until arena-backed scratch is implemented). BSP bytes remain a **second load** into a predeclared `base_address` in the BSP owner region. Retail maps prove **3.9–11 MiB** of struct data alone after geometry strip—format + partitioning are mandatory; enlarging the 2 MiB bootstrap array is not a format decision and does not pass M2 without measured owners. Implement the schema-aware converter (CTAG v1 + relocs), PS2 `scenario_tags_load` adapter, dynamic validation scratch and arena routing next; gate on synthetic + Blood Gulch fixtures and arena high-water from sibling auditors.

## Corroboration

### Agreements

- **m2_map_conversion:** Triple HP2 packs do not satisfy `scenario_tags_load`; separate CTAG section is required alongside BSP/MODL/TEX paths.
- **m2_arena_capacity:** Retail **tag_struct_bytes** exceed **2 MiB** — format choice (materialized pointers) does not remove partition/owner requirement (**C1**).
- **m2_loader_failure:** Fail-closed L2+ must apply at CTAG parse/reloc apply; HP2 L1 alone is insufficient.
- **m0_memory_ledger:** Tag region is a logical cap until partitioned owners are wired; CTAG load targets `resident_gameplay` sub-owners per contract.
- **m3_collision_owner:** BSP/collision bytes load into `current_bsp` / CE globals — second load, not embedded in tag struct blob.

### Conflicts

- **C1:** Corroborated **open** — integrator must choose partitioned stores + streaming, not “grow 2 MiB array.”

### Updated handoff

1. Implement a schema-aware CTAG v1 repacker and HP2 integration; the host-only envelope parser is not a retail converter.
2. Route validator claim scratch through a named fixed arena and relax the bootstrap-only tag span only after ownership/peak-overlap evidence exists.
3. Synthetic fixture first, then Blood Gulch; pair with **m2_arena** peak overlap measurement.
4. Document CTAG fourCC/version with **m2_map_conversion** pack layout section tags.
