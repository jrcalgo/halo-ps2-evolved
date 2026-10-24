# Conflict log (Round 2+)

Round 2 corroboration (2026-10-20): all **17** reports reviewed peer digest; **no new conflict IDs**. **C1–C5** positions unchanged — unanimous on policy direction (HCU sim, CTAG partitions, staged M1 I/O, NOTES seam, arena routing); open items are integrator sequencing and measurement, not contradictory facts.

| ID | Topic | Positions | Owner reports | Resolution |
|---|---|---|---|---|
| C1 | Tag store shape | 2 MiB contiguous cache vs CTAG+HP2 partitions | m2_tag_format, m2_arena, m0_memory | **Resolved (R3):** CTAG v1 + partitioned owners; bootstrap 2 MiB not retail store — [indepth_milestones_plan.md](indepth_milestones_plan.md) |
| C2 | Production collision path | HCU physics only vs parent world play | m3_collision (retry: ledger + parity checklist), m0_runtime | **Resolved (R3):** HCU-only; parent/world.elf fixtures until §6 parity — same |
| C3 | Boot ordering | Fix stubs before vs with M2 loader | m1_platform (retry: §4 precache R4 cluster), m1_startup, m2_loader | **Resolved (R3):** M1 cache/I/O + boot gate first; guest map load = M2 exit — same |
| C4 | Presentation seam | Empty render stubs vs NOTES tick hooks | m1_platform (retry: §5, 187 render), m3_snapshot | **Resolved (R3):** bounded adapter + M3 snapshot consume — same |
| C5 | BSS deployment | Logical regions vs single `.bss` block | m0_memory, m0_link | **Resolved (R3):** route via parent arenas; re-audit after glue — same |
