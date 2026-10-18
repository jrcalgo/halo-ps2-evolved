# M11 visibility, residency and streaming

M11 is **incomplete and in progress**. Host topology/visibility comparisons, bounded worker lifecycle checks, transactional uploads, metadata churn, three repeated EE map unload/reload cycles, and a constrained-cache raw-frame comparison pass under PCSX2. The constrained-cache sweep also records 1,426 allocation failures; only its final sampled view is proven pixel-identical, so full route quality remains open. Broader EE routes, production async texture-buffer ownership, real hardware, and full committed-memory qualification remain open. M12 has not started.

## Topology and host visibility

`python3 tools/audit_visibility.py` compiles the real runtime BSP reader, camera, arena and visibility code with the host C compiler. Retail inputs and outputs remain private. `build/visibility/audit.json` indexes a uniquely retained run under `build/visibility/runs/`.

Blood Gulch has 30 clusters, 70 portals and 396 batches in one connected component. Checks cover batch ownership and cluster bounds, reciprocal portal membership, portal planes, and point-location on each portal's two sides. No topology errors were found. The initial 28-view comparison exposed two aerial-camera failures: a point-location leaf can extend outside the rendered geometry bounds. `src/world/visibility_portal.c` conservatively bypasses portal traversal outside those bounds, while preserving the explicit conservative debug flag.

The expanded audit uses 448 cameras: the 12 route keys, 16 ground views, and both sides of every portal at offsets 0.001, 0.05 and 0.5 world units. It independently rasterizes baseline and portal-selected geometry at 128x112 and compares both colour and inverse depth (depth tolerance 1e-6). Comparing colour alone can miss a wrong surface with the same shade; a synthetic regression covers that ambiguity.

The pre-fix boundary run differed in 141 views. At a doorway, a portal can be entirely inside the near clip plane; rejecting it hides the room beyond. Local halo-ps2 commit `71145ef` carries the parent window through portals within `near_z + EYE_EPS` instead of rejecting them. The corrected run has zero colour or depth differences across all 448 cameras; 436 exercise portal traversal. Visibility arena high-water is 4,034 host bytes. This is host evidence, not an EE memory or whole-route acceptance result. The failed boundary report is retained at `build/visibility/audit-before-near-plane.json`.

## Cache regressions

`tests/texture_residency.c` exercises the actual runtime cache implementation alongside the existing upstream invariants. The first request previously bypassed the frame budget. Upload-byte addition could also wrap, and frame-wrap comparisons could pin old entries indefinitely or choose the wrong LRU victim. Local halo-ps2 commit `ea4249c` rejects individually impossible requests, subtracts remaining budget before admitting uploads, and uses unsigned frame ages for pinning and LRU selection. Frame numbers must advance monotonically modulo uint32.

The pre-fix failure is retained in `build/visibility/cache-before.json`. Hard-cap, arithmetic-wrap, previous-frame protection, wrapped LRU, flush and existing cache-invariant tests now pass. This does not establish GPU fence safety under asynchronous streaming or texture churn. The renderer still uses its existing current/previous-frame lifetime scheme.

## Safe raw GS comparison

Build with `WORLD_VARIANT=portal python3 tools/build_world.py`; outputs are separate in `build/world-portal-elf/`. `WORLD_VARIANT=portal BUILD_ENV=container python3 tools/build_world.py` produces matching allocated ELF sections. M10's accepted ELF and its staged run copies are preserved.

The raw readback investigation found a separate SDK defect: `GS_PSM_16S` (10) fell through to a 32-bit DMA size, although the framebuffer buffer holds 16-bit pixels. SDK fork `4960c2e2` adds the 16S case to sizing and conversion. The world build compiles that pinned SDK source directly, resolving its symbols before the old installed debug archive; the rest of the installed SDK/toolchain is unchanged. Halo-ps2 fork `8dc5907` adds aligned pre/post guards to the readback buffer and verifies them through uncached aliases. Earlier unguarded diagnostic runs are retained but do not qualify this result.

Run the following with the visible project PCSX2 profile, once per CPU mode (`recompiler` and `interpreter`):

```sh
python3 tools/run_world_viewer.py --variant portal --mode recompiler --force-conservative --objects --framebuffer --camera 65 -80 9 -90 -5
python3 tools/run_world_viewer.py --variant portal --mode recompiler --objects --framebuffer --camera 65 -80 9 -90 -5
python3 tools/compare_visibility.py
```

