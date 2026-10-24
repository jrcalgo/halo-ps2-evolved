# m2_arena_capacity_auditor

## Mission

Measure and document **working-set and high-water evidence** for M2 arena planning across CE tag residency, structure BSP / collision, textures, and sound. Cite aggregate retail reports under `docs/reports/` only. Explain why the current HCU **2 MiB** tag staging cap cannot load retail maps. Do **not** invent new pool sizes or close M0–M3 gates from estimates.

Evidence baseline (Round 1): parent HEAD `a2575e957feefbdff27febedabf60590401e6bcc`, HCU HEAD `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`, `halo-local.elf` SHA-256 `e45b4719d35450a77f2a541a7ed8abb877e5fbef495fc918539f8da91de597a2` when present.

## Inputs examined

| Source | Role |
|---|---|
| `docs/reports/tag-index.md` | Per-map Xbox tag-region layout, model buffers, tag-structure bytes, `sbsp` counts |
| `docs/reports/tag-payload-inventory.md` | Per-map bitmap and sound **payload** scale (not EE residency) |
| `config/memory-budget.json` | Version-2 EE region byte budgets |
| `docs/hcu-ps2-closure.md` | HCU bootstrap buffer sizes and logical region assignment |
| `docs/hcu-tag-loader-contract.md` | CE loader pointer and BSP placement assumptions |
| `docs/memory.md` | Parent world-arena high water (Blood Gulch stream viewer), converted pack sizes |
| `docs/player-movement.md` | Parent `COLL` pack size for one map |
| `plans/5.hcu-remake.md` | M2 checkpoint text on tag caps and partitioning |
| `submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h` | Declared PS2 bootstrap limits (not retail fit proof) |
| `submodules/halo-ce-universal/port/ps2/src/ps2_memory.c` | Static backing arrays for tag / texture / sound staging |
| `submodules/halo-ce-universal/source/cache/physical_memory_map.h` | Xbox `TAG_CACHE_SIZE` vs PS2 `HALO_PORT_TAG_CACHE_SIZE` |
| `submodules/halo-ce-universal/source/cache/cache_files.c` | `scenario_tags_load`, BSP verify/load in tag-cache tail |

## Findings

### 1. What is measured today vs what is not

**Measured (aggregate retail, tracked reports):**

- Raw Xbox **tag region** size per map: **6.71–16.21 MiB** for the 23 non-`ui` maps; **`ui`** is **1.57 MiB** (`docs/reports/tag-index.md` per-map table).
- **Tag-structure bytes** after removing only model vertex and index buffers: **3.93–10.96 MiB** on the same maps (`tag structs` column, `docs/reports/tag-index.md`).
- Model vertex + index buffers alone: roughly **2.40–4.86 MiB** vertices plus **0.25–0.54 MiB** indices on campaign maps; **~2.41–2.58 MiB** + **~0.25–0.27 MiB** on the smallest multiplayer maps (`docs/reports/tag-index.md`).
- Bitmap and sound **on-disc / tag-referenced payload** scale: **18.6–56.5 MiB** bitmaps and **11.5–164.5 MiB** sound per map (`docs/reports/tag-payload-inventory.md`). The report explicitly states these are not simultaneous EE residency requirements.
- HCU bootstrap **declared** staging sizes: tag **2,097,152** bytes (`HALO_PORT_TAG_CACHE_SIZE` / `0x200000`), texture staging **524,288** bytes (`32 × 16 KiB`), sound staging **524,288** bytes (`docs/hcu-ps2-closure.md`, `halo_ps2_limits.h`, `ps2_memory.c`).

**Measured (parent hybrid path, not HCU tag load):**

- Blood Gulch stream viewer: **12 MiB** boot arena; steady use **5,279,024** bytes after load; logged high water **6,465,536** bytes (**174,080** bytes above the **6,291,456**-byte `current_bsp` budget region) (`docs/memory.md`).
- Converted Blood Gulch packs (one map, parent converter): BSP **405,504**, objects **2,344,960–2,441,216**, textures **350,208** bytes; arena-resident TEXS **406,016**, lightmaps **33,120**; render BSP raw **611,856**; collision tables **666,372** bytes in `COLL` pack (`docs/memory.md`, `docs/player-movement.md`, `docs/milestones.md`).

