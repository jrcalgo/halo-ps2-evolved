# m2_loader_failure_auditor

## Mission

Specify fail-closed loader behavior for M2: every bounds check, malformed-image rejection, missing-map path, and unload/reload baseline the hybrid port must implement before retail map load can be claimed. Ground the specification in (1) existing HP2 validation in `submodules/halo-ps2/engine/src/stream/hp2.c`, (2) the audited CE cache/tag contract in `docs/hcu-tag-loader-contract.md`, and (3) retail HCU `scenario_tags_load` / BSP / unload semantics in `submodules/halo-ce-universal/source/cache/cache_files.c` and `scenario.c`. Report-only; no implementation claims.

## Inputs examined

| Area | Paths / symbols |
|------|-----------------|
| Prompt contract | `docs/investigations/_prompt_contract.md` |
| Loader contract (M2 gate) | `docs/hcu-tag-loader-contract.md` |
| M2 plan exit criteria | `plans/5.hcu-remake.md` (M2 §3–5, exit gate) |
| HP2 C reader | `submodules/halo-ps2/engine/src/stream/hp2.c`, `hp2.h` |
| HP2 format | `submodules/halo-ps2/docs/07-hp2-format.md` |
| HP2 Python reference | `submodules/halo-ps2/tools/halo2ps2/hp2.py`, `tools/tests/test_hp2.py` |
| HP2 host tests | `submodules/halo-ps2/engine/tests/test_hp2.c` |
| Parent world loader (HP2 consumer) | `submodules/halo-ps2/engine/src/world/world.c` (`world_load_section`, `world_load`) |
| Render BSP bounds (post-decode) | `submodules/halo-ps2/engine/src/world/bsp.c` (`bsp_open`), `engine/tests/test_bsp.c` |
| HCU tag load / verify | `submodules/halo-ce-universal/source/cache/cache_files.c` (`cache_file_header_verify`, `cache_file_tag_header_verify`, `scenario_tags_load`, `scenario_structure_bsp_load`, `scenario_tags_unload`) |
| HCU scenario lifecycle | `submodules/halo-ce-universal/source/scenario/scenario.c` (`scenario_load`, `scenario_unload`, `scenario_switch_structure_bsp`) |
| HCU schema validator | `submodules/halo-ce-universal/port/linux/game/tag_validate.c` |
| PS2 caps / bootstrap memory | `submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h`, `port/ps2/src/ps2_memory.c` |
| PS2 placeholder risk | `docs/hcu-ps2-platform-placeholder-audit.md` |
| Retail scale (not fit proof) | `docs/reports/tag-index.md`, `docs/reports/tag-payload-inventory.md` |
| EE budget regions | `config/memory-budget.json` v2 |

Evidence baseline per `_prompt_contract.md`: parent HEAD `a2575e957feefbdff27febedabf60590401e6bcc`, HCU HEAD `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`.

## Findings

### 1. Layered failure model (what must fail closed, and where)

M2 load is not one function; it is a **stack of validators** with different ownership. A failure at any layer must leave **no published gameplay authority** (no `global_tag_instances`, no collision BSP, no half-registered vertex buffers) unless the retail CE path explicitly rolls back (BSP switch only).

