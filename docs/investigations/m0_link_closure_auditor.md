# m0_link_closure_auditor

## Mission

Validate the ~345-unit HCU PS2 compile/link closure, unresolved-symbol classification, and source-selection boundaries (`port/ps2/port.json`, exclude lists, rooted link in `tools/hcu_ps2_closure.py`, `tools/hcu_ps2_link.py`). Determine whether the M0 exit-gate claim holds that **no unresolved simulation symbol is treated as a harmless stub**, and whether documentation matches the checked-in `build/hcu-ps2-closure/all/result.json` artifact.

## Inputs examined

| Artifact | Role |
|---|---|
| `docs/investigations/_prompt_contract.md` | Report-only rules, evidence baseline (parent `a2575e95…`, HCU `c406a414…`, ELF SHA-256) |
| `build/hcu-ps2-closure/all/result.json` | Latest `--layer all` closure report |
| `build/hcu-ps2-closure/all/rooted.o`, `halo-local.elf`, `ps2_platform_audit.json` | Rooted undefined set, final link, generated stub inventory |
| `docs/hcu-ps2-closure.md` | Published closure narrative and counts |
| `submodules/halo-ce-universal/port/ps2/port.json` | Source manifest, excludes, `port_sources`, replacements |
| `tools/hcu_ps2_closure.py` | `selected_sources`, `classify`, partial/rooted link driver |
| `tools/hcu_ps2_link.py` | Fail-closed link gate, `SKIP`, stub generation |
| `submodules/halo-ce-universal/port/ps2/game/ps2_coop.c`, `ps2_local.c`, `ps2_data.c` | Simulation/data adapters |
| `tests/test_hcu_ps2_closure.py` | Classification and manifest guards |
| `plans/5.hcu-remake.md` | M0 exit-gate wording |

## Findings

### 1. Compile closure (345 units) matches manifest + port overlay

- **`result.json`:** `compiled_count` 345, `failed_count` 0, `hcu_commit` `c406a4149ddebae4f45462ce4c1e8d9cce0567c2` (`build/hcu-ps2-closure/all/result.json:3830-3831`, `:28`).
- **`selected_source_count` 340** is only `selected_sources()` over `source/**/*.c` (`tools/hcu_ps2_closure.py:144-156`, `result.json:29`). The **`--layer all`** build adds five **`port_sources`** entries on every run (`tools/hcu_ps2_closure.py:272-273`, `port.json:15-21`), yielding **340 + 5 = 345** units with no double-count (port paths are outside `source/`).
- **Doc drift:** `docs/hcu-ps2-closure.md:110` still says “344 units”; `plans/remake-cowork.md:98` same. The live artifact and `plans/5.hcu-remake.md:11` agree on **345**.

### 2. Source-selection boundaries (`port.json`)

- **Whole-tree excludes** (`port.json:22-31`): `source/networking/`, `source/render/`, `source/rasterizer/`, editor, Bink, bungie_net, saved films, tool — CE desktop/online/render implementations are not compiled as-is.
- **Per-file excludes** (`port.json:33-63`): Windows cache paths, Xbox texture/sound cache, `profile.c` (replaced by `ps2_profile.c`), UI widgets, `structure_render.c`, etc.
- **Re-inclusions via `extra_game_sources`** (`port.json:65-68`): `render_cameras.c`, `rasterizer_geometry.c`, `rasterizer_swizzle.c` — partial render/rasterizer surface without the excluded directories.
- **Port replacements compiled as units:** `ps2_local.c` (local session / network-local branches), `ps2_coop.c` (25 local co-op hooks), `ps2_data.c` (extern data pointers + tag validators), `ps2_profile.c`, `ps2_input.c` (`port.json:15-21`).
- **`rejected_defines` enforcement:** closure aborts if `HALO_N64` or `HALO_LINUX` appear in manifest defines (`tools/hcu_ps2_closure.py:232-234`, `port.json:4`).
- **Replacement honesty:** `cache_files_windows.c` is **`planned`** with `replacement: null` and is listed in `exclude_sources` (`port.json:77-81`, `:38-39`); live `cache_file_*` / `cache_files_*` symbols remain link-time **generated** placeholders (see §6).