The last command requires all four runs. It verifies current source/ELF/pack/configuration/CPU identities, completed readbacks and guards. At frame 120, all 458,752 raw PSMCT16S bytes match exactly between culling on/off **within each CPU mode**. BSP batches fall from 240 to 106; the portal run tests 83 portals, while the baseline tests none. This is a submission-count observation, not an FPS claim. All four viewers finish their 181-frame diagnostic.

Interpreter and recompiler baselines differ at 23 pixels. The same differences appear with culling enabled; they are not introduced by portal culling. The report records this explicitly and does not declare cross-mode bit equivalence or determine which CPU implementation matches hardware. Captured images were inspected; the raw decoder's images are private alongside each run. Broader EE camera/route comparisons remain open.

Current guarded ELF: `e002209c53d2a1f239cd1c3c3d50001c4837b83b70fc710d4835188b12219dfa`. Reports: `build/visibility/elf-parity.json` and `build/visibility/framebuffer-comparison.json`. Native and pinned-container suites pass 39 project tests plus 12 upstream synthetic converter suites.

## Map teardown and reload

The `stream` viewer now exercises the real renderer teardown path, not only synthetic reader cancellation. At diagnostic frames 60, 120, and 180 it waits for GS work, clears renderer references into the map arena, resets the arena, reloads Blood Gulch BSP and texture packs (and object pack sections), then reinitializes renderer state. The visible runner requires three success markers and verifies that each loaded-map arena usage returns to its initial baseline.

Both current CPU modes pass. Recompiler run `world-stream-recompiler-19e0f31875cf41e1b2b217c6e272cd7a` and interpreter run `world-stream-interpreter-63c0440bd32740f5a29eec8ab23fe02c` each report three cycles at 5,279,024 bytes versus a 5,279,024-byte baseline, then finish 361 frames and show Blood Gulch after reload. Captures and detailed logs are retained under each ignored run directory. The runs each log three dropped frames caused by synchronous teardown/reload; this is a lifecycle check, not a steady-state performance result. Interpreter final capture was visually inspected.

The first teardown attempt stalled because it consumed the GS FINISH event expected by the next presentation wait. The renderer now re-primes the completion handoff after world clear; the subsequent interpreter and recompiler runs both complete. This demonstrates repeatable same-map arena reclamation under PCSX2, not disc-backed switching between distinct worlds or real-console safety.

## Constrained-cache rendered eviction check

The diagnostic renderer accepts a cache-page limit and reports actual per-frame texture evictions. With a 96-page cap it sweeps 12 fixed Blood Gulch views over 360 frames, including the same three unload/reload events, and takes a guarded raw GS readback at frame 300. Each run is paired with an uncapped run using the same ELF, packs, CPU mode, camera sweep and capture frame. `tools/compare_cache_stress.py` checks those identities and configs, requires a clean profiler sample at frame 300, then compares all 512×448 pixels.

Recompiler baseline/stress runs are `world-stream-recompiler-d1ffeb27a25043afb487506756d8d48c` and `world-stream-recompiler-f25080c32b6548f3ab28d5b7724fc188`; report `build/streaming-ee/cache-stress-recompiler.json`. Interpreter baseline/stress runs are `world-stream-interpreter-063dd8547a774576b2ca77bf3545b631` and `world-stream-interpreter-225e0ae20b2047249fc2c399980d1536`; report `build/streaming-ee/cache-stress-interpreter.json`. Both capped runs record 9 actual evictions and 1,426 failed allocation attempts over the sweep, with no deferred uploads. At the sampled frame 300, the profiler reports zero failed/deferred requests and the raw image matches its uncapped counterpart exactly (zero differing pixels) within each CPU mode. The reviewed image shows the same Blood Gulch view.

The 1,426 failures are a material limitation: they occur during earlier points in the deliberately constrained sweep and can omit requested texture/lightmap work. Therefore this proves a real eviction occurred without stale/corrupt output at one clean sampled view, but it does not prove artifact-free presentation throughout the sweep or under ordinary cache capacity. A broader route must demonstrate sustained texture completeness under less destructive pressure before the M11 cache-eviction acceptance is closed. These PCSX2 results also do not prove physical PS2 behavior.

