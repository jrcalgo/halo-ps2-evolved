# m1_startup_guest_path_auditor

**Supersession (2026-10-21):** the boot boundary this audit was waiting on is closed. Host ELF `e3577ca6…` reaches `game-initialize-done` and `m1-ui-map-request`. M1 is complete in `plans/5.hcu-remake.md`. The ordered blockers below are the prediction from this audit, not the current exit.

## Mission

Trace the HCU PlayStation 2 **guest** path from EE entry through CE shell startup, `main_loop`, `game_initialize`, and the **first map-load chain** (default local-game flow). Relate the path to the parent `halo-ps2` machine (separate ELF). Name the **last retained PCSX2 boot blocker** documented in `plans/remake-cowork.md`, and—using the **current** tree and link map—predict the **next** blockers after the `custom_maps` / `CreateDirectoryA` mitigation. Report-only; no implementation claims.

## Inputs examined

| Area | Path |
|------|------|
| Prompt contract | `docs/investigations/_prompt_contract.md` |
| Remake handoff / last boot | `plans/remake-cowork.md`, `plans/5.hcu-remake.md` |
| Closure / placeholders | `docs/hcu-ps2-closure.md`, `docs/hcu-ps2-platform-placeholder-audit.md` |
| Tag / loader contract | `docs/hcu-tag-loader-contract.md` |
| Boot probe | `tools/test_hcu_boot.py` (success marker: `HALO_PS2_LOCAL game-initialize-done`) |
| PS2 manifest | `submodules/halo-ce-universal/port/ps2/port.json` |
| Machine entry / memory | `port/ps2/src/ps2_main.c`, `port/ps2/src/ps2_memory.c`, `port/ps2/src/ps2_abi.c`, `port/ps2/src/ps2_crt.c` |
| Platform bridges | `port/ps2/src/ps2_edge.c` (linked via `tools/hcu_ps2_link.py`) |
| CE shell | `source/shell/shell_xbox.c`, `source/shell/shell.c` |
| Main loop / menu | `source/main/main.c` |
| Game init / load | `source/game/game.c`, `source/scenario/scenario.c`, `source/cache/cache_files.c` |
| Files / saves | `source/tag_files/files.c`, `source/tag_files/files_windows.c`, `source/saved games/saved_game_files.c`, `source/saved games/game_state_xbox.c`, `source/saved games/game_state.c` |
| Generated platform | `build/hcu-ps2-closure/all/ps2_platform.c`, `build/hcu-ps2-closure/all/halo-local.map` (symbol ownership spot-check) |
| Parent reference (not linked into `halo-local.elf`) | `submodules/halo-ps2/engine/src/main.c` |
| N64 integration pattern | `submodules/halo-64/port/n64/src/n64_main.c` (`halo_shell_main` after machine setup) |

Evidence baseline (Round 1): parent `a2575e957feefbdff27febedabf60590401e6bcc`, HCU `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`, `halo-local.elf` SHA-256 `e45b4719d35450a77f2a541a7ed8abb877e5fbef495fc918539f8da91de597a2` when present.

## Findings

### Executive summary

| Question | Answer |
|----------|--------|
| What is the guest entry? | `port/ps2/src/ps2_main.c` `main` → `halo_shell_main` (`shell_xbox.c` compiled with `-Dmain=halo_shell_main`). |
| Where does CE “start playing”? | `shell_initialize` then `main_loop`; simulation time stays frozen until menu/map paths clear `halt_time_scale` via game time APIs. |
| What is the **first map load** on default local boot? | **`levels\ui\ui`** (main-menu UI scenario) via `main_menu_load` → `main_load_ui_scenario` → `main_new_map` → `game_load` → `scenario_load` → `scenario_tags_load`. Campaign default **name** `levels\b30\b30` is set early but not loaded until solo/menu flags say so. |
| Last **guest-verified** stop | Retained log reached `game-initialize` then halted; `error_get()` text cited `file_create('custom_maps') error 0x00000002` (`plans/remake-cowork.md:46-52`). **`game-initialize-done` has not been seen** on a post-mitigation image. |
| **Next boot blocker** (current tree, ordered) | **(A)** Complete `game_initialize`—most likely **`create_mutex` stub** in `saved_game_files_initialize` (`match_vassert` → `system_exit` → `halt_and_catch_fire`), not a second `custom_maps` create if `ps2_edge.c` is linked. **(B)** After `game-initialize-done`, **`game_precache_new_map(..., TRUE)`** for `levels\ui\ui` fails on generated **`cache_files_precache_map_begin` / `cache_files_precache_in_progress`** (`game.c:834-862`). **(C)** If precache were faked to succeed, **`cache_file_open` stub** makes `scenario_tags_load` return `NONE` (`ps2_platform.c`). **(D)** M2: real tag bytes + 2 MiB cap vs retail sizes (`docs/reports/tag-index.md`). |

