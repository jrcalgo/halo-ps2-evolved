# M3 synthetic CE collision follow-up — 2026-10-21

## Outcome

A bounded host-only CE collision test is feasible before M2 has a resident retail BSP. The new fixture compiles and executes the pinned Halo CE `collision_bsp.c` surface-aware `collision_bsp_test_pill()` path and the parent repository's `collide_move_pill()` / `collide_test_vector()` against two representations of the same one-plane, finite square floor. It is useful as a source-backed smoke/parity seam, but **does not close M3 Step 15**: the geometry is synthetic; the execution is native ILP32 on the host; no live CE `global_collision_bsp`, retail map, PS2 runtime, actor/object collision, or full movement tick is involved.

The newer `collision_bsp_test_pill_new()` is also invoked at the in-square point. CE's wrapper in `source/physics/collisions.c` classifies this as collision type 2 and fills `surface_index`, `material_index`, and `plane_designator` with `NONE`, which is evidence that this routine is an out-of-world/BSP-boundary path, not a substitute for the surface-aware player pill resolver. The synthetic test does not claim that its one-node BSP fully encodes a retail outside volume.

## Fixture and method

New, isolated files:

- [`tests/m3_ce_collision_synthetic_main.c`](../../tests/m3_ce_collision_synthetic_main.c) builds a z=0 plane and square surface with four vertices/edges, one BSP3D node, one empty leaf, one BSP2D reference, and a terminal BSP2D surface. It creates CE tag-block records and equivalent parent `collide_bsp` tables from the same coordinates/connectivity.
- [`tests/m3_ce_collision_host_preamble.h`](../../tests/m3_ce_collision_host_preamble.h) isolates glibc declaration names for the CE XDK-shaped host ABI and declares the small host-only diagnostic shims needed by the retained source closure.
- [`tests/test_m3_ce_collision_synthetic.py`](../../tests/test_m3_ce_collision_synthetic.py) compiles the real pinned CE `source/physics/collision_bsp.c` and `bsp2d.c` together with parent `src/game/collide.c` and `src/game/pill.c`, using the repository's private ILP32 sysroot, function/data sections, and link-time garbage collection. The fixture enters the exact source functions; the shims do not synthesize collision answers. `tag_block_get_element_with_size` is only a fallback for invalid element access; the accepted valid fixture accesses use CE's fast inline accessor.

The valid in-square test starts at `(0, 0, 1)`, moves `(0, 0, -2)`, uses radius `0.25`, and intersects the square `[-2,2] × [-2,2]` at z=0. CE's finite-surface pill function reports surface 0 at `t=0.375`; the expected center-to-plane clearance is `1 - 0.25 = 0.75`, so `0.75 / 2 = 0.375`. The parent pill mover ends at z=`0.25`, grounded, with +Z normal. The parent's zero-radius segment/vector oracle reports the uninflated plane fraction `t=0.5`, correctly distinct from the radius-expanded pill fraction.

The outside-square case starts at `(3, 0, 1)` with the same vertical movement. CE's surface-aware pill path misses the finite polygon; the parent pill mover also remains ungrounded and completes to z=`-1`. The newer `pill_new` function is deliberately not compared in this case because the fixture BSP has no x/y outside-volume partition. This keeps the test from conflating the BSP boundary-query contract with bounded surface contact.

## Evidence and source identities

Source pins during this run:

- Parent checkout: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` (fixture source `src/game/collide.c` and `src/game/pill.c` are local working-tree content; file hashes below bind those exact bytes).
- halo-ce-universal: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.
- Halo-64 comparative checkout: `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.
- CE collision source SHA-256: `096debda0f9cdd62fa8b9981f040770e5e0dfbb8f6baa2f4a241ff0db00dde86`.
- Parent `collide.c` SHA-256: `a49b88a65989c09b25cc7a52ae755d8d51a562a66004746a4e16ffde3f478e74`.
- Parent `pill.c` SHA-256: `01f0ee4f818491b3e6c5cd6dcae9240585e2ff4b91dd9c4c53fecc38acfccf77`.
- Fixture main SHA-256: `34b3ee311a7fa5c3a5800b21e608db72f6b937467b179ed96b1b5b7cc3773e42`.
- Host preamble SHA-256: `41995d0aea06a4488a9612ba7708d6b19b08d85a89e8ccfafd758e188c03d6df`.
- Python test SHA-256: `499fb88b9010d01bbc8d4549651420e7dda04a0659b5e13a0df946b6c71a3907`.

