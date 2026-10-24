# C2.3 cut campaign (lane cut-campaign, round 9), 2026-10-24

Status: **no code cut applied; C2.3 campaign cuts not met.** Each candidate was checked against the
C1 actor roster and the r7 attribution; none had evidence that the multiplayer profiles (bots,
survival, ui) never reach it. Nothing in `submodules/halo-ce-universal` was changed by this lane.

## Inputs read
- `docs/reports/m2-c2-r7-elf-attrib-2026-10-24.md` (candidate classes a1, a2, a3; elf_static excess 959,352 B).
- `docs/reports/m2-c1-actor-roster-2026-10-23.json` (hcu-actor-roster-v1, 336 variants, 75 recipes).
- `docs/reports/m2-c2-status-2026-10-23.json` and the C2 section of `plans/7.hcu-remake-m2-m4.md`.

## Candidate decisions
| Class | Item | Decision | Evidence |
|---|---|---|---|
| a3 | `actor_type_{flood,infection,carrier,hunter,engineer,crew,sentinel}.c` | refused (not cut) | roster variants use actor types 3, 4, 8, 9, 10, 11, 12, 13 on campaign maps (flood 84 combat variants on c10, c20, c40, d20, d40). The roster has no multiplayer survival or bot maps, so it cannot clear these types for those profiles. Survival needs AI actors and encounters. |
| a3 | `cutscene/*`, `camera/camera_scripting.c` | not cut in this lane | `camera_scripting.c` is under `source/camera/`, outside this lane's ownership (cross-lane). The `cutscene/` callers are `hs.c` and `game.c`, outside ownership. A stub would change scripts, and no evidence shows multiplayer maps never call `recording_play` or `cinematic_*`. |
| a2 | Xbox platform files (`sound_dsound_xbox.c`, `input_xbox.c`, `shell_xbox.c`, ...) | not cut | Attribution says the credible figure (36,021 B own) needs PS2 replacement modules first. Those replacements are not present in this lane's scope. Their callers reach the menu path. |
| a1 | editor/debug | out of lane | `ai_debug.c` is excluded by the task. The rest is in other owners' paths. |

## Verification
- `python3 -I tests/test_hcu_c2_cut_campaign.py`: 2 tests, OK. It asserts that the roster reaches every a3 actor type, so an actor cut is refused by evidence.
- No build, closure, probe link or audit was run, since no source changed. Closure `failed_count` 0 and probe link `undefined=0` are unchanged from the orchestrator's last run.
- `git diff --check` run on the main repo for the new test and this report.

## Gap
The elf_static excess of 959,352 B is not addressed by this lane. The r7 attributable conservative total is 107,241 B and the upper bound 357,770 B, both on the sample link. No cut here is justified by evidence, so the gap is unchanged.

## Needed before a cut is possible
1. A roster or workload trace that includes the multiplayer survival and bot maps (`survival-bloodgulch`, bots profiles), so actor types can be checked against them.
2. Script-usage evidence for `recording_*`, `cinematic_*` and `camera_set_*` on multiplayer maps (the `tag-inventory.md` covers only campaign maps' built-ins).
3. The PS2 replacement modules for the Xbox platform files, and the owner of `source/camera/` for `camera_scripting.c`.