**Not measured (open for M2):**

- HCU **peak tag-image** residency for any converted map (no map has passed `scenario_tags_load` + `tag_validate_tags` on PS2).
- **Per-map retail structure-BSP block bytes** in the tracked `docs/reports/tag-index.md` (that report lists `sbsp` **counts** and paths, not per-BSP `reference->file_size`). Submodule Halo-PS2 reports include a Structure BSP table for some campaign maps only; that table is **not** in the tracked report and is not cited here as retail evidence.
- **Simultaneous peak overlap** of permanent tags + active BSP + CE collision working set + texture EE staging + audio staging + `dynamic_simulation` under budget v2 during map load, BSP switch, and reload.
- PS2-converted bitmap/sound bytes per map in EE, GS eDRAM, disc, and SPU2 RAM (payload inventory is Xbox raw sizes only).

### 2. Budget v2 EE regions (context for overlap)

From `config/memory-budget.json` (33,554,432 bytes total EE; **5,767,168** reserve uncommitted):

| Region | Bytes | M2 relevance |
|---|---:|---|
| `current_bsp` | 6,291,456 | Intended owner for map/BSP-heavy data (`hcu-ps2-memory-map.json` maps `tag_cache` here logically) |
| `resident_gameplay` | 6,815,744 | Permanent gameplay / object packs |
| `texture_cache` | 4,194,304 | EE RAM for textures and lightmaps (not GS eDRAM) |
| `dynamic_simulation` | 2,621,440 | Transient simulation pools (M2 must not double-count nested CE object pool) |
| `streaming` | 1,572,864 | Stream/read staging |
| `audio` | 524,288 | Audio staging on EE |
| `elf_static` | 2,097,152 | Executable and static tables |

HCU’s standalone link today places **2,097,152** bytes of `tag_cache` alone into the logical `current_bsp` slot; the full ELF **10,126,828** allocated bytes are **not** a complete game+parent map (`docs/hcu-ps2-closure.md`). Parent stream-viewer high water already exceeds **`current_bsp`** before HCU tag bytes are integrated (`docs/memory.md`).

### 3. Tags — retail working-set lower bounds (tag-index)

The Halo-PS2 `tagindex.py` report (`docs/reports/tag-index.md`) partitions each map’s contiguous **tag region** into:

- **array + paths** (~0.05–0.11 MiB + ~0.06–0.17 MiB),
- **vertex buf** and **index buf** (model geometry embedded in the tag region),
- **tag structs** (everything else in the region, including scenario, bitmap/sound **tag records**, `coll`, scripts, effects, etc.).

**Implication for HCU:** `scenario_tags_load` reads `header.tag_data_size` bytes into the tag-cache base as one contiguous image (`docs/hcu-tag-loader-contract.md`, `cache_files.c`). That size on retail maps is the **tag region** column, not the stripped **tag structs** column.

#### 3.1 Per-map tag region vs 2 MiB cap

`HALO_PORT_TAG_CACHE_SIZE` is **2,097,152** bytes (`halo_ps2_limits.h`). `TAG_CACHE_SIZE` on PS2 equals that constant (`physical_memory_map.h`). Retail **tag region** sizes (bytes from report section headers where given; MiB from summary table):

| Class | Maps | Tag region (MiB) | Tag structs only (MiB) | Fits 2 MiB tag region? |
|---|---|---:|---:|---|
| Smallest MP | hangemhigh, prisoner, putput | 6.71 | 3.93 | **No** / **No** |
| Typical MP | bloodgulch, beavercreek, wizard | 6.72–7.04 | 3.94–4.14 | **No** / **No** |
| Smallest campaign | c20 | 8.54 | 5.85 | **No** / **No** |
| Largest campaign | b40 | 16.21 | 10.96 | **No** / **No** |
| UI only | ui | 1.57 | 1.35 | **Yes** (only retained map under 2 MiB tag region) |

