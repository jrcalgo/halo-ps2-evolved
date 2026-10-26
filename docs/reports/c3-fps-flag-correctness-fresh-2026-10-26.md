# C3 FPS flag render-correctness audit — 2026-10-26

## Scope and result

Read-only audit of the four switches in the archived C3 one-view 14.96 → 29.97 FPS comparison: `HCU_C3_OBJECT_FASTPATH`, `HCU_C3_OBJECT_VIEW_CACHE`, `HCU_C3_BINDING_SEAL`, and `HCU_C3_SNAPSHOT_INDEX`. I inspected the archived source snapshot and captures, current source paths, and existing reports. I did not edit source, run a build, send game input, or close a game.

The severe black/cropped image difference belongs to the rejected r1 capture matrix. It is not evidence that the four flags changed the rendered frame: r1 records different window origins for the pair, and the report itself rejects its captures for position-dependent black crops. The authoritative r2 one-view baseline and optimized PNGs have the same SHA-256 (`704368d3f22b4b6641d67bfc85cbdd771e09847c08532a5d8efcb202eb4e0947`) and are pixel-identical. The r2 report also records exact RGB parity for all four view counts. That match is specific to the archived Blood Gulch workload; it does not prove every camera, asset, or pressured-chain state.

One latent correctness issue remains in the view setup cache. The view cache marks setup as emitted even when its chain reservation fails. It must track the actual result of that reservation before enabling the cache in a production preset.

## Archived image mismatch: r1 capture qualification

`docs/reports/c3-multiview-fps-ab-2026-10-25.md` states that r1 was rejected because window placement varied and its XWD captures had position-dependent black crops; it identifies r2 as authoritative. The per-run `active.json` records baseline-v1's capture window at `[40, 40, 640, 480]` and optimized-v1 at `[960, 482, 640, 480]`. Their tick-601 PNG difference covers `(199, 0, 640, 480)`, consistent with the visible black crop in optimized-v1. Both are 640×480 output files, but equal dimensions do not repair the differing desktop capture origins.

In r2, baseline-v1 and optimized-v1 tick-601 images are byte-identical. The archived r2 report's one-view rate remains 14.959 → 29.968 FPS with exact RGB, canonical snapshot, and native bitmap queue parity. Its visually oversized first-person weapon is present in both frames; that pre-existing image defect is not evidence of a new optimization regression. The current c258 build and current first-person changes are newer than the r2 source pins, so the archived FPS and image result should not be projected onto that ELF without a matched run.

## Flag-by-flag behavior

| Flag | What the source changes | Rendering assessment | Action |
|---|---|---|---|
| `HCU_C3_OBJECT_FASTPATH` | Replaces a zeroed 1,024-entry `object_table_t` per single-object submission with one stack `object_t`; `s_objr.span` supplies that one object. The same choice is applied to first-person submissions. | The object itself is fully zeroed and the draw fields are initialized before the call. The renderer gives a non-null span precedence over the table. This removes the large clear without changing the object's model, pose callback, material lookup, LOD, culling, or batch path. No direct rendering defect found. | Keep eligible after testing the single-object span path against table output; r2 pixel parity is supporting evidence for its workload. |
| `HCU_C3_OBJECT_VIEW_CACHE` | Emits the VU model setup once at the start of a view and reuses camera basis and horizontal-FOV scalar across repeated object submissions in that view. The cache key checks chain, camera, clip, frustum, and render-options pointer identity. It does not cache a viewport/scissor or skip BSP/GS viewport setup. | The cache's normal success path is view-scoped and retains per-view camera work. However, `obj_render_begin_view()` returns `void`; it calls `emit_model_setup()`, whose `chain_cnt()` failure simply returns, then sets `s_view.valid = 1`. The parent caller then unconditionally sets `s_objr.setup_emitted = 1`. A failed reservation can therefore be treated as a successful setup and later object calls may emit model batches without the required VU constants. `chain_cnt()` refusals in general scope count as deferrals and need not set `overflow`, so the overflow counter alone will miss this case. This is a real latent risk, not the established cause of the r1 crop. | Fix success propagation before keeping this flag on. Do not claim the cache is safe under chain pressure until a failure-path fixture covers it. |
| `HCU_C3_BINDING_SEAL` | Selects `hcu_bitmap_frame_owner_bind_immutable`; the bind computes a digest once and immutable mode skips the per-frame O(binding-count) digest. | This does not alter draw commands. Current binding code still checks profile scalars and pointers, generation, queue state, producer descriptor, readers, dispatch state, and DMA/fence gates. `hcu_main.c` verifies binding metadata before binding and documents its persistent map lifetime as immutable through detach/unbind. If the caller breaks that lifetime contract, the strict API would detect byte changes and the immutable API intentionally would not. | Safe under the documented immutable metadata lifetime; retain strict bind for mutable bindings. Not a plausible source of black geometry under the current lifecycle. |
| `HCU_C3_SNAPSHOT_INDEX` | Adds a 1,024-entry open-addressed index in the frame-scratch owner. It is cleared at bind and on every write; intern uses `{index, generation}` to recognize duplicates, and the legacy branch linearly checks the same pair. | This accelerates CE publication lookup before rendering. It does not change the published snapshot format or renderer draw path. Lookup by datum index has the same first-match semantics as the pre-existing linear lookup. Required storage grows by 8 KiB and the owner-size assertion accounts for it. No direct visual defect found. | Keep if the existing collision, duplicate, overflow, scratch-bound, and canonical-snapshot fixtures pass. |

