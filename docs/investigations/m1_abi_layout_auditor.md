# m1_abi_layout_auditor

## Mission

Independently verify that the HCU PlayStation 2 port’s compile-time layout probes match an ILP32, MSVC-shaped CE datum model under both the reproducible host check (`tools/hcu_ps2_abi_host.py`) and the intended R5900 target compile of `submodules/halo-ce-universal/port/ps2/src/ps2_abi.c`. Catalog nested-field and DMA-related assertion gaps relative to CE’s scattered Xbox layout checks and to M1 expectations in project docs. Cross-reference the open soft-double helper audit documented in `docs/hcu-ps2-closure.md`. Report-only; no implementation changes.

## Inputs examined

| Path | Role |
|---|---|
| `docs/investigations/_prompt_contract.md` | Report template and evidence baseline (parent `a2575e95…`, HCU `c406a414…`) |
| `tools/hcu_ps2_abi_host.py` | Host ILP32 `-fsyntax-only` driver for `ps2_abi.c` |
| `submodules/halo-ce-universal/port/ps2/src/ps2_abi.c` | Central PS2 ABI/layout assertions |
| `submodules/halo-ce-universal/port/ps2/include/halo_ps2_prefix.h` | Forced `-D__mips__` / ILP32 pointer/`long`/`wchar_t` shims |
| `submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h` | Tag/texture/sound cap constants |
| `submodules/halo-ce-universal/port/ps2/src/ps2_memory.c` | 16-byte-aligned backing stores; bump malloc rounds to 16 |
| `submodules/halo-ce-universal/source/cache/physical_memory_map.h` | `TAG_CACHE_SIZE` → `HALO_PORT_TAG_CACHE_SIZE` when `HALO_PS2` |
| `submodules/halo-ce-universal/source/tag_files/tag_groups.h` | `tag_block` / `tag_reference` shapes |
| `submodules/halo-ce-universal/source/memory/data.h` | `datum_header`, `data_iterator` |
| `submodules/halo-ce-universal/source/objects/objects.h`, `scenery.h`, `damage.c` | `object_datum` / `_object_datum`; retail offset asserts |
| `submodules/halo-ce-universal/source/items/items.h`, `weapons.h`, `projectiles.h` | Item/weapon/projectile datum nesting |
| `submodules/halo-ce-universal/source/render/render.h` | PS2-only bounded `environment_surface_flags`; `0x31294` globals |
| `submodules/halo-ce-universal/source/math/real_math.h`, `source/cseries/cseries.h` | `real` math and `fast_ftol` double conversion |
| `docs/hcu-ps2-closure.md` | Closure status, ABI summary, **R5900 double-precision helper audit** |
| `plans/5.hcu-remake.md` | M1 ABI/DMA/double expectations |

**Execution this session:** `python3 tools/hcu_ps2_abi_host.py` exited 0 with `host ILP32 PS2 ABI assertions passed (i386 layout; no execution)`. R5900 `mips64r5900el-ps2-elf-gcc` was **not** present in this environment (`build_toolchain.environment()` prefix had no EE compiler); R5900 pass is taken from `docs/hcu-ps2-closure.md:64` until a local rebuild confirms.

## Findings

### 1. Host ILP32 probe (`tools/hcu_ps2_abi_host.py`)

The host check is a **syntax-only** compile of the same translation unit the PS2 link uses (`tools/hcu_ps2_link.py` lists `port/ps2/src/ps2_abi.c`). It does not execute `ps2_abi_check()` (empty body at `ps2_abi.c:63-65`).

**Compiler flags and includes (material to layout):**

- Host: `cc -m32 -fshort-wchar -malign-double -fms-extensions -fcommon` (`hcu_ps2_abi_host.py:40-41`).
- Target personality on host: `-D__mips__ -D__MIPSEL__ -D_EE -D__STRICT_ANSI__` plus forced `halo_ps2_prefix.h` (`hcu_ps2_abi_host.py:41-47`, `halo_ps2_prefix.h:12-70`).
- Includes: HCU `port/ps2/include`, game `source/**`, `port/include`, `port/include/xdk`, and **toolchain** freestanding headers via `-nostdinc` + `-isystem` host internal + PS2 SDK sysroot (`hcu_ps2_abi_host.py:27-43`).

**Interpretation:** The probe validates that `sizeof` / `offsetof` expressions in `ps2_abi.c` are consistent with **i386 ILP32 + MSVC extension alignment** while parsing headers as the PS2 build does. It is a strong regression guard for struct packing drift; it is **not** a proof that i386 and R5900 disagree or agree on every edge case (bitfields, pragma packs, `-Os` reordering is irrelevant here). Equivalence of host vs R5900 for these checks is an **assumption** backed by closure doc, not re-measured here.

