# M2 C2 round 2, lane render-dma (C2.7 and the renderer half of C2.6), 2026-10-23

Scope: renderer DMA chains, direct snapshot emission into the idle geometry chain, the frame-scratch packet
workspace, renderer owner telemetry, and the idle-chain rule. Host and EE-compile evidence only. No PCSX2 or
hardware run was made. C2.7 and C2.6 are not closed by this lane.

## What changed

- `submodules/halo-ps2/engine/src/render/storage.h`: exact packet workspace spans (`BSP_RENDER_VIF_PROGRAM_*`,
  `BSP_RENDER_ENV_PACKET_*`, `BSP_RENDER_FONT_PACKET_*`), `bsp_render_chain_is_idle()` (the idle-chain rule),
  `bsp_render_owner_counters`, and the prototypes of `bsp_render_dma_counters()` and `bsp_render_texcache_counters()`.
- `submodules/halo-ps2/engine/src/render/bsp_render.c`:
  - Per-chain counters (qwords used, high-water, overflow, rebuilds) for geometry[0..1] and upload[0..1].
  - Build: if the chosen chain is the one the in-flight kick references, the build moves to the other chain and
    `s_idle_redirects` counts it.
  - Emit: the emit hook is refused (status -1, `s_idle_violations`) if its chain is in flight. This is a check that
    should stay at 0.
  - Kick: records `s_kick_index`.
  - `_Static_assert` that the three packet spans tile `BSP_RENDER_WORKSPACE_BYTES` (5632).
  - `_Static_assert(CACHE_FIRST_PAGE == 17)`.
  - `bsp_render_dma_counters()`, `bsp_render_texcache_counters()`, `bsp_render_idle_redirects()`,
    `bsp_render_idle_violations()`.
- `submodules/halo-ps2/engine/src/render/bsp_render.h`: prototypes of the two idle-rule getters.
- `src/stream/hcu_bitmap_attach.c`: `attach_emit` appends the snapshot matrices with
  `hcu_render_snapshot_emit_chain(geometry)` before the bitmap drain. The drain always runs. A snapshot failure is
  returned as `HCU_BITMAP_FRAME_E_QUEUE` and counted by `bsp_render_emit_failures()`.
- `src/stream/hcu_render_telemetry.{c,h}` (new): the samplers `hcu_render_telemetry_sample_dma`,
  `hcu_render_telemetry_sample_render_chunks` and `hcu_render_telemetry_sample_texture`, and
  `hcu_render_telemetry_bind()`.
- Tests: `tests/bsp_render_storage_main.c` (extended), `tests/render_dma_telemetry_main.c` (new),
  `tests/test_render_dma.py` (new), `tests/test_hcu_bitmap_renderer.py` (stale `#define CHAIN_QW` literal check
  updated to the `BSP_RENDER_*` macros; see below).

## Accounting (bytes)

| Owner | Kind | Capacity | Source |
| --- | --- | ---: | --- |
| DMA geometry | BACKING (within DMA) | 1,048,576 | 2 x 32768 qw |
| DMA upload | BACKING (within DMA) | 131,072 | 2 x 4096 qw |
| DMA total | BACKING | 1,179,648 | `BSP_RENDER_DMA_STORAGE_BYTES` |
| Render chunks | BACKING | 1,187,840 | 1,048,576 texture cache + 139,264 (17 reserved pages) |
| Texture | NESTED in render chunks | 1,048,576 | texture cache pages x 8192 |
| Packet workspace | frame scratch | 5,632 | [0,4096) VU1 program, [4096,5120) env, [5120,5632) font |

Emit failures are charged to DMA geometry, because the emit hook writes the geometry chain. The DMA sampler's
`high` is the sum of the two per-kind peaks, an upper bound on the peak of the sum. Its `resets` counts geometry
rebuilds. Idle redirects and idle violations are reported by their own getters and are not added to any owner.

## Evidence

Commands run in the repo root.

