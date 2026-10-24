# C2.8 guest evidence: foreign replacement, failed preflight, fail then retry (2026-10-24)

Evidence level: PCSX2 interpreter, production headless runtime guest (no renderer loop, no DMA/GS readers). The renderer-drain proof is C3.11 and stays out of scope; the existing headless drain predicate (`renderer_drained`, `renderer_never_started`) gates every unload and successor stage here.

Closes the C2.8 items that were host-only: (a) foreign-profile replacement through the real map service, (b) a failed successor preflight preserves the old map, (c) a failed successor load followed by a successful retry. All four runs below passed, with zero failures on every owner, arena and cache-owner line.

## Pair choice

Partition row `boardingaction_mounted_gunner_4p4bot` (A = `boardingaction`): tag cap 4,673,104 B, BSP cap 1,354,160 B (the guest's `partition-selected` line). A successor shares the row's guarded owners, so it must fit those caps. From the guarded fit table (peak plus margin = cap) the same-family rows whose peaks are at or below A's caps are beavercreek, carousel, chillout, damnation, hangemhigh, longest, prisoner, ratrace and wizard (putput's BSP 1,638,400 B, bloodgulch and sidewinder do not fit). I picked `damnation_mounted_gunner_4p4bot` (B = `damnation`) because it is the tightest fit, not the easiest: measured tag 4,662,634 B (10,470 B under the cap) and BSP 1,320,960 B (33,200 B under the cap). The extra pair `boardingaction` to `ui` (tag 789,137 B, BSP 2,048 B) shows a row replaced by the UI package.

The service requires the successor's spans to be disjoint from the live runtime's, so the guest splits the row's 1 MiB residency span: the selected runtime keeps the first 8 x 64 KiB slots, the successor takes the second 8. Both loaded within half a span with zero failures. Metadata and relocation storage for B come from the 1,048,576 B `streaming_map_owner` arena (used 252,992 B with both registered; 795,584 B free); B's stream scratch comes from the section scratch arena.

## Mechanism (opt-in, off by default)

