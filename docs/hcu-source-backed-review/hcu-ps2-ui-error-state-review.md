# M0 UI error/help state call-family review

These rooted UI entry points have state or control-flow effects in addition to
displaying pixels, so the generated no-op bodies are not approved as harmless
render omissions.

- `display_error_deferred` stores a per-player error code, modal flag, and
  pause-game-time flag. The input abstraction calls it on controller removal;
  later UI processing consumes the record. A no-op can suppress the requested
  pause and leave the user without the disconnect state.
- `display_error_when_main_menu_loaded` stores an error for a future main-menu
  transition. Its current rooted caller handles network-host loss before
  aborting the network session. Its exact reachability in all PS2 modes is
  still unreviewed, so do not blanket-exclude it as networking.
- `display_errors_deferred_until_cinematic_stop` drains and clears queued
  per-player cinematic errors, preserving their modal/pause settings. A no-op
  retains stale state and loses the error at the cinematic boundary.
- `display_error_damaged_media` is an abort path called for cache/map status 2.
  It queues a damaged-media dashboard error, closes the input frame, and enters
  `main_loop_of_death`. If the generated no-op returns, cache failure callers
  continue cleanup or load logic instead of halting/recovering.
- `display_scenario_help` is a HaloScript-visible campaign function. It maps
  the active scenario to authored help widgets and opens one. The no-op loses
  campaign behavior until the PS2 UI/tag path can host that content.

All five remain `pending`. M1's lack of a full UI renderer does not justify
discarding modal/pause state, fatal load handling, or campaign script effects.
Each needs a PS2 state owner and tests for state consumption/control flow;
scenario help additionally needs a qualified presentation path. The exact
rooted call sites and these risk findings are locked by
`test_ui_error_entry_points_are_stateful_and_remain_pending`.
