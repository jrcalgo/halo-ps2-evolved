# m0_memory_ledger_auditor

## Mission

Review the provisional memory-owner ledger for the standalone HCU PS2 `halo-local.elf`: ELF sections, fixed buffers in `ps2_memory.c`, arena ownership vs parent `halo-ps2`, alignment, and region totals against `config/memory-budget.json` v2. Flag logical budget assignments that are not backed by parent-arena routing, and distinguish contiguous linker `.bss` from a deployed v2 layout. Report-only; do not close M0–M3 gates or invent pool sizes.

## Inputs examined

| Input | Role |
|---|---|
| `docs/investigations/_prompt_contract.md` | Investigator rules and evidence baseline |
| `tools/hcu_ps2_memory_audit.py` | Map/`nm`/`readelf` ledger tool and region-candidate logic |
| `config/memory-budget.json` | v2 region capacities (32 MiB EE contract) |
| `config/hcu-ps2-memory-map.json` | Provisional owner → region map and `symbol_regions` for `ps2_memory.o` |
| `submodules/halo-ce-universal/port/ps2/src/ps2_memory.c` | Fixed backing arrays and bump `malloc_arena` |
| `submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h` | Declared byte caps for game state, tag, texture pages, sound |
| `docs/hcu-ps2-closure.md` | Published ELF/BSS tables and allocation-ownership gap |
| `plans/remake-cowork.md` | Handoff snapshots and ledger review notes |
| `docs/memory.md` | Parent world-viewer arena rules and double-counting policy |
| `submodules/halo-ps2/engine/src/main.c` | Parent boot `malloc` + `arena_init` (contrast entry path) |
| `build/hcu-ps2-closure/all/halo-local.elf` | Linked image (SHA-256 below) |
| `build/hcu-ps2-closure/all/halo-local.map` | Linker `.bss` layout |
| `build/hcu-ps2-closure/all/memory-symbols.json` | Regenerated audit output |
| `tests/test_hcu_ps2_closure.py` | Unit tests for `apply_region_candidates` and closure doc reconciliation |

**Evidence baseline (contract):** parent HEAD `a2575e957feefbdff27febedabf60590401e6bcc`, HCU HEAD `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`.

**Built ELF (workspace):** SHA-256 `e45b4719d35450a77f2a541a7ed8abb877e5fbef495fc918539f8da91de597a2` (matches contract and `docs/hcu-ps2-closure.md`).

## Findings

### 1. Tool behavior and what the ledger proves

`tools/hcu_ps2_memory_audit.py` states explicitly that region totals are **provisional logical assignments**, not proof of physical linker/loader or parent-arena placement (`tools/hcu_ps2_memory_audit.py:267`). Authoritative BSS byte totals come from **non-overlapping link-map input-section ranges** plus linker `*fill*`; symbol sizes from `nm -S` may alias and are never summed into section totals (`tools/hcu_ps2_memory_audit.py:3-7`, `110-120`).

For `ps2_memory.o`, the tool splits the single `.bss` input section by **symbol address order**, applying `symbol_regions` from `config/hcu-ps2-memory-map.json` (`tools/hcu_ps2_memory_audit.py:156-161`, `184-221`). Gaps between symbols inherit the previous symbol’s region (`tools/hcu_ps2_memory_audit.py:205-215`). Linker fill uses `fill_policy: preceding-owner-region` (`config/hcu-ps2-memory-map.json:38`).

File-backed `SHF_ALLOC` bytes (excluding `NOBITS`) are added once to `elf_static` (`tools/hcu_ps2_memory_audit.py:252-256`, `config/hcu-ps2-memory-map.json:10`).

### 2. ELF sections (measured, this build)

From `build/hcu-ps2-closure/all/memory-symbols.json` (`file_backed_allocated_bytes`, `file_backed_sections`):

| Section | Bytes |
|---|---:|
| `.text` | 1,527,792 |
| `.data` | 98,980 |
| `.rodata` | 265,584 |
| `.ctors` / `.dtors` / `.sdata` / `.MIPS.abiflags` | 56 |
| **File-backed total → `elf_static`** | **1,892,412** |

