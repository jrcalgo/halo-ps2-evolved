# m1_dma_layout_auditor

## Mission

Inventory Halo CE (HCU) record layouts and 16-byte alignment assumptions that affect DMA-facing data, D-cache–flushed REF payloads, VU1 palette uploads, or the planned M3 post-tick snapshot seam on the PS2 hybrid port. Relate them to the EE DMAC 16-byte quadword quantum (`submodules/halo-ps2/docs/01-ps2-architecture.md`), parent renderer chain/upload buffers, HP2 world section residency, and compile-time checks in `submodules/halo-ce-universal/port/ps2/src/ps2_abi.c`. Close the DMA inventory gap explicitly deferred from `docs/investigations/m1_abi_layout_auditor.md`. Report-only; no implementation changes.

## Inputs examined

| Area | Paths |
|------|--------|
| Prompt contract | `docs/investigations/_prompt_contract.md` |
| ABI sibling report | `docs/investigations/m1_abi_layout_auditor.md` (gaps §4–5, handoff DMA bullets) |
| PS2 hardware model | `submodules/halo-ps2/docs/01-ps2-architecture.md` (§2.4 DMAC, VIF, GIF) |
| M1/M3 plans | `plans/5.hcu-remake.md` (M1 step 2 `:115`, M3 snapshot step 5 `:148`) |
| ABI probe | `submodules/halo-ce-universal/port/ps2/src/ps2_abi.c`, `tools/hcu_ps2_abi_host.py` |
| PS2 memory bootstrap | `submodules/halo-ce-universal/port/ps2/src/ps2_memory.c`, `port/ps2/include/halo_ps2_limits.h`, `source/cache/physical_memory_map.h` |
| CE core records | `source/memory/data.h`, `source/tag_files/tag_groups.h`, `source/objects/objects.h`, `source/objects/scenery.h`, `source/objects/damage.c`, `source/items/items.h`, `source/items/weapons.h`, `source/items/projectiles.h`, `source/units/units.h`, `source/units/vehicle_datum.h`, `source/game/players.h`, `source/render/render.h`, `source/render/render_objects.c`, `source/math/real_math.h`, `source/structures/structures.c` |
| CE pool / blocks | `source/memory/memory_pool.c`, `source/objects/objects.c` (`object_header_block_*`) |
| Parent renderer / DMA | `submodules/halo-ps2/engine/src/render/chain.h`, `upload.h`, `bsp_render.h`, `bsp_render.c`, `core/mem.h`, `core/mem.c`, `core/mat.h`, `sim/objects.h`, `sim/skeleton.h`, `world/world.c` |
| PS2 SDK types | `submodules/ps2sdk/ee/packet2/include/packet2_types.h` (`dma_tag_t`) |
| Budget regions | `config/memory-budget.json`, `docs/memory.md` (DMA command buffers) |
| Placeholder / parent fixtures | `src/hybrid/protocol.h`, `src/game/shot.h` |
| Closure context | `docs/hcu-ps2-closure.md` |

**Execution this session:** `python3 tools/hcu_ps2_abi_host.py` → **passed** (`host ILP32 PS2 ABI assertions passed`). R5900 `mips64r5900el-ps2-elf-gcc` was not invoked here; layout numbers below come from CE header compile-time asserts and `ps2_abi.c` unless noted.

**Evidence baseline (Round 1):** parent HEAD `a2575e957feefbdff27febedabf60590401e6bcc`, HCU HEAD `c406a4149ddebae4f45462ce4c1e8d9cce0567c2` (`_prompt_contract.md`).

## Findings

### 1. What “DMA-facing” means in this repo (taxonomy)

Four layers must not be conflated when inventorying layouts:

| Layer | Owner | Typical memory | 16-byte rule in practice |
|-------|--------|----------------|---------------------------|
| **A. Hardware chains** | Parent `halo-ps2` | `dma_commands` region (1 179 648 B) | Every chain slot is a **16-byte quadword**; `dma_tag_t` is `aligned(16)` (`packet2_types.h:124`). |
| **B. REF / IMAGE payloads** | Parent renderer + HP2 world | Uncached EE buffers, texture/lightmap pages, baked batch packets | **Address** lower 4 bits zero; **byte length** often multiple of 16 for GIF uploads (`upload.h:8`); **D-cache flush** before DMA (`bsp_render.h:27-28`, `world.c:35`). |
| **C. Planned HCU→parent seam** | Future HCU snapshot builder | `frame_scratch` (393 216 B) (`config/memory-budget.json:19`) | Not implemented; must be pointer-free rows suitable for EE read and optional bulk copy into chains. |
| **D. CE simulation authority** | HCU `source/` | `game_state`, datum arrays, object header blocks, `render_globals` | **Not** EE DMA payloads today; 4-byte-oriented MSVC-shaped structs; pointers and pool-relative block refs. |