### 2. R5900 / ILP32 primitive contract (`ps2_abi.c`, `halo_ps2_prefix.h`)

| Assertion | Expected | Location |
|---|---|---|
| `void *` | 4 | `ps2_abi.c:29`, `halo_ps2_prefix.h:68` |
| `long` | 4 | `ps2_abi.c:30`, `halo_ps2_prefix.h:69` |
| `wchar_t` | 2 (`-fshort-wchar`) | `ps2_abi.c:31`, `halo_ps2_prefix.h:70` |
| `float` / `real` | 4 | `ps2_abi.c:32-33` |
| `datum_header` | 2 | `ps2_abi.c:34` |
| `tag_block` | 12 | `ps2_abi.c:35` |
| `tag_reference` | 16 | `ps2_abi.c:36` |

`tag_block` layout matches CE: `long count`, `void *address`, `tag_block_definition *definition` (`tag_groups.h:87-92`). `tag_reference` is four 32-bit fields (`tag_groups.h:94-100`).

**Cache cap coupling (PS2 bootstrap, not Xbox map size):**

| Macro chain | Bytes | `ps2_abi.c` |
|---|---|---|
| `HALO_PORT_TAG_CACHE_SIZE` | `0x200000` | `halo_ps2_limits.h:24`, assert `ps2_abi.c:37` |
| Texture pages × 16 KiB | `0x20 × 0x4000` | `halo_ps2_limits.h:25-26`, `ps2_abi.c:38-39` |
| Sound staging | `0x80000` | `halo_ps2_limits.h:27`, `ps2_abi.c:40` |
| `TAG_CACHE_SIZE == HALO_PORT_TAG_CACHE_SIZE` | — | `physical_memory_map.h:15-18`, `ps2_abi.c:37` |

These asserts encode **intended PS2 buffer sizes**, not retail Xbox `TAG_CACHE_SIZE` (`0x1600000` on non-PS2 builds, `physical_memory_map.h:17-18`).

### 3. Key CE datum layouts asserted in `ps2_abi.c`

#### 3.1 `object_datum` (base object record)

| Check | Value | CE corroboration |
|---|---|---|
| `sizeof(object_datum)` | `0x1A4` (420) | `scenery.h:33`, `object_types.c:238` (`'obje'` element size) |
| Nested `_object_datum` | **not** sized directly in `ps2_abi.c` | Implied `0x1A0` bytes after leading `definition_index` (420 − 4) |

`object_datum` is `long definition_index` + `struct _object_datum object` (`objects.h:318-322`). Pool headers use separate `object_header_datum` (`objects.h:218-226`); **not** covered by `ps2_abi.c`.

#### 3.2 `weapon_datum` chain

Nested shape (`weapons.h:161-219`):

```
weapon_datum
  long definition_index
  struct _object_datum object      // 0x1A0
  struct _item_datum item          // 0x38 (derived: 0x1DC − 0x1A4)
  struct _weapon_datum weapon
```

| Check | Offset / size | `ps2_abi.c` |
|---|---|---|
| `weapon_trigger` | 36 (`0x24`) | `:42` |
| `weapon_magazine` | 12 (`0x0C`) | `:43` |
| `weapon_datum` total | 636 (`0x27C`) | `:44` |
| `weapon` payload start | `0x1DC` | `:45` |
| `weapon.triggers` | `0x210` | `:46` |
| `weapon.magazines` | `0x258` | `:47` |
| `weapon.game_time_last_fired` | `0x278` | `:48-49` |

Internal `_weapon_datum` contains two `weapon_trigger` and two `weapon_magazine` (`weapons.h:206-207`). Offset arithmetic is internally consistent: `0x258 − 0x210 = 0x48` (two 36-byte triggers), `0x278 − 0x258 = 0x20` (two 12-byte magazines plus `animation_state` and `overheated_effect_index` per `weapons.h:208-210`).

**Gap:** `weapons.h` has **no** compile-time `sizeof`/`offsetof` asserts (unlike `projectiles.h` and `scenery.h`). PS2 relies entirely on `ps2_abi.c` for weapon layout regression.

#### 3.3 `projectile_datum` chain

Nested shape (`projectiles.h:26-54`):

| Check | Offset / size | `ps2_abi.c` | CE header asserts |
|---|---|---|---|
| Total size | 552 (`0x228`) | `:50` | — |
| `projectile.target_object_index` | `0x1E8` | `:51` | `projectiles.h:56-59` |
| `projectile.detonation_timer` | `0x1F0` | `:52` | `projectiles.h:60-63` |
| `projectile.arming_time` | `0x1F8` | **missing** | `projectiles.h:64-67` |

