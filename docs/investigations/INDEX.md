# M0–M3 investigations index

Process: Round 1 independent reports → Round 2 corroboration → Round 3 integrator plan.

**Round 3 deliverable:** [indepth_milestones_plan.md](indepth_milestones_plan.md) (M0–M3 sequencing, **C1–C5** resolutions, implementation checklist).

**Final execution spec:** [final_milestone_plan.md](final_milestone_plan.md) (M0–M6, evidence pins, gate checklist).

| ID | Report | Milestone |
|---|---|---|
| m0_link_closure_auditor | [m0_link_closure_auditor.md](m0_link_closure_auditor.md) | M0 |
| m0_memory_ledger_auditor | [m0_memory_ledger_auditor.md](m0_memory_ledger_auditor.md) | M0 |
| m0_runtime_ownership_auditor | [m0_runtime_ownership_auditor.md](m0_runtime_ownership_auditor.md) | M0 |
| m1_abi_layout_auditor | [m1_abi_layout_auditor.md](m1_abi_layout_auditor.md) | M1 |
| m1_pad_multitap_auditor | [m1_pad_multitap_auditor.md](m1_pad_multitap_auditor.md) | M1 |
| m1_platform_callsite_auditor | [m1_platform_callsite_auditor.md](m1_platform_callsite_auditor.md) | M1 |
| m1_startup_guest_path_auditor | [m1_startup_guest_path_auditor.md](m1_startup_guest_path_auditor.md) | M1 |
| m1_dma_layout_auditor | [m1_dma_layout_auditor.md](m1_dma_layout_auditor.md) | M1 |
| m2_tag_image_format_investigator | [m2_tag_image_format_investigator.md](m2_tag_image_format_investigator.md) | M2 |
| m2_map_conversion_auditor | [m2_map_conversion_auditor.md](m2_map_conversion_auditor.md) | M2 |
| m2_loader_failure_auditor | [m2_loader_failure_auditor.md](m2_loader_failure_auditor.md) | M2 |
| m2_arena_capacity_auditor | [m2_arena_capacity_auditor.md](m2_arena_capacity_auditor.md) | M2 |
| m3_object_lifecycle_auditor | [m3_object_lifecycle_auditor.md](m3_object_lifecycle_auditor.md) | M3 |
| m3_player_movement_auditor | [m3_player_movement_auditor.md](m3_player_movement_auditor.md) | M3 |
| m3_collision_owner_auditor | [m3_collision_owner_auditor.md](m3_collision_owner_auditor.md) | M3 |
| m3_snapshot_render_auditor | [m3_snapshot_render_auditor.md](m3_snapshot_render_auditor.md) | M3 |
| m3_first_person_pose_auditor | [m3_first_person_pose_auditor.md](m3_first_person_pose_auditor.md) | M3 |

Contract: [_prompt_contract.md](_prompt_contract.md)

## Round 1 status

| Report | Status |
|---|---|
| m0_link_closure_auditor | done |
| m0_memory_ledger_auditor | done |
| m0_runtime_ownership_auditor | done |
| m1_abi_layout_auditor | done |
| m1_pad_multitap_auditor | done |
| m1_platform_callsite_auditor | done |
| m1_startup_guest_path_auditor | done |
| m1_dma_layout_auditor | done |
| m2_tag_image_format_investigator | done |
| m2_map_conversion_auditor | done |
| m2_loader_failure_auditor | done |
| m2_arena_capacity_auditor | done |
| m3_object_lifecycle_auditor | done |
| m3_player_movement_auditor | done |
| m3_collision_owner_auditor | done |
| m3_snapshot_render_auditor | done |
| m3_first_person_pose_auditor | done |

**17 / 17** Round-1 complete (2026-10-20). **17 / 17** Round-2 corroboration complete (2026-10-20). **Round 3 complete (2026-10-20):** [indepth_milestones_plan.md](indepth_milestones_plan.md); [_conflict_log.md](_conflict_log.md) **C1–C5** resolved. Peer summaries: [_peer_digest.md](_peer_digest.md). Consolidated plan: [final_milestone_plan.md](final_milestone_plan.md).

### Cross-links from completed reports (for pending peers)

- [m1_abi_layout_auditor](m1_abi_layout_auditor.md) defers CE gameplay DMA inventory to **m1_dma_layout_auditor** (nested-field gaps listed there).
- [m1_pad_multitap_auditor](m1_pad_multitap_auditor.md): `ps2_input_publish_state` unwired; parent `pad_poll_players` never feeds HCU XInput.
- [m1_startup_guest_path_auditor](m1_startup_guest_path_auditor.md): boot chain through `game_initialize`; first maps `levels\ui\ui` then `levels\b30\b30`; its `CreateDirectoryA` finding has since been changed to an explicit fail-closed PS2 implementation, not actual writable directory support. The current ELF still lacks a fresh guest boot because the PCSX2 Qt/xcb launch failed before guest execution.
- [m0_memory_ledger_auditor](m0_memory_ledger_auditor.md): logical v2 ledger reconciles; `ps2_memory.o` is contiguous BSS, not parent boot arenas; `audio` region exactly full.
- [m0_link_closure_auditor](m0_link_closure_auditor.md): narrow M0 stub rule passes; `result.json` still `gate: open`; its 345-unit/726-external drift finding is superseded by the current 348-unit/708-external cross-check in the final milestone plan.
- [m2_tag_image_format_investigator](m2_tag_image_format_investigator.md): **CTAG v1** — HP2 offsets + relocation table; loader materializes EE pointers before full `tag_validate_tags` (not PS2 stubs).
- [m2_loader_failure_auditor](m2_loader_failure_auditor.md): layered fail-closed L0–L6; pairs with tag format and [m2_map_conversion_auditor](m2_map_conversion_auditor.md).
- [m2_arena_capacity_auditor](m2_arena_capacity_auditor.md): tag/BSP/payload ranges; 2 MiB cap invalid for real maps.
- [m3_object_lifecycle_auditor](m3_object_lifecycle_auditor.md) ↔ [m3_snapshot_render_auditor](m3_snapshot_render_auditor.md): post-tick immutable snapshot not built; parent table is consume-only target.
- [m3_player_movement_auditor](m3_player_movement_auditor.md): parent `mover` vs CE `game_tick`; tiered parity fixtures A–D.
- [m3_first_person_pose_auditor](m3_first_person_pose_auditor.md): hybrid FP boundary; `play_fp` wraps vs CE `first_person_weapons_*`.
- [m1_dma_layout_auditor](m1_dma_layout_auditor.md): Round 1 retry — four-layer DMA taxonomy, CE datum inventory, master safe-to-DMA table; cross-walks [m1_abi_layout_auditor](m1_abi_layout_auditor.md); snapshot in `frame_scratch`.
- [m3_collision_owner_auditor](m3_collision_owner_auditor.md): Round 1 retry — CE `source/physics/` authority, retirement ledger (M3/M4/M6), 16-row parity checklist vs host fixtures; parent `ee-world.mk` / `world.elf` collpack is fixture-only.
- [m1_platform_callsite_auditor](m1_platform_callsite_auditor.md): Round 1 retry — its 562-placeholder inventory is an earlier snapshot (current closure: 348 compiled units, 703 live externals); 13 cache **R4** + Win32 I/O on precache path; 187 render stubs + zeroed `render`; file/directory APIs now explicitly fail closed, the Xbox keyboard/rumble worker is excluded under `HALO_PS2`, and writable PS2 filesystem support is still absent; pairs with [m1_startup_guest_path_auditor](m1_startup_guest_path_auditor.md).
