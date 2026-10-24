# Step 8 production binder and map/texture ownership check

Status: host ILP32 ownership fixture passed; no production memory or map-admission code changed. This is not EE or PCSX2 qualification.

## Finding

The default production layout is insufficient for the opt-in pad-8 candidate tag+BSP split even though the CE provider can report itself ready. With `current_bsp=6,291,456` bytes and `tag_cache=4,477,120`, the actual `hcu_memory_bind_parent_v2()` path gives the BSP provider only `1,814,336` bytes. The pad-8 candidate requires `1,993,712`, a 179,376-byte shortfall. The natural all-map minimum from the tail-inclusive candidate report is 1,993,704 bytes, still 179,368 bytes short. In the default guarded layout, texture begins 16 bytes beyond the current BSP region, so the three candidate spans are not one contiguous candidate owner.

There is already an opt-in candidate recarve in `src/stream/hcu_main.c:192-228`, called only when `HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC` is defined at `src/stream/hcu_main.c:327-333`. It repartitions the same 10 MiB BSP+texture total into a 6,470,832-byte map region and 4,014,928-byte texture region, moving the boundary canary to the combined end. This pad-8 profile allocates 8 bytes more to BSP than the tail-inclusive natural minimum (1,993,704) and 8 bytes less to texture (4,014,936). The real parent binder then exposes the exact pad-8 candidate tag/BSP/texture capacities as adjacent views. No additional production carve change is warranted by this test alone: the candidate is diagnostic-only, map admission remains closed, and target texture residency/render behavior remains unqualified.

This is adjacent fixed spans, not one shared runtime allocation cursor. The CE port intentionally consumes separate tag, BSP, and texture-provider interfaces. The useful ownership invariant is therefore: one backing interval is partitioned into nonoverlapping adjacent views, while CE's tag and BSP stores retain their own semantic bounds. `src/stream/hcu_map_service.c:529-553` uses the streaming map-owner for HMAP/CRNG/CBIX preflight and passes the tag-cache size to CTAG validation; it does not own or allocate the renderer's texture data. CE's `ps2_cache.c:322-340` obtains its BSP base/capacity from the BSP provider. The selected PS2 CE sound/cache adapter is `port/ps2/src/ps2_sound_cache.c`, not the excluded Xbox LRU texture cache.

## Correct texture ownership interpretation

Do not infer a 23 MiB PS2 requirement from `HALO_PORT_TEXTURE_CACHE_PAGE_COUNT=0x580` in `halo_ps2_limits.h:24-25`. The HCU PS2 manifest explicitly excludes `source/cache/xbox_texture_cache.c` and selects `port/ps2/src/ps2_sound_cache.c` (`port.json:20-40, 62-67`). The PS2 adapter's `_texture_cache_bitmap_get_hardware_format()` returns the tag bitmap as a ready token (`ps2_sound_cache.c:51-57`); its `texture_cache_open/flush/close` functions are empty or lifecycle-only (`:222-235`). The Xbox page inventory and `XPhysicalProtect` path are therefore not evidence of PS2 texture backing requirements.

The `texture_cache` region at issue is used by the retained halo-ps2 GS texture-pack/cache path, while the candidate all-map host fixture loads converted `TEXS`, `LMn`, and selected `OTEX` resources into an adjacent owner and verifies capacity/high-water. That host fixture is useful coexistence evidence but does not establish that the actual EE recarve survives GS uploads, texture eviction/pins, animation/object asset overlap, or frame DMA. Continue using the measured PS2 owner and renderer tests; do not use the excluded Xbox LRU values as sizing authority.

## Evidence and reproduction

Run:

```sh
python3 tools/test_hcu_mp_production_bind_capacity.py
```

The runner compiles and executes the real parent binder (`src/stream/hcu_memory_bind.c`), HCU PS2 provider (`port/ps2/src/ps2_memory.c`), and halo-ps2 arena implementation. It runs both the ordinary guarded layout and the existing recarved candidate geometry, then checks source selection so the excluded Xbox texture cache cannot be mistaken for the PS2 owner. In this environment, native ILP32 execution may require the unsandboxed test path if the sandbox exits with SIGSYS.

The retained run manifest is `build/mp-production-binder-capacity-1792695756835008376/manifest.json` (SHA-256 `fbeb5a800c74a43f3efb4a67d006df02c27e859d9327f3116676df11237d26af`). Its runtime output records:

```text
production-binder-default tag=4477120 bsp=1814336 required_bsp=1993712 bsp_shortfall=179376 texture=4194304 gap=16 ready=1 candidate_fit=0
production-binder-recarved tag=4477120 bsp=1993712 map=6470832 texture=4014928 total=10485760 unified_adjacent=1 parent_bytes_unchanged=1 guards=1 ready=1
```

`ready=1` in the first row demonstrates why startup readiness cannot replace per-profile capacity assertions. The second row proves only the binder-level recarve arithmetic and canary placement, not that all 13 maps pass loading, all renderer assets remain resident, or textures reach the GS.

## Recommendation / next gate

1. Keep the default profile and ordinary map admission unchanged. Keep the candidate recarve under its explicit diagnostic macro.
2. Before promoting the candidate profile, connect this owner to the real halo-ps2 render-cache path and measure cache pages, pinning, eviction/reload, upload ordering, mip/lightmap/CLUT behavior, and guard integrity. Do not port or size from the excluded Xbox texture LRU; Halo-64 is only an architectural comparator, not PS2 capacity evidence.
3. Then use the recarved layout through the real map preflight, CTAG mount, BSP query/render-resource selection, renderer cache staging, and failure/reload flows on the required multiplayer map corpus. Require high-water and guard results at target/PCSX2; the current binder test is not that evidence.
4. Only after those results should the capacity profile/API be promoted out of the diagnostic path. Any later change should continue to partition the existing 10 MiB; no reserve or other region is authorized by this result.

## Source-backed comparison note

Halo-64 may offer architectural examples for separating game data from platform rendering, but its N64 memory figures and cache reductions are not PS2 sizing evidence. This finding uses the PS2 budget/layout and current HCU source; it does not adopt Halo-64's 8 MiB constraints.
