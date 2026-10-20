# M0 rooted rasterizer frame/map boundary review

This pass covers twelve rooted PS2 rasterizer APIs: initialize/dispose,
map initialize/dispose, frame begin/update/end, window(s) begin/end, and
present. The source drawing backend is not ported, but the CE wrappers expose
state and lifecycle that the PS2 snapshot/GS owner must explicitly replace.

`rasterizer_initialize` in retail allocates
`global_rasterizer_model_ambient_reflection_tint` from game-state memory and
then calls the backend initializer. The current `port/ps2/src/ps2_edge.c`
initializer sets viewport and clip defaults only. Its code is valuable M1 CPU
camera state, but is not a full owner for the CE allocation or parent GS init.

`rasterizer_initialize_for_new_map` in
`source/rasterizer/common/rasterizer_common.c` binds
`global_rasterizer_data` into the active scenario's rasterizer-data tag block,
resets lights, flushes text cache, initializes screen effects, resets near
clip, and clears the ambient-reflection tint. The paired
`rasterizer_dispose_from_old_map` disposes screen effects, flushes the cache,
and clears the tag pointer. These are map/tag lifetime operations, not just
draw calls. Full `rasterizer_dispose` similarly releases device resources;
the PS2 parent must own what it initializes.

`rasterizer_frame_update` writes `global_frame_parameters.dt`. The retail
frame-begin wrapper restores clip defaults and applies debug render switches
before entering the backend. Main-loop order is frame-begin, windows-begin,
one or more window-begin/end pairs, windows-end, frame-end, then present.
Each window payload contains camera, frustum, viewport, fog, local-player,
target, and mirror state. That information must reach a render snapshot even
when GS drawing occurs elsewhere. End/present boundaries also need a defined
DMA completion/publication contract. `rasterizer_present` carries optional
screenshot parameters in addition to presentation.

Keep all twelve rows pending until the machine interface defines and tests
those ownership contracts. Follow-up should specifically prove tint allocation
ownership, tag-pointer invalidation on map unload, dt and clip propagation,
camera/frustum/fog payloads for 1–4 players, nesting/reset between windows,
frame publish/GS DMA ordering, and screenshot policy. Existing bounds tests
cover only viewport math; they do not qualify the full CE callback boundary.

Regression anchor:
`tests/test_hcu_external_review.py::test_rasterizer_frame_and_map_boundary_remains_pending`.