M1 step 2 language (“every DMA-visible record”) applies to **layers A–C** and to any CE-derived row that layer C copies into B without repacking (`plans/5.hcu-remake.md:115`). Layer D is snapshot **source** data, not safe to DMA as-is (`m1_abi_layout_auditor.md` §4 gap 1).

### 2. DMA quadword quantum (hardware + project convention)

- EE DMAC transfers in **16-byte quadwords**; source chains use `cnt` / `ref` / `end` tags (`01-ps2-architecture.md:75-77`).
- Parent VIF1 chain builder documents the same quantum (`chain.h:3-7`): flat `uint64_t` arrays, REF points at flushed external data, CNT carries inline per-draw state.
- `halo-ps2/CLAUDE.md`: C11, no `double`, **16-byte aligned DMA structs**, VU1 layouts beside `.vsm`.

**Implication:** Any contiguous array intended for `chain_ref(..., qw, ...)` or GIF IMAGE tags must have **qword-aligned base** and usually **size ≡ 0 (mod 16)** for upload helpers.

### 3. Gaps closed vs `m1_abi_layout_auditor` (explicit cross-walk)

| ABI auditor gap (`m1_abi_layout_auditor.md`) | This report’s resolution |
|-----------------------------------------------|---------------------------|
| §4.1 — No CE struct `alignof == 16` except `ps2_dma_record` | **Confirmed**; full inventory in §6–§8; only probe + static HCU buffers use 16-byte alignment in `port/ps2`. |
| §4.2 — Datum pool base alignment beyond `ps2_memory.c` static arrays | **Documented** §9: `memory_pool_block_allocate` rounds to **4 bytes** (`memory_pool.c:158-160`); `object_header_block` payloads inherit pool alignment, not 16. |
| §4.3 — `object_header_block_reference` / node matrix pools | **Documented** §7.3: matrices are `real_matrix4x3[]` in object-attached blocks (`objects.c:1307`, `1917-1949`); no PS2 assert on block base or stride. |
| §4.4 — Tag cache **contents** layout | **Out of scope** (M2 loader); ABI only caps `HALO_PORT_TAG_CACHE_SIZE` (`ps2_abi.c:37`). |
| §4.5 — Parent DMA chains | **Inventory** §10–§11. |
| §5 — Nested-field coverage (`unit_datum`, `damage.c`, `projectile.arming_time` in CE only) | **Listed** §6–§7; PS2 TU still missing `projectile.arming_time` (`0x1F8`) assert (`projectiles.h:64-67` vs `ps2_abi.c:50-52`). |
| Open Q4 — in-pool `real_matrix4x3` 4 vs 16 | **Still open** §14 Q3; evidence favors **4-byte** pool slots unless snapshot builder repacks. |

### 4. `ps2_abi.c` — layout locked today (DMA-relevant subset)

Compile-only TU (`ps2_abi_check` empty at `:63-65`). Host driver: `tools/hcu_ps2_abi_host.py`.

#### 4.1 Scalars, tags, cache caps

| Assertion | Value | `ps2_abi.c` |
|-----------|-------|-------------|
| ILP32 pointers/`long`, 16-bit `wchar_t`, 32-bit `float`/`real` | — | `:29-33` |
| `datum_header` | 2 | `:34` |
| `tag_block` | 12 | `:35` |
| `tag_reference` | 16 | `:36` |
| `TAG_CACHE_SIZE` == `HALO_PORT_TAG_CACHE_SIZE` | 2 097 152 | `:37` |
| Texture cache pages × 16 KiB | 524 288 | `:38-39` |
| Sound cache | 524 288 | `:40` |

`tag_reference` is **16 bytes** but contains a `char *name` (`tag_groups.h:94-100`) — size matches a quadword lane, **not** DMA-safe semantics.

#### 4.2 Combat / object records (sizes and offsets)

