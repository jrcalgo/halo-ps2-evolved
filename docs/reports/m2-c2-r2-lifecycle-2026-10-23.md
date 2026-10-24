# M2 C2 lifecycle lane (r2): renderer drain and foreign-profile replacement

Date: 2026-10-23. Lane: C2.8 (map service lifecycle). Evidence level: host execution, plus an EE compile of `hcu_map_service.o`.

## Changes

- `src/stream/hcu_map_service.h`: `hcu_map_profile_runtime` gains `renderer_drained` and `renderer_context`. The service gains a second, foreign successor slot and `hcu_map_service_register_successor_runtime`.
- `src/stream/hcu_map_service.c`:
  - `profile_readers_drained` now takes the runtime. It also requires the renderer predicate to return nonzero. A NULL predicate fails closed.
  - Preflight for a different catalog map stages a successor under its own runtime (`profile_preflight_successor`). Its spans must be disjoint from the registered runtime's, and nothing publishes while the owner is live.
  - `profile_load` swaps the successor runtime in once CE has released the owner. A failed load leaves the successor registered for a retry.
  - Unregister and shutdown clear the successor slot.
- `tests/hcu_map_service_profile_main.c`: the mount seam records an ordered trace (`prepare`, `publish`, `load-fail`, `dispose`, `unpublish`). The scripted dispose callback reads the live owner's tag bytes. The renderer predicate is scripted and defaults to drained. Six new cases cover the foreign replacement A (`ui`) to B (`beavercreek`).
- `tests/test_hcu_map_service_profile.py`: PASS count 12 to 18. The compile adds `-DHCU_M2_MP_HOST_ORACLE` so the host catalog admits `beavercreek`. The define is never in the EE build.

## Evidence

- `python3 -I tests/test_hcu_map_service_profile.py`: OK. Artifacts in `build/m2-c2-r2-lifecycle/result.json` (`passing_checks: 18`, `result: passed`).
- EE compile: `build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-gcc` with the flags from `tools/ee-world.mk`, output `build/m2-c2-r2-lifecycle/ee/hcu_map_service.o`, no diagnostics.
- `git diff --check` on the touched files: clean. No submodule files were touched.

## Limitations

- The mount seam, the CE dispose callback and the renderer drain predicate are all scripted. No real CE simulation dispose, GS/DMA fence, or target run is exercised.
- The successor reuses the `ui` package bytes and metadata, with a different map name. The real package for `beavercreek` is not exercised here.
- Production does not yet supply a renderer predicate. `hcu_main.c` does not register a runtime today, so its behavior is unchanged. A production predicate (`bsp_render_fence_observed(bsp_render_kick_seq()) == 1` and world cleared) is a cross-lane change for `hcu_main.c`.
- C2 exit is not claimed.
