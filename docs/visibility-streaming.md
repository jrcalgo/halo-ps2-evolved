# M11 visibility, residency and streaming

M11 is **incomplete and in progress**. Host topology/visibility comparisons and one fixed EE/GS culling comparison pass. Async staging, cancellation/unload, GPU cache churn and total committed-memory qualification remain open. M12 has not started.

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

## Remaining M11 gates

- Extend EE comparison beyond this fixed camera, including portal crossings and the map perimeter.
- Audit resource-key namespaces and submitted/uploading texture lifetimes; force cache churn and prove no stale textures.
- Add fixed-capacity staging/read requests with explicit ownership, completion and map generations. Current `stream/file.c` performs blocking reads; async streaming is not implemented.
- Drain/cancel requests and GPU references before releasing map storage. Implement and test repeated unload/reload.
- Stress delayed reads, exhausted staging, upload limits and failed loads on host and EE.
- Measure all committed EE regions without double counting and preserve the reserve. The 4,034-byte host visibility measurement is not total EE memory accounting.

The M10 report is historical evidence at completion commit `d5a5c23`; its strict current-source qualifier will intentionally reject later M11 source/runner changes. Reproduce M10 from that frozen revision when needed. Do not overwrite its accepted ELF/report to make a later revision appear identical. Close M11 only through the governing plan's milestone procedure, then make its dedicated completion commit.

## Bounded staging lifecycle checkpoint

`src/stream/staging.{h,c}` adds a portable, fixed four-slot owner-thread state machine backed by caller-provided storage. Requests carry a map identifier and a non-repeating 64-bit ticket; ticket exhaustion rejects further work rather than wrapping. No request performs heap allocation. High-water accounting counts the full stride of each occupied slot, including cancelled work awaiting acknowledgement.

Queued and ready requests can be cancelled immediately. Reading requests retain their buffers until the worker reports completion; acquired buffers retain theirs until the consumer releases them. A map is drained only after both kinds of ownership end. Short/failed reads discard the request. Duplicate, stale and out-of-order operations fail without transitioning another request. Workers must return completion messages to the owner thread; these functions are deliberately not thread-safe. A consumer must release only after its final use (including any DMA use) ends. This module does not supply a GPU fence.

`python3 -m unittest discover -s tests -p test_staging.py -v` passes the compiled C lifecycle regression: full-pool rejection, oversize rejection, delayed cancellation, held-buffer cancellation, ready/queued cancellation, map isolation, slot reuse, stale completion, short/failed reads, duplicate operations and serial exhaustion. Four 256-byte fixture slots reach exactly 1,024 bytes high-water. This is synthetic host evidence, not an EE streaming allocation measurement.

Next: integrate an actual EE read worker and bounded completion transport; reserve aligned production storage/worker stack inside the streaming budget; connect stable map/resource keys and upload lifetimes; then exercise cancellation and unload/reload in the visible viewer. The current world viewer still uses blocking reads and does not link this module. M11 remains incomplete.

Checkpoint validation: all 40 project host tests and 12 upstream synthetic suites pass natively. The restricted first run failed two existing ILP32 executions with SIGSYS; the permitted unrestricted rerun passed. Container and EE validation of this new module have not run.

## EE worker handoff checkpoint

`src/stream/reader_ee.{h,c}` now supplies a PS2SDK thread backend with a single active read and four bounded request descriptors. The owner dispatches a mailbox through a wake semaphore; the worker performs `file_read_at` and signals completion. `reader_pump` polls completion without waiting for a read, then publishes it through the staging state machine. Paths are copied into fixed descriptors; offsets, lengths and path capacity are checked. Cancellation never overwrites an active descriptor. Shutdown refuses active reads and acquired buffers; it terminates the idle worker only after all slots drain. The caller supplies storage and an aligned stack of at least 16 KiB, both of which must remain live until successful shutdown. Main-thread scheduling must allow the worker to run; this API does not create an IOP service or make the blocking file backend itself asynchronous.

A pthread/semaphore kernel shim executes the actual worker source with a deterministic held read. The test cancels that map while the read is outstanding, queues another map, verifies buffer contents after completion, and verifies drain/shutdown refusal until consumer release. Both staging tests pass with C warnings as errors. This establishes host handoff behavior, not PS2SDK runtime equivalence or GPU-fence correctness.

`python3 tools/build_streaming.py` cross-compiles both worker and lifecycle objects with the installed R5900 compiler and PS2SDK headers (`-D_EE`, warnings as errors). Source hashes and compiler identity are retained in `build/streaming-ee/result.json`. The first ad-hoc command omitted `_EE`; the checked-in command includes the SDK-required definition and passes. No viewer ELF links these objects yet. Next work is viewer integration and visible EE diagnostics, production streaming-budget reservation, bounded failure/status reporting, repeated unload/reload, and cache/GPU lifetime integration. M11 remains incomplete.

Validation after the worker addition: all 41 project host tests and 12 upstream synthetic converter suites pass natively. Container validation and EE runtime validation remain pending for this checkpoint.

## Visible EE streaming diagnostic