| Type | Size | PS2 assert | CE corroboration |
|------|------|------------|------------------|
| `object_datum` | 420 (`0x1A4`) | `:41` | `scenery.h:32-33` |
| `weapon_trigger` | 36 (`0x24`) | `:42` | `weapons.h` |
| `weapon_magazine` | 12 (`0x0C`) | `:43` | `weapons.h` |
| `weapon_datum` | 636 (`0x27C`) | `:44` | prefix + item + weapon |
| `projectile_datum` | 552 (`0x228`) | `:50` | `projectiles.h` |
| `render_globals` (HALO_PS2) | 201 364 (`0x31294`) | `:53` | `render.h:101-117` bitmap guards |

**Weapon nested offsets** (`:45-49`): `weapon` @ `0x1DC`, `triggers` @ `0x210`, `magazines` @ `0x258`, `game_time_last_fired` @ `0x278`.

**Projectile offsets in PS2 TU** (`:51-52`): `target_object_index` @ `0x1E8`, `detonation_timer` @ `0x1F0`. **Missing in PS2 TU:** `arming_time` @ `0x1F8` (`projectiles.h:64-67`); additional runtime asserts in `projectiles.c:259-275` not mirrored in `ps2_abi.c`.

#### 4.3 Only explicit 16-byte alignment probe

```55:61:submodules/halo-ce-universal/port/ps2/src/ps2_abi.c
struct ps2_dma_record
{
	unsigned char bytes[16];
} __attribute__((aligned(16)));

typedef char ps2_dma_record_is_16[sizeof(struct ps2_dma_record) == 16 ? 1 : -1];
typedef char ps2_dma_record_is_aligned[__alignof__(struct ps2_dma_record) == 16 ? 1 : -1];
```

Grep: **no other references** to `ps2_dma_record` in the tree. Pattern placeholder for future snapshot/DMA rows, not M3 schema.

**M1 plan status:** “Exhaustive nested-field comparison, every DMA-visible record” remains **open** (`plans/5.hcu-remake.md:122`).

### 5. PS2 port buffers — 16-byte alignment (HCU bootstrap)

`ps2_memory.c` static backing stores (`:21-25`):

| Buffer | Bytes | Macro |
|--------|------:|-------|
| Game state | 3 428 352 | `HALO_PORT_GAME_STATE_SIZE` (`halo_ps2_limits.h:19-22`) |
| Tag cache | 2 097 152 | `HALO_PORT_TAG_CACHE_SIZE` (`:24`) |
| Texture cache | 524 288 | 32 × 16 KiB (`:25-26`) |
| Sound cache | 524 288 | `HALO_PORT_SOUND_CACHE_SIZE` (`:27`) |
| `malloc` arena | 262 144 | `PS2_MALLOC_BYTES` (`ps2_memory.c:19`) |

`__wrap_malloc` rounds allocation size **up to 16 bytes** (`ps2_memory.c:75-76`).

**Budget note:** These arrays are **not** yet carved from the parent boot arena (`ps2_memory.c:4-9`, `docs/hcu-ps2-closure.md:116-118`). Alignment of **bases** is satisfied for static BSS; **contents** (datum pools inside game state) are not.

### 6. CE datum inheritance chain (simulation records — snapshot sources)

Common prefix (all typed object datums):

```
long definition_index;              /* 4 */
struct _object_datum object;        /* 416 when total object_datum is 0x1A4 */
/* type-specific tail */
```

| Datum | Total size | Tail offset | Derived tail size | Key headers |
|-------|------------|-------------|-------------------|-------------|
| `object_datum` | `0x1A4` (420) | — | — | `objects.h:318-322` |
| `item_datum` | `0x1DC` (476) | `item` @ `0x1A4` | `0x38` (56) | `items.h:36-57` |
| `weapon_datum` | `0x27C` (636) | `weapon` @ `0x1DC` | `0xA0` (160) | `weapons.h:213-218` |
| `projectile_datum` | `0x228` (552) | `projectile` @ `0x1DC` | `0x4C` (76) | `projectiles.h:48-54` |
| `unit_datum` | *(no single `sizeof` assert)* | `unit` @ `0x1A4` | `0x280` (640) derived† | `units.h:555-560` |
| `vehicle_datum` | `0x47C` (1148) | `vehicle` @ `0x424` | `0x58` (88) | `vehicle_datum.h:57-68` |
| `player_datum` | `0xD4` (212) | — | — | `players.h:177-178` |