1. Focused host tests:
   `python3 -I -m pytest -q tests/test_render_dma.py tests/test_bsp_render_storage.py tests/test_hcu_bitmap_renderer.py tests/test_hcu_render_snapshot.py`
   Output: `18 passed in 0.75s`.
   - `test_renderer_chain_layout_workspace_and_idle_rule_host` compiles `tests/bsp_render_storage_main.c` with
     `-std=c11 -Wall -Wextra -Werror` and runs it. It pins the two geometry and two upload chains, the four exact
     DMA spans, `BSP_RENDER_WORKSPACE_BYTES == 5632`, the three packet spans (0/4096/1024/5120/512), the idle-chain
     truth table, and a 64-frame build/kick alternation that never builds on the in-flight chain.
   - `test_renderer_owner_samplers_and_registry_host` compiles the telemetry test with stubbed EE counters and the
     real `hcu_owner_telemetry.c`. It checks the sampler arithmetic (DMA 1,179,648 capacity; texture nested;
     render chunks adds 139,264 reserved), the unbound path, and the owner registry (nesting and `backing_capacity`).
   - Source tests check that the build redirect and emit gate exist, that `attach_emit` calls the snapshot emit
     before `hcu_bitmap_renderer_hook_emit`, and that the sampler signatures match `hcu_owner_sampler_fn`.
2. EE cross-compile with `build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-gcc`, `-std=gnu11 -Wall -Wextra
   -Wno-unused-parameter -G0 -O2 -D_EE`, PS2SDK headers from `build/toolchain/install/ps2sdk`, and the halo-ce
   port/source includes (the `ee-world.mk` set):
   - `build/m2-c2-r2-render-dma/bsp_render.o`: rc 0, no warnings.
   - `build/m2-c2-r2-render-dma/hcu_bitmap_attach.o`: rc 0, no warnings.
   - `build/m2-c2-r2-render-dma/hcu_render_telemetry.o`: rc 0, no warnings.
3. `git diff --check` in the repo (for the tracked touched files) and in `submodules/halo-ps2` (for storage.h,
   bsp_render.c, bsp_render.h): rc 0 for both. The new untracked files were not in the diff check.

## Stale test corrected

`tests/test_hcu_bitmap_renderer.py::test_renderer_dma_budget_unchanged` required the literal `#define CHAIN_QW
<digits>`. Earlier uncommitted work in `bsp_render.c` had changed that define to `BSP_RENDER_GEOMETRY_CHAIN_QW`
(HEAD has the literal `32768`). The test failed with `AttributeError: 'NoneType' object has no attribute 'group'`.
It now reads the value from `storage.h` and checks that `CHAIN_QW` and `UPLOAD_QW` name those macros. The
assertion (2 x 32768 + 2 x 4096 chain qwords = 1,179,648 bytes) is unchanged.

## Not proved (remaining limitations)

- C2.7 needs a current guest in-flight chain and fence, and a full rendered workload on the EE. Neither has run.
  No PCSX2 or hardware evidence exists for the direct snapshot emission.
- The VU1 consumer of the snapshot matrices (the VIF1 UNPACK of V4-32 matrices) is not verified on the EE.
  `hcu_render_snapshot_emit_chain` is called in production now, but no test checks the uploaded matrices against
  the VU1 side.
- The idle-chain redirect is a correction for a misuse (building twice without a kick). The frame loop in
  `bsp_render_build`/`bsp_render_kick` alternates correctly, so the redirect counter should stay 0 in a correct
  loop. The host test only checks the alternation rule, not the EE loop itself.
- The render-chunks owner mapping (texture window with reserved pages as the BACKING store) is this lane's
  interpretation of the owner table in `hcu_owner_telemetry.h`. The C2.6 owner should confirm it.
- The high-water for the DMA owner is an upper bound (sum of per-kind peaks). Exact peaks of the sum need one
  combined high-water register.
- Texture-cache `high_water` and `resets` are per world (reset at `bsp_render_set_world`). Texture `failures` are
  `tc_t.failed`, which is cumulative per world.
- Nothing from the HCU frame reaches these hooks in the live loop (the ADR-031 seam is still C3 work).
