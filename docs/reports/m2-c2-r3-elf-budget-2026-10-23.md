# M2 C2 r3 elf-budget lane (C2.3): AI debug storage gate and ELF need (2026-10-23)

Lane: C2.3, elf-budget. Build outputs are in `build/m2-c2-r3-elf-budget/`. The committed budget is unchanged: committed 27,787,264 B, reserve 5,767,168 B, `elf_static` 2,097,152 B. No budget revision was made.

## Verdict

| Item | Result |
| --- | --- |
| (1) ai_debug storage behind a diagnostic define, CE still compiles for EE | **Pass** for the object-level check. The PS2 default keeps the line-of-sight buffers at one entry. `HCU_AI_DEBUG_DIAGNOSTICS` restores the original layout exactly (547,628 B). Both modes compile for EE with the closure's flags. |
| (2) decision for each large unowned static | **Decided**. All five stay in `elf_static` as CE state. Reasons are below. None is moved. |
| (3) fresh probe ELF and new `elf_static` need | **Not achieved**. The full relink is blocked by another lane's uncommitted `port/ps2/src/ps2_render.c` (exact error below). The new need is a projection from the measured object sizes, not a link. |
| (4) remaining overflow | Projected **814,696 B** (from 1,125,968 B on the same baseline ELF). Not closed. No revision implemented. |
| Tests | `tests/test_hcu_c2_budget_ai_debug.py`: 3 of 3 pass. `tests/test_hcu_c2_budget_partition.py`: 4 of 4 pass. |

C2.3 stays open.

## (1) ai_debug storage gate

Files changed:
- `submodules/halo-ce-universal/source/ai/ai_debug.h`. When `HALO_PS2` is defined and `HCU_AI_DEBUG_DIAGNOSTICS` is not, it defines `AI_DEBUG_LINEOFSIGHT_STUB`. In that mode `MAXIMUM_AI_DEBUG_LINEOFSIGHT_POINTS` and `MAXIMUM_AI_DEBUG_LINEOFSIGHT_PAIRS` are 1, instead of 16384 and 8192. The fixed-offset asserts after the line-of-sight arrays are inside `#ifndef AI_DEBUG_LINEOFSIGHT_STUB`. The asserts before them are unchanged, and the asserts in `action_uncover.c`, `actor_looking.c` and `ai_communication.c` are still in force.
- `tools/audit_hcu_c2_budget_elf_owners.py`: the `ai_debug` description now names the gate.
- `tests/test_hcu_c2_budget_ai_debug.py` (new): text checks of the gate and asserts, and a compile of `ai_debug.c` for both modes when the EE toolchain is present.

Why only the line-of-sight arrays are stubbed:
- They are bounds-checked against their constants, and overflow sets `lineofsight_overflowed` and logs once (`ai_debug_lineofsight_findpoint`, `ai_debug_lineofsight_storeray`).
- `actor_record[512]` is not stubbed. Its writes in `source/ai/actor_firing_position.c` are indexed by `firing_position->original_index`, and that index is not bounded by `ai_debug`. They are gated by `debug_evaluation`, which is reachable through `render_evaluations` and `render_pursuit`, so a one-entry array could overflow. That file is outside this lane.
- The 637 references to `ai_debug` across the CE tree are unchanged. Removing the struct from every user needs edits outside this lane.

Measured with the closure's flags (`hcu_ps2_closure.FLAGS`, the manifest include set, and the `halo_ps2_prefix.h` and msvc-semantics includes), mips64r5900el-ps2-elf-gcc 15.2.0:

| Mode | `ai_debug` symbol (`nm -S`) | Result |
| --- | ---: | --- |
| Production (PS2 default) | 236,356 B | compiles, rc 0 |
| `-DHCU_AI_DEBUG_DIAGNOSTICS` | 547,628 B | compiles, rc 0, equals the original layout |

Production saves 311,272 B. The objects are `build/m2-c2-r3-elf-budget/ai-debug/ai_debug-{production,diagnostic}.o`.

## (2) Unowned large statics: decisions

Each stays in `elf_static` as CE state. None is moved, because moving CE global storage after allocation is not allowed, and each move would need a cross-lane edit.

| Symbol | Bytes | Defined in | Decision |
| --- | ---: | --- | --- |
| `render` | 201,364 | `port/ps2/src/ps2_render.c` (PS2), `source/render/render.c` (CE) | stays. It is the CE renderer globals. Binding it to a named region needs the renderer owner (cross-lane, C2.6). |
| `update_client_globals` | 66,708 | `source/game/player_queues_new.c` | stays. Client netcode state with no region owner. |
| `game_engine_vehicle_homes` | 53,248 | `source/game/game_engine.c` | stays. Per-map gameplay state, so it belongs with `resident_gameplay` accounting, which is measured in C2.6. |
| `features` | 44,040 | `source/units/biped_limp_noodle.c` | stays. Collision feature list, static CE state. |
| `hs_nodes_to_walk` | 38,002 | `port/linux/game/tag_schema_scenario.c` | stays for now. It is map-load validator scratch, a candidate for the `streaming` owner. That needs a binding change in a port file outside this lane, and attribution alone does not change the total. |

