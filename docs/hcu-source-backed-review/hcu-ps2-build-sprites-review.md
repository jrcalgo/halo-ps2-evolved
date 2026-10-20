# M0 source review: CE sprite-batch construction boundary

## Disposition

`build_sprites_begin`, `build_sprite`, and `build_sprites_end` remain pending PS2 render-adapter ownership. Their only rooted callers in this selected closure are antenna-chain and glow-particle widget rendering (`antenna.c` and `glow.c`), but the functions form a stateful geometry-buffer protocol. They are not safe no-ops, nor are they ordinary gameplay simulation methods.

## Source trace

- `build_sprites_begin` (`source/render/render_sprite.c:204-229`) validates/reset-initializes a caller-owned batch, stores bitmap/shader/flags, initializes group/sprite counts and centroid, sets the valid bit, and may enter viewmodel projection when the first-person bit is set. The two current rooted caller families pass flags `0`; do not generalize that local fact to unrooted or future callers.
- `build_sprite` (`render_sprite.c:342-585`) selects/adds bitmap groups, transforms and fades billboard geometry, enforces per-batch sprite limits, updates centroid/counts, allocates and locks dynamic vertex buffers, and writes quad vertices. The antenna caller builds a billboard strip from chain vertices (`source/objects/widgets/antenna.c:490-531`); glow builds one sprite per linked glow particle (`source/objects/widgets/glow.c:552-575`). Both use source shader blend modes and tag bitmap/sequence indices.
- `build_sprites_end` (`render_sprite.c:231-294`) calculates/transforms the centroid, unlocks each live dynamic buffer, submits screen-space or unlit world/viewspace geometry with first-person flags, deletes buffers, clears batch-valid, and restores viewmodel projection if entered. No-op behavior would leave buffer ownership unresolved and drop the widget visuals.

## Edge conditions and PS2 budget

The source computes `one_over_sprite_count = 1.f / data->sprite_count` before it knows whether any group contains sprites. The antenna loop can skip all sprites when each vertex's `sprite_scale` is zero or its falloff is nonpositive; glow may receive an empty particle chain. The source then multiplies the zero centroid by the reciprocal and later may have no group to submit. The PS2 adapter should decide whether to preserve this harmless IEEE-754 diagnostic artifact or guard empty batches, and test empty and mixed batches without consuming a render buffer. It also needs fixed-pool/high-water behavior for dynamic vertex storage; Xbox lock/unlock/delete ownership cannot be replaced by unconstrained allocation in a map-loaded EE runtime.

## Required acceptance evidence

Keep all three pending until the PS2 renderer bridge has a bounded batch contract and tests for: empty batch; one sprite; maximum-count and overflow; multiple texture groups; antenna chain with zero and nonzero sprites; glow with no/live particles; alpha/additive shader selection; expected vertex/index counts; unlock/delete on every path; first-person projection begin/end ordering; and equivalent batch output across render schedules. The regression test added with this report only anchors this source review and pending disposition.
