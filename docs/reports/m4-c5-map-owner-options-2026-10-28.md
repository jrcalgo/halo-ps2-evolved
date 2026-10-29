# M4 C5 map owner options (2026-10-28)

Read-only analysis. No source, test or tool file was changed. Diffs below are proposals, not applied. No build or test was run. Line numbers refer to the current working tree.

## 1. What actually refuses the C5 map request

The request is made in `src/stream/hcu_c5_boot.c:437-438` (`main_set_map_name(HCU_C5_BOOT_MAP_PATH)` then `main_menu_switch_to_single_player()`), inside CE's normal solo path. CE then calls the registered preflight, which is `hcu_map_service_preflight_impl` in `src/stream/hcu_map_service.c:1282`. The branches run in this order:

| Order | Lines | Branch | Effect on b30 in the default C5 build |
|---|---|---|---|
| 1 | 1300-1316 | C5 local setup gate | Passes for the boot rows (`hcu_c5_boot.c:158-178`) |
| 2 | 1319-1330 | successor failure latch | Not armed (profile-only) |
| 3 | 1331-1346 | `profile_requested` gate | Not taken (no `register_profile` call in C5) |
| 4 | 1356-1392 | `HALO_HCU_HEADLESS_RUNTIME_GUEST` admission | Compiled out (`tools/c5_build.py:180` sets `WORLD_HCU_HEADLESS_RUNTIME_GUEST=0`) |
| 5 | 1395-1396 | `preflight_ready && !runtime_registered` | Not taken |
| 6 | 1410-1434 | capacity gate | **Refuses b30** |
| 7 | 1435-1436 | `runtime_registered` -> `profile_preflight` | Never reached for b30 |
| 8 | 1437-1450 | live-owner branch | Never reached for b30 |

**Correction to the premise.** The capacity gate runs before the live-owner branch. For b30 the refusal is the printed line at `hcu_map_service.c:1430` (`map-preflight rejected map=b30 reason=capacity-not-qualified`), followed by `fail_preflight_for_entry` at 1432. It is not silent. The silent refusal is the live-owner branch at 1449 (`fail_preflight_for_entry` with no print). That branch is reachable only for maps that pass the capacity gate, which in the default build means `ui`. A live-owner refusal for b30 cannot happen until the capacity gate admits b30.

**b30 is not admitted even with the diagnostic define.** The `HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC` list at 1410-1426 contains beavercreek, bloodgulch, boardingaction, carousel, chillout, damnation, hangemhigh, longest, prisoner, putput, ratrace, sidewinder, wizard and ui. It does not contain b30. So `c5_build.py --map-capacity-diagnostic` (`tools/c5_build.py:303-305`) still refuses `--boot-map b30`.

**A registered runtime does not help a non-headless build.** `runtime_registered` is checked at 1435, after the capacity gate. Only the headless block at 1356-1392 returns before the gate. `register_profile` (1516) has the same ordering problem.

## 2. Route 1: register a runtime profile

### 2.1 The sanctioned C2 path, as built today

1. Partition row. `hcu_main.c:411-425` (`hcu_select_and_bind_partition`) selects `HALO_HCU_PARTITION_PROFILE` from `hcu_memory_partition_select_v2`. The table is `src/stream/hcu_memory_profile.c:279-299`. It has rows only for the 13 `*_4p4bot` maps plus `ui`. There is no b30 row. Line `hcu_main.c:147` says a non-bootstrap partition that is not in the table fails closed.
2. Generated image header. `tools/ee-world.mk:174-177` runs `tools/c2_profile_image_header.py --row $* --package-root $(WORLD_HCU_PROFILE_PACKAGE_ROOT)`. `tools/ee-world.mk:58` defaults the root to `build/m2-c2-r3-selected-packages/pkg`. That root holds 52 files: 4 per map for the 13 `*_4p4bot` maps. There is no b30 package and no ui package.
3. Macros. The header defines `HCU_C2_IMAGE_ROW/MAP/SCENARIO/PROFILE_ID/PACKAGE_*/METADATA_*/RELOCATION_BYTES/SOURCE_*/DATUM_*` (`tools/c2_profile_image_header.py:151-177`). `hcu_main.c:97-98` includes it under `HALO_HCU_PROFILE_IMAGE_HEADER`. The header is wired in `tools/ee-world.mk:187` as `-DHALO_HCU_PROFILE_IMAGE_HEADER="<row>.h"`.
4. Registration. `hcu_main.c:4010` calls `hcu_register_selected_runtime` during boot, before the shell. The function returns 1 early when `!s_partition_selected` (`hcu_main.c:675`), so bootstrap builds never register. The function fills `hcu_map_profile_runtime` (`hcu_main.c:705-745`), sets `headless_candidate_admission` and `partition_row` under `HALO_HCU_HEADLESS_RUNTIME_GUEST` (`hcu_main.c:732-735`), and calls `hcu_map_service_register_runtime` (`hcu_main.c:756`). It checks `HCU_C2_IMAGE_ROW == s_partition_name` at `hcu_main.c:688`.
5. Guest flags. `tools/ee-world.mk:188-189` add `-DHALO_HCU_HEADLESS_RUNTIME_GUEST=1` and `-DHALO_PS2_C2_PRODUCTION_RUNTIME_GUEST=1`. `tools/ee-world.mk:109` sets the production define on `main.o`. The `hcu_map_service.o` rule (`tools/ee-world.mk` around 216-218) also takes `HALO_HCU_HEADLESS_RUNTIME_GUEST`.
6. Shell map. `hcu_main.c:4101-4103` copies `HCU_C2_IMAGE_MAP` and `HCU_C2_IMAGE_SCENARIO` into `hcu_c2_runtime_map_name` and `hcu_c2_runtime_scenario_path`. These are the map the headless guest loads.

