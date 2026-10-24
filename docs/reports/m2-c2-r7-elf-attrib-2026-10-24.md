# C2 ELF text attribution (lane elf-attrib), 2026-10-24

Lane elf-attrib (C2.3 analysis, read-only on source). Tool: `tools/c2_elf_text_attribution.py`; tests: `tests/test_c2_elf_text_attribution.py` (15 synthetic-map tests, pass). Machine-readable output: `docs/reports/m2-c2-r7-elf-attrib-2026-10-24.json`.

## Verdict

**Not met.** The ranked, attributable list does not reach 979,064 B. The best attributable total, the union of the three candidate classes, is **357,770 B upper bound and 107,241 B conservative** (each class's own reachable bytes). The rest of the goal would have to come from **761,249 B of map residual** (501,623 B bss, 259,626 B rodata) that this map cannot attribute, and from variant-specific debug storage whose size differs between builds (see Caveats). Confidence: high for the attribution and the map totals; medium for the candidate classes; low for any residual-based claim.

## Inputs and reconciliation

| Input | Path | sha256 |
|---|---|---|
| candidates | `build/m2-c2-r7-elf-attrib/candidates.json` | `8f1a22277bec9aa8…` |
| closure_result_json | `build/m2-c2-r7-elf-attrib/closure-snapshot/result.json` | `9b03be95284faf6b…` |
| map_copy | `build/m2-c2-r7-elf-attrib/hcu-gameplay-machine.map` | `abf25913998a63e4…` |
| map_original | `build/hcu-parent-link-probe/hcu-gameplay-machine.map` | `bf698b3f6520fff1…` |

The map is `build/hcu-parent-link-probe/hcu-gameplay-machine.map` (written 2026-10-23 23:23). It is copied to `build/m2-c2-r7-elf-attrib/` and the closure objects are snapshotted to `build/m2-c2-r7-elf-attrib/closure-snapshot/`, because another lane rewrote `build/hcu-ps2-closure/all-no-bootstrap-memory/` during this run (`source_units_units.c.o` changed at 00:44, and an `objdump -r` on it failed in the first attempt).

The ELF `build/hcu-parent-link-probe/hcu-gameplay-machine.elf` is **newer** (2026-10-24 00:46) and was not produced from this map: `render` is at `0x0045e920` in the ELF and `0x00462a20` in the map. The ELF was therefore not used for sizes. The ELF's symbol table shows `ai_debug` at 236,356 B, which comes from a different variant's object (`build/m2-c2-r3-elf-budget/ai-debug/ai_debug-production.o`), not from this map.

| Kind | Map header total (B) | Attributed (B) | Residual (B) |
|---|---:|---:|---:|
| text | 1,736,232 | 1,736,096 | 136 |
| data | 73,196 | 71,198 | 1,998 |
| rodata | 384,296 | 124,670 | 259,626 |
| bss | 1,825,644 | 1,324,021 | 501,623 |

Retained input sections: 8,081. Reachable section nodes from the 35 rooted-link roots: 10,105 (all 35 roots resolve).

## Top 60 source files by retained bytes, per section

### text

| # | Source | Bytes |
|---:|---|---:|
| 1 | `source/units/units.c` | 67,780 |
| 2 | `closure:ps2_abi.o` | 59,816 |
| 3 | `source/game/game_engine.c` | 48,972 |
| 4 | `sdk:lib` | 41,820 |
| 5 | `source/objects/objects.c` | 39,188 |
| 6 | `source/hs/hs.c` | 37,856 |
| 7 | `source/ai/actor_perception.c` | 33,172 |
| 8 | `source/ai/ai_communication.c` | 31,048 |
| 9 | `source/units/bipeds.c` | 28,544 |
| 10 | `source/game/players.c` | 26,484 |
| 11 | `source/ai/encounters.c` | 25,232 |
| 12 | `source/ai/ai_script.c` | 23,884 |
| 13 | `source/ai/actors.c` | 23,776 |
| 14 | `source/ai/actions.c` | 23,044 |
| 15 | `source/ai/actor_moving.c` | 21,704 |
| 16 | `source/items/weapons.c` | 20,680 |
| 17 | `source/hs/hs_compile.c` | 20,192 |
| 18 | `source/sound/sound_manager.c` | 18,476 |
| 19 | `source/units/vehicles.c` | 18,156 |
| 20 | `source/models/model_animations.c` | 17,444 |
| 21 | `source/hs/hs_runtime.c` | 17,404 |
| 22 | `source/physics/physics.c` | 17,204 |
| 23 | `source/ai/actor_firing_position.c` | 16,772 |
| 24 | `other:ccaRr9Ju.ltrans0.ltrans.o` | 15,240 |
| 25 | `source/ai/ai.c` | 14,816 |
| 26 | `source/main/main.c` | 14,772 |
| 27 | `source/interface/hud_draw.c` | 14,688 |
| 28 | `gcc-lib:libc.a(libc_a-vfprintf.o)` | 14,616 |
| 29 | `gcc-lib:libc.a(libc_a-svfprintf.o)` | 14,264 |
| 30 | `source/effects/effects.c` | 13,936 |
| 31 | `source/effects/decals.c` | 13,700 |
| 32 | `source/ai/action_obey.c` | 12,984 |
| 33 | `source/items/projectiles.c` | 12,976 |
| 34 | `source/ai/actor_combat.c` | 12,712 |
| 35 | `source/physics/collisions.c` | 12,688 |
| 36 | `source/physics/collision_bsp.c` | 12,372 |
| 37 | `source/ai/actor_looking.c` | 12,344 |
| 38 | `source/objects/damage.c` | 12,296 |
| 39 | `source/game/player_control.c` | 12,016 |
| 40 | `source/math/real_math.c` | 11,956 |
| 41 | `source/sound/sound_dsound_xbox.c` | 11,744 |
| 42 | `source/camera/observer.c` | 11,192 |
| 43 | `source/interface/hud_weapon.c` | 10,968 |
| 44 | `closure:ps2_platform.o` | 10,732 |
| 45 | `gcc-lib:libc.a(libc_a-vfscanf.o)` | 10,592 |
| 46 | `source/ai/path.c` | 9,868 |
| 47 | `gcc-lib:libc.a(libc_a-svfiscanf.o)` | 9,688 |
| 48 | `closure:ps2_edge.o` | 9,636 |
| 49 | `source/interface/first_person_weapons.c` | 9,480 |
| 50 | `source/ai/action_alert.c` | 9,440 |
| 51 | `port/linux/game/tag_validate.c` | 9,108 |
| 52 | `source/physics/collision_features.c` | 7,912 |
| 53 | `gcc-lib:libc.a(libc_a-strtod.o)` | 7,848 |
| 54 | `source/effects/particle_systems.c` | 7,812 |
| 55 | `source/saved games/saved_game_files.c` | 7,768 |
| 56 | `source/sound/game_sound.c` | 7,724 |
| 57 | `parent:60869cbb0e20/stream/hcu_map_service.c` | 7,628 |
| 58 | `source/objects/object_lights.c` | 7,616 |
| 59 | `source/objects/widgets/flags.c` | 7,612 |
| 60 | `source/interface/hud.c` | 7,492 |

### rodata

| # | Source | Bytes |
|---:|---|---:|
| 1 | `other:map-residual` | 259,626 |
| 2 | `port/linux/game/tag_schema_effects.c` | 17,584 |
| 3 | `parent:60869cbb0e20/stream/hcu_filexio_irx.c` | 16,072 |
| 4 | `source/hs/hs.c` | 14,204 |
| 5 | `port/linux/game/tag_schema_render.c` | 12,034 |
| 6 | `port/linux/game/tag_schema_objects.c` | 11,336 |
| 7 | `port/linux/game/tag_schema_collision.c` | 8,660 |
| 8 | `port/linux/game/tag_schema_scenario.c` | 8,024 |
| 9 | `source/ai/ai_communication.c` | 6,328 |
| 10 | `port/linux/game/tag_schema_models.c` | 5,120 |
| 11 | `parent:60869cbb0e20/stream/hcu_map_catalog.c` | 3,560 |
| 12 | `rooted.o:unresolved` | 1,780 |
| 13 | `gcc-lib:libc.a(libc_a-vfscanf.o)` | 1,010 |
| 14 | `other:ccaRr9Ju.ltrans0.ltrans.o` | 984 |
| 15 | `source/ai/actions.c` | 936 |
| 16 | `source/input/input_xbox.c` | 784 |
| 17 | `gcc-lib:libc.a(libc_a-svfiscanf.o)` | 690 |
| 18 | `sdk:lib` | 688 |
| 19 | `gcc-lib:libc.a(libc_a-ctype_.o)` | 648 |
| 20 | `source/text/text_group.c` | 592 |
| 21 | `gcc-lib:libc.a(libc_a-strerror.o)` | 572 |
| 22 | `source/hs/hs_runtime.c` | 568 |
| 23 | `closure:ps2_memory.o` | 528 |
| 24 | `closure:ps2_edge.o` | 528 |
| 25 | `source/ai/actor_moving.c` | 492 |
| 26 | `source/ai/action_obey.c` | 487 |
| 27 | `source/hs/hs_globals_external.c` | 445 |
| 28 | `source/units/dialogue_definitions.c` | 418 |
| 29 | `gcc-lib:libc.a(libc_a-vfiprintf.o)` | 400 |
| 30 | `gcc-lib:libc.a(libc_a-svfprintf.o)` | 400 |
| 31 | `gcc-lib:libc.a(libc_a-vfprintf.o)` | 400 |
| 32 | `gcc-lib:libm.a(libm_a-e_rem_pio2.o)` | 392 |
| 33 | `source/units/units.c` | 380 |
| 34 | `source/units/bipeds.c` | 324 |
| 35 | `gcc-lib:libc.a(libc_a-strtod.o)` | 296 |
| 36 | `gcc-lib:libc.a(libc_a-mprec.o)` | 296 |
| 37 | `parent:60869cbb0e20/stream/sha256.c` | 288 |
| 38 | `source/cseries/cseries.c` | 272 |
| 39 | `gcc-lib:libc.a(libc_a-gdtoa-gethex.o)` | 256 |
| 40 | `gcc-lib:libgcc.a(_clz.o)` | 256 |
| 41 | `source/game/game_engine.c` | 226 |
| 42 | `source/physics/collisions.c` | 204 |
| 43 | `source/hs/hs_compile.c` | 196 |
| 44 | `source/units/vehicles.c` | 172 |
| 45 | `source/ai/actor_looking.c` | 168 |
| 46 | `source/camera/director.c` | 166 |
| 47 | `parent:60869cbb0e20/stream/hcu_owner_telemetry.c` | 144 |
| 48 | `source/ai/actor_perception.c` | 144 |
| 49 | `source/math/real_math.c` | 144 |
| 50 | `source/rasterizer/rasterizer_swizzle.c` | 128 |
| 51 | `source/ai/actor_firing_position.c` | 124 |
| 52 | `source/interface/hud_draw.c` | 122 |
| 53 | `source/math/geometry.c` | 120 |
| 54 | `source/objects/objects.c` | 120 |
| 55 | `source/items/weapons.c` | 111 |
| 56 | `source/game/players.c` | 108 |
| 57 | `source/interface/first_person_weapons.c` | 106 |
| 58 | `closure:ps2_crt.o` | 102 |
| 59 | `gcc-lib:libc.a(libc_a-mktime.o)` | 96 |
| 60 | `source/ai/encounters.c` | 96 |

### data

| # | Source | Bytes |
|---:|---|---:|
| 1 | `source/hs/hs_runtime.c` | 9,604 |
| 2 | `source/interface/interface.c` | 7,338 |
| 3 | `source/hs/hs_globals_external.c` | 7,076 |
| 4 | `sdk:lib` | 4,220 |
| 5 | `source/hs/hs.c` | 3,518 |
| 6 | `source/game/players.c` | 3,100 |
| 7 | `source/objects/object_types.c` | 2,608 |
| 8 | `source/sound/sound_classes.c` | 2,448 |
| 9 | `other:map-residual` | 1,998 |
| 10 | `source/units/dialogue_definitions.c` | 1,672 |
| 11 | `source/units/units.c` | 1,563 |
| 12 | `source/sound/sound_manager.c` | 1,552 |
| 13 | `source/items/projectiles.c` | 1,548 |
| 14 | `source/game/game.c` | 1,544 |
| 15 | `source/effects/particles.c` | 1,536 |
| 16 | `source/items/weapons.c` | 1,536 |
| 17 | `source/game/player_control.c` | 1,535 |
| 18 | `source/objects/objects.c` | 1,534 |
| 19 | `source/effects/effects.c` | 1,529 |
| 20 | `source/units/bipeds.c` | 1,529 |
| 21 | `source/ai/ai.c` | 1,528 |
| 22 | `source/items/items.c` | 1,528 |
| 23 | `source/units/vehicles.c` | 1,528 |
| 24 | `gcc-lib:libc.a(libc_a-mallocr.o)` | 1,040 |
| 25 | `source/bitmaps/bitmaps.c` | 1,024 |
| 26 | `source/models/model_animation_definitions.c` | 784 |
| 27 | `source/tag_files/files_windows.c` | 616 |
| 28 | `source/ai/encounters.c` | 400 |
| 29 | `gcc-lib:libc.a(libc_a-locale.o)` | 364 |
| 30 | `source/shaders/shader_definitions.c` | 360 |
| 31 | `source/cutscene/recorded_animation_playback_v1.c` | 304 |
| 32 | `gcc-lib:libc.a(libc_a-impure.o)` | 292 |
| 33 | `source/ai/ai_communication.c` | 276 |
| 34 | `source/cutscene/recorded_animation_initialize.c` | 272 |
| 35 | `source/cutscene/recorded_animation_playback.c` | 272 |
| 36 | `port/ps2/src/ps2_rasterizer.c` | 244 |
| 37 | `source/ai/ai_profile.c` | 224 |
| 38 | `source/main/debug_keys.c` | 200 |
| 39 | `source/objects/widgets/widgets.c` | 200 |
| 40 | `source/items/projectile_definitions.c` | 160 |
| 41 | `source/game/game_engine_ctf.c` | 136 |
| 42 | `source/game/game_engine_king.c` | 136 |
| 43 | `source/game/game_engine_oddball.c` | 136 |
| 44 | `source/game/game_engine_race.c` | 136 |
| 45 | `source/game/game_engine_slayer.c` | 136 |
| 46 | `source/game/game_engine_stub.c` | 136 |
| 47 | `source/game/game_globals.c` | 132 |
| 48 | `source/memory/byte_swapping.c` | 108 |
| 49 | `gcc-lib:libc.a(libc_a-gettzinfo.o)` | 88 |
| 50 | `source/cseries/cseries.c` | 88 |
| 51 | `source/saved games/game_state.c` | 76 |
| 52 | `parent:60869cbb0e20/stream/file.c` | 64 |
| 53 | `source/ai/actor_types.c` | 64 |
| 54 | `source/camera/camera_scripting.c` | 64 |
| 55 | `source/sound/sound_dsound_xbox.c` | 60 |
| 56 | `source/math/real_math.c` | 56 |
| 57 | `source/ai/ai_scenario_definitions.c` | 48 |
| 58 | `source/units/unit_dialogue.c` | 44 |
| 59 | `source/game/game_allegiance.c` | 40 |
| 60 | `source/ai/actor_type_carrier.c` | 32 |

### bss

| # | Source | Bytes |
|---:|---|---:|
| 1 | `other:map-residual` | 501,623 |
| 2 | `port/linux/game/tag_schema_effects.c` | 262,544 |
| 3 | `port/linux/game/tag_validate.c` | 262,273 |
| 4 | `source/game/player_queues_new.c` | 84,544 |
| 5 | `source/hs/hs.c` | 78,595 |
| 6 | `source/tag_files/tag_groups.c` | 65,536 |
| 7 | `sdk:lib` | 63,790 |
| 8 | `port/ps2/src/ps2_rasterizer.c` | 58,517 |
| 9 | `source/game/game_engine.c` | 54,535 |
| 10 | `port/ps2/game/ps2_local.c` | 49,152 |
| 11 | `source/objects/object_lights.c` | 45,097 |
| 12 | `source/units/biped_limp_noodle.c` | 44,808 |
| 13 | `source/units/units.c` | 40,974 |
| 14 | `port/linux/game/tag_schema_scenario.c` | 40,378 |
| 15 | `port/linux/game/tag_schema_models.c` | 32,767 |
| 16 | `source/effects/decals.c` | 30,923 |
| 17 | `port/linux/game/tag_schema_collision.c` | 18,448 |
| 18 | `parent:60869cbb0e20/render/bsp_render.c` | 17,848 |
| 19 | `rooted.o:unresolved` | 11,708 |
| 20 | `source/saved games/game_state.c` | 10,277 |
| 21 | `source/objects/widgets/antenna.c` | 6,101 |
| 22 | `parent:60869cbb0e20/world/section.c` | 4,224 |
| 23 | `source/sound/game_sound.c` | 4,112 |
| 24 | `source/main/console.c` | 3,525 |
| 25 | `other:ccaRr9Ju.ltrans0.ltrans.o` | 3,024 |
| 26 | `source/camera/observer.c` | 2,676 |
| 27 | `source/main/main.c` | 2,671 |
| 28 | `parent:60869cbb0e20/stream/hcu_main.c` | 2,132 |
| 29 | `source/cache/cache_files.c` | 2,097 |
| 30 | `parent:60869cbb0e20/platform/pad.c` | 2,070 |
| 31 | `source/structures/structures.c` | 2,058 |
| 32 | `source/input/input_xbox.c` | 1,708 |
| 33 | `source/bungie_net/common/thread_win32.c` | 1,544 |
| 34 | `source/memory/crc.c` | 1,025 |
| 35 | `source/camera/director.c` | 1,009 |
| 36 | `source/scenario/scenario.c` | 905 |
| 37 | `source/game/players.c` | 723 |
| 38 | `source/effects/weather_particle_systems.c` | 636 |
| 39 | `closure:ps2_edge.o` | 588 |
| 40 | `source/game/game_engine_king.c` | 574 |
| 41 | `source/interface/player_ui.c` | 560 |
| 42 | `source/input/input_abstraction.c` | 496 |
| 43 | `source/sound/sound_manager.c` | 396 |
| 44 | `source/interface/event_manager.c` | 360 |
| 45 | `gcc-lib:libc.a(libc_a-findfp.o)` | 340 |
| 46 | `source/hs/hs_compile.c` | 300 |
| 47 | `port/ps2/src/ps2_cache.c` | 300 |
| 48 | `source/saved games/saved_game_files.c` | 284 |
| 49 | `source/game/game_engine_oddball.c` | 264 |
| 50 | `source/render/render_cameras.c` | 259 |
| 51 | `source/sound/sound_dsound_xbox.c` | 257 |
| 52 | `parent:60869cbb0e20/stream/hcu_file_bridge.c` | 256 |
| 53 | `source/game/game_engine_race.c` | 256 |
| 54 | `source/text/draw_string.c` | 228 |
| 55 | `source/objects/widgets/light_volumes.c` | 180 |
| 56 | `port/ps2/src/ps2_owner_counters.c` | 176 |
| 57 | `source/ai/encounters.c` | 154 |
| 58 | `closure:ps2_memory.o` | 144 |
| 59 | `source/models/models.c` | 136 |
| 60 | `source/sound/sound_definitions.c` | 132 |

## Top 60 source files, all sections

| # | Source | text | rodata | data | bss | total |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `closure:ps2_abi.o` | 59,816 | 0 | 0 | 0 | 59,816 |
| 2 | `closure:ps2_crt.o` | 2,288 | 102 | 0 | 4 | 2,394 |
| 3 | `closure:ps2_edge.o` | 9,636 | 528 | 0 | 588 | 10,752 |
| 4 | `closure:ps2_memory.o` | 4,028 | 528 | 0 | 144 | 4,700 |
| 5 | `closure:ps2_platform.o` | 10,732 | 24 | 0 | 128 | 10,884 |
| 6 | `gcc-lib:crtbegin.o` | 408 | 0 | 0 | 32 | 440 |
| 7 | `gcc-lib:crtend.o` | 96 | 0 | 0 | 0 | 96 |
| 8 | `gcc-lib:libc.a(libc_a-__call_atexit.o)` | 504 | 0 | 4 | 4 | 512 |
| 9 | `gcc-lib:libc.a(libc_a-_isatty.o)` | 120 | 0 | 0 | 0 | 120 |
| 10 | `gcc-lib:libc.a(libc_a-abort.o)` | 24 | 0 | 0 | 0 | 24 |
| 11 | `gcc-lib:libc.a(libc_a-assert.o)` | 120 | 0 | 0 | 0 | 120 |
| 12 | `gcc-lib:libc.a(libc_a-atof.o)` | 8 | 0 | 0 | 0 | 8 |
| 13 | `gcc-lib:libc.a(libc_a-atoi.o)` | 32 | 0 | 0 | 0 | 32 |
| 14 | `gcc-lib:libc.a(libc_a-callocr.o)` | 312 | 0 | 0 | 0 | 312 |
| 15 | `gcc-lib:libc.a(libc_a-closer.o)` | 112 | 0 | 0 | 0 | 112 |
| 16 | `gcc-lib:libc.a(libc_a-ctype_.o)` | 0 | 648 | 0 | 0 | 648 |
| 17 | `gcc-lib:libc.a(libc_a-div.o)` | 48 | 0 | 0 | 0 | 48 |
| 18 | `gcc-lib:libc.a(libc_a-dtoa.o)` | 7,432 | 0 | 0 | 0 | 7,432 |
| 19 | `gcc-lib:libc.a(libc_a-environ.o)` | 0 | 0 | 4 | 4 | 8 |
| 20 | `gcc-lib:libc.a(libc_a-envlock.o)` | 32 | 0 | 0 | 0 | 32 |
| 21 | `gcc-lib:libc.a(libc_a-errno.o)` | 16 | 0 | 0 | 0 | 16 |
| 22 | `gcc-lib:libc.a(libc_a-exit.o)` | 56 | 0 | 0 | 0 | 56 |
| 23 | `gcc-lib:libc.a(libc_a-fclose.o)` | 472 | 0 | 0 | 0 | 472 |
| 24 | `gcc-lib:libc.a(libc_a-fflush.o)` | 1,200 | 0 | 0 | 0 | 1,200 |
| 25 | `gcc-lib:libc.a(libc_a-fgets.o)` | 560 | 0 | 0 | 0 | 560 |
| 26 | `gcc-lib:libc.a(libc_a-fileno.o)` | 264 | 0 | 0 | 0 | 264 |
| 27 | `gcc-lib:libc.a(libc_a-findfp.o)` | 1,336 | 0 | 12 | 340 | 1,688 |
| 28 | `gcc-lib:libc.a(libc_a-fiprintf.o)` | 136 | 0 | 0 | 0 | 136 |
| 29 | `gcc-lib:libc.a(libc_a-flags.o)` | 216 | 0 | 0 | 0 | 216 |
| 30 | `gcc-lib:libc.a(libc_a-fopen.o)` | 488 | 0 | 0 | 0 | 488 |
| 31 | `gcc-lib:libc.a(libc_a-fprintf.o)` | 136 | 0 | 0 | 0 | 136 |
| 32 | `gcc-lib:libc.a(libc_a-fputc.o)` | 472 | 0 | 0 | 0 | 472 |
| 33 | `gcc-lib:libc.a(libc_a-fputs.o)` | 408 | 0 | 0 | 0 | 408 |
| 34 | `gcc-lib:libc.a(libc_a-fread.o)` | 1,000 | 0 | 0 | 0 | 1,000 |
| 35 | `gcc-lib:libc.a(libc_a-freer.o)` | 1,200 | 0 | 0 | 0 | 1,200 |
| 36 | `gcc-lib:libc.a(libc_a-fscanf.o)` | 136 | 0 | 0 | 0 | 136 |
| 37 | `gcc-lib:libc.a(libc_a-fseek.o)` | 32 | 0 | 0 | 0 | 32 |
| 38 | `gcc-lib:libc.a(libc_a-fseeko.o)` | 1,576 | 0 | 0 | 0 | 1,576 |
| 39 | `gcc-lib:libc.a(libc_a-fstatr.o)` | 120 | 0 | 0 | 0 | 120 |
| 40 | `gcc-lib:libc.a(libc_a-fvwrite.o)` | 1,392 | 0 | 0 | 0 | 1,392 |
| 41 | `gcc-lib:libc.a(libc_a-fwalk.o)` | 200 | 0 | 0 | 0 | 200 |
| 42 | `gcc-lib:libc.a(libc_a-gdtoa-gethex.o)` | 3,176 | 256 | 0 | 0 | 3,432 |
| 43 | `gcc-lib:libc.a(libc_a-gdtoa-hexnan.o)` | 1,424 | 0 | 0 | 0 | 1,424 |
| 44 | `gcc-lib:libc.a(libc_a-getenv_r.o)` | 376 | 0 | 0 | 0 | 376 |
| 45 | `gcc-lib:libc.a(libc_a-gettimeofdayr.o)` | 120 | 0 | 0 | 0 | 120 |
| 46 | `gcc-lib:libc.a(libc_a-gettzinfo.o)` | 16 | 0 | 88 | 0 | 104 |
| 47 | `gcc-lib:libc.a(libc_a-gmtime_r.o)` | 1,440 | 0 | 0 | 0 | 1,440 |
| 48 | `gcc-lib:libc.a(libc_a-impure.o)` | 0 | 0 | 292 | 0 | 292 |
| 49 | `gcc-lib:libc.a(libc_a-isalpha.o)` | 24 | 0 | 0 | 0 | 24 |
| 50 | `gcc-lib:libc.a(libc_a-isattyr.o)` | 112 | 0 | 0 | 0 | 112 |
| 51 | `gcc-lib:libc.a(libc_a-isspace.o)` | 24 | 0 | 0 | 0 | 24 |
| 52 | `gcc-lib:libc.a(libc_a-iswspace.o)` | 8 | 0 | 0 | 0 | 8 |
| 53 | `gcc-lib:libc.a(libc_a-iswspace_l.o)` | 40 | 0 | 0 | 0 | 40 |
| 54 | `gcc-lib:libc.a(libc_a-lcltime.o)` | 16 | 0 | 0 | 0 | 16 |
| 55 | `gcc-lib:libc.a(libc_a-lcltime_r.o)` | 1,272 | 0 | 0 | 0 | 1,272 |
| 56 | `gcc-lib:libc.a(libc_a-locale.o)` | 320 | 0 | 364 | 0 | 684 |
| 57 | `gcc-lib:libc.a(libc_a-localeconv.o)` | 40 | 0 | 0 | 0 | 40 |
| 58 | `gcc-lib:libc.a(libc_a-lseekr.o)` | 120 | 0 | 0 | 0 | 120 |
| 59 | `gcc-lib:libc.a(libc_a-makebuf.o)` | 512 | 0 | 0 | 0 | 512 |
| 60 | `gcc-lib:libc.a(libc_a-malign.o)` | 24 | 0 | 0 | 0 | 24 |

## Top 60 functions by retained size (map `.text.*`)

| # | Function | Bytes | Source |
|---:|---|---:|---|
| 1 | `vehicle_update` | 11,968 | `source/units/vehicles.c` |
| 2 | `ai_communication_event` | 10,520 | `source/ai/ai_communication.c` |
| 3 | `observer_update` | 8,868 | `source/camera/observer.c` |
| 4 | `actor_perception_update` | 8,720 | `source/ai/actor_perception.c` |
| 5 | `unit_update` | 8,460 | `source/units/units.c` |
| 6 | `projectile_update` | 8,440 | `source/items/projectiles.c` |
| 7 | `game_engine_rasterize_in_game_score` | 7,492 | `source/game/game_engine.c` |
| 8 | `object_compute_node_matrices` | 7,220 | `source/objects/objects.c` |
| 9 | `actor_move_update` | 7,056 | `source/ai/actor_moving.c` |
| 10 | `player_control_update` | 6,876 | `source/game/player_control.c` |
| 11 | `tag_block_get_element_fast` | 6,840 | `source/ai/action_alert.c` |
| 12 | `biped_update_physics` | 6,700 | `source/units/bipeds.c` |
| 13 | `actor_select_firing_position` | 6,632 | `source/ai/actor_firing_position.c` |
| 14 | `decal_new_from_collision` | 6,524 | `source/effects/decals.c` |
| 15 | `actor_look_update` | 6,272 | `source/ai/actor_looking.c` |
| 16 | `object_cause_damage` | 5,844 | `source/objects/damage.c` |
| 17 | `biped_update` | 5,672 | `source/units/bipeds.c` |
| 18 | `biped_update_moving` | 5,644 | `source/units/bipeds.c` |
| 19 | `physics_update` | 5,412 | `source/physics/physics.c` |
| 20 | `main_loop` | 5,180 | `source/main/main.c` |
| 21 | `collision_move_point` | 5,176 | `source/physics/collisions.c` |
| 22 | `effect_update` | 5,136 | `source/effects/effects.c` |
| 23 | `actor_combat_update` | 5,112 | `source/ai/actor_combat.c` |
| 24 | `players_update_before_game` | 5,088 | `source/game/players.c` |
| 25 | `actor_move_vector_avoidance` | 5,072 | `source/ai/actor_moving.c` |
| 26 | `normalize3d` | 4,888 | `closure:ps2_abi.o` |
| 27 | `weapon_update` | 4,832 | `source/items/weapons.c` |
| 28 | `build_structure_lens_flares` | 4,688 | `source/structures/structure_lens_flares.c` |
| 29 | `lightning_submit` | 4,464 | `source/objects/widgets/lightning.c` |
| 30 | `action_obey_command_begin` | 4,424 | `source/ai/action_obey.c` |
| 31 | `infection_swarm_control` | 4,136 | `source/ai/actor_type_infection.c` |
| 32 | `path_state_traverse` | 4,100 | `source/ai/path.c` |
| 33 | `breakable_surface_effect` | 4,060 | `source/physics/breakable_surfaces.c` |
| 34 | `glow_submit` | 3,852 | `source/objects/widgets/glow.c` |
| 35 | `hud_draw_screen` | 3,792 | `source/interface/hud.c` |
| 36 | `object_new` | 3,784 | `source/objects/objects.c` |
| 37 | `prop_status_refresh` | 3,740 | `source/ai/actor_perception.c` |
| 38 | `render_weapon_hud` | 3,716 | `source/interface/hud_weapon.c` |
| 39 | `vector_from_points3d` | 3,696 | `closure:ps2_abi.o` |
| 40 | `hud_render_unit_interface` | 3,648 | `source/interface/hud_unit.c` |
| 41 | `input_abstraction_update` | 3,636 | `source/input/input_abstraction.c` |
| 42 | `action_charge_perform` | 3,564 | `source/ai/action_charge.c` |
| 43 | `players_update_after_game` | 3,548 | `source/game/players.c` |
| 44 | `hud_draw_static_element` | 3,520 | `source/interface/hud_draw.c` |
| 45 | `update_channels` | 3,460 | `source/sound/sound_manager.c` |
| 46 | `hud_messaging_update` | 3,412 | `source/interface/hud_messaging.c` |
| 47 | `sound_render` | 3,356 | `source/sound/sound_manager.c` |
| 48 | `physics_compute_unit_collisions` | 3,340 | `source/physics/physics.c` |
| 49 | `encounter_update_status` | 3,288 | `source/ai/encounters.c` |
| 50 | `game_engine_update` | 3,256 | `source/game/game_engine.c` |
| 51 | `actor_emotion_update` | 3,216 | `source/ai/actor_perception.c` |
| 52 | `biped_limp_noodle_move_relax_and_constrain_positions` | 3,164 | `source/units/biped_limp_noodle.c` |
| 53 | `render_camera_build_frustum` | 3,132 | `source/render/render_cameras.c` |
| 54 | `startup.main` | 3,048 | `parent:60869cbb0e20/stream/hcu_main.c` |
| 55 | `cross_product3d` | 2,960 | `closure:ps2_abi.o` |
| 56 | `hcu_map_service_preflight` | 2,856 | `parent:60869cbb0e20/stream/hcu_map_service.c` |
| 57 | `particle_system_update` | 2,844 | `source/effects/particle_systems.c` |
| 58 | `magnitude_squared3d` | 2,808 | `closure:ps2_abi.o` |
| 59 | `crosshairs_draw` | 2,804 | `source/interface/hud_weapon.c` |
| 60 | `actor_action_handle_lost_contact` | 2,800 | `source/ai/actions.c` |

## Candidate classes (PS2-unreachable in multiplayer)

Each class is a set of source files by path pattern (`build/m2-c2-r7-elf-attrib/candidates.json`). **Own** is the reachable bytes of the class's own nodes (the conservative figure). **Removed** is the bytes that disappear from the reachable image if the class's nodes are blocked, including nodes only they reach (an upper bound: it counts callees that a real cut would have to keep or stub).

| Class | Files | Own (B) | Removed upper bound (B) | Callers that must be cut or stubbed (top) |
|---|---:|---:|---:|---|
| a1-editor-debug | 12 | 39,591 | 55,588 | `source/hs/hs_globals_external.c` (147), `source/ai/ai_script.c` (75), `source/ai/ai.c` (25), `source/ai/ai_communication.c` (24) |
| a2-xbox-platform | 7 | 36,021 | 276,307 | `source/saved games/saved_game_files.c` (59), `source/hs/hs_compile.c` (45), `source/units/units.c` (35), `source/objects/objects.c` (33) |
| a3-campaign-ai-cutscene | 15 | 31,629 | 32,046 | `source/hs/hs.c` (19), `source/game/game.c` (9), `source/ai/actor_types.c` (8), `source/camera/director.c` (4) |
| union of the three | 34 | — | 357,770 | — |

### a1-editor-debug: files and removed bytes by source

Files: `source/ai/ai_debug.c`, `source/camera/editor_flying_camera.c`, `source/camera/flying_camera.c`, `source/cseries/debug_memory.c`, `source/dialogs/edit_text.c`, `source/game/cheats.c`, `source/game/game_statistics.c`, `source/input/HaloAutoTest.c`, `source/interface/terminal.c`, `source/main/console.c`, `source/main/debug_keys.c`, `source/physics/collision_debug.c`

| Removed (B) | Source |
|---:|---|
| 13,612 | `source/ai/ai_debug.c` |
| 5,559 | `source/camera/editor_flying_camera.c` |
| 5,276 | `source/hs/hs_compile.c` |
| 4,819 | `source/cseries/debug_memory.c` |
| 4,380 | `source/main/console.c` |
| 4,009 | `source/hs/hs.c` |
| 2,361 | `source/game/cheats.c` |
| 2,331 | `source/camera/flying_camera.c` |
| 2,197 | `source/tag_files/files_windows.c` |
| 1,774 | `source/interface/terminal.c` |

Example root paths (first two of the largest blocked nodes):

- `source_ai_ai_debug.c.o` `.rodata.ai_debug_render_actor.str1.8`: `.text.halo_shell_main` → `.text.main_loop` → `.text.debug_keys_initialize` → `.data.global_debug_key_list` → `.text.debug_key_select_next_encounter` → `.text.ai_debug_change_selected_encounter` → `.rodata.ai_debug_render_actor.str1.8`
- `source_ai_ai_debug.c.o` `.text.ai_debug_update`: `.text.game_tick` → `.text.ai_update` → `.text.ai_debug_update`

### a2-xbox-platform: files and removed bytes by source

Files: `source/bungie_net/common/thread_win32.c`, `source/cseries/cseries_windows.c`, `source/input/input_xbox.c`, `source/saved games/game_state_xbox.c`, `source/shell/shell_xbox.c`, `source/sound/sound_dsound_xbox.c`, `source/tag_files/files_windows.c`

| Removed (B) | Source |
|---:|---|
| 24,839 | `source/game/game_engine.c` |
| 21,526 | `source/game/player_queues_new.c` |
| 14,943 | `source/sound/sound_dsound_xbox.c` |
| 14,797 | `source/interface/hud_draw.c` |
| 13,101 | `source/main/main.c` |
| 9,910 | `source/game/player_control.c` |
| 8,613 | `source/interface/hud_weapon.c` |
| 7,527 | `source/interface/hud.c` |
| 6,890 | `source/input/input_xbox.c` |
| 6,550 | `source/interface/motion_sensor.c` |

Example root paths (first two of the largest blocked nodes):

- `source_sound_sound_dsound_xbox.c.o` `.text.dsound_initialize`: `.text.halo_shell_main` → `.text.shell_initialize` → `.text.sound_initialize` → `.data.platform_definitions` → `.data.platform_sound_dsound` → `.text.dsound_initialize`
- `source_bungie_net_common_thread_win32.c.o` `.bss.thread_globals`: `.text.game_initialize` → `.text.saved_game_files_initialize` → `.text.create_mutex` → `.bss.thread_globals`

### a3-campaign-ai-cutscene: files and removed bytes by source

Files: `source/ai/actor_type_carrier.c`, `source/ai/actor_type_crew.c`, `source/ai/actor_type_engineer.c`, `source/ai/actor_type_flood.c`, `source/ai/actor_type_hunter.c`, `source/ai/actor_type_infection.c`, `source/ai/actor_type_mounted_weapon.c`, `source/ai/actor_type_sentinel.c`, `source/camera/camera_scripting.c`, `source/cutscene/cinematics.c`, `source/cutscene/recorded_animation_definitions.c`, `source/cutscene/recorded_animation_initialize.c`, `source/cutscene/recorded_animation_playback.c`, `source/cutscene/recorded_animation_playback_v1.c`, `source/cutscene/recorded_animations.c`

| Removed (B) | Source |
|---:|---|
| 6,559 | `source/ai/actor_type_infection.c` |
| 4,955 | `source/cutscene/recorded_animation_playback_v1.c` |
| 4,921 | `source/cutscene/recorded_animation_playback.c` |
| 3,739 | `source/cutscene/recorded_animations.c` |
| 3,694 | `source/camera/camera_scripting.c` |
| 2,348 | `source/ai/actor_type_flood.c` |
| 1,416 | `source/cutscene/cinematics.c` |
| 666 | `source/cutscene/recorded_animation_initialize.c` |
| 617 | `source/ai/actor_type_engineer.c` |
| 613 | `source/ai/actor_type_crew.c` |

Example root paths (first two of the largest blocked nodes):

- `source_ai_actor_type_infection.c.o` `.text.infection_swarm_control`: `.text.actors_update` → `.text.actor_type_swarm_control` → `.text.actor_type_definition_get` → `.rodata.actor_type_definitions` → `.data.actor_type_infection` → `.text.infection_swarm_control`
- `source_camera_camera_scripting.c.o` `.text.scripted_camera_update`: `.text.game_tick` → `.text.first_person_weapons_update` → `.text.director_get_perspective` → `.text.scripted_camera_update`

## Ranked reduction plan

Sums are over disjoint items; the class union is used where classes overlap. Items are ranked by conservative (own) bytes, with the upper bound in brackets.

| Rank | Item | Recoverable (B) | Keeps it alive / what must change | Confidence |
|---:|---|---:|---|---|
| 1 | a1 editor/debug (`ai_debug.c`, `editor_flying_camera.c`, `flying_camera.c`, `debug_memory.c`, `console.c`, `debug_keys.c`, `cheats.c`, `collision_debug.c`, `terminal.c`, `HaloAutoTest.c`, `dialogs/*`, `game_statistics.c`) | 39,591 [55,588] | Roots `halo_shell_main` → `main_loop` → `debug_keys_update`, `game_tick` → `ai_update` → `ai_debug_update`, `game_initialize` → `cheats_initialize`. `hs_globals_external.c` (147 refs) and `ai_script.c` (75) reference the debug globals and must be stubbed. | medium: the callers are table entries, not logic |
| 2 | a3 campaign cutscene and campaign-only actor types (`cutscene/*`, `actor_type_{flood,infection,hunter,sentinel,crew,engineer,carrier,mounted_weapon}.c`, `camera_scripting.c`) | 31,629 [32,046] | Roots `game_tick` → `first_person_weapons_update` → `director_get_perspective` → `scripted_camera_update`; `actors_update` → `actor_type_swarm_control` → `infection_swarm_control`. Callers `hs.c` (22), `game.c` (13), `actor_types.c` (8) need the type tables and the script hooks stubbed. `director.c` is excluded: the normal camera uses it. | medium-low: the flood and infection types may be needed by the campaign scripts that share MP maps |
| 3 | a2 Xbox platform files (`shell_xbox.c`, `sound_dsound_xbox.c`, `input_xbox.c`, `game_state_xbox.c`, `thread_win32.c`, `files_windows.c`, `cseries_windows.c`) | 36,021 [276,307] | Only the conservative figure is credible. The upper bound removes `game_engine.c`, `hud_draw.c` and the rest of the menu-to-game path, because `halo_shell_main` reaches the game through `shell_initialize`. Cutting these files needs the PS2 port's replacements, not a root change. | low (needs replacement modules) |
| — | Union of 1–3 (overlap removed) | 357,770 | Upper bound; the conservative sum is 107,241 | low–medium |
| — | Map residual, bss (`COMMON` gaps) | 501,623 | Unattributed by this map: a `COMMON` block in `rooted.o` lists only some symbols, and the declared object sizes do not cover the header total. Needs a map from the same link as the ELF. | unknown |
| — | Map residual, rodata (merged `.rodata.str1.*`) | 259,626 | Merged string bytes that ld reports on no input section. Attribution would need each object's `.rodata.str1.*` sizes after deduplication. | unknown |

Needed, not in the plan: the tag validator's and tag schema's bss (`tag_validate.c` 262,273; `tag_schema_effects.c` 262,544), the BSP renderer and PS2 render state (`ps2_render.c` 201,364 in the variant ELF, not in this map), `hs.c` scripting, `units.c`, and the parent `core/mem.c`. These serve every map and are not multiplayer-specific.

## Gap to 979,064 B

- Attributable and classed: 107,241 B conservative, 357,770 B upper bound.
- Shortfall to the goal: 871,823 B conservative, 621,294 B even at the upper bound.
- Closing it needs the 761,249 B of residual attributed (bss and rodata), which requires a map from a consistent link. Without that, no claim above 357,770 B is supported.

## Caveats

- The map is not from the same link as the ELF and the closure objects were rewritten during the run (see Inputs). Results describe the map in `build/m2-c2-r7-elf-attrib/`.
- Name collisions: `-fcommon` names are resolved by name to their first declaring object. `render` and `ai_debug` are declared 8 bytes in the closure objects but linked at 201 KB and 236 KB in the variant ELF. The map does not give their owners.
- Removal estimates use pre-LTO section sizes (`objdump -h`) from the closure objects. The map's sizes are post-LTO, so the two differ by a few percent of the candidate bytes.
- Reachability is computed over the relocation graph (`objdump -r`). It does not model data written through pointers, so it can over-keep and under-remove.
- `.rodata` string merging is the reason the map's section sizes are relaxed. The tool reads the `(size before relaxing)` line; four entries were corrected this way.
- Parent objects: `parent:` labels point at `submodules/halo-ps2/engine/src/<path>.c` by relative path; they were not checked one by one.

## Reproduce

```sh
python3 -I tools/c2_elf_text_attribution.py --map build/m2-c2-r7-elf-attrib/hcu-gameplay-machine.map \
    --closure build/m2-c2-r7-elf-attrib/closure-snapshot \
    --objdump build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-objdump \
    --candidates build/m2-c2-r7-elf-attrib/candidates.json --out-json build/m2-c2-r7-elf-attrib/run.json
python3 -I tests/test_c2_elf_text_attribution.py
```

The committed JSON is `run.json` with the sections list removed and the input hashes added (`all_sources_bytes` and `residual` are derived from it).
