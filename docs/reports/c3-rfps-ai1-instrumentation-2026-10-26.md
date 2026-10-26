# C3 realtime batch instrumentation (AI1)

The realtime CE loop collects one timing record per nonempty scheduler batch.
Calls to `hcu_c3_render_tick(tick - 1)` and `hcu_c3_snapshot_tick(tick - 1)` remain
outside timing preprocessor guards and occur once after every actual batch. In a
quiet build, their calls remain present while QPC phase reads and logger calls
compile out.

Phase slots, in QPC ticks, are disjoint sums per batch:

| Slot | Meaning |
| --- | --- |
| 0 | Input sampling/abstraction for each simulation step |
| 1 | `player_control_update` for each step |
| 2 | Input finish/end for each step |
| 3 | `game_time_update` for each step |
| 4 | Parent `main_game_render` publication |
| 5 | HCU `hcu_c3_render_tick` callback |
| 6 | HCU `hcu_c3_snapshot_tick` callback |
| 7 | Accumulated explicit 1 ms idle sleeps between nonempty batches |

The interval is previous actual batch end to this batch end. Thus zero-step
clock polls and sleep are included once. Interval minus the eight measured phase
sums is the unassigned residual; the idle phase is a subset of that interval,
not an additional time amount. The first interval starts at the first scheduler
batch's QPC sample. Thirty records emit interval min/max and eight histogram
bins (<10, <20, <30, <40, <60, <100, <200, >=200 ms), mean steps, and mean phase
times. The accumulator helper is `src/stream/hcu_batch_profile.h`.

Sparse timing frames also expose fine BSP clip gather/group cycle totals and
input/output batch, polygon, and vertex counts, plus `video_present_timing`
wait and framebuffer-select durations. These come from renderer and video
timing accessors and compile to zero-valued accessors when timing is disabled.

Build command: `python3 build/c3/fps-next/ai2/build_case.py --case baseline --views 2`.
The private builder pins the helper header along with the runtime logger and CE
loop source. Focused tests:
`pytest -q tests/test_hcu_batch_profile.py tests/test_hcu_c3_scheduler.py tests/test_hcu_ps2_input.py tests/test_hcu_render_snapshot.py tests/test_hcu_game_time_scheduler.py`
(17 passed, 1 skipped, 7 subtests passed). The scheduler input-order test now
uses the fixed-step block's source boundaries instead of a fixed-size character
window, which became too short after timing brackets were added.
