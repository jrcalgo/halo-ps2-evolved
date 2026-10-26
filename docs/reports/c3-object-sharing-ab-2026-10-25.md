# C3 cross-view world-object preparation cache A/B — 2026-10-25

## Result

The cache preserved baseline rendering and passed the captured safety checks, but this matrix did not show a consistent host FPS gain. The measured FPS changes were +0.008%, −0.027%, +2.025%, and −0.244% for one through four views. The three-view result improved by 0.294 FPS; the other three results were essentially flat or slower. Keep `HCU_C3_OBJECT_PREPARE_CACHE` opt-in (default off) until a repeatable gain is demonstrated.

All four pairs had exact full-frame RGB output, exact canonical snapshots, exact native bitmap request dumps and equal queue semantics. Raw snapshot bytes differed in dynamic publication metadata; replay assigns a fresh sequence, and every optimized replay logged a sequence different from its reference sequence. All timed runs had zero dropped-tick delta and passed held-counter, cache-guard, source, package, settings, process-cleanup and artifact checks.

## Method

The eight runs used commit `2a8a0836893c31bf80b12fa37e28edb99b97135e` and one source pin map/archive across both arms. Both arms retained the prior object fast path, view cache, binding seal, snapshot index 1, resident HUD, real-time scheduler, and fixed pad driver. The only timed build-flag change was `HCU_C3_OBJECT_PREPARE_CACHE=0` versus `1`; movement tracing was explicitly disabled. The optimized arm replayed the matching baseline snapshot only after the timing window for parity capture.

Each view count used the same Blood Gulch package/profile, player count matching the view count, 640×480 PCSX2 window at `[3200,647,640,480]`, neutral input, and disabled OSD. PCSX2 ran sequentially, one owned process group at a time. Rates use scheduler cumulative counters at completed ticks 151 and 601 with their matching host log timestamps. Timing means and sample counts use log rows within that same host-time interval. Each case had 5–15 `c3-timing` and `c3-view-perf` samples in the measured interval, depending on view count. This is one run per configuration, with all baseline runs before the cache-enabled runs. There are no confidence intervals or repeat trials, so the small FPS differences should not be treated as established speedups or slowdowns.

The [machine-readable report](../../build/c3/perf/object-sharing-ab-20261025-r1/report.json) and [per-run evidence](../../build/c3/perf/object-sharing-ab-20261025-r1/runs/) retain values, hashes, captures, settings and safety counters. Build/run/score helpers remain in that ignored harness directory.

## Performance

| Views | FPS baseline → cache | Change | Game Hz baseline → cache | Drops 151→601 B/O | View build ms B/O | Render callback ms B/O | Objects/fx ms B/O | Outer residual ms B/O | Timing/view samples B/O |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 29.972 → 29.975 | +0.008% | 30.039 → 30.041 | 0 / 0 | 7.798 / 7.991 | 19.520 / 19.471 | 2.626 / 2.418 | 1.119 / 1.519 | 15/15 / 15/15 |
| 2 | 18.745 → 18.740 | −0.027% | 30.018 → 30.010 | 0 / 0 | 15.265 / 18.938 | 25.273 / 35.658 | 4.362 / 5.411 | 1.922 / 2.056 | 10/10 / 10/10 |
| 3 | 14.536 → 14.830 | +2.025% | 30.005 → 30.061 | 0 / 0 | 19.131 / 18.765 | 25.680 / 25.584 | 5.411 / 5.014 | 2.861 / 2.622 | 7/7 / 7/7 |
| 4 | 9.991 → 9.967 | −0.244% | 29.973 → 30.101 | 0 / 0 | 25.620 / 23.891 | 35.280 / 35.803 | 6.976 / 6.156 | 3.902 / 3.186 | 5/5 / 5/5 |

`Outer residual` is `view-build-ms − c3-view-perf total-ms`; it estimates work outside the measured inner view path. The object/fx, view total and residual values move in different directions across view counts. This mixed timing evidence, alongside nearly unchanged FPS, does not establish useful cross-view CPU headroom. The four-view host rate remains below 30 FPS in both arms; game simulation stayed near 30 Hz with no warm-window dropped ticks.

## Cache activity and memory

These are cumulative counters since launch at each run’s last periodic sample inside the warm interval. Sampled render-frame endpoints differ between view counts; the totals are evidence of cache use, not normalized work-per-frame comparisons.

