# M0 rooted platform configuration hook review

Four `config_*` symbols are rooted in the selected PS2 link and remain
pending: `config_boolean`, `config_changes`, `config_real`, and `config_string`.
The Linux configuration engine itself is not a PS2 product dependency, but
the CE callsites that consume these hooks cannot all be dismissed as UI.

`source/units/units.c::unit_animation_enhanced` starts with
`enhanced = TRUE`, watches `config_changes()`, and when settings are first
read assigns `config_boolean("game.enhanced_animations") != 0`. It returns
that setting for `cyborg` and `cyborg_mp`; rooted biped and unit animation
paths call it. The generated PS2 `config_boolean` returns zero, so the first
query disables this enhanced-animation behavior instead of keeping the CE
port's enabled default. This is a concrete source parity difference. Whether
the PS2 product wants a fixed-true CE default, explicit per-console config, or
another stable setting owner must be decided and tested; returning zero by
accident is not an acceptable policy.

`source/sound/sound_manager.c::sound_manager_port_volume` reads real
`audio.music_volume` and `audio.effects_volume` settings and caches them
against `config_changes()`. `sound_manager_master_gain` multiplies this
platform gain into actual channel properties. Until M14 supplies the PS2
sound owner, a zero real-return can become a mute multiplier. This remains a
separate sound mix concern from Windows DirectSound exclusion.

`source/interface/terminal.c::terminal_shows` reads
`game.console_log` once and caches whether chatter/important/serious terminal
messages should appear. It is diagnostic filtering, but the PS2 diagnostic
policy and string lifetime still need an explicit owner; it must not suppress
the backing error/assert state.

Keep all four rows pending. Add a deliberate PS2 configuration/default owner
with tests for animation default and selected class, config-change invalidation,
sound gain defaults/volume endpoints when M14 is connected, terminal severity
filtering, and stable string storage. Do not port the Linux config UI/parser
solely to satisfy these four hooks.

Regression anchor:
`tests/test_hcu_external_review.py::test_platform_config_hooks_include_gameplay_animation_parity_and_remain_pending`.
