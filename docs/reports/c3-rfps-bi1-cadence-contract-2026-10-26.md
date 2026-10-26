# C3 cadence contract prototype (BI1) — 2026-10-26

## Result

Added an unused, standalone integer presentation pacer at `port/ps2/include/halo_ps2_presentation_clock.h` and an actual-source host contract fixture. This is a feasibility precursor only. It does not change CE simulation, C3 publication, rendering, GS presentation, build registration, or the default executable. It provides no evidence that 60 distinct frames/s fit PCSX2 or physical PS2 budgets.

The clock schedules presentation opportunities at a configured integer rate, defaulting to 60 when passed zero. Its fractional phase is kept as an integer remainder in nanoseconds-times-rate units; it caps accumulated elapsed time to 250 ms and due work to eight opportunities per call, counting opportunities beyond that cap. A backward clock jump resets its baseline and emits none. Pausing discards phase and elapsed time; the first resume call establishes a fresh baseline. The helper has no simulation tick callback or game-state dependency. Callers must continue advancing simulation separately at the existing fixed 30 Hz.

## Host contract evidence

`tests/test_c3_cadence_contract.py` compiles the new header and the repository's actual `src/stream/hcu_snapshot_bank.c`, then runs `tests/c3_cadence_contract_main.c`. Command: `pytest -q tests/test_c3_cadence_contract.py` — passed. The fixture checks:

- 30 fixed simulation-loop iterations and roughly 60 presentation opportunities are counted independently. Integer 30 Hz nanosecond increments yield 59 here due to 10 ns of accumulated quantization; this is clock arithmetic evidence, not rendered FPS.
- Exact fractional accounting over 60,000 one-millisecond intervals, zero-due intervals, backward-time reset, elapsed clamp, due cap/drop accounting, and pause/resume behavior.
- Actual HCU snapshot-bank behavior with two endpoint readers pinning A and B while C publishes. With all three slots either pinned or published, the next write is refused; A and B retain their sequence/map generation, and releasing A permits reuse of that slot. This demonstrates the bank protocol in isolation, not safe CE integration or GS lifetime.

## Memory and integration boundary

The corrected B1 report records cache-OFF frame-scratch ownership at 262,608 of 393,216 bytes, leaving 130,608 bytes, and a candidate derived-copy workload of 82,912 bytes. The arithmetic leaves 47,696 bytes before alignment, guards, other workspace, and lifetime costs. This prototype allocates no derived snapshot and makes no claim that this nominal slack is usable. Cache-ON is excluded from cadence conclusions. The test exercises pinned endpoints directly with the existing three-slot bank and adds no bank storage.

There is no integration point in this change. Before any useful presentation-rate switch, work remains to wire an opt-in scheduler into C3 without changing tick order/delta, define snapshot retention at the correct post-tick publication boundary, prove readers end only after the true renderer/GS consumer fence, and measure render/present time and distinct render sequence IDs under the target workload. Repeating the latest snapshot would measure presentation opportunity throughput only; interpolation additionally needs immutable compatible endpoints, lifecycle/discontinuity rules, pose coverage, and a presentation-only path that does not advance HUD, particles, sounds, or animation. Those contracts are not implemented here.

## Decision

This precursor validates bounded integer pacing behavior and one existing bank pin/refusal contract on the host. It does not establish the requested >30 distinct rendered frames/s while preserving the full graphical workload. Do not describe this helper as a 60 FPS mode or enable it in production until CE integration, matched 30 Hz simulation/fidelity checks, and target-specific PS2 timing/GS evidence are available.
