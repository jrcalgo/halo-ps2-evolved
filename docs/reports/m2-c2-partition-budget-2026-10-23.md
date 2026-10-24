# M2 C2 partition lane: profile-v2 partition table and budget audit (2026-10-23)

Machine evidence: `docs/reports/m2-c2-partition-budget-2026-10-23.json`. Generated outputs are in `build/m2-c2-partition-2026-10-23/`.

## What changed
- `tools/audit_hcu_c2_partition_budget.py` (new): derives the guarded map/render partition for each measured case from the C2 capacity report and checks it against `config/memory-budget.json` and linked EE ELF LOAD segments.
- `src/stream/hcu_memory_profile.{c,h}`: a generated profile-v2 table (26 rows, each a v1 profile struct) and `hcu_memory_partition_select_v2(name)`, `_count_v2()`, `_entry_v2()`.
- `tests/hcu_mp_partition_table_main.c` (new): host check of the table. Rows are aligned, each fills the 10 MiB backing exactly, and names resolve.

## Partition rule (per row)
- `map_parent = tag_cache + 16 + structure_bsp` (both aligned to 16 bytes).
- `render_texture = 10,485,760 - map_parent`. This equals the capacity report's residual.
- `claims = ceil((tag+bsp)/32)*4`, charged to resident_gameplay. Its need is 3,424,256 (game state) + claims, which must fit the 6,815,744-byte resident region.

## Results
- Committed budget: 27,787,264 bytes committed, 5,767,168 reserve, total 33,554,432. PASS.
- Profiles: 26 of 26 fit the guarded backing and resident check.
- Smallest render margin: `sidewinder_marine_shotgun_4p4bot`, 1,578,064 bytes. Largest: `longest_mounted_gunner_4p4bot`, 5,530,320 bytes.
- Max claims scratch: 1,113,460 bytes (per-row values are in the JSON).
- ELF placement: LOAD highest guest byte exclusive is 0x4f9494 (step8 probe) and 0x5a14b4 (parent-link probe). Both are below the reserve start, 27,787,264 (0x1a80000).

## Not closed
- C2.3 accounting: the probe ELF MemSiz exceeds elf_static (2 MiB) plus streaming (1.5 MiB) by 496,788 bytes (step8) and 1,184,948 bytes (parent-link). This excess is not proven inside a named region, so committed-memory closure is open.
- Renderer indices, live set and workspaces are unmeasured, so the render margin is not a renderable-fit proof.
- Only 26 profiles are in the capacity matrix; the status file's 27th profile is not measured here.
- Startup does not call the selector yet. The call belongs in `src/stream/hcu_main.c`, outside this lane.
- ILP32 runner `tools/test_hcu_mp_production_bind_capacity.py` currently fails to compile because the submodule `port/ps2/src/ps2_memory.c` has uncommitted edits from another lane (undeclared `sdk_malloc_preactivation_calls`, `malloc_refused_unbound`).

## Cross-lane change requested
Before `hcu_memory_bind_profile_v1` in startup, select the explicit profile:
`const hcu_memory_profile_t *p = hcu_memory_partition_select_v2(profile_name); if (!p) return -1; hcu_memory_bind_profile_v1(&layout, p, &partition);`