| Layer | Owner today | Validates | On failure (required behavior) |
|-------|-------------|-----------|--------------------------------|
| L0 — Pack / file I/O | Parent file service (M1/M2); **PS2 closure still placeholders** | Path exists, read length, optional streaming header | Return explicit error; **no** success-shaped zero reads (`docs/hcu-ps2-platform-placeholder-audit.md`) |
| L1 — HP2 container | `hp2.c` / `hp2.py` | Magic, version, file size, section table, per-section offset/size, codec, LZ4, CRC | Status ≠ `HP2_OK`; do not decode into destination |
| L2 — M2 tag image (not implemented) | Future converter + loader | Version, tables, relocations, cross-tag refs, region ownership | Refuse map; release partial allocations; see §4 |
| L3 — CE tag header + region | `cache_file_tag_header_verify` | Tag table, scenario index, vertex/index buffer tables, each non-null `base_address` in tag region | `scenario_tags_load` → `NONE`, `cache_file_close` (`cache_files.c:1254–1282`) |
| L4 — CE schema walk | `tag_validate_tags` | Pointer extents, overlap claims, indices/enums/tags; **refuse** on bad pointers | `scenario_tags_load` → `NONE`, `cache_file_close` (`cache_files.c:1274–1282`, `tag_validate.c:26–27`) |
| L5 — CE collision BSP | `scenario_structure_bsp_load` + `tag_validate_structure_bsp` | File extent, load target in tag cache tail, read complete, BSP header pointers, schema | `FALSE`; scenario switch may **reload previous BSP** (`scenario.c:1106–1134`) |
| L6 — Render/collision packs (parent) | `world_load_section` + `bsp_open` | HP2 + arena + `BSPS` layout | `NULL` / `-1`; caller must not treat world as loaded |

**Critical contract gap (documented, not optional):** HP2 L1 validation does **not** make CE L3–L5 safe. Typed converters (`SCEN`, `MODL`, …) are not a schema-preserving tag image (`docs/hcu-tag-loader-contract.md:48–49`). M2 must add L2 **or** materialize full CE pointers into a contiguous owning region before calling unmodified `tag_validate_tags` (`docs/hcu-tag-loader-contract.md:64–66`).

### 2. HP2 validation — specified checks (`hp2.c`)

Reference: `open_common` (`hp2.c:18–44`), `hp2_load_stored` (`hp2.c:103–116`), `lz4_decode` (`hp2.c:64–100`).

#### 2.1 `hp2_open` / `hp2_open_header` (header + section table only)

| Check | Condition | Status |
|-------|-----------|--------|
| Minimum bytes | `avail < 64` | `HP2_ERR_TRUNCATED` |
| Magic / version | Not `HP2P` or version ≠ 1 | `HP2_ERR_MAGIC` |
| Section count | `count > HP2_MAX_SECTIONS` (64) | `HP2_ERR_LAYOUT` |
| Declared file size | `rd32(image+8) != file_size` | `HP2_ERR_LAYOUT` |
| Table fits in `avail` | `64 + 32*count > avail` | `HP2_ERR_TRUNCATED` |
| Sector alignment | `offset % HP2_SECTOR` (2048) ≠ 0 | `HP2_ERR_LAYOUT` |
| Payload in file | `offset > file_size` OR `stored_size > file_size - offset` | `HP2_ERR_TRUNCATED` |

**Not validated at open (gaps M2 loader should either add or document as out of scope for L1):**

- **Duplicate section tags** — `hp2_find` returns first match; `hp2.py` `build` rejects duplicates, but `hp2.c` does not (`hp2.c:57–61`, `hp2.py:185–186`).
- **`align` field** — stored in `hp2_section` but **not enforced** by `hp2_load` (`hp2.h:27`, `07-hp2-format.md:28`).
- **Overlapping section payloads** — not detected if each entry individually fits the file.
- **Payload bytes present in `avail`** — `hp2_open_header` only requires the table in `hdr`; payload may be read later via `hp2_load_stored` (by design, `hp2.h:41–44`). A streaming loader must fail if the disc read returns fewer than `stored_size` bytes before calling decode.
- **`raw_size` / `stored_size` zero** — allowed; `hp2_load_stored` with `cap >= raw_size` succeeds for empty raw (`test_hp2.c:54–56`).

#### 2.2 `hp2_load` / `hp2_load_stored` (per section)

| Check | Condition | Status |
|-------|-----------|--------|
| Destination capacity | `cap < raw_size` | `HP2_ERR_SPACE` |
| Stored codec | `codec == HP2_CODEC_STORED` requires `stored_size == raw_size` | `HP2_ERR_LAYOUT` |
| Unknown codec | Not stored or LZ4 | `HP2_ERR_CODEC` |
| LZ4 decode | `lz4_decode` returns `< 0` or length ≠ `raw_size` | `HP2_ERR_DECODE` |
| CRC | `hp2_crc32(dst, raw_size) != section.crc32` | `HP2_ERR_CRC` |

