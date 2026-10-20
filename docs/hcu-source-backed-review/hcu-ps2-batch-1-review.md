# CE save, format, cache, and config roots under the PS2 M0 slice

Status: slice `[32:64]` of the pending ledger is closed. Generated typed zeros either looked like a valid Xbox save handle, muted mix, disabled enhanced animations, skipped lightmap sampling, or dropped Custom Edition prefix/version gates. `ps2_m0_batch_1.c` owns those caller contracts. `_snprintf` / `_vsnprintf` / `__sync_val_compare_and_swap_4` stay on the existing PS2 CRT. Re-open before adding memory-unit saves, Bink attract movies, Xbox sprite buffers, a network session, or Custom Edition tag conversion.

## Evidence and boundary

Live caller sections were taken from the ledger rows. Data-section callers in this slice are ordinary `.text` functions; save enumeration lives in `enumerate_memory_units` and `saved_game_files_delete_all_custom_profiles` (`source/saved games/saved_game_files.c`). The generated bodies in `build/hcu-ps2-closure/all/ps2_platform.c` are typed zeros except where `port/ps2/src/ps2_crt.c` already supplies a real function.

`source/cache/xbox_sound_cache.c`, `source/cache/xbox_texture_cache.c`, `source/interface/attract_mode.c`, `source/interface/ui_widget.c`, `source/render/`, `source/networking/`, and `source/tool/` are excluded from the PS2 manifest (`port/ps2/port.json:35-76`). Those CE files remain comparison sources.

## Per-symbol dispositions

### `XFindFirstSaveGame` — state-adapter

- Caller: `source/saved games/saved_game_files.c:672,1807,1867` (`enumerate_memory_units`, `saved_game_files_delete_all_custom_profiles`)
- Effect: CE treats only `INVALID_HANDLE_VALUE` as “no enumeration.” The generated `NULL` is not that value, so the `do` loop runs once on unwritten `find_data` and then `XFindClose` is called.
- Disposition: return `INVALID_HANDLE_VALUE`. No memory-unit catalogue exists.
- Sources: `saved_game_files.c:672-693,1807-1830,1867-1985`; `port/ps2/src/ps2_m0_batch_1.c`.

### `XFindNextSaveGame` — state-adapter

- Caller: the same enumeration loops (`saved_game_files.c:688,1825,1980`)
- Effect: CE advances metadata only after a valid first handle. A generated zero already ends the loop, but only after a false-valid first handle.
- Disposition: return `0`. Pair with the invalid first handle.
- Sources: `saved_game_files.c:688,1825,1980`; `ps2_m0_batch_1.c`.

### `XFindClose` — state-adapter

- Caller: `saved_game_files.c:690,1827,1982`
- Effect: `if (!XFindClose(find_handle))` logs failure. Generated zero is that failure after a false-valid first handle.
- Disposition: return `0`. Callers skip close when first is `INVALID_HANDLE_VALUE`.
- Sources: `saved_game_files.c:690-693`; `ps2_m0_batch_1.c`.

### `__sync_val_compare_and_swap_4` — implemented

- Caller: `source/cseries/errors.c:144` (`.text.write_to_error_file` / `write_to_debug_file`)
- Effect: the port opens `d:\\debug.txt` once. The CAS installs the `FILE *` or closes a losing `fopen`.
- Disposition: `ps2_crt.c:76-83` already compares, stores, and returns the previous value. The EE image is single-threaded for this log.
- Sources: `errors.c:128-152`; `port/ps2/src/ps2_crt.c:76-83`.

### `_control87` — state-adapter

- Caller: `source/math/real_math.c:132` (`real_math_reset_precision`)
- Effect: CE writes `CW_DEFAULT` with mask `0xFFFFF` at init, each tick, and map transition. The return is unused. The generated zero writes nothing.
- Disposition: keep a software control word with MSVC mask semantics. The R5900 has no x87 field (`port/ps2/include/float.h`).
- Sources: `real_math.c:129-132`; `float.h:4-34`; `ps2_m0_batch_1.c`.

### `_snprintf` — implemented

