# Platform leftovers outside the network session

Status: map-share idle, the endgame-sound delay, the demo launcher, and the D3D flip counter are closed for this profile. DirectSound storage, the PC menu path, the profile index, the next campaign level, and the Xbox nickname stay pending.

## Closed for this profile

`map_share_downloading` is the Linux download predicate (`port/linux/game/map_share.c:1481-1487`). `cache_files_give_time_to_precache` returns before precache only when it is true (`source/cache/cache_files.c:1177-1180`). The PS2 manifest does not compile `map_share.c`. False is "no download in progress," so local precache is not deferred. `map_share_update` runs from `main_loop` (`source/main/main.c:3581`) and advances share files, peer answers, and download end (`map_share.c:3339-3357`). With no share session, the empty body does not change CE precache or the local connection. Re-open both if a PS2 map-share client is linked.

`timeout_for_endgame_sound` is written by `game_engine_initialize_for_new_map` (`source/game/game_engine.c:7389`), CTF init (`source/game/game_engine_ctf.c:468`), and race init (`source/game/game_engine_race.c:1491`). No selected source reads it. The generated `long` is storage for those writes. It does not gate sound playback in this image.

`xbox_demos_launch` launches `d:\XDemos\XDemos.xbe` and then loops forever when demos exist (`source/interface/marketing_and_strategic_business_development.c:51-66`). The only rooted caller is `main_run_demos_private`, which clears `run_xdemos` before the call (`source/main/main.c:2257-2261`). The empty body does not start another executable and does not change the campaign map.

`d3d_find_flipcount` is covered with the fatal-screen review's frame-rate overlay. This row uses that same evidence: the null result selects the handler branch that does not sample flip deltas (`main.c:1837-1840,2897`).

## Still pending

`dsound_globals` is the Xbox DirectSound device object (`source/sound/sound_dsound_xbox.c:141-318`). Channel get, callback, location, properties, dispose, end scene, flush, initialize, listener, pause, and virtual queue all read it. The generator emits `unsigned char dsound_globals[30924]` (`tools/hcu_ps2_link.py`). The DirectSound exclusion review already removed the playback dispatch for `platform=-1`. This object is still the device record those channel calls expect. A zero array does not establish initialized, channel, or pause state. Keep it pending with the sound-cache rows.

`pc_menus_screen` is the path argument to `ui_widget_load_by_name_or_tag` inside `player_ui_fast_setup_network_server` (`source/interface/player_ui.c:662-669`). The generated NULL fails that load. The widget loader itself is still pending. Do not treat a NULL path as a successful menu.

`reset_last_player1_profile_index` stores `NONE` into `event_handler_functions.last_player1_profile_index` (`source/interface/ui_widget_event_handler_functions.c:1771-1775`). The rooted caller is `delete_enumerated_saved_game_file` (`source/saved games/saved_game_files.c:1578`). An empty stub leaves the last profile index unchanged after a delete. The saved-profile UI owner is not approved.

`ui_set_next_level` is the local campaign win path, after the network co-op branch returns (`source/main/main.c:2399-2409`). A valid level calls `main_set_map_name`; `NONE` rolls credits (`source/interface/ui_widget.c:2086-2107`). An empty stub drops the next-level transition.

`xbox_set_machine_name` converts the script string and calls `XSetNicknameW` (`source/networking/network_game_manager.c:232-243`). The rooted caller is the HaloScript evaluator (`source/hs/hs.c:15102`). The empty body reports neither the nickname nor the CE error. There is no PS2 nickname store.

## Regression

`tests/test_hcu_external_review.py::test_platform_leftovers_keep_campaign_and_sound_state_pending` locks the idle map-share predicate, the write-only sound delay, and the five pending rows.