### 1. Two machines in one repo (guest vs parent)

- **`build/hcu-ps2-closure/all/halo-local.elf`** — HCU local-game closure: CE shell + generated platform + `ps2_edge.c` / `ps2_memory.c` / `ps2_input.c` / `ps2_coop.c`. **This report traces only this image.**
- **`submodules/halo-ps2/engine/halo-ps2.elf`** — Parent phase-1 world renderer: `malloc` boot arena, `world_load` on `.hp2` packs, `pad_poll` flycam (`engine/src/main.c:126-159`). **No `halo_shell_main`, no CE `main_loop`.**
- **Hybrid fixture** `src/platform/main.c` (repo root) uses parent `pad_init` / `pad_poll` only; it is **not** the HCU guest entry.

Integration intent (plan): N64 calls `halo_shell_main` after machine services (`n64_main.c:449-451`); PS2 is supposed to mirror that split (`plans/5.hcu-remake.md:144`), but **`ps2_main.c` does not call parent `engine/src/main.c`**—only CE shell after `physical_memory_allocate`.

### 2. EE entry → `halo_shell_main`

**PS2SDK** brings up the EE and calls the linked `main` after `StartTimerSystemTime()` (PS2SDK startup contract cited in `docs/hcu-ps2-closure.md:60`).

**`ps2_main.c:14-20`**

1. `printf("HALO_PS2_LOCAL entered")`
2. `ps2_abi_check()` — compile-time layout checks only (`ps2_abi.c:63-65`)
3. `physical_memory_allocate()` — assigns pointers to static `game_state`, `tag_cache`, `texture_cache`, `sound_cache` (`ps2_memory.c:33-38`)
4. `return halo_shell_main()`

**`shell_xbox.c:105-135` (`halo_shell_main`)**

1. Marks: `shell`, `modules`, `rasterizer-pre`
2. `fuck_code_in_the_eye()` — Xbox module walk; on PS2 `DmWalkLoadedModules` / `DmWalkModuleSections` return `XBDM_ENDOFLIST` immediately (`ps2_edge.c:27-39`) so no spin
3. `rasterizer_preinitialize__fill_you_up_with_the_devils_cock()`
4. **`physical_memory_allocate()` again** — idempotent reassignment (`shell_xbox.c:114`, `ps2_memory.c:33-38`)
5. `shell_initialize()` → on success `main_loop()` → `shell_dispose()`
6. `__except` → `halt_and_catch_fire()` (`shell_xbox.c:130-132`; `__try`/`__except` are no-ops on PS2 via `halo_ps2_prefix.h:59-61`)

### 3. `shell_initialize` (pre–`main_loop`)

`shell.c:26-73` in order:

