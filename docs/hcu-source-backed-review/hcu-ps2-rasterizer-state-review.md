# M0 rasterizer state-global and script API review

This review covers five rooted surfaces: the CE `rasterizer_globals` datum,
`global_rasterizer_model_ambient_reflection_tint`, and the
`rasterizer_lights_reset_for_new_map`, `rasterizer_model_ambient_reflection_tint`,
and `rasterizer_set_near_clip_distance` functions.

The source shows why broad rasterizer stubbing is unsafe even before drawing is
connected. `rasterizer_globals` is initialized with meaningful default clip
distances and drawing flags and is read from `main.c`, objective widgets,
lightning, and HaloScript registrations. The PS2 bounds adapter fills only the
screen/frame bounds, clip defaults, and initialized bit; every other CE field
must be classified by consumer before a zero-filled global can be accepted.

The global ambient-reflection tint pointer is allocated from game-state memory
by retail `rasterizer_initialize`; `rasterizer_initialize_for_new_map` and
`cinematic_stop` clear it. HaloScript writes its four channels through
`rasterizer_model_ambient_reflection_tint`, which the Xbox model renderer reads
when shading reflections. The PS2 initializer does not allocate this pointer,
so the current null/no-storage behavior silently drops that state. Whether the
parent GS snapshot supports it or scripts may safely omit it remains undecided.

`rasterizer_set_near_clip_distance` updates the active cinematic
screen-effect datum, and the getter later chooses between that override and
retail defaults. Cinematic stop resets it, while HaloScript can set it.
`rasterizer_lights_reset_for_new_map` clears lens-flare occlusion histories and
their active count. These are presentation-side state owners, but can influence
the next map/frame if a PS2 adapter consumes them; they are not permission to
remove all CE camera/light script state.

Keep all five pending. Close only after enumerating every `rasterizer_globals`
consumer, assigning the tint and near-clip state to either a PS2 snapshot or a
source-proven excluded feature, and testing reset semantics across map and
cinematic transitions. The report intentionally does not approve rendering
functions or claim visual parity.

Regression anchor:
`tests/test_hcu_external_review.py::test_rasterizer_state_globals_and_script_controls_remain_pending`.