The four-flag A/B is a bundle, so it cannot assign a causal FPS share to a single switch. The retained combined one-view profile reports object/FX mean 21.165 → 2.594 ms, view-build mean 26.338 → 7.765 ms, and binding-hash work 11.382 → 0 ms. These measurements support the combined performance result, not independent estimates for each optimization. The archived isolated runs are explicitly directional only.

## View-cache correction and targeted verification

Use a success-returning `emit_model_setup()` that returns false when `chain_cnt()` cannot reserve its full packet and true only after writing it. Make `obj_render_begin_view()` return that status and publish `s_view` fields/`valid` only after successful emission. The parent should assign `setup_emitted` from that return value instead of setting it unconditionally. In `obj_render_pass()`, if setup is still absent, retry it and skip dependent object/FP model emission if reservation still fails. Count the refusal in an observable failure/space counter. This keeps the successful fast path and fails closed when its prerequisites are missing.

Targeted host-fixture cases before re-enabling the flag:

1. Give the chain one qword less than the model setup reservation requires. Assert setup fails, no valid cache or `setup_emitted` is published, and no dependent model packets are emitted.
2. Reset/replenish the chain, assert setup succeeds, then call the object pass repeatedly with the same view identity. Assert setup is emitted once and output packets match the uncached path.
3. Change one cache identity component at a time (chain, camera, clip, frustum, options). Assert the old basis/setup cache is not reused.
4. Exercise the camera-local first-person context after a world-view pass and verify it gets its own successful model setup before viewmodel packets.

For game-level acceptance, rerun a pinned one-view Blood Gulch A/B on the current post-first-person-fix source, with the same package, PCSX2 settings, window rectangle, workload, and matched tick. Retain full RGB captures and per-view diffs, canonical snapshots, bitmap queues, object/FP counters, chain deferred/overflow/refusal counts, and frame FPS. The first-person gun/hands and a Warthog should be visibly checked in the captured view; do not use the rejected r1 image as parity evidence.

## Sources inspected

- [Controlled FPS report](c3-multiview-fps-ab-2026-10-25.md) and `build/c3/perf/multiview-ab-20261025-r1/report.md` / `report.json`.
- `build/c3/perf/multiview-ab-20261025-r1/runs/{01-baseline-v1,05-optimized-v1}/active.json` and tick-601 PNGs; `build/c3/perf/multiview-ab-20261025-r2/runs/{01-baseline-v1,05-optimized-v1}/tick-601.png`.
- Archived r2 source snapshot under `build/c3/perf/multiview-ab-20261025-r2/optimized-v1/source-snapshot/`.
- Current `src/stream/hcu_render_objects.c`, `src/stream/hcu_bitmap_frame.c`, `src/stream/hcu_main.c`, `src/stream/hcu_snapshot_bank.c/.h`, and `submodules/halo-ps2/engine/src/render/obj_render.c`, `obj_render.h`, `chain.c`.
- `docs/reports/c3-change-impact-fresh-2026-10-26.md` for the current ELF/source-pin boundary and existing c258/v9 runtime evidence.
