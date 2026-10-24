# M2 C2 r7, lane staging-verdicts (C2.5 decisions)

Date: 2026-10-24. Build outputs: `build/m2-c2-r7-staging-verdicts/`. Host and EE compile evidence only. Nothing here ran on PCSX2 or hardware. C2.5 exit is **not met**: 20 callsites remain open.

## Scope and rules

Owned files: `submodules/halo-ce-universal/source/hs/hs.c` (changed), `source/tag_files/files.c` (read, not changed), `source/saved games/game_state.c` and `game_state_xbox.c` (read, not changed), `tools/audit_hcu_postload_allocations.py` (changed), `docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json` (regenerated). `hs_compile.c` is outside this lane and was not edited.

## Decisions

The PS2 build is the manifest `submodules/halo-ce-universal/port/ps2/port.json`. It excludes `source/networking/` (telnet console) and `source/rasterizer/`. It defines `HALO_PS2`.

### 1. Checkpoint revert: `game_state_read_from_file` (malloc/free of one GAME_STATE_SIZE image)

Verdict: **recurrent-open** (campaign-reachable). Not moved.

- The read copies the saved image into a malloc block, validates it with `game_state_image_accept`, and that function copies it into the fixed game-state base (`game_state.c:921`). The malloc block is freed before return, so the growth is not cumulative, but each revert takes one GAME_STATE_SIZE block.
- Callers of `game_state_revert` (`game_state.c:391`):
  - `main.c:2070` and `:2090` (`main_revert_map_private`), reached from `main_revert_map` (`main.c:984`). Its callers: the solo pause menu's restart at checkpoint (`ui_widget_event_handler_functions.c:1991`), and the script built-in `game_revert` (`hs.c` `main_revert_map_evaluate`). `game_revert` appears in the campaign inventory (`tag-inventory.md`, a10: 2 nodes).
  - `main.c:2113` (`main_skip_cinematic`, via `player_control.c:1808`).
  - `main.c:2266` (lost-map respawn). `main_lost_map` is armed only when `!game_engine_running()` (`players.c:5136`), so a multiplayer game (game engine running) never arms it.
  - `game_state.c:421` (save and quit, `player_spawn_count==1`).
- Multiplayer: the solo pause menu is `ui\shell\solo_game\pause_game` (`ui_widget.c:597`), not the multiplayer pause. So for the multiplayer profiles the checkpoint revert is reachable only through cinematic skip and save-and-quit, whose reachability in the multiplayer maps' scripts is **not traced** (the tag inventory covers campaign and `ui` only).
- So the revert is a campaign feature. Staging it in a fixed owner is a memory-budget decision (C2.1/C2.3), so no allocation was moved.

### 2. Checkpoint revert read, the `game_state_read_core` malloc/free (core files)

Verdict: **unreachable-selected-build**.

- `game_state_read_core` (`game_state_xbox.c:421`) is reached only through `game_state_load_core` (`game_state.c:1086`) and `main_load_core_private` (`main.c:2287`). The `load_core` flag is set only by `main_load_core`, `_at_startup`, `_name` and `_name_at_startup` (`main.c:1042-1072`).
- Their only callers are the `core_load*` script built-ins (`hs.c`, `main_load_core_*_evaluate`). The core files live on the `d:` drive, which PS2 does not have.
- Change (hs.c): those four evaluators are now explicit functions. On `HALO_PS2` they refuse the load and count it in `hs_port_core_load_refusals`. The non-PS2 path is unchanged.

### 3. Script source reload: `file_read_into_memory` (files.c, match_malloc/match_free)

Verdict: **unreachable-selected-build** (after the change below).

- The chain is `file_read_into_memory` <- `hs_rebuild_source_file` <- `hs_rebuild_source`. `hs_rebuild_source` runs only when `hs_recompile_pending` is set, or from `hs_hack`.
- The setters are `hs_recompile_evaluate` (the `script_recompile` built-in), `hs_recompile()` and `hs_hack`. `hs_recompile()` and `hs_hack` have no callers in `source/` or `port/ps2`.
- `script_recompile` is in the campaign inventory (a30, c20, d40: one node each), so it was reachable.
- Change (hs.c): `hs_recompile_evaluate` on `HALO_PS2` refuses the recompile and increments `hs_port_recompile_refusals` instead of setting the pending flag. Behaviour change: on PS2 a `script_recompile` call in a30, c20 or d40 does nothing (it is a development hook). The scripts already compiled stay.
- The datastore reads and writes in `files.c` keep their earlier `unreachable-selected-build` rows.

