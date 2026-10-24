# m1_platform_callsite_auditor

## Mission

Classify all **562** generated link-closure placeholders in `build/hcu-ps2-closure/all/ps2_platform.c` by **live call-site reachability** (rooted HCU image vs. textual references) and **simulation risk**, using the platform audit artifact, linker generator rules, and M1 family triage in `docs/hcu-ps2-platform-placeholder-audit.md`. Produce a report-only disposition ledger for the main agent; do not treat classifier labels or no-ops as behavioral proof.

## Inputs examined

| Source | Role |
| --- | --- |
| `docs/investigations/_prompt_contract.md` | Report contract, evidence baseline |
| `docs/hcu-ps2-platform-placeholder-audit.md` | M1 family risks, gate sequence, 562 inventory summary |
| `docs/hcu-ps2-closure.md` | Rooted roots, class counts, `ps2_input` / time ownership notes |
| `build/hcu-ps2-closure/all/ps2_platform_audit.json` | Per-symbol class, behavior, declaration, `source_references` |
| `build/hcu-ps2-closure/all/ps2_platform.c` | Generated bodies (574 lines, 562 definitions) |
| `tools/hcu_ps2_link.py` | `SKIP` list, `standin_audit()` reference scan, emit rules (`L22-L38`, `L184-L223`, `L269-L291`) |
| `tools/hcu_ps2_closure.py` | `classify()` buckets (`L39-L172`) |
| `submodules/halo-ce-universal/port/ps2/port.json` | Selected sources, excluded `cache_files_windows.c`, planned cache adapter (`L77-L82`) |
| `submodules/halo-ce-universal/source/cache/cache_files.c` | Live `scenario_tags_load`, precache, `cache_file_open`/`read` callers (`L649`, `L812-L900`, `L1189-L1260`) |
| `submodules/halo-ce-universal/source/game/game.c` | `game_precache_new_map` blocking loop (`L812-L900`) |
| `submodules/halo-ce-universal/port/ps2/src/ps2_edge.c` | Partial file/launch stand-ins **outside** the 562 (`CreateDirectoryA`, `GetFileAttributesA`, errors) |
| `submodules/halo-ce-universal/port/ps2/game/ps2_coop.c` | Real `network_coop_*` simulation hooks (not placeholders) |
| `docs/investigations/m1_startup_guest_path_auditor.md` | Boot chain cross-deps |
| `docs/investigations/m1_pad_multitap_auditor.md` | XInput bridge vs. generated `XInitDevices` |

Evidence baseline (contract): parent `a2575e957feefbdff27febedabf60590401e6bcc`, HCU `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`, `halo-local.elf` SHA-256 `e45b4719d35450a77f2a541a7ed8abb877e5fbef495fc918539f8da91de597a2` when present.

## Findings

### 1. Inventory reconciliation (562 placeholders)

The refreshed audit JSON matches the parent audit doc:

| Dimension | Count |
| --- | ---: |
| **Total generated definitions** | 562 |
| Functions / data | 485 / 77 |
| **Classifier `class`** | `ps2-service` 93, `render` 187, `excluded-feature` 282 |
| **Generated behavior** | `no-op` 261, `returns-zero-or-null` 223, `zero-initialized-storage-placeholder` 77, `drops-message` 1 (`platform_log`) |

**Link closure roots** (from `hcu_ps2_closure.py` / closure doc): `game_initialize`, `game_tick`, `halo_shell_main`, `actors_update`, `hs_update`. Every symbol in the 562 set is an undefined relocation satisfied by `ps2_platform.c` in the current `halo-local.elf` link; `hcu_ps2_link.py` refuses to generate bodies for symbols classified as `simulation`, `data`, or `unclassified` (`L271-L275`).

**Implemented outside the 562** (`tools/hcu_ps2_link.py` `SKIP`, `L22-L38`): physical memory, CRT allocators, Dm walk stubs, `rasterizer_initialize`, `DirectSoundCreate`, directory/attribute/error helpers in `ps2_edge.c`, monotonic/UTC time in `ps2_time.c`, and the four core XInput entry points in `ps2_input.c` (compiled into `rooted.o`, not recompiled in the link step). `D3D__RenderState` and `render_location_visible` live in `ps2_edge.c`.

**Not in the 562 but on the startup path:** `CreateDirectoryA` / `GetFileAttributesA` / `GetLastError` / `SetLastError` (`ps2_edge.c:88-115`) — partial virtual FS for `custom_maps` only; all other file I/O in the table below remains generated zero/null.

