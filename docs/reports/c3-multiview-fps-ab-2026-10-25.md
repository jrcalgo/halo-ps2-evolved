# C3 multiview renderer FPS A/B — 2026-10-25

## Result

The combined C3 renderer changes approximately double or better the measured host render rate in the tested Blood Gulch workload, with exact captured RGB, canonical snapshot, and native bitmap queue parity at one through four views. Optimized runs had zero dropped ticks in the measured warm interval; baseline three- and four-view runs dropped 113 and 224 ticks. One view measured 29.968 FPS, nominal NTSC 30 at about 59.94 VPS. Split-screen remains below the 30 FPS objective; the unrounded rates and strict 30.00 threshold result are retained in the JSON.

| Views / players | Baseline FPS | Optimized FPS | Gain | Baseline game Hz | Optimized game Hz | Baseline → optimized drops |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 14.959 | 29.968 | +100.3% | 30.052 | 30.035 | 0 → 0 |
| 2 | 8.001 | 18.705 | +133.8% | 30.004 | 30.062 | 0 → 0 |
| 3 | 5.984 | 14.535 | +142.9% | 24.041 | 30.004 | 113 → 0 |
| 4 | 4.991 | 9.990 | +100.2% | 20.052 | 29.969 | 224 → 0 |

These are measurements for the fixed Blood Gulch / `bloodgulch_mounted_gunner_4p4bot` workload, not a general game-wide FPS claim. Scheduler game Hz and host render FPS are distinct measurements.

## Method and controls

Each configuration ran in its own fresh PCSX2 session, sequentially: baseline one through four views, then optimized one through four views. The runner held each owned PCSX2 window at 640×480 on the secondary monitor at `[3200, 647]`, with the window kept above other windows; the capture record confirms that geometry for all runs. The PCSX2 settings and neutral input/OSD state matched across runs. The sessions used the same Vulkan renderer (automatic renderer selection resolved to Vulkan), native resolution (`upscale_multiplier=1`), and recompiler mode. There was no autofire or keyboard input.

The workload kept the resident C3 HUD and 30 Hz scheduler common to both variants. Baseline compiled with `HCU_C3_OBJECT_FASTPATH=0`, `HCU_C3_OBJECT_VIEW_CACHE=0`, `HCU_C3_BINDING_SEAL=0`, and `HCU_C3_SNAPSHOT_INDEX=0`; optimized used `1` for all four. The 3-view source layout is one full-width top view and two quarter-width bottom views, with both lower regions active.

Warm rates use cumulative scheduler counter deltas at completed ticks 151 and 601, divided by the corresponding host-log timestamp interval. Sparse CPU-phase and publication means use the records available in that same interval; these are arithmetic means, not percentiles. Snapshot replay is prepared only after tick 601, the timed endpoint, so reference staging does not enter the measured interval.

## Timing details

View-build time, object/FX time, and binding-seal work show the principal measured differences. Sparse profiler record counts vary with render rate: the one-view baseline has 7 samples and its optimized counterpart has 15; the optimized four-view case has 5. The scorer retains counts per field. These are diagnostic means rather than a full frame distribution.

| Views | Baseline → optimized view-build ms | Baseline → optimized objects/FX ms | Baseline → optimized binding hash ms | Binding bytes / calls, baseline → optimized |
|---:|---:|---:|---:|---:|
| 1 | 26.338 → 7.765 | 21.165 → 2.594 | 11.382 → 0.000 | 32,872 / 1 → 0 / 0 |
| 2 | 52.668 → 17.847 | 41.559 → 5.289 | 11.380 → 0.000 | 32,872 / 1 → 0 / 0 |
| 3 | 76.711 → 19.876 | 62.003 → 5.698 | 11.380 → 0.000 | 32,872 / 1 → 0 / 0 |
| 4 | 102.165 → 25.390 | 82.173 → 6.866 | 11.380 → 0.000 | 32,872 / 1 → 0 / 0 |

View building remains a substantial renderer cost. CE publication also grows from 5.526 ms at one view to 20.015 ms at four, and simulation has not been separately timed here. These phases do not account for the entire gameplay loop; FPS is the end-to-end result.

## Rendering, safety, and memory evidence

For all four view counts, baseline and optimized captures are exact across the full 640×480 RGB frame and each active view. Canonical snapshots match; raw snapshots differ because they contain dynamic fields. Native bitmap request dumps match byte-for-byte and their queue semantics match. All held unsafe counters are zero in all eight runs: overflow, idle violations, emit failures, early releases, commit rejects, and write refusals. These parity and safety checks establish the tested output contract for this workload; they do not establish C3 closure or cover other maps, assets, or runtime states.

The optimized object path uses bounded single-object storage instead of clearing an entire 1,024-entry object table per individual draw. In the compiled audit, baseline object-pass stack allocation is 131,680 bytes and the disassembly shows the 131,092-byte table clear. The optimized combined build has a 720-byte object-pass frame and no such clear. The opt-in snapshot identity index is 1,024 entries × 8 bytes = 8 KiB of publication-lifetime scratch; it is included in the frame-scratch owner requirement.

