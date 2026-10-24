# M3 integrated tick/input/render cadence fixture

Date: 2026-10-21  
Scope: host-only source-extraction fixture for the seam between CE fixed ticks, the PS2 input publication boundary, and the production CE PS2 render snapshot adapter. No production code, M2 map service, plan, or renderer allocation was changed.

## Result

Added [`tests/test_hcu_m3_tick_render_invariance.py`](../../tests/test_hcu_m3_tick_render_invariance.py), a host C integration harness that extracts and compiles these exact current-source function bodies:

- CE `game_tick()` from [`game.c:334`](../../submodules/halo-ce-universal/source/game/game.c#L334).
- CE `game_time_update()` from [`game_time.c:379`](../../submodules/halo-ce-universal/source/game/game_time.c#L379).
- PS2 `input_frame_begin()` and `input_frame_end()` from [`input_xbox.c:710`](../../submodules/halo-ce-universal/source/input/input_xbox.c#L710).
- PS2 `ps2_render_frame_state_advance()` and `render_frame()` from [`ps2_render.c:94`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L94) and [`ps2_render.c:126`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L126).
- The parent-owned real snapshot publisher from [`hcu_render_snapshot.c:38`](../../src/stream/hcu_render_snapshot.c#L38) and commit path at [`hcu_render_snapshot.c:112`](../../src/stream/hcu_render_snapshot.c#L112).

The single test passed:

```text
python3 -m pytest -q tests/test_hcu_m3_tick_render_invariance.py -x
1 passed in 0.15s
```

The harness runs three independent deterministic traces, each with four one-tick CE scheduler updates and the same sequence of sampled input values. Before each render-cadence run it explicitly unbinds and rebinds the publisher, so the zero-render schedule's empty-latest assertion cannot depend on a snapshot from a prior cadence. The zero-render trace is the per-tick hash baseline; one-render and three-render traces compare every corresponding checkpoint to that baseline. Between tick checkpoints it runs respectively zero, one, or three real production `render_frame()` calls with changing render-only camera positions. It compares a canonical FNV-1a hash over tick-owned local time, deterministic RNG state, CE-shaped object identity/flags, object transform, and the input sample consumed at the CE frame boundary. Every per-tick hash matches across all three render schedules. It also verifies:

- The extracted `input_frame_begin()` actually invokes the PS2 poll hook before CE's device-state snapshot: the poll publishes a varying sample; the snapshot callback captures it; the harness checks the exact value.
- The extracted scheduler executes one actual extracted CE `game_tick()` for each 0.034-second update, and a following 0.001-second sub-tick update leaves the authoritative state hash and CE local tick time unchanged.
- The actual PS2 `render_frame()` invokes the first-person render-pose hook exactly 0, 4, or 12 times for the three schedules, advances `render.frame_index` accordingly, leaves the authoritative object matrix unchanged, and publishes a snapshot containing the current object transform when called.
- The no-render schedule produces no snapshot; schedules with rendering publish and expose the expected current object transform.

This improves the previous separate scheduler and render tests by composing the source bodies and parent snapshot publisher in one fixture. It does not make the mock callbacks into Halo gameplay.

## Deliberate boundary and remaining gap

The suite executes the real CE scheduler and tick control-flow bodies, real input frame begin/end bodies, real PS2 render frame/state-advance bodies, and the real parent snapshot storage/commit/DMA-pack implementation. To keep the fixture independent of a retail map and the much larger CE object/data-array runtime, the tick phase callbacks are deterministic host doubles. In particular, the test's `objects_update()` callback increments a CE-shaped test object's transform and RNG; it is not the retail CE `objects_update()` implementation or a live CE object datum. The fixture therefore proves render-cadence noninterference against a controlled authoritative-state surrogate, and verifies the actual source call-order around it; it does not prove full gameplay determinism, actual object-array lifecycle, AI, collision, damage, or weapon-state determinism.

The fixture is host native, not R5900 execution. It does not prove an EE performance budget, guest pad injection, retail BSP load, VIF1 submission, GS scene drawing, frame presentation, or the two-bank retained-reader lifetime under a concurrent consumer. A PS2 render snapshot remains a CPU-side snapshot/DMA packing result, not evidence of a rendered Halo scene. These remain separate M2/M3 acceptance gates.

## Comparison reference

Halo-64's [`n64_render_game.c:517`](../../submodules/halo-64/port/n64/game/n64_render_game.c#L517) keeps a platform frame adapter separate from CE-facing simulation state and platform drawing. This fixture follows that structural separation only: tick-owned state is hashed independently from changing render-camera/frame state. It does not copy Halo-64 renderer behavior, N64 resource limits, or gameplay cuts.

## Reproduction identities

The two submodule HEAD pins observed when the fixture ran were HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56` and halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The checkout has other modified files/submodule worktree state, so HEAD pins alone are not a complete source identity. SHA-256 values for the fixture and extracted source files at execution time:

| File | SHA-256 |
|---|---|
| `tests/test_hcu_m3_tick_render_invariance.py` | `bc4a733af793277c04be0f273adf4a6495fc3cbfc00557d33d53f3e77eb044bc` |
| `submodules/halo-ce-universal/source/game/game.c` | `941e187aa0bfb1278cab7c5a94ae688808f702742d68e92802e7489a491a2dad` |
| `submodules/halo-ce-universal/source/game/game_time.c` | `b100377e516f9d287aef9a2188a9492ce29d4addf61cb08e411f328c8e9464a3` |
| `submodules/halo-ce-universal/source/input/input_xbox.c` | `6e8a39cf5c72c6f0c7e9a7ac1153f490b7a66533e35bef9cf5d1d4fc65b3f779` |
| `submodules/halo-ce-universal/port/ps2/src/ps2_render.c` | `be715452680f1178262ca293d1758c2684ea2e95d0324cd7d48deb8517fcb828` |
| `src/stream/hcu_render_snapshot.c` | `ec56be9a8b7ca2806bbc665e7dc2e72e36c5ca790fd5de0e4f83a8b9fa6bf03b` |

The harness compiles a temporary executable and deletes it through `TemporaryDirectory`; there is no retained binary or runtime log to hash. `git diff --check -- tests/test_hcu_m3_tick_render_invariance.py` passed. No commit was made.