### 2. Methodology: “live call site” vs. audit `source_references`

`standin_audit()` (`hcu_ps2_link.py:184-223`) builds `source_references` by **identifier text search** over all of `submodules/halo-ce-universal/source/**/*.c`, not by relocations from `rooted.o` and **not** filtered by `port/ps2/port.json` exclusions.

Implications:

1. **Strong live evidence:** symbol is undefined in the rooted link **and** referenced from a **manifest-selected** `.c` file (345 units per closure doc).
2. **Weaker / dead text:** references exist only in **excluded** sources (e.g. `source/cache/cache_files_windows.c`, `source/interface/progress_bar.c`, `source/rasterizer/**`) — **31 symbols** (see §7).
3. **Link-only / no CE source mention:** **5 symbols** with empty `source_references` but still generated because `nm -u rooted.o` lists them (`GetDiskFreeSpaceExA`, three `XDEVICE_TYPE_*_TABLE` data blobs, `halo_ps2_wcstok`).

Filtered counts (manifest-selected references only):

| Bucket | Symbols |
| --- | ---: |
| Referenced from ≥1 selected `source/` or `port/ps2/` file | 526 |
| Text refs only in excluded/uncompiled sources | 31 |
| No text refs in `source/` (link closure only) | 5 |

Every `render` entry (187/187) has at least one textual reference; most hit headers plus `.c` (e.g. `rasterizer.h` + `rasterizer.c`).

### 3. Simulation risk tiers (all 562)

Risk describes **potential to alter lifecycle, simulation, or error visibility** if the generated body remains a success-shaped no-op or zero/null return. It does **not** close M1.

| Tier | Count | Meaning |
| --- | ---: | --- |
| **CRITICAL_map_lifecycle** | 13 | Cache/precache API; blocks or corrupts map load |
| **CRITICAL_io** | 7 | Win32 file handles used by cache/tags/saves |
| **HIGH_ce_map_path** | 16 | `custom_edition_*` map/tag path (stubs return false/null) |
| **HIGH_sync_timing** | 6 | `Sleep`, `SwitchToThread`, threads/events — spin/wait behavior |
| **HIGH_input_semantics** | 3 | `XInitDevices`, `XInputDebugInitKeyboardQueue`, `XInputSetState` (core XInput in `ps2_input.c`; these remain stubs) |
| **HIGH_render_state_coupling** | 35 | `render*`, frame begin/end/present, map dispose/init render hooks |
| **MEDIUM_sound_selection** | 10 | `sound_cache_*`, `_sound_cache_sound_request` |
| **MEDIUM_texture_binding** | 6 | `texture_cache_*`, `_texture_cache_bitmap_get_hardware_format` |
| **MEDIUM_error_visibility** | 7 | `display_error_*`, `platform_show_message` |
| **MEDIUM_load_ui_loop** | 4 | `progress_bar_*` (UI source excluded; **game.c** still calls them in precache) |
| **MEDIUM_memory_reporting** | 2 | `GlobalMemoryStatus`, `LocalSize` |
| **MEDIUM_render_draw_only** | 152 | Rasterizer/draw helpers with weaker direct sim coupling |
| **REVIEW_network_stub** | 52 | `network_*`, session clients, `network_coop_note_*` no-ops |
| **LOW_*** | 48 | Bink, editor, diagnostics, text-dead, link-only |
| **REVIEW_other** | 201 | Residual excluded-feature symbols (D3D device state, dsound, UI, debug, etc.) |

### 4. CRITICAL — cache, map lifecycle, and file I/O (M1 gate)

`cache_files_windows.c` is **excluded** from the PS2 manifest (`port.json:39`). Implementations of `cache_file_open`, `cache_file_read`, and the precache family exist only in that file on Xbox; on PS2 they are **entirely** the generated stubs in `ps2_platform.c`. `cache_files.c` remains compiled and calls them directly.

**Representative generated bodies** (`ps2_platform.c`):

- `cache_file_open` → null handle / false success shape (`returns-zero-or-null`).
- `cache_file_read` → returns zero **without** setting `*completion_flag_reference` (`ps2_platform.c:137`).
- `cache_files_precache_map_begin` / `cache_files_precache_map_loaded` / `cache_files_precache_map_status` → false/zero (`returns-zero-or-null`).
- `SwitchToThread` → no-op return 0 while `scenario_tags_load` spins on `read_complete` (`cache_files.c:1246-1249`).

**Live manifest call sites (highest severity):**

