# M2 whole-map budget/repartition review (2026-10-21)

## Decision

**No budget-v2 whole-resident-map partition is currently demonstrated for the complete ten-map stock campaign, and no repartition can be approved from the available measurements.** This is stronger than the finding that the present `current_bsp` span is too small: a lower-bound construction for the largest campaign map (`d20`) exceeds the *entire committed budget* before texture/lightmap residency, dynamic simulation, DMA, streaming, checkpoint, audio, frame scratch, renderer data, and transition overlap are charged. Even the best-case campaign pair (`d40` with its smallest referenced BSP) needs a different ownership layout and lacks room evidence for the other owners.

This does **not** prove the product can never fit in 32 MiB. It proves only that an ordinary complete compact CTAG image plus one complete raw CE structure-BSP, with the existing CE game state, validation claims, and exact current ELF, cannot be accepted as a whole-resident allocation under the 26.5 MiB committed budget. A lossless, pointer-safe residency scheme or measured changes to genuinely available simultaneous working sets might change that result. Neither has been demonstrated. Keep campaign maps unqualified and M2 open.

## Scope and evidence identity

The question is whether a single campaign map at a time can be supported for **all ten** missions, keeping the stock campaign data semantically complete and the 5.5 MiB reserve unavailable. This review does not sum all ten maps simultaneously. It chooses the largest per-map `compact CTAG + largest referenced raw BSP` pair because every mission/BSP must be supportable. BSPs not simultaneously active are not summed together.

The CE/BSP figures below come from the retained all-map compaction/schema join, not the older `*-current.json` artifacts. The schema ELF is `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`; the all-map CTAG working-set JSON SHA-256 is `f6548404f3f0f2bc3814f23fd2ffba16506a63a15bd2193d61ed94dec2128aed`, and the BSP schema JSON SHA-256 is `8f59ff7e42c05380edb26aa0c94a569432e3ab14799aafe48559c42133abadc7`. Both were checked against the current files with `sha256sum`. The candidate audit itself is `docs/reports/m2-2026-10-21-capacity-candidate-audit.md` and contains the map table and provenance at lines 11–25 and 43–69.

For the *current* combined machine ELF, `build/hcu-parent-link-probe/result.json` binds ELF SHA-256 `72fe0034df7a70a13e26d95ef470006054e6e5ff5425170c89a80e98b2319ff2`, link-map SHA-256 `e43b4f3d782e9662338f3bf2211b1e31ccc20e7bcbb03523e79889b121755c71`, and memory-audit SHA-256 `1a48c99f86a01bb6497edb23579d4546354644cf7e7f82c37c5a080dfcdf77ab`. It records `p_filesz=2,086,532`, `p_memsz=4,201,244`, `.bss=2,114,588`, zero unresolved imports, `acceptance=false`, and explicitly says no guest execution was observed for that linked image. The current memory-map proposal is *logical*, and its high-water fields are unknown except for UI host fixtures; see [`config/hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L1-L8) and lines 74–86. The exact config hashes inspected were budget `67ef6d6085de71c22e3998a355cb2f79a8123837b7b14e89593a0d497de21b74`, memory map `1dff9c71e47d0f988c6765bf6559ee9dc67d3e3c012779414a4881ee84504ad0`, binder `4542021506d0873ad18f55e515ec22877d21eac38bd39bc939d61e186f720d17`, and entry `55be5d93372e6833d8a7c063facdf18b1b3054dca1a6ae5495aa4bf07cff724a`.

The review worktree and submodules are dirty. Commit pins alone therefore do not identify every compiled source byte. `docs/reports/m2-2026-10-21-capacity-candidate-audit.md` ties the map set to the recorded XISO SHA and details that its `2fba…` ELF is a schema/packing ELF, not a gameplay guest. Do not combine the older HCU/parent boot ELF/PCSX2 observations with the current ELF or claim a current-target peak from the static join.

## Budget model and present ownership

Budget v2 is 33,554,432 bytes total, of which 5,767,168 bytes (5.5 MiB) are a forbidden reserve. Therefore the maximum committed amount is 27,787,264 bytes (26.5 MiB). Named reservations are `system_kernel=1,572,864`, `elf_static=2,097,152`, `resident_gameplay=6,815,744`, `current_bsp=6,291,456`, `texture_cache=4,194,304`, `dynamic_simulation=2,621,440`, `dma_commands=1,179,648`, `streaming=1,572,864`, `checkpoint=524,288`, `audio=524,288`, and `frame_scratch=393,216` ([`config/memory-budget.json`](../../config/memory-budget.json#L4-L20)). The named non-map allocations are not available to silently enlarge the map region: they stand for live engine duties and most have no measured spare/high-water evidence yet.

The present [binder](../../src/stream/hcu_memory_bind.c#L41-L70) places a **single contiguous** tag cache at the start of `current_bsp`, the BSP cache in the remaining tail, CE game state in `resident_gameplay`, and the claims bitmap—computed from both configured spans—in that same resident arena. The entry defaults the tag span to 2,097,152 bytes ([`hcu_main.c`](../../src/stream/hcu_main.c#L17-L19)); PS2 CE claim sizing is `ceil((tag_span + bsp_span)/32) * 4` bytes ([`tag_validate.c`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L244-L283)). Thus current combined tag/BSP capacity is 6,291,456 bytes and its claims are 786,432 bytes. Do not count CE's 1 MiB nested object pool twice: `HALO_PORT_GAME_STATE_SIZE` already owns the game-state buffer, while M2 still has to route transient objects/effects to the distinct dynamic pool ([`config/hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L3-L8), [limits header](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L18-L22)).