Link map output section: `.bss` at `0x002ce200`, size `0x7da5b0` (**8,234,416** bytes) (`build/hcu-ps2-closure/all/halo-local.map:24210`).

**Total `SHF_ALLOC` accounted by the audit:** 1,892,412 + 8,234,416 = **10,126,828** bytes (matches `docs/hcu-ps2-closure.md`).

Named BSS symbols: **657**, unmapped: **0** (`memory-symbols.json`).

### 3. Fixed buffers in `ps2_memory.c` (source vs link map)

Source declarations (`submodules/halo-ce-universal/port/ps2/src/ps2_memory.c:15-26`):

| Symbol | Declared size (from macros) | Bytes | `aligned(16)` |
|---|---|---:|:---:|
| `game_state` | `HALO_PORT_GAME_STATE_SIZE` = `0x305000` + `0x40000` | 3,428,352 | yes |
| `tag_cache` | `HALO_PORT_TAG_CACHE_SIZE` = `0x200000` | 2,097,152 | yes |
| `texture_cache` | `0x20` × `0x4000` | 524,288 | yes |
| `sound_cache` | `0x80000` | 524,288 | yes |
| `malloc_arena` | `256 * 1024` | 262,144 | yes |
| `malloc_used` + four `physical_*` pointers | — | 24 (nm) + 8-byte gap before `malloc_arena` | — |

Macro definitions: `submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h:19-27`.

Link map: one `.bss` input section for `ps2_memory.o`, **`0x685020` (6,836,256)** bytes (`halo-local.map:24214`). That equals the sum of the five arrays plus pointer/cursor metadata and **8 bytes** of intra-object padding between `malloc_used` and `malloc_arena` (symbol addresses in `memory-symbols.json`: `malloc_used` at `2941856`, `malloc_arena` at `2941872`).

**Linker order within `ps2_memory.o` differs from source declaration order:** metadata and `malloc_arena` are placed at the **low** end of the object’s BSS; `game_state` is at the **high** end (`game_state` at VMA `6349744`, size `3428352`). All remain one contiguous object-file block inside the global `.bss`.

`physical_memory_allocate` only assigns pointers to the static arrays (`ps2_memory.c:33-38`); it does **not** call the parent arena or relocate storage.

### 4. BSS owner rollup (map input sections)

From `memory-symbols.json` → `bss_bytes_by_input_object` (sums to **8,234,416**):

| Owner / group | Bytes | Provisional v2 region (audit) |
|---|---:|---|
| `ps2_memory.o` | 6,836,256 | Split: see §5 |
| `rooted.o` | 1,131,699 | `resident_gameplay` |
| `ps2_platform.o` | 232,789 | `resident_gameplay` |
| EE CRT / libc / PS2SDK / glue (many archive members) | 32,554 | `resident_gameplay` via `system_runtime_owner_contains` |
| `ps2_edge.o` | 580 | `resident_gameplay` |
| `crtbegin.o` + LTO `.ltrans` artifact | 400 | `resident_gameplay` |
| `linker-fill` | 538 | Preceding owner region |

Notable symbols (sizes from `memory-symbols.json`, not summed into section totals):

- `ai_debug`: **547,628** bytes, `rooted.o`, `resident_gameplay`
- `render`: **201,364** bytes, `ps2_platform.o` `COMMON`, `resident_gameplay`

### 5. Provisional logical region totals vs `memory-budget.json` v2

Audit output `candidate_allocated_bytes_by_region` vs v2 `regions[].bytes`:

| Region | Used (audit) | Capacity (v2) | Spare | Notes |
|---|---:|---:|---:|---|
| `elf_static` | 1,892,412 | 2,097,152 | 204,740 | File-backed only; correct per tool policy |
| `resident_gameplay` | 5,088,688 | 6,815,744 | 1,727,056 | Includes CE globals, `malloc_arena`, CRT/SDK, `render`, `ai_debug`, and **`game_state` backing** |
| `current_bsp` | 2,097,152 | 6,291,456 | 4,194,304 | Only the **`tag_cache` array** today |
| `texture_cache` | 524,288 | 4,194,304 | 3,670,016 | Only the **`texture_cache` staging array** |
| `audio` | 524,288 | 524,288 | **0** | **`sound_cache` exactly fills** staging capacity |
| `dynamic_simulation` | *(not charged)* | 2,621,440 | — | See §6 |
| `system_kernel`, `dma_commands`, `streaming`, `checkpoint`, `frame_scratch`, `uncommitted_reserve` | *(not in this ELF ledger)* | per v2 | — | Parent / runtime stores; not part of standalone HCU image accounting |

