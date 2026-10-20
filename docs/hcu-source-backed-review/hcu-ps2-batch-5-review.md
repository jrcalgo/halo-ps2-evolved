# CE rasterizer roots under the PS2 M0 batch-5 slice

Status: pending slice `[160:192]` is closed. Eight symbols have a source-backed owner in `port/ps2/src/ps2_m0_batch_5.c` (or the existing `ps2_edge.c` initializer). Generated zero/empty bodies are not approved where they mint a valid dynamic-vertex index, leave a zero camera clip, or drop the cinematic/map clip reset. Draw-only Xbox device calls stay excluded; script post-process writes that have no allocated cinematic datum are explicit state adapters.

## Evidence and boundary

The live caller sections on the ledger rows were traced to source, not inferred from names. `source/rasterizer/` is excluded from the PS2 manifest, so the retail wrappers and Xbox device bodies are not in the image. Generated `build/hcu-ps2-closure/all/ps2_platform.c` supplies typed zeros and empty functions unless a port file owns the symbol.

Dynamic vertex callers are `flag_render_proper` (`source/objects/widgets/flags.c:751-755`), `lightning_submit` (`source/objects/widgets/lightning.c:346-349`), and `render_dynamic_quad` (`source/game/game_engine_king.c:649-650`). Each treats a return other than `NONE` as a writable buffer and then locks. Xbox `_rasterizer_dynamic_vertices_new` starts at `NONE` and keeps `NONE` on capacity failure (`source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c:758-811`). The generated body returns `0`, which is a live index.

`.data.rasterizer_*_definition` objects in `source/hs/hs_globals_external.c:1086-1192` take addresses of `rasterizer_globals` fields. Text readers include `set_window_camera_values` and `halt_and_catch_fire` (`source/main/main.c:1212-1213,3214-3219,3236`). CE initializes clip defaults to `0.0625` / `1024` / `0.01171875` (`source/rasterizer/rasterizer.c:568-574,575-601`). A BSS-zero object collapses those cameras until something writes the fields.

`rasterizer_initialize` is already owned by `port/ps2/src/ps2_edge.c:82-107`. `shell_initialize` stores its boolean (`source/shell/shell.c:59-62`). `game_initialize_for_new_map` calls `rasterizer_initialize_for_new_map` (`source/game/game.c:666`). CE then resets lights, screen-effect state, tint, and near clip (`source/rasterizer/common/rasterizer_common.c:32-54`). `cinematic_stop` clears letterbox and re-enables input, then calls `rasterizer_screen_effects_initialize_for_new_map` and `rasterizer_set_near_clip_distance(0.0f)` (`source/cutscene/cinematics.c:242-257`). CE's setter writes `cinematic_screen_effect_globals`; the getter prefers a positive override, otherwise `0.0625` (`source/rasterizer/rasterizer_cinematics.c:474-497`). The halt path reads `rasterizer_globals.near_clip_distance` directly.

`rasterizer_frame_begin` / `rasterizer_frame_end` / `rasterizer_present` are rooted only from `halt_and_catch_fire` (`source/main/main.c:3201-3275`). CE frame-begin restores zero clips before the Xbox device (`source/rasterizer/rasterizer.c:742-751`). Present and frame-end only forward to that device.

`halo_shell_main` calls `rasterizer_preinitialize__fill_you_up_with_the_devils_cock` and ignores the boolean (`source/shell/shell_xbox.c:112-114`). The CE body creates the D3D8 device (`source/rasterizer/xbox/rasterizer_xbox.c:1834-1854`). Generated `FALSE` is a failed create, not a successful one.

`rasterizer_set_vblank_callback` is installed from `main_initialize_time` inside `main_loop` (`source/main/main.c:2894`). The handler increments `frame_and_vertical_blank_index` and calls `input_vertical_blank_interrupt` (`source/main/main.c:1833-1855`). On `HALO_PS2` that input function is empty (`source/input/input_xbox.c:633-646`). `main_rasterizer_throttle` waits on the index only when `rasterizer_globals.framerate_throttle` is true (`source/main/main.c:2772-2796`).

HaloScript evaluators in `source/hs/hs.c` are the sole rooted callers of `rasterizer_fps_accumulate`, `rasterizer_lights_reset_for_new_map`, `rasterizer_model_ambient_reflection_tint`, the screen-effect setters, and `rasterizer_script_screen_effect_set_value`. CE screen-effect writers no-op when `cinematic_screen_effect_globals` is NULL (`source/rasterizer/rasterizer_cinematics.c:134-214,217-470`). That pointer is allocated only by `rasterizer_screen_effects_initialize`, which is not a live owner in this closure. `rasterizer_model_ambient_reflection_tint` no-ops on a NULL tint pointer (`source/rasterizer/xbox/rasterizer_xbox_models.c:543-557`). The generated tint pointer stays NULL.

Model and widget calls are the flag/king and `light_volume_render` submission brackets (`source/objects/widgets/flags.c:925-954`, `source/game/game_engine_king.c:711-740`, `source/objects/widgets/light_volumes.c:276-320`). They are draw submission. `rasterizer_models_begin(FALSE)` also runs a render-only obscurer query (`source/rasterizer/rasterizer.c:1806-1842`).

`rasterizer_frame_update` writes `global_frame_parameters.dt` (`source/rasterizer/common/rasterizer_common.c:67-73`) from `game_frame` (`source/game/game.c:998`). Every `dt` reader lives in excluded Xbox rasterizer files.

## Disposition rationale