### 3. Rooted link mechanics

- **Roots** (unchanged): `game_initialize`, `game_tick`, `halo_shell_main`, `actors_update`, `hs_update` (`tools/hcu_ps2_closure.py:336-339`, `docs/hcu-ps2-closure.md:13`).
- **Partial link** merges all 345 `.o` files (`tools/hcu_ps2_closure.py:305-309`). **Rooted link** uses `ld -r --gc-sections` with `-u` on each root (`tools/hcu_ps2_closure.py:335-340`).
- **Rooted size in `result.json`:** `code_constants_static_data` 1,644,318 bytes, `elf_static_spare` 452,834 (`result.json:4598-4600`) — aligns with `docs/hcu-ps2-closure.md:37` (1,643,814 / 453,338; small delta likely object churn).
- **Gap:** `result.json` classifies **live externals on `layer.o` only** (`tools/hcu_ps2_closure.py:315-323`), not on `rooted.o`. Rooted reachable externals are a strict subset (530 live vs 726 on `layer.o` by recomputation); both sets have **zero** `simulation` / `data` / `unclassified`.

### 4. Unresolved-symbol classification (`classify`)

Priority order (`tools/hcu_ps2_closure.py:159-172`):

1. `toolchain` — `__*` and `TOOLCHAIN_RUNTIME` (`:21-37`, `:160-161`)
2. `simulation` — `SIMULATION_EXACT` + prefixes `network_damage_`, `network_objects_`, `network_actors_`, `coop_scripts_`, `coop_enemies_` (`:84-104`, `:162-163`)
3. `data` — `DATA_EXACT` + `tag_` / `data_` / `datum_` prefixes (`:105-109`, `:164-165`)
4. `ps2-service` — `PS2_SERVICES` + broad XDK/cache/XInput prefixes (`:39-60`, `:166-167`)
5. `excluded-feature` — desktop/editor/network UI prefixes including **`network_coop_note_`** (`:61-83`, `:168-169`)
6. `render` — `RENDER_EXACT` + rasterizer/draw prefixes (`:110-126`, `:170-171`)
7. `unclassified` — would fail the link gate (`:172`)

**Co-op correction (evidence the bug was real):** `coop_scripts_*` / `coop_enemies_*` / gameplay `network_coop_*` are **`simulation`** (`tools/hcu_ps2_closure.py:94-104`, `:102-104`). `network_coop_note_*` stays **`excluded-feature`** via prefix (`:79`, `:168-169`). Tests lock this (`tests/test_hcu_ps2_closure.py:21-43`).

**Naming hazard (documented, not blocking link today):** `EXCLUDED_EXACT` lists lowercase `create_thread` (`tools/hcu_ps2_closure.py:64`) while the live undefined symbol is `CreateThread` (classified **`ps2-service`** via `Create` prefix, `:54-58`, `:166-167`). Same pattern may apply to other XDK spellings. Broad `PS2_SERVICE_PREFIXES` (`Get`, `Set`, `Copy`, …) can preempt `excluded-feature` for symbols not listed in `SIMULATION_EXACT`/prefixes — acceptable for stub generation but risky if a future gameplay symbol matched a service prefix.

### 5. Measured relocation classes (`result.json` / rooted `nm -u`)

**On `layer.o` live externals** (`partial_link`, `result.json:3840-3841`):

| Class | Count |
|---|---:|
| excluded-feature | 287 |
| render | 189 |
| toolchain | 139 |
| ps2-service | 111 |
| simulation | **0** |
| data | **0** |
| unclassified | **0** |

`live_external_count` **726** (`result.json:3840`). **`docs/hcu-ps2-closure.md:20`** cites 773/755 historically; **`docs/hcu-ps2-closure.md:27`** cites ps2-service **115** vs artifact **111** — treat doc counts as stale unless regenerated from this `result.json`.

