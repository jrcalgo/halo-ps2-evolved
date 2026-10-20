# CE virtual-keyboard roots under the PS2 local pad profile

Status: `virtual_keyboard_active` is approved as the explicit inactive local-pad state adapter; `virtual_keyboard_close` is approved as unreachable in the current rooted path. Re-open both before adding virtual text entry or UI/profile editing.

## Evidence and boundary

The PS2 manifest excludes both `source/interface/virtual_keyboard.c` and the UI widget implementation (`port/ps2/port.json:46-65`). The linked rooted closure identifies exactly one live caller for each symbol: `input_abstraction_update` in `source/input/input_abstraction.c`. Its call is conditional: only if a controller disconnect error is to be displayed does it query `virtual_keyboard_active`; it calls `virtual_keyboard_close` only when that predicate is true (`input_abstraction.c:816-824`).

The CE implementation's active query returns `virtual_keyboard_globals.active` (`source/interface/virtual_keyboard.c:480-484`). Its close function cancels text entry, restores the saved text buffer, clears keyboard pointers/state, and plays back feedback (`951-958`); therefore close itself is not inherently a harmless empty function. But in this PS2 local pad profile no `virtual_keyboard_launch` is a live rooted external, and its CE UI owners are excluded. That proves the call to close is unreachable under the current selected closure, not that text input is generally unsupported by the product.

## Disposition rationale

- `virtual_keyboard_active`: `state-adapter` false because the current selected PS2 image has no virtual keyboard implementation or rooted launch path. This preserves the current pad-only input profile and makes the conditional unplug branch explicit.
- `virtual_keyboard_close`: `excluded-proven` for this profile because its sole rooted caller is gated by the false active state. The CE routine's side effects are documented; this approval is strictly reachability-based.

Re-open before implementing CE menus, player-name/profile editing, campaign naming, or any virtual keyboard launch path. Such additions must also account for saved text, cancellation, feedback sounds, and input state; changing the active query alone is insufficient.

## Regression

`tests/test_hcu_external_review.py::test_virtual_keyboard_is_inactive_only_for_current_rooted_pad_profile` checks manifest exclusions, rooted callsites, absence of `virtual_keyboard_launch` from the selected live-external set, conditional active->close ordering, and the differing CE effects of query versus close.

## Sources

- `submodules/halo-ce-universal/port/ps2/port.json:46-65`
- `submodules/halo-ce-universal/source/input/input_abstraction.c:816-824`
- `submodules/halo-ce-universal/source/interface/virtual_keyboard.c:480-484,951-958`
- `build/hcu-ps2-closure/all/result.json` (`rooted_link.live_externals`)
- `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
