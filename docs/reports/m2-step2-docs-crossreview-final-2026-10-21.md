# M2 Step 2 final lifecycle cross-review — 2026-10-21

This report closes the documentation/runtime cross-review for the UI lifecycle portion of M2 Step 2. It is report-only: no code or plan edits were made.

## Verdict and scope

**The opt-in UI lifecycle acceptance is now complete for its defined test scope.** Both PCSX2 interpreter and recompiler passed the exact same lifecycle diagnostic ELF, both with a 5-second post-marker window and required physical-placement validation. The results exercise the intended order: preserve a live owner when pre-unload preflight fails; use CE’s actual unload path to unpublish scenario state; release the parent CTAG owner; refuse an injected post-release request safely at CE preflight; retry in the same process; then complete two more clean UI unload/reload cycles.

This does **not** close M2, prove a retail gameplay map fits, or prove visible rendering. The lifecycle diagnostic ELF and ordinary gameplay ELF are separate artifacts and have different results. In particular, the ordinary profile in [`result.json`](../../build/hcu-parent-link-probe/result.json) is over the fixed `elf_static` file-backed limit by **388 bytes**; that is a production-profile issue, not a failure of the lifecycle ELF, which is under the same bound. Keep the ordinary-image overage visible and do not mark the ordinary build accepted on the basis of the diagnostic run.