## Measured memory snapshot (partial)

For the current stream viewer ELF, allocatable ELF sections total 2,127,664 bytes, including `.bss` (which already contains the 1 MiB staging storage, worker stack, metadata, and other static state). The viewer reserves a 12 MiB world arena; the loaded Blood Gulch map and renderer use 5,279,024 bytes, return to that baseline after every reload, and report a 6,314 KiB high-water value. Separately allocated renderer DMA chains use 1,179,648 bytes (two 32,768-qword chains and two 4,096-qword upload buffers).

These figures are a partial snapshot, not total EE memory accounting: kernel/IOP overhead and other SDK/runtime allocations are not included. The measured DMA allocation also exceeds the initial `dma_commands` regional estimate of 1 MiB by 131,072 bytes. The stream staging area is part of ELF `.bss`, so adding its 1,048,576 bytes again to ELF static would double count it. The current budget remains a proposed partition; M11 memory acceptance stays open until all allocations are mapped to non-overlapping physical regions, including the measured DMA excess.

## Remaining M11 gates

- Extend EE comparison beyond this fixed camera, including portal crossings and the map perimeter.
- Extend rendered cache-churn checks beyond the current one-frame exact comparison. The capped sweep records real evictions but also allocation failures; verify texture completeness across multiple route views and tune pressure without masking misses.
- Integrate asynchronous texture-page reads and conversion with explicit ownership through DMA completion; current streaming worker exercises a synthetic byte fixture and the world pack loads remain synchronous.
- Extend EE visibility comparisons across portal crossings and map perimeter routes.
- Reconcile the measured DMA buffers with the 1 MiB regional estimate and map every EE, kernel, IOP, SDK and staging allocation to non-overlapping budget regions.
- Verify teardown/reload on physical PS2 hardware when available; current three-cycle evidence is PCSX2 only.
- Stress delayed reads, exhausted staging, upload limits and failed loads on host and EE.
- Measure all committed EE regions without double counting and preserve the reserve. The 4,034-byte host visibility measurement is not total EE memory accounting.

The M10 report is historical evidence at completion commit `d5a5c23`; its strict current-source qualifier will intentionally reject later M11 source/runner changes. Reproduce M10 from that frozen revision when needed. Do not overwrite its accepted ELF/report to make a later revision appear identical. Close M11 only through the governing plan's milestone procedure, then make its dedicated completion commit.

## Bounded staging lifecycle checkpoint

`src/stream/staging.{h,c}` adds a portable, fixed four-slot owner-thread state machine backed by caller-provided storage. Requests carry a map identifier and a non-repeating 64-bit ticket; ticket exhaustion rejects further work rather than wrapping. No request performs heap allocation. High-water accounting counts the full stride of each occupied slot, including cancelled work awaiting acknowledgement.

Queued and ready requests can be cancelled immediately. Reading requests retain their buffers until the worker reports completion; acquired buffers retain theirs until the consumer releases them. A map is drained only after both kinds of ownership end. Short/failed reads discard the request. Duplicate, stale and out-of-order operations fail without transitioning another request. Workers must return completion messages to the owner thread; these functions are deliberately not thread-safe. A consumer must release only after its final use (including any DMA use) ends. This module does not supply a GPU fence.

`python3 -m unittest discover -s tests -p test_staging.py -v` passes the compiled C lifecycle regression: full-pool rejection, oversize rejection, delayed cancellation, held-buffer cancellation, ready/queued cancellation, map isolation, slot reuse, stale completion, short/failed reads, duplicate operations and serial exhaustion. Four 256-byte fixture slots reach exactly 1,024 bytes high-water. This is synthetic host evidence, not an EE streaming allocation measurement.

At this checkpoint, the next work was to integrate an EE read worker and bounded completion transport. That work is recorded in the following checkpoints; the current remaining gaps are listed above. M11 remains incomplete.

Checkpoint validation: all 40 project host tests and 12 upstream synthetic suites pass natively. The restricted first run failed two existing ILP32 executions with SIGSYS; the permitted unrestricted rerun passed. Container and EE validation of this new module have not run.

## EE worker handoff checkpoint