| Symbol | Behavior | Selected-source callers (audit) |
| --- | --- | --- |
| `cache_files_initialize` | no-op | `cache_files.c` → `tag_files_open` (`shell.c` startup) |
| `cache_file_open` / `cache_file_read` / `cache_file_close` | zero/null / no-op | `cache_files.c` `scenario_tags_load` (`L1233-L1257`) |
| `cache_files_precache_*` | mostly zero/null | `game.c` `game_precache_new_map` (`L818-L883`), `main.c`, `cache_files.c` |
| `CreateFileA`, `ReadFile`, `GetFileSize`, `SetFilePointer`, `CloseHandle` | zero/null | `cache_files.c`, `tag_files/files_windows.c`, `saved games/*` |
| `texture_cache_open` / `sound_cache_open` | no-op | `scenario_tags_load` (`cache_files.c:1199-1200`) |

**Blocking loop evidence** (`game.c:812-900`): blocking precache waits on `cache_files_precache_map_status` in a loop calling `main_pregame_render` until non-zero status, then asserts `cache_files_precache_map_loaded`. With current stubs, `cache_files_precache_map_begin` fails the guard at `L834-L848` or never completes status — **map load cannot reach retail semantics**. This aligns with `docs/hcu-ps2-platform-placeholder-audit.md` and manifest `planned` cache adapter (`port.json:77-82`).

**Disposition:** all 20 CRITICAL symbols → **`open`** — require real PS2 cache/map/file owner (M1/M2); no success-shaped stand-in.

### 5. HIGH — time, threads, input, render coupling, CE maps

#### 5a. Sync / threads (`ps2-service`, generated)

| Symbol | Live selected refs | Risk note |
| --- | --- | --- |
| `Sleep` | `main.c` | Menu/idle timing; zero sleep → tight spin |
| `SwitchToThread` | `cache_files.c` | **Busy-wait** with broken `cache_file_read` completion |
| `CreateThread`, `WaitForSingleObject`, `ResumeThread`, `SetEvent` | `input_xbox.c` (`input_initialize` uses `CreateThread` path) | Keyboard thread / input init may not run; see pad auditor |

#### 5b. Input (`ps2-service`)

| Symbol | Owner | Note |
| --- | --- | --- |
| `XInputOpen/Close/GetState/GetDeviceChanges` | **`ps2_input.c`** (in `rooted.o`, SKIP) | Semantic adapter; needs pad bridge (`m1_pad_multitap_auditor.md`) |
| `XInitDevices` | **generated stub** | `input_xbox.c:1194` — device tables not initialized on PS2 |
| `XInputDebugInitKeyboardQueue`, `XInputSetState` | **generated stub** | Keyboard queue / rumble |

#### 5c. Custom Edition path (`excluded-feature` classifier, still **live** in `cache_files.c`)

All 16 `custom_edition_*` symbols are `returns-zero-or-null` or no-op but are referenced from **`cache_files.c`** (e.g. `custom_edition_level_name`, `custom_edition_cache_tags_load` at `L1206-L1210`). CE-on-disk maps are **not** optional for the ported `scenario_tags_load` branch: stubs force the retail `cache_file_open` path, which is also stubbed.

**Disposition:** **`open`** for PS2 data-root / converted image policy (M2 design); until then treat as **HIGH** false-negative map detection.

#### 5d. Render (`render` class, 187 symbols)

Classifier assigns `render` by name (`hcu_ps2_closure.py:110-126`); parent owns GS/VU (`hcu-ps2-closure.md`).

| Sub-bucket | Count | Sim coupling |
| --- | ---: | --- |
| `rasterizer_*` | 104 | Frame/window/present hooks; globals as zero-init **data** |
| `render_*` + `render` | 47+1 | `render_frame`, `render_initialize`, map dispose — tied to `main.c` / `game.c` |
| `build_sprite*`, `structure_render*`, other | 35 | Draw path; may still touch globals read by sim |

**35 HIGH_render_state_coupling** symbols include `render`, `render_frame`, `render_frame_present`, `rasterizer_frame_begin/end`, `rasterizer_present`, `render_initialize`, `render_initialize_for_new_map`, `process_ui_widgets`, `first_person_legs_reset`, `rendered_cluster_get`, etc. Empty bodies mean **no presentation** but CE may still advance some flags only inside these functions on Xbox — M3 must prove tick/snapshot contract (`m3_snapshot_render_auditor.md` dependency).

