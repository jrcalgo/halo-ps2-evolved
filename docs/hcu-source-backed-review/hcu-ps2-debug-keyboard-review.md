# M0 Xbox debug-keyboard service review

`XInputDebugGetKeystroke` is called only by CE's keyboard-debug-queue drain in `source/input/input_xbox.c`. The call is inside a `while (... == ERROR_SUCCESS)` loop that translates Xbox Debug Monitor keystroke records into CE keyboard events. The PS2 port does not provide the Xbox Debug Monitor keyboard queue; physical PS2 gameplay input is sampled and published independently through `ps2_input_poll_devices` / the DualShock bridge before CE snapshots input state.

The PS2 edge adapter returns error code 38 for the unsupported debug-keyboard queue. This is deliberately nonzero, so the CE drain loop terminates immediately and cannot spin on a fabricated success record. It does not modify the controller state or CE's already-published pad events. This is an explicit unsupported-device boundary, not a replacement for the PS2 pad path.

Sources: [`input_xbox.c`](../submodules/halo-ce-universal/source/input/input_xbox.c#L1073), [`ps2_edge.c`](../submodules/halo-ce-universal/port/ps2/src/ps2_edge.c#L121), and the parent [DualShock bridge](../src/stream/hcu_input_bridge.c#L5). Test: `test_xinput_debug_keyboard_queue_terminates_without_affecting_pad_path` checks the call-loop and error result together with the independently published pad input path. This review does not approve general keyboard input, event, or thread placeholders.
