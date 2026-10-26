# C3 real-time fixed-tick simulation — 2026-10-25

## Scope

This report records the opt-in real-time scheduler for the C3 interactive renderer. The scheduler runs CE simulation at a fixed 30 Hz from elapsed monotonic time and renders the newest published state when a render interval is due. The deterministic qualification path remains the default: `HCU_C3_REALTIME_SCHEDULER=0` unless explicitly enabled. The feature does not change CE movement constants or the `1/30` second simulation step.

## Scheduler contract

The accumulator in `submodules/halo-ce-universal/port/ps2/include/halo_ps2_scheduler.h` represents time in integer microsecond-rate units. Each elapsed microsecond contributes 30 units; a complete tick consumes 1,000,000 units. This preserves the exact fractional phase across intervals rather than repeatedly rounding a nominal 33,333 microsecond tick.

Each render interval runs at most four fixed simulation steps. For every step, the loop samples physical input, calls `player_control_update(1/30)`, closes the input frame, advances `game_time_update(1/30)`, and publishes cumulative progress. It then publishes the newest CE snapshot once and calls the parent render once for the catch-up batch. The parent renderer retains its existing synchronization and DMA fence path.

When more than four whole ticks are due, the scheduler executes four, counts the remaining whole ticks as dropped, and keeps the fractional remainder. For example, a 2-second stall is 60 due ticks: four steps execute, 56 are reported dropped, and the fractional phase is zero. This bounds recovery work instead of allowing an unbounded catch-up spiral. It does not attempt to simulate the dropped time.

Physical input is sampled once per simulation step, including each step of a multi-tick catch-up. This keeps movement input applied at the simulation cadence. The pad bridge exposes current controller state rather than a history of transitions, so a very brief press that begins and ends between two polls can still be missed, especially during a long render interval.

Queued sound events are drained by the per-simulation-step progress hook in real-time mode, preventing multiple catch-up steps from filling the bounded request ring before the next render. The deterministic mode keeps its existing render-tick drain. No sound playback implementation or movement scaling was added by this scheduler change.

## Clocks and interpretation

The scheduler reads `QueryPerformanceCounter` and `QueryPerformanceFrequency`. On PS2, `QueryPerformanceCounter` is backed by `GetTimerSystemTime()` at the 147.456 MHz bus-clock rate (`submodules/halo-ce-universal/port/ps2/src/ps2_time.c`). The progress hook reports completed simulation ticks, CE game-time ticks, render counts, dropped ticks, and elapsed time in this guest monotonic clock domain.

Guest timer rates and emulator wall-clock frame rate answer different questions. Any runtime FPS claim must use PCSX2 emulator-log timestamps and frame numbers; the guest clock report alone is not a host FPS measurement. The existing renderer waits and fences remain in place. The completed runtime result below uses host log timestamps for the rate calculation.

## Verification

The pure scheduler fixture (`tests/test_hcu_c3_scheduler.py`, `tests/hcu_c3_scheduler_main.c`) covers 15, 30, and 60 Hz render opportunities over 20 seconds, preserving 600 fixed simulation steps at each rate. It also checks mixed fractional intervals, two-step catch-up, and a 2-second stall producing four executed steps and 56 dropped ticks while retaining the fractional phase. These are host checks; they do not measure EE/PCSX2 performance or qualify gameplay rendering. The focused run passed 60 tests and two subtests across `test_hcu_c3_scheduler.py`, `test_hcu_ps2_input.py` and `test_c2_profile_boot_matrix.py`. Both timing and quiet EE variants linked successfully.

## Build and runtime evidence

The feature is compiled only when explicitly enabled with `HCU_C3_REALTIME_SCHEDULER=1`; `tools/ee-world.mk` forwards `HALO_PS2_C3_REALTIME_SCHEDULER=1` to the parent and CE closure builds. With the flag left at its default value of zero, the deterministic qualification loop is unchanged.

The completed timing build was configured for one view and one player on Blood Gulch, with scripted autofire disabled, resident HUD dispatch enabled, timing enabled, and telemetry disabled. Its manifest records ELF SHA-256 `97f489c7bcf106a4de7812a2999a6392f447ba4dafdcac14d431dba81b456370` and package SHA-256 `23d41d49c5e755da415f068e6420745eca8d51a71474d40c7335cca834273aac`.

- Build and launch manifest: [`desktop-launch.json`](../../build/c3/perf/realtime-simulation-20261025-r1/timing/desktop-launch.json)
- Active launch record: [`desktop-active.json`](../../build/c3/perf/realtime-simulation-20261025-r1/timing/desktop-active.json)
- Current PCSX2 emulator log: [`realtime-20261025T220132Z-emu.txt`](../../build/c3/perf/realtime-simulation-20261025-r1/timing/play/realtime-20261025T220132Z-emu.txt)
- Built ELF: [`bloodgulch-realtime-timing.elf`](../../build/c3/perf/realtime-simulation-20261025-r1/timing/play/bloodgulch-realtime-timing.elf)

### Runtime result: pass

The [retained proof](../../build/c3/perf/realtime-simulation-20261025-r1/scheduler-proof.json) measures completed step 151 through 901, from host log timestamps 103.7699 s to 128.7619 s. During those 24.9920 wall seconds, CE advanced 750 simulation/game ticks and the renderer completed 374 additional frames: **30.0096 gameplay ticks/s and 14.9648 rendered frames/s**. Movement and animation now advance at their intended fixed-tick cadence while rendering remains below 30 FPS.

The first cold window discarded 20 ticks during initial render/resource setup, exercising the bounded-overrun path. All following sampled windows reported zero further drops. The run exercised backward and sideways movement, right-stick looking and forward movement, with each key released afterward. No guest failure, assertion or exception was detected. The input ledger, exact executable and stable post-shutdown log hash are in the timing active record; captures include `before-movement.png`, `after-s.png`, `after-a.png`, `after-right.png`, `after-w.png` and `final.png`.

A separate quiet interactive ELF was linked with timing/telemetry disabled and the scheduler enabled: SHA-256 `2d7cf30c8ee5c2b41d1ba8ea0403644a037e6a34982e572889fc7f3aef1a03ce`. Its launch record is under [`quiet/desktop-active.json`](../../build/c3/perf/realtime-simulation-20261025-r1/quiet/desktop-active.json). It retains manual controls and disables scripted firing. A focused [gameplay capture](../../build/c3/perf/realtime-simulation-20261025-r1/quiet/gameplay-quiet.png), the startup scheduler marker and an absence of hot timing lines verified the live quiet session. That check is separate from the timing proof above.

## Known limits

The scheduler bounds catch-up by dropping whole ticks after an overrun, so sustained overload can slow simulation relative to elapsed host time. Very brief controller transitions can be missed between input polls because the bridge does not preserve event history. The known oversized/intersecting first-person geometry remains unchanged. A single Blood Gulch view on the PCSX2 recompiler does not qualify all maps, multiple views, hardware timing, or the renderer as a whole.