#### 2.3 `lz4_decode` (malformed compressed stream)

Fails closed (returns `-1`) on: truncated literal/match extension bytes; literal length exceeding source or destination; missing match offset words; **zero or backward offset > output**; match length exceeding destination; any path that would overrun `cap` (`hp2.c:73–97`). Host tests cover literal overrun and zero offset (`test_hp2.c:69–73`).

#### 2.4 Python parity (`hp2.py`)

`parse` mirrors header/table rules (`hp2.py:210–224`). `read` adds payload truncation, codec, and CRC (`hp2.py:160–170`). `test_hp2.py` asserts corruption and truncated packs raise `Hp2Error` (`test_hp2.py:37–49`).

#### 2.5 Parent `world_load_section` (fail-closed consumer pattern)

Sequence: file size → read header → `hp2_open_header` → `hp2_find` → arena alloc for raw + scratch → read `stored_size` at `offset` → `hp2_load_stored` → release scratch mark (`world.c:9–37`).

| Failure | Observable | Fail-closed? |
|---------|------------|--------------|
| `file_size_of` < 0 | `NULL`, log cannot open | Yes |
| Header read error | `NULL` | Yes |
| `hp2_open_header` ≠ OK | `NULL` | Yes |
| Missing section (`!optional`) | `NULL`, log | Yes |
| `arena_alloc` failure | `NULL` | Yes |
| Payload read error | `NULL` | Yes |
| Decode ≠ OK | `NULL` | **Partial:** raw buffer may already be allocated in arena; scratch released. **M2 must** pair with `arena_reset` / level teardown so failed map load does not leave charged bytes (`arena_reset` in `mem.c:33–36`). |

`world_load` treats missing `BSP*` / failed `bsp_open` as hard failure (`world.c:103–106`). Optional sections (`LM*`, `ANIM`, `OTEX`, `SKY0`) use `optional=1` — absence is not a map failure.

### 3. HCU retail loader — fail-closed cases to preserve for M2

Source of truth for **gameplay tag authority** remains `scenario_tags_load` until the access layer is consistently offset-based (`docs/hcu-tag-loader-contract.md`).

#### 3.1 Missing map / bad cache file

| Stage | Check | Outcome |
|-------|-------|---------|
| Open | `cache_file_open` fails | `scenario_tags_load` returns `NONE` (no close needed) (`cache_files.c:1233–1347`) |
| Header | `cache_file_header_verify` — signatures, `file_length`, `tag_data_offset`/`tag_data_size` vs `TAG_CACHE_SIZE`, no overflow (`cache_files.c:870–935`) | `cache_file_close`, `NONE` |
| Read tags | `read_complete != TRUE` | Error, `cache_file_close`, `NONE` (`cache_files.c:1254–1259`) |
| Tag header | `cache_file_tag_header_verify` — signature, counts, scenario tag, each `base_address` in region (`cache_files.c:388–467`) | `cache_file_close`, `NONE` |
| Schema | `tag_validate_tags` | `cache_file_close`, `NONE` (`cache_files.c:1274–1282`) |

`cache_file_header_verify` also refuses wrong `version` (not 5 for Xbox path) and damaged name field (`cache_files.c:903–912`, `886–886`).

**PS2 risk:** generated `cache_file_open` / `ReadFile` placeholders can report success without data (`docs/hcu-ps2-platform-placeholder-audit.md:13–14`). M2 tests must not run against those stubs without a real bounded file service.

#### 3.2 Malformed tag image (in-cache, post-read)

`cache_file_region_contains` defines the arithmetic for all extent checks: `count > 0`, address ≥ region base, `offset + count*element_size ≤ region_size` (`cache_files.c:347–362`).

`tag_validate_tags` refuses (does not “correct”) when:

