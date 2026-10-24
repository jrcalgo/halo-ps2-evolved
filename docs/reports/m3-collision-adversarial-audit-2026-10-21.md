# M3 Step 15 collision adversarial-test audit

Status: report-only review of the current host fixture and pinned HCU collision/schema paths. No implementation or retail/guest parity is claimed.

## Finding

The smallest high-value next increment is a **bounded malformed-graph test against the real HCU collision entry points, paired with HCU's real pre-use graph validator**. The existing synthetic test establishes only a valid finite square-floor case and an out-of-square miss. It does not exercise the defensive tree/ring limits that M2's CE schema validator is intended to guarantee before collision traversal.

The current fixture builds HCU `collision_bsp.c` and `bsp2d.c` with the parent `collide.c`/`pill.c`, but `init_square()` supplies only a valid one-node BSP. The assertions cover the surface-aware CE pill result (`surface=0`, `t=.375`), parent pill position, parent vector time, `pill_new` boundary output, and one outside-square miss ([`tests/m3_ce_collision_synthetic_main.c:65-103`](../../tests/m3_ce_collision_synthetic_main.c#L65), [`tests/m3_ce_collision_synthetic_main.c:164-203`](../../tests/m3_ce_collision_synthetic_main.c#L164)). The Python harness compiles the actual HCU collision functions but this environment's execution is skipped on SIGSYS ([`tests/test_m3_ce_collision_synthetic.py:18-53`](../../tests/test_m3_ce_collision_synthetic.py#L18)); a fresh run here was **1 skipped**, so it adds no new native execution evidence.

## Source-backed test seam

HCU's collision traversal has defensive bounds worth testing directly:

- 3D traversal stops when a child is out of range, exceeds `MAXIMUM_BSP3D_TRAVERSAL_DEPTH`, or consumes more node visits than the original node count. The source explicitly describes the node-count budget as a guard against cycles and multiple-parent graphs ([`collision_bsp.c:1264-1292`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1264)). Both pill APIs route through this guard ([`collision_bsp.c:1664-1695`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1664), [`collision_bsp.c:2453-2474`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2453)).
- A decoded collision leaf must be in range and its BSP2D-reference interval must lie within the references block ([`collision_bsp.c:1320-1354`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1320)).
- Surface rings are individually bounded to the maximum eight edges, and surface/edge index helpers reject out-of-range entries ([`collision_bsp.c:348-391`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L348)).
- These runtime guards are not a substitute for the schema gate. HCU's collision schema checks the 3D/2D graphs, leaf references, and surface edge rings before gameplay reads them ([`tag_schema_collision.c:4-9`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L4), [`tag_schema_collision.c:1017-1075`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L1017), [`tag_schema_collision.c:1090-1169`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L1090), [`tag_schema_collision.c:1172-1245`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L1172)). The generic tag walker bounds in-image block/data extents and then applies graph/value checks; it is the required ingress validator, not an optional test convenience ([`tag_validate.c:4-27`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L4)).

## Recommended next host increment

Extend the existing host fixture, retaining the valid square baseline, with narrowly separated cases:

1. **Cycle guard:** mutate a copy of the one-node test BSP so a traversed 3D child points back to node 0. Call both CE pill APIs with inputs that visit that child. Require bounded return, no reported surface hit, and no corruption of a guard region around the result/fixture. This directly tests the runtime cycle defense; it does not assert that malformed data is accepted by the game.
2. **Invalid child/leaf:** use one child outside the 3D-node block and one leaf-encoded child outside the leaf block. Require bounded no-hit results and unchanged canaries. Keep these separate from an invalid raw pointer or truncated block, which belongs to the M2 extent/schema gate and must not be passed directly into collision code.
3. **Leaf-reference range:** provide an in-range leaf whose `first_bsp2d_reference_index + count` exceeds the reference block. Confirm `collision_bsp_valid_leaf()` makes traversal skip it safely. In a paired validator case, require the real HCU graph/schema validator to repair the reference range or reject the candidate according to its documented behavior before invoking collision.
4. **Ring bound:** make a surface edge chain fail to close within `MAXIMUM_EDGES_PER_COLLISION_SURFACE`; verify the collision primitive terminates without a hit, and separately confirm the HCU schema validator refuses that malformed surface ring. Do not use a corrupted backing pointer for this case.
5. **Repeatability and memory safety:** replay every case from freshly reset data, compare result fields that each API promises to initialize, and compile/run the fixture with host ILP32 plus ASan/UBSan where available. A sanitizer pass is still host evidence only. If the sandbox blocks ILP32 execution, run through the repository's already-approved native-test path and record the exact command/result rather than treating a skip as a pass.

The paired validator should use the source-backed schema fixture path already exercised for retail package CTAG/CBSP validation; avoid cloning graph-validation rules into a test double. The test should prove the transition `malformed serialized graph -> CE validator repair/refusal -> collision call only for the validator-approved graph`. It should not make the collision query itself responsible for validating arbitrary unbounded tag pointers.

## Important limits and dependencies

- This is an adversarial **host algorithm/validator** subtest, not Step 15 parity. Step 15 still requires the same exact resident retail BSP to drive HCU and parent with identical movement inputs, and must cover floor/ceiling/step, static hits, dynamic objects, actors, and projectiles ([`plans/7.hcu-remake-m2-m4.md:634-640`](../../plans/7.hcu-remake-m2-m4.md#L634)).
- HCU `collision_bsp_test_pill()` is surface-aware; `collision_bsp_test_pill_new()` is a distinct boundary/normal query, as the current fixture correctly documents. Do not equate their hit outputs.
- The synthetic fixture lacks a gameplay BSP resident in target-sized EE arenas. It cannot establish movement cadence, actor/object collision, dynamic-simulation allocation, or PCSX2 behavior. M2's capacity-qualified gameplay-map prerequisite remains unmet, so M3 Step 16 and M3 exit stay blocked by dependency, not by this test.
- **Halo-64 comparison:** its history records a measured pill-feature/BSP-walk optimization and collision cost, not a correctness shortcut ([`submodules/halo-64/port/n64/HISTORY.md:659-676`](../../submodules/halo-64/port/n64/HISTORY.md#L659)). Use that as a reminder to profile the complete EE path after correctness is established; do not import Halo-64's N64 cadence reductions or treat its geometry cache as evidence for CE collision parity.

## Evidence from this audit

- Inspected the existing fixture/harness and the current HCU collision and schema source cited above.
- Ran `python3 -m pytest -q tests/test_m3_ce_collision_synthetic.py`: **1 skipped** (native ILP32 execution is blocked in this sandbox). No new passing runtime result is claimed.
- Recommendation is limited to the next adversarial host test seam; no target acceptance, retail BSP parity, or rendered gameplay is asserted.
