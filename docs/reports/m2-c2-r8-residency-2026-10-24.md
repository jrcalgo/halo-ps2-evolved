# M2 C2 r8 residency lane: residency slot count (C2.4)

Date: 2026-10-24. Lane: residency-measure. Scope: make the residency arena slot count of the
profile-mount fixture configurable, run the parametrized mount test per slot count, and record
which packages pass and the residency high-water.

## Change

- `tests/hcu_profile_mount_main.c`: the slot count is `HCU_PROFILE_MOUNT_TEST_RESIDENCY_SLOTS`
  (default `16u`, so the default build is unchanged). The fixture prints one line per run,
  `RESIDENCY_STATS map=... slots=N segment_bytes=65536 resident_high_water=... refused_pins=... evictions=...`,
  taking the maximum high-water and summing refused pins and evictions over the three cycles.
- `tests/test_hcu_profile_mount.py`: `HCU_PROFILE_MOUNT_RESIDENCY_SLOTS=<N>` adds
  `-DHCU_PROFILE_MOUNT_TEST_RESIDENCY_SLOTS=<N>u` to the compile. Each package also writes
  `<profile>.result.json` beside the shared `result.json`, which the next package overwrites.

Artifacts: `build/m2-c2-r8-residency/pm-{1,2,4,8,16}/` (per-package `*.result.json`, `hcu-profile-mount-fixture`),
`build/m2-c2-r8-residency/pytest-n{1,2,4,8,16}.log`.

## Results (27 packages: `ui` + 26 selected sessions; `HCU_C1_PROFILES=build/m2-c2-hcp2-primary`)

| slots | arena | packages passed | notes |
|---:|---:|---:|---|
| 1 | 64 KiB | 0 of 27 | every package fails at cycle 0's lease gate: `read_tags(&mount, 0)` returns 42 (`tests/hcu_profile_mount_main.c:524`) |
| 2 | 128 KiB | **27 of 27** | refused_pins 0 in every package |
| 4 | 256 KiB | 27 of 27 | refused_pins 0 |
| 8 | 512 KiB | 27 of 27 | refused_pins 0 |
| 16 | 1 MiB | 27 of 27 | refused_pins 0; the default |

Minimum slot count passing all 27: **2** (128 KiB of residency arena).

Single-slot failure: the cycle-0 gate takes a lease on CE segment 0, the only slot, then reads
tags. Reading the tag stream needs a second slot for the next segment, so the stream fails with
return 42. This is the fixture's lease gate holding a segment while the walk runs, not a
walk requirement by itself. The walk pins one segment at a time (`pinned_walk` in
`src/stream/hcu_profile_mount.c`), so one slot suffices for a stream with no lease held. That
case was not run separately.

### Residency high-water

`resident_high_water` is capped by the slot count, so it reports the arena in use, not the
need: every package at N = 2, 4, 8 and 16 reports exactly `N x 65536` B (for example 131072 B at
N = 2, 1048576 B at N = 16), except `ui` at N = 16, which peaks at 801517 B. The measured need is
therefore at most 2 segments (128 KiB) for the fixture's gates, and the evictions show the
arena is recycled throughout (about 850 to 1700 evictions per package at N = 16, 1000 to 1700 at
N = 2).

Per-package high-water (`resident_high_water` in bytes):

- N = 2: 131072 for all 27 packages (`ui` included).
- N = 4: 262144 for all 27.
- N = 8: 524288 for all 27.
- N = 16: 1048576 for 26 packages; `ui` 801517.

No package refused a pin at any N tested.

## Limits

- Measurement is of the fixture only: the mount test with its gates (pin, lease, gameplay ref,
  unload refusal). It does not include a live gameplay roster, renderer DMA holds or
  simultaneous GS/DMA staging, so it does not size the production partition span.
- The lease-gate result (N = 1 fails) is caused by the test's own lease on segment 0. The
  production minimum for a gameplay-only stream is not measured here.
- The minimum passing count (2) is one slot above the walk's single-pin need; the partition
  span should not be sized from 2 alone. Size it from the live roster and DMA holds in C2.4/C2.7.
- All 27 packages were checked with a separate artifacts directory per N, so the shared
  `result.json` overwrite is not relied on.

## Verification

- Default (N = 16) full suite passed 27 of 27 after the changes (run before the per-package copy was added,
  and again at N = 16 with it: `build/m2-c2-r8-residency/pytest-n16.log`, 27 passed).
- `git diff --check` clean on `tests/hcu_profile_mount_main.c` and `tests/test_hcu_profile_mount.py`.
- No file under `build/m2-c1-*` or `docs/reports/m2-c2-status-2026-10-23.json` was written.
