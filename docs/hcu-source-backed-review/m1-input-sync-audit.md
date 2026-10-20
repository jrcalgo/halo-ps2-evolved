# M1 input, time, and synchronization audit (2026-10-20)

## Input path

The parent polls `pad_poll_players()` and publishes four logical samples through
`ps2_input_publish_dualshock()` in `src/stream/hcu_input_bridge.c:5`. CE calls
`ps2_input_poll_devices()` at the top of `input_frame_begin()` before
`input_get_device_states()` snapshots XInput changes in
`submodules/halo-ce-universal/source/input/input_xbox.c:705`. A source-order
regression check enforces that order in
`tests/test_hcu_ps2_input.py:45`.

The host integration fixture now exercises four logical ports through the real
parent bridge and HCU PS2 XInput adapter. It checks independent stick/analog
values and button state per port, insertion mask `0xF`, held state, release,
port-2 disconnect and removal, same-port reconnect/insertion, and continued
state on unaffected ports (`tests/hcu_input_bridge_main.c:17` and `:57`). The
PS2 adapter itself accepts logical ports 0–3 and only the no-slot XInput device
contract (`submodules/halo-ce-universal/port/ps2/src/ps2_input.c:112`).

`halo-ps2` maps four players as port-0 slots 0–3 when multitap 0 is present;
otherwise it maps port-0 slot 0, then port-1 slots 0–2 (provided multitap 1 is
present for slots 1–2) in `submodules/halo-ps2/engine/src/platform/pad.c:116`.
The current host bridge fixture mocks the final four logical samples; it does
not exercise `pad_poll_players()`'s physical port/slot selection or libpad
hotplug state machine. Real DS2/multitap and PCSX2 controller qualification
remain open, as do pressed/held/released transitions through CE's full
`input_get_device_states()` state machine (not merely the XInput layer).

## Time and synchronization owners

The current exact-root M0 ledger records the following live owner decisions in
`docs/hcu-source-backed-review/hcu-ps2-external-review.json`:

| Calls | Owner / behavior | Safety evidence |
|---|---|---|
| `CreateMutexA`, `WaitForSingleObject`, `ReleaseMutex` | EE binary semaphore in `ps2_edge.c`; saved-game locks are taken/released on EE main thread | caller and semaphore behavior reviewed in `hcu-ps2-batch-0-review.md`; target APIs are not a generic cross-thread mutex implementation |
| `CreateThread` | returns null with `ERROR_NOT_ENOUGH_MEMORY`; no EE worker is started | `thread_win32.c` checks null before priority/resume and profile loading remains synchronous |
| `SetThreadPriority`, `ResumeThread`, `GetExitCodeThread` | excluded-proven behind failed `CreateThread` handle | source branch guards recorded in the M0 ledger |
| `SwitchToThread` | no-op only after synchronous `ps2_cache` sets `read_complete` before return | cache load loops inspected; no unbounded wait is authorized |
| `GetTimerSystemTime`, `Sleep` | monotonic EE bus-clock counter and finite elapsed-time loop in `ps2_time.c` | wrapper conversion uses `MSec2TimerBusClock`; M0 review identifies pinned PS2SDK timer |
| `time`, `gmtime_r`, `localtime` | RTC/Newlib wall-clock for diagnostics and file timestamps, not simulation delta | missing wall-clock formatting is already handled by callers or produces zeroed SYSTEMTIME |

The distinctions matter: `Sleep` is not a scheduler yield; it busy-waits for a
finite number of EE bus ticks. The `SwitchToThread` no-op is not a general
threading facility. Mutex evidence is scoped to the present local, main-thread
save-file calls. Campaign AI/script or later async streaming work may invalidate
those proofs and must trigger a fresh closure/caller audit.

## Verification and remaining work

- `PYTHONPATH=. pytest -q tests/test_hcu_ps2_input.py`: 3 passed after expanding
  the host bridge scenario.
- The focused parent/HCU physical-memory and allocation suite remains green:
  22 passed, 1 skipped, 549 subtests passed.
- Not yet qualified: actual DS2, multitap 0/1, CE pressed/held/released frame
  snapshots, OPL/PCSX2 input-device behavior, or a future worker-thread profile.