| # | Call | Log mark | PS2 notes |
|---|------|----------|-----------|
| 1 | `cseries_initialize()` | `cseries` | Profiling off; debug memory uses bump arena later |
| 2 | `shell_platform_initialize()` | `platform %d` | `XGetLaunchInfo` returns failure (`ps2_edge.c:49-54`) — no `XDEMOS` cmdline |
| 3 | `errors_initialize()` | `errors` | |
| 4 | `tag_files_open()` → `cache_files_initialize()` | `tags` | **`cache_files_windows.c` is excluded** from PS2 manifest (`port.json:38`); `cache_files_initialize` is a **generated no-op** (`ps2_platform.c:139`) |
| 5 | `directory_create("custom_maps")` | `directory` | See §3.1 |
| 6 | `real_math_initialize()` | `math` | |
| 7 | `game_state_initialize()` | `game-state` … `game-state-done` | See §3.2 |
| 8 | `rasterizer_initialize()` | `rasterizer %d` | PS2 returns `TRUE` without D3D (`ps2_edge.c:58-61`) |
| 9 | `input_initialize()` | `input` | XInput adapter present; **no pad publish** (`m1_pad_multitap_auditor.md`) |
| 10 | `sound_initialize()` | `sound` | `DirectSoundCreate` fails (`ps2_edge.c:65-72`) |
| 11 | — | `shell-ready` | |
| 12 | `shell_platform_verify()` | (none) | `physical_memory_verify()` empty on PS2 |

#### 3.1 `custom_maps` at shell time

`directory_create` (`files.c:296-310`): if `!file_exists`, calls `file_create` on a directory reference.

Directory `file_create` (`files_windows.c:398-402`): `CreateDirectoryA(info->path, NULL)`; on failure logs `error(_error_silent, "file_create('%s') error 0x%08x", …)` (`files_windows.c:408-409`) and returns `FALSE` **without aborting**.

On PS2, `file_exists` uses `GetFileAttributesA` → always “missing” with `GetLastError` 2 (`ps2_edge.c:100-105`). **`CreateDirectoryA` succeeds only for the exact path `"custom_maps"`** (`ps2_edge.c:88-97`); other paths return 0 and set `ps2_last_error = 3`.

**Historical boot:** shell mark `directory` appears **before** `game-initialize` in the retained log (`remake-cowork.md:44-45`), so shell likely continued even when `custom_maps` create failed at that revision; the halt message can be a **stale** `error_globals.message_buffer` entry unless a later `error()` overwrote it (see §6).

#### 3.2 `game_state_initialize` in shell (not `game_initialize`)

`game_state.c:1043-1053`:

- `game_state_allocate_buffer(HALO_PORT_GAME_STATE_BASE_ADDRESS, …)` — PS2 uses `physical_memory_get_game_state_base_address()` instead of Xbox VA (`game_state_xbox.c:191-214`)
- `game_state_create_or_open_file()` — PS2 **does not halt** when `z:\savegame.bin` cannot be opened (`game_state_xbox.c:257-267`)

### 4. `main_loop` setup (before the `while (TRUE)` body)

`main.c:3382-3408`:

| Step | Effect |
|------|--------|
| Default solo map name | `levels\b30\b30` if not editor (`3390-3393`) |
| `want_to_be_at_main_menu = TRUE` | Menu-first local boot (`3396`) |
| `halt_time_scale = TRUE` | Game time frozen until map/menu path runs (`3398`) |
| `console_initialize`, `debug_keys_initialize` | |
| **`game_initialize()`** | See §5; marks `game-initialize` / `game-initialize-done` (`3403-3405`) |
| `console_startup()` | |
| **`main_setup_connection()`** | If `want_to_be_at_main_menu`, **`main_menu_load()`** and **return** (`2810-2813`) — first menu/map work runs **here**, not only inside the loop |
| `main_initialize_time()` | Vblank callback, flip counters (`2841-2849`) |

**Loop body** (`3414+`): each frame runs deferred map flags, then `input_frame_begin`, network hooks, `game_tick` when active, present/throttle, etc. After `main_setup_connection`, `want_to_be_at_main_menu` is cleared by `main_menu_load` (`1139`), so the loop’s `main_menu_load` guard (`3482-3485`) is for **re-entry**, not the first menu load.

**Skip-menu path:** if `want_to_be_at_main_menu` were false before `main_setup_connection`, code loads `soloplayer_map_name` with blocking precache + `main_new_map` (`2824-2835`).

### 5. `game_initialize` — full subsystem order and failure pressure

`game.c:278-328` (abbreviated labels; order is exact in source):

