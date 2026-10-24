# M2 UI interpreter post-load fault audit

**Scope:** report-only audit of the interpreter run associated with the exact combined ELF SHA-256 `ff114d1d652588c2f71a42a6a09f5b8de944d9ba0afb3f1b3ee87f4f783ec7a9`. This does not diagnose the independent gameplay-map capacity gate and does not claim a rendered scene.

## Finding

The guest does reach `m2-ui-map-loaded`; roughly 0.26 seconds later the interpreter halts in Halo CE's script-node datum lookup while executing the `ring_loop` script. The strongest source-level defect candidate is the safety validator's treatment of an invalid non-`NONE` expression root as valid: `hs_root_type_valid` returns true when `hs_syntax_try_get` returns `NULL`. That permits a malformed/out-of-range root to pass the validator and later reach runtime `datum_get`, which asserts when the index is outside the data array's live count or its datum header is unused. This is a concrete validation hole consistent with the observed assertion, but the evidence does not yet establish whether the offending map datum was malformed at source, byte-swapped incorrectly, or corrupted during tag loading.

The logged datum `0x01ffe4f0` has absolute-index low 16 bits `0xe4f0` (58,608), outside the documented 19,001-node syntax array. A hypothetical byte swap would produce `0xe4f001ff`, whose low 16 bits are `0x01ff` (511), a plausible in-range index. This makes byte order a high-value diagnostic hypothesis—not a proven fix. The two preceding unaligned address errors (`0x7d2dc6` and `0x7d2dca`) are additional evidence of invalid/misaligned state and must be explained before accepting a script-only workaround.

## Guest evidence and boundary

The run report records interpreter mode, exact ELF hash above, successful `m1-ui-map-loaded` boundary, `reached_game_initialize_done: true`, then `status: failed` with `halt ... weapon (0x0), deleted unexpectedly`; `launcher.log` establishes the more specific sequence:

1. UI preflight reads HMAP (72 B), CTAG (1,547,396 B), CRNG (2,900 B), CBIX (44 B), and B000 (2,288 B).
2. `HALO_PS2_LOCAL m2-ui-map-loaded` appears at approximately 30.925 s.
3. At 31.1848 s PCSX2 reports unaligned stores/loads at `0x7d2dc6` and `0x7d2dca`.
4. At 31.1852 s CE asserts `script node index #58608 (0x1ffe4f0) is unused or changed` at `memory/data.c:412`; at 31.1856 s it stops `ring_loop` for a corrupt syntax tree and halts.

The exact evidence is in `build/hcu-ps2-closure/emulator-m1-interpreter-32107ad0c18a4e4780ac3218ce3ef15e/result.json` and the corresponding `launcher.log` (particularly lines 320–399). The “map-loaded” marker means the UI map load boundary passed; it does not mean CE script state remained valid or that a scene rendered. PCSX2's reported success marker is only the requested stage marker, not process health after that boundary.

## Source trace and likely validation gap

- `source/hs/hs.c:12806-12833` validates the syntax-data extent, cache containment, alignment, data-array signature, count bounds, and string data. It validates header/extent properties, not every persisted script root's datum index.
- `source/hs/hs.c:12865-12872` makes `hs_syntax_try_get` return `NULL` when the expression's absolute index is at least `hs_syntax_data->count`, otherwise delegating to `datum_try_and_get`.
- `source/hs/hs.c:13026-13033` (`hs_root_type_valid`, immediately before the cited `hs_expression_refusal`) returns `!root || root->type == type`. Thus a non-`NONE` root whose index is invalid yields `root == NULL` and is treated as valid rather than refused. This contradicts the safety contract in the comment at `source/hs/hs.c:13024-13025`, which says “No root is of any type.”
- `source/hs/hs.c:13115-13137` runs that check over scenario script/global roots. Later, `source/hs/hs.c:13158-13170` marks a script disabled only after the overall scan finds a refusal or duplicate link. The `NULL` root being treated as acceptable means this path may never set the disabled bit for the bad root.
- `source/hs/hs_runtime.c:844-860` starts non-static/non-stub scripts when their disabled bit is clear. Runtime then uses `hs_syntax_get`/`datum_get`; `source/memory/data.c:145-200` confirms an invalid or unused index asserts. This explains why a malformed root can survive load-time checks and fail only after the marker.
- `source/hs/hs_scenario_definitions.c:281-311` byte-swaps the data-array header and all syntax nodes, with a special magic-header branch swapping `0x4000` nodes and the ordinary branch swapping the actual node count. The observed index pattern warrants verifying which branch runs and the actual byte order of `hs_script.root_expression_index` and syntax-node links. Do not simply add a second byte swap: tags may already have passed through the map converter's byte-order transformation.
- `source/hs/hs.c:13260-13328` contains the PS2 allocation/validation fallback and calls scenario postprocess/runtime initialization. Its comments promise damaged script data will not run scripts, so the root-validation hole is especially important to test against that intended behavior.