**On `rooted.o` for link** (`tools/hcu_ps2_link.py:269-275`): **726** undefined symbols (`nm -u`), **0** with class `simulation`, `data`, or `unclassified` (recomputed). **`halo-local.elf`:** `nm -u` **0** undefined; SHA-256 **`e45b4719d35450a77f2a541a7ed8abb877e5fbef495fc918539f8da91de597a2`** matches `_prompt_contract.md` baseline.

### 6. Link closure vs “harmless stub” (M0 gate slice)

**Fail-closed link gate (`tools/hcu_ps2_link.py:271-275`):** refuses to emit `ps2_platform.c` bodies for any rooted undefined symbol classified `simulation`, `data`, or `unclassified`. Current build passes; **562** generated definitions, all **`ps2-service` (93), `excluded-feature` (282), `render` (187)** per `ps2_platform_audit.json` (no simulation entries).

**Simulation symbols are implemented in port game units, not generated stubs:**

- **Local connection / combat / objects:** `ps2_local.c` defines `global_network_game_*`, `network_game_is_active`, `network_damage_*`, `network_objects_*`, `object_bounds_cache_*`, etc. (`ps2_local.c:31-44` and following).
- **Co-op gameplay hooks (25):** `ps2_coop.c` defines all `network_coop_*` state helpers and `coop_scripts_*` / `coop_enemies_*` reachable in the rooted image (`ps2_coop.c:23-199+`; scope documented in file header `:1-8`).
- **Data externs:** `ps2_data.c` defines pointer globals and `tag_validate_*` (`ps2_data.c:19-47`). Remaining `DATA_EXACT` records (e.g. `game_engine_globals`, `global_stage`, `error_globals`) are defined in compiled CE sources such as `source/game/game_engine.c:923-924`, `source/cseries/errors.c:70`.

**Verdict on “no unresolved simulation symbol classified as a harmless stub” (narrow, classifier + link tool):** **Holds for the current artifact.** Unresolved simulation/data/unclassified symbols are absent from the rooted undefined set; the link tool cannot silently stub them. Co-op helpers previously mis-bucketed as `excluded-feature` are now **`simulation`** and backed by real port code.

**Caveats (still open for full M0 exit gate, `plans/5.hcu-remake.md:110`):**

1. **`network_coop_note_*` (15 undefined on `rooted.o`):** Classified **`excluded-feature`** (`tools/hcu_ps2_closure.py:79`) and receive **generated no-ops** in `ps2_platform.c`. Call sites exist in live CE sources (e.g. `source/units/units.c:2362`, `source/objects/objects.c:3044`, `source/physics/breakable_surfaces.c:244`). Docs require call-site proof they are replication-only when `network_coop_active()` is false (`docs/hcu-ps2-closure.md:58`, `docs/hcu-local-coop-audit.md:22`). That is **not** the same as “simulation stub,” but it **is** a generated harmless stub on a live path until audited.
2. **Render / cache / file PS2-service stubs** (562 entries) can still affect **simulation-adjacent state** (`render`, `cache_files_precache_map_loaded`, etc.) — explicitly out of scope for the narrow simulation classifier gate but contrary to the **spirit** of M0 step 5 / M1 (`plans/5.hcu-remake.md:118`, `docs/hcu-ps2-platform-placeholder-audit.md:13-17`).
3. **`result.json` `gate`: `"open"`** (`result.json:4`) — tooling does not auto-close M0.

### 7. `SKIP` / real implementations vs generated platform

`tools/hcu_ps2_link.py:22-37` skips symbols with real port owners: physical memory, heap wrappers, time (`GetTickCount`, QPC, `GetSystemTime`), XInput quad (`ps2_input.c`), `CreateDirectoryA` / file attrs (edge), `render_location_visible`, `D3D__RenderState`. Tests assert timer and XInput ownership (`tests/test_hcu_ps2_closure.py:51-78`). Everything else undefined on `rooted.o` (except toolchain) is stubbed in `ps2_platform.c` (`tools/hcu_ps2_link.py:152-180`, `:281-305`).

