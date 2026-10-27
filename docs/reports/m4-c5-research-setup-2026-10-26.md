# M4 C5 step 8 research: local setup, teardown and profile qualification (2026-10-26)

Read-only research. No source, test or tool was modified, and `src/stream/hcu_main.c` was not touched (Codex is editing it).

## Scope actually read

- Every file under `submodules/*/docs` was listed. The halo-ce-universal docs (`custom_edition_caches.md`, `mods.md`) and the halo-ps2 docs (`01` to `14`, `reports/*`) were read in part; the long reports (`tag-inventory.md`, `tag-index.md`, `map-headers.txt`) were skimmed by listing only.
- `submodules/halo-ce-universal/AGENTS.md` was read in full.
- `src/stream/hcu_main.c`, `src/stream/hcu_map_service.c`, `src/stream/hcu_map_service.h`, `src/stream/hcu_memory_profile.c`, `tests/test_hcu_ce_map_lifecycle.py` and `tests/hcu_ce_map_lifecycle_main.c` were searched by grep and read at the cited line ranges. Not every line was read.

## 1. Where setup is parsed

**Finding: the HCU path has no parser for mode, roster, difficulty or seed.** A grep of `src/stream/*.c` for `difficulty`, `roster` and `seed` returns nothing relevant. The only setup inputs in the HCU stream code are:

| Input | Where | Notes |
|---|---|---|
| Map name | `map_loader(void *context, const char *map_name)`, `src/stream/hcu_map_service.c:1005` | Entry point from CE when a map is requested. `profile_load()` is used if a runtime is registered. |
| Partition profile | `HALO_HCU_PARTITION_PROFILE` macro, default `"bootstrap"`, `src/stream/hcu_main.c:147` | Compile-time. `"bootstrap"` skips the versioned table; any other name must be a row of `hcu_memory_partition_select_v2()`, otherwise boot fails closed (`hcu_main.c:418-421`). |
| Profile package and runtime | `hcu_map_service_register_profile` / `_register_runtime` / `_register_successor_runtime`, `hcu_map_service.c:1486-1597`; called from `hcu_main.c` around lines 681-860 | The profile is bound at boot, not per setup. |
| Preflight by name | `hcu_map_service_preflight(const char *map_name)`, `hcu_map_service.c:1261`, impl at `:1270` | Map-level checks (catalog, CTAG stream, HMAP, CBIX, asset profile gate, "capacity-not-qualified" at `:1400`). |

Mode, roster, difficulty and seed are therefore not parsed in `src/stream`. They belong to CE's own setup (the CE game-side code under `submodules/halo-ce-universal/port/linux/game/`, e.g. `menu_functions.c`, `network_test.c`), which is outside the HCU stream layer. CE's `custom_edition_maps.c`/`menu_functions.c` decide the kind (singleplayer vs multiplayer) and difficulty before calling `map_name`.

For the lifecycle test, `tests/test_hcu_ce_map_lifecycle.py` pins the UI HCP2 package (`levels\ui\ui`, profile id 1) by SHA256 and runs `validate_files()` on it; it skips when the build inputs are absent.

## 2. Where teardown begins

The unload/teardown chain in `hcu_map_service.c`:

1. `profile_preflight()` (`:707`): validates the successor candidate fully (metadata, residency bind, mount prepare) while the old map is still live. Rejections log `profile-preflight rejected reason=...` (e.g. `:640-690`, `:724-801`).
2. `hcu_renderer_quiesce` callback (`src/stream/hcu_main.c:3404`): called "after the candidate is fully validated and before CE disposes its live scenario. A false result vetoes CE teardown." It drains the C3 render map, checks reader count, renderer drain and bitmap-frame idle.
3. `profile_unload()` (`hcu_map_service.c:898`): tears down the mounted profile owner.
4. `map_unloader()` (`hcu_map_service.c:1093`): the CE unload hook that frees the map service's owner.