### 2.2 Runtime admission

`runtime_registration_valid` (`hcu_map_service.c:1577`) requires package and metadata pins, a compatibility gate, residency and span checks, and under headless (guard at 1582) `partition_row` set and `maximum_tag_image_bytes == physical_memory_get_tag_cache_size()` (1583-1585). `hcu_map_service_register_runtime` (1602) is refused whenever `mount.active || source.active || profile_owner_live || profile_candidate_ready || reload_pending || preflight_ready` (1602-1612). The registration must happen before the UI owner mounts. A call from `hcu_c5_boot.c` at tick time is therefore too late.

### 2.3 Can it be done from new files only?

No, for three reasons.

- Timing. The C5 boot hook runs on the first simulated tick (`hcu_c5_boot.c:115-117`), after the UI owner is mounted. `hcu_map_service_register_runtime` refuses at 1609. Registration must come from boot code before the shell, which is `hcu_main.c:4010` or an equivalent in `main.c`.
- Admission. Admission at 1356-1392 is compiled only under `HALO_HCU_HEADLESS_RUNTIME_GUEST` in `hcu_map_service.o`. A new file cannot enable it without a build-flag change in `tools/ee-world.mk` or `tools/c5_build.py`.
- Capacity. The b30 row does not exist, and `hcu_c5_boot.c:100-102` says no qualified row exists for the boot map. A new file can add a runtime for b30 only if the partition row, package and tag/BSP sizing exist first. These are the qualification artifacts the C2 workflow (`tools/c2_profile_boot_matrix.py`) produces. A new file cannot create them.

### 2.4 Proposed minimal diffs (not applied)

`tools/c5_build.py:178-180` (the pinned defines), for a qualified row `<row>` once it exists:

```diff
-    "WORLD_HCU_TAG_CACHE_BYTES=2097152", "WORLD_HCU_PARTITION_PROFILE=",
+    "WORLD_HCU_TAG_CACHE_BYTES=2097152", "WORLD_HCU_PARTITION_PROFILE=<row>",
     ...
-    "WORLD_HCU_HEADLESS_RUNTIME_GUEST=0", "EE_OPTFLAGS=-Oz",
+    "WORLD_HCU_HEADLESS_RUNTIME_GUEST=1", "EE_OPTFLAGS=-Oz",
```

`tools/ee-world.mk` needs no line changes. The header rule at 174-177 and the defines at 186-189 already key off these variables.

`src/stream/hcu_main.c:4010` and `hcu_main.c:688` are unchanged if the row name matches `HCU_C2_IMAGE_ROW`. `hcu_map_catalog.c:121` already has the b30 identity. A row in `src/stream/hcu_memory_profile.c` (after line 298) would be needed:

```diff
+	{ "<row>", { HCU_MEMORY_PROFILE_VERSION_1, <tag>, <bsp>, <texture>, <residency> } },
```

Values depend on a capacity measurement that does not exist for b30. This is the blocking input.

`src/stream/hcu_c5_boot.c`: under headless the shell, not `hcu_c5_boot.c`, loads the map (`hcu_main.c:4101-4103`). `hcu_c5_boot.c:18-19` says C5 deliberately does not define `HALO_PS2_C2_PRODUCTION_RUNTIME_GUEST`. The C5 boot hooks (`ps2_bots_update_actions` wrap, `hcu_c5_boot.c:63`) and the non-headless `main_loop` request path would have to be reconciled with the headless guest. This is not verified. The headless build "exits before CE's renderer loop" (`hcu_main.c` comment near line 349), so the C5 tick may not run at all.

