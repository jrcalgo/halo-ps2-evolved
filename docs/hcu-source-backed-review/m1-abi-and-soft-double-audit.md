# M1 ABI and remaining soft-double audit (2026-10-20)

## ABI check

`python3 tools/hcu_ps2_abi_host.py` passes both the host `-m32 -fshort-wchar`
syntax/layout compile and the R5900 PS2 target compile. This validates compile-time
record sizes and offsets under the two intended compiler profiles; it is not a
host runtime or physical-console test. The checker is defined in
`tools/hcu_ps2_abi_host.py:25` and compiles the same HCU TU twice at
`tools/hcu_ps2_abi_host.py:45` and `tools/hcu_ps2_abi_host.py:64`.

`port/ps2/src/ps2_abi.c` now asserts the 32-bit pointer/long and 16-bit
`wchar_t` ABI; `data_array` size and signature/data offsets; `datum_header`;
tag-block and tag-reference sizes/critical pointers; 420-byte object, 1,060-byte
unit, 1,148-byte vehicle, 636-byte weapon, and 552-byte projectile datums; and
damage flags/regions, unit player index, weapon primary trigger, projectile
target, and projectile arming-time offsets. It also retains a synthetic aligned
16-byte DMA-record check. The PS2 parent calls `ps2_abi_check()` during startup
at `src/stream/hcu_main.c:129`, and the diagnostic entry does likewise at
`submodules/halo-ce-universal/port/ps2/src/ps2_main.c:18`.

This synthetic DMA record does not establish that render snapshots or actual
DMA payloads are correctly aligned. `real_matrix4x3` is 52 bytes and must be
repacked only at a DMA/snapshot boundary, as detailed in
`docs/investigations/final_milestone_plan.md` under “DMA prep” and “M3 render
snapshot.” CE object/datum pool alignment must remain unchanged.

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

ABI compile checks pass. The current memory-ready PCSX2 run links and calls the
ABI check but does not execute every datum-consuming simulation path, so M4
step 1 remains partial until a guest fixture exercises representative object,
unit, weapon, projectile, and tag/datum accesses and an actual DMA-facing
snapshot boundary is qualified. No math parity or performance claim is made.