1. `game_state_malloc` → `game_globals`; memset; `game_time_initialize`
2. `game_engine_initialize`, allegiance, **`interface_initialize`**, **`scenario_initialize`**, director, observer
3. **`render_initialize`**, objects, structures, breakables, decals, collision log
4. players, contrails, particles, effects, weather, particle systems
5. sound classes, game sound, rumble, player effects
6. **`ai_initialize`**, editor, **`ui_widgets_initialize`**, **`hs_initialize`**, recorded anims, cheats, transport
7. telnet, network packets, cinematic, **`saved_game_files_initialize`**
8. event manager, input abstraction, player UI, bink, **`progress_bar_initialize`**

**Excluded CE sources** (`port.json:47-48`): full `ui_widget.c`, `progress_bar.c`. Those entry points are **generated no-ops** in `ps2_platform.c` (`ui_widgets_initialize`, `progress_bar_initialize`).

#### 5.1 `saved_game_files_initialize` — primary `game_initialize` halt candidate (current tree)

`saved_game_files.c:506-562`:

1. Seven `find_and_create_directory_if_necessary("z:\\saved\\…")` calls (`509-541`). Each uses `file_create` when missing (`2014-2026`). **`CreateDirectoryA` only special-cases `custom_maps`**, not `z:\saved\…` → create fails; function logs `error(_error_silent, "failed to find/create …")` and sets `success = FALSE` but **does not assert** on that alone.
2. **`create_mutex` ×2** (`549-551`). Generated stub: **`create_mutex` returns FALSE** (`ps2_platform.c:188`).
3. **`match_vassert(..., saved_game_files_globals.initialized, "failed to initialize saved game files")`** (`553-557`) → `display_assert` + **`system_exit(-1)`** → **`halt_and_catch_fire`** (`cseries.h:126`, `cseries_windows.c:110-123`, `main.c:3115`).

If mutex creation were fixed, **`player_profiles_initialize`** → `player_profile_create_default_profiles_on_disk` still calls **`file_create` + `file_open` + writes** under `z:\saved\player_profiles\default_profile\` (`player_profile.c:524-532`, `847-872`) — all depend on Win32 file stubs (`CreateFileA` returns NULL in `ps2_platform.c:16`).

**Ordering note:** `saved_game_files_initialize` runs **late** in `game_initialize` (after AI/HS). A halt **inside** `game_initialize` on the historical run is **consistent** with mutex failure **or** an earlier `match_vassert`/`match_assert` in a prior initializer; the log text naming `custom_maps` is **not sufficient** to pin the callsite without a stack trace from that ELF build.

### 6. Retained guest boot evidence (`remake-cowork.md`)

**Observed marks (order):** `entered`, `memory`, `shell`, `modules`, `rasterizer-pre`, `shell-init`, `cseries`, `platform 1`, `errors`, `tags`, `directory`, `math`, `game-state`, `game-state-done`, `rasterizer 1`, `input`, `sound`, `shell-ready`, `main-loop`, **`game-initialize`**.

**~17 ms later:**

```text
HALO_PS2_LOCAL halt 0x1ab76c file_create('custom_maps') error 0x00000002
```

- Return address `0x1ab76c` resolved to **`error`** (`remake-cowork.md:50`) — consistent with **`halt_and_catch_fire` printing `error_get()`** (`main.c:3115`), not proof the halt was inside `file_create`.
- **`0x2`** matches `ERROR_FILE_NOT_FOUND` / failed directory create when `CreateDirectoryA` was a generated zero return (`remake-cowork.md:50-52`).
- **`camera->z_far>camera->z_near`** during halt draw is a **follow-on** assert (zero clip planes), not the primary stop (`remake-cowork.md:50`).

**Mitigation in tree (unverified on guest):** `CreateDirectoryA("custom_maps")` in `ps2_edge.c:88-97`; link tool lists `ps2_edge.c` explicitly (`tools/hcu_ps2_link.py:258`). **`game-initialize-done` not logged** after rebuild; environment blocked PCSX2 re-run (`remake-cowork.md:91-93`, `docs/hcu-ps2-closure.md:136`).

**Boot test contract:** `tools/test_hcu_boot.py:63-65` passes on substring **`HALO_PS2_LOCAL game-initialize-done`** (not map load).

### 7. First map-load chain (after `game_initialize`)

#### 7.1 Menu path (default)

```
main_setup_connection (main.c:2810-2813)
  → main_menu_load (1124-1141)
       → main_load_ui_scenario(FALSE) (1896-1921)
            → game_precache_new_map("levels\\ui\\ui", TRUE)  [1901, 1907]
            → game_dispose_from_old_map / game_unload / game_engine_dispose
            → main_new_map(&options)  [map_name levels\\ui\\ui]
