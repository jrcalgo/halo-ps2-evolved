# CE dynamic raster geometry roots

Status: all nine dynamic-buffer/draw roots remain pending. They must be implemented as bounded PS2 renderer services, not empty link stubs.

## Source trace

The rooted dynamic API family is `rasterizer_dynamic_triangles_{new,lock,unlock,delete}`, `rasterizer_dynamic_vertices_{new,lock,unlock,delete}`, and `rasterizer_dynamic_unlit_geometry_draw`. The Xbox reference uses per-frame typed vertex groups and triangle/index spans: `rasterizer_dynamic_geometry_begin` resets counts/locks for each view, and `new` validates requested counts and returns `NONE` on exhausted capacity (`source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c:515-570,615-660,755-812`). Lock resolves a buffer index to writable storage, unlock closes the write window, and draw submits that storage with the caller's material/transform/state; the Xbox `delete` methods intentionally do not individually reclaim frame buffers (`749-753,845-922,973-977`). This is a bounded frame arena protocol, not general-purpose heap allocation.

The rooted callers show the geometry is not optional debug output:

- `source/objects/widgets/flags.c:751-959` allocates vertex and triangle buffers, fills cloth geometry, unlocks, submits, and deletes per draw.
- `source/objects/widgets/lightning.c:346-462` allocates/writes/unlocks/submits/deletes unlit geometry.
- `source/game/game_engine_king.c`'s `render_dynamic_quad` path and the flag path share the dynamic vertex/triangle API.
- The same renderer contract is used by contrails, sprites, world surface selection, and other non-rooted consumers; e.g. `source/render/render_contrails.c:140-158,436-448` and `source/structures/structure_render.c:438-465,1127`.

The parent PS2 renderer owns GS/VU1/DMA, while CE owns which geometry to produce. Each call therefore needs an adapter crossing from CE's typed CPU geometry to bounded parent buffers and a render submission. Returning `NONE`, a null lock pointer, or dropping draw is not a harmless visual fallback for all consumers: flag cloth and lightning disappear, and downstream buffer/index assumptions can change. Source behavior also establishes key semantics: per-view frame reset, capacity rejection, typed vertex-size selection, lock/unlock lifetime, and deferred buffer reuse. Do not copy Xbox maxima blindly; size and measure PS2 frame arenas under the existing budget and allow deterministic exhaustion.

## Acceptance required before approval

1. Implement a bounded dynamic geometry arena in the PS2 renderer with per-frame/per-view reset and explicit max vertices/triangles/buffer descriptors.
2. Preserve CE index conventions, vertex-type stride/layout, lock/unlock validity, invalid-index handling, and `NONE` on exhausted capacity; do not retain caller pointers across frame reset.
3. Prove the arena's high-water and overflow path on EE/PCSX2 and reconcile its bytes to the render memory region without double-counting GS storage.
4. Add host tests for zero-size requests, capacity exact-fit/overflow, reset across split-screen views, lock/unlock order, and draw submission; add integrated Blood Gulch flag-cloth and lightning fixtures. Rendering acceptance also requires visible capture, not only a clean link.
5. Keep these nine rows pending until the target parent adapter and fixtures exist. The report records CE semantics and risk, not an implementation approval.

## Sources

- Rooted identities: `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
- `submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c:515-570,615-753,755-977`
- `submodules/halo-ce-universal/source/objects/widgets/flags.c:751-959`
- `submodules/halo-ce-universal/source/objects/widgets/lightning.c:346-462`
- `submodules/halo-ce-universal/source/render/render_contrails.c:140-158,436-448`
- `submodules/halo-ce-universal/source/structures/structure_render.c:438-465,1127`
