# M2 Step 8 multiplayer topology solution review — 2026-10-21

## Finding

For the 13 stock multiplayer maps, the existing CE interfaces already support a tag image and one active BSP at different physical bases, but they require each image to be a single contiguous span. The present fixed `current_bsp` span is 71,216 bytes short for Sidewinder's *map-specific* CTAG+BSP pair. A fixed all-map binding is tighter: the largest aligned CTAG is 4,477,120 bytes and the largest BSP is 1,984,512 bytes, so a fixed pair needs 6,461,632 bytes, **170,176 bytes over** the current 6,291,456-byte `current_bsp` region.

The production binder's uncommitted-looking `resident_gameplay` remainder is not a demonstrated 1.98 MiB BSP owner. The actual production layout charges 2,114,588 bytes of ELF BSS to that region before carving the boot arena; after CE game state and current bitmap claims, only 486,372 bytes remain in the arena. The experimentally qualified interval-claims table would raise this to 1,207,228 bytes, still **777,284 bytes short** of a contiguous Sidewinder BSP. Therefore the tempting “put BSP in resident_gameplay” move is not an implementable fit under current owners.

No existing contiguous span has been proved safely reallocatable. The lowest-risk topology *candidate* is to extend the contiguous map owner by 170,176 bytes into `texture_cache`, retaining the existing CE one-span BSP contract and reducing texture-cache capacity from 4,194,304 to 4,024,128 bytes. This is arithmetic only: no all-13 texture/lightmap EE high-water plus bot/co-op workload establishes that 170,176 bytes can be removed safely. Do not make that capacity move the default until the proposed diagnostic slice measures it.

## Input scope and data