So the teardown begins once CE asks to dispose the live scenario, and it is only allowed to proceed after step 1 accepts the successor and step 2 reports the renderer quiescent. The legacy bootstrap path is gated by `hcu_map_service_set_legacy_renderer_drained()` (`hcu_main.c:4049`).

## 3. Where a pre-teardown validator hooks in

The existing hook points are, in order of how early they run:

- **Best hook for a setup-level rejection:** `map_preflight(void *context, const char *map_name)` (`hcu_map_service.c:1088`), which CE calls by name before `map_loader`. `hcu_map_service_preflight_impl` (`:1270`) already rejects by reason with the `HALO_PS2_LOCAL map-preflight rejected reason=...` telemetry, and the rejection happens before any teardown. A mode/roster/difficulty/seed profile check would fit here as one more reason string.
- **Second-level hook:** `profile_preflight()` (`:707`). It is the point that actually authorises CE teardown for a successor (`profile-preflight` phase logs). A profile-capability check that depends on the successor's metadata belongs here, next to `successor-capacity-or-spans`.
- **Veto after validation:** `hcu_renderer_quiesce` (`hcu_main.c:3404`). It is the last point where a rejection is still free; afterwards CE disposes the live scenario.

Reject before teardown means: fail in `map_preflight` or `profile_preflight` and keep the old owner mounted. `profile_unload` and `map_unloader` must not run first.

## 4. Which profiles are currently qualified

The authoritative source is the runtime marker `HALO_PS2_LOCAL partition-selected ... qualified=1` plus `profile-runtime ... qualified=1`, read by `tools/c2_profile_boot_matrix.py` (`:157`) and summarised by `tools/c2_profile_fit_table.py`. I did not reconstruct a per-row pass list from the boot logs, so the rows below are the **registered table**, not a verified qualified set.

- `src/stream/hcu_memory_profile.c:279-306` (`hcu_partition_table_v2`) lists 29 rows:
  - 26 `*_marine_shotgun_4p4bot` / `*_mounted_gunner_4p4bot` rows for beavercreek, bloodgulch, boardingaction, carousel, chillout, damnation, hangemhigh, longest, prisoner, putput, ratrace, sidewinder, wizard (13 maps x 2 roles);
  - `bots_sidewinder` (commented "static package-derived candidate; not measured fit");
  - `ui`.
- Boot logs under `build/c2-finish`, `build/matrix-rerun` and `build/record` contain `profile-runtime row=` lines. The largest counts are `bloodgulch_mounted_gunner_4p4bot` (908 lines) and `beavercreek_mounted_gunner_4p4bot` (13); `bots_sidewinder` (17). The 4p4bot rows are the ones exercised most.
- The M2 C1 corpus qualification (`build/m2-c1-corpus-{primary,rebuild}-v3`, per the user's memory note) reports 6/6 `c1-*` ledger rows passed on 2026-10-23. Its canonical JSON is `docs/reports/m2-c1-qualification-2026-10-23.json`, which I did not open. That is the closest thing to a "qualified population" in the repo.
- `docs/reports/m2-c2-r9-runtime-guest-2026-10-24.md:58-63` says `partition-selected qualified=1` was not observed on that run because the ELF halted earlier. Treat any row without a fresh `qualified=1` log line as unqualified.

Recommendation for step 8: derive the qualified set by running `tools/c2_profile_fit_table.py` against the current boot matrix output rather than reading the registered table, and record the row names and their `profile_package_sha256` in the step-8 evidence.

## Caveats

- Mode, roster, difficulty and seed have no HCU-side representation today. Any step-8 validator for them must add the inputs; it cannot reuse an existing parse.
- `hcu_main.c` is being edited concurrently. Line numbers above are from the current working tree and may shift.
- halo-64 setup (reference only): `submodules/halo-64/port/n64/game/n64_campaign.c:1480-1489` sets `campaign.difficulty = PIN(difficulty, 0, 3)`, and `n64_campaign.c:1642` formats it for the HUD. `n64_menu.c` holds the player-join setup. This is the difficulty clamp to reference, not a profile check.