| Views | Prepared total | Reused total | Slots total | Fallbacks | Guard |
|---:|---:|---:|---:|---:|---|
| 1 | 48,365 | 36,416 | 17,640 | 0 | ok |
| 2 | 31,233 | 45,952 | 11,130 | 0 | ok |
| 3 | 23,941 | 51,648 | 8,609 | 0 | ok |
| 4 | 16,289 | 45,824 | 5,550 | 0 | ok |

The cache is allocated from the existing frame scratch arena: 98,304 bytes reserved plus a 16-byte canary. The optimized boot record reported 360,928 bytes used of the 393,216-byte arena after binding, leaving 32,288 bytes. Every optimized timing sample reported `guard=ok`; baseline samples reported `guard=unused`. The cache adds no heap allocation or large BSS allocation according to the implementation review.

## Parity and safety

| Views | Full RGB exact | Canonical snapshot exact | Raw snapshot exact | Native bitmap dump exact | Queue semantics | All rendering/safety checks |
|---:|---|---|---|---|---|---|
| 1 | yes | yes | no | yes | yes | pass |
| 2 | yes | yes | no | yes | yes | pass |
| 3 | yes | yes | no | yes | yes | pass |
| 4 | yes | yes | no | yes | yes | pass |

Raw snapshot differences are expected from dynamic sequence metadata; canonical snapshots match exactly. Replay publications received a fresh sequence in all optimized captures (reference → published: 591→593, 369→370, 286→293, 198→199). All captures were 640×480 and all PCSX2 process groups stopped cleanly. Held unsafe counters (overflow, idle violations, emit failures, early releases, commit rejects and write refusals) were zero; cache fallback totals were zero; no fatal markers were found. Every run retained matching source pins, package hash, effective PCSX2 settings, neutral input/OSD state and valid captured artifacts.

Implementation validation reported separately before the matrix: 22 focused host tests plus 7 subtests passed, and the actual EE adapter fixture passed ASan/UBSan with `ASAN_OPTIONS=detect_leaks=0` (LeakSanitizer was unavailable in the ptrace environment). These checks do not substitute for the runtime A/B results above.

## Implementation and limits

The cache resolves world-object model slots and pose hashes once per pinned publication, keeps model metadata and default permutations per resident slot, and prepares world roots and node matrices for reuse across views. A bitmap ensures overlapping palette ranges are converted once. Keys include publication sequence, map generation, object generation, resource identity and slot residency epoch; loading, eviction and map reload invalidate prepared state. Invalid or unavailable cache entries use the original path. Compact validity metadata is cleared between publications; the large matrix pool is not cleared each frame.

Camera-dependent visibility, LOD, clipping, first-person transforms, final projected palettes and draw emission remain per view. Snapshot/resource pins and completion fences are retained. The flag defaults to zero; enabling it is a separate build choice.

This series tests one Blood Gulch workload in PCSX2’s recompiler. Exact baseline parity does not establish source-game parity or full C3 qualification. The oversized/intersecting first-person weapon geometry remains present in both arms. The cache is not being promoted into the quiet desktop configuration because this series did not show a consistent FPS benefit.

## Restored quiet desktop

After timing finished, the current-source one-player Blood Gulch guest was rebuilt with all previous optimizations enabled and `HCU_C3_OBJECT_PREPARE_CACHE=0`. Telemetry, timing and movement tracing are disabled. Its ELF SHA-256 is `830224d4cc9ab7909b99d1a80855d111ae111f730ccb2c3d7bb1b602c722db03`; the manifest pins source commit `2a8a083` and the fixed controller driver. The owned process group `1014044` was left visible on the secondary monitor, with no test keys held.

The full-window capture shows PCSX2 OSD **29.97 FPS / 59.94 VPS / 100% speed**. This is a live OSD observation, separate from the timed rates above. No movement test input was sent in this quiet verification. Controller setup messages stopped after initialization; the known Xbox-style device warnings remain in the startup log.

- [Quiet launch manifest](../../build/c3/perf/object-sharing-ab-20261025-r1/quiet-baseline-v1/desktop-launch.json)
- [Quiet active-session record](../../build/c3/perf/object-sharing-ab-20261025-r1/quiet-baseline-v1/desktop-active.json)
- [Full quiet capture](../../build/c3/perf/object-sharing-ab-20261025-r1/quiet-baseline-v1/gameplay-quiet.png)
- [Quiet desktop verification](../../build/c3/perf/object-sharing-ab-20261025-r1/quiet-baseline-v1/reportquiet-verification.json)