Exact byte example: `hangemhigh` tag data **7,040,008** bytes at offset `0x22f6200` (`docs/reports/tag-index.md`); **3.93 MiB** tag structs after stripping **2.41 MiB** vertices and **0.25 MiB** indices.

**Only `ui`** has a tag region under **2 MiB** in the inventory. All **23 gameplay maps** exceed **2,097,152** bytes at the first read of `tag_data_size`.

#### 3.2 Why “strip model vertices” does not rescue 2 MiB

Even if M2 moved **all** vertex and index buffers out of the CE tag image (parent already keeps render geometry in HP2 packs per plan), the report’s **tag structs** column remains **3.93–10.96 MiB** on non-`ui` maps. That column is a **lower bound** on schema-preserving permanent tag bytes still referenced by CE (`tag_get`, reflexives, script nodes, bitmap/sound tag headers, `coll` tags, etc.).

Campaign maps also carry large script surface area in the tag graph (e.g. **4,557–17,516** script nodes per `tag-payload-inventory.md`), which must remain addressable if campaign scope is retained (`tag-payload-inventory.md` M2 implications).

#### 3.3 Xbox reference scale (not a PS2 allocation proposal)

Retail Xbox builds use **`TAG_CACHE_SIZE 0x01600000` (22 MiB)** when not on `HALO_PS2` (`physical_memory_map.h`). The measured retail tag regions (**6.71–16.21 MiB**) fit inside **22 MiB** with headroom for **BSP tail** loads (see below). PS2’s **2 MiB** cap is a **bootstrap fail-closed bound**, not a measured retail capacity (`halo_ps2_limits.h` comment, `docs/hcu-ps2-closure.md`).

#### 3.4 Tag groups with collision / audio / texture *metadata*

Counts are not byte sizes; they bound converter and validator work and show that “tags” are not only scenario + BSP:

- **`coll`**: **25–62** tags per map (e.g. a10 **47**, bloodgulch **36**) (`docs/reports/tag-index.md` group table).
- **`bitm`**: **329–525** on gameplay maps (**195** on `ui`).
- **`snd!`**: **314–1,510** on gameplay maps (**29** on `ui`).

Payload bytes for bitmaps/sounds live in separate inventory columns (`tag-payload-inventory.md`), not in the tag-region partition.

### 4. Why the 2 MiB tag cap fails (mechanism + arithmetic)

**A. First load fails `tag_data_size` bound.**

`cache_file_header_verify` requires `header->tag_data_size <= TAG_CACHE_SIZE` (`cache_files.c`). With `TAG_CACHE_SIZE == 2,097,152`, any map whose tag region exceeds **2 MiB** is rejected before validation. **23 of 24** retained maps fail on tag region alone; only **`ui`** is below **2 MiB** total tag region (**1,642,244** bytes in the detailed section).

**B. Even a hypothetical “structs-only” image exceeds the cap on every gameplay map.**

Minimum **tag structs** reported: **3.93 MiB** (hangemhigh, prisoner, putput) **>** **2 MiB**. No gameplay map in the inventory reports struct-only bytes under **2,097,152**.

**C. BSP tail sharing the same `TAG_CACHE_SIZE` window.**

On stock CE (non–Custom Edition), structure BSPs load into the tag cache **after** `tag_data_size`, and verification requires the BSP read to fit in **`TAG_CACHE_SIZE - tag_data_size`** (`cache_files.c` `cache_file_structure_bsp_reference_verify`, `scenario_structure_bsp_load`). Therefore the **single** `tag_cache` array must cover **tag image + active BSP extent** (plus alignment), not tag image alone (`docs/hcu-tag-loader-contract.md`).

Additional constraints from the same verifier:

- Each `reference->file_size` must be **`<= TAG_CACHE_SIZE`** individually (`cache_files.c`).
- So a **single** structure BSP larger than **2 MiB** fails even if tag data were empty.