`src/stream/reader_ee.{h,c}` now supplies a PS2SDK thread backend with a single active read and four bounded request descriptors. The owner dispatches a mailbox through a wake semaphore; the worker performs `file_read_at` and signals completion. `reader_pump` polls completion without waiting for a read, then publishes it through the staging state machine. Paths are copied into fixed descriptors; offsets, lengths and path capacity are checked. Cancellation never overwrites an active descriptor. Shutdown refuses active reads and acquired buffers; it terminates the idle worker only after all slots drain. The caller supplies storage and an aligned stack of at least 16 KiB, both of which must remain live until successful shutdown. Main-thread scheduling must allow the worker to run; this API does not create an IOP service or make the blocking file backend itself asynchronous.

A pthread/semaphore kernel shim executes the actual worker source with a deterministic held read. The test cancels that map while the read is outstanding, queues another map, verifies buffer contents after completion, and verifies drain/shutdown refusal until consumer release. Both staging tests pass with C warnings as errors. This establishes host handoff behavior, not PS2SDK runtime equivalence or GPU-fence correctness.

`python3 tools/build_streaming.py` cross-compiles both worker and lifecycle objects with the installed R5900 compiler and PS2SDK headers (`-D_EE`, warnings as errors). Source hashes and compiler identity are retained in `build/streaming-ee/result.json`. The first ad-hoc command omitted `_EE`; the checked-in command includes the SDK-required definition and passes. At this checkpoint no viewer ELF linked these objects. The subsequent visible integration and teardown evidence appears below; production texture-page ownership and cache/GPU lifetime remain open. M11 remains incomplete.

Validation after the worker addition: all 41 project host tests and 12 upstream synthetic converter suites pass natively. Container validation and EE runtime validation remain pending for this checkpoint.

## Visible EE streaming diagnostic

`WORLD_VARIANT=stream python3 tools/build_world.py` builds a separate `build/world-stream-elf/world.elf`. A parent-owned render hook executes worker lifecycle checks alongside the portal viewer; upstream sources remain pinned and unmodified. `python3 tools/run_world_viewer.py --variant stream --mode interpreter --objects` (or `recompiler`) stages a synthetic 256-byte fixture, launches visibly, and requires three successful cancellation/reload/content/drain cycles plus short-read rejection. The runner rejects missing success markers or a reservation above 1.5 MiB.

Two initial visible runs timed out: changing worker priority alone did not solve starvation. PS2SDK's `InitThread` sets the owner to priority 1. The diagnostic explicitly changes owner priority to 64, with the worker at 30, so the worker can execute and block on I/O while rendering continues. This scheduling policy is diagnostic-only and requires profiling before production adoption. A transient X11 window-enumeration failure was retried; its failed run is retained.

The diagnostic reserves 1,048,576 staging bytes, a 16,384-byte stack and 824 bytes of reader metadata (1,065,784 bytes total, excluding kernel thread/semaphore overhead). All four slots are occupied to prove exhaustion; cancelled active reads retain storage until completion. Each of three reload requests verifies all fixture bytes, then cancels while held and requires release before drain. An EOF-crossing request must be discarded; shutdown occurs only after all requests drain. At that checkpoint this tested worker/map-ID lifecycle, not full `world_t` teardown, DMA ownership or texture-cache churn. The later map teardown/reload evidence is recorded above. The reservation is compiled static storage and lies within ELF `.bss`; it must not be counted a second time in a total physical-memory sum.

The recompiler run `world-stream-recompiler-e35d5c061b474c0eb3689c8b22affbaf` completed 181 frames with zero logged drops and all worker markers. The interpreter run and final runner qualification are recorded below. Native host validation remains 41 project tests plus 12 upstream synthetic suites passing.

Interpreter run `world-stream-interpreter-14fbe719829f4960917e9caf14e2115a` passes the explicit runner checks and completes 181 frames with zero logged drops; its final visible capture was inspected. Native/container allocatable ELF sections match (`build/streaming-ee/viewer-parity.json`). Diagnostic ELF SHA-256: `0cb8ce3c489c1b31b997b298dfb65843596659116d0778f25ef1f7ff94ecda1c`. These short emulator checks do not establish real-console performance. The subsequent qualified recompiler run is `world-stream-recompiler-9c2f7919a37f4679b7379d0d97ec5d67`; its result also records the synthetic fixture hash. Captures and failed attempts remain private in `build/emulator/runs/`.

