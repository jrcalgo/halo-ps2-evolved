# M0 production-closure audit: compiler and numeric runtime helpers

Date: 2026-10-21. Scope: `__extendsfdf2`, `__fixdfsi`, `__truncdfsf2`, `rint`, and `sqrt`. Report-only; no source, ledger, or plan changes.

## Exact artifact and caller-set verification

The fresh HCU production closure in `build/hcu-ps2-closure/all-no-bootstrap-memory/result.json` has 322 rooted externals and was rebuilt with the profile define `HALO_PS2_NO_BOOTSTRAP_MEMORY`. The current `rooted.o` hashes to `f1a169d679ee354044390083945b9e74319ca0b833b01da25ff904f3ea1f5e3a`. The five symbols audited here are still undefined runtime dependencies in that object (`mips64r5900el-ps2-elf-nm -u` lists each name).

I compared the fresh `live_externals` rows to the current source-backed ledger. For all five, `caller_sections` match exactly; the caller counts are:

| Symbol | Live caller sections | Exact callsite set described by current closure |
|---|---:|---|
| `__extendsfdf2` | 240 | Float-to-double promotions throughout AI, movement, physics/collision, animation, weapons, geometry, effects, camera, and render-state code; representative sections include `accelerate_to_position`, `actor_move_update`, `animation_get_keyframe_rotation`, `collision_move_point`, `first_person_weapons_update`, `physics_update`, `projectile_update`, and `vehicle_update`. |
| `__fixdfsi` | 4 | `dsound_volume_from_gain`, `fast_ftol`, `real_a_rgb_color_to_pixel32`, `real_argb_color_to_pixel32`. |
| `__truncdfsf2` | 163 | Double-to-float truncations across simulation and presentation; representative sections include actor movement/perception, collision, animation, `main_loop`, `physics_update`, `projectile_update`, and `vehicle_update`. |
| `rint` | 3 | `fast_ftol`, `real_a_rgb_color_to_pixel32`, `real_argb_color_to_pixel32`. |
| `sqrt` | 66 | Length, normalization, collision, AI, movement, path, projectile, and vehicle math; includes `distance2d`, `distance3d`, `fast_normalize2d`, `fast_normalize3d`, collision pill/sphere tests, `player_control_update`, and `vehicle_update`. |

The complete exact section arrays and source-candidate path/hash maps are preserved in the matching symbol rows in `docs/hcu-source-backed-review/hcu-ps2-external-review.json`; the fresh closure provides the comparison baseline. All five source-candidate lists have the same paths as the ledger, but their source hashes differ for three paths: `port/ps2/src/ps2_cache.c`, `source/main/main.c`, and `source/scenario/scenario.c`. This is a source freshness invalidation, not a changed call-section set. The differences in `ps2_cache.c` add serialized-BSP header handling and the current tag-image argument at the cache materialization boundary; `main.c` and `scenario.c` add the opt-in UI lifecycle diagnostic and owner-release work. None of those changed functions occurs in these five exact caller-section sets, except `main_loop` is a `__truncdfsf2` caller. The new `main_loop` block is guarded by `HALO_PS2_M2_UI_LIFECYCLE_TEST`, which is absent from this production closure's flags/profile defines, so it does not add that test block to the production code. Source hash mismatch still must be rebound by the central ledger refresh/review process.

There is an important end-to-end freshness gap: `docs/hcu-source-backed-review/hcu-ps2-external-review.json` and `build/hcu-parent-link-probe/result.json` still bind the production parent image to HCU rooted SHA `0645f18c1bc7332b8f4ec161b85b947653e4673fdab1a7fa57fac4e7de64a3e1`, while the freshly generated closure object is `f1a169d6…`. The optical combined map is older than this closure rebuild. Thus I can confirm the fresh HCU object still requests these five externals and its call sections are stable, but I cannot claim the current parent machine image links this exact latest root or re-prove its archive-member providers from a matching combined map. The top-level M0 gate must remain open until the combined probe and source ledger are rebuilt against this exact closure.

## Owner and semantic review

### Compiler-generated conversions

- `__extendsfdf2` is the GCC soft-float single-to-double extension helper. Its broad live use is expected because CE's `real` values are often promoted to C `double` by expressions or library interfaces. The exact call-site set is the 240-section current-rooted set above; it is not one suspicious caller. This is real simulation work on the EE and double precision is software-emulated on R5900, so performance is a genuine concern. Replacing it with single precision or a custom helper would change semantics and is not justified without parity vectors and EE timing.
- `__fixdfsi` converts double to signed integer. The four live sections narrow the main gameplay-visible behavior: CE's `fast_ftol` performs `__builtin_rint((double)value)` before the signed conversion; the color converters round normalized channels before packing; `dsound_volume_from_gain` converts a sound-gain quantity. `fast_ftol`'s source documents the Xbox `FISTP` round-to-nearest/default-control-word intent at `source/cseries/cseries.h:335-344`. The wrapper around color packing is in `source/effects/decals.c:819-848` and the inline ARGB conversion is in `source/bitmaps/bitmaps_inlines.h:44-74`.
- `__truncdfsf2` narrows double back to single. It is live in 163 sections including the simulation families listed above. This is not an optional “speed” shim: it preserves the source compiler's double-expression then float-store behavior. In particular, `main_loop` is in the set, but the M2 lifecycle block in that function is compile-time guarded and absent from this production profile.