- Callers: AI describe, mutex names, main throttle, profile paths (`action_obey.c`, `ai_debug.c`, `ai_script.c`, `thread_win32.c`, `main.c`, `player_profile.c`, `saved_game_files.c`, `unit_dialogue.c`)
- Effect: callers format into a capacity and sometimes test `> 0` (`saved_game_files.c:1884-1901`).
- Disposition: `ps2_crt.c` forwards to Newlib `vsnprintf`. The live `> 0` checks accept a C99 length; truncation also hits the `count >= capacity` guard in `terminal.c` for the va sibling.
- Sources: `saved_game_files.c:1884-1901`; `ps2_crt.c:47-56`.

### `_vsnprintf` — implemented

- Caller: `source/interface/terminal.c:373` (`terminal_printf`)
- Effect: `count = _vsnprintf(line->buffer, NUMBEROF(line->buffer)-2, format, arglist)` then `if (count < 0 || count >= capacity) terminate`.
- Disposition: same Newlib forward. The caller already accepts both MSVC `-1` and C99 “would-be length.”
- Sources: `terminal.c:373-375`; `ps2_crt.c:42-45`.

### `_vsnwprintf` — implemented

- Caller: `source/text/unicode.c:1339` (`usnprintf`)
- Effect: UI and script wide text (`L"%s"`, `L"%d"`, `L"%hs"`). The CRT copy of the format string dropped every substitution.
- Disposition: MSVC wide rules: `%s` is `wchar_t *`, `%hs` / `%S` are `char *`. Truncation returns `-1`.
- Sources: `unicode.c:1316-1342,1578`; `game_engine.c:1174,3728`; `ps2_m0_batch_1.c`.

### `_sound_cache_sound_request` — state-adapter

- Callers: `sound_manager.c` channel/impulse/render paths; `predicted_resources.c:147`; `game_sound.c`
- Effect: CE returns whether a permutation is resident. `channel_get_state` forces state `0` on false (`sound_manager.c:1950-1956`).
- Disposition: a non-null permutation is decision-ready. Parent SPU2 still owns samples. A generated false changes event eligibility.
- Sources: `xbox_sound_cache.c:665-739`; `sound_manager.c:360-361,1950-1956`; `ps2_m0_batch_1.c`.

### `_texture_cache_bitmap_get_hardware_format` — state-adapter

- Callers: `decals.c:1799`; `object_lights.c:543,1467,1481,2235`; `lightning.c:289`; `weapons.c:620`; `predicted_resources.c:61`
- Effect: `lights_illumination_at_point` samples lightmaps only after a non-null result. A generated null skips lighting.
- Disposition: return the tag `bitmap` as the ready token. Parent GS owns pixels.
- Sources: `object_lights.c:1465-1491`; `decals.c:1797-1806`; `ps2_m0_batch_1.c`.

### `attract_mode_start` — implemented

- Caller: `source/hs/hs.c` (`attract_mode_start_evaluate`); not allowed in map scripts (`hs.c:12558`)
- Effect: CE picks a movie, stops menu music, starts Bink, and if playback is inactive writes `attract_mode_countdown_timer` (`attract_mode.c:193-217`). The generated empty body drops that transition.
- Disposition: stop menu music and refresh the countdown. Bink stays excluded.
- Sources: `attract_mode.c:193-217`; `hs.c:12558,14206`; `ps2_m0_batch_1.c`.

### `build_sprites_begin` — state-adapter

- Callers: `antenna.c:490`; `glow.c:552`
- Effect: CE resets the caller-owned batch and sets the valid bit. Generated empty leaves stack `sprite_data` uninitialized for `build_sprite` / `end`.
- Disposition: initialize counts, groups, centroid, and the valid bit. No Xbox dynamic buffers.
- Sources: `render_sprite.c:204-228`; `antenna.c:490-495`; `ps2_m0_batch_1.c`.

### `build_sprite` — state-adapter

