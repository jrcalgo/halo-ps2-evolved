# M2 Step 2 lifecycle-image footprint audit (2026-10-21)

## Scope and conclusion

This is a report-only audit of the ordinary combined diagnostic profile and the opt-in M2 UI-lifecycle fault profile. It does not change budgets, remove test assertions, or qualify either ELF. Both images fail the fixed static-image boundary. The current lifecycle ELF is **3,716 bytes over** `elf_static` and its calculated minimum boot allocation crosses the protected reserve by **4,150 bytes**. The ordinary profile is closer, but still fails by **388 bytes** and crosses the reserve by **822 bytes**. Therefore the lifecycle profile needs a net reduction of at least 3,717 file bytes from its current output, including enough additional savings to bring the ordinary/common image under the boundary; merely removing lifecycle-only code would leave the ordinary profile failing.

The lifecycle-specific code is precisely identifiable in the HCU rooted-object symbol diff. It consists of the opt-in CE test sequence, CE unload trace, and parent-side one-shot fault hooks. The remaining delta between ELF LOAD growth and those source-object deltas includes link-time section placement/alignment and LTO output; it must be remeasured from the next exact paired build rather than attributed by subtraction to a presumed source file.

## Exact artifacts and profile comparison

Inputs are the checked-in source pins recorded in both probe reports: halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and memory map SHA-256 `1dff9c71e47d0f988c6765bf6559ee9dc67d3e3c012779414a4881ee84504ad0`. The parent and HCU worktrees are dirty; the saved object hashes are therefore essential parts of the identity. The lifecycle closure's rooted-object SHA-256 is `9228fd45686aaaf3218adfdf74f6ec32b062646f725a18a070e68da24c3f441c`; ordinary is `9640620fcf5eb19b625ffb835ee5e8af73bfc41300543d75f0b268425894f0b3`.

| Measure | Ordinary profile | M2 UI lifecycle profile | Change |
|---|---:|---:|---:|
| ELF SHA-256 | `1e0684f35d3cd447b2adc0b229abb0a0347b9b9604549fe6b6d78f3566a00879` | `ad2df862790d2753cec9af25ce56dc21f050858a7669d290e699760d77b360a1` | distinct artifacts |
| LOAD `p_filesz` | 2,097,540 B | 2,100,868 B | +3,328 B |
| `elf_static` capacity | 2,097,152 B | 2,097,152 B | unchanged |
| File-backed overage | 388 B | 3,716 B | +3,328 B |
| LOAD memory including BSS | 4,214,436 B | 4,217,788 B | +3,352 B |
| BSS | 2,116,772 B | 2,116,796 B | +24 B |
| Minimum reserve headroom | −822 B | −4,150 B | −3,328 B |
| Probe acceptance | false | false | neither accepted |

The report files are `build/hcu-parent-link-probe/result.json` and `result-m2-ui-lifecycle.json`; link maps are `hcu-gameplay-machine.map` and `hcu-gameplay-machine-m2-ui-lifecycle.map`. Their map SHA-256 values are respectively `42378ceef29d5d940891de9cbc4b4a47f4b9f9014c67bc889f913c96357bee7c` and `11e19bd77c751773cc76b902ff33d148f06cd5087faa73f5a0aec281b9afa896`. The lifecycle result says no guest execution was observed for this image. `tools/hcu_parent_link_probe.py` calculates `p_filesz`, obtains `_fbss`/`_end`, computes boot backing plus guard slack, and explicitly treats the result as a lower bound that excludes allocator metadata (`tools/hcu_parent_link_probe.py:98-140`, `:308-321`). It marks an ELF over `elf_static` diagnostic-only (`:323-331`). The negative headroom is thus a necessary-condition failure, not a measured successful EE boot placement.

## Attributed contributors

The paired `nm -S` diff of the final ELFs isolates these text symbols as lifecycle-profile additions/growth:

| Symbol | Ordinary | Lifecycle | Growth | Source owner / role |
|---|---:|---:|---:|---|
| `main_loop` | 5,180 B | 6,100 B | +920 B | HCU `source/main/main.c`; runs the test-only lifecycle script |
| `scenario_unload` | 208 B | 368 B | +160 B | HCU `source/scenario/scenario.c`; records CE-unpublished and owner-released trace points |
| `hcu_map_service_preflight` | 1,252 B | 1,340 B | +88 B | Parent `src/stream/hcu_map_service.c`; adds a test fault branch |
| `hcu_map_service_lifecycle_trace` | absent | 172 B | +172 B | Parent; validates/reports trace state |
| `hcu_map_service_lifecycle_consume_deferred_failure` | absent | 232 B | +232 B | Parent; injects/consumes post-unload one-shot refusal |
| `hcu_map_service_lifecycle_arm_deferred_failure_once` | absent | 16 B | +16 B | Parent; arms deferred failure |
| `hcu_map_service_lifecycle_fail_preflight_once` | absent | 16 B | +16 B | Parent; arms preflight refusal |
| `game_map_loaded` | absent | 16 B | +16 B | HCU; lifecycle initial-state gate |
| `main_menu_unload` | absent | 44 B | +44 B | HCU; repeats ordinary menu unload/load path |

The final ELF's changed text symbol sizes total **1,664 B**; the final LOAD `.text` section grows **1,728 B**, leaving 64 B in placement/alignment effects. HCU `rooted.o` section totals are `.text` +1,140 B, `.rodata` +1,176 B, with no BSS delta. The source-object detail is independently reproducible from the closure reports: under the lifecycle define, `source/main/main.c` grows from 23,748 to 24,668 text bytes and from 3,242 to 4,186 rodata bytes; `source/scenario/scenario.c` grows from 16,696 to 16,856 text bytes and from 1,762 to 1,994 rodata bytes. Their exact source-level increases are 1,080 text and 1,176 rodata bytes. CE test blocks and diagnostic strings are at `submodules/halo-ce-universal/source/main/main.c:409-420` and `:3470-3567`, and `source/scenario/scenario.c:200-205` and `:390-411`.