Verification command (run outside the sandbox because sandbox execution of native ILP32 programs returns `SIGSYS`):

```sh
PYTHONPATH=. python3 -m pytest -q \
  tests/test_m3_ce_collision_synthetic.py \
  tests/test_m3_collision_oracle.py
```

Result: **3 passed** (two parent oracle cases and the new synthetic CE/parent executable). `git diff --check` passed. The ordinary sandbox invocation skips the native ILP32 executable specifically after observing the known `SIGSYS`; it must not be counted as execution evidence. The passing test is an ILP32 host run, not R5900/PCSX2 evidence.

## Source-backed interpretation

- CE's `collision_bsp_test_pill()` sets BSP traversal state and calls its own recursive pill walk; the recursion follows BSP3D partitions, checks leaf/reference correspondence, computes radius-expanded contact, resolves the BSP2D surface, and calls the surface edge ring to verify the projected point. See [`collision_bsp.c`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1160), [`bsp3d_test_pill_recursive`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2460), and [`collision_surface_test_point`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1544).
- CE's `collision_bsp_test_pill_new()` uses a different recursive path and returns only fraction and normal; its consumer `collision_test_pill_new()` assigns type 2 plus `NONE` surface/material fields. Do not promote that path as the full surface-aware movement solver ([CE collision wrapper](../../submodules/halo-ce-universal/source/physics/collisions.c#L1139)).
- Parent `collide_test_vector()` resolves BSP leaf contents to a BSP2D surface and verifies the projected point against the edge loop ([`collide.c`](../../src/game/collide.c#L117), [`collide.c`](../../src/game/collide.c#L168)). Parent `collide_move_pill()` composes its feature builder and movement solver with caller-provided scratch ([`pill.c`](../../src/game/pill.c#L352), [`pill.c`](../../src/game/pill.c#L861)). In this synthetic fixture, the surface geometry and boundary behavior agree while their result representations differ.
- halo-ps2 remains relevant to target memory/layout constraints, not as the collision oracle: its spec budgets collision BSP together with current-BSP data and resident collision tags separately; the pinned engine's current `engine/src/sim/objects.*` files are render-snapshot/object-record code, not a CE collision implementation. Thus no halo-ps2 collision code was substituted into this test ([`02-specs.md`](../../submodules/halo-ps2/docs/02-specs.md#L58), [`02-specs.md`](../../submodules/halo-ps2/docs/02-specs.md#L117), [`objects.h`](../../submodules/halo-ps2/engine/src/sim/objects.h#L1)).
- Halo-64 provides a comparative source for the shared pill recursion/radius-expansion pattern. Its BSP traversal and `t = -(inverse*distance0) - fabs(inverse)*radius` are structurally similar, but the N64 port's flagged BSP indices and platform/resource constraints are not adopted here ([`Halo-64 collision_bsp.c`](../../submodules/halo-64/source/physics/collision_bsp.c#L2140), [`Halo-64 collision_bsp.c`](../../submodules/halo-64/source/physics/collision_bsp.c#L2214)). It is comparative evidence only; this test executes HCU CE source.

## What remains before Steps 15/16 can pass

1. M2 Step 10 must provide an admitted, capacity-qualified retail gameplay BSP and bind it to CE's collision tag globals in the combined runtime.
2. Expand the current one-floor check into the plan's retail trace categories: floor/ceiling/step/slope, surface filter/breakability, zero-length/start-solid/grazing, malformed/depth-bounded inputs, dynamic object/actor/projectile cases, and full player movement state. Compare identical initial states and per-tick trajectories, not only one collision primitive result.
3. Run the exact traces against CE runtime and parent oracle in native host, then current combined PS2 image under PCSX2 interpreter and recompiler; preserve hashes/logs and verify PS2 scratch is arena-backed with no heap allocation.
4. Only after those gates pass may Step 16 alter `WORLD_HCU_GAMEPLAY=1` source selection. Keep parent collision code and fixtures in `WORLD_PLAY=1` as the comparison oracle.

No shared plan or production/runtime code was edited. This report and the three unique test-only source files are the entire write set for this task.