- `rasterizer_dynamic_vertices_new`: `implemented`. Return `NONE`. The generated `0` is a successful index and the callers lock it.
- `rasterizer_dynamic_vertices_unlock`: `implemented`. No-op on an unused index. Callers only unlock after a non-`NONE` new.
- `rasterizer_globals`: `implemented`. CE clip and push-buffer defaults; `framerate_throttle` is FALSE because this profile has no vblank device.
- `rasterizer_frame_begin`: `implemented`. Restore zero clip fields the way CE does before the Xbox device. `halt_and_catch_fire` reads those fields into the camera.
- `rasterizer_set_near_clip_distance`: `implemented`. A positive value writes `rasterizer_globals.near_clip_distance`; `0` restores `0.0625`. That is the getter's observable result on the field the halt and window cameras read.
- `rasterizer_screen_effects_initialize_for_new_map`: `implemented`. `cinematic_stop` uses this after it has already restored input and letterbox; the owned body clears the cinematic near-clip override.
- `rasterizer_initialize_for_new_map`: `implemented`. Same CE call order for lights reset, screen-effect init, tint clear, and near-clip reset. No tag-block bind: `global_rasterizer_data` is file-static in an excluded unit and is not a live external.
- `rasterizer_lights_reset_for_new_map`: `implemented`. Explicit no-op. CE memsets file-static lens-flare histories that this profile never allocates. The rooted caller is the HaloScript evaluator.
- `rasterizer_initialize`: `implemented`. Existing `ps2_edge.c` owner. It writes bounds, the same clip defaults, and `initialized`. It does not allocate the tint pointer; the tint writer already no-ops on NULL.
- `rasterizer_preinitialize__fill_you_up_with_the_devils_cock`: `state-adapter`. Generated `FALSE` is a failed D3D create. The shell ignores the boolean and does not stop.
- `rasterizer_set_vblank_callback`: `state-adapter`. Empty install. PS2 input vblank is already empty; throttle stays false on the owned globals object.
- `rasterizer_fps_accumulate`: `state-adapter`. Empty accumulator. The HaloScript allowlist disables the command (`source/hs/hs.c:12664`).
- `rasterizer_frame_update`: `state-adapter`. Empty write. No rooted consumer of `global_frame_parameters.dt` remains in the selected closure.
- `rasterizer_model_ambient_reflection_tint`: `state-adapter`. Empty write equals CE's NULL-pointer guard. The generated tint pointer is NULL.
- `rasterizer_screen_effect_set_convolution`, `rasterizer_screen_effect_set_filter`, `rasterizer_screen_effect_set_filter_desaturation_tint`, `rasterizer_screen_effect_set_video`, `rasterizer_screen_effect_start`, `rasterizer_screen_effect_stop`, `rasterizer_script_screen_effect_set_value`: `state-adapter`. Empty bodies match CE's NULL `cinematic_screen_effect_globals` guards. They do not change campaign flags; `cinematic_stop` already cleared those before it called the reset we own.
- `rasterizer_frame_end`, `rasterizer_present`: `excluded-proven`. Device present/cleanup. Only the halt loop calls them. Parent GS owns publication. Empty does not report success.
- `rasterizer_model_begin`, `rasterizer_model_draw`, `rasterizer_model_end`, `rasterizer_model_transparent_geometry_submit`, `rasterizer_models_begin`, `rasterizer_models_end`, `rasterizer_profile_enable`, `rasterizer_widget_begin`, `rasterizer_widget_batch_sprites`: `excluded-proven`. Draw submission. After `dynamic_vertices_new` returns `NONE`, the flag and king brackets are not entered. Lightning never reaches a widget. Light-volume begin/batch drop sprites only.

Re-open the excluded draw symbols before a parent GS/VU owner publishes flag cloth, lightning, king quads, or light volumes. Re-open the screen-effect adapters before allocating `cinematic_screen_effect_globals` or reading script effect values back. Re-open vblank before enabling `framerate_throttle` or a real vertical-blank interrupt.

## Regression

`tests/test_hcu_external_review_batch_5.py::test_batch_5_rooted_symbols_are_dispositioned` recomputes pending slice `[160:192]`, checks every batch-5 row, requires a real CE or port snippet for each contract, and checks that `ps2_m0_batch_5.c` defines exactly the skip list.

## Sources

- `docs/hcu-source-backed-review/hcu-ps2-external-review.json` (caller sections and caller_sources)
- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_5.c`
- `submodules/halo-ce-universal/port/ps2/src/ps2_edge.c:82-107`
- `submodules/halo-ce-universal/source/rasterizer/rasterizer.c:568-601,700-751,755-781,810-815,1082-1145,1564-1568,1650-1657,1774-1777,1806-1842`
- `submodules/halo-ce-universal/source/rasterizer/common/rasterizer_common.c:32-73`
- `submodules/halo-ce-universal/source/rasterizer/rasterizer_cinematics.c:134-214,474-497`
- `submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c:758-811`
- `submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox.c:843-849,1834-1854`
- `submodules/halo-ce-universal/source/objects/widgets/flags.c:749-960`
- `submodules/halo-ce-universal/source/objects/widgets/lightning.c:346-453`
- `submodules/halo-ce-universal/source/game/game_engine_king.c:636-744`
- `submodules/halo-ce-universal/source/objects/widgets/light_volumes.c:276-320`
- `submodules/halo-ce-universal/source/cutscene/cinematics.c:242-257`
- `submodules/halo-ce-universal/source/main/main.c:1833-1855,2894,3201-3275`
- `submodules/halo-ce-universal/source/game/game.c:666,998`
- `submodules/halo-ce-universal/source/hs/hs_globals_external.c:1086-1192`
- `submodules/halo-ce-universal/source/input/input_xbox.c:633-646`
- `build/hcu-ps2-closure/all/ps2_platform.c`
