# M0 rooted `attract_mode_start` state-transition review

The rooted caller is the HaloScript `attract_mode_start` evaluator in
`source/hs/hs.c`. The CE implementation in `source/interface/attract_mode.c`
does more than request video: it chooses a movie index, stops menu music,
starts Bink playback, and if playback is inactive sets
`attract_mode_countdown_timer = system_milliseconds()`.

The current PS2 Bink state deliberately reports no active playback. Therefore
the retail function would still perform a meaningful countdown-state update
on PS2 even though its movie cannot render. The generated empty
`attract_mode_start` body loses that transition and may change menu behavior.
Neither the Bink exclusion nor the fact that this is a UI/attract path proves
that the whole function is safe to omit.

Keep the symbol pending until the PS2 presentation owner selects an explicit
policy: preserve the countdown/music state without video, or remove/disable the
script/UI path and prove it unreachable for the accepted local-game product.
Add a state/timer test for whichever policy is chosen. This review does not
require Bink movie playback for M1 and does not approve any Bink implementation.