## Texture namespace and submission lifetime audit

The current renderer assigns contiguous cache keys: world textures `[0,T)`, lightmap pages `[T,T+L)`, and object textures `[T+L,T+L+O)`, where `T=s_src.texture_count`, `L=s_page_slots` and `O=obj_src->texture_count`. `tc_acquire` rejects keys outside its configured (capacity-clamped) range. These identifiers are stable within the loaded world; they are not map-generation tickets. `bsp_render_set_world` and `bsp_render_set_object_pass` initialize the cache, so future map switches must drain rendering before calling them and must invalidate prior-map handles.

For the existing synchronous renderer, frame N preparation overlaps drawing N-1. Entries touched in either frame cannot be LRU victims. Before the next kick, `main.c` calls `bsp_render_wait_gpu` and then `video_wait_gpu`; the latter uses `draw_wait_finish`, so the 40 ms polling timeout alone is not treated as a completion fence. The kick submits texture transfers on GIF and waits for DMA before VIF draw submission. Texture source bytes remain in the loaded world arena; the synthetic async reader does not feed them. This source audit explains the present two-frame protection, but does not establish safety for future async texture buffers or complete map teardown.

The audit found an actual failure-path defect: a partial pixel/CLUT chain could leave a cache claim resident after upload construction failed. Local fork `f322272` adds transactional `gs_upload_pair`, restores the chain cursor/overflow on either failure, and cancels only the newly allocated, unsubmitted cache claim. Earlier chain packets remain intact; the unreachable tail is ignored. Cancellation retains the frame's budget charge and does not count as an LRU eviction. `tc_cancel_claim` is explicitly forbidden on hits or submitted resources; it is not a GPU fence or general eviction API.

`tests/upload_transaction.c` compiles the actual upload, chain and cache implementations and checks every pair-capacity boundary (including partial first/second transfers), prefix preservation, invalid CLUT length, pre-existing overflow, claim release and retry. Native suites pass 42 project tests and 12 upstream synthetic suites. This tests packet construction failure, not a real GS queue overflow. The dependency gitlink, local bare fork, private recovery bundle and lock now track the fix; no external push occurred.

After this fix, visible recompiler run `world-stream-recompiler-28052d349e4844dba8926daaf2deaf3a` passes all three synthetic worker cycles and completes 181 frames with zero logged drops; its final capture was inspected. Native/container allocated ELF sections agree (`build/streaming-ee/upload-viewer-parity.json`). The visible run is a normal-path smoke check; upload overflow is deliberately exercised by the host regression rather than claimed from this run. The earlier interpreter diagnostic belongs to the previous fork revision; it was not rerun for this fix.

## Cache churn and pending upload ownership

The deterministic cache stress regression performs 200,000 acquire/hit/eviction/cancel operations across 64 stable keys, eight pages and eight CLUT slots, with wrap-safe frames and periodic whole-cache validation. It verifies every key-to-entry mapping, entry-to-page run, page owner and unique CLUT owner, then cancels pending claims and flushes. This is metadata/churn evidence; it does not render stale/corrupt texture pixels.

That stress test exposed a lifecycle hole in the first transactional rollback helper: `tc_cancel_claim` could not distinguish a new upload from an already-uploaded resident entry. Fork `8236f72` adds `pending_upload` state. New misses become pending; successful transactional pixel+CLUT chain construction calls `tc_commit_claim`; rollback cancels only pending claims. Attempts to cancel a committed hit do nothing. The upload budget remains charged conservatively after a failed construction. Both submodule commits (`f322272` transactional pair and `8236f72` pending state) are in the pinned local fork and its workspace-local recovery bundle.

Host tests now compile the actual cache, chain and upload code for all pair-capacity boundaries and the long deterministic churn sequence. R5900 cache/worker objects and the complete stream viewer rebuild pass. All project host tests plus upstream synthetic suites pass. Visible post-fix recompiler run `world-stream-recompiler-a67a31d59f4544069b345c4c6d731cdd` passes all three worker cycles and completes 181 frames with zero logged drops. The full native suite reports 43 project tests and 12 upstream synthetic suites passing. Full route churn, render-pixel integrity through eviction and unload/reload remain open.
