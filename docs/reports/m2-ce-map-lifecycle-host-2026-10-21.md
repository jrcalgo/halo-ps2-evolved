# M2 CE scenario/service lifecycle host fixture — 2026-10-21

## Result

The focused native host ILP32 fixture passed:

```sh
PYTHONPATH=. python3 -m pytest -q tests/test_hcu_ce_map_lifecycle.py -x
```

Result: **1 passed** (run outside the sandbox because sandboxed i386 execution is blocked by SIGSYS). The test links the actual CE `scenario_load()` and `scenario_unload()` from `source/scenario/scenario.c`, the actual CE `cache_files.c` included by the harness, real CE tag schema validation, HCU PS2 cache/CTAG/CBSP adapters, the parent `hcu_map_service`, package mount/source readers, and halo-ps2 HP2 section/file readers. The test asserts the required entry points are live in the retained link map ([`tests/test_hcu_ce_map_lifecycle.py:61-94`](../../tests/test_hcu_ce_map_lifecycle.py#L61), harness [`tests/hcu_ce_map_lifecycle_main.c:122-210`](../../tests/hcu_ce_map_lifecycle_main.c#L122)).

## Exercised transition

1. First load explicitly calls `ps2_cache_preflight_map("levels\\ui\\ui")`, then the real CE `cache_files_give_time_to_precache()` path starts the registered parent loader. Once the owner is mounted but before scenario publication, the harness changes only the final relocation word in the retained CTAG payload to an aligned out-of-image field and calls real CE `scenario_tags_load()`. The exact `cache_file_read(NONE, tag_data_offset, tag_data_size, physical_tag_cache, &read_complete, TRUE)` path reaches `ps2_ctag_materialize()`, which rejects before copying; CE returns `NONE`, leaves `tags_loaded`, `tag_header`, global tag instances, and tag count unpublished, and the entire destination remains CE's `0xCD` poison. The parent mount and `.map` source remain active. Restoring the original relocation permits a successful same-mount `scenario_tags_load()` retry; `scenario_tags_unload()` then clears those globals before the fixture proceeds to full scenario loading. The output marker is `ce-lifecycle invalid final CTAG relocation unpublished; same-mount retry passed`.
2. The real CE `cache_files_give_time_to_precache()` path observes ready, then real `scenario_load()` loads 983 CE tag instances and publishes scenario, selected BSP, collision BSP, and BSP3D pointers from the retail UI package.
3. While the CE globals and parent owner are live, a same-map preflight sets `reload_pending`. The harness asserts scenario/BSP pointers and parent arena usage remain unchanged.
4. Real `scenario_unload()` is called. Linker wrapping instruments the exact `ps2_cache_release_map_owner()` call and asserts at that boundary that CE scenario/BSP/collision/BSP3D/game-global pointers and indices are already cleared, CE tag publication is false, the global tag instance table/count are unpublished, and `cache_file_globals.tag_header == NULL`. Only then does the real parent owner release run.
5. Before the deferred post-unload loader runs, the test makes the first HP2 header read return one genuine byte and the next read return EOF. The parent preflight rejects HMAP, does not mount/publish CTAG, clears staged/reload state, returns owner usage to zero, and leaves the source descriptor closed. CE has no scenario/tag globals published.
6. A fresh explicit preflight followed by CE precache and real `scenario_load()` succeeds in the same process. Final `scenario_unload()` releases a second time; the wrapper confirms two ordered CE-to-parent releases total.

The guest code uses a 16 MiB test tag-cache array, 8 MiB test BSP-cache array, 16 MiB parent map arena, 128 KiB visitor scratch, and 4 MiB validator claims array inherited from the BSP transaction fixture. These are host fixture capacities—not PS2 budget proof, target placement, or endorsed pool sizes. The new invalid-relocation case is a *pre-copy atomic rejection*: it proves the current whole-buffer materializer leaves its exact CE destination untouched except for CE's own poison fill. It does not simulate a transport error after partial streamed writes to the final destination; the streamed CTAG implementation does not exist yet. The fixture also does not test CE schema/BSP failure rollback, late resource EOF, physical FileXio, PCSX2 fault injection, or visible rendering. The normal CE validator reports nonfatal correction notices for absent Xbox vertex/index buffers; the actual schema validation and scenario/BSP load still succeed.

## Artifact identity

Retained under `build/m2-ce-map-lifecycle-host/`:

| Artifact | SHA-256 |
|---|---|
| ILP32 fixture ELF (late relocation rejection + retry) | `b0c78f83217de8bd02896cf11d63b24ecb6e2d1c3a956e0eb1f176bb2e463bfc` |
| linker map | `3cdb5bcf43bf51a18d0475d5dc1d8dcf43461404e3db00b9f64978de0a5e7cb9` |
| runtime log | `342b33a064811f4ce906241fd86594dba04586855a1eee67deaa6ff22905bb74` |
| manifest | `76e7bb0173d897217d4ae3176e67c39e728690711b1dc3be583d65e49c789e89` |
| UI HP2 | `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90` |
| decompressed UI map | `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e` |

Source HEAD pins recorded by the manifest: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`; halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The source worktrees were dirty; ELF/link-map hashes bind this exact host fixture, and the manifest explicitly marks the pins as dirty-worktree identities.

## Interpretation

This closes two specific host evidence gaps within the composed CE/parent fixture: (a) a late CTAG relocation rejection through real CE `scenario_tags_load()` after mount but before publication, with a same-owner correction/retry; and (b) real CE `scenario_load`/`scenario_unload` composed with the parent UI owner through same-map preflight, post-unload transport failure, and same-process recovery. The direct CE callback path validates before copying today, so the injected invalid relocation confirms `0xCD` remains in the cache and no CE globals publish. This strengthens M2 Step 9 but does **not** close its full L0–L6/failure matrix, does not test a partial streamed write, does not qualify the PS2's 32 MiB gameplay live set, does not admit any gameplay map, and does not close M2. The production catalog remains UI-only until the Longest streamed CTAG/CBSP and whole-machine ownership work described in [`m2-capacity-next-slice-2026-10-21.md`](m2-capacity-next-slice-2026-10-21.md) passes. PCSX2 and physical FileXio/OPL remain separate acceptance tiers.

## Source references

- PS2 stale cache-header pointer clear: [`cache_files.c:652-656`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L652)
- Fixture's pre-release and post-unload null-pointer assertions: [`hcu_ce_map_lifecycle_main.c:24-35`](../../tests/hcu_ce_map_lifecycle_main.c#L24), [`hcu_ce_map_lifecycle_main.c:210-224`](../../tests/hcu_ce_map_lifecycle_main.c#L210)

- CE scenario load and publication: [`scenario.c:1230-1247`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230)
- CE scenario unpublication before parent owner release: [`scenario.c:370-403`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370)
- CE precache callback: [`cache_files.c:1164-1210`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1164)
- CE tag-read-before-publication boundary: [`cache_files.c:1262-1314`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1262)
- HCU whole-buffer CTAG validation/materialization and fail-closed completion: [`ps2_cache.c:375-415`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375), [`ps2_ctag.c:208-263`](../../submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c#L208)
- Parent deferred loader and failure cleanup: [`hcu_map_service.c:95-150`](../../src/stream/hcu_map_service.c#L95)
- Parent same-map preflight state: [`hcu_map_service.c:245-275`](../../src/stream/hcu_map_service.c#L245)
- Comparative method only: [Halo-64 render/lifecycle notes](../../submodules/halo-64/port/n64/NOTES.md#L33); no N64 memory or feature cuts are adopted.
