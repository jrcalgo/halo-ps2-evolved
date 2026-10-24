# Round 2 peer digest

One-paragraph summaries for corroboration (Round 2 **complete** — see each report `## Corroboration`). Evidence baseline: parent `a2575e9`, HCU `c406a414`, ELF `e45b4719…`.

## M0

- **m0_link_closure:** 345 compile, 0 link undefined; narrow stub rule passes on rooted closure; `result.json` gate still open; 562 extern stubs; doc drift vs live counts.
- **m0_memory_ledger:** 10,126,828 B allocated; logical v2 ledger reconciles; `ps2_memory.o` contiguous BSS; not parent boot arenas; `audio` exactly full; grouped owners need semantic sign-off.
- **m0_runtime_ownership:** HCU owns identity/collision; hybrid snapshot consumer on halo-ps2; retire parent `src/game` sim paths and `world.elf` collision as production authority.

## M1

- **m1_abi:** Host ILP32 OK; `ps2_abi.c` locks key datums; nested combat/DMA types incomplete; double-helper gate open.
- **m1_pad:** Four-port XInput adapter linked; **`ps2_input_publish_state` unwired** from parent `pad_poll_players`.
- **m1_platform_callsite:** Round 1 retry — **562** stubs (93 service / 282 excluded / 187 render); **R4×40** incl. all 13 cache symbols; **Appendix A** per-symbol tiers; CE `source_references` scan caveat; **`SKIP`** (`CreateDirectoryA`, XInput quad) not in 562; M3 cluster = render global + 187 stubs.
- **m1_startup:** Chain to `scenario_tags_load` (`ui` then `b30`); **`custom_maps` / CreateDirectoryA** named blocker; cache I/O follows.
- **m1_dma:** Round 1 retry — four-layer DMA taxonomy, full CE datum/matrix inventory, parent chain align rules, master table (DMA vs repack-only); aligns with ABI gaps (`arming_time`, block refs); snapshot in `frame_scratch`.

## M2

- **m2_tag_format:** **CTAG v1** — reloc table + materialized EE pointers; not offset-only HCU refactor.
- **m2_map_conversion:** Triple HP2 packs; stripped model pools; tag structs still 3.9–11 MiB; separate CE tag image needed.
- **m2_loader_failure:** HP2 L1 today; layered L0–L6 fail-closed; pointer contract before converter claims.
- **m2_arena_capacity:** Retail tags exceed 2 MiB cap; bitmap/sound are stream totals; partition + measure overlap.

## M3

- **m3_object_lifecycle:** HCU full lifecycle; parent table animation-only; need post-tick snapshot.
- **m3_player_movement:** Parent `move`/`pill` fixtures vs CE `game_tick` + input bridge gap.
- **m3_collision:** Round 1 retry — CE `collisions.c`/`collision_bsp.c` as sole production owner; retirement ledger for `collide.c`/`pill.c`/`collpack.c` + consumers; 16-row parity checklist; `world.elf` HP2 packs stay fixtures until gates.
- **m3_snapshot_render:** Snapshot unbuilt; CE couples render tick; NOTES seam + 187 render stubs.
- **m3_first_person_pose:** CE sim vs parent `play_fp` wraps; snapshot + fpview consume-only target.

## Conflict candidates (resolved in Round 3 — see [indepth_milestones_plan.md](indepth_milestones_plan.md))

1. **Tag residency:** Single 2 MiB array vs CTAG + partitioned regions (`m2_tag_format`, `m2_arena_capacity`, `m0_memory_ledger`).
2. **Collision at runtime:** `halo-local.elf` HCU physics vs `world.elf` collpack (`m3_collision`, `m0_runtime_ownership`).
3. **M1 boot vs M2 load:** Platform cache/file stubs block menu before tag image exists (`m1_platform_callsite`, `m1_startup`, `m2_loader_failure`).
4. **Render vs sim:** `render_frame_pregame` / 187 stubs vs NOTES state-advancing hooks (`m1_platform_callsite`, `m3_snapshot_render`).
5. **Memory accounting:** Logical v2 ledger vs contiguous `ps2_memory.o` vs `game_state_malloc` pools (`m0_memory_ledger`, `m2_arena_capacity`).