`candidate_regions_over_capacity`: **{}** (no region exceeds its v2 capacity for this image).

**Important:** Fitting inside v2 **region capacities** for this standalone ELF is **not** the same as fitting the **32 MiB committed EE map** with parent renderer, BSP packs, stacks/kernel reservation, DMA chains, and runtime peaks—all absent from this ledger (`docs/hcu-ps2-closure.md:106`, `docs/memory.md`).

### 6. Logical assignment without parent-arena routing (critical)

| Issue | Evidence |
|---|---|
| HCU uses **private static `.bss`**, not parent boot arena | `ps2_memory.c:4-9`, `ps2_memory.c:21-25`; contrast `submodules/halo-ps2/engine/src/main.c:137-140` (`malloc` + `arena_init`) |
| Budget region names in comments are **intent only** | `ps2_memory.c:6-9` (“not yet caller-owned parent arenas”) |
| Audit maps arrays to `current_bsp` / `texture_cache` / `audio` **by name**, while bytes still live in **one contiguous ELF `.bss`** | `config/hcu-ps2-memory-map.json:3-6`; `halo-local.map:24210`; `docs/hcu-ps2-closure.md:104` |
| **`physical_*` pointers** charged to `resident_gameplay` via `symbol_regions` | `config/hcu-ps2-memory-map.json:33-36`; symbols at `memory-symbols.json` ~5752–5793 |
| **`malloc_arena`** charged to `resident_gameplay` | `config/hcu-ps2-memory-map.json:31-32`; `hcu-ps2-memory-map.json:7-8` notes bootstrap-only / unproven high-water |
| **CE object pool** (`game_state_memory_pool_new` → `game_state_malloc`) is **nested inside `game_state`**, not routed to `dynamic_simulation` | `submodules/halo-ce-universal/source/saved games/game_state.c:943-950`; `hcu-ps2-memory-map.json:6-7`; declared payload cap `HALO_PORT_OBJECT_MEMORY_POOL_SIZE` `0x100000` in `halo_ps2_limits.h:35` (metadata/alignment/high-water **not** measured here) |
| Charging `dynamic_simulation` for the object pool **without** allocator routing would **double-count** | Same nesting path; audit correctly omits `dynamic_simulation` from totals |
| User-process CRT/libc/SDK globals assigned to `resident_gameplay`, not `system_kernel` | `config/hcu-ps2-memory-map.json:8`, `17-24`; consistent with `docs/hcu-ps2-closure.md:101` |

**Conclusion:** The ledger is arithmetically closed for the standalone ELF and useful for M0 **inventory**, but it **must not** be read as parent-arena placement, loader segmentation, or M1 memory-gate acceptance (`docs/hcu-ps2-closure.md:86-87`, `114-128`).

### 7. Contiguous BSS vs deployed v2 layout

- The image has **one** `.bss` output section; `ps2_memory.o` contributes a **single** 6,836,256-byte input range (`memory-symbols.json` `bss_input_sections` entry at VMA `2941840`–`9778096`).
- v2 assumes **distinct** regions (`config/memory-budget.json:8-21`); deploying that layout requires **moving or aliasing** backing storage (linker script, loader, or arena providers)—not relabeling in JSON (`docs/memory.md:43`, `docs/hcu-ps2-closure.md:104`).
- Relabeling BSS bytes into `streaming` / `current_bsp` while they remain in `.bss` would violate the project’s **no double-count** rule (`docs/memory.md:3`, `43`).

### 8. Alignment

