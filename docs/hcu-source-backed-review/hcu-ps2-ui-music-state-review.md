# M0/M1 main-menu music state review

The only live rooted callers in this closure are
`source/main/main.c::main_change_map_name`. The query
`ui_main_menu_music_active()` controls an optional one-second fade/wait before
transitioning away from the main-menu scenario. If false, the transition
proceeds immediately; `ui_stop_main_menu_music()` is called at the normal
transition boundary regardless. The current PS2 sound preference is `-1`, so
no music backend can have started a menu track in M1.

Accordingly, the `ui_main_menu_music_active` PS2 state adapter returns false,
and `ui_stop_main_menu_music` is an excluded no-op for this no-audio M1 profile.
This preserves local map-transition progress without falsely delaying for
audio that is not playing. It does not approve music-start/play/query behavior
for a future SPU2 implementation; M14 must re-audit those surfaces with actual
audio state.

`test_m1_menu_music_state_does_not_block_map_change` verifies the sole rooted
caller, the transition's false-query path, generated state/no-op bodies, and
disabled PS2 audio platform.