`WORLD_VARIANT=stream python3 tools/build_world.py` builds a separate `build/world-stream-elf/world.elf`. A parent-owned render hook executes worker lifecycle checks alongside the portal viewer; upstream sources remain pinned and unmodified. `python3 tools/run_world_viewer.py --variant stream --mode interpreter --objects` (or `recompiler`) stages a synthetic 256-byte fixture, launches visibly, and requires three successful cancellation/reload/content/drain cycles plus short-read rejection. The runner rejects missing success markers or a reservation above 1.5 MiB.

Two initial visible runs timed out: changing worker priority alone did not solve starvation. PS2SDK's `InitThread` sets the owner to priority 1. The diagnostic explicitly changes owner priority to 64, with the worker at 30, so the worker can execute and block on I/O while rendering continues. This scheduling policy is diagnostic-only and requires profiling before production adoption. A transient X11 window-enumeration failure was retried; its failed run is retained.

The diagnostic reserves 1,048,576 staging bytes, a 16,384-byte stack and 824 bytes of reader metadata (1,065,784 bytes total, excluding kernel thread/semaphore overhead). All four slots are occupied to prove exhaustion; cancelled active reads retain storage until completion. Each of three reload requests verifies all fixture bytes, then cancels while held and requires release before drain. An EOF-crossing request must be discarded; shutdown occurs only after all requests drain. This tests worker/map-ID lifecycle, not full `world_t` unload/reload, DMA ownership or texture-cache churn. The reservation is compiled static storage; whole-ELF and total committed-memory accounting remain open.

The recompiler run `world-stream-recompiler-e35d5c061b474c0eb3689c8b22affbaf` completed 181 frames with zero logged drops and all worker markers. The interpreter run and final runner qualification are recorded below. Native host validation remains 41 project tests plus 12 upstream synthetic suites passing.

Interpreter run `world-stream-interpreter-14fbe719829f4960917e9caf14e2115a` passes the explicit runner checks and completes 181 frames with zero logged drops; its final visible capture was inspected. Native/container allocatable ELF sections match (`build/streaming-ee/viewer-parity.json`). Diagnostic ELF SHA-256: `0cb8ce3c489c1b31b997b298dfb65843596659116d0778f25ef1f7ff94ecda1c`. These short emulator checks do not establish real-console performance. The subsequent qualified recompiler run is `world-stream-recompiler-9c2f7919a37f4679b7379d0d97ec5d67`; its result also records the synthetic fixture hash. Captures and failed attempts remain private in `build/emulator/runs/`.

## Texture namespace and submission lifetime audit

The current renderer assigns contiguous cache keys: world textures `[0,T)`, lightmap pages `[T,T+L)`, and object textures `[T+L,T+L+O)`, where `T=s_src.texture_count`, `L=s_page_slots` and `O=obj_src->texture_count`. `tc_acquire` rejects keys outside its configured (capacity-clamped) range. These identifiers are stable within the loaded world; they are not map-generation tickets. `bsp_render_set_world` and `bsp_render_set_object_pass` initialize the cache, so future map switches must drain rendering before calling them and must invalidate prior-map handles.

For the existing synchronous renderer, frame N preparation overlaps drawing N-1. Entries touched in either frame cannot be LRU victims. Before the next kick, `main.c` calls `bsp_render_wait_gpu` and then `video_wait_gpu`; the latter uses `draw_wait_finish`, so the 40 ms polling timeout alone is not treated as a completion fence. The kick submits texture transfers on GIF and waits for DMA before VIF draw submission. Texture source bytes remain in the loaded world arena; the synthetic async reader does not feed them. This source audit explains the present two-frame protection, but does not establish safety for future async texture buffers or complete map teardown.

The audit found an actual failure-path defect: a partial pixel/CLUT chain could leave a cache claim resident after upload construction failed. Local fork `f322272` adds transactional `gs_upload_pair`, restores the chain cursor/overflow on either failure, and cancels only the newly allocated, unsubmitted cache claim. Earlier chain packets remain intact; the unreachable tail is ignored. Cancellation retains the frame's budget charge and does not count as an LRU eviction. `tc_cancel_claim` is explicitly forbidden on hits or submitted resources; it is not a GPU fence or general eviction API.

`tests/upload_transaction.c` compiles the actual upload, chain and cache implementations and checks every pair-capacity boundary (including partial first/second transfers), prefix preservation, invalid CLUT length, pre-existing overflow, claim release and retry. Native suites pass 42 project tests and 12 upstream synthetic suites. This tests packet construction failure, not a real GS queue overflow. The dependency gitlink, local bare fork, private recovery bundle and lock now track the fix; no external push occurred.

After this fix, visible recompiler run `world-stream-recompiler-28052d349e4844dba8926daaf2deaf3a` passes all three synthetic worker cycles and completes 181 frames with zero logged drops; its final capture was inspected. Native/container allocated ELF sections agree (`build/streaming-ee/upload-viewer-parity.json`). The visible run is a normal-path smoke check; upload overflow is deliberately exercised by the host regression rather than claimed from this run. The earlier interpreter diagnostic belongs to the previous fork revision; it was not rerun for this fix.
