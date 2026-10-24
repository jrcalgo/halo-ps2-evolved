# M2 C2 guest verify (lane guest-verify, round 6), 2026-10-24

Status: **partial.** The lifecycle guest now runs both unload/reload cycles to `m2-ui-lifecycle-complete cycles=2`
with current source. The C2.6 counter set is not complete: the lifecycle run prints arena and cache-owner counters
only at boot and before the shell, so no per-cycle high-water, failure or reset set is claimed. The 2-cycle result is
a host-fixture-free guest result; the legacy first-load-after-preflight success path is still not covered by any
host test (see Host test).

## Changes

- `tests/hcu_map_service_profile_main.c`: a legacy-path case in section 5a. With the renderer predicate set and a mount
  marked active, a load is refused by the owner gate and the unload is blocked while the renderer is busy; the mount
  flag is then cleared. The first-load-after-preflight success case was attempted and removed: `hcu_map_service_preflight`
  opens the real CE map (`maps/ui.map`) and checks its source SHA, which the host fixture does not carry
  (`source-open-failed`).
- `tests/test_hcu_map_service_profile.py`: PASS count 23 to 24.
- `src/stream/hcu_main.c`: the reserve literals (`reserve=0x1a00000`, `reserve_bytes=5767168`) are now printed from
  `HCU_COMMITTED_BYTES` (27787264u), `HCU_RESERVE_BYTES` and `HCU_RESERVE_START` (= committed bytes, 0x1a80000). Only the
  reserve printf lines and the three macro definitions were touched.
- `tools/c2_guest_run.py`: output dir `build/m2-c2-r6-guest-verify/`; `GUEST_RESERVE_START` = 0x1a80000; the brief-reserve
  constant removed; date 2026-10-24.
- `tests/test_c2_guest_parse.py`: the brief-reserve assertion removed.

## Host test

`python3 -I tests/test_hcu_map_service_profile.py` (artifacts under `build/m2-c2-r6-guest-verify/map-service-profile`):
`Ran 1 test ... OK`, 24 `PASS` lines, `map-service-profile-lifecycle passed`.
`python3 -I tests/test_c2_guest_parse.py`: 6 tests, OK.
`git diff --check` on the touched files and `submodules/halo-ps2`: clean.

## Lifecycle ELF

`timeout 2400 python3 tools/hcu_parent_link_probe.py --asset-profile host --m2-ui-lifecycle-test` completed with
`EXIT=0`. ELF `build/hcu-parent-link-probe/hcu-gameplay-machine-m2-ui-lifecycle.elf`, copied to
`build/m2-c2-r6-guest-verify/fresh/hcu-gameplay-machine-m2-ui-lifecycle.elf`, sha256 prefix `cc0886a4afb1dceddf63`.
The ELF prints the reserve through format arguments (`reserve=0x%x`), and the run shows `reserve=0x1a80000`.

## Guest run

`timeout 900 python3 -I tools/c2_guest_run.py --only lifecycle --source-elf <fresh ELF> --timeout 600` on the existing Xvfb
`:99`. The emulator ran to the 600 s bound and was signalled by the runner (`bounded timeout after 600s (SIGINT)`);
no emulator process was left. `manifest.json` reports `no_run_errors: true`, 266 HALO lines, all required markers present.
Log: `build/m2-c2-r6-guest-verify/runs/lifecycle/halo_ps2_local.txt`; raw `emu.txt` in the same run directory.

Ordered lifecycle lines (exact, the timestamps removed):

```
map-mount result=0 active=1
m2-ui-lifecycle-start tag_base=0x952750 tag_bytes=2097152 bsp_base=0xb52750 bsp_bytes=4194304
m2-ui-lifecycle-injected preflight-before-unload
m2-ui-lifecycle-preunload-failure-preserved
m2-ui-owner cycle=0 phase=ce-unpublished-owner-released ... mount=0 source=0 ... staged=ui
m2-ui-lifecycle-injected preflight-after-unload
m2-ui-lifecycle-postunload-ce-preflight-refused
m2-ui-lifecycle-postunload-failure-safe-empty
map-mount result=0 active=1
m2-ui-lifecycle-postunload-retry-complete
m2-ui-lifecycle-ce-unpublished cycle=1 ...
m2-ui-owner cycle=1 phase=ce-unpublished ... mount=1 source=1 ...
m2-ui-lifecycle-owner-released cycle=1 ...
m2-ui-owner cycle=1 phase=ce-unpublished-owner-released ... mount=0 source=0 ...
map-mount result=0 active=1
m2-ui-lifecycle-cycle-complete cycle=1
m2-ui-lifecycle-ce-unpublished cycle=2 ...
m2-ui-owner cycle=2 phase=ce-unpublished ... mount=1 source=1 ...
m2-ui-lifecycle-owner-released cycle=2 ...
m2-ui-owner cycle=2 phase=ce-unpublished-owner-released ... mount=0 source=0 ...
map-mount result=0 active=1
m2-ui-lifecycle-cycle-complete cycle=2
m2-ui-lifecycle-complete cycles=2
```

