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