### 8. Tests today vs closure artifact

- **Present:** classifier invariants, manifest/`ps2_coop.c` inclusion, replacement status, timer/XInput `SKIP`, memory-audit doc arithmetic (`tests/test_hcu_ps2_closure.py`).
- **Missing:** no test reads `build/.../result.json` to assert `partial_link.classes` has empty `simulation`/`data`/`unclassified`; no test mirrors `hcu_ps2_link.py`’s full `nm -u rooted.o` gate; no CI assertion on ELF hash / zero undefined.

## Interface contracts for the main agent

1. **Closure command:** `HALO_BUILD_JOBS=4 python3 tools/hcu_ps2_closure.py --layer all` → `build/hcu-ps2-closure/all/result.json` (`docs/hcu-ps2-closure.md:5`, `tools/hcu_ps2_closure.py:243-354`).
2. **Link command:** `python3 tools/hcu_ps2_link.py` → `halo-local.elf`, `ps2_platform.c`, `ps2_platform_audit.json` (`tools/hcu_ps2_link.py:19`, `:288-311`).
3. **Classifier is shared:** `hcu_ps2_link.py` imports `classify` from `hcu_ps2_closure.py` (`tools/hcu_ps2_link.py:17`) — single source of truth for stub policy.
4. **Simulation must be defined before link;** data/simulation/unclassified undefined on `rooted.o` is a hard error (`tools/hcu_ps2_link.py:3-5`, `:271-275`).
5. **Manifest is authoritative for CE file set;** `port_sources` are always appended for `all` layer (`tools/hcu_ps2_closure.py:272-273`).
6. **Do not treat `excluded-feature` or `render` generated bodies as implemented services** (`ps2_platform_audit.json` warning, `docs/hcu-ps2-platform-placeholder-audit.md:7-8`).
7. **Co-op:** `network_coop_active()` is false; local branches in `ps2_coop.c` / `ps2_local.c` are the supported semantics (`ps2_coop.c:23-27`).
8. **M0 memory / owner acceptance is separate** from link closure (`docs/hcu-ps2-closure.md:3-4`, `:104-106`; `result.json:4` `gate: open`).

## Recommended tests / fixtures

1. **`test_result_json_no_simulation_unresolved`:** load `build/hcu-ps2-closure/all/result.json`; assert `partial_link.classes` keys `simulation`, `data`, `unclassified` are absent or empty; assert `failed_count == 0` and `compiled_count == 345`.
2. **`test_rooted_undefined_matches_link_gate`:** run `undefined_symbols(nm, rooted.o)` + `classify`; assert no `simulation`/`data`/`unclassified` (duplicate of `hcu_ps2_link.py:271-275` in pytest).
3. **Optional:** extend `result.json` schema to record **rooted.o** live-external class counts (today only `layer.o`, `tools/hcu_ps2_closure.py:315-323`) to avoid layer/root confusion.
4. **`network_coop_note_*` reachability fixture:** under `network_coop_active()==FALSE`, trace or harness-assert that note calls are no-ops for simulation state (units, objects, breakable surfaces) — addresses §6 caveat.
5. **Regression:** keep `tests/test_hcu_ps2_closure.py:21-43` when touching `SIMULATION_*` / `EXCLUDED_PREFIXES`.
6. **Link integration test (toolchain present):** run `hcu_ps2_link.py` in CI; assert `nm -u halo-local.elf` empty and SHA-256 pinned when manifest/HCU pin unchanged.
7. **Doc sync check:** assert `docs/hcu-ps2-closure.md` unit count and ps2-service count match `result.json` fields.

## Dependencies on other investigators

