# M2 C2 residency lane evidence (r4), 2026-10-23

Lane: residency (C2.4 production path, C2.8 production drain).
Build directory: `build/m2-c2-r4-residency/` (EE objects in `ee/`, host map-service artifacts in `map/`, profile-mount artifacts in `pm/`).

## Scope completed

1. Residency binding before prepare (`src/stream/hcu_map_service.c`, `profile_bind_residency`).
   Both the live-owner candidate path and the successor path call `hcu_profile_mount_bind_residency` before `hcu_profile_mount_prepare`. A failed bind stops the stage before any prepare.
2. Fail-closed registration (`runtime_registration_valid` requires `runtime_residency_valid`).
   A runtime needs non-NULL residency entries, a nonzero entry capacity, and a 16-byte-aligned arena that is a whole number of 64 KiB slots.
   The residency entries and arena join the runtime span checks (`runtime_spans_valid`, `runtime_spans_disjoint`, five spans).
3. Legacy production drain gate (`src/stream/hcu_map_service.c`, `src/stream/hcu_main.c`).
   `hcu_map_service_set_legacy_renderer_drained` installs the predicate. `hcu_main` installs `hcu_renderer_drained` right after `hcu_map_service_init_with_arenas` succeeds.
   With the predicate set, the legacy unloader keeps a live owner published while the renderer is busy, the legacy loader refuses to mount over a live owner, and shutdown is refused while the owner is live.
   Without the predicate (host fixtures) the legacy behavior is unchanged.

## Not completed (open, cross-lane or deferred)

- Task 2, partition residency span: `src/stream/hcu_memory_profile.c` rows are unchanged. The render residual is not reduced and no residency span is recorded. Binding the arena out of the map/render backing needs carve-out logic in `hcu_memory_profile_plan_v1` / `hcu_memory_bind_profile_v1`, which is outside this lane's row-only ownership. Needs a generator update in `tools/audit_hcu_c2_partition_budget.py` (untracked, not in this lane) plus `tests/hcu_mp_partition_table_main.c`.
- Task 3, runtime registration in `hcu_main.c`: production does not register the profile runtime. The runtime needs package read, package SHA, compatibility gate, metadata bytes/SHA, source reader, relocation/scratch storage and the residency arena, none of which `hcu_main.c` currently provides. The arena has no source until the partition residency span exists. Legacy-path gating is in place; registration is not.
- The residency arena and `renderer_drained` are therefore not wired into production. Production still uses the legacy path.
- The host fixture scripts the profile mount seam, so the residency bind is exercised as a call-order and state check only, not as real chunk pinning. `tests/hcu_profile_mount_main.c` covers real pinning.

## Test evidence

- `python3 tests/test_hcu_map_service_profile.py` (env `HCU_MAP_SERVICE_PROFILE_ARTIFACTS=build/m2-c2-r4-residency/map`): OK, 23 `PASS` lines. Five new: runtime without whole-slot arena refused; failed residency bind stops stage before prepare; legacy unload/load/shutdown blocked while renderer busy; legacy owner released after drain; every profile prepare saw a bound mount.
- `python3 -m pytest -q tests/test_hcu_main_wiring.py`: passed, including new `test_legacy_renderer_drain_gate_installed_after_map_init`.
- `python3 -m pytest -q tests/test_hcu_profile_mount.py -k ui` (env `HCU_C1_PROFILES=build/m2-c2-hcp2-primary HCU_C1_REBUILD=build/m2-c2-hcp2-rebuild HCU_PROFILE_MOUNT_ARTIFACTS=build/m2-c2-r4-residency/pm`): 1 passed, 26 deselected.
- EE compile (`make -f tools/ee-world.mk PS2SDK=$PWD/build/toolchain/install/ps2sdk WORLD_HCU_GAMEPLAY=1 WORLD_OUTPUT=build/m2-c2-r4-residency/ee`, with `build/toolchain/install/ee/bin` on PATH) of `stream/hcu_map_service.o` and `stream/hcu_main.o`: rc=0, no warnings. Log at `build/m2-c2-r4-residency/ee-compile.log`.
- `git diff --check` clean for the touched repo files, and for `submodules/halo-ce-universal` and `submodules/halo-ps2`.

## Honest status

Partial. Tasks 1, 4 and the legacy half of 3 are done and tested. Task 2 (partition residency span) and the production runtime registration in task 3 are open.
The required reading list in the task was not completed in this lane: the submodule docs were not read in full.
The diff stat for the touched files includes uncommitted prior work from other sessions in the same worktree.
