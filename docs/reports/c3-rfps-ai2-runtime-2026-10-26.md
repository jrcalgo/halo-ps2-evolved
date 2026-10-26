# C3 renderer timing instrumentation and runtime harness (AI2)

## Code changes

The opt-in BSP phase structure now splits clipped-polygon gathering from grouping and records input visible-batch count, gathered polygon count, and gathered vertex count across rendered views. Existing `BSP_RENDER_PHASE_TIMING` controls the added reads and counters; quiet builds do not execute the new instrumentation. The existing aggregate clip phase remains intact.

`video_present_timing_get` reports the most recent `graph_wait_vsync` and framebuffer-selection durations separately in EE Count cycles. Its measurements are enabled only by `HALO_PS2_C3_TIMING`; quiet builds return zeros. This preserves the existing prior-kick/GPU-fence order and still calls both original presentation operations.

No object-pose clear optimization was applied. `obj_render_pass` uses the static `s_nodes` workspace without clearing the full `object_nodes_t`. `objects_pose_model` writes active node matrices and sets `out->count`, or sets count to zero on failure. The 8,196-byte struct size therefore does not establish a repeated clear cost or justify a fastpath.

## Runtime harness

`build/c3/fps-next/ai2/` contains an adapted ignored C3 `build_case.py` and a runbook. The build helper pins the renderer and video sources in its source snapshot and builds a fresh timing ELF per view count. Use `python3 build/c3/fps-next/ai2/build_case.py --case baseline --views N` for N=2,3,4 after renderer and parent logger sources are frozen, followed by `tools/c3_render_run.py` as documented in the harness README. Do not use retained ELFs as fresh baselines. Runtime runs remain pending coordinated source freeze and sequential PCSX2 slots.

The parent timing logger owns the new public accessors and will report gather/group and presentation wait/select fields. No PCSX2 timing run was started in this implementation pass. Any future PCSX2 result describes emulator-host performance only, not native PS2 hardware performance.

## Verification and limits

- `ASAN_OPTIONS=detect_leaks=0 make -C submodules/halo-ps2/engine/tests` passed all host engine tests. Leak detection is disabled because the default LeakSanitizer execution fails in this environment with “LeakSanitizer does not work under ptrace”.
- Quiet and `HALO_PS2_C3_TIMING=1` EE builds passed using `tools.build_toolchain.environment()` and the repository SDK at `build/toolchain/install/ps2sdk`. A first attempt without the SDK environment failed because the engine Makefile defaulted to `/home/ai/ps2dev`; the corrected builds passed. The final output ELF was rebuilt quiet. Timing-only changes compile cleanly; the quiet build has no warning from the new code.
- No PCSX2 or hardware execution was performed. Pixel parity for these diagnostics must be checked in the coordinated fresh multi-view run.