† `unit` size: `offsetof(vehicle_datum, vehicle)` (`0x424`) − `sizeof(_object_datum)` (`0x1A0`) = `0x280`.

**Alignment / DMA:** None of these totals are multiples of 16 except coincidentally (`player_datum` 212, `projectile_datum` 552). None are asserted `__alignof__ == 16`. **Do not** `memcpy` whole datums across the tick boundary for rendering.

### 7. CE fields that touch rendering or matrix data

#### 7.1 `_object_datum` block references (`objects.h:249-316`)

| Field | Type | Role |
|-------|------|------|
| `original_node_orientations` | `object_header_block_reference` | Pool-relative block |
| `node_orientations` | same | Orientations for skinning |
| `node_matrices` | same | `real_matrix4x3` array via `object_get_node_matrix` |

`object_header_block_reference` is `{ short size; short offset; }` (`objects.h:249-253`). Payload lives in the **object memory pool** (`object_header_block_allocate`, `objects.c:724+`). Resolution: `object_header_block_get` (`objects.c:668+`).

#### 7.2 `real_matrix4x3` (`real_math.h:477-491`)

| Property | Value |
|----------|--------|
| Layout | `real scale` + `real n[4][3]` |
| `sizeof` | **52** (not 48 — includes leading `scale`) |
| Typical `__alignof__` | **4** (ILP32 `real`) |
| Multiple of 16 | **No** |
| VU relevance | CE stores node transforms; parent/VU1 consume **`mat4`** (64 B) or **5×4 float palette rows** (`skeleton.h:16-19`). Snapshot must **repack**, not alias CE pool memory in a REF tag. |

#### 7.3 `render_skinning` (`render.h:63-67`)

```c
struct render_skinning {
    real_matrix4x3 const *node_matrices;
    short node_matrix_count;
};
```

Pointer + count — **forbidden** in layer C snapshot without indirection replacement.

#### 7.4 CE per-frame render bookkeeping (`render_objects.c`)

| Struct | `sizeof` assert | Multiple of 16? | Pointer fields? |
|--------|-----------------|-------------------|-----------------|
| `render_model_effect` | `0x28` (40) | No | — |
| `object_render_data` | `0x48` (72) | No | `struct render_lighting *lighting` (`:162-172`) |
| `object_render_state` | `0x100` (256) | **Yes** | No pointers in struct body |
| `render_object_globals` | `4 + 256×4` | No (1028) | Index array only |

`MAXIMUM_RENDERED_OBJECTS` = `HALO_PORT_MAXIMUM_RENDERED_OBJECTS` (256) on PS2 (`objects.h:50`, `halo_ps2_limits.h:37`). Desktop OpenCE uses 1024 (`halo_port_capacity.h:90`) — PS2 snapshot caps must follow **256**, not desktop.

`object_render_data` embeds `real_matrix4x3 shadow_matrix` (52 B) — shadow path only; still 4-byte-oriented.

#### 7.5 `render_globals` (PS2 size only in `ps2_abi.c`)

Contains cameras, frusta, cluster visibility bitvectors, surface lists (`render.h:77-109`). PS2 shrinks `environment_surface_flags` to a tight bit vector (`render.h:101-117`; size `0x31294` in `ps2_abi.c:53`).

**Role:** Mutable simulation/render-bridge state updated during `interface_draw_screen` / render tick — **not** a DMA buffer. Snapshot seam must choose **subset** (e.g. camera, fog, visible cluster flags) vs recomputation on parent.

#### 7.6 BSP / environment geometry (collision + static draw)

Compile-time sizes in `structures.c` (relevant if BSP bytes are ever DMA’d from EE without repack):

| Struct | Size assert | mod 16 |
|--------|-------------|--------|
| `environment_vertex_compressed` | `0x20` (32) | **0** |
| `structure_cluster_portal` | `0x40` (64) | **0** |
| `structure_fog_plane_render` | `0x20` (32) | **0** |
| `structure_runtime_globals` | `0x808` (2056) | **8** |

Parent Blood Gulch path uses **HP2** sections and baked batch packets in world arena (`world.c:26-35`), not raw CE `environment_vertex_compressed` at runtime on PS2 hybrid.

### 8. Parent renderer types (layer A–B — actual DMA path)

#### 8.1 Chain and upload contracts