Shared prefix with weapons: `projectile` sub-struct base at `0x1DC` (same as `weapon` payload), consistent with identical `definition_index` + `_object_datum` + `_item_datum` prefix.

#### 3.4 `render_globals` (PS2-only size)

| Check | Value | Notes |
|---|---|---|
| `sizeof(render_globals)` | `0x31294` | `ps2_abi.c:53` |

On `HALO_PS2`, `environment_surface_flags` is a **bit-packed** `unsigned long[]` sized with `BIT_VECTOR_SIZE_IN_BYTES(MAXIMUM_SURFACES_PER_STRUCTURE)` (`render.h:101-105`, `101-117`), not one `unsigned long` per surface. Additional compile checks in `render.h:111-117` guard bitmap width. Retail/non-PS2 builds keep the larger mistaken array (`render.h:103-105`); the `0x31294` assert applies only when PS2 headers are active (as in `ps2_abi.c` includes).

### 4. DMA-related layout evidence and gaps

**What exists today**

| Mechanism | Evidence |
|---|---|
| Synthetic 16-byte DMA quantum | `struct ps2_dma_record` + `sizeof`/`__alignof__` asserts (`ps2_abi.c:55-61`) |
| Major EE backing buffers 16-byte aligned | `game_state`, `tag_cache`, `texture_cache`, `sound_cache`, `malloc_arena` (`ps2_memory.c:21-25`) |
| Bump allocator 16-byte rounding | `__wrap_malloc` (`ps2_memory.c:75-76`) |
| M1 plan statement | DMA moves 16-byte quadwords (`plans/5.hcu-remake.md:81`, `115`) |

**Gaps (no compile-time qualification in `ps2_abi.c` or port-wide inventory)**

1. **No CE gameplay struct is asserted `alignof(...) == 16` or DMA-safe size multiple**, except the synthetic `ps2_dma_record`. Real matrices (`real_matrix4x3` is 48 bytes at 4-byte alignment typical for `real` arrays, `real_math.h:477-492`), object pools, tag cache views, and VU-bound geometry are unchecked.
2. **No link between datum pool allocations and 16-byte base alignment** beyond static array bases in `ps2_memory.c`. `game_state_malloc` consumers (objects, actors, effects, etc.) are not probed.
3. **`object_header_block_reference` indirect blocks** (`objects.h:249-253`, `node_matrices` / `node_orientations` in `_object_datum`) — offsets into pool memory are runtime; no PS2 assert that allocated blocks are 16-byte aligned.
4. **Texture/tag cache contents** — caps are asserted; **layout of bytes inside cache files** is a loader/conversion problem (M2), not ABI TU.
5. **Parent renderer DMA chains** (`halo-ps2` `chain.c` / `upload.c`, per `docs/source-audit.md`) — outside HCU `ps2_abi.c`; coordination with snapshot records is an M3 seam, not covered here.

**Suggested owner for DMA struct inventory:** `m1_dma_layout_auditor` (separate report per `docs/investigations/INDEX.md`); this report only flags the split.

### 5. Nested-field assertion coverage map

CE embeds hundreds of translation-unit-local `typedef char ..._assert[...]` checks (example cluster in `damage.c:305-342` for combat-critical `object_datum` / `unit_datum` offsets). `ps2_abi.c` centralizes a **small** cross-build subset.

| Record / topic | In `ps2_abi.c` | Elsewhere in CE source | PS2 gap severity |
|---|---|---|---|
| Primitives + tags | Yes | `data.h:50-51` (`data_iterator` 0x10) | Low for primitives; `data_iterator` not in `ps2_abi.c` |
| `object_datum` size | Yes | `scenery.h:33` | Medium: no nested `_object_datum` field offsets in PS2 TU |
| `object_datum` combat offsets | No | `damage.c:305-342` (+ more in same file) | Medium–high for damage/destroy paths |
| `item_datum` | No | — | Low unless item-specific code is ported early |
| `weapon_datum` | Size + 4 offsets | No weapon header asserts | Medium: triggers/magazines internal fields not pinned |
| `projectile_datum` | Size + 2 offsets | + `arming_time` in header | Low–medium: one known missing offset in PS2 TU |
| `unit_datum` / `vehicle_datum` / `player_datum` | No | `vehicle_datum.h:65-68`, `players.h:178`, `damage.c` unit offsets | High for movement/combat M3 |
| `actor_datum` / AI records | No | `actors.c`, `ai_debug.h` (closure cites `path_storage`) | High for AI budget paths |
| Cache file structs | No | `cache_files.c:224-232` | M2 loader |
| `render_globals` | PS2 size only | `render.h:111-117` bitmap guards | Medium for visibility/render seam |
| Xbox MSVC parity | **Not tested** | N/A | **Unknown** — closure explicitly open (`hcu-ps2-closure.md:64`) |

