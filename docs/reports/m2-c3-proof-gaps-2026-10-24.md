# C3.10 / C3.11 renderer proof gaps — 2026-10-24

This is a source and runner audit for the two existing C3 render packages. It is not a qualification result. The governing scope is [C2 items 7–8 and their C3.10/C3.11 carry-over](../../plans/7.hcu-remake-m2-m4.md#c2--establish-bounded-storage-and-production-ownership): C3.10 needs guest evidence with actual geometry and upload chains in flight; C3.11 needs renderer-aware map replacement while the old renderer has live DMA/GS readers. C2 headless replacement results do not cover that scope.

## What the current source and checker establish

- The renderer binds two geometry chains and two upload chains into the 1,179,648-byte parent DMA span. The host layout is deterministic (two 32,768-QW geometry chains followed by two 4,096-QW upload chains), and DMA telemetry reports combined capacity/used/high-water/failure/reset counters for geometry and uploads.
- The renderer tracks VIF1 and GS FINISH observations independently internally; a kick is retired only after both are seen. bsp_render_wait_gpu() polls these signals. The C3 frame log reports aggregate last-frame geometry/upload bytes, upload count, overflow, kick sequence, and a combined fence query.
- The successor runner added in ba07ec1 can render both maps, capture before/after, and check candidate-validation, quiesce, dispose, and surviving-map usability markers. de9031d adds the candidate marker before quiesce. The checker deliberately returns c3_11_qualified: false and says actual in-flight uploads/draw source references and both emulator modes on the exact tuple still need verification.
- Teardown source calls renderer wait, DMA wait, requires the drain predicate, detaches bitmap frame hooks, clears the world, unbinds the BSP reader, then clears media. CE successor code preflights before disposal; mode 2 checks old-owner/map state and renders ticks on the old map; mode 3 checks empty state after the injected load failure and retries. These are code paths and machine-checkable markers, not proof that an emulator observed live DMA/GS reads at those boundaries.

## Unproven requirements

| Requirement | Existing observable data | Missing evidence / limit |
|---|---|---|
| C3.10: actual VIF and GS fences during live rendering | Per-kick fence API; final/periodic c3-frame has one combined fence value; teardown/quiesce log a combined fence | No guest artifact here records paired VIF-seen and GS-seen values/timestamps for a kick while its resources are held, nor demonstrates both signals pending and then complete under the tested workload. Per ADR-032, -1 is unknown/unobserved and must fail closed. |
| C3.10: all four DMA chains in use | Aggregate geometry and upload bytes, capacity, high-water, failures and resets; total chain layout is defined | No per-chain start/end physical addresses, spans, per-chain used QW/high-water, build/in-flight chain indices, or simultaneous proof that each of the two geometry and two upload chains carried packets. Aggregate nonzero counts cannot identify which chain was used. |
| C3.10: source/generation pins | Snapshot map generation and view-generation acceptance are logged separately; bitmap owner tracks its generation; media/world reader is registered | No frame/kick record joins map generation, snapshot slot/source spans, CE tag/BSP source pins and DMA chain addresses to the same outstanding kick, then shows those pins retained through both fence observations and released afterward. |
| C3.10: request/queue failure accounting | Renderer upload/geometry overflow and emit failures, bitmap request queue structures, and various C3 failure markers exist | No single guest result aggregates queue-full/request rejection, stale-generation, lease/dispatch, upload allocation, and per-chain DMA failure counters at frame end and replacement boundaries. Existing zero overflow/emit fields are not a proof that all bitmap queue failures were zero. |
| C3.11: validation before quiesce | map-replacement phase=candidate-validated and quiesce-begin/end; checker compares marker order and map identity | Marker order is an assertion over logs. It does not prove the candidate’s full package/metadata bytes or old renderer source readers were actually live at the moment of validation. |
| C3.11: old renderer is live and preserved on bad preflight | Checker requires an old-map reader count above zero at successful-mode quiesce; mode 2 rejects any candidate/quiesce markers and requires only the old map ready plus visible captures | The reader count is coarse BSP/world registration, not an in-flight per-chain source read. Mode 2’s current checks do not compare pre/post renderer kick/frame/generation identity or DMA owner counters; visible captures and old-map usable ticks are indirect. |
| C3.11: drain-before-dispose and release-after-tags-live | Checker requires quiesce-end drained=1 readers=0 between quiesce-begin and CE dispose; CE prints disposal/unload steps | No paired VIF/GS observations or source-pin list is tied to this exact boundary. The integration now requires bsp_render_fence_observed(kick) == 1; unknown/stale values fail closed. The map-service bitmap gate also refuses a sealed batch awaiting dispatch. These fixes still require guest proof. |
| C3.11: late failure reaches empty state then retry | Mode 3 emits empty/retry/load/usable markers and checker parses the successor lifecycle | Existing renderer-aware checker does not assert that the failed-load attempt had live old-map DMA/GS readers before teardown, or that the retried new renderer draws the requested frame count. Its map-ready/capture checks establish visible captures for old/new, not which exact attempt/frame generated each capture. |

There are older render-loop-only results under build/c3/render-loop/v1..v4, but no current rendered successor results under build/c3/replacement at audit time. Those render-only outputs do not qualify replacement. This report makes no claim that an emulator run passed or failed the new successor paths.

The fresh recompiler baseline at `build/c3/baseline-f6/recompiler/v1/manifest.json` ran ELF `13a18fead1206123ea5a61dec2d4ce45c82b3aad3c106aa9ad50ebe4a83e4670` from parent `f6d7038`, completing its release marker in 140.9 seconds. Its held capture (`capture-01-c3-render-held.png`, SHA-256 `6e2135f3a641e247946a57da14f8bcb82c69aac70f9832a77ce2ac71d2fcbff1`) contains sky and HUD, so it is rejected as scene evidence. The unit's Z rises by 6 units every 30 ticks; the camera follows. Its nonblack fraction is 0.200714, demonstrating why a brightness-only check cannot qualify rendering. The added scene-variation check rejects it (13 color buckets, nonflat fraction 0.00105). A textured scene and the actual cause of unit drift remain to be verified.

## Reproducible rendered-successor commands

Run from the repository root after the render package tree exists at build/c3/render-tree/pkg. These commands exercise both package directions and all three runner cases in both emulator modes. They are instructions only; this audit did not run them. The runner selects the old package with --rows, the successor with --successor, stages both package identities, links with C3 render defines, captures old/new frames, then validates the resulting guest markers.

```bash
set -e
for mode in interpreter recompiler; do
  for pair in \
    bloodgulch_mounted_gunner_4p4bot:beavercreek_mounted_gunner_4p4bot \
    beavercreek_mounted_gunner_4p4bot:bloodgulch_mounted_gunner_4p4bot; do
    old=${pair%%:*}
    new=${pair##*:}
    for fault in none preflight load; do
      python3 tools/c2_profile_boot_matrix.py \
        --c3 --rows "$old" --successor "$new" --successor-fault "$fault" \
        --render-views 4 --render-frames 300 --successor-ticks 30 \
        --c3-workload 4p4bot --emu-mode "$mode"
    done
  done
done
```

Interpret cases conservatively:

- none: successful foreign replacement; requires candidate validation, renderer quiescence, old disposal, new load, surviving-map ticks, and captures.
- preflight: malformed successor preflight; must show no quiesce and a still-usable old map. A fresh before/after renderer identity and owner-counter comparison is still required.
- load: late successor load failure; must show an empty released state and successful retry. The checker’s requested render frame count currently applies to the successor ELF/render loop budget, but replacement captures and explicit per-attempt frame coverage still need attribution.

A run is only admissible as an exact-tuple result when its generated result records the package/manifests, current parent and CE source revisions, linked ELF identity, PCSX2 executable/configuration, launch provenance, and both captures. To close the actual in-flight parts, add or collect the per-kick/per-chain and source-pin observations in the table above; a passing current checker alone cannot promote C3.10 or C3.11.

## Conservative status

**C3.10: open, guest-unproven.** Fixed DMA ownership/layout, source counters, snapshot generation checks, and host lifecycle tests are implementation evidence only. No evidence in this report proves all four chains were exercised with geometry/upload payloads while live, with source pins held across separately observed VIF and GS completion.

**C3.11: open, guest-unproven.** The current rendered-successor runner and source order make the lifecycle observable and check marker order, preservation, and retry behavior. They do not yet establish drain under an actually in-flight renderer, per-chain/map-source lifetime across the teardown boundary, or exact-tuple behavior in both emulator modes. Do not report either requirement as passed from source inspection or render-only captures.