### 2.5 Risk, effort, default builds, recommendation

- Risk: medium. The map service path is well tested (see section 4). The risk is in the headless guest changing what C5 measures.
- Effort: high. It needs a b30 package (`tools/c2_profile_image_header.py` and the pack tools), a partition row with measured sizing, the headless C5 boot reconciliation, and a qualified run.
- Default builds: none affected. Every change is gated by `WORLD_HCU_PARTITION_PROFILE` and `WORLD_HCU_HEADLESS_RUNTIME_GUEST`, both defaulting to empty or 0 (`tools/ee-world.mk:56`, `:55`).

## 3. Route 2: diagnostic-only live-owner staging

### 3.1 Current semantics that a change must respect

- Preflight staging (legacy). Success stages the entry and sets `preflight_ready` (`hcu_map_service.c:1459-1510`). It opens the source (1459), takes `arena_mark(map_arena)` (1466), and commits `service->identity` (1510). Failure goes through `clear_staged_request` (`hcu_map_service.c:308-319`), which closes the source only when no mount is active.
- Live-owner rule. Lines 1437-1440 say explicitly: "Do not allocate or overwrite a live owner's arena during CE's preflight-before-unload transition. Reuse is safe only for the exact currently mounted map; the loader repeats full checks after unload." The only accepted live case is same-map reuse at 1441-1447, which sets `reload_pending` and returns 1.
- Loader (legacy) `map_loader` at `hcu_map_service.c:1017`. It refuses with `owner-still-active` when `legacy_renderer_drained && mount.active` (1024-1028) and when `reload_pending && (mount.active || source.active)` (1035-1038). On a failed mount it closes the source, clears `preflight_ready`, `staged_map`, `staged_entry` and `reload_pending`, notifies `map-empty` (1096) and returns 0.
- Unloader (legacy) `map_unloader` at 1105. It returns with `renderer-busy` while the owner is live and the renderer is not drained (1111-1116). Otherwise it unloads the mount, or closes the source, and keeps the staged request when `reload_pending` is set.
- Profile successor latch (profile-only). `hcu_map_service_latch_successor_preflight_failure` (490-510) requires `runtime_registered` and `profile_owner_live`. It has no legacy equivalent.
- Profile candidate semantics (profile-only, for reference). `discard_profile_candidate` (627-637), `profile_preflight_successor` (641-716) and `profile_load` (840-905) are the reference for "stage beside a live owner". The legacy path has no separate candidate storage, so it cannot reuse them.
- Shutdown. `hcu_map_service_shutdown` (~1690-1730) refuses while a legacy or profile owner is live (1694-1701).

### 3.2 Invariants a staged-over-live-owner path would break

1. Arena. Preflight loads sections into `map_arena` at 1466 onward. The live mount occupies the same arena. The code avoids this on purpose (1437-1440). A second arena would be needed, and the M2 capacity findings say the parent has no spare capacity for b30.
2. Source reader. `ctag_map_source_open_any` at 1459 would reopen `service->source` while the live mount still reads from it. `clear_staged_request`'s guard (313) exists to protect the live reader.
3. Identity. `service->identity` and `ctag_info` are written at 1510 and describe the live map. Same-map reuse (1441-1442) and the unload path read them.
4. Pre-teardown guarantee. The whole point of preflight is that CBIX and the CTAG first pass succeed before CE tears down the old map. A foreign stage that defers all checks to `map_loader` would give up that guarantee. A failure after unload leaves an empty state, which is a new state for legacy.
5. Reload flag. `reload_pending` is defined as "same map, re-run full checks". Reusing it for a foreign map changes the meaning of 1035-1038 and `preserve_reload` in `map_unloader`.
6. Rejection state. The local-setup test requires that every rejection leave loaded-map state byte-identical (`tests/test_hcu_map_service_local_setup.py:1-10`, assertion at 66). A live-owner staging path that touches `staged_*` before rejecting would break it.

### 3.3 Tests that would have to change

- `tests/test_c4_bsp_fault_legacy.py:161-205` runs with no live owner. Its rollback assertions (`preflight_ready`, `staged_map`, `staged_entry`, `map_used`, `scratch_used`, `source_active`, `mount_active`, `descriptor`, `canaries`) would not change, but a new foreign-stage path must keep them.
- `tests/test_hcu_map_service_local_setup.py:66` is an exact-string assertion on the capacity-path reason. It uses `HCU_M2_MP_HOST_ORACLE` (its `-D` flags at lines ~38-40). A live-owner change must keep that path intact.
- `tests/hcu_ce_map_lifecycle_main.c` and `tests/test_hcu_ce_map_lifecycle.py:250` assert the same-map deferred reload (`reload_pending` expectations at `hcu_ce_map_lifecycle_main.c:136`, `:828`, `:920`, `:1034-1040`). Any reuse of `reload_pending` for a foreign map breaks them.
- `tests/test_hcu_map_service_profile.py:70-148` covers the profile runtime and its owner/storage invariants (33 and 31 `PASS` lines). Those are profile-only and should be unaffected, but they count `PASS ` lines, so any new host test would change the counts.