**MSVC / Xbox compiler parity:** All numeric expectations in `ps2_abi.c` are **decompilation-derived CE source constants**, not a second compiler re-run against `cachebeta.exe` PDB in this repo. Host i386 and (per closure) R5900 GCC must match each other; **equivalence to original Xbox MSVC** remains unverified.

### 6. Soft-double (`double`) vs M1 “single precision” rule — closure cross-reference

`docs/hcu-ps2-closure.md` documents an **open** R5900 double-precision helper audit (`hcu-ps2-closure.md:66-70`):

| Metric | Value (closure doc) |
|---|---|
| Relocation entries to soft-double helpers | 2,099 across 238 retained text sections |
| Dominant symbols | 1,530 `__extendsfdf2`, 466 `__truncdfsf2`; also `__muldf3`, `__divdf3`, compares |
| Hot sections cited | `biped_update_physics`, `collision_test_vector`, `physics_update`, `actor_move_update`, `object_new`, `projectile_update` |
| Stated M1 status | **“no double” assertion is not met yet**; do not mechanically replace without parity fixtures and EE measurement |

Source-level drivers (independent of relocation counts):

- `real` remains 32-bit (`ps2_abi.c:33`), but `arctangent` calls `atan2(y, x)` on `real` (`real_math.h:940-945`), and `square_root` / `power` use `sqrt` / `pow` (`real_math.h:992`, `1006`) — libm paths that compile to double helpers on soft-float EE.
- `fast_ftol` explicitly casts through `double` for `__builtin_rint` (`cseries.h:335-343`).

**Layout interaction:** Double helpers do **not** change struct sizes in `ps2_abi.c`, but they violate the **intended EE FPU/DMA-era performance and determinism gate** in `plans/5.hcu-remake.md:115` until audited replacements or documented exceptions exist. Closure recommends hot-call-site inventory + fixtures before M1 performance acceptance (`hcu-ps2-closure.md:68-70`).

### 7. Consistency checks performed

- Host ABI script: **pass** (this session).
- Manual offset consistency: weapon trigger/magazine spacing and shared `0x1DC` item/weapon/projectile prefix **consistent** with headers listed above.
- `projectile.arming_time` assert present in `projectiles.h:64-67` but **absent** from `ps2_abi.c` — only nested-field drift found between CE header and PS2 central TU.

## Interface contracts for the main agent

1. **Treat `ps2_abi.c` + `hcu_ps2_abi_host.py` as the canonical cross-compiler layout gate** for the listed primitives, tag shapes, object/weapon/projectile sizes, PS2 `render_globals`, cache macros, and synthetic DMA record — not as full CE datum coverage.
2. **Do not close M1 ABI on host pass alone**; require R5900 compile of the same TU in CI/link (`hcu-ps2-closure.md:64`) and document any host/target divergence if introduced.
3. **Weapon/projectile offsets** listed in closure (`hcu-ps2-closure.md:64`) match `ps2_abi.c:42-52`; extend PS2 TU with `projectile.arming_time` (`0x1F8`) if parity with `projectiles.h` is desired.
4. **Double-precision policy** is tracked under closure § “R5900 double-precision helper audit”; ABI layout work does not satisfy that gate (`hcu-ps2-closure.md:66-70`).
5. **DMA-visible CE records** need a separate inventory (`m1_dma_layout_auditor`); current evidence is buffer alignment + 16-byte probe only.

## Recommended tests / fixtures

| Test | Purpose |
|---|---|
| `python3 tools/hcu_ps2_abi_host.py` | Fast host ILP32 regression (already in closure workflow) |
| R5900 `-fsyntax-only` or link of `ps2_abi.o` in `hcu_ps2_closure.py` / link pipeline | Prove target matches host for `sizeof`/`offsetof` set |
| Generated offsetof table test (future) | Dump `offsetof` for `damage.c` combat set + `unit_datum`/`vehicle_datum` into a golden JSON; run on host **and** R5900 |
| Add `projectile.arming_time` to golden set | Close known PS2/header gap |
| Soft-double fixture suite per closure | Per-call-site `float` replacements with recorded rounding for `fast_ftol`, `arctangent`, `square_root`, `power` hot paths |
| PCSX2/EE hardware 30 Hz tick profile | After double work; closure excludes PCSX2 as EE evidence (`hcu-ps2-closure.md:70`) |