- Schema machinery broken (`schemas_fit`) (`tag_validate.c:1208–1211`)
- Header signature, `tag_count`, or instance table out of region (`tag_validate.c:1213–1219`)
- Buffer tables or per-tag claims fail (`tag_validate.c:1221–1228`)
- Any schema walk sets `validation.refused` (bad pointers, cyclic block graph via claim bits — `tag_validate.c:12–19`, `922+`)

Maps with **wrong pointers are refused**; some index/enum issues are corrected and logged (`tag_validate.c:20–27`).

#### 3.3 BSP load failure and rollback

`scenario_structure_bsp_load` fails closed on: reference extent vs map file; load target outside `tag_cache_base + tag_data_size .. TAG_CACHE_SIZE`; incomplete read; bad BSP header pointers; `tag_validate_structure_bsp` failure (`cache_files.c:1374–1450`).

`scenario_switch_structure_bsp`: unloads old BSP before loading new; if new load fails, attempts to **reload old BSP**; if that fails, globals nulled and may `main_goto_main_menu` (`scenario.c:1081–1134`). First BSP failure in `scenario_load` means `scenario_switch_structure_bsp(0)` fails → `scenario_load` returns `FALSE` (`scenario.c:1203–1212`).

**M2 implication:** collision BSP bytes must have a **single declared owner** (`current_bsp` per `config/memory-budget.json`); a second HP2 pack section without updating CE `reference->base_address` breaks `cache_file_structure_bsp_reference_verify` semantics (`docs/hcu-tag-loader-contract.md:28–36`).

#### 3.4 Unload / reload baseline (CE)

`scenario_unload` → `scenario_tags_unload` → closes sound/texture caches, unloads menu/mod tags, `cache_file_close`, deregisters vertex/index buffers, clears `global_tag_instances` / `tags_loaded` (`scenario.c:361–377`, `cache_files.c:592–627`).

**Required M2 baseline properties (exit gate, `plans/5.hcu-remake.md:136`):**

1. After successful unload, no live pointers into the previous map’s tag/BSP storage.
2. After failed load, same as (1) — no `tags_loaded`, no BSP globals (`scenario_load` / `scenario_tags_load` paths above).
3. Repeated load/unload of the same map: arena high-water for parent world path returns to ≤ prior baseline (`arena_reset`); HCU side must not leak bump `malloc_arena` without reset policy (`ps2_memory.c:73–82` — **no free**; exhaustion returns `NULL`).
4. Map switch mid-session: texture/sound caches closed in `scenario_tags_unload` before tag table torn down — order is load-bearing (`cache_files.c:601–617`).

### 4. M2 runtime tag image — bounds and malformed cases to specify (L2)

No implementation exists; `docs/hcu-tag-loader-contract.md:78–83` lists host fixture requirements. The following is the **auditor’s normative checklist** for the main agent, aligned with CE + HP2.

#### 4.1 Image header (versioned, checksummed — plan step 3)

Must validate before exposing any pointer to CE:

| Class | Examples | Fail closed |
|-------|----------|-------------|
| Magic / version | Unknown magic or unsupported version | Refuse; do not partially apply relocations |
| Total image size | Header `size` vs actual bytes / HP2 `raw_size` | Refuse |
| Table extents | Tag count, string table, relocation count, stride fields | Reject on overflow in `count * stride + base` (64-bit intermediate) |
| Scenario index | Absolute index in range; group `scnr` | Match `cache_file_tag_header_verify` scenario checks (`cache_files.c:432–439`) |
| Checksum | Header + payload hash | Refuse on mismatch (same role as HP2 CRC) |

#### 4.2 Relocation / pointer materialization

Required if not using pure offset accessors (`docs/hcu-tag-loader-contract.md:64–66`):