| Rule | Source |
|------|--------|
| Chain = 16-byte quadwords | `chain.h:3-7` |
| REF target must be D-cache flushed | `chain.h:23`, `bsp_render.h:27-28` |
| GIF upload `bytes` multiple of 16 | `upload.h:8` |
| `tex_image_t.pixels` / `clut` 16-byte aligned | `bsp_render.h:27-28` |

#### 8.2 Buffer sizes and allocation

| Buffer | Quadwords each | Bytes each (×2) | Source |
|--------|---------------:|----------------:|--------|
| Frame chain | 32 768 | 524 288 (1 048 576 total) | `bsp_render.c:27`, `docs/memory.md:66-71` |
| Upload chain | 4 096 | 65 536 (131 072 total) | `bsp_render.c:28` |
| **Sum** | — | **1 179 648** | `config/memory-budget.json:15` |

Allocation: `memalign(64, bytes)` + uncached alias `0x30000000` (`bsp_render.c:104-110`). **64-byte** base alignment stricter than DMAC 16-byte quantum.

Parent arenas: sub-arenas carved at **16-byte** boundary (`mem.c:27`, `mem.h:16-17`).

#### 8.3 `object_t` / `mat4` (planned snapshot consumer shape)

| Type | `sizeof` | Typical `__alignof__` | Notes |
|------|----------|------------------------|-------|
| `mat4` | 64 | 4 | `mat.h:8` — size is 4×16, alignment **not** forced to 16 |
| `object_t` | 128 | 4 | `sim/objects.h:19-29` — ends with `mat4 root`; 128 ≡ 0 (mod 16) but struct alignment 4 |

`object_nodes_t`: `mat4 world[64]` + `mat4 skin[64]` (`sim/objects.h:57`) → **8 192 bytes** per pose scratch — stack/scratch sizing for snapshot builder, not DMA chain storage as a whole.

#### 8.4 VU1 palette row (`sim/skeleton.h:16-19`)

**Five quadwords** (80 bytes) per node: four rows of clip-space matrix + light direction row. 80 **not** a power of two; batches built explicitly in engine code. Not a CE type.

#### 8.5 HP2 world section load alignment (`world.c`)

| Allocation | Align | Purpose |
|------------|-------|---------|
| Decoded section `raw` | **64** | `arena_alloc(a, raw_size, 64)` (`:26`) |
| Decode scratch `stored` | **16** | `:29` |
| Pack header buffer | `aligned(16)` static | `:11` |

Comment `:35`: `SyncDCache` because **DMA reads batches and textures straight from this memory**.

### 9. Allocator alignment vs DMA (CE + PS2 bootstrap)

| Mechanism | Alignment | DMA implication |
|-----------|-----------|-----------------|
| `ps2_memory.c` static regions | 16-byte base | Good for any future DMA from those bases |
| `__wrap_malloc` / bump | 16-byte size round | Returned block offset within arena is 16-step |
| `memory_pool_block_allocate` | **4-byte** round (`memory_pool.c:158-160`) | Object header blocks and `real_matrix4x3` arrays can start at **4 mod 16** |
| `game_state_malloc` / datum arrays | Inherited from pool + `data_array` | No PS2 inventory of per-array alignment |
| Parent `arena_alloc` | Caller-chosen; sub-arena **16** | World/raw 64 for section blobs |

**Risk:** Blind EE `chain_ref` into a `real_matrix4x3[]` inside an object pool block may violate **address** alignment for REF if the block base is only 4-aligned.

### 10. Service types adjacent to DMA (not gameplay datums)

| Type | Size | 16-byte lane? | In `ps2_abi.c`? |
|------|------|---------------|-----------------|
| `data_iterator` | `0x10` (16) | Size only; no align assert | No (`data.h:50-51`) |
| `tag_reference` | 16 | Yes size; contains pointer | Partial (`:36`) |
| `datum_header` | 2 | No | Yes (`:34`) |

### 11. Non-CE “snapshot” placeholders

| Type | Location | DMA / align contract |
|------|----------|----------------------|
| `hybrid_snapshot` | `src/hybrid/protocol.h:14-17` | M08 synthetic; POD, no `aligned(16)` |
| `shot_impact_event` | `src/game/shot.h:28-34` | Parent combat fixture queue; mixed layout |
| `ps2_dma_record` | `ps2_abi.c:55-61` | Only HCU 16-byte align probe |

No `snapshot_builder`, `ps2_render_snapshot`, or `frame_scratch` writer in HCU `port/ps2` (grep).