**Tracked report gap:** per-BSP `file_size` for retail maps is **not** listed in `docs/reports/tag-index.md`. **Unknown** whether every retail BSP is **≤ 2 MiB** in isolation; **known** that several campaign BSPs in extended Halo-PS2 documentation exceed **2 MiB** per block (not duplicated here as tracked evidence). For PS2, failing the **tag region** check already blocks all gameplay maps regardless.

**D. Raising only `HALO_PORT_TAG_CACHE_SIZE` toward retail raw sizes does not close M2.**

`plans/5.hcu-remake.md` and `docs/hcu-tag-loader-contract.md` state that matching raw **6.71–16.21 MiB** tag regions:

1. **Violates EE budget** if charged entirely to `current_bsp` (**6,291,456** bytes) or any single region without partitioning.
2. **Still omits** bitmap/sound **payloads** (tens to hundreds of MiB per map in `tag-payload-inventory.md`).
3. **Still duplicates** geometry/textures already owned by HP2 packs if loaders are not redesigned.
4. **Does not replace** schema validation, relocation, or pointer materialization (`tag_validate_tags`, direct pointers in tag blocks).

**E. Fail-closed memset proves the cap is enforced.**

`scenario_tags_load` fills the tag cache with `0xCD` up to `TAG_CACHE_SIZE` on bounded PS2 builds (`cache_files.c`), matching the fixed `tag_cache[PS2_TAG_CACHE_BYTES]` array (`ps2_memory.c`).

### 5. BSP and collision — residency and evidence

#### 5.1 CE ownership model

- **`sbsp` tags** in the tag array have **data address 0**; BSP bytes live in the map file at offsets recorded in the scenario’s structure-BSP block (`docs/reports/tag-index.md` layout table).
- HCU loads the active BSP to `reference->base_address` with size `reference->file_size` (`docs/hcu-tag-loader-contract.md`, `cache_files.c`).
- **`coll` tags** (counts in tag-index) describe collision models; their struct bytes are part of **tag structs**, not the separate BSP read path. CE collision against structure geometry uses the loaded **structure BSP** (`docs/hcu-tag-loader-contract.md`).

#### 5.2 Multi-BSP maps (working-set shape)

`sbsp` count per map (`docs/reports/tag-index.md`):

| sbsp count | Example maps |
|---:|---|
| 1 | Most multiplayer maps, `ui` |
| 2–6 | a30, b30, c10, c20, d20, … |
| 9–13 | a10, b40, c40, d40 |

**Working-set note (behavioral, not a new size):** Retail CE keeps **one** loaded structure BSP for collision/render at a time in normal play, but **all** permanent tag data (including every `sbsp` tag’s metadata and scenario references) must remain valid in the tag image. M2 must measure peak during **BSP switch** (unload old BSP extent, load new) and during **load** (tag image + first BSP).

#### 5.3 Parent collision pack (single-map measurement, not retail tag report)

For Blood Gulch, parent `tools/convert_collision.py` emits **666,372** bytes of collision tables in a `COLL` pack, charged beside **611,856** bytes render BSP raw in `current_bsp` spare (`docs/player-movement.md`, `docs/memory.md`). That demonstrates **collision bytes are separate from tag structs** and must be budgeted in addition to CE tag images, not folded into the 2 MiB cap.

#### 5.4 Parent arena high water vs `current_bsp`

After Blood Gulch load in the stream viewer, **6,465,536** bytes high water in a **12 MiB** arena exceeds **`current_bsp` (6,291,456)** by **174,080** bytes (`docs/memory.md`). Steady **5,279,024** bytes mix BSP, textures, lightmaps, objects, and renderer tables without yet splitting across v2 regions. This is **parent-path** evidence that map residency planning must account for **combined** peaks, not tag cache alone.

**Unknown:** CE HCU collision BSP residency size per retail map on PS2 (no converted CE tag image + BSP load yet).

### 6. Textures — staging caps vs payload scale

#### 6.1 HCU bootstrap (declared, not retail working set)

