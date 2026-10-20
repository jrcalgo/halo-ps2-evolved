# CE main-menu shell and UI processing roots

Status: five rooted calls remain pending. Their behavior controls local menu/input/game transitions; the shell is not equivalent to the renderer.

## Trace

| Root | CE behavior and caller | PS2 issue |
|---|---|---|
| `main_menu_active` | Stores the main-menu state in `we_are_at_the_main_menu` (`source/interface/ui_widget.c:1940-1945`); main transitions call it from `source/main/main.c:1122,1546,1952`. | Must share a single authoritative state with menu shell and local-game transitions. |
| `main_menu_is_active` | Reads that state (`ui_widget.c:1948-1953`). Used by controller-disconnect/input policy (`source/input/input_abstraction.c:768+`), player spawn/queue behavior (`source/game/player_queues_new.c:951-963`), and player logic (`source/game/players.c:4824`). | Returning false changes control/player lifecycle; returning true can suppress in-game input. |
| `main_screen_shell_begin_fade` | Stops menu music, marks active non-error widgets to close after a fade, computes their remaining fade duration, and disposes navigation stacks (`ui_widget.c:3001-3024`). | Requires coherent fade timer and widget ownership, not simply a GS black overlay. |
| `main_screen_shell_load` | Uninhibits processing, may start intro Bink on first load, performs filesystem initialization, resets attract/input timers, closes old UI, loads menu root, and dispatches deferred errors/music (`ui_widget.c:4909+`). | Must define PS2 startup UI and save/service behavior; excluding Bink does not establish equivalent shell initialization. |
| `process_ui_widgets` | Each call updates system time, input/mouse events, filesystem-thread completion/error state, progress/keyboard/attract-mode gates, active widgets, modal/pause state, and UI actions (`ui_widget.c:8434+`). Called in the main loop (`source/main/main.c:3294,3617`). | No-op loses UI-driven controls/transitions; thread/storage services and the event bridge must be qualified. |

These dependencies connect to the prior widget lifecycle review: `ui_widget.c` is excluded in `port/ps2/port.json:46-65`; its rooted functions are placeholders in the selected PS2 link. The M1 run reaching `m1-ui-map-request` does not establish a functioning menu shell or processing loop. Bink and filesystem worker threads can be replaced by deliberate PS2 policies, but their state transitions must remain explicit.

## Acceptance needed

1. Implement a bounded, single-owner menu-active/widget lifecycle state with transition tests (menu->map, map->pause/menu, local player join/leave).
2. Route PS2 controller events through the CE UI/event path and verify disconnect/insert plus widget-active control behavior.
3. Test fade begin/load with deterministic timers and ensure old map-owned widget/tag references are gone before cache unload.
4. Decide startup intro/movie behavior separately from shell initialization. Prove deferred error and filesystem status semantics even if persistent storage is unavailable.
5. Keep all five ledger entries pending until the PS2 owner and integration tests exist.

## Sources

- `submodules/halo-ce-universal/source/interface/ui_widget.c:1940-1953,3001-3024,4909+,8434+`
- `submodules/halo-ce-universal/source/main/main.c:1122,1523,1546,1952,3294,3617`
- `submodules/halo-ce-universal/source/input/input_abstraction.c:768+`
- `submodules/halo-ce-universal/source/game/player_queues_new.c:951-963`
- `submodules/halo-ce-universal/source/game/players.c:4824`
- `submodules/halo-ce-universal/port/ps2/port.json:46-65`
