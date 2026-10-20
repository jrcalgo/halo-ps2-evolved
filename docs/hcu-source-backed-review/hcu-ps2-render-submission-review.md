# Render frame, decal, screen-effect, and map-registration roots

Status: all of these rooted render calls stay pending. Empty or zero bodies are not draw-only on these callers.

## Frame entry

`render_frame` is called from `main_loop` with the local windows (`source/main/main.c:3381-3384`) and from `screenshot_render`. `render_frame_present` follows the pregame and screenshot paths (`main.c:1226,2976`). `render_frame_pregame` draws the movie or pregame window (`2004-2006`). The CE `render_frame` submits the frame (`source/render/render.c:594`). The generated bodies are empty.

`render` itself is also a rooted global. `.data.editor_custom_render` is `editor_custom_render = &render` (`source/camera/editor_flying_camera.c:216`). The editor camera then copies that camera (`562-565`). Text callers include `glow_submit`, `light_volume_render`, `light_volume_submit`, `lightning_submit`, `particle_new`, `particles_update`, and `unit_render_debug`. A zero `render` object is not the editor or particle camera.

`rasterizer_set_vblank_callback` installs `main_vertical_blank_interrupt_handler` during time init (`main.c:2894`). The empty stub stores no callback, so the flip-delta and frame-index handler does not run from vblank.

`rasterizer_preinitialize__fill_you_up_with_the_devils_cock` creates the D3D8 device (`source/rasterizer/xbox/rasterizer_xbox.c:1834-1854`). `halo_shell_main` calls it and ignores the boolean (`source/shell/shell_xbox.c:112-114`). False does not stop the shell, and it also does not create the device the Xbox rasterizer expects. The parent GS setup is a different owner. This row stays pending until that owner is the one the shell calls.

## Models, widgets, and decals

`flag_render_proper` and `render_dynamic_quad` call `rasterizer_models_begin`, `rasterizer_model_begin`, `rasterizer_model_draw`, `rasterizer_model_transparent_geometry_submit`, `rasterizer_model_end`, `rasterizer_models_end`, and `rasterizer_profile_enable`. `light_volume_render` calls `rasterizer_widget_begin`, `rasterizer_widget_set_texture`, `rasterizer_widget_batch_sprites`, `rasterizer_widget_draw_sprite3d`, and `rasterizer_widget_end`. `light_volume_submit` calls `rasterizer_widget_submit`. These are the same class of bounded geometry submission as the dynamic-geometry review. Empty calls drop the submission and can leave a begin without an end.

`decal_new_from_collision` calls `rasterizer_decal_vertices_new`, lock, unlock, and delete (`source/effects/decals.c:2108`). Permanent decal deletion calls delete as well. `decals_initialize`, `decals_dispose`, `decals_initialize_for_new_map`, and `decals_dispose_from_old_map` bracket the decal lifetime. `rasterizer_decals_flush_evaluate` is the script flush. `.data.after_load_procs` is the saved-game table in `source/saved games/game_state.c:196-211`; `rasterizer_decals_update_function_pointers` is one entry, and `game_state_call_after_load_procs` runs it after a core load (`249-255,370`). `bitmap_delete` calls `rasterizer_bitmap_delete`. A zero vertex index or a skipped function pointer is a decal and bitmap lifetime change, not a hidden debug draw.

## Screen effects and map GPU registration

The screen-effect script evaluators call `rasterizer_screen_effect_set_convolution`, `set_filter`, `set_filter_desaturation_tint`, `set_video`, `start`, `stop`, and `rasterizer_script_screen_effect_set_value`. `cinematic_stop` calls `rasterizer_screen_effects_initialize_for_new_map` after it clears letterbox and re-enables input (`source/cutscene/cinematics.c:242-249`). `rasterizer_fps_accumulate_evaluate` is the script accumulator. These write presentation state that cinematics and scripts read back. They stay pending with the earlier rasterizer-state review.

`scenario_structure_bsp_load` calls `structure_bsp_header_register_vertex_buffers` (`source/cache/cache_files.c:1497`). The CE body writes `D3DCOMMON_TYPE_VERTEXBUFFER` into each buffer header and registers it (`source/cache/cache_files_windows.c:485-497`). Unload calls the deregister pair. `scenario_tags_load` and `scenario_tags_unload` call `tags_header_register_vertex_and_index_buffers` and the deregister. Skipping them leaves CPU cache headers unregistered and, on unload, can leave a registered buffer after the cache is released.

`progress_bar_initialize` copies `loading.tga` through `CreateDirectoryA` and `CopyFileA` (`source/interface/progress_bar.c:1557-1571`). `game_dispose` calls `progress_bar_dispose`. The file copy is a loading-screen asset, and the writable copy is not the read-only asset root.

`objects_initialize_for_new_map` calls `first_person_legs_reset` (`source/objects/objects.c:1074-1076`). The CE body clears the waist key, model, and rim, then calls `object_mesh_reset` (`port/linux/game/first_person_legs.c:125-131`). The empty stub keeps the previous map's mesh index.

`pal_tags_first_person_advance` returns TRUE for a non-PAL animation (`port/linux/game/pal_tags.c:408-431`). `first_person_weapons_update` treats FALSE as "no keyframe" and skips `animation_update_render_only` (`source/interface/first_person_weapons.c:1858-1868`). The generated FALSE therefore stops first-person weapon animation for every map, not only PAL maps. `pal_tags_first_person_frames` replaces the frame count used by `weapon_get_first_person_animation_time` (`source/items/weapons.c:1379-1383`). A zero frame count is not the NTSC count the real function returns when the animation is not PAL.

## Regression

`tests/test_hcu_external_review.py::test_render_submission_roots_remain_pending` checks the main-loop frame call, the after-load decal pointer, the PAL false branch, and that every row in this review stays pending.
