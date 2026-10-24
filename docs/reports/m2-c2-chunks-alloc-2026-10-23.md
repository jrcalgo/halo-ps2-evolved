# M2 C2 lane chunks-alloc: C2.4 and C2.5 evidence (2026-10-23)

Scope: requirements C2.4 (bounded chunks, pin/lease/evict) and C2.5 (post-load allocation audit). Both remain **partial**. Evidence is host execution plus EE cross-compile; there is no device or workload run.

## C2.4: residency with pin, lease and gameplay counts

Added to `src/stream/hcu_asset_profile.{c,h}`:

- `hcu_asset_residency` table with caller-supplied entries. Each resident chunk has three independent counts: CE `pin_count`, DMA/GS `lease_count`, and `gameplay_refs`.
- `pin` verifies and copies a chunk with `hcu_asset_profile_read_chunk` (segment and logical SHA-256). A repeat pin only increments the count. A failed pin changes no resident state.
- `evict` refuses with `HCU_ASSET_PROFILE_E_BUSY` while any count is nonzero, and returns the storage only on success. Refusals and evictions are counted.
- Unpin, release-lease and gameplay-ref decrement refuse underflow.
- New error codes: `HCU_ASSET_PROFILE_E_BUSY = -7`, `HCU_ASSET_PROFILE_E_STATE = -8`.

Driver `tests/hcu_asset_residency_main.c` with pytest `tests/test_hcu_asset_residency.py`, run on real HCP2 packages from `build/m2-c2-hcp2-primary`:

- `bots-bloodgulch.hcp`, profile 3. Pins CE `1:0` (4,767,713 B) and SOUND_META `3:0` (50,496 B). For each: double pin, lease, gameplay ref, then refused evict, unpin, refused evict, release lease, refused evict, drop gameplay ref, evict, re-pin, SHA-256 compared to the package's own logical digest (matches), and evict again.
- Driver output: `PIN 1:0 bytes=4767713 sha256=f4d58290c9a9c8a0b7af8d88e63229eac693008f62f5cb87a6969c753e6ee38d high_water=4767713`, `PIN 3:0 bytes=50496 sha256=e79723fb83bf1c5c3ceb9c37a1d3e81ded985968f82ccbbca8507cb2876065fb high_water=4767713`, `REFUSED 6 evictions 4 verify_failures 0`.
- A corrupted copy is rejected at preflight (`FAIL preflight rc=-5`) with no pin output.
- Result: `11 passed` across the residency and existing asset-profile tests.

Remaining C2.4 gaps (why this is partial):

1. The residency unit is the whole logical chunk. The CE chunk is 4.77 MB, far above the 64 KiB decoded-chunk target. The HCP2 package is segmented on disk, but the decoded residency is not. The requirement is not met.
2. The table is not wired into CE gameplay pointers or the live DMA/GS path. No caller in `src/` or `source/` uses it yet, and the existing bitmap lease path is separate.
3. Pin-time verification failure (preflight passes but a later read fails) is not directly tested. Only preflight rejection is covered.
4. No partition or budget is assigned. Storage is caller-supplied and is not charged against the 27,787,264-byte committed limit.

## C2.5: post-load allocation audit and compat allocator

Compat allocator, `submodules/halo-ce-universal/port/ps2/src/ps2_memory.c`:

- Always-on counters: `sdk_malloc_preactivation_calls`, `sdk_realloc_fallbacks`, `sdk_free_fallbacks`, `malloc_refused_unbound`, exposed by `physical_memory_get_malloc_fallback_counters()`.
- Before activation, `__real_malloc` is still used, and only for blocks that predate arena activation. After `physical_memory_free`, allocation returns NULL and is now counted. Post-activation realloc and free of non-arena (pre-activation SDK) blocks use the SDK path for correctness and are counted as fallbacks.
- Realloc copy and failure semantics are unchanged. A failed realloc keeps the original block (covered by the existing diagnostic driver).

Endless-play churn, `tests/hcu_ps2_malloc_endless_main.c` with `tools/test_hcu_ps2_malloc_endless.py`, against the real `ps2_memory.c` on host:

- Output: `ps2-malloc-endless ops=2000000 allocs=785655 frees=785426 reallocs=336483 failures=0 fragmentation_failures=0 realloc_failures_preserved=0 largest_after_drain=1048560 sdk_fallbacks=0`.
- Content is checked on realloc and periodically across all live blocks. Live bytes are capped at half the 1 MiB arena by test policy. After a full drain, a request of capacity minus one header succeeds, which shows full coalescing.
- The existing diagnostic driver (`tools/test_hcu_ps2_malloc_diagnostic.py`) still passes.

Call-site classification, `docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json`:

- Each of the 211 callsites now has `enclosing_function`, `phase_classification`, `phase_basis` and `phase_confidence`. Counts: load-or-init 151, post-load-candidate 22, unknown 38.
- Labels come from static name heuristics (for example `lru_new` may run after load). They are not a workload trace, and `phase_confidence` is `low`.
- Zero callsites were moved to preallocated or scoped storage. No site has been proven recurrent, so no move was justified.

Remaining C2.5 gaps:

- No runtime phase trace. Recurrent path, bot, renderer, wave and mode allocations are not proven and not moved.
- The CE game-state and nested object pools have no free path for endless play. This lane did not change them.
- The endless churn covers only the compat arena, not CE game-state or pool churn.

## Build and check evidence

- `python3 -I -m pytest -q tests/test_hcu_asset_residency.py tests/test_hcu_asset_profile_chunks.py tests/test_hcu_asset_profile_hcp2.py tests/test_hcu_asset_profiles.py`: 11 passed.
- `python3 -I tools/test_hcu_ps2_malloc_diagnostic.py`: passes.
- `python3 -I tools/test_hcu_ps2_malloc_endless.py`: passes.
- EE cross-compile with `build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-gcc` (exit 0): `ps2_memory.c` (with `HALO_PS2_STEP8_MEMORY_DIAGNOSTIC=1`), `hcu_asset_profile.c`, `sha256.c`. Objects are in `build/m2-c2-chunks-alloc/`.
- `git diff --check` is clean in the parent repo (for the touched files) and in `submodules/halo-ce-universal` (`port/ps2/src/ps2_memory.c`).

## Process gap

The required reading list (about 344 KB across the submodule docs) was not read in full before starting. I started from the status JSON, the C2.4 and C2.5 reports, and the code. I have not read the docs listed in the task, and this lane's conclusions do not depend on them.

## Not changed

- `docs/reports/m2-c2-status-2026-10-23.json`, `plans/*.md` and the canonical closure ledger were not edited.
- The 27,787,264-byte committed limit and the 5,767,168-byte reserve were not changed.
- Scratch outputs are in `build/m2-c2-chunks-alloc/`. No C1 artifact directories were touched.