- Callers: `antenna.c:516`; `glow.c:560`
- Effect: CE writes quads into locked Xbox buffers. This adapter only advances `sprite_count` under the valid bit.
- Disposition: presentation geometry stays with the parent GS. The batch protocol is acknowledged.
- Sources: `render_sprite.c:342-585`; `antenna.c:514-528`; `glow.c:559-572`.

### `build_sprites_end` — state-adapter

- Callers: `antenna.c:531`; `glow.c:575`
- Effect: CE unlocks, submits, and deletes buffers, then clears the valid bit.
- Disposition: clear the valid bit. No buffer to unlock because begin never allocated one.
- Sources: `render_sprite.c:231-289`; `antenna.c:531`; `glow.c:575`.

### `config_boolean` — implemented

- Caller: `source/units/units.c:3345` (`unit_animation_enhanced`)
- Effect: first read sets `enhanced = config_boolean("game.enhanced_animations") != 0`. The CE/Linux default is true. Generated zero disables cyborg enhanced animation.
- Disposition: return `1` for that name.
- Sources: `units.c:3332-3346`; `port/linux/src/port_config.c:297`; `ps2_m0_batch_1.c`.

### `config_changes` — implemented

- Callers: `units.c:3342`; `sound_manager.c:1137`
- Effect: both sites reread settings when the generation changes. Generated zero is a stable generation after the first read.
- Disposition: return the fixed generation `0`.
- Sources: `units.c:3342-3345`; `sound_manager.c:1137-1141`.

### `config_real` — implemented

- Caller: `source/sound/sound_manager.c:1140-1141` (`sound_manager_port_volume`)
- Effect: music/effects gain start at `1.f` and are replaced by `config_real`. Generated zero mutes the mix.
- Disposition: return `1.0` for `audio.music_volume` and `audio.effects_volume`.
- Sources: `sound_manager.c:1130-1143`; `port_config.c:187-189`.

### `config_string` — implemented

- Caller: `source/interface/terminal.c:333` (`terminal_shows`)
- Effect: `"important"` keeps serious and important lines. Generated null leaves that default, but the name has no owner. Return the CE/Linux default string.
- Disposition: return `"important"` for `game.console_log`.
- Sources: `terminal.c:326-341`; `port_config.c:287`.

### `connected_geometry_new` — state-adapter

- Caller: `source/structures/structure_lens_flares.c:321` (`build_structure_lens_flares`)
- Effect: CE allocates dynamic point/edge/triangle arrays. A generated empty new leaves garbage for `add_triangle`. The HS command is not allowed in map scripts (`hs.c:12636`).
- Disposition: zero the accumulator. Fail-closed editor scratch.
- Sources: `structure_lens_flares.c:321`; `connected_geometry.c:117-124`; `hs.c:12636`.

### `connected_geometry_add_triangle` — state-adapter

- Caller: `structure_lens_flares.c:335`
- Effect: CE inserts vertices/edges. Generated zero is `NONE` only by accident of `memset`.
- Disposition: return `NONE` without walking arrays.
- Sources: `structure_lens_flares.c:335-340`; `connected_geometry.c:346-388`.

### `connected_geometry_group_coplanar` — state-adapter

- Caller: `structure_lens_flares.c:343`
- Effect: the group count drives marker placement after the builder has already resized `lens_flares` to empty.
- Disposition: return `0`. The wipe is the editor caller’s CE behavior; this helper does not invent groups.
- Sources: `structure_lens_flares.c:182-188,343-344`.

### `connected_geometry_delete` — state-adapter

- Caller: `structure_lens_flares.c:565`
- Effect: CE releases dynamic arrays. Safe on a zeroed accumulator.
- Disposition: zero the struct again.
- Sources: `connected_geometry.c:127-145`; `structure_lens_flares.c:565`.

### `create_global_network_game_server` — state-adapter

- Caller: `source/interface/player_ui.c:673` (`player_ui_fast_setup_network_server`); HS not allowed in maps (`hs.c:12679`)
- Effect: both creates must succeed before `game_connection_set(network_server)`. Generated false already takes the failure path that disposes and returns to the main menu.
- Disposition: return `FALSE`. This machine has no network session owner.
- Sources: `player_ui.c:651-685`; `hs.c:12679`.