Order holds: `ce-unpublished` precedes `owner-released`, which precedes the next `map-mount result=0`. The pre-unload
failure is preserved; the post-unload CE preflight is refused and leaves a safe empty state; the retry completes.

Memory lines (boot, exact):

```
kernel-reservation low=0x0 low_bytes=1048576 high=0x1f80000 high_bytes=524288 reserve=0x1a80000 reserve_bytes=5767168
memory-physical elf_end=0x48308c boot=0x4832b0 boot_end=0x19d285a reserve=0x1a80000 allocator_gap=548
memory-layout bss=1772428 backing=22344820 guard_slack=310
```

Arena lines (boot, all cycles identical; `alloc_failures=0 resets=0` for every arena):

| arena | cap | used | high |
|---|---:|---:|---:|
| resident_gameplay | 5,043,316 | 4,214,784 | 4,214,784 |
| current_bsp | 6,291,456 | 2,097,152 | 2,097,152 |
| texture_cache | 4,194,304 | 0 | 0 |
| dynamic_simulation | 2,621,440 | 0 | 0 |
| dma_commands | 1,179,648 | 0 | 0 |
| streaming | 1,572,864 | 0 | 0 |
| checkpoint | 524,288 | 0 | 0 |
| audio | 524,288 | 0 | 0 |
| frame_scratch | 393,216 | 0 | 0 |

Cycle owner: `m2-ui-owner` lines show the UI owner (`cap=1048576`) at `used=39752 high=39880` while mounted and
`used=0` after release, with `high=39880` kept.

Cache owner (exact, the only `cache-owner` lines in the run):

```
cache-owner phase=before-shell name=tags current=0 peak=0 publications=0 failures=0 unmounts=0 resets=0
cache-owner phase=before-shell name=bsp current=0 peak=0 publications=0 failures=0 unmounts=0 resets=0 lease_failures=0 readers_drained=1 mount_rejections=0
```

Owner telemetry: 26 `owner-telemetry` lines (bound and before-shell). Partition `bootstrap`, `backing_cap=12582912
backing_used=274704 backing_high=274704 backing_failures=0 backing_resets=0 nested_within_parent=1 renderer_drained=1`.
Backing owners, `failures=0 resets=0` for all: `scratch cap=393216 used=274704 high=274704`; `tags cap=2097152 used=0`;
`bsp cap=4194304 used=0`; `dynamic_simulation cap=2621440`; `streaming cap=1572864`; `dma cap=1179648`;
`audio_requests cap=524288`. Nested owners `game_state`, `object_pool`, `actor_pool`, `render_texture` are unbound (`cap=0`).

## Not produced / open

- No per-cycle arena, cache-owner or owner-telemetry lines after the boot and before-shell points. The per-cycle
  high-water (C2.6) is therefore not measured for the unload/reload cycles.
- The legacy first-load-after-preflight-then-mount path (the orchestrator's gate change) is exercised on the guest
  (`map-mount result=0` after each preflight) but has no host test.
- `src/stream/hcu_main.c` still carries the stale comment `The v2 reserve is [26 MiB, 31.5 MiB)` at the kernel-stack
  check. It is not a printed literal and is outside this lane's ownership.
- Step 8 and gameplay ELF runs were not repeated.

## Needed cross-lane changes

1. `src/stream/hcu_main.c` stale reserve comment above `report_kernel_stack` (`26 MiB .. 31.5 MiB` should read
   `27,787,264 B .. 32 MiB`); not this lane's file region.
2. Emit arena, cache-owner and owner-telemetry lines at each cycle's unload and reload points so C2.6 high-water
   can be read per cycle.