The latest machine ELF has 2,086,532 file-backed LOAD bytes, within the 2 MiB `elf_static` limit by only 10,620 bytes; its 2,114,588-byte `.bss` is charged separately to `resident_gameplay`. This is a useful exact artifact-size lower bound, **not** proof of a fully reconciled physical M2 map. The link probe derives static placement conditions but labels the actual boot pointer and target bounds unverified ([`hcu_parent_link_probe.py`](../../tools/hcu_parent_link_probe.py#L92-L160)); the current result likewise records `acceptance=false` and no guest execution. The historical M1 guest placements with other hashes cannot close the current ELF's physical-placement question.

## All-campaign map data lower bounds

The following figures join each compact complete CTAG image to the smallest and largest complete raw BSP referenced by that scenario. Smallest-BSP pairs are optimistic feasibility lower bounds, not necessarily the spawn BSP; largest-BSP pairs are the required per-map maximum for a campaign-support gate that includes all referenced BSPs. No BSP schema fields or compressed vertices are omitted. Values are bytes, before base alignment, any staging, renderer packs, active resource working sets, or map-transition overlap.

| Mission | CTAG image | Smallest raw BSP | CTAG + smallest | Largest raw BSP | CTAG + largest |
|---|---:|---:|---:|---:|---:|
| a10 | 9,622,260 | 1,529,856 | 11,152,116 | 8,568,832 | 18,191,092 |
| a30 | 9,689,096 | 6,199,296 | 15,888,392 | 7,174,144 | 16,863,240 |
| a50 | 11,174,776 | 3,835,904 | 15,010,680 | 7,159,808 | 18,334,584 |
| b30 | 10,268,076 | 4,022,272 | 14,290,348 | 6,608,896 | 16,876,972 |
| b40 | 11,781,424 | 1,288,192 | 13,069,616 | 5,838,848 | 17,620,272 |
| c10 | 11,553,616 | 4,704,256 | 16,257,872 | 5,988,352 | 17,541,968 |
| c20 | 6,267,540 | 6,864,896 | 13,132,436 | 9,039,872 | 15,307,412 |
| c40 | 11,186,344 | 1,400,832 | 12,587,176 | 6,318,080 | 17,504,424 |
| d20 | 10,046,996 | 3,807,232 | 13,854,228 | 8,517,632 | **18,564,628** |
| d40 | 10,302,684 | 8,192 | **10,310,876** | 7,907,328 | 18,210,012 |

The source candidate audit independently reports the CTAG/smallest-BSP column at [`m2-2026-10-21-capacity-candidate-audit.md`](m2-2026-10-21-capacity-candidate-audit.md#L43-L58). Largest-BSP values above were recomputed from the matching `retail-bsp-schema-2fba411b.json` records by taking `max(structure_bsps[].raw_bytes)` per campaign scenario; these are data-derived, not target load observations. The absolute campaign minimum is `d40 + d40_space` at 10,310,876 bytes (10,310,880 after separate 16-byte span alignment). The all-campaign required worst pair is `d20 + d20_hangar` at 18,564,628 bytes (18,564,640 after alignment). The current 6,291,456-byte `current_bsp` therefore misses even the most favorable pair by 4,019,420 bytes and the all-mission worst pair by 12,273,184 bytes. The 2 MiB tag cache itself is smaller than every compact campaign CTAG image. A larger contiguous address space is required unless a separately proven data-access design removes the need for those complete images to remain simultaneously pointer-addressable.

## Lower-bound arithmetic: the hardest map breaks the full committed budget

For d20, align the complete CTAG image and largest complete raw BSP independently to the binder's 16-byte allocation boundary:

```text
tag span = align16(10,046,996) = 10,047,008
BSP span = align16( 8,517,632) =  8,517,632
tag+BSP address span                 = 18,564,640
CE claims = ceil(18,564,640 / 32) * 4 = 2,320,580
```

Claims are sized from configured capacities, not just currently visited bytes, in the current CE implementation. A best-case (no allocator padding, no additional CE validation scratch) whole-machine lower bound is:

```text
PS2 kernel/system reservation                 1,572,864
current ELF LOAD file-backed bytes            2,086,532
current ELF .bss                               2,114,588
CE game-state binding                          3,428,352
d20 compact CTAG + largest complete raw BSP   18,564,640
CE tag/BSP claims bitmap                       2,320,580
                                               ----------
minimum already identified                    30,087,556 bytes
budget-v2 committed ceiling                    27,787,264 bytes
minimum deficit                                 2,300,292 bytes
```

The six rows count separate owners: file-backed ELF vs. NOBITS; CE game state vs. both; tag/BSP image vs. claims; and system/kernel reservation. This minimum omits the texture/lightmap cache, dynamic simulation, DMA/VIF/GS command buffers in EE RAM, streaming and decode scratch, checkpoints, audio staging, frame scratch, CE schema validation scratch beyond claims, parent-side BSP/render data, map source access state, canaries/alignment outside the spans, and any old/new-map coexistence. It also makes no allowance for the boot allocator's metadata or a margin. Consequently, **no redistribution among existing v2 EE regions can make the current full-image d20 requirement fit while also retaining the listed indispensable owners and the reserve**: it is already over the committed ceiling with those other owners assigned zero bytes. This is a lower-bound impossibility for *that whole-resident representation*, not a proof against a new lossless/pointer-safe representation or future measured code/data reductions.

For comparison, the unusually small d40 minimum pair yields:

```text
tag+BSP spans after alignment                  10,310,880
claims                                            1,288,860
kernel + ELF file bytes + .bss + game state     9,202,336
identified subtotal                             20,802,076
committed ceiling                               27,787,264
headroom before any other runtime owner          6,985,188
```

That 6,985,188 is not “free RAM”: it would still have to cover texture/lightmaps, simulation pools/effects/actors, DMA, streaming/decoding, audio/checkpoint/frame scratch, renderer/collision presentation needs, allocator gaps, and measured high-water/margin. More importantly it applies only to the smallest `d40_space` BSP, while `d40b` is 7,907,328 raw bytes and makes the complete pair 18,210,012 bytes. It is not a valid all-campaign proof.

The in-region check reaches the same conclusion for the minimum case: exact current `.bss` + CE game state + expanded d40 claims = 6,831,800 bytes, which exceeds the entire 6,815,744-byte `resident_gameplay` cap by 16,056 bytes before alignment or any additional resident allocations. That local overage might be solved by a real reassignment of claims or static owners, but it cannot fix the d20 aggregate deficit. Conversely, moving claims to another arena does not save aggregate bytes.

## What a repartition can and cannot currently claim

1. **Changing only `current_bsp` is not a valid whole-machine proposal.** Expanding it from 6,291,456 to 18,564,640 for d20 costs 12,273,184 bytes. The 5.5 MiB reserve remains forbidden, and the other region caps name real systems, not generic spare capacity. Even the more favorable 10,310,880 d40 spans cost 4,019,424 more than current `current_bsp` after alignment, while d40's real larger BSP remains 18,210,012 total.
2. **Carving arbitrary existing regions down to absorb the map has no evidence basis.** The logical memory map labels texture, dynamic simulation, DMA, streaming, audio, checkpoint, and scratch high-water as unknown (except UI-only host values); it does not prove those allocations can surrender bytes without losing in-scope features. Halo-CE campaign AI, scripts, effects, local players, collision, rendering, and sound remain in scope. GS eDRAM, IOP RAM, and SPU2 RAM are distinct physical stores and cannot satisfy CE EE pointers ([`config/hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L101-L105)).
3. **The frame/streaming arenas are not substitutes for steady map residency.** Bounded HP2 reading can remove encoded whole-section staging, but it cannot change the compact CTAG or raw BSP final-image lower bound. Current memory map reports only `1,550,484` bytes streaming and `275,491` frame-scratch high-water for a UI-only host fixture, not a campaign map; no gameplay map guest peak exists ([`config/hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L74-L86)).
4. **Pointer topology is a real constraint.** The current binder provides CE one tag-cache base/size and one BSP base/size; CE rebased tag and BSP structures are expected to use addressable contiguous ranges. Splitting a tag image over multiple unrelated spans or placing fragments into texture, dynamic, IOP, GS, or SPU2 memory is not compatible by assumption. It requires an explicit CE-facing address/lifetime contract, conversion of every affected dereference, and parity evidence. The allocator (`arena_alloc`) simply returns a single aligned range from one arena and does not provide scatter/gather pointers ([`engine/src/core/mem.c`](../../submodules/halo-ps2/engine/src/core/mem.c#L1-L33)); guarded v2 layout binds each named region as a disjoint contiguous span ([same file](../../submodules/halo-ps2/engine/src/core/mem.c#L103-L135)).
5. **Phase overlap could improve peaks only if it is physically real and semantically safe.** Arena bytes reused after a completed phase can reduce peak use, but only where lifetimes do not overlap and no CE/raw pointer survives. The current map switch has explicit old-map preservation/failure rules, so treating source staging, rollback, active BSP, tag data, or validation memory as mutually exclusive without transaction proof would be unsafe.

## Viable next decision paths (no capacity assignments proposed)

### Path A — lossless typed backing / paging with CE consumer conversion

Keep complete logical tag/BSP data as authoritative source bytes, but identify classes that need not be materialized as one resident raw pointer image at once. For every candidate range, record its schema identity, source offset/size/hash, all readers, pointer escape lifetime, concurrency/reentrancy, and what bytes the PS2 renderer actually needs in EE vs GS memory. Replace direct pointer assumptions with explicit handles/leases or bounded materialization windows only if the consumer audit says the range can safely be paged. Preserve original bytes and use the existing whole-image CE path as a parity oracle. This is an architectural change, not a memory-layout shuffle; it must retain campaign collision/pathfinding, AI/script/effect data, visual/material/surface queries, and sound behavior.

### Path B — phase sharing/repartition based on measured worst-case lifetimes

Instrument the exact combined runtime and build a phase-by-phase live-owner graph (boot, map preflight, tag materialization/validation, BSP activation, first rendered frame, gameplay high-water, BSP transition, map unload/retry, map switch). For every byte owner measure EE physical base, capacity, used/high, alignment, retention, and consumers; distinguish reserved capacity from actually necessary high-water. Then test a candidate shared-memory topology against d20's largest BSP, all encounter/script/object peaks, renderer upload and texture peaks, audio, four-player state, and failure/rollback paths. A proposed reduction is acceptable only with a producer/consumer contract, canaries, source-parity tests and guest evidence. Do not list a target size for a region until these measurements and its lifetime proof exist.

### Path C — converter compaction only after consumer proof

The retained schema/working-set outputs contain arithmetic projections (for example, animation-data externalization or compressed BSP-vertex externalization), but explicitly lack reader-lifetime, parity, destination, or pointer proof. Do not subtract those bytes from the lower bound today. A field can be moved out of the resident CE image only after all direct consumers are found in HCU/parent, a source-backed read/lease path is implemented, and CE-equivalent behavior is demonstrated. No truncation, approximate geometry, or dropping unknown fields is a compliant “repartition.”

## Measurements and tests required before approving any new layout

1. **Re-freeze a single current evidence tuple.** Rebuild/hash the current HCU closure, parent/HCU/halo-ps2 dirty source trees, toolchain/prefix/manifest, combined gameplay ELF, linker map/LOAD segments, package conversions, and all 24 map source identities. Regenerate matching-schema CTAG/BSP/package reports and reject stale report joins. The latest `2fba…` schema ELF and `72fe…` machine ELF are different artifacts and must remain separate.
2. **Audit every actual BSP per scenario, not only aggregate maxima.** Generate a compact CSV/JSON with map hash, scenario BSP identity/path, raw bytes, encoded CBSP bytes, selected spawn/zone/transition order, and all high-water consequences. The table above's max raw extent is a necessary all-mission test but must be tied to actual scenario paths and BSP switch behavior.
3. **Add exact capacity arithmetic tests.** On target ILP32, assert 16-byte span rounding, claims formula from the actual CE function, overflow behavior, and checked aggregate ownership against the committed ceiling. Include d40-small as a best-case lower bound and d20-largest (`d20_hangar`) as the mandatory adversarial campaign case; assert the unsolved current whole-image layout fails closed. Test no reserve reads/allocations.
4. **Instrument source and destination ownership.** Add allocator/provider instrumentation for exact EE base/end, owner, high-water and lifetime; identify duplicate counting across ELF `.bss`, compatibility malloc, game state, object pool, claims, CE tag/BSP providers, stream staging, renderer BSP/material packs, textures/lightmaps, DMA, animation, effects, sound and checkpoint. Prove all intervals disjoint when concurrent and record physical target/PCSX2 evidence with the same ELF hash.
5. **Run a d20 vertical memory/parity fixture before breadth claims.** Materialize the complete d20 CTAG and `d20_hangar` raw BSP through the proposed design; run CE schema/verifier, collision/material/path/cluster queries, scenario objects, campaign AI/script/effect/audio resource reads and parent render snapshot checks; compare bytes/results with source CE oracle. Then exercise all campaign BSP variants, 1–4 players, first frame, repeated transitions, unload and retry. A UI-only, host-overprovisioned, or map-package parse test is not a capacity pass.
6. **For paging/streaming, test escaped-pointer safety and I/O failure.** Enumerate pointer-escape sites; test overlapping pins, cache pressure, reads split across chunk boundaries, short-read/EOF, corrupt digest/CRC, missing device, simultaneous animation samples and asynchronous/runtime reads. Show that eviction cannot invalidate any live CE pointer and that failed preflight leaves old map state intact (or, after destructive unload, returns a valid safe state and retries deterministically).
7. **For phase sharing, prove non-overlap empirically and structurally.** Inject failures at every phase and assert no consumer observes reclaimed storage; run canaries under worst traffic and use hardware/EE cycle evidence for streaming stalls. Preserve the reserve and ensure all required effects/AI/script/render/audio duties still pass.

## Recommendation for the plan

Treat this report as a Step 8 gate input, not as a new allocation plan. Update Step 8 to state explicitly that all ten campaign missions' **largest referenced complete BSPs** are part of the capacity set; the earlier smallest-BSP table is only a favorable rejection bound. Make the d20 complete CTAG + `d20_hangar` pair the adversarial whole-image test, retain d40-small as an arithmetic sanity bound, and require all remaining engine owners and the untouched reserve in the same physical ledger. Step 9's streamed-materializer work should continue as a loader correctness improvement, but it cannot be presented as solving this lower-bound residency gap by itself. A compliant capacity design is still open; do not hard-code new region capacities or reopen reserve bytes based on this report.

## Verification

This report-only task made no runtime, plan, configuration, or submodule edits. All calculated map rows were derived from the retained matching `2fba…` report pair, and the current ELF numbers from its matching `result.json`. `git diff --check` is the only requested test for this report-only assignment and must be run after adding the report. The compact-image and maximum-BSP arithmetic is static evidence only; there is no d20 guest load, rendered-scene, or gameplay-parity evidence attached.