## Smallest safe diagnostic/fix experiment

Run this as an isolated HCU-only experiment on a temporary branch or disposable worktree; preserve the existing shared worktree and exact failing binary as controls.

1. First add diagnostics only (no endian or runtime-semantic changes). Just before `hs_scenario_functions_check`, print map/scenario identity, syntax-array address/size/signature/count/record size, `hs_scripts.count`, and for each invalid root its script name/index/type plus both the raw root index and `DATUM_INDEX_TO_ABSOLUTE_INDEX(root)`. For a small set of those roots, print raw bytes for the root field, the syntax-array header, and the target node's `datum_header`, `next_node_index`, and `data`. Also report which `hs_syntax_data_byte_swap` branch ran. Bound all loops and output; avoid per-node logging.
2. Change only the validator predicate in the experiment: a `NONE` root remains permitted where retail CE semantics allow it; otherwise require `root != NULL && root->type == type`. For globals/scripts, decide and encode separately if a `NONE` root has a legal role; do not conflate `NONE` with out-of-range.
3. Build a new combined ELF, record its full source/submodule pins and SHA-256, and run the same PCSX2 interpreter scenario. The intended safe outcome for a bad script is a specific pre-runtime refusal/disabled script with no datum assert. Check whether `ring_loop` is disabled, whether any next script fails, and whether CE state remains alive past the original crash point. Do not call this M2 map acceptance or rendering.
4. If diagnostics show a consistent byte-order inversion (e.g. original index `0x01ffe4f0` becomes valid `0xe4f001ff` only after exactly one conversion, and the same relation holds for root/link fields across a retail sample), then test a narrowly scoped byte-order correction in the cache/tag materialization path. Re-run the validator and compare known Xbox/CE syntax records before and after; never “fix” by swapping arbitrary indices in runtime, because datum identifiers and absolute indices are a single packed datum value and all persisted links must stay coherent.
5. Independently investigate `0x7d2dc6`/`0x7d2dca`: capture PCSX2 EE PC/backtrace or instrument the relevant tag/script access to identify the store/load site. The proposed invalid-root check may avoid the crashing script but does not explain or repair earlier misaligned accesses.

The minimal source-level correction is therefore the invalid-root acceptance predicate, but only diagnostic evidence should determine whether to land it and whether the upstream data needs a byte-order fix. A host unit test should cover `NONE`, in-range-valid, out-of-range, and in-range-unused-ID roots; then the guest regression should show the same behavior without changing accepted valid roots.

## Not the gameplay-map capacity issue

This failure occurs after loading the small UI map's CTAG (about 1.55 MB) and B000 data, at the HaloScript runtime boundary. It does not exercise a campaign/multiplayer map's BSP payload, gameplay-map service policy, candidate non-UI map working set, or the large-map CTAG staging limits. Those remain separate M2 blockers. Fixing or bypassing this script assertion cannot demonstrate that a gameplay map fits the PS2 arenas, that its collision/BSP loads, or that rendering works. Conversely, the large-map capacity concern cannot explain the logged out-of-range `script node` datum without additional evidence of memory overwrite.

## Confidence and open questions

- **High confidence:** the immediate reported assert is CE `datum_get` rejecting a script-node datum; the run is not a successful post-marker guest run.
- **High confidence:** `hs_root_type_valid` treats a missing node as valid, and the source has a runtime route that starts scripts not marked disabled.
- **Medium confidence:** the out-of-range value is caused by endian conversion or the map/tag load path. The bit pattern is suggestive, but there is no raw on-disc/on-guest field comparison yet.
- **Unresolved:** origin of the two unaligned accesses; whether the invalid index is a script root, a node edge reached during `ring_loop`, or a node index transformed by compilation/postprocessing; whether source-level player weapon deletion is a separate cascade or an independent fault.

## Source references

- [`hs.c`](../../submodules/halo-ce-universal/source/hs/hs.c:12806) — PS2 syntax data validation, invalid-index helper, script-function validation, allocator fallback, map init.
- [`hs_scenario_definitions.c`](../../submodules/halo-ce-universal/source/hs/hs_scenario_definitions.c:281) — syntax-data byte-swap branch logic.
- [`hs_runtime.c`](../../submodules/halo-ce-universal/source/hs/hs_runtime.c:844) — scenario script thread startup and disabled-script check.
- [`data.c`](../../submodules/halo-ce-universal/source/memory/data.c:145) — `datum_get` bounds/identifier validation and assertion.
- [`result.json`](../../build/hcu-ps2-closure/emulator-m1-interpreter-32107ad0c18a4e4780ac3218ce3ef15e/result.json) and [`launcher.log`](../../build/hcu-ps2-closure/emulator-m1-interpreter-32107ad0c18a4e4780ac3218ce3ef15e/launcher.log:320) — exact guest run result and timeline (build artifacts are local evidence, not source-controlled deliverables).