**Disposition:** default **`state-only adapter` or parent render seam`** for HIGH tier; **`presentation-only`** for MEDIUM_draw (152) unless call-graph shows sim writes.

### 6. MEDIUM — sound, texture, errors, progress UI, memory reports

| Family | Symbols | Live path | Disposition |
| --- | --- | --- | --- |
| Sound cache | 10 + `interrupt_result` data | `cache_files.c`, `sound_dsound_xbox.c`, predicted resources | **`open`** bounded request channel; sim must not wait on playback |
| Texture cache | 6 + `_texture_cache_bitmap_get_hardware_format` | Tag load, bitmap paths | **`open`** staging reads; format helper returns null |
| Diagnostics | 7 `display_error_*`, `platform_show_message` | Cache failures, UI, cinematics | **`state-only`** — errors must stay observable in tests |
| `progress_bar_*` | 4 | `game.c` precache loop (`L864-L875`) | **`unreachable` or stub UI** — progress bar `.c` excluded; calls still linked |
| `GlobalMemoryStatus` / `LocalSize` | 2 | Bink, `cseries_windows.c` | **`open`** honest memory reporting |

### 7. REVIEW — network, coop notes, excluded-feature bulk

#### 7a. `network_coop_*` simulation hooks

**Not in the 562:** `network_coop_active` and related **simulation** symbols are implemented in `port/ps2/game/ps2_coop.c` (manifest `port_sources`).

#### 7b. `network_coop_note_*` (15 symbols, `excluded-feature`, no-op stubs)

**Live** on manifest paths: `units.c`, `objects.c`, `game_sound.c`, `hud_messaging.c`, `hud_nav_points.c`, `breakable_surfaces.c`, `scenery.c`, etc. Linux implementations live under `port/linux/game/network_coop.c`; PS2 replaces them with empty stubs.

**Risk:** notes are replication/event fan-out on desktop; for **local** PS2, no-ops are likely safe **if** callers do not gate local sim on note side effects. This is **not proven** without per-caller review or guest trace.

**Disposition:** **`unreachable-with-proof` per callsite** or **`state-only` local shim** — track in M22/co-op tests; do not blanket-approve `excluded-feature`.

#### 7c. Other `network_*` / online (37+ symbols)

`main.c`, `game.c` reference `network_game_*`, `dispose_global_network_game_*`, `initialize_network_game_packets`, etc. Manifest excludes `source/networking/` directory but **main** still contains menu/network branches.

**Disposition:** **`unreachable` for local-game boot path** requires call-graph proof from `m1_startup_guest_path_auditor`; until then **`REVIEW_network_stub`**.

#### 7d. Excluded-feature prefix groups (282 total)

| Group | ≈Count | Typical disposition |
| --- | ---: | --- |
| `network_*` | 50 | Proof of unreachable or stub |
| `DirectSound*` / `dsound_*` | 36 | Presentation; `DirectSoundCreate` already fails closed in `ps2_edge.c` |
| `D3DDevice_SetRenderState_*` | 30 | 28 refs only in excluded `progress_bar.c` — **text-dead on PS2** |
| `debug_*`, `collision_debug` | 28 | Diagnostics |
| `custom_edition_*` | 16 | See §5c |
| `ui_*`, `telnet_*`, `bink_*`, `editor_*` | 30 | Low local-game priority |

### 8. LOW / text-dead / link-only (36 symbols)

**31 symbols** — audit references **only** excluded sources (full list: `CreateEventA`; `D3DDevice_SetRenderState_*` ×28; `D3DDevice_SetRenderState_PSTextureModes` also refs excluded rasterizer fog). **Disposition:** **`unreachable` on PS2 image** (manifest exclusion); retain in audit for link completeness.

**5 symbols** — no `source/` text refs: `GetDiskFreeSpaceExA`, `XDEVICE_TYPE_*_TABLE` ×3, `halo_ps2_wcstok`. **Disposition:** **`link_closure_only`** — verify no future selected source imports; low immediate sim risk.

### 9. Classifier vs. behavior matrix (ps2-service 93)

| Bucket | Count | Manifest-live | Notes |
| --- | ---: | ---: | --- |
| Win32 file API | 15 | 15 | All CRITICAL_io or save/tag paths |
| Cache / precache | 13 | 13 | CRITICAL_map_lifecycle |
| XInput / XInit | 13 | 4 live in stubs; 4 real in `ps2_input.c` | Split ownership |
| Sound cache | 10 | 10 | MEDIUM |
| Diagnostics | 8 | 8 | MEDIUM_error_visibility |
| Texture cache | 6 | 6 | MEDIUM |
| Thread/sync | 3 | 3 | HIGH_sync_timing |
| Alloc reporting | 2 | 2 | MEDIUM |
| Other (`platform_log`, stack_walk*, `halo_keyboard_actions`, etc.) | 23 | 18 | Mixed LOW–MEDIUM |

### 10. Top manifest-live files by placeholder symbol hits

Audit text hits (includes header co-references); useful for prioritizing call-site review:

| File | Placeholder symbols (audit) |
| --- | ---: |
| `source/main/main.c` | 62 |
| `source/cache/cache_files.c` | 51 |
| `source/game/game.c` | 42 |
| `source/game/game_engine.c` | 34 |
| `source/sound/sound_dsound_xbox.c` | 41 |
| `source/render/render.c` | 25 |
| `source/saved games/saved_game_files.c` | 16 |

`source/cache/cache_files_windows.c` (33 symbols in unfiltered audit) is **not compiled** on PS2 — those references must not be used as proof of runtime behavior.

### 11. Disposition summary (562 rows → four M1 buckets)

| Disposition | Count | Description |
| --- | ---: | --- |
| **`open` — required service** | 20 | CRITICAL cache + Win32 I/O |
| **`open` — high priority** | ~70 | CE maps, sync/input gaps, sound/texture/error channels, HIGH render coupling |
| **`adapter` / parent seam** | ~187 | `render` class — presentation or state publish |
| **`proof_unreachable` or LOW** | ~285 | Excluded desktop/network/debug; 31 text-dead + coop notes pending proof |

Exact per-symbol rows: regenerate from `ps2_platform_audit.json` with manifest filter (scriptable); this report keeps family-level evidence to avoid duplicating 562 lines in git.

### 12. Generator contract reminders (`hcu_ps2_link.py`)

- Void functions → empty body (`no-op`).
- Non-void → `memset` zero return (`returns-zero-or-null`) — **indistinguishable from “success”** for many Win32 `BOOL`/`HANDLE` APIs.
- Data → zero-init BSS-style placeholders (77), including `rasterizer_globals`, `render_globals`, `interrupt_result`.
- `platform_log` → empty variadic (`drops-message`).
- Missing declaration → link fails (`missing` list); current closure has **zero** missing.

## Interface contracts for the main agent

1. **Audit JSON is necessary but not sufficient for “live”:** filter `source_references` against `port/ps2/port.json` selected sources before closing a symbol as unreachable.
2. **Cache/map owner is the M1 blocker:** 13 `cache_files_*` / `cache_file_*` + 7 file APIs must be replaced together; `cache_files_windows.c` cannot be linked as-is.
3. **`cache_file_read` must set completion flags and honor `_cache_file_read_failed` semantics** (`cache_files.h:25-31`) — a zero return alone is unsafe with `while (!read_complete) SwitchToThread()` (`cache_files.c:1246-1249`).
4. **Keep `SKIP` symbols out of `ps2_platform.c`:** extend real implementations in `port/ps2/src/*` and add to link objects if needed (`ps2_input.c` is only in `rooted.o` today).
5. **`network_coop_note_*`:** do not treat `excluded-feature` as approval; require callsite proof or local no-op shim documented per function.
6. **Render stubs:** any symbol in HIGH_render_state_coupling must either advance agreed snapshot fields or be proven draw-only via relocation trace (`m3_snapshot_render_auditor`).
7. **Regenerate evidence bundle** when manifest or roots change: `python3 tools/hcu_ps2_link.py` → `ps2_platform_audit.json` + ELF hash.

## Recommended tests / fixtures

1. **Negative map load:** `game_precache_new_map` / `scenario_tags_load` with missing image — must surface error, not infinite loop (`cache_file_read` + `SwitchToThread`).
2. **Positive bounded read:** fixture tag image via planned adapter — `cache_files_precache_map_status` reaches `_cached_map_file_success`, `cache_files_precache_map_loaded` true (`game.c:880-895` asserts).
3. **Partial read / `_cache_file_read_failed`:** completion flag `2` path (`cache_files.c:1254-1259`).
4. **Precache non-blocking:** `main_queue_map_name` path (`game.c:828-831`) without wedging `main_loop`.
5. **Input init:** `input_initialize` with stubbed `XInitDevices` / thread APIs — document expected degradation; full test after pad bridge.
6. **Coop note smoke:** one combat + HUD frame with `network_coop_active()==FALSE` (`ps2_coop.c`) — guest trace that `network_coop_note_*` stubs do not prevent local effects (contrast Linux `network_coop.c`).
7. **Render/tick:** compare `render_frame` / `game_tick` ordering with null renderer harness (parent/HCU combined image).

## Dependencies on other investigators

| Investigator | Dependency |
| --- | --- |
| `m1_startup_guest_path_auditor` | Which `main.c` / menu branches call `network_game_*` during local boot |
| `m1_pad_multitap_auditor` | `XInitDevices`, `CreateThread`, `XInputSetState` stubs vs. `ps2_input.c` |
| `m3_snapshot_render_auditor` | HIGH render list vs. tick snapshot contract |
| `m0_runtime_ownership_auditor` | Arena routing vs. `GlobalMemoryStatus` / cache buffers |
| M2 cache design | Converted image + CE custom map policy for `custom_edition_*` |

## Open questions

1. **Will PS2 link compile `ps2_input.c` directly** (today only in `rooted.o`) when parent machine joins the same ELF?
2. **`progress_bar_*`:** stub in platform vs. exclude calls from `game.c` for PS2 — UI module is manifest-excluded but game precache still invokes it.
3. **`network_coop_note_*`:** per-function audit vs. blanket no-op for local SKU — any caller that mutates sim only inside the note implementation?
4. **Hardware format helper:** `_texture_cache_bitmap_get_hardware_format` referenced from headers 18× — null return impact on tag load validation.
5. **Saved game X APIs:** `XCreateSaveGame`, `XFindFirstSaveGame`, etc. — live in `saved_game_files.c`; interaction with PS2 `game_state_xbox.c` bypass unverified.

## Handoff summary

The **562 generated placeholders** break down as **93 ps2-service**, **187 render**, and **282 excluded-feature**, with behaviors dominated by **261 no-ops** and **223 zero/null returns**. **`standin_audit` text references over-approximate live sites:** **526** symbols touch manifest-selected sources; **31** are text-dead on PS2 (mostly D3D render-state setters from excluded progress bar); **5** are link-only.

**M1-critical gap:** the entire **cache/map/file stack** (20 symbols, CRITICAL tier) is still generated nonsense while `cache_files.c` and `game_precache_new_map` remain on the rooted path — **no retail map load** until the planned cache adapter (`port.json`) replaces `cache_files_windows.c` semantics. **Time and core XInput** are partially real (`ps2_time.c`, `ps2_input.c`); **XInitDevices, thread, and rumble/keyboard helpers** remain stubs. **187 render** and **282 excluded-feature** entries are not blanket-safe: **35** render symbols are **HIGH** sim/presentation coupled; **15** `network_coop_note_*` stubs are live from gameplay code despite `ps2_coop.c` covering the simulation `network_coop_*` API.

**Next agent actions:** implement/cache owner for CRITICAL family; filter audit JSON to manifest-live refs for per-symbol ticketing; prove or replace HIGH render and network note stubs; regenerate `ps2_platform_audit.json` and ELF hash after each closure change.

## Corroboration

### Agreements

- **m1_startup_guest_path:** **R4** cache cluster blocks `game_precache_new_map` after menu path; `CreateDirectoryA` is **`SKIP`** (`ps2_edge.c`) — startup blocker is separate from **562** inventory but still guest-critical.
- **m2_loader_failure:** Success-shaped **ReadFile** / **cache_file_open** stubs violate L0–L6 fail-closed intent until real adapter lands.
- **m3_snapshot_render:** **187** render stubs + zeroed **`render`** global explain why CE tick can advance while presentation timers may not — NOTES seam is mandatory.
- **m0_link_closure:** Classifier buckets and **562** count match link audit; `network_coop_note_*` live refs align with m0 §6 caveat.
- **m1_pad_multitap:** Real XInput path via **`SKIP`**; thread/`XInitDevices` stubs remain in **R4**/**R3** tiers here.

### Conflicts

- **C3:** M1 must replace cache/file **R4** cluster before M2 tag bytes matter at runtime — corroborated with **m1_startup** and **m2_loader**; not a disagreement on ordering.
- **C4:** Render **R4** data (`render` global) vs sim-only M1 boot — implement minimal timer/frame_index adapter or accept deferred HUD until M3 snapshot.

### Updated handoff

1. **Appendix A** is the ticket backlog; prioritize **13** cache symbols + Win32 **R4** I/O on `game.c:812-905` path.
2. Regenerate audit JSON after each stub owner change; re-run **m0_link** SHA pin.
3. Gate **15** `network_coop_note_*` with `network_coop_active()==FALSE` proof before M3 state hash.