- All five backing arrays use `__attribute__((aligned(16)))` (`ps2_memory.c:21-25`).
- Bump allocator rounds requests to 16 bytes (`ps2_memory.c:75-76`).
- ELF section alignment for `.bss` is visible in the map (`0x002ce200` base); linker fill **538** bytes is accounted separately (`bss_bytes_by_input_object` → `linker-fill`).

### 9. Grouped-owner semantics (M0 review still open)

| Group | Concern |
|---|---|
| `ps2_platform.o` → all `resident_gameplay` | **201,364**-byte `render` is simulation-adjacent; owner-by-object-file hides render vs platform stub semantics (`docs/hcu-ps2-closure.md:99-100`, `130`) |
| `rooted.o` → all `resident_gameplay` | **547,628**-byte `ai_debug` is campaign AI/path storage; cannot be accepted as “generic gameplay” without explicit retention policy |
| `system_runtime` rule | Correctly buckets libc/SDK; **not** kernel/stacks (`config/hcu-ps2-memory-map.json:8`) |
| Duplicate display row | Earlier duplicate `ps2_platform.o` row in closure doc was removed; totals always counted that owner once (`plans/remake-cowork.md:126`) |

### 10. Capacity vs content (do not confuse with ledger arithmetic)

- HCU tag staging is **2 MiB** (`halo_ps2_limits.h:24`); retail tag-index aggregates show **multi‑MiB** raw tag regions per map (`docs/hcu-ps2-closure.md:134`). That is an **M2 content/partition** problem, not an error in the BSS sum.
- `current_bsp` v2 capacity (**6,291,456**) is largely **unused** in the logical ledger because only the 2 MiB `tag_cache` array is present—**not** evidence that map data fits.

### 11. Historical doc drift (non-blocking)

`plans/remake-cowork.md` initial handoff cites `.bss` **8,234,288** bytes and **653** symbols; this build has **8,234,416** bytes and **657** symbols (`memory-symbols.json`). Prefer the regenerated JSON and SHA-256 above for Round 1 evidence.

## Interface contracts for the main agent

1. **Treat `memory-symbols.json` as the machine-readable ledger** for this ELF hash; regenerate with `python3 tools/hcu_ps2_memory_audit.py` after every link (`docs/hcu-ps2-closure.md:88`).
2. **Do not charge `dynamic_simulation`** for the CE object pool until `game_state_malloc` is routed out of the `game_state` backing store or the ledger explicitly subtracts nested pool bytes from `resident_gameplay` (`config/hcu-ps2-memory-map.json:6-7`).
3. **Parent integration contract:** replace `ps2_memory.c` static arrays with storage obtained from the caller’s arena (parent `arena_init` path or agreed glue), then re-run the audit—expect `ps2_memory.o` BSS to shrink or disappear from the ELF in favor of NOBITS/external regions.
4. **`symbol_regions` updates** require simultaneous review of gap/fill attribution in `apply_region_candidates` (`tools/hcu_ps2_memory_audit.py:184-221`).
5. **M0 gate language:** “no overages and full symbol mapping” ≠ “accepted ownership”; keep semantic review explicit (`docs/hcu-ps2-closure.md:106-107`).

## Recommended tests / fixtures

| Test | Purpose |
|---|---|
| `tests/test_hcu_ps2_closure.py::test_candidate_regions_split_memory_provider_and_reconcile_bytes` | Guards split accounting for `ps2_memory.o` |
| `tests/test_hcu_ps2_closure.py::test_documented_bss_owner_rows_reconcile_without_duplicate_platform_group` | Closure doc table sums to **8,234,416** |
| Re-run `hcu_ps2_memory_audit.py` after link in CI | Pin `candidate_allocated_bytes_by_region` and `bss_bytes_by_input_object` for ELF hash `e45b4719…` |
| Future: fixture asserting `dynamic_simulation` stays zero until pool routing lands | Prevents accidental double-count |

## Dependencies on other investigators