### 4. Console command compile: `hs_compile_add_source` over 0x400 bytes (heap fallback)

Verdict: **unreachable-selected-build**. No code change was needed in `hs_compile.c`, which is outside this lane.

- Callers of `hs_compile_and_evaluate` (`hs.c`): `console.c:239` (`console_process_command`), `console.c:425` (`console_startup`), `cheats.c:225` and `telnet_console.c:397`.
- `console_process_command` is reached only from `console_update`. The console opens on the backquote key (`input_key_is_down`). Key state is written only from keystrokes read on `keyboard_handle` (`input_xbox.c`, around lines 1040-1131). PS2 never opens that handle: `ps2_input.c` `valid_device_type` accepts only `XDEVICE_TYPE_GAMEPAD`, so `XInputOpen` for the debug keyboard fails.
- `console_startup` reads its init lines into `char buffer[200]`, below the 0x400 scratch limit (r6 change), so it never reaches the heap.
- `cheats.c` calls are compiled out on PS2 (`CHEATS_DEBUG_STUB`, with `cheats_update`'s body under `#ifndef CHEATS_DEBUG_STUB`).
- `telnet_console.c` is excluded from the PS2 build (`port.json` `exclude_dirs` contains `source/networking/`).
- Scenario compiles (`hs_compile_initialize(TRUE)`) are load-only.
- Therefore no command longer than 0x400 bytes reaches the heap in the selected build.

## Tool change: counter-backed closure

`tools/audit_hcu_postload_allocations.py`:

- `bounded-after-binding` and `bounded-in-pool` close a site only when its basis cites a counter (`COUNTER_BASIS`: `counter`, `sdk_*`, `refused_*`, `used_after_drain`, `*_fallbacks`, `*_failures`, `*_counter`). Other bounded bases stay open.
- `load-only` and `unreachable-selected-build` close.
- Every other verdict is open.
- The tool prints the totals, the count of bounded sites closed by a counter, the open count per verdict, and each open site (`path:line function api [verdict]`). The same is written into the inventory JSON (`scope.open_sites`).
- Built-in rows for the four sites above were rewritten with the caller chains.

## Totals (regenerated inventory)

Output of `python3 -I tools/audit_hcu_postload_allocations.py --output docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json`:

```
verdict totals (callsites with a phase other than load-or-init):
  bounded-after-binding: 3
  bounded-in-pool: 4
  cross-lane-open: 8
  load-only: 8
  recurrent-open: 2
  unknown-open: 7
  unreachable-selected-build: 27
  unverified-open: 1
bounded verdicts closed by a counter-backed basis: 5
open callsites remaining: 20
  bounded-in-pool: 2
  cross-lane-open: 8
  recurrent-open: 2
  unknown-open: 7
  unverified-open: 1
```

Open callsites (20):

```
src/stream/hcu_main.c:657 main arena_alloc [cross-lane-open]
src/stream/hcu_main.c:660 main arena_alloc [cross-lane-open]
src/stream/hcu_main.c:751 main arena_alloc [cross-lane-open]
src/stream/hcu_main.c:752 main arena_alloc [cross-lane-open]
src/stream/hcu_main.c:754 main arena_alloc [cross-lane-open]
src/stream/hcu_main.c:756 main arena_alloc [cross-lane-open]
src/stream/hcu_main.c:758 main arena_alloc [cross-lane-open]
src/stream/hcu_map_service.c:195 feed_ctag_first_pass arena_alloc [cross-lane-open]
.../source/cseries/cseries_windows.c:176 system_calloc GlobalAlloc [unknown-open]
.../source/cseries/cseries_windows.c:182 system_malloc GlobalAlloc [unknown-open]
.../source/cseries/cseries_windows.c:209 system_realloc GlobalAlloc [unknown-open]
.../source/cseries/cseries_windows.c:214 system_realloc GlobalReAlloc [unknown-open]
.../source/memory/stack_memory_pool.c:1167 stack_memory_pool_resize_block stack_memory_pool_allocate [unknown-open]
.../source/memory/stack_memory_pool.c:1182 stack_memory_pool_resize_block stack_memory_pool_allocate [unknown-open]
.../source/objects/objects.c:810 object_header_delete memory_pool_block_free [bounded-in-pool]
.../source/objects/objects.c:835 object_header_block_allocate memory_pool_block_reallocate [bounded-in-pool]
.../source/objects/objects.c:4757 object_name_list_allocate game_state_malloc [unverified-open]
.../source/saved games/game_state_xbox.c:343 game_state_read_from_file malloc [recurrent-open]
.../source/saved games/game_state_xbox.c:362 game_state_read_from_file free [recurrent-open]
.../halo-ps2/engine/src/core/mem.c:65 arena_sub_aligned arena_alloc [unknown-open]
```

(`.../` is `submodules/halo-ce-universal/`.)

The objects.c rows are `bounded-in-pool` with a basis that does not cite a counter (`object_memory_pool` and FALSE on exhaustion). The `object_name_list_allocate` row is `unverified-open` from the other lane's verdict file.

## Verification

- EE compile of the touched object: `python3 -I build/m2-c2-r7-staging-verdicts/ee_compile.py source/hs/hs.c` (in the submodule; flags from `tools/hcu_ps2_link.py` and the manifest's include list), `rc=0`, output `build/m2-c2-r7-staging-verdicts/hs.o`. `nm` shows `hs_port_recompile_refusals` and `hs_port_core_load_refusals`, and the `hs_recompile_evaluate` body is the PS2 variant.
- `python3 -I -m py_compile tools/audit_hcu_postload_allocations.py`: compiled.
- `git diff --check`: clean for the submodule and for the root repository's touched files.
- Closure: the baseline `build/hcu-ps2-closure/all-no-bootstrap-memory/result.json` has `failed_count` 0. I did **not** rerun the full closure, because five lanes edit this worktree concurrently. The one changed object compiles, which is the touched-object gate.
- `python3 -I tests/test_hcu_c2_alloc_b.py`: 8 of 9 pass. The failure is `test_api_less_built_in_lookup_falls_back`, which expects `file_read_into_memory` to be `recurrent-open`. That expectation is the lane-B test's and is now stale: see the cross-lane change below.

## Not met (honest)

- **C2.5 is not met.** 20 callsites stay open: 8 cross-lane (`hcu_main.c`, `hcu_map_service.c`), 7 unknown (Windows cseries, `stack_memory_pool.c`, `mem.c`), 2 recurrent (checkpoint revert, campaign-reachable), 2 bounded-in-pool without a counter (objects.c), 1 unverified (`object_name_list_allocate`, other lane).
- **Checkpoint revert** is not moved: one GAME_STATE_SIZE block per revert. The fix (a fixed staging owner) is a memory-budget decision for C2.1/C2.3.
- **Counter not exported.** `hs_port_recompile_refusals` and `hs_port_core_load_refusals` are static counters. No accessor exists, and `hs.h` is not in this lane.
- **Multiplayer reachability of cinematic skip and save-and-quit** (paths into the checkpoint revert) is not traced for the multiplayer maps: their scripts are not in the inventory.
- No PCSX2 or hardware evidence.

## Cross-lane changes needed

- `tests/test_hcu_c2_alloc_b.py`: `test_api_less_built_in_lookup_falls_back` should expect `unreachable-selected-build` for `files.c` `file_read_into_memory`, which the hs.c refusal makes unreachable. Not edited here (not in this lane).
- `source/hs/hs_compile.c`: no change required for the verdict. Optional hardening (not done): fail closed on PS2 for commands over 0x400 bytes, which would make the heap path impossible even if a console reached it.
- `port/ps2/port.json` / the cseries rows: `cseries_windows.c` appears in the callsite set though it is Windows-only. Its rows are `unknown-open`. The owner of the source-set rule should confirm whether the file is selected.
