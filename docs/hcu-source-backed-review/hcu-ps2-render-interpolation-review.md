# M0 render interpolation and camera-state review

This review distinguishes two facts: interpolation is optional presentation
state, but its API boundary is not uniformly draw-only. Some native-port
fallbacks must be preserved for the PS2 camera/render snapshot to remain valid.

The PS2 closure currently emits empty/zero placeholders for nine rooted
symbols: `halo_interpolation_enabled`, `render_fov_vertical`, and the seven
`render_interpolation_*` functions (camera, fraction, frame begin/end, object
node matrices, reset, tick). CE callsites are present in `main.c`,
`game_time.c`, `objects.c`, and `antenna.c`; native-port ownership lives in
`port/linux/game/render_interpolation.c` and `port/linux/game/view_fov.c`.

## State and caller findings

- `main_game_render` obtains a valid `observer_result` from
  `observer_get_camera`, then replaces it with
  `render_interpolation_camera(...)` before `set_window_camera_values`.
  Native disabled-interpolation behavior returns the original observer.
  The PS2 pointer stub returns `NULL`, so the observer is discarded and camera
  values are not written for that view. This is a required state/fallback
  contract, not safely omitted drawing.
- `render_fov_vertical` writes the view's vertical projection angle. Native
  default config returns the native field of view; a generated zero float
  instead makes the camera projection invalid/collapsed. The PS2 adapter needs
  a defined identity behavior even if custom FOV settings are excluded.
- `object_get_node_matrices` and `object_get_node_matrix` use a `NULL`
  interpolation result to select the authoritative CE object datum matrices.
  That fallback can be correct with interpolation disabled, but must remain
  explicit when a parent render snapshot is introduced; it cannot expose a
  stale or partial snapshot.
- `render_interpolation_fraction` returns the active fraction or exactly 1.0
  when interpolation is inactive. Its antenna caller uses that value to build
  presentation geometry; generated zero is not proven equivalent.
- Frame begin/end manage an interpolation-active flag and fraction. Tick
  advances previous/latest object/camera records at the 30 Hz simulation
  boundary; reset invalidates records on map transition because object indices
  are reused. The native implementation allocates with `calloc`/`realloc`,
  which cannot be transplanted unmodified into the PS2 no-post-map-malloc
  model. These APIs therefore need an explicitly selected disabled/fallback
  contract or a bounded snapshot implementation, not opportunistic stubs.
- `halo_interpolation_enabled` is a native config function, defaulting from
  `display.interpolation`; neither desktop config nor networking interpolation
  is part of the current PS2 M1 profile. A PS2 policy must define it and ensure
  caller ordering and frame/tick invariants.

Keep the nine ledger rows pending until the machine adapter has a documented
non-interpolated baseline (identity observer/FOV, fraction 1.0, NULL node
snapshot with CE datum fallback, and stable frame/tick/reset semantics) or a
bounded interpolation pool with render-schedule tests. Camera validity should
be tested separately from actual GS scene rendering. This report does not
recommend copying the native heap-backed interpolation implementation.

Regression anchor:
`tests/test_hcu_external_review.py::test_render_interpolation_placeholders_are_not_camera_or_state_safe`.