### 12. Master inventory — CE / HCU vs DMA-facing expectations

| Category | Examples | `ps2_abi.c` size/offset? | `alignof==16` asserted? | Safe REF/DMA / snapshot memcpy? |
|----------|----------|----------------------------|-------------------------|--------------------------------|
| Tag/datum headers | `datum_header`, `tag_block`, `tag_reference` | Partial | No | No (`tag_reference` pointer) |
| Object core | `object_datum`, `_object_datum` | Size only | No | No (block refs) |
| Items / weapons / projectiles | `item_datum`, `weapon_datum`, `projectile_datum` | Weapon/proj partial | No | No |
| Units / vehicles / players | `unit_datum`, `vehicle_datum`, `player_datum` | No | No | No |
| Render bridge | `render_globals`, `object_render_*` | Globals size only | No | No (pointers / mutable) |
| Math | `real_matrix4x3` | No | No | Repack only |
| BSP structs | `environment_vertex_compressed`, … | CE TU asserts only | No | Parent uses HP2 packs |
| HCU staging | `game_state[]`, caches | Cache macros | **Base** 16 only | Contents unqualified |
| HCU probe | `ps2_dma_record` | Yes | **Yes** | Yes (16 B placeholder) |
| Parent chains | `chain_t`, `dma_tag_t` | N/A | Tags yes | Per REF rules |
| Parent sim table | `object_t`, `mat4`, VU palette rows | N/A | No / by convention | Built per frame on parent |

### 13. Open risks (plans / closure)

- M1 gate: identify and assert **every layer A–C record**; only `ps2_dma_record` today (`plans/5.hcu-remake.md:115-122`).
- `HALO_PORT_OBJECT_MEMORY_POOL_SIZE` = 1 MiB via `game_state_malloc` — snapshot high-water stacks with pool + `frame_scratch` (`docs/hcu-ps2-closure.md:121`).
- Retail tag images exceed 2 MiB tag cache; competes for EE map with scratch (`plans/5.hcu-remake.md:138`).
- `interface_draw_screen` may run multiple times per tick — snapshot immutability vs `render_globals` mutation (`docs/hcu-ps2-platform-placeholder-audit.md:17`, cited in prior draft).

## Interface contracts for the main agent

1. **Versioned `ps2_render_snapshot` (or equivalent)** in HCU `port/ps2`: caller-owned `frame_scratch` buffer; **no pointers**; generation-safe handles for objects; cap objects at `HALO_PORT_MAXIMUM_RENDERED_OBJECTS` (256).
2. **Row layout:** each sub-record that may be copied into a DMA chain or read as a quadword stream uses `__attribute__((aligned(16)))` and `static_assert(sizeof % 16 == 0)` — extend pattern beyond `ps2_dma_record`.
3. **Matrix path:** CE `real_matrix4x3` → parent `mat4` and/or `skel_palette_entry` float rows in the builder; never publish `object_header_block_get` pointers across the seam.
4. **Parent owns** `dma_commands` chains (`CHAIN_QW` / `UPLOAD_QW`); snapshot is **input** to `bsp_render_build` / `obj_render`, not a replacement chain buffer.
5. **Extend ABI gate:** add snapshot header/row types to `ps2_abi.c` or sibling compile-only TU; keep `tools/hcu_ps2_abi_host.py` in CI; add `projectile.arming_time` (`0x1F8`) if parity with `projectiles.h` is desired (`m1_abi_layout_auditor.md` §7).
6. **Pool policy decision:** either align object header blocks to 16 bytes at allocation time or always repack matrices into scratch before REF — document in M3 builder.

## Recommended tests / fixtures

| Test | Purpose |
|------|---------|
| `python3 tools/hcu_ps2_abi_host.py` | Regression on existing asserts |
| Future `ps2_snapshot_layout.c` | `sizeof` / `offsetof` / `__alignof__` for snapshot rows |
| `make -C submodules/halo-ps2/engine/tests` (`test_chain.c`) | Chain REF alignment behavior |
| M3: tick → snapshot → zero parent sim mutation with render suppressed | `plans/5.hcu-remake.md:148-150` |
| Host vs R5900 `__alignof__` dump for `mat4`, `object_t`, snapshot rows | Catch toolchain drift |
| Optional: assert `object_render_state` size `0x100` in PS2 TU | Already CE-asserted (`render_objects.c:197-198`) |