The current numbered Group A Step 2 entry also records a fresh normal-profile UI load as part of its status ([`plans/7.hcu-remake-m2-m4.md:207`](../../plans/7.hcu-remake-m2-m4.md#L207)). Earlier normal-profile UI evidence exists for a different ELF (e.g. `03670da6…`); if Step 2’s formal exit criterion requires a normal-profile run of the *current* ordinary ELF, that criterion remains open until an in-budget production image is requalified. If the intended step is specifically the lifecycle follow-through now added, mark that lifecycle subcheck complete and track the 388-byte production overage separately—do not hold this subcheck open for gameplay-map capacity/rendering work assigned elsewhere.

## Exact paired guest evidence

Both results identify lifecycle ELF SHA-256 `c1167ae2e3d8a604d826f4dbde6f2e8ba305f7d9356b47434a7de18bd40d9d38`, parent/HCU/halo-ps2 commits `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`, and unchanged host assets. The data ISO is `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`; it is mounted as data for a direct ELF boot (`boot_from_disc=false`), not used as a bootable PlayStation disc.

| Mode | Result and log | Stability | Physical-placement outcome |
|---|---|---:|---|
| Interpreter | [`result.json`](../../build/hcu-ps2-closure/emulator-m1-interpreter-633e8b7c18124e17810bc993df02a0fc/result.json), SHA-256 `f8adb4c98e140bcc834eb0cc1497a284a9bdac78a414503aeb91f4e0e57b3ae2`; log SHA-256 `d0a5d66432e24cd951db9ec55954c981f4c68b40261844d5273b3f89611aa49d` | 5.0155 s (required 5.0 s) | `physical_memory` valid; `linked_physical.passed=true`; 207,014 bytes to reserve |
| Recompiler | [`result.json`](../../build/hcu-ps2-closure/emulator-m1-recompiler-80d252f52e3144f9bf370ad24d8b393f/result.json), SHA-256 `0d74e297aff96750ca572b1b6d6ebbf4ae444d6d6e6dff23b470b14847343bc4`; log SHA-256 `3d74a053032ceb532b26b328268e602de4a0a7faf62804313a5eb29822df8cc2` | 5.0167 s (required 5.0 s) | `physical_memory` valid; `linked_physical.passed=true`; 207,014 bytes to reserve |

Both results are `passed`, stage `m2-ui-lifecycle`, reach `game-initialize-done` and `m2-ui-lifecycle-complete cycles=2`, and have `host_assets_unchanged=true`. In each result, all eight linked-layout checks pass: exact ELF, CRT end, malloc request, allocator gap, arena capacities, physical non-overlap, load intervals, and boundary canaries. The runtime arena bases/capacities agree across modes; UI reloads restore base `0x16ed690`, cap `1,572,864`, used `39,752`, and high-water `39,880`.

The full logs preserve the same critical state transitions in both modes:

- The pre-unload injection leaves the before/after owner records identical (`used=39,752`, `mount=1`, `source=1`, descriptor `256`, no staged request), followed by the preservation marker.
- At the deliberate CE-unpublished seam for cycles 1 and 2, scenario/BSP/collision/BSP3D/game globals and tag instances are null, all relevant indices are `-1`, tag count is zero, and `cache=1`. That cache value is the expected pre-release seam: the parent owner remains alive until CE has unpublished all pointers.
- The following owner-release records have all CE globals null and `cache=0`; parent streaming owner `used=0`, mount/source `0`, descriptor `-1`, and the same base/capacity. Historical `high=39,880` remains intact; teardown should not erase a high-water measurement.
- The post-release injected attempt reaches `m2-ui-lifecycle-postunload-ce-preflight-refused`, then `...failure-safe-empty`; the same-process retry reaches `...postunload-retry-complete` and reloads the UI.
- Deliberate completion rows are exactly cycles `[1,2]` (initial cycle-0 cleanup is not miscounted). Each reload restores identical owner state and preserves the ordered CE-unpublish → parent-release → reload sequence.

These checks agree with the current validator at [`tools/test_hcu_boot.py:95-180`](../../tools/test_hcu_boot.py#L95). In particular, it correctly expects `cache=1` before parent owner release and validates exact cycles 1 and 2. This is consistent with the earlier documentation review and with Halo-64’s documented lesson that unloading the old map’s owned data must happen before freeing/reusing its backing allocation ([`HISTORY.md:724-729`](../../submodules/halo-64/port/n64/HISTORY.md#L724)). Halo-64 is evidence for lifecycle discipline only; its allocator and memory implementation are not transplanted to PS2.

## The `0x1ff` startup message

The interpreter log contains one `Address Error, addr=0x1ff [store]` at guest timestamp `1.6433`, followed by PCSX2’s BIOS thread-list pattern message and then `HALO_PS2_LOCAL machine entry` at `1.6445`. It precedes the HCU startup markers, memory-ready trace, lifecycle injections, and terminal marker. The paired recompiler log has no matching address/TLB fault line. This matches earlier exact-run audits that classify the same interpreter-only pre-machine-entry message as early BIOS/emulator noise, not as a post-marker guest exception ([`m2-final-guest-run-audit.md:49-53`](m2-final-guest-run-audit.md#L49)). Both current harness runs finish the guest lifecycle and their full 5-second post-marker windows without a searched guest-fault marker. Therefore this message does **not** block the lifecycle pass; reports should still call it out as pre-machine-entry emulator/BIOS noise, not say the complete raw log contains no address-error text.

## Ordinary production-profile overage is separate

The current ordinary probe [`build/hcu-parent-link-probe/result.json`](../../build/hcu-parent-link-probe/result.json) identifies gameplay ELF `147f386d9f34eb6b87254f83c124b4a73ad790855dc0219fe9ae868a1348e66d`. Its PT_LOAD file-backed size is `2,097,540` bytes against `2,097,152` bytes of `elf_static`, an overage of **388 bytes**, with zero undefined symbols; its overall link-probe acceptance remains false. Do not infer that it fits because the lifecycle profile fits.

By contrast, [`result-m2-ui-lifecycle.json`](../../build/hcu-parent-link-probe/result-m2-ui-lifecycle.json) binds the tested lifecycle image above to `1,889,156 / 2,097,152` PT_LOAD file bytes (zero overage) and zero undefined symbols. It is a distinct opt-in diagnostic profile with its own test-only loop and must not be described as the ordinary gameplay image. This distinction prevents either error: using a diagnostic fit to waive the ordinary-image 388-byte failure, or using that ordinary overage to invalidate already-passed lifecycle semantics.

## Completion recommendation

1. Mark the **UI lifecycle subcheck** complete for M2 Step 2: same-hash interpreter/recompiler, 5-second fault-free windows, physical layout, preservation/failure/retry, and two clean owner-release/reload cycles are all present.
2. If the numbered Group A Step 2 is defined to additionally require a current, budget-fitting **ordinary-profile** `m2-ui` run, keep the numbered item partial until the 388-byte production overage is addressed and that exact ordinary artifact is requalified. Existing older ordinary-profile UI evidence should remain identified by its own ELF hash, not silently promoted to the current `147f386d…` ELF.
3. Whichever way Step 2 is marked, do not advance to another step until its status in the plan is explicitly updated. Do not mark M2 complete: gameplay-map resident/collision working-set capacity, full gameplay load, and rendered-scene evidence remain separate unfinished requirements; a black or absent UI viewport is not a rendering pass.