```

#### 7.2 `game_precache_new_map` (blocking) — halt before any `scenario_load`

`game.c:812-862` when `blocking == TRUE` and map not already “loaded”:

1. `cache_files_precache_map_loaded` → **FALSE** (stub)
2. `cache_files_precache_map_begin` → **FALSE** (stub, `ps2_platform.c:142`)
3. **`match_vassert(..., FALSE, "read the last error message for which map failed to load")`** (`843-847`) → halt
4. If that were bypassed, **`match_assert(cache_files_precache_in_progress() && cache_files_precache_is_copying_map(map_name))`** (`858-862`) — both stubs false → **`match_assert` → halt**

So the **first intentional map name** (`levels\ui\ui`) hits **precache API stubs** before `main_new_map` → `game_load`.

#### 7.3 `main_new_map` → `scenario_load` → `scenario_tags_load`

`main.c:1465-1486`:

- `game_load` → `scenario_load` (`game.c:633-636`, `scenario.c:1203`)
- On failure: `error(_error_immediate, "game_load() failed.")` then `errors_handle()` (`1475-1485`)

**`scenario_tags_load`** (`cache_files.c:1189-1259`):

- Opens texture/sound staging (`texture_cache_open`, `sound_cache_open`)
- CE maps: `custom_edition_level_name` — **stub always FALSE** (`ps2_platform.c:196`)
- Retail/UI path: **`cache_file_open(stripped_scenario_name, &header)`** — stub **always FALSE** (`ps2_platform.c:136`)
- Therefore **`global_scenario_index == NONE`**, `game_load` fails unless errors are handled without halt

**Important:** Xbox implementation in `cache_files_windows.c` is **not linked** on PS2 (`port.json:38-39`); manifest marks replacement **`planned`** (`port.json:77-81`). All cache lifecycle symbols in the live ELF are **generated** (`docs/hcu-ps2-platform-placeholder-audit.md:13`).

#### 7.4 Campaign map name vs first load

- `main_globals.soloplayer_map_name = "levels\\b30\\b30"` (`3392`) is the **default solo** label.
- **`main_load_ui_scenario` sets `load_last_solo_level = TRUE`** (`1917`), so later loop iterations can drive solo progression (`3487-3490`) **after** UI scenario load succeeds.
- First **bytes** on disk for a scenario still flow through the same **`scenario_tags_load` / `cache_file_open`** pipeline for whatever name is passed.

### 8. Map-load requirements table (post–`game_initialize`)

| Requirement | CE owner | PS2 `halo-local.elf` status |
|-------------|----------|-------------------------------|
| Tag cache base | `physical_memory_get_tag_cache_base_address()` | 2 MiB static (`ps2_memory.c:16-22`, `halo_ps2_limits.h:24`) — **below retail tag-structure sizes** (`docs/reports/tag-index.md`; M2) |
| Cache init | `cache_files_initialize` | Generated no-op |
| Precache | `cache_files_precache_map_*` | Generated false / no-op — **blocks `game_precache_new_map` asserts** |
| Map open/read | `cache_file_open`, `cache_file_read`, Win32 `CreateFileA`/`ReadFile` | **Stubs**; retail `cache_files_windows.c` **excluded** |
| Header/tags | `cache_file_header_verify`, tag validation | No bytes → no load (`hcu-tag-loader-contract.md`) |
| BSP | `scenario_switch_structure_bsp(0)` | Depends on loaded scenario |
| `custom_maps` dir | `shell.c:49` | Virtual success for name only (`ps2_edge.c:88-97`) |
| Save tree + profiles | `saved_game_files_initialize`, `player_profile` disk create | **`z:\saved` not virtualized**; mutex stub → **halt in `game_initialize`** |
| Menu UI widgets | `ui_widget_*`, progress during precache | Excluded sources → stubs; menu behavior **unverified** |
| Input | `input_frame_begin` in loop | No hardware bridge until pad publish (`m1_pad_multitap_auditor.md`) |

### 9. Boot log token map

| Token | Source |
|-------|--------|
| `entered` / `memory` | `ps2_main.c:16-19` |
| `shell` … `main-loop` | `shell_xbox.c:109-121` |
| `cseries` … `shell-ready` | `shell.c:34-65` |
| `game-initialize` / `game-initialize-done` | `main.c:3403-3405` |
| `assert` | `cseries.c:435-436` (`display_assert` on PS2) |
| `halt` | `main.c:3115` |

### 10. Ascii lifecycle (guest)

```
[PS2SDK crt0]
    → ps2_main: abi_check, physical_memory_allocate
    → halo_shell_main: shell_initialize (tags, custom_maps, game_state, …)
    → main_loop:
         game_initialize  ──► (saved_game_files / mutex) ──► game-initialize-done [M1 probe]
         main_setup_connection
              → main_menu_load
                   → main_load_ui_scenario
                        → game_precache_new_map(levels\ui\ui)  ──► precache stubs [blocker]
                        → main_new_map
                             → game_load → scenario_tags_load → cache_file_open [blocker]