The pinned compiler source is PS2 GCC EE v15.2.0, commit `df77d03bc1bd5765b40de554918a5ff541202548` (`config/toolchain-sources.json:12-16`). The prior audit describes the helper source algorithms and confirms these are libgcc implementations, not generated PS2 zero bodies (`hcu-ps2-toolchain-eight-review.md:11-25`). That document's older combined-map claim is not fresh proof for the current `f1a169d6…` root.

### `rint` and nearest-integer conversion

The source calls `__builtin_rint((double)value)` in `fast_ftol` (`source/cseries/cseries.h:335-344`), and similarly rounds each channel in the ARGB/RGB conversion functions (`bitmaps/bitmaps_inlines.h:69-73`, `effects/decals.c:842-846`). The intended contract is nearest integer under the default control word, matching the source comment's Xbox `FISTP` expectation. The prior source audit says Newlib's `s_rint` uses the TWO52 add/subtract method and `_control87` only saves a software control word rather than programming the EE FPU (`hcu-ps2-toolchain-eight-review.md:47-57`). This supports owner identification, but no current target test proves the EE FPU's active rounding mode or tie behavior. Keep that specific equivalence open for target vectors; a host test or map-member check is insufficient.

### `sqrt`

CE's `square_root` inline delegates directly to `sqrt` (`source/math/real_math.h:985-1000`), and `reciprocal_square_root` relies on it (`:996-1000`). The 66 live caller sections put it in distances, normalizers, collision and actor movement, not just cosmetic code. The prior toolchain audit identifies Newlib's wrapper plus IEEE implementation and explicitly leaves positive/zero/negative/NaN vectors and EE timing for later qualification (`hcu-ps2-toolchain-eight-review.md:42-45`, `m0-toolchain-runtime-audit.md:32-33`). Correct provider ownership is therefore plausible; exact CE numerical edge behavior and performance remain unmeasured.

## Provider evidence and test coverage

`config/toolchain-sources.json:12-23` pins the PS2 EE GCC and Newlib inputs. The previous combined optical map contains concrete `libgcc.a(_sf_to_df.o)`, `libgcc.a(_df_to_si.o)`, `libgcc.a(_df_to_sf.o)`, `libm.a(libm_a-s_rint.o)`, and `libm.a(libm_a-w_sqrt.o)` provider records; `tests/test_hcu_ps2_toolchain_runtime_owners.py:11-43` asserts those member names and rejects matching generated `ps2_platform.c` bodies. However, that test currently reads `build/hcu-ps2-closure/all/ps2_platform.c` and the prior combined `hcu-gameplay-machine.map`, and insists that each ledger row already be `implemented`. It neither uses the production profile's fresh rooted hash nor executes any numeric helper.

The exact link-probe and provider evidence in `hcu-ps2-toolchain-eight-review.md:3-9,69-73` are bound to an older rooted object. `m0-toolchain-runtime-audit.md:25-33` already records the missing EE numerical vectors/timing. Therefore the valid conclusion for this batch is: **source-defined providers and unchanged caller-section ownership are strongly supported, but an exact-current-parent-image provider proof and EE behavior/performance qualification are not present**. Do not treat this report as approval to close any ledger row or M0 gate by itself.

## Open questions / next evidence

1. Rebuild the combined parent image from current HCU root `f1a169d6…` and save its rooted-object and ELF/map hashes together. Verify zero unresolved symbols and that all five definitions resolve to the pinned `libgcc`/`libm` members in that exact map.
2. Update the production profile regression to consume `all-no-bootstrap-memory` and assert current row/caller equality; keep provider identity and semantic caller review separate.
3. Add EE/PCSX2 numeric fixtures for `rint` ties and values around positive/negative integer boundaries, truncation boundaries for float↔double conversions, and `sqrt` positive/zero/negative/infinity/NaN behavior. Record the rounding control state used. Compare expected CE behavior, not only the same Newlib implementation.
4. Measure EE instruction/time cost for representative hot paths (`actor_move_update`, collision pill tests, `physics_update`, and `vehicle_update`) before considering any optimization. Preserve exact double semantics unless a measured and fixture-backed port change is accepted.

## Handoff status

No ledger rows were modified or promoted. This batch covered five of the 25 current pending symbols; **25 pending remain** because the exact combined image has not yet been refreshed and the target numeric tests are still missing. A local structural comparison verified the same 240/4/163/3/66 caller-section sets in the fresh closure; `nm -u` verified all five remain live unresolved runtime references in that root.
