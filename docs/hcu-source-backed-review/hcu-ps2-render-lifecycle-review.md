# M0 rooted render lifecycle review

Five rooted calls are treated here: `render_initialize`,
`render_initialize_for_new_map`, `render_dispose_from_old_map`,
`render_dispose`, and the script-facing `render_effects`.

The first four are not interchangeable with `render_frame`/GS drawing. The
retail `source/render/render.c` lifecycle chain calls
`render_objects_initialize*`/`render_objects_dispose*`. Startup allocates
`cached_object_render_states` with `game_state_data_new` and asserts success;
map initialization marks the data array valid, old-map disposal invalidates
it, and final disposal clears its pointer. The cache is consumed by
`object_get_cached_render_state` in CE render-object lighting. For the PS2
machine, this may be a render-only owner to replace with the parent's snapshot
and material/light cache, but that ownership choice must be explicit and
budgeted. An empty generated stub currently drops the allocation and lifecycle
without a test proving that no in-scope caller requires the datum.

`render_effects` is invoked by the HaloScript evaluator and sets four CE
globals: weather particle systems, particle systems, particles, and contrails.
The particle-system and weather render functions consume these gates. Thus
the effect is script-visible presentation state even if PS2 does not reproduce
the Xbox draw routines. Preserve it in the snapshot/presentation adapter, or
prove the scripts and all consumers are deliberately excluded; a no-op is not
semantically equivalent.

Keep these five symbols pending. Follow-up should trace every read of
`cached_object_render_states` into the selected PS2 owner, reconcile its
allocation with the game-state/memory ledger, exercise startup/map reload/
unload/dispose, and test HaloScript toggling against presentation flags. Do
not port the rasterizer's drawing functions as a side effect of this review.

Regression anchor:
`tests/test_hcu_external_review.py::test_render_lifecycle_stubs_have_game_state_ownership_and_remain_pending`.
