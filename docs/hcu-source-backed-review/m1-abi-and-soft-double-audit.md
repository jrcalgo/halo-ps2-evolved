# M1 ABI and remaining soft-double audit (2026-10-20)

## ABI check

`python3 tools/hcu_ps2_abi_host.py` passes both the host `-m32 -fshort-wchar`
syntax/layout compile and the R5900 PS2 target compile. This validates compile-time
record sizes and offsets under the two intended compiler profiles; it is not a
host runtime or physical-console test. The checker is defined in
`tools/hcu_ps2_abi_host.py:25` and compiles the same HCU TU twice at
`tools/hcu_ps2_abi_host.py:45` and `tools/hcu_ps2_abi_host.py:64`.

`port/ps2/src/ps2_abi.c` asserts the 32-bit pointer/long and 16-bit
`wchar_t` ABI; `data_array` size and signature/data offsets; `datum_header`;
tag-block and tag-reference sizes/critical pointers; 420-byte object, 1,060-byte
unit, 1,148-byte vehicle, 636-byte weapon, and 552-byte projectile datums; and
damage flags/regions, unit player index, weapon primary trigger, projectile
target, and projectile arming-time offsets. It also retains a synthetic aligned
16-byte DMA-record check. `ps2_abi_check()` now performs a target-side read/write
round-trip for `data_array`, tag-block/reference pointers, and object, unit,
vehicle, weapon, and projectile fields. The parent and diagnostic entries fail
early if it returns false (`src/stream/hcu_main.c:130`,
`submodules/halo-ce-universal/port/ps2/src/ps2_main.c:18`). The host/target ABI
driver remains compile-only. The user's PCSX2 run reached `memory-ready` for
ELF `2eb1f907d781bcfe4fb6170ba698f05d58090510b818c595acb8f2921fb1c54e`, but
target disassembly then showed that the optimizer had reduced
`ps2_abi_check()` to an unconditional `return 1`; that run is not ABI
load/store evidence. The probe records are now volatile so those accesses and
comparisons survive optimization. Current ELF SHA-256 is
`7833c801a8084d0f549f5e598a11667cf6393ed9579402b9ff813cda5f5d716d`; target
disassembly includes the stack record writes and `lw`/`lwc1` comparisons, and
the image remains zero-undefined and within file-backed `elf_static`. A fresh
PCSX2 run of this new hash is still required to execute the corrected probe.

The synthetic DMA-record assertion does not by itself establish a render
payload. `tests/test_hcu_dma_palette.py` now compiles and runs the pinned
halo-ps2 `chain.c`, `skeleton.c`, and `mat.c` path; its fixture allocates the
same CNT-chain payload layout used in `engine/src/render/obj_render.c:100-105`,
checks the 80-byte VU1 palette starts on a 16-byte boundary, verifies the
five-quadword content, and verifies chain QWC accounting. It tests the parent
renderer’s existing matrix-to-VU1-palette boundary, not a CE-to-parent object
snapshot: no production HCU `real_matrix4x3` snapshot consumer is connected
yet. `real_matrix4x3` is 52 bytes and must be repacked only at a DMA/snapshot
boundary, as detailed in
`docs/investigations/final_milestone_plan.md` under “DMA prep” and “M3 render
snapshot.” CE object/datum pool alignment must remain unchanged.

The parent now has a pointer-free conversion API in
`src/stream/hcu_render_snapshot.c`: it copies the pinned CE 13-float
`real_matrix4x3` wire representation, applies CE's separate uniform scale to
the forward/left/up basis, and writes halo-ps2's row-basis `mat4` convention.
`tests/test_hcu_render_snapshot.py` feeds that record through the real parent
matrix transform, VU1 palette, and aligned DMA-chain construction, checking
translation, nontrivial rotation, scale, and malformed non-finite input. This
test passed with the existing palette test (2 passed). The R5900 combined-link
probe compiled the new object, but its adapter symbol is discarded by section
GC because the production renderer still has no snapshot caller. This is
stronger than the prior synthetic palette-only fixture, but does not yet
complete the production snapshot-consumer requirement or render a CE object.

## Soft-double relocation inventory

The rooted closure report `build/hcu-ps2-closure/all/result.json` records live
R5900 soft-double arithmetic helpers at these call-site counts:

| Helper | Live callers | Representative call sites |
|---|---:|---|
| `__adddf3` | 6 | `object_new`, `render_camera_build_frustum`, `vehicle_update` |
| `__subdf3` | 4 | `bsp3d_test_pill_recursive`, `input_abstraction_update`, `sound_calculate_fade` |
| `__muldf3` | 15 | `bsp3d_test_pill_recursive`, `physics_compute_new`, `player_control_modify_desired_angles`, `unit_euler_aiming_update` |
| `__divdf3` | 12 | `biped_update_physics`, `collision_test_vector`, `physics_update_new`, `vehicle_update` |

The same rooted closure includes software-libm `acos` (10 callers), `asin` (1),
`atan2` (16), `ceil` (2), `cos` (47), `floor` (12), `pow` (11), `sin` (45),
and `sqrt` (66). Those counts are link-relocation counts for this closure, not
unique source expressions or per-frame execution counts. The relevant call
paths span simulation, collision, AI, aiming, camera, UI, sound, and rendering;
they are not safely dismissed as rasterization-only. Example double-typed CE
locals occur in item angular-velocity handling (`source/items/items.c:464`),
collision ray construction (`source/units/units.c:9052`), and grenade-origin
calculation (`source/units/units.c:11871`). Important roots include
`collision_test_vector` (`source/physics/collisions.c:478`),
`bsp3d_test_pill_recursive` (`source/physics/collision_bsp.c:2453`),
`player_control_modify_desired_angles` (`source/game/player_control.c:1951`),
and `vehicle_update` (`source/units/vehicles.c:2449`).

Do not replace math functions or force `double` to `real` as part of ABI cleanup.
That changes rounding and possibly gameplay/collision decisions. The measured
host profile must remain the accepted baseline until M13/M3-style parity fixtures
cover affected behavior and EE profiling demonstrates a bottleneck. For now,
record the dependencies as known CPU costs and keep single-precision conversion
as a measured optimization decision.

## Gate state

`python3 tools/hcu_ps2_abi_host.py` passes host ILP32 and R5900 compile-only
assertions; `pytest -q tests/test_hcu_dma_palette.py` passes. The current
combined gameplay ELF includes the runtime ABI smoke and has zero undefined
imports, but PCSX2 was unavailable in the current session because no X display
could be reached. M4 step 1 therefore remains partial until the exact ELF
executes the smoke and the HCU-to-parent object snapshot has a real consumer at
the DMA boundary. No math parity or performance claim is made.