Binding sealing is an explicit caller contract: profile and bitmap-binding metadata must remain immutable throughout the bound generation. Scalar profile, generation, queue and fence checks remain active; the strict binding API retains its hash checks. The snapshot writer index is a separate optimization. Neither moves animation simulation into the parent nor removes completion fences.

The eight measured multiview ELFs have 2,385,156–2,386,308 PT_LOAD file-backed bytes against a 2,490,368-byte static cap, leaving 104,060–105,212 bytes. Their PT_LOAD non-file-backed spans are 1,987,792 bytes each. The [eight-build budget audit](../../build/c3/perf/multiview-ab-20261025-r1/elf-budget-provenance-audit.md) identifies each ELF and its size; r2 reused these exact binaries. The guest matrix separately validated frame behavior. The ELF audit does not establish platform-wide memory closure.

## Capture qualification and provenance

The first r1 matrix was rejected for comparison because window placement varied between runs and its XWD captures contained position-dependent black crops. The r2 matrix is authoritative: it holds the window at a fixed secondary-monitor rectangle throughout each session and before capture. All eight r2 measurements are complete, all archived hashes and immutable workload tuples validate, and all paired parity results pass. The retained machine-readable record is [`report.json`](../../build/c3/perf/multiview-ab-20261025-r2/report.json); per-run logs, screenshots, raw/canonical snapshots, native queue dumps, launch settings, and active records are under [`runs/`](../../build/c3/perf/multiview-ab-20261025-r2/runs/). The compiled memory/disassembly evidence is [`compiled-audit.json`](../../build/c3/perf/renderer-ab-20261025-r1/compiled-audit/compiled-audit.json) with notes in [`compiled-audit-notes.md`](../../build/c3/perf/renderer-ab-20261025-r1/compiled-audit/compiled-audit-notes.md).

The measurement source pins are consistent across all eight cases (27 pinned files; pin-map SHA-256 `7e6fbeadaf3e2f65d2bc138f7d57f33aece5b4017a7ec547e18ab7e4ee4aac2d`). The corresponding commits are engine `7e43fbb`, CE `15534fc3`, and parent `8791056`, `095c3c4` and `3cebe60`; their committed source contents match the bytes used by the builds. The [pre-commit provenance archive](../../build/c3/perf/multiview-ab-20261025-r2/pre-commit-source/provenance.json) retains the original revisions and tracked patches.

Known limitation: the first-person weapon mesh remains oversized and intersects the view. It is present in the matched output and was not reconstructed or changed for this optimization. No C3 closure or 30 FPS split-screen claim is made.

## Quiet interactive build

The optimized one-player Blood Gulch build was verified with `HCU_C3_TIMING=0` and `HCU_C3_TELEMETRY=0`; all four optimization flags, resident HUD and the fixed-tick scheduler are enabled. Its ELF SHA-256 is `2124217d0683c6b0b5ad03cadd03ddd2c5c4b4b0505118d2bedbbe5ec0c39cd4`. The [active record](../../build/c3/perf/multiview-ab-20261025-r2/quiet-optimized-v1/desktop-active.json) and [gameplay capture](../../build/c3/perf/multiview-ab-20261025-r2/quiet-optimized-v1/gameplay-quiet.png) verify the owned desktop window, successful map load, realtime scheduler and absence of hot C3 timing lines or guest failure markers. The capture's OSD shows 29.97 FPS, 59.94 VPS and 100% emulation speed; the table above uses the separate timed runs.

Manual controls remain WASD movement, arrow-key look, Control crouch, F fire and G jump. Scripted firing is disabled. Startup and SDK messages can still appear; the C3 per-frame telemetry is compiled out.

## Next object-sharing opportunity

Snapshots already deduplicate world objects and poses, and model/texture residency is shared across views. The parent still repeats resource/model lookup, palette hashing, default permutation selection and matrix conversion when preparing each view. A bounded per-snapshot prepared-object cache could share those results while keeping visibility, LOD, clipping, first-person state and draw emission specific to each camera. This preparation cache was not part of the measurements above. It was subsequently implemented behind `HCU_C3_OBJECT_PREPARE_CACHE` and evaluated in the [separate cross-view A/B report](c3-object-sharing-ab-2026-10-25.md), which found no consistent FPS gain and retained the default-off setting. The four-view object/FX phase is 6.866 ms; publication, simulation and other renderer phases also need attention before claiming 30 FPS split-screen.

## Separate earlier isolated runs

An earlier, separate one-view series reported approximately 14.985 FPS baseline, 19.983 FPS with the object fast path, 19.402 FPS with binding sealing, 14.977 FPS with snapshot indexing, 19.982 FPS with view setup caching, and 29.972 FPS with the combined changes. Treat those figures as directional only: they came from separate sessions, were not the controlled multiview comparison, and small setup/index differences are within the noise of that earlier series. The authoritative comparison is the matched r2 matrix above.
