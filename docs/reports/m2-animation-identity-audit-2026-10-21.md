# M2 animation trace identity and first-person phase audit

## Call-site identity inventory

The phase setter tags only categories. The identity values needed for an eventual live-set trace are available at higher-level call sites, but not at the generic byte readers:

- [`object_compute_node_matrices()`](../../submodules/halo-ce-universal/source/objects/objects.c#L2457) has `object_index`; it resolves the runtime animation graph index and selected animation index/frame around lines 2515–2532, and the definition graph/index for overlays around lines 2553–2613. Its phase scope restores at line 2960 and has one ordinary return.
- [`unit_preprocess_node_orientations()`](../../submodules/halo-ce-universal/source/units/units.c#L11327) has `unit_index` and the unit definition's graph index near lines 11351–11357. Action/overlay animation indices and frames are selected in separate branches beginning around lines 11360–11378; further seat and aiming animation indices are selected later in that same function. The phase scope restores at line 11644 and has one ordinary return.
- [`first_person_weapon_build_node_matrices()`](../../submodules/halo-ce-universal/source/interface/first_person_weapons.c#L1172) has `local_player_index`, the current weapon datum, first-person graph index, `state_animation.index`, and its frame index at the first-person read around lines 1210–1244. Its PAL interpolation path can read the adjacent frame at lines 1254–1266. The newly added phase scope encloses both reads and restores at the function's single return.
- A map epoch is not currently exposed by the PS2 adapter; add a diagnostic generation at map load/unload boundaries if needed. `game_tick()` is a natural source for an explicit monotonic simulation-tick counter. `game_time_get()` is gameplay time and may pause/reset. The parent render frame counter is at [`ps2_render.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L91-L100), but generic animation readers cannot see it unless an explicit adapter context is installed.

The low-level readers record only animation and backing pointers, byte offset/length, site/detail, admission status, and active phase. The pointers are useful within one capture but are not stable cross-run identifiers. Compressed readers intentionally describe conservative remaining-container extents; those events are not exact dereference or lifetime-pin records. Do not infer a tag datum, graph element, owning actor, map epoch, tick, or render frame from pointer arithmetic.

## Bounded representation recommendation

Do not expand every 24-byte event with five or six 32-bit identity fields without an explicit memory budget: at 4,096 events, each additional 32-bit field adds 16 KiB. A report-only proposal is to introduce a versioned fixed-width trace header and a bounded, caller-owned context side table (for example, a capped 256-entry table) containing map epoch, datum index, graph index, animation index, tick, render frame, phase, and validity bits. Events would carry a compact context token; `0` means no context. Table exhaustion and event overflow must invalidate the complete trace, never wrap or imply completeness. The side table's bytes must be charged to the same named arena as the diagnostic trace buffer. This is a design candidate, not implemented API or capacity approval.

Capture only fields present at each high-level caller; use explicit absent sentinels for values that branch does not own. Never reconstruct tag or actor identity in the byte accessor. Keep all diagnostic reads behind `HALO_PS2_M2_ANIMATION_TRACE`, no heap/I/O in recording, and ensure phase/context restoration on every return path. Add trace-on/off parity checks for pose matrices/orientations, animation state, RNG, game time, and side effects before using the observer on runtime workloads.

## First-person phase implementation and verification

The recorder's existing `phase` field now also tags `first_person_weapon_build_node_matrices()` as `first_person_pose`. This is a coarse scope only; it does not yet emit the available player, weapon, graph, animation, frame, tick, or render-frame values.

Focused command `python3 -m pytest -q -rs tests/test_ps2_animation_trace.py tests/test_animation_data_ranges.py tests/test_hcu_parent_link_probe.py` passed **21 tests**. The current trace closure SHA-256 is `bc5e31e3ac7f5dd5368a9decc1228545c2561e5d0437318f80f084a7cd53eedc` (341 selected sources, 370 compiled units, zero compile failures; gate open). Exact diagnostic machine ELF SHA-256 is `11a4f6f4b6bf81652675e51e5f4905c67d754373d758531acf4d56a83570fd7f`: 2,094,468 LOAD file bytes against the 2,097,152-byte `elf_static` cap, 2,116,724 `.bss`, zero undefined imports; overall probe acceptance is false.

The exact-image interpreter PCSX2 run exited 127 before guest startup because Qt/XCB could not connect to display `:0.0`. Result SHA-256 is `20e1f202fa54a6dfb827df8d01c72de9a0857f4ffecb11e7fbdd4a07b62ff364`; launcher SHA-256 is `d4e353e3b1e7915bdb756934b4a16682ffca01f8ecc1cad9cff77b91ca6ff779`. There is no guest log or runtime trace for this ELF. REA's binary layout provider is unavailable because `REA_PWNTOOLS_PYTHON` is not configured; R5900 layout observations came from `readelf`.

## Remaining Step 8 checks

1. Add a fixed-width versioned context API and bounded caller-owned context table only after recording its exact arena charge and proving no production build includes it.
2. Populate context independently at object, unit, and first-person call sites; tests must include absent fields, nested scopes, context-table exhaustion, and no cross-map alias after unload/reload.
3. Add trace-on/off synthetic pose parity for the three scopes, including first-person adjacent-frame interpolation and weapon/state transitions.
4. Add frame/tick correlation without treating render frame as simulation identity; run schedule permutations to prove instrumentation does not alter CE simulation hashes.
5. Provide a bounded export and offline decoder, then execute a representative campaign encounter in a capacity-approved diagnostic image. The UI-only path produces zero observer events and is not representative evidence.
6. Keep cache/lease changes and map admission closed until exact-access/lifetime semantics, EE high-water, and the all-campaign memory topology independently pass the plan's gates.

## Implementation supersession (2026-10-21)

The report-only side-table recommendation above has since been implemented in the opt-in diagnostic profile; use [`m2-animation-context-implementation-2026-10-21.md`](m2-animation-context-implementation-2026-10-21.md) for the current API, fields, exact CE scope coverage, hashes, tests, memory charge, and limitations. Object primary pose, unit animation branches, and first-person state/firing/moving/jitter now attach caller identity. The directional first-person camera overlay records animation identity but intentionally clears frame validity because the chosen directional subframe varies with motion. Parent map lifecycle, CE simulation tick, and PS2 CE render-frame owners now update independent trace clocks. These changes supersede only the proposal's “not implemented” and “no tick/map/frame” statements; the proposed versioned guest export/decoder and all parity/live-set/placement evidence are still outstanding. The latest exact-image PCSX2 attempt failed before guest startup because the host could not open X11, so there is no guest trace or capture.