## (3) Fresh probe ELF: not achieved

The probe was run through `tools/hcu_parent_link_probe.py` with `--step8-mp-capacity-diagnostic --step8-mp-workload-only --step8-mp-workload-players 2` (the profile name is `step8-mp-workload-2p-tagcache-4477120`). A wrapper at the scratchpad redirected the parent build root to `build/m2-c2-r3-elf-budget/`. The closure step still writes to the shared `build/hcu-ps2-closure/` path, which the probe hardcodes.

Attempt 1 failed in the closure with 5 failed units. Attempt 2 failed with 1 failed unit:

```
submodules/halo-ce-universal/port/ps2/src/ps2_render.c:19:10: fatal error: world/bsp.h: No such file or directory
```

`ps2_render.c` is modified and uncommitted in the shared worktree (`git status`). Its include `world/bsp.h` is not on the closure's include set at present. In attempt 1, `source/ai/actors.c`, `source/memory/data.c`, `source/objects/objects.c` and `source/saved games/game_state.c` failed on `uint32_t`. Those files are also modified by other lanes, and they passed by attempt 2. `ai_debug.c` compiled in both attempts.

The baseline owner audit on the existing probe ELF (`build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-2p-tagcache-4477120.elf`, JSON at `build/m2-c2-r3-elf-budget/baseline-owners.json`) reports:

| Item | Bytes |
| --- | ---: |
| code and constants | 2,050,568 |
| `.bss` | 2,115,732 |
| owned `.bss` (6 regions) | 943,180 |
| diagnostic in `elf_static` | 573,848 |
| unowned `.bss` | 1,172,552 |
| `elf_static` need | 3,223,120 |

This ELF gives 64 B less than the earlier `hcu-gameplay-machine-step8-mp-workload-tagcache-4477120.elf` figure (3,223,184) recorded by the r2 lane. The difference is in code and constants.

Projection, from the object measurement above and this baseline:

- `elf_static` need: 3,223,120 - 311,272 = **2,911,848 B**
- overflow: 2,911,848 - 2,097,152 = **814,696 B**

This is a projection, not a link. Re-run `tools/audit_hcu_c2_budget_elf_owners.py --elf` on the lane ELF once `ps2_render.c` builds.

## (4) Budget revision: not implemented

No candidate donor is proven safe. The r2 lane's candidates are not changed by this lane:
- `resident_gameplay`: the usage beyond the game-state reservation and claims is unmeasured (C2.6).
- `streaming`: 587,336 B slack is measured, which is less than the 814,696 B remaining overflow.

`config/memory-budget.json` is unchanged.

## Shared-worktree notes

- The closure runs wrote to `build/hcu-ps2-closure/all-no-bootstrap-memory-step8-mp-workload-2p/`, which is shared. The lane outputs are under `build/m2-c2-r3-elf-budget/`.
- `git diff --check` is clean for the touched tracked files (`ai_debug.h`, `audit_hcu_c2_budget_elf_owners.py`). The new test file has no trailing whitespace.

## Cross-lane changes needed

1. `port/ps2/src/ps2_render.c` (renderer lane): `world/bsp.h` is missing from the closure's include set. This blocks the fresh link.
2. `source/ai/actor_firing_position.c` (AI lane): bounds the `actor_record` writes. Only then can `actor_record[512]` (32,768 B) be stubbed too.
3. `port/linux/game/tag_schema_scenario.c` (streaming): `hs_nodes_to_walk` (38,002 B) could be bound into the streaming validator scratch, with the binding changed under the streaming owner.
4. C2.6 telemetry for `resident_gameplay` and `dynamic_simulation`, which the remaining 814,696 B overflow depends on.

## Commands run

- `python3 -I tools/audit_hcu_c2_budget_elf_owners.py --elf build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-workload-2p-tagcache-4477120.elf --json build/m2-c2-r3-elf-budget/baseline-owners.json`: elf_static need 3,223,120.
- `python3 -I /tmp/.../scratchpad/compile_ai_debug.py`: production rc 0 (236,356 B), diagnostic rc 0 (547,628 B).
- `HALO_BUILD_JOBS=8 python3 -I /tmp/.../scratchpad/lane_probe.py` (two attempts): closure failed, log `build/m2-c2-r3-elf-budget/relink.log` and `relink2.log`.
- `python3 -I tests/test_hcu_c2_budget_ai_debug.py` and `python3 -I -m pytest -q tests/test_hcu_c2_budget_ai_debug.py`: 3 passed.
- `python3 -I -m pytest -q tests/test_hcu_c2_budget_partition.py`: 4 passed.