| Class | Detection | Fail closed |
|-------|-----------|-------------|
| Out-of-range target | Reloc target outside owning region | Refuse map |
| Misaligned target | Violates 16-byte (or tag-specific) alignment | Refuse |
| Duplicate ownership | Two relocations claim same destination range | Refuse |
| Cyclic reloc graph | Cycle in pointer fixup order | Refuse (analogous to `tag_validate` claim bits, `tag_validate.c:15–19`) |
| Xbox absolute addresses | Unconverted CE file offsets left in image | Refuse at validate |
| Truncated reloc stream | Entry extends past image | Refuse |

#### 4.3 Cross-tag references

| Class | Fail closed |
|-------|-------------|
| Tag index ≥ count or wrong generation | Refuse (CE uses datum index with generation — `cache_get_tag_instance`, `cache_files.c:299–312`) |
| Reference to stripped/unsupported group | Refuse or explicit unsupported-field policy (plan step 4) |
| BSP reference | Must map to bounded load target + size; multi-BSP maps need per-index targets (`docs/hcu-tag-loader-contract.md:74–76`) |

#### 4.4 Budget / region exhaustion

| Class | Policy |
|-------|--------|
| Tag image larger than assigned region (not necessarily 2 MiB — retail 3.93–10.96 MiB tag-structure bytes per `plans/5.hcu-remake.md:138`) | Refuse before read |
| BSP + tag peak > `current_bsp` | Refuse |
| Converter scratch + load peak > `streaming` | Refuse or bounded double-buffer policy with measured peak |
| `HALO_PORT_TAG_CACHE_SIZE` (`0x200000`, `halo_ps2_limits.h:24`) | **Bootstrap cap only** — retail maps exceed it; refusing is correct for current buffer, not evidence of M2 completion |

Fail closed means: **no** fallback to empty tags for required data (contrast `cache_empty_tag_instance` for invalid *runtime* indices — `cache_files.c:322–341`, not for load).

#### 4.5 HP2 section binding for tag image

Plan step 4: load through HP2 with existing L1 checks. Additional M2 rules:

- Section tag(s) reserved for tag image (e.g. `TAGS` / name TBD by format investigator) must be **required** for map packs, not optional.
- Decode buffer capacity must use **declared** `raw_size`, not a fixed 2 MiB.
- On failure after partial decode: free/reset destination arena; do not call `tag_validate_tags` on buffer.

### 5. Missing-map and precache paths

| Path | Behavior to preserve / test |
|------|-----------------------------|
| `game_precache_new_map` | `cache_files_precache_map_begin` false → error “map doesn't exist”; blocking may assert (`game.c:834–848`) |
| Precache failure status | `_cached_map_file_failed` → `display_error_damaged_media` (`game.c:877–878`) |
| `scenario_load` with failed tags | `global_scenario_index == NONE` → delayed errors listing missing tags (`scenario.c:1219–1239`) |
| `world_load_section` | Missing file / section → `NULL` (hard fail for required tags) |

M2 adapter must expose **distinct** errors: not found, truncated, corrupt (CRC/schema), unsupported version, budget exceeded — even if UI remains deferred (`docs/hcu-ps2-platform-placeholder-audit.md:20`).

### 6. Render BSP (`bsp_open`) — post-HP2 malformed image

Independent of CE collision BSP: `bsp_open` validates `BSPS` magic, version, size field, table alignment, record counts, batch/VIF packets, portal/cluster indices, acyclic BSP tree (`bsp.c:62–164`). Fuzz-style tests reject truncated and tampered tables (`test_bsp.c:184–251`). M2 campaign path using CE collision must not assume `BSP0` HP2 section satisfies CE `structure_bsp` layout without explicit conversion ownership.

## Interface contracts for the main agent

1. **Failure status taxonomy** — Implement a single enumerated load result covering at least: `OK`, `NOT_FOUND`, `IO_TRUNCATED`, `HP2_*` mirror, `TAG_HEADER`, `TAG_SCHEMA`, `RELOC`, `BSP_COLLISION`, `BSP_RENDER`, `BUDGET`, `UNSUPPORTED`. Map HP2 statuses 1:1 from `hp2.h:13–22`.