- `HALO_PORT_TEXTURE_CACHE_SIZE`: **524,288** bytes (**32** pages × **16 KiB**) (`halo_ps2_limits.h`, `ps2_memory.c`).
- Budget region `texture_cache`: **4,194,304** bytes EE (`config/memory-budget.json`).
- GS eDRAM is a **separate 4 MiB** store (`docs/memory.md`); not part of the EE table.

HCU texture staging is **524,288** bytes against a **4,194,304**-byte EE `texture_cache` region (**12.5%** of that region if used as the sole charge) (`docs/hcu-ps2-closure.md`, `config/memory-budget.json`).

#### 6.2 Retail payload scale (tag-payload-inventory)

| Map class | Bitmap payload MiB (raw Xbox) | Images |
|---|---:|---:|
| MP low | 18.7–22.7 | 462–516 |
| MP typical | ~22 | ~500 |
| Campaign high | 45.7–56.5 | 863–1,009 |
| `ui` | 18.6 | 384 |

The report requires per-pack accounting in EE, GS eDRAM, and disc staging separately (`tag-payload-inventory.md`). **No** map’s bitmap payload fits in **524,288** bytes staging or entirely in **4,194,304** bytes EE cache at once.

#### 6.3 Parent converted Blood Gulch (one map)

- Compressed texture pack **350,208** bytes; decompressed TEXS **406,016**; lightmap **33,120** (`docs/memory.md`).
- Stream viewer: **16** BSP mip0 images **299,040** bytes forced through staging in a diagnostic (`docs/memory.md`); frame upload budget **1,572,864** bytes (`tc_init`, `docs/memory.md`).
- Halo-PS2 doc note (design bound, not this repo’s measured PS2 cap): default tex budget **3 MiB** of a **6 MiB** pool with BSP textures **≤ 1.1 MiB** (`submodules/halo-ps2/docs/11-model-section.md`) — treat as **upstream converter documentation**, not a committed pool size for HCU.

**Unknown:** HCU runtime texture high water on any retail or converted map.

### 7. Sound — staging caps vs payload scale

#### 7.1 HCU bootstrap

- `HALO_PORT_SOUND_CACHE_SIZE`: **524,288** bytes (`halo_ps2_limits.h`).
- Budget `audio` region: **524,288** bytes (`config/memory-budget.json`).
- SPU2 sound RAM **2 MiB** is separate hardware (`plans/5.hcu-remake.md`); IOP RAM **2 MiB** for IOP-side buffers — not substitutable for map-wide Xbox sample payloads.

Closure notes the HCU `sound_cache` array **exactly consumes** the `audio` region in logical accounting (`docs/hcu-ps2-closure.md`).

#### 7.2 Retail payload scale (tag-payload-inventory)

| Map class | Sound payload MiB | Permutations |
|---|---:|---:|
| MP | 11.5–15.3 | 913–985 |
| Campaign | 55.1–164.5 | 1,727–7,816 |
| `ui` | 11.8 | 259 |

`tag-payload-inventory.md` explicitly rejects implying the **512 KiB** EE staging buffer holds a whole map’s sound set. Campaign maps reference **thousands** of permutations; **`snd!` tag counts** reach **1,346–1,510** on large maps (`docs/reports/tag-index.md`).

**Unknown:** Transcoded ADPCM size per map on SPU2, active voice working set, and EE staging high water during combat.

### 8. Peak overlap sketch (charges must not double-count)

M2 must assign **exactly one owner** per byte (`docs/hcu-tag-loader-contract.md`, `config/memory-budget.json` notes). A conservative overlap checklist for **measurement fixtures** (not size proposals):

