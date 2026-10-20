# CE UI widget lifecycle and control roots

Status: ten roots remain pending; `ui_widgets_safe_to_load` is source-proven to have no runtime effect and is approved as an empty CE behavior.

## Findings

The PS2 manifest explicitly excludes `source/interface/ui_widget.c` (`port/ps2/port.json:46-65`), so the CE implementation is a comparison reference rather than code linked into the PS2 image. The APIs below are currently unresolved external placeholders. They are not uniformly drawing calls: they own UI memory, active-widget stacks, input gating, pause policy, fade state, and object creation. This is a substantial integration gap, not merely an adapter/detail issue.

| Root | CE behavior | M0 disposition |
|---|---|---|
| `ui_widgets_initialize` | Allocates `WIDGET_MEMORY_POOL_SIZE`, resets globals/deferred errors, records allocation success, initializes fade state (`source/interface/ui_widget.c:2163-2196`). | Pending: real bounded pool and failure semantics required. |
| `ui_widgets_dispose` | Closes active widgets, releases widget pool, clears globals (`2198-2208`). | Pending: teardown and allocation ownership required. |
| `ui_widgets_close_all` | Closes virtual keyboard, deletes per-player widgets, disposes navigation stacks (`2912-2933`). | Pending: map-transition/player UI lifecycle and ordering required. |
| `ui_widget_load_by_name_or_tag` | Resolves tag/name, allocates widget instance from widget pool, builds/pushes UI object (`3897+`). | Pending: no-op would remove reachable UI creation; bound pool/tag fixture needed. |
| `ui_widgets_active_for_local_player` | Scans active widget roots and reports whether a local player's UI is active (`4369-4396`); called by player-control update (`source/game/player_control.c:620`). | Pending: affects input/control behavior; cannot be replaced with false. |
| `ui_widgets_inhibit_processing` | Asserts initialized and sets `processing_inhibited` (`source/interface/ui_widget.c:1660-1672`). | Pending: map transition ordering must gate widget processing. |
| `ui_widgets_disable_pause_game` | Asserts nonnegative ticks and sets `pause_disabled_ticks` (`2031-2043`). | Pending: pause/game-time arbitration is behavioral state. |
| `ui_widgets_set_fade_value` | Writes `fade_to_black`, read by widget presentation (`1852-1860`). | Pending: map transition fade must remain coherent with parent snapshot renderer. |
| `ui_widget_load_progress_widget` | Calls `_error_silent` with text stating the legacy progress screen was replaced (`source/interface/ui_widget.c:1954-1962`); called from `game_unload` (`source/game/game.c:749`). | Pending: verify `_error_silent` is diagnostic-only under the PS2 provider before omitting. |
| `ui_widgets_safe_to_load` | Function body only returns; its `safe` argument is not read (`source/interface/ui_widget.c:1654-1658`). | `excluded-proven`: exact no-op is source behavior. |

The fast setup call path is especially important: `player_ui_fast_setup_network_server` closes widgets, disposes network-server/client state, sets local connection, then creates the connected-pregame widget (`source/interface/player_ui.c:654-682`). A false-success widget loader or no-op close would leave a broken menu/session transition. This report does not disposition those APIs as “render-only.”

## Regression contract

`tests/test_hcu_external_review.py::test_ui_widget_lifecycle_roots_keep_stateful_owners_pending` checks the selected source manifest, the exact empty `safe_to_load` body, and that stateful lifecycle/input/pause/fade/load roots remain pending with rationale and evidence. Completion still requires a bounded widget-pool implementation, local-player widget/input fixture, map-transition teardown ordering, and a source-backed `_error_silent` disposition.

## Sources

- `submodules/halo-ce-universal/port/ps2/port.json:61-65`
- `submodules/halo-ce-universal/source/interface/ui_widget.c:1654-1672,1852-1860,1954-1962,2031-2043,2163-2208,2912-2933,3897+,4369-4396`
- `submodules/halo-ce-universal/source/interface/player_ui.c:654-682`
- `submodules/halo-ce-universal/source/game/player_control.c:620`
- `submodules/halo-ce-universal/source/game/game.c:749`
- `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