- **Memory / M0 ledger:** grouped BSS owners, `ps2_platform.o` `render` storage, arena routing (`docs/hcu-ps2-closure.md:86-106`).
- **Platform-placeholder / M1:** 562 stub behaviors and cache/map critical path (`docs/hcu-ps2-platform-placeholder-audit.md`).
- **Local co-op:** two-player campaign scenarios for `ps2_coop.c` branches (`docs/hcu-local-coop-audit.md`).
- **`network_coop_note_*`:** replication vs simulation audit (cross-cut with co-op investigator).

## Open questions

1. Are all **`network_coop_note_*`** call sites dead or side-effect-free when `network_coop_active()` is false, or do some still require local presentation/state updates?
2. Should **`result.json`** close the simulation gate automatically (set `gate`/`status`) when classes are clean and `failed_count == 0`?
3. Should **`CreateThread` / Win32-thread symbols** be `excluded-feature` (match `create_thread` intent) instead of stubbed `ps2-service`?
4. Is **`live_external_count` on `layer.o`** still the right report surface, or should docs/rooted metrics be canonical?

## Handoff summary

- **345/345** units compile; **`result.json`** matches HCU pin **`c406a414…`**; **`halo-local.elf`** links with **0** undefined symbols (SHA **`e45b4719…`**).
- **Classifier + link gate:** **0** `simulation` / `data` / `unclassified` on **`rooted.o`**; **562** stubs are only ps2-service / excluded / render.
- **Narrow M0 claim** (“simulation not harmlessly stubbed”) **holds**; **full M0 exit gate** still **open** (memory owners, `gate: open`, note/render/cache stub semantics).
- **`port.json`:** 340 CE files + 5 port units; render/network dirs excluded with **3** `extra_game_sources` exceptions.
- **`ps2_coop.c` / `ps2_local.c`** own simulation co-op/network-local symbols; **`ps2_data.c`** + CE `.c` own data symbols.
- **15 `network_coop_note_*`** symbols are **excluded-feature stubs** — audit required before treating as safe.
- **Doc fixes needed:** 344→345 units; live external / ps2-service counts vs `result.json` (726 / 111).
- **`result.json` does not classify `rooted.o`** — only partial `layer.o` (`tools/hcu_ps2_closure.py:315-323`).
- **Tests** cover classifier/manifest, not **`result.json`** or end-to-end link artifact.
- **Recommended:** add `result.json` + `rooted.o` gate tests and `network_coop_note_*` reachability proof in CI.

## Corroboration

### Agreements

- **m0_memory_ledger:** ELF `e45b4719…` and **345** compile units align with closure artifacts; link does not imply memory-owner sign-off (`gate: open` on both tracks).
- **m0_runtime_ownership:** **562** stub buckets match the intended split (HCU sim in-tree, platform/render generated); no `simulation` undefined on `rooted.o` supports single-ELF direction for `halo-local.elf`.
- **m1_platform_callsite:** **562** count and classifier buckets (**93** / **282** / **187**) match `ps2_platform_audit.json`; `SKIP` symbols are correctly outside this inventory.
- **m1_pad_multitap:** XInput quad in `SKIP` + `ps2_input.c` corroborates link policy vs generated stubs.

### Conflicts

- **C5 (BSS deployment):** Contiguous `ps2_memory.o` `.bss` vs logical v2 regions — link closure is clean while ledger says routing is naming-only; no contradiction in link facts, integrator must sequence arena glue before claiming deployed layout.
- **C4 (partial):** **187** render stubs link-resolve but are not implemented services — agrees with m0 “do not treat as implemented.”

### Updated handoff

1. Close M0 link slice: add `result.json` + `rooted.o` class tests; sync `docs/hcu-ps2-closure.md` counts (**726** live externals, **345** units).
2. Treat **15** `network_coop_note_*` as Round 2 follow-up with **m1_platform** (live refs, R3 tier) before M3 sim hash claims.
3. Defer automatic `gate: closed` until memory grouped owners accept — per **m0_memory** and remake plan M0 exit.