The runtime catalog names the 13 multiplayer entries plus the separate UI entry ([`hcu_map_catalog.c:135-265`](../../src/stream/hcu_map_catalog.c#L135)). Campaign maps are outside this decision. The table below uses the retained retail working-set report's compact CTAG and largest *raw* active BSP values; its own exclusions include claims, renderer resources, texture/audio working sets, alignment and transition peaks ([`retail-map-minimum-working-set-current.json:1-16`](retail-map-minimum-working-set-current.json#L1)). Raw BSP is retained in full; no compressed-vertex savings are credited.

| Map | CTAG bytes | Raw active BSP bytes | Pair bytes | Pair margin in 6,291,456 B |
|---|---:|---:|---:|---:|
| Beaver Creek | 4,319,568 | 724,992 | 5,044,560 | +1,246,896 |
| Blood Gulch | 4,477,116 | 1,296,384 | 5,773,500 | +517,956 |
| Boarding Action | 4,358,612 | 1,343,488 | 5,702,100 | +589,356 |
| Carousel | 4,277,864 | 507,904 | 4,785,768 | +1,505,688 |
| Chill Out | 4,252,432 | 567,296 | 4,819,728 | +1,471,728 |
| Damnation | 4,345,868 | 1,320,960 | 5,666,828 | +624,628 |
| Hang ’Em High | 4,246,076 | 589,824 | 4,835,900 | +1,455,556 |
| Longest | 4,263,624 | 374,784 | 4,638,408 | +1,653,048 |
| Prisoner | 4,241,088 | 884,736 | 5,125,824 | +1,165,632 |
| Putput | 4,250,464 | 1,638,400 | 5,888,864 | +402,592 |
| Rat Race | 4,270,452 | 544,768 | 4,815,220 | +1,476,236 |
| Sidewinder | 4,378,160 | 1,984,512 | **6,362,672** | **−71,216** |
| Wizard | 4,259,188 | 552,960 | 4,812,148 | +1,479,308 |

All tag spans round up to 16 bytes without changing these listed values except the global maximum: 4,477,116 becomes **4,477,120**. BSP extents are already 16-byte multiples. The all-map fixed pair is therefore 4,477,120 + 1,984,512 = **6,461,632 bytes**. Because `physical_memory_bind_*` establishes one fixed address/capacity per CE cache before `physical_memory_allocate()`, a static all-map topology must cover both maxima, not only each map's actual sum.

## What the production code can and cannot bind

`hcu_memory_bind_parent_v2()` currently allocates CE game state from `resident_gameplay`, places the tag span at the start of `current_bsp`, binds the BSP cache to the remaining tail, and allocates claims from `resident_gameplay` ([`hcu_memory_bind.c:19-72`](../../src/stream/hcu_memory_bind.c#L19)). The PS2 provider has separate tag-cache and structure-BSP base/capacity bindings and rejects overlap/late binding ([`ps2_memory.c:91-110,141-177`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L91)). Thus tag and BSP can already be physically disjoint; their *individual* contiguity is the constraint.

The validator intentionally translates the separate BSP address range into a logical claims offset after the tag span (`tag_validate.c`, `claims_address_space_capacity()` and `claim_address_offset()` at lines 237-258 and 442-475). This proves disjoint tag/BSP regions are supported; it does not prove segmented storage within the BSP. `ps2_cbsp_materialize()` receives one destination base and capacity and writes/rebases the decoded BSP in that image ([`ps2_cbsp.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c)); CE's cache read API and direct consumers likewise publish ordinary pointers into the materialized image. A multi-span BSP would need a logical-address translation layer across schema relocation, CE validation and every direct BSP consumer. It is a broad CE data-model/API redesign, not a low-risk way to append 71 KiB.

The PS2 production machine uses a 1,048,576-byte map-owner slice plus a disjoint 524,288-byte HP2 scratch slice inside `streaming` ([`hcu_main.c:372-401`](../../src/stream/hcu_main.c#L372)); those solve section staging, not final CE pointer residency. `frame_scratch` has 393,216 bytes and its render snapshots are already bound there. Its remaining snapshot margin is neither adjacent to the BSP span nor exposed to the CE BSP binder. The 5,767,168-byte reserve remains unavailable ([`memory-budget.json:1-20`](../../config/memory-budget.json#L1)).

## Resident-gameplay arithmetic: why it is not the spare BSP span

The PS2 game-state allocation is fixed at `0x305000 + 0x40000 = 3,428,352` bytes ([`halo_ps2_limits.h:18-22`](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L18)). Under the current fixed all-map cache capacities, the bitmap claims domain is 6,461,632 bytes. The current CE validator's bitmap is one bit per addressable byte, rounded to four-byte `unsigned long` words ([`tag_validate.c:272-283`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L272)); this needs `ceil(6,461,632/32)*4 = 807,704` bytes.

The exact production entry deducts ELF NOBITS/BSS from `resident_gameplay` before allocating its v2 arena ([`hcu_main.c:218-236`](../../src/stream/hcu_main.c#L218)); the current integrated candidate records **2,114,588 B BSS** ([`plans/7.hcu-remake-m2-m4.md:17`](../../plans/7.hcu-remake-m2-m4.md#L17)). Therefore:

| Resident owner | Bytes |
|---|---:|
| Region budget | 6,815,744 |
| ELF BSS charged to region | −2,114,588 |
| Remaining boot-arena capacity | **4,701,156** |
| CE game state | −3,428,352 |
| Bitmap claims for fixed all-MP spans | −807,704 |
| Free contiguous resident tail after current owners | **465,100** |

The last line differs from the UI/default 2 MiB tag + 4 MiB BSP binding. With that existing 6,291,456-byte claims domain, claims are 786,432 bytes and resident free tail is 486,372 bytes. Both values are below the 1,984,512-byte BSP requirement. The alternative bounded interval table is source-differential-tested at peak 4,820 intervals from an a30/a50 trace; the 8,192-entry table plus context is 65,576 bytes ([`m2-step8-claims-interval-experiment-2026-10-21.md:1-4,45-48`](m2-step8-claims-interval-experiment-2026-10-21.md#L1)). At that provisional size, resident free tail would be 1,207,228 bytes, still 777,284 bytes short. Its capture is not all-13 validation, and the interval implementation is not yet integrated into production binding.

These calculations include only current fixed CE/BSS owners, not the simultaneous game workload. The production run has not measured bot/co-op/dynamic high-water, all-map texture/lightmap EE high-water, BSP renderer data, transition overlap, or a full resident live set. Consequently these are rejection/feasibility bounds, not an accepted memory layout.

## Candidate comparison

| Candidate | Bytes / API impact | Evidence and disposition |
|---|---|---|
| Keep single `current_bsp` region, map-specific CTAG+BSP extents | Sidewinder exceeds it by 71,216 B. A fixed maximum cache split instead misses by 170,176 B. | Rejected as current topology. CE bindings are fixed before allocation; there is no per-map rebind lifecycle today. |
| Put the BSP span in `resident_gameplay` | Needs one contiguous 1,984,512-B span. | Rejected under present owners: only 465,100 B resident tail remains for fixed all-map bitmap claims, or 1,207,228 B with the experimental interval table. The latter still misses by 777,284 B before gameplay-resident extras. |
| Expand `current_bsp` by taking 170,176 B from `texture_cache` | Fixed spans become tag 4,477,120 + BSP 1,984,512 = 6,461,632 B; texture falls to 4,024,128 B. One CE BSP image remains contiguous. | Best next topology experiment, but not yet safe: no 13-map texture/lightmap EE peak or co-op/bot live-set trace proves the transferred bytes are unused. `texture_cache` is a named owner, not spare merely because the CE binding's minimum is 512 KiB ([`ps2_memory.c:27,158-164`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L27)). |
| Externalize the intact BSP over current/texture spans | Could retain current nominal capacities while making a logical BSP larger than 6 MiB. | Not low-risk. It changes ordinary pointer assumptions and requires an address translation contract for every relocated pointer, validator check, and consumer; current CBSP materialization is a one-destination operation. |
| Shrink claims to interval table, then combine with resident placement | Saves up to 742,128 B compared with 807,704-B bitmap. | Insufficient on its own: still 777,284 B below Sidewinder BSP in resident tail; interval peak comes from only two campaign host fixtures, not the 13 MP target workload. |

No campaign capacity results are used in this recommendation. Halo-64/N64 actor, animation, or pool reductions are not candidates: co-op and bots remain in the multiplayer workload and must retain CE/HCU behavior.

## Recommended next implementation slice

Build an **opt-in fixed-capacity texture-to-map repartition diagnostic**, keeping the default map catalog closed and the production budget total/reserve unchanged:

1. Freeze/re-generate one coherent 13-map CTAG/raw-BSP artifact tuple against one retained schema ELF, because the current working-set report names a historical schema identity ([`retail-map-minimum-working-set-current.json:1-16`](retail-map-minimum-working-set-current.json#L1)). Confirm all 13 largest active BSP extents and aligned CTAG maxima from that tuple.
2. Parameterize the v2 boundary so the candidate contiguous map owner is 6,461,632 bytes and the adjacent texture owner is 4,024,128 bytes, with a single intact guard between them. Keep all other region sizes and reserve exactly fixed. Bind tag=4,477,120 and BSP=1,984,512 before CE allocation. Verify the configured CE claims size is 807,704 bytes, all physical intervals/canaries and reserve boundary, and no CE address overlap. This is a diagnostic build, not a default or admission change.
3. Before claiming the 170,176-byte transfer safe, run all 13 retail maps through real package-backed CE load/query/unload, then measure texture/lightmap EE ownership and frame/cache high-water while exercising the agreed multiplayer envelope: 1–4 local players, supported bot maximum, co-op/game-mode state, vehicles, weapons/effects, collision/PVS/sound consumers, and map-switch rollback/retry. Report per-owner peaks, not compressed pack sizes. If texture ever needs the borrowed bytes, stop and pursue an explicitly reviewed pointer translation or another measured owner.
4. Only after the exact candidate's target placement and simultaneous workload pass should the binder/layout become production-selected. Keep the entire untouched reserve, DMA, audio, dynamic-simulation, streaming, and scratch capacities unchanged; do not compensate by dropping bots/co-op behavior or copying N64 limits.

The first code-sized seam is an independent `structure_bsp` span parameter in the parent binder/layout diagnostic plus a paired texture-cap parameter. The PS2 provider already takes distinct cache bases and claims size is computed after both cache bindings, so no CE parser change is necessary for this repartition. The diagnostic must update the memory-map audit/tests and verify address ranges before boot allocation is frozen. The follow-up map/query qualification must test BSP pointer identity, all existing schema/query oracles, failure cleanup and retry. Existing successful Longest/Blood Gulch **host** fixtures and UI **guest** placement do not satisfy those target requirements.

## Decision

Current evidence disproves two easy fixes: the 71 KiB map-specific deficit cannot be placed into the present resident tail, and interval claims alone do not provide a large enough resident span. The only near-term candidate that preserves CE's present contiguous BSP pointer contract is a 170,176-byte measured repartition from `texture_cache` to the contiguous map owner. Its safety is unresolved until the exact all-13 and multiplayer workload peaks are recorded. Step 8 therefore remains open, with no map support or capacity change approved by this report.

## Texture owner follow-up (2026-10-22)

The texture-side evidence does **not** currently justify that repartition. The retained Blood Gulch viewer diagnostic measured 406,016 B of TEXS and 33,120 B of LM0 source payload, with 524,288 B staging high-water across its 16-miss case; it is one map and one diagnostic workload, not an all-13 multiplayer upper bound. The parent renderer stages decoded texture data in EE memory for GS transfer, while GS eDRAM is a separate store and cannot be counted as EE texture-cache capacity. CE's cache owner includes bitmap access and Bink/cache consumers; no measured complete call/lifetime audit proves the 170,176 B is dead or safely loanable. Consequently the `texture_cache` reduction remains an experiment only. Keep the production split unchanged until a source-backed consumer/lifetime inventory and all-13 map + 1–4 player/bot/co-op peak trace prove it. Source identity and measured viewer data are recorded in `plans/7.hcu-remake-m2-m4.md` under the Blood Gulch visual-render entry; this report deliberately makes no broader capacity claim.
