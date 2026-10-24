# Step 8: game-state routing and exact claims alternatives

This report audits two concrete capacity proposals against the current source. Neither proposal currently closes campaign admission. The governing budget and reserve remain unchanged.

## Game-state allocations cannot be rerouted by name alone

`game_state_malloc()` returns `base_address + cpu_allocation_size`, advances one contiguous allocation cursor, and incorporates the allocation size into the allocation checksum ([game_state.c:549](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L549)). The wrappers for data arrays, object memory pools, and LRU caches all use that allocator ([game_state.c:860](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L860), [game_state.c:943](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L943)). The existing 1 MiB object pool is nested inside the 3,428,352-byte game-state binding ([objects.c:1050](../../submodules/halo-ce-universal/source/objects/objects.c#L1050), [PS2 limits:18](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L18)).

That contiguity is observable behavior: `game_state_image_contains()` rejects addresses outside the one game-state span; image pointers are calculated by subtracting the live base, and image acceptance copies the complete `GAME_STATE_SIZE` back over the live base ([game_state.c:650](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L650), [game_state.c:825](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L825)). A name-based arena branch would invalidate checkpoint validation and restoration unless those contracts change with it. Keeping the original complete allocation while routing another copy buys zero aggregate bytes.

The current parent binds the whole dynamic arena to the compatibility allocator, so it is not an unused secondary object pool ([hcu_memory_bind.c:60](../../src/stream/hcu_memory_bind.c#L60)). The allocator is a bounded bump store whose `free` does not reclaim individual allocations ([ps2_memory.c:300](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L300)). Carving a typed object store from it must reduce the compatibility span by precisely the same amount and prove all remaining compatibility allocations fit; the two cannot both own the same bytes.

An eventual split can preserve identity using an explicit, versioned list of stable game-state segments, with per-segment bounds and snapshot translation. The first eligible experiment is the object pool alone: export its allocation record, give it one caller-owned dynamic segment, keep pointers stable throughout a map, and implement segment-aware image validation/copy for save and revert. Do not generalize routing by display name; use an enum owner attached to the allocating call site. The upper bound for this first experiment is approximately 1 MiB of **resident-region relief**, offset by approximately 1 MiB less compatibility capacity. It is zero whole-machine savings. Larger splits require actual per-owner allocation sizes and checkpoint coverage; the full 3.43 MiB cannot fit within the 2.62 MiB dynamic region even with compatibility usage zero.

## Claims have a replaceable representation, but are not dead after initial load

The validator implements exact byte-set membership. `claim()` rejects any overlap and otherwise marks bytes, including a prefix before it detects a later overlap; its aligned-word branch checks all 32 bytes before claiming any byte in that word, which limits the failure prefix. `unclaim()` clears a range ([tag_validate.c:477](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L477)). `tag_validate_any_claimed()` is also used by the model-index validator ([tag_schema_models.c:443](../../submodules/halo-ce-universal/port/linux/game/tag_schema_models.c#L443)). BSP activation clears only the BSP domain and deliberately preserves tag claims, including names ([tag_validate.c:1446](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L1446)). Therefore releasing all claims after CTAG validation breaks later BSP validation; a replacement must support the same union, overlap, range-clear, and membership behavior.

An exact sorted disjoint interval representation is a valid candidate: retain half-open byte ranges with adjacent ranges merged; query via binary search; split/remove intervals when clearing the BSP domain. Each interval needs at least two 32-bit offsets, eight bytes total, plus metadata and update workspace. A record-count bound and a checked capacity failure are mandatory. Arbitrary malformed input can alternate occupied/unoccupied bytes, so the worst-case interval representation can be larger than the bitmap. It must fail atomically and safely if its bounded table fills, and the required retail corpus must demonstrate a sufficient bound. Four-byte-granularity bitmaps are not equivalent because names and opaque data may occupy unaligned bytes.

Concrete next implementation: add a host diagnostic shadow interval set beside the existing bitmap. Replay every claim, clear and membership query from all 24 maps and 82 BSPs, compare every return and every range query, and record maximum live merged intervals, insertion shifts and scan cost. Preserve prefix mutation on failed claims if differential tests establish that callers observe it; otherwise explicitly prove failed validation resets all state before changing semantics. With a table of N intervals the exact replacement costs `8*N + metadata + workspace`; claiming any saving before measuring N is premature. Then implement the same bounded representation behind `HALO_PS2`, test overlap-at-first/middle/end, zero length, overflow, adjacent intervals, BSP clearing, stale-map rejection, exhaustion, and failure rollback. Target-cycle and physical-owner evidence remain separate gates.

## Maximum savings and campaign consequences

The current full-image D20 lower bound is 30,087,556 bytes against 27,787,264 committed bytes, excluding texture, DMA, audio, streaming, scratch and other indispensable owners ([repartition review](m2-2026-10-21-budget-repartition-review.md)). Its claims are 2,320,580 bytes. Even the impossible ideal of **zero-byte claims** lowers that subtotal only to 27,766,976 bytes: 20,288 bytes remain for all omitted owners. An actual interval table reduces that margin further. Moving the object pool does not alter this arithmetic.

For every campaign map, relocation of game-state ownership saves zero aggregate bytes; replacing claims can save at most `ceil(align16(tag_bytes)+align16(max_bsp_bytes))/32)*4`, less the replacement table. The maximum raw credits, before replacement-store subtraction, are:

| Map | Full tag + largest BSP, aligned | Maximum claims removal |
|---|---:|---:|
| a10 | 18,191,104 | 2,273,888 |
| a30 | 16,863,248 | 2,107,908 |
| a50 | 18,334,592 | 2,291,824 |
| b30 | 16,876,976 | 2,109,624 |
| b40 | 17,620,272 | 2,202,536 |
| c10 | 17,541,968 | 2,192,748 |
| c20 | 15,307,424 | 1,913,428 |
| c40 | 17,504,432 | 2,188,056 |
| d20 | 18,564,640 | 2,320,580 |
| d40 | 18,210,016 | 2,276,252 |

These are upper bounds, not accepted savings or new budget assignments. The complete per-map owner deficit still requires actual renderer/resource/animation stores and target high-water; no number for those can be inferred from these two changes. The claims experiment is worthwhile because it can materially reduce validation overhead, but a separate lossless data-residency change remains necessary for campaign fit.

Halo-64 provides a useful comparative warning: its renderer notes retain lightmap sampling, camera/frame state and first-person marker advancement despite replacing drawing ([N64 notes:35](../../submodules/halo-64/port/n64/NOTES.md#L35)). Its reduced pools and feature omissions supply no PS2 capacity credit. This audit uses source contracts; shipped-artifact reverse engineering is not needed for these allocator and validator questions.