```
[elf_static]     HCU/parent code, constants (standalone HCU already nears elf_static — docs/hcu-ps2-closure.md)
[resident_gameplay] CE game_state, globals, permanent tag structs, object packs, rooted .bss
[current_bsp]    Active structure BSP + CE BSP tail policy + COLL/collision tables + OTEX scratch peaks
[texture_cache]  EE texture/lightmap pages + decode scratch (parent: TEXS + LM0 in arena today)
[dynamic_simulation] CE object pool (today nested in game_state — do not double-count)
[streaming]      HP2 read staging (parent stream ELF: 1,048,576 storage + decode — docs/memory.md)
[audio]          EE sound staging before SPU2 upload
[frame_scratch]  Pill/collision scratch (parent: 47,644 bytes — docs/player-movement.md)
GS eDRAM / IOP / SPU2   Separate from EE regions
```

**Known conflict:** Parent arena high water **>** `current_bsp` before HCU integration (`docs/memory.md`). **Known:** Retail tag region **>** HCU tag cap on all gameplay maps. **Unknown:** CE+parent combined peak on the same v2 ledger.

### 9. Bootstrap constants vs pool sizes (do not conflate)

| Symbol / buffer | Declared bytes | Evidence type |
|---|---:|---|
| `HALO_PORT_TAG_CACHE_SIZE` | 2,097,152 | Bootstrap cap; retail tag regions exceed |
| `HALO_PORT_TEXTURE_CACHE_SIZE` | 524,288 | Bootstrap staging; retail bitmap payloads exceed |
| `HALO_PORT_SOUND_CACHE_SIZE` | 524,288 | Bootstrap staging; retail sound payloads exceed |
| `HALO_PORT_OBJECT_MEMORY_POOL_SIZE` | 1,048,576 | Xbox-retained **count** macro; nested in `game_state` today — **not** measured PS2 high water (`halo_ps2_limits.h`, `docs/hcu-ps2-closure.md`) |
| `HALO_PORT_MAXIMUM_*` actor/object/effect counts | various | Xbox values pending PS2 measurement (`halo_ps2_limits.h` header comment) |

Do **not** treat Xbox pool count macros or N64/OpenCE limits as PS2 budgets (`plans/5.hcu-remake.md`).

## Interface contracts for the main agent

1. **Partition before resize:** Emit permanent tag structs, transient BSP/collision, render geometry, and bitmap/sound payloads into distinct owners with validated relocation or consistent offset accessors (`docs/hcu-tag-loader-contract.md`). Increasing `HALO_PORT_TAG_CACHE_SIZE` alone is insufficient and unsafe for EE v2.
2. **Loader invariants:** Preserve `tag_data_size` bounds, BSP `reference->file_size` checks, and pointer containment rules in `cache_files.c` until the access layer is migrated wholesale.
3. **Accounting:** Charge BSP tail, `COLL`, and OTEX-style scratch in `current_bsp` (or documented sub-arenas); charge bitmap/sound **payloads** against streaming/GS/SPU2, not the 2 MiB tag array.
4. **Fail closed:** Maps whose **measured** peak exceeds a region are rejected (`plans/5.hcu-remake.md` M2/M5); bootstrap caps remain until conversion proves otherwise.
5. **Reserve:** Do not spend **5,767,168** bytes reserve to “fit” tag data without a versioned budget revision and measured end-to-end proof (`config/memory-budget.json`).

## Recommended tests / fixtures

1. **Tag-index regression:** Host test that every map in `docs/reports/tag-index.md` has `tag_region_bytes > HALO_PORT_TAG_CACHE_SIZE` except `ui`, and `tag_struct_bytes > HALO_PORT_TAG_CACHE_SIZE` for all non-`ui` maps (parse MiB table or JSON from `tagindex.py report --json`).
2. **Loader rejection fixtures:** Truncated `tag_data_size`, `tag_data_size == 2,097,152 + 1`, and BSP `file_size` greater than remaining tail — expect verify failures without guest boot.
3. **Per-map peak ledger:** After CE tag image + BSP load on PS2, record high water per v2 region, GS, IOP, SPU2; include BSP switch and three reload cycles (pattern from `docs/memory.md` / M11 teardown).
4. **Payload spot checks:** For one MP and one campaign map, compare `tag-payload-inventory.md` permutation counts to staged bytes on disc and EE after streaming (no assumption that full payload is resident).
5. **Collision:** Load `COLL` + structure BSP for Blood Gulch–class map; assert scratch **47,644** bytes (`docs/player-movement.md`) stays inside `frame_scratch`.
6. **Double-count guard:** Assert `game_state_malloc` object pool is not also summed into `dynamic_simulation` (`docs/hcu-ps2-closure.md`).