The parent `hcu_map_service.o` comparison is also direct: ordinary versus lifecycle changes include `.text.hcu_map_service_preflight` +88 B, lifecycle hook text +436 B, lifecycle strings/preflight literals +187 B, and lifecycle BSS +12 B. The source-controlled behavior is in `src/stream/hcu_map_service.c:421-465` and `:490-570`. The lifecycle macro is intentionally applied only to the relevant HCU CE source files in `tools/hcu_ps2_closure.py:336-360`; the parent make rule similarly gates it to `hcu_map_service.c` (`tools/ee-world.mk:150-159`).

There are two cautionary accounting details:

1. The LOAD file-image delta is +3,328 B, while LOAD memory grows +3,352 B. The 24-B net BSS increase is only part of this: the lifecycle profile also has a different layout/alignment footprint. Do not treat `p_filesz` as a proxy for BSS/boot-backing size.
2. The two paired result records contain differing hashes for 41 of 42 ordinary parent objects, even though they name the same parent/HCU/halo-ps2 commits. The parent worktree is dirty, and the two profiles were not produced from byte-identical parent object sets. Consequently the 3,328-B final ELF delta is an exact artifact comparison but not a clean experiment assigning every delta byte to the lifecycle define. The `hcu_map_service.o` difference and HCU rooted-object/symbol differences are attributable; a follow-up must rebuild both profiles from one frozen worktree/source manifest to finish causal attribution. The relevant per-object hashes are preserved in each result JSON.

## Footprint reduction candidates, ordered by safety

1. **Build a controlled paired profile from one frozen source state.** Record the exact dirty-tree diff or source manifest, toolchain SHA/version, compiler flags, parent-object hashes, root hash, both link maps, and both ELF hashes. The lifecycle optimization experiment must change only the lifecycle profile; otherwise a size delta is not causally interpretable. Ensure both result JSONs include the same physical-placement calculation.
2. **Try test-profile-only `-Oz` on the opt-in orchestration units.** The current closure reports show both profiles use `-Os` (`tools/hcu_ps2_closure.py:137-145`); the lifecycle profile additionally defines `HALO_PS2_M2_UI_LIFECYCLE_TEST` only for `source/main/main.c` and `source/scenario/scenario.c` (`:336-360`). The Step 2 log records a previous whole-profile `-Oz` build with the *same* 2,100,868-B `p_filesz` and −4,150-B headroom, so repeating a global `-Oz` build is not justified. A targeted `-Oz` for only those two lifecycle CE units and parent `hcu_map_service.c` remains a distinct experiment: it is a compiler choice, not a logic deletion, and cannot change production-profile code if its flag is gated only on the test profile. Compare symbol and map footprints, then rerun host lifecycle tests and the exact PCSX2 interpreter/recompiler lifecycle test. Since ordinary already overruns by 388 B, either the test profile also needs at least 388 B of common-profile savings or the production/common build must be independently reduced and remeasured.
3. **If optimization alone is insufficient, reduce diagnostic representation, not assertions.** `main_loop` currently embeds the full sequence and numerous long `printf` failure/trace messages (`main.c:3481-3565`). Preserve every state predicate, fault arm/consume, retry, and unload/reload operation. Consider keeping machine-readable stable event tokens/reason IDs while removing repeated explanatory suffixes/format payloads, updating the parser in the same change. Do not drop checks for scenario/BSP publication, cache owner, tag/BSP bases/capacities, or the two-cycle retry.
4. **Avoid removing code that improves assurance.** The code exercises a pre-unload refusal while preserving live UI state; then unloads, injects a deferred refusal, checks safe-empty CE and owner state, retries the load; then performs repeated unload/load cycles. Those assertions are the substance of Step 2 evidence and should remain. The live CE unpublish-before-release trace in `scenario_unload()` is specifically guarding the CTAG pointer lifetime boundary (`scenario.c:380-411`).
5. **Do not borrow Halo-64's feature cuts or simulation throttling to save this image.** Halo-64 is a useful comparison for identifying platform glue and for its explicit distinction between simulation and rendering state, not authority to remove CE local-game lifecycle behavior; its N64 constraints differ from the PS2 memory/CPU envelope. See `submodules/halo-64/port/n64/NOTES.md:33` and keep this diagnostic reduction test-only.

## Next falsifiable build/guest gate

After choosing a source-backed reduction, rebuild both `--no-bootstrap-memory` profiles at the same parent/HCU/halo-ps2 source state. The ordinary image must have zero `elf_static` overage and nonnegative minimum reserve headroom. The lifecycle image must also have zero overage and **strictly positive measured headroom after allocator metadata and actual boot pointer are included**; the current probe headroom excludes allocator metadata, so `p_filesz` under the limit alone is not sufficient. Reconcile `bss` to the assigned region and keep the reserve intact. Then run the exact lifecycle ELF in both PCSX2 interpreter and recompiler through the failure markers, retry, and repeat cycles; hash the ELF, ISO, settings, logs, and result manifests. Any changed optimization/profile requires fresh guest runs. Do not claim Step 2 complete from host tests or a link-only size reduction.

Budget ownership remains as configured; `config/hcu-ps2-memory-map.json:10-25` assigns the file-backed image to `elf_static` and CE/HCU/PS2 runtime state to `resident_gameplay`. Changing those capacities, consuming the reserve, or counting BSS as file-backed bytes would not solve this issue.