```

Parent `halo-ps2.elf` for contrast: `malloc` arena → `world_load(.hp2)` — **no** box above.

## Interface contracts for the main agent

1. **Single guest image:** Lifecycle ordering is CE-owned from `shell_initialize` through `game_tick`; machine code supplies memory bases, `ps2_edge` bridges, and (later) per-tick pad publish before `input_frame_begin` (`plans/5.hcu-remake.md:144`, `m1_pad_multitap_auditor.md`).
2. **M1 filesystem minimum:** `CreateDirectoryA("custom_maps")` must succeed for shell `directory_create`; `GetFileAttributesA`/`GetLastError` must preserve fail-closed `file_exists` (`ps2_edge.c:81-115`, `files.c:307-308`).
3. **`game_initialize` save contract:** Either implement **`create_mutex`** (and policy for `z:\saved\…` + profile file I/O) or prove saved-game disk paths unreachable for local-game boot; **`match_vassert` on mutex is a hard halt** (`saved_game_files.c:553-557`).
4. **Precache contract:** Blocking `game_precache_new_map` requires **`cache_files_precache_map_begin` returning TRUE** and **`cache_files_precache_in_progress()` true** before the wait loop (`game.c:834-862`) — success-shaped all-false stubs are invalid.
5. **Map-load contract:** `scenario_tags_load` needs a **real `cache_file_open` + read** path or a coordinated M2 adapter; stub `cache_file_open` cannot satisfy first map load (`hcu-tag-loader-contract.md`, `port.json:77-81`).
6. **Verification:** Pass `tools/test_hcu_boot.py` (`game-initialize-done`), then extend probes for first `game_precache` / `scenario_load` outcome with hashed ELF + emulator logs retained.

## Recommended tests / fixtures

1. **M1 boot:** `tools/test_hcu_boot.py` on `build/hcu-ps2-closure/all/halo-local.elf` — assert `game-initialize-done`; capture full EE log on failure (halt line + prior `HALO_PS2_LOCAL assert` lines).
2. **Mutex gate:** Host or guest breakpoint on `saved_game_files_initialize` — confirm `create_mutex` return before `match_vassert`.
3. **Precache gate:** With `game-initialize-done` reached, expect halt or assert at `game.c:843-847` or `858-862` for `levels\ui\ui` until precache stubs are replaced.
4. **`scenario_tags_load`:** Instrument or log `cache_file_open` return for stripped name `ui` (path strip behavior via `tag_name_strip_path`) — expect FALSE with current `ps2_platform.c`.
5. **Negative FS:** `directory_create("custom_maps")` with `CreateDirectoryA` failure vs `ps2_edge` success — only the former should emit `file_create('custom_maps')` silent error.
6. **M2 sizing (report-only):** Compare `HALO_PORT_TAG_CACHE_SIZE` to `docs/reports/tag-index.md` campaign minima — documents loader capacity gate, does not close M2.

## Dependencies on other investigators

| Investigator | Dependency |
|--------------|------------|
| `m1_platform_callsite_auditor` | Full map of generated `CreateFileA` / `ReadFile` / cache symbols on startup vs map paths |
| `m2_loader_failure_auditor` | Fail-closed behavior when `cache_file_open` / read fails |
| `m2_arena_capacity_auditor` | Tag region vs `HALO_PORT_TAG_CACHE_SIZE` and BSP overlap |
| `m0_runtime_ownership_auditor` | Replacing `ps2_memory.c` static arrays with parent arenas; glue entry |
| `m1_pad_multitap_auditor` | Tick boundary for `input_frame_begin` after boot reaches main loop |
| `m1_dma_layout_auditor` | EE layout vs contiguous `.bss` (not boot order, but same ELF) |

## Open questions

1. **Historical halt callsite:** Log ties halt to `error` and buffer text `custom_maps`; whether failure was shell `directory_create`, `saved_game_files` mutex, or another `match_vassert` is **unproven** without symbolized stack from that ELF build.
2. **Post-`ps2_edge` depth:** Whether `game-initialize-done`, `main_menu_load`, and precache asserts occur in order on current image is **unknown** (no successful PCSX2 run in continuation environment).
3. **`errors_handle` after failed `game_load`:** Whether `_error_immediate` from `main_new_map` always escalates to halt vs continuing main loop with no map — needs guest trace.
4. **Stubbed `ui_widgets_initialize`:** Impact on `main_load_ui_scenario` / `ui_widget_load_progress_widget` during blocking precache (`game.c:863-864`) is unverified.
5. **Parent integration:** When and how `halo-local.elf` will share address space or IPC with `halo-ps2` services for render/GS is **not decided** in-tree.

## Handoff summary

- **Guest trace:** `ps2_main` → `halo_shell_main` → `shell_initialize` (including **`custom_maps`** and **`game_state_initialize`**) → `main_loop` → **`game_initialize`** (ends with **`saved_game_files_initialize` / mutex**) → **`main_setup_connection` → `main_menu_load` → `main_load_ui_scenario`** → blocking **`game_precache_new_map("levels\\ui\\ui")`** → **`main_new_map` → `game_load` → `scenario_load` → `scenario_tags_load`** for the **first map load** attempt.
- **Last named blocker in retained guest evidence:** **`file_create('custom_maps')` / `CreateDirectoryA` failure (error `0x2`)** during startup directory ensure (`remake-cowork.md`); mitigated in source by **`ps2_edge.c`** but **not guest-confirmed**; halt may have used **stale** error buffer text.
- **Next blockers on current link closure (ordered):** **`create_mutex` in `saved_game_files_initialize`** (before `game-initialize-done`); then **`game_precache_new_map` asserts** for UI map; then **`cache_file_open` stub** (no `cache_files_windows.c`); then **M2 tag image + capacity**. That predicted open gate is closed by the host ELF named in the supersession above.

## Corroboration

### Agreements

- **m1_platform_callsite:** Ordered failure after menu matches **R4** cache precache cluster; **CreateDirectoryA** outside **562** but addressed in `ps2_edge.c` **`SKIP`**.
- **m2_loader_failure:** `scenario_tags_load` on first map is first CE loader gate — must fail closed without CTAG image.
- **m2_arena_capacity:** UI map may fit tighter caps; `b30` gameplay path proves retail sizing violation — boot can reach menu before M2 complete only with synthetic/ui assets.
- **m1_pad_multitap:** Input bridge not on startup path until `main_loop` tick — does not block `shell-ready` / `game_initialize`.

### Conflicts

- **C3:** Corroborated staging — M1 platform I/O before M2 bytes on guest critical path; M2 work parallel on host.

### Updated handoff

1. Re-verify guest boot with current ELF: confirm `custom_maps` / mutex / precache ordering vs `remake-cowork.md` log.
2. M1 gate marker: `game-initialize-done` printf or equivalent before claiming menu path.
3. First map load success is **M2**-gated; do not conflate with M1 shell boot.