2. **No authority on failure** — On any non-`OK` after load begins: do not set `cache_file_globals.tags_loaded`, do not publish `global_tag_instances`, do not set `tag_instance->base_address` for BSP, do not register vertex/index buffers. Match `scenario_tags_load` / `scenario_structure_bsp_load` ordering.

3. **Pointer model fork** — Before converter work: choose materialized EE pointers vs offset accessors (`docs/hcu-tag-loader-contract.md:64–66`). Tests must target the chosen model only; mixing invalidates `tag_validate_tags`.

4. **Region ownership** — Document for each payload class (permanent tags, collision BSP, render BSP/geometry, bitmaps, sound, streaming scratch) exactly one owner region from `config/memory-budget.json`. Duplicate load into two regions = test failure (`docs/hcu-tag-loader-contract.md:67–71`).

5. **HP2 streaming** — When using `hp2_open_header`, require `stored_size` bytes read validation before `hp2_load_stored`; treat short read as `IO_TRUNCATED`, not `HP2_ERR_DECODE`.

6. **Arena pairing** — Parent world loader must `arena_reset` level arena on failed `world_load` / failed HCU map bind; record high-water across reload (`plans/5.hcu-remake.md:136`).

7. **Placeholder gate** — Do not mark M2 loader tests passing on generated `cache_file_*` / `ReadFile` stubs (`docs/hcu-ps2-platform-placeholder-audit.md:13`).

## Recommended tests / fixtures

### Host — HP2 (extend existing)

| Fixture | Assert |
|---------|--------|
| `engine/tests/test_hp2.c` + `test_hp2.py` | Keep CRC, truncation, `hp2_open_header` file_size mismatch, corrupt LZ4 |
| **New:** duplicate section tags in one pack | `hp2_open` OK but deterministic policy (reject at open or reject ambiguous `hp2_find`) |
| **New:** overlapping section ranges | Reject at open |
| **New:** `align` 64/128 with under-aligned `dst` | Reject or align alloc in loader |
| **New:** `stored_size` < actual file slice (streaming) | `hp2_load_stored` with short buffer |

### Host — M2 tag image (synthetic, no retail bytes in repo)

| Fixture | Assert |
|---------|--------|
| Minimal 2–3 tag synthetic map | Round-trip converter; `tag_validate_tags` passes on loaded buffer |
| Bad tag count / table OOB | Refuse; `tags_loaded` false |
| Reloc pointing outside image | Refuse |
| Cyclic block pointer graph | Refuse |
| Valid image, `raw_size` > region cap | Refuse before decode |
| Byte-stable reconvert | Identical output (`plans/5.hcu-remake.md:132`) |

### Host — HCU paths (reuse patterns)

| Fixture | Assert |
|---------|--------|
| `tools/map_validate.c` fuzz philosophy | Bounds on tag cache claims (reference for property tests) |
| `scenario_tags_load` with injected bad header | Returns `NONE`, file closed |
| BSP switch rollback | Load BSP A → switch to corrupt BSP B → A restored or menu (`scenario.c:1106–1134`) |

### Integration (post-placeholder)

| Fixture | Assert |
|---------|--------|
| Load bloodgulch (or designated M2 map) → unload → reload | Arena/`malloc_arena` high-water baseline |
| Missing map name | Precache begin false / damaged media path |
| Truncated HP2 on disc | No partial world; error logged |

### Negative controls (must not pass)

- Tag table only updated while leaving CE `base_address` as Xbox VA.
- Enlarged `HALO_PORT_TAG_CACHE_SIZE` without budget ledger approval.
- Successful `scenario_tags_load` with `tag_validate_tags` skipped.

## Dependencies on other investigators

| Investigator | Need |
|--------------|------|
| `m2_tag_image_format_investigator` | Versioned header layout, section tag name(s), checksum scope, reloc record format |
| `m2_arena_capacity_auditor` | Per-map peak charges against `current_bsp`, `resident_gameplay`, `streaming`; reload high-water protocol |
| `m2_map_conversion_auditor` | Which tag groups/fields are emitted vs stripped; BSP reference translation; unsupported group policy |
| M1 cache/file service owner | Real `cache_file_open`/`read` semantics; elimination of success-shaped stubs |

