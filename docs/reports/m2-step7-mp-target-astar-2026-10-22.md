# Step 7/8 target-side CE A* probe on stock multiplayer BSPs

Date: 2026-10-22  
Scope: opt-in candidate-capacity diagnostic in PCSX2 recompiler. This is BSP path-search evidence, not playable-match, actor-steering, rendering, or physical-EE acceptance.

## Result

The same combined parent/HCU guest image loaded each of the 13 stock multiplayer maps through the existing Step 8 candidate map owner, ran CE's unchanged `path_input_new()` / `path_state_new()` / `path_state_find()` on one deterministic route per map, verified the goal is present in CE's path hash and its parent chain has strictly decreasing depth to the expected start surface, and unloaded the map with the existing query fixture. The current per-map route and memory results are retained in [`step7-path-validation.json`](../../build/hcu-ps2-closure/emulator-m1-recompiler-80c299fa2b81415889d742d698a8c116/step7-path-validation.json), SHA-256 `aa1a711dfef03de8e09d7f6337d25050eb949d2355501eb56978b254bbdad3e2`.

| Map | Surface route | CE nodes explored | Chain nodes | Allocator high-water / 2.5 MiB | Failed allocs |
|---|---:|---:|---:|---:|---:|
| Beaver Creek | 47 → 201 | 11 | 3 | 1,107,072 / 2,621,440 B | 0 |
| Blood Gulch | 101 → 108 | 6 | 3 | 1,191,728 / 2,621,440 B | 0 |
| Boarding Action | 393 → 486 | 5 | 3 | 1,276,384 / 2,621,440 B | 0 |
| Carousel | 17 → 74 | 13 | 5 | 1,361,072 / 2,621,440 B | 0 |
| Chill Out | 20 → 195 | 6 | 3 | 1,445,728 / 2,621,440 B | 0 |
| Damnation | 131 → 476 | 4 | 3 | 1,530,384 / 2,621,440 B | 0 |
| Hang ’em High | 39 → 65 | 9 | 3 | 1,615,040 / 2,621,440 B | 0 |
| Longest | 0 → 29 | 6 | 3 | 1,699,696 / 2,621,440 B | 0 |
| Prisoner | 0 → 94 | 7 | 3 | 1,784,352 / 2,621,440 B | 0 |
| Putput | 267 → 268 | 6 | 3 | 1,869,008 / 2,621,440 B | 0 |
| Rat Race | 0 → 33 | 4 | 3 | 1,953,664 / 2,621,440 B | 0 |
| Sidewinder | 69 → 121 | 10 | 3 | 2,038,320 / 2,621,440 B | 0 |
| Wizard | 25 → 46 | 11 | 3 | 2,122,976 / 2,621,440 B | 0 |

Every route row reports root equal to its requested start surface and `reached=1`; all 13 high-water values stay below the 2,621,440-byte configured dynamic-simulation allocator capacity, and all per-route allocation-failure counters remain zero. The CE `path_state` object is 82,060 bytes. The monotonic compatibility allocator consumes 82,176 bytes on most routes (82,208 for Carousel, which exercised more nodes); `free()` intentionally does not reclaim allocations inside the bounded arena, so the guest test measures cumulative map-loop demand, not a reusable per-tick allocator. The maximum observed high-water leaves 498,464 bytes in that arena for this diagnostic profile. It does not establish the capacity of a full match or AI population.

## Reproduction and source identity

Build the diagnostic image and run the validator (the latter needs access to the active desktop/display for PCSX2):

```sh
python3 tools/hcu_parent_link_probe.py --step8-mp-capacity-diagnostic
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_step7_path_guest.py --mode recompiler --timeout 600
```

Successful guest result: `build/hcu-ps2-closure/emulator-m1-recompiler-80c299fa2b81415889d742d698a8c116/result.json`, SHA-256 `3e118a0f693b0737aa20f781ad300ca8f2ce211f7f77115425e223a986628e42`; guest log SHA-256 `5ddc2b0bb5b4be8795fa5eadcc92cf69db42e41f0837257f14bf085177158fd1`; ELF SHA-256 `3f8efe1407f44a1f74d3a5f0d8c7c8941173d19f54ef17ffef258ce320ff93e3`. The run passed the 13-route validator, reached the capacity diagnostic completion marker, and emitted no `HALO_PS2_FAIL`. Source pins recorded by the boot runner: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b` (the HCU/parent worktrees contain uncommitted changes; the ELF hash binds the tested build). The boot-stage outcome remains `memory-placement-observed-not-playable`.

Relevant implementation/source references: the diagnostic route table, centroid bounds, bounded allocation, CE search and rooted-chain checks are in [`ps2_m2_ui_lifecycle_test.c:49-213`](../../submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c#L49). CE's API initialization and search are [`path.c:291-367`](../../submodules/halo-ce-universal/source/ai/path.c#L291) and [`path.c:1811-1838`](../../submodules/halo-ce-universal/source/ai/path.c#L1811); path-state layout/capacity are in [`path.h:25-145`](../../submodules/halo-ce-universal/source/ai/path.h#L25). PS2 allocator telemetry is [`ps2_memory.c:312-367`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L312), enabled for the separately compiled allocator by [`hcu_ps2_closure.py:538-553`](../../tools/hcu_ps2_closure.py#L538) and [`hcu_ps2_link.py:439-454`](../../tools/hcu_ps2_link.py#L439). The guest log validator enforces route coverage, exact endpoints, root identity, capacity, and no allocation failures in [`test_hcu_step7_path_guest.py:16-73`](../../tools/test_hcu_step7_path_guest.py#L16).

## Limits and remaining Step 7/8 work

This closes a previously missing *target-side CE A* BSP-consumer slice* across all stock multiplayer maps. It does not exercise actor bot goal selection, object-backed source/target identities, `path_state_build_path()` smoothing/obstacle avoidance, actor steering/progress, breakable-surface updates during live AI, concurrent bot workloads, full local/network co-op, gameplay frame cost, target BSP capacity under rendering, or actual PS2 hardware. `path_state_build_path()` is deliberately omitted because its avoidance stage requires a live source actor; this isolated diagnostic does not fabricate one. It also does not consume render textures, submit BSP geometry, or prove audio/presentation. Keep Steps 7 and 8 open.

Halo-64 retains AI pathfinding for its bots, but it provides no evidence for CE path output or EE capacity; its N64 cuts and sizing are not copied. REA was not needed for this source-extracted behavior and exact guest-run check; its MIPS decompiler limitations would not improve this call-path validation.