## Dependencies on other investigators

| Investigator | Dependency |
|--------------|------------|
| `m1_abi_layout_auditor` | Scalar/datum overlap; avoid duplicating primitive tables |
| `m2_arena_capacity_auditor` | `frame_scratch` high-water vs `dma_commands`; arena routing |
| `m3_snapshot_render_auditor` | Consumer field contract in `obj_render` / HUD / FP |
| `m3_object_lifecycle_auditor` | Which CE fields appear in snapshot handles |
| `m0_memory_ledger_auditor` | Assign snapshot + chain bytes to budget v2 |

## Open questions

1. Exact **snapshot schema** (per-object record, node palette cap, HUD blob) — not in repo (M3).
2. Should **`mat4` / `object_t`** use `aligned(16)` on EE for REF convenience, or stay 4-aligned with explicit copy?
3. **Object pool block alignment:** upgrade `memory_pool` to 16-byte blocks vs repack-only in scratch?
4. **R5900 vs host ILP32** `__alignof__` on large CE structs — host passes sizes/offsets in `ps2_abi.c` but does not record alignments.
5. Which **`render_globals`** fields are snapshot-authoritative vs recomputable on parent each draw?
6. **SIF0/1/2** IOP↔EE DMA (pad, CDVD, RPC) — out of hybrid render path; needs separate audit if HCU services grow.

## Handoff summary

- **Taxonomy:** Hardware chains (16-byte qw), flushed REF payloads, planned `frame_scratch` snapshot, and CE simulation records are **four distinct layers**; M1 DMA asserts apply to the first three, not raw datums.
- **Hardware / parent:** 16-byte DMAC quantum (`01-ps2-architecture.md:75-77`); `dma_tag_t` aligned 16 (`packet2_types.h:124`); 1 179 648 B double chains; 64-byte uncached alloc; 16-byte texture uploads + `SyncDCache` (`docs/memory.md`, `bsp_render.c`, `upload.h`).
- **`ps2_abi.c`:** ILP32, tag/datum sizes, `object_datum` 420 B, `weapon_datum` 636 B (offsets listed), `projectile_datum` 552 B (missing `arming_time` offset), PS2 `render_globals` 201 364 B, cache caps, **`ps2_dma_record` only 16-byte align probe**.
- **CE datums:** 4-byte-oriented, pointer/block-ref heavy; inheritance table §6; render-side `object_render_data` / `object_render_state` sizes in CE asserts — **not** in `ps2_abi.c`.
- **`real_matrix4x3`:** 52 bytes, not 16-multiple; pool alignment **4-byte** unless changed.
- **M3 snapshot:** unimplemented; `frame_scratch` 393 216 B budgeted; designing 16-byte-aligned, pointer-free rows is the primary work to close M1 step 2 beyond `ps2_dma_record`.
- **ABI auditor gaps:** inventory and parent DMA path documented here; Xbox MSVC parity and double-helper gate remain in `m1_abi_layout_auditor.md` / `docs/hcu-ps2-closure.md`.

## Corroboration

### Agreements

- **m1_abi_layout_auditor:** Datum sizes/offsets and `arming_time` gap are consistent; DMA report is the CE struct superset for M3 parity asserts.
- **m3_snapshot_render:** Snapshot belongs in **`frame_scratch`** as pointer-free POD rows — not raw `object_datum` DMA.
- **m0_memory_ledger:** **393,216** B `frame_scratch` region budget matches config v2; snapshot high-water not yet measured.
- **m0_runtime_ownership:** Parent halo-ps2 chains (64 B alloc, `SyncDCache`) are presentation DMA; CE datums stay repack-only per master table §7.
- **m3_collision_owner:** Collision queries use CE records in sim memory; HP2 `collision.hp2` is not a DMA payload into CE pools.

### Conflicts

- None on 16-byte hardware quantum vs 4-byte CE pools — layered taxonomy resolves **C5** partial (BSS layout vs DMA row design are separate workstreams).

### Updated handoff

1. M3 snapshot schema: 16-byte-align rows in `frame_scratch`; never snapshot pointer/block-ref fields verbatim.
2. Extend `ps2_abi.c` beyond `ps2_dma_record` probe only after snapshot field list is frozen with **m3_snapshot_render**.
3. VU upload path: treat `real_matrix4x3` repack at upload boundary unless pool alignment policy changes.