### `create_global_network_game_client` — state-adapter

- Caller: `player_ui.c:673`
- Effect: paired with the server create. False is the failed-service result, not success.
- Disposition: return `FALSE`.
- Sources: `player_ui.c:673-684`; `network_game_globals.c:456-468`.

### `custom_edition_cache_refuse` — implemented

- Caller: `source/cache/cache_files.c:904` (`cache_file_header_verify`)
- Effect: a true refuse stops Xbox version-5 checks and names the CE cache. Generated false lets version 609 fall through.
- Disposition: refuse signature `'head'` + version `609`.
- Sources: `cache_files.c:900-905`; `port/linux/game/custom_edition_cache.c:659-692`; `cache_file_formats.h:36-37`.

### `custom_edition_cache_tags_load` — state-adapter

- Caller: `cache_files.c:1233` (`scenario_tags_load`) after `custom_edition_level_name`
- Effect: CE expects a converted tag header. Generated null already fails the map. Treating the file as Xbox is not allowed.
- Disposition: return `NULL`. No PS2 converter.
- Sources: `cache_files.c:1231-1256`.

### `custom_edition_cache_tags_loaded` — state-adapter

- Callers: `cache_files.c` BSP/tag paths; `game_engine.c`; `tag_groups.c`
- Effect: false selects stock Xbox offsets. True is valid only after a converted cache exists.
- Disposition: return `FALSE`.
- Sources: `cache_files.c:375-378,646-647,1390,1489`.

### `custom_edition_cache_tags_unload` — state-adapter

- Caller: `cache_files.c:647`, only when `custom_edition_cache_tags_loaded()`
- Effect: CE tears down converted owners. Unreachable while loaded is false.
- Disposition: empty unload of an empty owner.
- Sources: `cache_files.c:646-647`.

### `custom_edition_level_name` — implemented

- Callers: `cache_files.c:1028,1231`; `source/main/main.c:1279`
- Effect: a `custom_maps\` name must not be treated as an Xbox campaign map. Generated false would send it into stock load.
- Disposition: prefix `CUSTOM_EDITION_LEVEL_NAME_PREFIX`.
- Sources: `main.c:1276-1280`; `custom_edition_cache.c:695-699`; `custom_edition_cache.h:41`.

### `custom_edition_maps_description` — state-adapter

- Caller: `source/text/text_group.c:221` (`fallback_string`)
- Effect: CE catalogue copy by display index. No PS2 catalogue.
- Disposition: return `NULL`. The fallback then continues.
- Sources: `text_group.c:218-221`.

### `custom_edition_maps_name` — state-adapter

- Caller: `text_group.c:219`
- Effect: same catalogue path for names.
- Disposition: return `NULL`.
- Sources: `text_group.c:218-219`.

### `custom_edition_structure_bsp_load` — state-adapter

- Caller: `cache_files.c:1489`, only when `custom_edition_cache_tags_loaded()`
- Effect: CE materializes converted BSP geometry. Generated false would fail that load. Unreachable while loaded is false.
- Disposition: return `FALSE`.
- Sources: `cache_files.c:1486-1490`.

## Regression

`tests/test_hcu_external_review_batch_1.py::test_batch_1_rooted_symbols_are_dispositioned` locks the slice, each disposition, the skip list against `ps2_m0_batch_1.c`, and one real contract snippet per approved row.

## Sources

- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_1.c`
- `submodules/halo-ce-universal/port/ps2/src/ps2_crt.c`
- `submodules/halo-ce-universal/source/saved games/saved_game_files.c`
- `submodules/halo-ce-universal/source/cseries/errors.c`
- `submodules/halo-ce-universal/source/math/real_math.c`
- `submodules/halo-ce-universal/source/sound/sound_manager.c`
- `submodules/halo-ce-universal/source/objects/object_lights.c`
- `submodules/halo-ce-universal/source/units/units.c`
- `submodules/halo-ce-universal/source/cache/cache_files.c`
- `submodules/halo-ce-universal/source/hs/hs.c`
- `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
