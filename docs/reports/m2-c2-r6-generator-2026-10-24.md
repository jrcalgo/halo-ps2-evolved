# M2 C2 r6 generator evidence: residency span and renderer residuals (2026-10-24)

Lane: generator (C2.1/C2.2 consistency). Owned files: `tools/audit_hcu_c2_partition_budget.py`,
`tests/test_hcu_c2_budget_partition.py`, and the generated outputs under
`build/m2-c2-partition-2026-10-23/` (also mirrored to `build/m2-c2-r6-generator/`).

## Changed files

- `tools/audit_hcu_c2_partition_budget.py`
  - New constants: `RESIDENCY_BYTES = 16 * 65536` (1,048,576) and `RESIDENCY_SEGMENT_BYTES = 65536`.
  - `render = MAP_RENDER_BYTES - map_parent - GUARD - RESIDENCY_BYTES`. The map parent already includes the
    tag/BSP guard, so the render span is the texture parent minus the map/render guard and the residency span.
    Every row's render bytes drop by 1,048,592 against the old formula, as the r5 lane recorded.
  - Every row carries `residency_bytes` (1,048,576) and `residency_guard_bytes` (16).
  - `fits_guarded_map_render_backing` now checks `map_parent + render + GUARD + residency == 10 MiB`.
  - `render_residual_matches_capacity_report` now checks `render + GUARD + residency == capacity residual`.
  - The `.inc` writer emits the four-field profile row (`tag, bsp, render, residency`) in the exact layout of
    `src/stream/hcu_memory_profile.c`.
  - Renderer residuals: `render - 5,632 (BSP_RENDER_WORKSPACE_BYTES) - 139,264 (HCU_RENDER_TEXTURE_RESERVED_BYTES)`,
    with `texture_cache_pages_available = residual // 8192` (`TC_PAGE_BYTES`).
  - Page-need columns (see the limitation below): `package_media_bytes`, `texture_pages_needed_upper_bound`,
    `texture_pages_short_of_upper_bound`, and an audit-level `texture_pages` summary.
- `tests/test_hcu_c2_budget_partition.py`
  - Existing tests now pass (they were failing 2 of 4 with `KeyError: 'residency_bytes'`).
  - New `test_inc_is_byte_identical_to_c_rows`: the generated `.inc` equals the rows between
    `hcu_partition_table_v2[] = {` and `};` in `src/stream/hcu_memory_profile.c`, byte for byte.
  - New `test_renderer_residual_and_page_flags_are_consistent`: residual, pages, guard, and page-flag consistency
    for all 27 rows, and `ui` has no package media.

No EE source, C source, or ledger was edited. `src/stream/hcu_memory_profile.c` already held the reduced rows, and the
generator now reproduces them exactly.

## Results

Commands, from the repository root:

```
python3 -I tools/audit_hcu_c2_partition_budget.py --out build/m2-c2-partition-2026-10-23
python3 -I tools/audit_hcu_c2_partition_budget.py --out build/m2-c2-r6-generator
python3 -I -m pytest -q tests/test_hcu_c2_budget_partition.py
cc -std=gnu99 -Wall -Wextra -Isrc -Itests/hcu_ps2_memory_shim \
   -Isubmodules/halo-ce-universal/port/ps2/include -Isubmodules/halo-ps2/engine/src \
   tests/hcu_mp_partition_table_main.c src/stream/hcu_memory_profile.c \
   submodules/halo-ps2/engine/src/core/mem.c -o build/m2-c2-r6-generator/host/hcu_mp_partition_table_main
build/m2-c2-r6-generator/host/hcu_mp_partition_table_main
```

- Generator: `committed_pass: true`, committed 27,787,264 bytes, 27 of 27 rows fill the 10 MiB backing and fit
  resident gameplay.
- `pytest tests/test_hcu_c2_budget_partition.py`: `6 passed in 0.42s`.
- C table test: `partition-table-v2 rows=27 failures=0`, exit 0.
- `.inc` vs the C rows: identical (`diff` empty, and the byte-identity test passes).
- `git diff --check` is not applicable to the two files, which are untracked. A trailing-whitespace grep and
  `py_compile` are clean on both.
- No EE object was touched, so no cross-compile was run.

### Renderer residuals (smallest rows)

| profile | render bytes | residual after 5,632 + 139,264 | texture pages available |
|---|---:|---:|---:|
| sidewinder_marine_shotgun_4p4bot | 529,472 | 384,576 | 46 |
| sidewinder_mounted_gunner_4p4bot | 2,748,464 | 2,603,568 | 317 |
| putput_marine_shotgun_4p4bot | 1,011,856 | 866,960 | 105 |
| bloodgulch_marine_shotgun_4p4bot | 1,119,072 | 974,176 | 118 |

No row has a negative residual. The smallest render margin is sidewinder marine, as the task stated.
`ui` has 1,037 pages available.

## Page need: estimate not available from the inputs

The task asks to flag rows where pages available are below the pages the profile's packages need, estimating
pages as `ceil(bitmap texture bytes / 8192)`. The inputs do not provide bitmap texture bytes:

- `docs/reports/m2-c2-r3-selected-packages-2026-10-23.json` stores only `media_bytes_independent` per package
  (all independently addressable media, sounds included). The session profiles and the memory audit have no
  bitmap-only or texture-byte field either (searched all numeric keys).
- The r3 package list has 26 packages. `ui` has none.

So the generator reports an upper bound, `ceil(media_bytes_independent / 8192)`, which is not a bitmap estimate
and not a working set. Under that bound, all 26 package rows are flagged as short (for example, beavercreek marine
has 210 pages available against a bound of 2,524). Those flags do not show a shortfall, because whole-package media is
not what a map needs resident at once. `ui` has no package bound, so its flag is `null`. The audit output carries
this in `texture_pages.note`.

The page check therefore remains **open**. It needs a per-package bitmap working-set figure (texture bytes the
renderer keeps resident across a frame) from the r3 producer or the session capacity matrix. With that input,
`texture_pages_short_of_upper_bound` becomes the real shortfall flag, and the generator needs only the field name
change.

## Changed-output and cross-lane notes

- `config/memory-budget.json` is unchanged. The r5 note asked it to carry the 1 MiB residency span and the
  16-byte guard. Its regions still sum to the committed budget, and the residency span sits inside `current_bsp`
  plus `texture_cache`, so no region change is needed. That should be confirmed by the budget lane.
- The r5 note that the 16-slot count is a fallback still applies. This lane only encodes it.
- The `OUT` default of the generator is still `build/m2-c2-r2-budget`. The lane's outputs were written with `--out`.

## Verdict

- Generator consistency with `src/stream/hcu_memory_profile.c` (residency span, reduced render bytes, guards,
  `.inc` byte identity, renderer residuals): **pass**, with the tests and the C table test above.
- Page-need check for each profile's packages: **partial**. Flags are computed, but only from a whole-media upper
  bound that does not establish a shortfall. The bitmap working-set input is missing for all 26 packages, and
  `ui` has no package at all.