## Dependencies on other investigators

| Investigator | Dependency |
|---|---|
| `m2_tag_image_format_investigator` | Serialized tag image layout, relocation, and what remains in “tag structs” after partition |
| `m2_loader_failure_auditor` | Failure modes when verify/run against bootstrap caps |
| `m2_map_conversion_auditor` | HP2 section sizes vs CE bytes for the same map |
| `m0_memory_ledger_auditor` | Accepting logical region assignment vs physical arena routing |
| `m3_collision_owner_auditor` | CE vs parent collision residency once BSP loads |

## Open questions

1. Per-map retail **`reference->file_size`** for each structure BSP (extend tracked `tag-index` report or new aggregate report).
2. CE **converted** tag-image size per map after moving vertices/bitmaps/sounds out — may be below raw **tag structs** but still above **2 MiB** on all gameplay maps until proven.
3. Maximum **simultaneous** BSP bytes if CE retains Xbox tail-in-cache layout vs HP2 `BSP*` sections.
4. PS2 **texture** high water during 12-view sweeps and combat-heavy scenes on campaign maps (**56.5 MiB** raw bitmap class on `d40`).
5. **Sound** bank strategy: which permutations are resident on SPU2 vs streamed given **2 MiB** SPU2 RAM and **524,288** EE staging.
6. Whether resolving parent arena overrun (**174,080** bytes) is a layout split only or requires shrinking converted data.

## Handoff summary

Retail **tag regions (6.71–16.21 MiB)** and **tag structs alone (3.93–10.96 MiB)** from `docs/reports/tag-index.md` **prove the HCU 2 MiB tag cache cannot load any gameplay map** under the current `scenario_tags_load` contract. Only **`ui`** fits the cap on total tag region size. **Bitmap and sound payloads** from `tag-payload-inventory.md` are orders of magnitude larger than **512 KiB** EE staging and require streaming and separate stores; they are not solved by enlarging the tag array. **BSP/collision** requires space beyond tag structs (separate BSP reads, `coll` tags, parent `COLL` **666,372** bytes example); parent Blood Gulch arena high water already **exceeds** `current_bsp`. M2 must **partition, relocate, and measure peak overlap** on budget v2 — not raise bootstrap caps to retail raw sizes. No new pool sizes are proposed here; use declared `HALO_PORT_*` limits only as documented fail-closed bootstrap bounds.

## Corroboration

### Agreements

- **m2_tag_image_format:** CTAG materialization does not eliminate partition need — agrees retail struct totals.
- **m2_map_conversion:** Stripped geometry vs tag_struct_bytes split matches MODL vs CTAG ownership story.
- **m0_memory_ledger:** v2 region caps are bootstrap bounds; measured overlap is required for M2 exit, not ledger arithmetic alone.
- **m1_dma_layout_auditor:** `frame_scratch` snapshot budget is separate from tag/BSP peak — do not steal tag owner for snapshot without remeasure.
- **m3_collision_owner:** BSP + collision residency consumes `current_bsp` / CE globals beyond tag array.

### Conflicts

- **C1:** Unanimous — **2 MiB** contiguous tag store is invalid for gameplay maps; Round 3 integrator must publish partition map.
- **C5:** Logical regions vs monolithic BSS — arena high-water tests must run after parent routing, not on today's standalone ELF layout alone.

### Updated handoff

1. M2 deliverable: peak overlap table per map class (ui / MP / campaign) using `tag-index.md` + streaming totals.
2. Do not propose new `HALO_PORT_*` caps in implementation PRs without remeasure — use fail-closed bootstrap limits until evidence says otherwise.
3. Blood Gulch parent arena overrun example stays the first integrated measurement target.
