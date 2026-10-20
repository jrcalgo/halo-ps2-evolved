# Linux mouse and touch overlays on the PS2 pad path

Status: all five roots are `state-adapter` false. A zero result leaves the DualShock look and move values already written. Re-open before adding a mouse or touch device.

## Call sites

The generated bodies return 0 (`build/hcu-ps2-closure/all/ps2_platform.c`). `HALO_LINUX` is unset. The calls that survived in the rooted image are port overlays, and each one runs only when the predicate is true.

| Root | Caller | Effect of a false result |
|---|---|---|
| `halo_linux_touch_look` | `player_control_update` (`source/game/player_control.c:1215-1224`) | Does not add swipe or gyro into `look_delta`. Stick look above this block remains. |
| `halo_linux_mouse_aiming` | `player_control_update` (`1286-1292`) | Does not clear `magnetism_level`. Magnetism still applies to the pad. |
| `halo_linux_touch_aiming` | Same `if` as mouse aiming. | Same. Either true result would suppress magnetism. |
| `halo_linux_mouse_look` | `player_control_update` (`1336-1340`) | Does not replace `facing_delta` with a mouse delta. |
| `halo_linux_touch_move` | `input_abstraction_update` (`source/input/input_abstraction.c:277-287`) | Does not overwrite `forward_movement` or `strafe` after the keyboard contribution. |

False is the pad-only profile: no mouse and no touch stick. It is not a claim that those devices are implemented. The keyboard-actions review used the same standard for a zero key mask.

## Regression

`tests/test_hcu_external_review.py::test_linux_input_overlays_stay_false_on_the_pad_path` checks the five predicates, the zero generated results, and the ledger rows.
