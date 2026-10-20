# M0 rooted `halo_keyboard_actions` device-profile review

The sole rooted caller is `keyboard_controls_update` in
`source/input/input_abstraction.c`. For each valid gamepad,
`input_abstraction_update` first maps the CE gamepad buttons and sticks into
`game_input_state`, then overlays keyboard controls. Keyboard buttons merge by
`MAX` with the gamepad values; keyboard movement replaces movement only when
the keyboard has a nonzero direction. A zero keyboard-action mask therefore
does not erase or alter the already-populated pad state. It only means no
keyboard keys are down.

The current PS2 input publisher exposes the DualShock/multitap controller
states, and the accepted M1 input profile has no PS2 keyboard device owner. The
generated zero mask is thus a narrow “no keyboard actions available” adapter,
not the source for controller input. This approval is limited to that profile;
adding a USB keyboard driver requires a new input device mapping and a revised
review. The focused regression is
`test_zero_keyboard_actions_preserve_gamepad_state_in_pad_only_profile`.