## Open questions

1. **Duplicate HP2 section tags** — Should M2 reject at `hp2_open` (strict) or define deterministic precedence? Retail converters should not emit duplicates (`hp2.py:185–186`).

2. **`hp2_section.align`** — Enforce at alloc time in parent loader only, or add to `hp2_load_stored`?

3. **Failed `world_load_section` arena policy (section-level resolved, 2026-10-20)** — `world_load_section` now records the arena mark before output allocation and rolls back the complete section transaction on stored-read failure, scratch exhaustion, and CRC/decode failure. Host tests verify those failures restore the mark and zero `raw_size`; success retains decoded output and releases scratch. This does not answer or implement whole-map rollback across tag validation, BSP load, and render-pack setup.

4. **Collision vs render BSP** — Single HP2 map pack may hold both `BSP0` (render) and CE collision extent; confirm whether collision stays in tag image tail (CE model) or separate section with updated `scenario_structure_bsp_reference` (`docs/hcu-tag-loader-contract.md:28–36`).

5. **Custom Edition path on PS2** — Out of scope for PS2 product? If unreachable, document call-graph proof; if reachable, same fail-closed table as CE branch in `scenario_tags_load` (`cache_files.c:1206–1231`).

6. **Error surfacing** — Deferred `error(_error_delayed)` vs silent refuse: M2 tests should key off return values and bounded log buffer, not UI (`docs/hcu-ps2-platform-placeholder-audit.md:20`).

## Handoff summary

### Implementation delta (2026-10-20)

The section-level rollback item above is implemented in `halo-ps2/engine/src/world/section.c` (split out of `world.c` so the HP2 consumer can be host-tested without PS2 renderer headers). `engine/tests/test_world_loader.c` and the engine test Makefile cover success, missing optional sections, read failure, scratch exhaustion, and payload CRC failure. This is only the parent HP2 section consumer; the report's L0–L6 transaction and the HCU cache/arena integration remain open.

- **Implemented today:** HP2 L1 bounds/CRC/LZ4 (`hp2.c`); Python parity; parent `world_load_section` fail-fast; CE `scenario_tags_load` / BSP verify / unload ordering; `tag_validate_tags` refuse-on-bad-pointer; render `bsp_open` layout checks.
- **Not implemented:** M2 tag image L2; PS2 real map I/O; partitioned regions for retail-sized tag data; reload high-water evidence.
- **Normative fail-closed rule:** Any load step that cannot prove bounds and ownership must behave like `scenario_tags_load` on damage — close/release, return failure, **no published tags or BSP** — with BSP switch rollback where CE already defines it.
- **Blocking contract:** Follow `docs/hcu-tag-loader-contract.md` pointer/relocation model before claiming converter/loader; HP2 alone is insufficient.

## Corroboration

### Agreements

- **m2_tag_image_format:** Pointer materialization + `tag_validate_tags` is the L2+ bar; stub validator on PS2 is known gap.
- **m1_platform_callsite:** Generated **ReadFile** / cache APIs must not return success on garbage — matches fail-closed table.
- **m1_startup_guest_path:** First live load attempt `levels\ui\ui` then `b30` — loader must refuse without image bytes.
- **m2_arena_capacity:** Partition failure modes (OOM, overlap) need explicit rollback like CE BSP switch path.
- **m3_collision_owner:** Published BSP must match CE `global_collision_bsp_get` before retiring parent collpack.

### Conflicts

- **C3:** Staged M1 I/O fixes before M2 image on guest — corroborated; loader design can proceed in parallel on host fixtures.

### Updated handoff

1. Layered tests L0–L6: add CTAG corrupt/trunc/reloc OOB cases when converter exists.
2. Replace PS2 `tag_validate_tags` stub with real linkage before M2 gate.
3. Any load step that publishes tags without bounds proof is a regression — mirror `scenario_tags_load` damage path.