- **M1 / platform:** Guest boot, placeholder audit, and whether `malloc_arena` high-water belongs in `streaming`, `frame_scratch`, or stays bootstrap (`docs/hcu-ps2-closure.md:125-126`).
- **M2 / loader:** Tag/BSP partition vs 2 MiB cap; materialized pointers (`docs/hcu-tag-loader-contract.md` per `plans/remake-cowork.md:120-122`).
- **Parent renderer / DMA:** `dma_commands`, GS VRAM, and world arena measurements in `docs/memory.md` (not duplicated in HCU standalone ledger).

## Open questions

1. Final owner for **256 KiB** `malloc_arena` under v2 (`streaming` vs `resident_gameplay` vs `frame_scratch`) pending call-site high-water and map-reload tests (`config/hcu-ps2-memory-map.json:7-8`, `docs/hcu-ps2-closure.md:96`).
2. Whether **`ai_debug`** remains in retail-equivalent builds or moves behind a debug gate without breaking campaign AI (`ai_debug` 547,628 bytes in `memory-symbols.json`).
3. **`render` / visibility globals** ownership between HCU simulation and parent GS path (`docs/hcu-ps2-closure.md:130`).
4. Glue decision: single EE image with parent `main` vs HCU `ps2_main` and who owns the 32 MiB carve (`docs/hcu-ps2-closure.md:128`).
5. When/if BSS is **physically split**, how linker fill and `physical_*` metadata relocate without breaking DMA alignment assertions (`port/ps2/src/ps2_abi.c` compile-time cache size checks).

## Handoff summary

- **Arithmetic:** For ELF `e45b4719…`, the audit reconciles **8,234,416** bytes of `.bss` (657 symbols, 0 unmapped), **1,892,412** file-backed bytes, and **10,126,828** total allocated bytes across **five** v2 regions with **no** `candidate_regions_over_capacity` entries.
- **`ps2_memory.o`:** **6,836,256** bytes in one `.bss` input section; five fixed arrays match `halo_ps2_limits.h`; **16-byte** alignment; **`audio` staging has zero spare** at v2 capacity.
- **Routing:** All major caches are **static ELF `.bss`**, not parent arenas; logical `current_bsp` / `texture_cache` / `audio` labels are **naming-only** until M1/M2 routing lands.
- **Double-count guard:** Object pool lives under **`game_state` / `resident_gameplay`** today; do not add **`dynamic_simulation`** without allocator changes.
- **M0 recommendation:** Keep the memory-owner **acceptance gate open** pending grouped-owner semantics (`render`, `ai_debug`, platform COMMON) and parent/runtime inclusion boundaries; the ledger is fit for inventory and integration planning, not deployed layout sign-off.

## Corroboration

### Agreements

- **m0_link_closure:** Same ELF hash and **10,126,828** B total allocated narrative; **345**-unit closure does not change BSS reconciliation arithmetic.
- **m2_arena_capacity:** Retail tag/BSP totals exceed v2 bootstrap caps — ledger’s **2 MiB** tag label is a fail-closed bound, not retail capacity (**C1** aligned).
- **m2_tag_format / m2_map_conversion:** Separate CE tag image and partitions are required; cannot fold retail structs into `resident_gameplay` without measured overlap.
- **m1_dma_layout_auditor:** `frame_scratch` **393,216** B budget and 16-byte alignment policy fit `frame_scratch` region; snapshot not yet charged.
- **m0_runtime_ownership:** `current_bsp` / texture / audio region names are logical until M2 loader publishes bytes.

### Conflicts

- **C1:** Single contiguous tag cache vs CTAG partitions — corroborated **open**; this report inventories caps, **m2_arena** proves violation on retail maps.
- **C5:** `ps2_memory.o` monolith vs parent `arena_init` — corroborated **open**; main agent must shrink/re-home BSS before DMA snapshot design is final.

### Updated handoff

1. Do not add **`dynamic_simulation`** until `game_state_malloc` routing is explicit (**m3_object_lifecycle** pool under `game_state`).
2. M2 planning: use `memory-symbols.json` + **m2_arena** overlap table; never raise **2 MiB** tag cap as a format fix alone.
3. M0 exit: semantic sign-off on **`render`**, **`ai_debug`**, and **`audio`** zero-spare staging before closing memory gate.