- `tools/c2_profile_boot_matrix.py --rows ROW --successor SUCC_ROW [--successor-fault none|preflight|load] [--successor-ticks N]` writes `<out>/succ-inc/hcu_c2_successor.h` (mode, ticks) and `hcu_c2_succ_image.h` (the successor row's generated image header from `tools/c2_profile_image_header.py`, identifiers renamed `HCU_C2_IMAGE_*` to `HCU_C2_SUCC_*`, content verbatim) and puts that directory on `C_INCLUDE_PATH` for the link, like `--cycles`. No build script changed.
- `src/stream/hcu_main.c` (only when both headers exist): opens the successor's package and source maps, registers it with `hcu_map_service_register_successor_runtime` beside the selected runtime (own metadata, relocation, scratch, residency half), and fills the successor name/scenario for CE. Its package reader honours a transient fault gate (`hcu_c2_successor_fault_armed`): while armed every successor package read fails, so the pinned-digest gate fails closed. Nothing is skipped or weakened. The boundary hook also prints the `streaming_map_owner` arena per phase.
- `src/stream/hcu_map_service.c`: the headless candidate admission only accepted the selected runtime's own map, so a registered successor was rejected as `headless-candidate-capacity`. It now admits a registered successor under its own runtime when it names the same partition row. With no successor registered the branch behaves as before. Host test `test_headless_admission_accepts_a_registered_foreign_successor` fails without this change (checked by compiling the fixture against the HEAD service: assertion at the successor preflight).
- `submodules/halo-ce-universal/source/main/main.c` (`HALO_PS2_C2_PRODUCTION_RUNTIME_GUEST`, only when `<hcu_c2_successor.h>` exists): after the cycle-1 load, runs CE's own transaction for the successor: `ps2_cache_preflight_map`, `game_dispose_from_old_map` (old tags live), `game_unload` (unpublish), `game_precache_new_map`/`main_new_map`, with a machine-checkable `production-ce-successor-step` line after each step (old/new mounted flags, tag/BSP owner bytes, failure/rejection/unmount/reset counters, CE scenario and BSP presence, fault count). Then 30 CE ticks on the surviving map, then the normal release block releases whichever map survives (so the only `production-ce-map-released result=` line is the terminal one).

Modes: `none` = replacement; `preflight` = the fault gate is armed during the successor's preflight; `load` = the first attempt's gate is armed after the old owner is unpublished, so the service's post-unload revalidation of the successor fails and CE is left with no map, then CE retries without the fault.

### Default build unchanged

Without the headers the changed files compile to the same code. Same flags as the link, `-g0`: `hcu_main.o` sha256 `8a056d9a...9d204`, `main.c` (CE) object `188d4d3c...ef06`, each byte-identical to the object built from `git show HEAD:` of the same file (and the `-E` output identical). `hcu_map_service.o` in the headless build is not byte-identical, because of the admission branch; its behaviour with no successor registered is the same (`admitted` is `&service->runtime`, same map and row checks).

## Results (build/m2-c2-foreign/boardingaction_mounted_gunner_4p4bot/)

Driver commands: `python3 -I tools/c2_profile_boot_matrix.py --rows boardingaction_mounted_gunner_4p4bot --successor damnation_mounted_gunner_4p4bot [--successor-fault preflight|load]`, and `--successor ui`. Each run is a fresh link plus one PCSX2 run (`timeout`, DISPLAY=:99). `build/m2-c2-matrix/summary.json` was not touched (mtime 04:49:06, before this lane).

| Case (directory) | Result | Checks | Guest elapsed incl. link | Boot end | Margin to 0x1a40000 |
|---|---|---:|---:|---|---:|
| `damnation_mounted_gunner_4p4bot-replace` | pass | 32 | 569.7 s | 0x1a148da | 177,958 B |
| `damnation_mounted_gunner_4p4bot-failed-preflight` | pass | 26 | 396.4 s | 0x1a147da | 178,214 B |
| `damnation_mounted_gunner_4p4bot-fail-then-retry` | pass | 37 | 548.9 s | 0x1a14ada | 177,446 B |
| `ui-replace` | pass | 32 | 342.7 s | 0x1a09f5a | 221,350 B |

Boot end rises from 0x19dd45a (the plain row, margin 404,390 B) because the second image and the successor code are in the ELF; every run stays below the 0x1a40000 reserve, and `config/memory-budget.json` is untouched. Failure counters were checked on 184 lines (replace, retry, ui) and 144 (failed preflight), all zero; `renderer_drained=1` at every boundary.

### (a) Foreign replacement, boardingaction to damnation

Steps in order, all result=1 (`production-ce-successor-step`):

| Step | old mounted | new mounted | tag / BSP bytes |
|---|---:|---:|---|
| preflight (CE, before touching A) | 1 | 0 | 4,673,095 / 1,343,488 |
| dispose (A's tags live) | 1 | 0 | 4,673,095 / 1,343,488 |
| unload (A unpublished) | 0 | 0 | 0 / 0 |
| load (B mounted, not yet read by CE) | 0 | 1 | 0 / 0 |
| new-map (CE built B) | 0 | 1 | 4,662,634 / 1,320,960 (1,910 tags, scenario and BSP present) |

Service boundaries: `map-loaded 1`, `map-released 1` (before the successor mount), `map-loaded 2`, `map-released 2`. Two successful successor stages (pre-unload, plus the post-unload revalidation CE's unloader forces), one successor mount, no rejection, no fault. Final release: tags and bsp `used` 0, both cache owners `current` 0 with 2 publications, 2 unmounts, 2 resets; game_state, tags and bsp owner resets 2; backing used 3,382,400 / high 9,398,983, equal to the same-map two-cycle value in the matrix for boardingaction (9,398,983), so B raised no peak above A's. `streaming_map_owner` used 252,992 B at every boundary. 30 ticks on B ran (`production-ce-successor-usable result=1 ticks=30 local-players=1`); terminal `production-ce-map-released result=1 map=damnation mounted=0 tag-bytes=0 bsp-bytes=0`.

`ui-replace`: same sequence to `ui` (tag 789,137 B, BSP 2,048 B, 366 tags), same boundary sequence and final owner state; `streaming_map_owner` used 140,184 B.

### (b) Failed preflight preserves the old map

B's preflight failed on the injected package-read fault: `successor-fault injected kind=package-read`, `profile-preflight rejected reason=successor-package-gate map=damnation`. `preflight` step result=0 with A still mounted, tag/BSP bytes still 4,673,095 / 1,343,488; `after-failed-preflight` identical, scenario and BSP present, no `map-released` boundary in between (boundaries: `map-loaded 1`, `map-released 1` only). 30 ticks then ran on A (`production-ce-successor-usable result=1 old=boardingaction ticks=30 local-players=1`) and the run ended by releasing A (`production-ce-map-released result=1 map=boardingaction`), one publication, one unmount, resets 1.

### (c) Failure then retry

Attempt 1: preflight passes, A disposed with tags live, A unpublished (`map-released 1`), then the fault fires at the service's post-unload revalidation of B (`successor-fault injected ... size=32`, one `successor-package-gate` rejection). `load` result=0 and `after-failed-load`: neither map mounted, tag/BSP bytes 0 / 0, counters still zero, no mount. The service keeps the successor registered. Retry (`production-ce-successor-retry`): preflight, dispose and unload run against the empty state (0 mounted, 0 bytes), B mounts (`map-loaded 2`), CE builds it (4,662,634 / 1,320,960), 30 ticks, release. Final owner state equals the replacement run (2 publications, 2 unmounts, 2 resets, backing high 9,398,983). In the retry CE never calls the unloader (no map is loaded), so there is one stage pass and no second revalidation; total successful stage passes are 2.

## Tests

- `tests/test_c2_profile_boot_matrix.py`: 44 passed (20 new: replacement, failed-preflight and retry log parsing with each negative case, header rename, include files, stage paths, CLI validation, summary.json never rewritten, same-row/same-map refusal, `released_map`).
- `tests/test_hcu_map_service_profile.py`: 2 passed (new headless variant, 28 PASS lines, covers successor admission, other-row refusal, unknown-map refusal, B's own later cycles).
- `tests/test_hcu_profile_mount.py`: passed; `tests/test_c2_guest_run.py`, `tests/test_c2_guest_parse.py`: passed.
- `tests/test_hcu_ce_map_lifecycle.py::test_real_ce_load_unload_and_same_map_reload` fails in setup with `ProfileValidationError: HCP media chunk exceeds 65536-byte decoded limit` in `tools/hcu_profile_validate.py` (the ui HCP1 package), before any compiled code of this lane runs. I did not verify it against HEAD; it is outside the files touched here.

## Limits

- The late failure is the service's post-unload package revalidation, not a failure inside `hcu_profile_mount_load` or the CE tag stream; the scripted host fixture covers the mount-load failure only.
- Fault injection is a transient read failure on the successor package, not a corrupted package; the pinned digest is not bypassed.
- `tools/c2_guest_run.py` reports `guest_completed=false` for the replacement, retry and ui runs because its tuple check expects the terminal release to name the selected row's map; those runs end on the successor's release. The verdict is `result.json` from this tool, not the runner's flag (the failed-preflight run ends on A and shows true).
- One pair of maps and one row; 30 ticks on the surviving map; interpreter only. Renderer-held DMA/GS readers (C3.11) are not exercised.