### 3.4 Risk, effort, default builds, recommendation

- Risk: high. A second live reader or an arena overlap corrupts the map owner that CE is still using. The code's own comments forbid it.
- Effort: medium to high. It needs a second arena or a CE-style preflight-then-unload with weaker guarantees, plus the test changes in 3.3.
- Default builds: not affected if guarded by `HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC` (`tools/ee-world.mk:52`, default 0). The b30 capacity problem still stops it (section 1), so the diagnostic branch would also need the list changed.
- Recommendation: do not choose Route 2. It is a measurement-only admission that cannot produce a qualified result, and it violates three invariants (arena, source reader, identity) that the existing tests depend on. It would give C5 a map that was never qualified, so C5 evidence would not be trustworthy.

## 4. Logging change: `fail_preflight_for_entry` refusal reason

Current helper (`hcu_map_service.c:1229-1234`): it only clears a validated stage and prints nothing. It has four call sites: 1343 (asset-profile gate, already prints at 1341), 1352 (lifecycle injection, prints at 1351), 1432 (capacity, already prints at 1430), and 1449 (live-owner, silent).

Do not put the print inside `fail_preflight_for_entry`. Three of its four callers already print, so the helper would double-print. Print at the silent site only:

```diff
 		if (service->mount.active &&
 			strcmp(service->identity.map_name, entry->identity.map_name) == 0) {
 			...
 			return 1;
 		}
+		printf("HALO_PS2_LOCAL map-preflight rejected map=%s reason=live-owner-not-replaceable\n",
+			entry->identity.map_name);
 		fail_preflight_for_entry(service, entry);
 		return 0;
```

Safety.
- It is log-only. The state change is unchanged.
- In default builds the branch is reached only when `ui` is requested while a different owner is live, because the capacity gate admits only `ui`. The line is rare.
- No test or tool matches the absence of this line. The local-setup test asserts a different exact string (`:66`). The C4 and profile tests use `assertIn` and `PASS ` counts, which the new line does not affect. `tools/hcu_ps2_link.py` and `tests/test_hcu_ps2_closure.py` reference only `hcu_map_service_lifecycle_fail_preflight_once`, not the log text.
- The print goes to the same stdout as every other `HALO_PS2_LOCAL` line.

Verdict: safe. It is the lowest-risk change in this report and it would make the silent path visible. It does not make b30 reachable; the capacity line at 1430 already reports b30's refusal.

## 5. Recommendation

1. Take the logging change (section 4) on its own. It is safe and explains the silent path.
2. Do not take Route 2. It breaks the arena, source and identity invariants, and it would produce unqualified evidence.
3. Route 1 is the only sanctioned way to get a gameplay map into C5. It is blocked on inputs C5 does not have: a b30 partition row with measured sizing, a b30 package in the package root, and a decision on how the headless guest affects the C5 tick. Decide on that qualification work first. Until then the honest C5 result is a printed `capacity-not-qualified` refusal for b30.

## 6. Files read

- `src/stream/hcu_map_service.c` (lines 300-330, 470-520, 620-960, 1000-1130, 1220-1470, 1500-1751)
- `src/stream/hcu_map_service.h` (lines 80-310)
- `src/stream/hcu_main.c` (lines 75-125, 345-360, 405-445, 530-560, 669-790, 3412-3430, 3990-4030, 4095-4110)
- `src/stream/hcu_c5_boot.c` (lines 350-450 and header comments)
- `src/stream/hcu_memory_profile.c` (lines 279-320)
- `src/stream/hcu_map_catalog.c` (line 121)
- `tools/ee-world.mk` (lines 40-70, 165-230)
- `tools/c5_build.py` (lines 33, 170-190, 300-320)
- `tools/c2_profile_image_header.py` (lines 151-203)
- `tests/test_c4_bsp_fault_legacy.py` (lines 1-30, 161-205)
- `tests/test_hcu_map_service_profile.py` (lines 1-150)
- `tests/test_hcu_map_service_local_setup.py` (lines 1-70)
- `tests/test_hcu_ce_map_lifecycle.py` (line 250), `tests/hcu_ce_map_lifecycle_main.c` (lines 118-130, 136, 979-1040)
- `build/m2-c2-r3-selected-packages/pkg` (directory listing)