## Dependencies on other investigators

| Investigator | Dependency |
|---|---|
| `m1_dma_layout_auditor` | Enumerate gameplay/render structs requiring 16-byte alignment or quadword multiples beyond `ps2_dma_record` |
| `m1_platform_callsite_auditor` | Placeholder calls that touch `render_globals` / time — layout vs behavior |
| `m2_tag_image_format_investigator` / `m2_loader_failure_auditor` | Tag/cache **contents**; ABI only caps sizes |
| `m3_collision_owner_auditor` / `m3_object_lifecycle_auditor` | Need `unit_datum`/`object_datum` offset asserts from `damage.c` class for parity tests |
| `m0_memory_ledger_auditor` | `game_state` backing vs datum pools — orthogonal to struct packing but affects where aligned buffers must land |

## Open questions

1. Does R5900 GCC 15.2.0 with the PS2 manifest flags ever disagree with i386 on any **currently asserted** type (especially bitfields in `_object_datum` or `word`/`byte` mixes)? Not re-run here.
2. What is the authoritative Xbox MSVC `sizeof`/`offsetof` table for `weapon_datum` and `projectile_datum` — PDB extract, or are CE header constants sufficient for M1?
3. Should PS2 `ps2_abi.c` duplicate high-value `damage.c` offset asserts, or should those stay in their TU and only run on PS2 via full closure compile?
4. Minimum DMA alignment for **in-pool** `real_matrix4x3` arrays used by VU upload — 4 vs 16 bytes?
5. When soft-double helpers are reduced, do any `real`↔`double` edges change **simulation hash** on fixed maps (closure requires fixtures before swaps)?

## Handoff summary

- **Verified (host, this session):** `tools/hcu_ps2_abi_host.py` passes; `ps2_abi.c` pins ILP32 primitives, tag/datum header shapes, PS2 cache limits, `object_datum` 420 bytes, weapon 636 bytes with trigger/magazine sub-sizes and offsets `0x1DC`/`0x210`/`0x258`/`0x278`, projectile 552 bytes with offsets `0x1E8`/`0x1F0`, PS2 `render_globals` `0x31294`, and synthetic 16-byte DMA record alignment.
- **Trusted but not re-run here:** R5900 compile of the same assertions (`docs/hcu-ps2-closure.md:64`).
- **Nested-field gaps:** No `_object_datum` field offsets in PS2 TU; no `item`/`unit`/`vehicle`/`actor`/`player` datum asserts; `projectile.arming_time` (`0x1F8`) in CE header only; weapon lacks header-local asserts.
- **DMA gaps:** Buffer-level 16-byte alignment in `ps2_memory.c` only; no CE struct DMA inventory in `ps2_abi.c`.
- **Double helpers:** M1 FPU gate **open** per `docs/hcu-ps2-closure.md:66-70` (2,099 relocations, hot physics/projectile paths); unrelated to struct sizes but blocks “EE-ready” M1 acceptance as documented.
- **MSVC/Xbox parity:** Explicitly open (`hcu-ps2-closure.md:64`); do not infer from host+R5900 agreement alone.

## Corroboration

### Agreements

- **m1_dma_layout_auditor (retry):** Four-layer DMA taxonomy; `object_datum` **420** B, weapon **636** B, projectile **552** B; `arming_time` gap and pool **4-byte** alignment match ABI gaps listed here; `real_matrix4x3` **52** B not 16-multiple.
- **m0_memory_ledger:** PS2 `render_globals` **201,364** B matches ledger `render` grouping; zeroed stub global in **m1_platform** is behavioral, not layout drift.
- **m3_collision_owner / m3_object_lifecycle:** Parity tests need `unit_datum`/`object_datum` offsets — DMA inventory §6 inheritance table is the superset for assert planning.
- **m0_link_closure:** Host `hcu_ps2_abi_host.py` gate is the fast regression named in closure doc.

### Conflicts

- None on struct sizes between ABI and DMA reports; **open** MSVC parity and soft-double gate remain ABI-local, not peer disputes.

### Updated handoff

1. Add `projectile.arming_time` (`0x1F8`) to `ps2_abi.c` golden set when next touching ABI TU.
2. Pull high-value `damage.c` offsetof asserts into host+R5900 golden JSON per **m3_collision** parity checklist — coordinate with DMA §6, do not duplicate divergent numbers.
3. M1 acceptance: ABI layout can advance while double-helper gate stays open per closure doc.
