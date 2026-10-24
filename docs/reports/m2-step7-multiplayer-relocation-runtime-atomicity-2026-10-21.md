# M2 Step 7 — multiplayer relocation and runtime failure atomicity

Date: 2026-10-21  
Scope: report-only review of the CE/HCU map and BSP publication boundary for the thirteen stock multiplayer maps, including the product's required co-op and AI-bot gameplay consumers. Campaign missions and campaign-only maps are excluded. This report makes no implementation or target-capacity claim.

## Finding

The relocation code has strong **component and host transaction** evidence, but there is not yet one accepted MP gameplay-map lifecycle fixture that composes late relocation/runtime faults with CE tag/BSP publication and a real map's post-load consumers. Existing closest coverage is split across:

| Evidence | What it demonstrates | What it does not demonstrate |
|---|---|---|
| UI CE lifecycle fixture, [`tests/test_hcu_ce_map_lifecycle.py`](../../tests/test_hcu_ce_map_lifecycle.py) and [`tests/hcu_ce_map_lifecycle_main.c`](../../tests/hcu_ce_map_lifecycle_main.c) | Actual `scenario_load()`/`scenario_unload()` composition; tag-read validation/visitor failures, initial B000 late-write failure, preflight relocation-allocation exhaustion (36,716-byte request at a deliberately bounded 39,831-byte owner cap), cursor/source/mount cleanup, and same-process retry. The current plan records the precise assertion and ELF/log hashes at [`plans/7.hcu-remake-m2-m4.md:617`](../../plans/7.hcu-remake-m2-m4.md#L617). | UI-only tag/BSP scale and semantics; no stock MP gameplay consumer or bot/local co-op workload. The owner exhaustion failure is preflight scratch allocation, not runtime schema relocation after CE has unpublished the prior gameplay map. |
| Retail CE BSP transaction fixture, [`tests/test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py) and [`tests/hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c) | Actual CE `scenario_switch_structure_bsp()` with HCU/parent package path; B000 restore, byte identity, CE verifier/schema rejection, CBSP CRC/rebase failure, candidate plus rollback failure to safe-null/menu, and retry. Uses retail `a30` and `a50` packages. | Both package maps are campaign maps. Host arrays are over-sized and use POSIX package reads. This is not MP map admission, target placement, or target capacity. |
| MP lifecycle/query fixture, [`tests/test_hcu_mp_capacity.py`](../../tests/test_hcu_mp_capacity.py) and [`tests/hcu_mp_capacity_main.c`](../../tests/hcu_mp_capacity_main.c) | Real CE scenario load/unload twice for Longest and Blood Gulch with the 1 MiB owner + 512 KiB scratch split, source-derived collision/PVS (and, for Blood Gulch, player-PVS) checks, preservation when preflight rejects a different map, and clean unload. | These are only 2/13 stock MP maps. It has no injected late CTAG/CBSP relocation fault or post-unload gameplay-load failure. Its host-sized results do not open production admission or prove guest EE capacity. |

Accordingly, do not call the atomicity category wholly unimplemented: the shared parser, publication ordering, rollback, and retry mechanisms are exercised. The material residual is **composed MP runtime failure evidence**, not another generic malformed relocation parser test or generic arena rollback test.

## Scope: stock MP, co-op, and bots

The controlling product scope says all thirteen Xbox multiplayer maps, one-to-four-player local split screen, stock multiplayer modes, vehicles, co-op, and AI bots are retained; campaign missions are out of scope ([`plans/5.hcu-remake.md:235`](../../plans/5.hcu-remake.md#L235)). The retail runtime catalog enumerates the stock MP set: Beaver Creek, Blood Gulch, Boarding Action, Carousel, Chill Out, Damnation, Hang 'Em High, Longest, Prisoner, Putput, Rat Race, Sidewinder, and Wizard ([`src/stream/hcu_map_catalog.c`](../../src/stream/hcu_map_catalog.c), test-map entries; cross-check the package corpus in [`retail-cbsp-catalog-package-audit-current.json`](retail-cbsp-catalog-package-audit-current.json)). Current production-sized MP host qualification covers only Longest and Blood Gulch; its own report says it does not exercise the other eleven maps, bots/co-op/vehicles/effects peak ownership, or guest gameplay ([`m2-multiplayer-production-capacity-host-2026-10-21.md`](m2-multiplayer-production-capacity-host-2026-10-21.md)).

Co-op and bot state do not change the fundamental CTAG/CBSP transaction contract: no gameplay consumer may receive a tag or BSP pointer until image checks, schema relocation, and CE validation have succeeded. They do change what a post-commit acceptance fixture must keep alive and observe. Multiplayer co-op/local players and AI bot actors may consume map tags, spawn/encounter data, collision, PVS, and pathfinding. A failed candidate must not leave one player's actor, a bot, or a script/vehicle reference pointing into the failed image; a successful retry must rebuild/resolve those consumers against the newly published generation. This is a consumer-lifetime requirement, not a reason to weaken schema validation or to add bot/co-op fields to the loader transaction itself.

Important implementation boundary: [`port/ps2/game/ps2_coop.c`](../../submodules/halo-ce-universal/port/ps2/game/ps2_coop.c) explicitly implements *local campaign* branches and returns `FALSE` from `network_coop_active()`; its comments say it does not provide network co-op. The plan excludes network transport but retains co-op. Therefore this file is not evidence that the required multiplayer co-op feature is implemented, nor does its campaign-only branch scope expand this report to campaign. A search of the PS2 port found no bot-specific implementation. Bot behavior needs its own CE-AI ownership and gameplay acceptance work; this atomicity audit can only require that AI consumers see a fully committed map or a cleanly torn-down state.

## Publication and rollback contract

1. CE `scenario_tags_load()` poisons the fixed tag destination with `0xCD`, calls `cache_file_read()`, then validates the cache header and all tag schemas before assigning `tag_header`, `global_tag_instances`, `global_tag_count`, and `tags_loaded` ([`cache_files.c:1237-1333`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1237)). The whole-buffer relocation path validates relative fixups before copying; the lifecycle regression confirms malformed final relocation leaves the poisoned destination and CE tag globals unpublished.
2. For a first BSP, `scenario_load()` calls `scenario_switch_structure_bsp(0)` and tears the scenario down on refusal ([`scenario.c:1218-1280`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1218)). For a switch, CE unpublishes/unloads the prior BSP, attempts candidate load and `structure_bsp_port_verify`, then either republishes a restored old BSP or reaches safe-null/menu if restoration also fails ([`scenario.c:1101-1204`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1101)).
3. `scenario_unload()` clears scenario/tag/BSP globals before releasing the parent map owner ([`scenario.c:390-425`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L390)). Parent `ctag_mount` marks BSP scratch and releases it on materialization/backend rejection ([`src/stream/ctag_mount.c:68-105`](../../src/stream/ctag_mount.c#L68)); map preflight similarly releases its owner mark on all outcomes ([`src/stream/hcu_map_service.c:405-510`](../../src/stream/hcu_map_service.c#L405)).

This is the correct basic atomicity model for bots and co-op too: they are downstream consumers of the committed generation. The risk that remains is proving the *same composition* for an MP package, including failure after candidate bytes have landed in an unpublished destination and recovery/reuse in the same process. Host visitor composition already proves late outer-CRC failure and no in-place rebase in isolation; the package/runtime fixture must connect that ordering to CE publications and live consumer state.

## Narrowest useful implementation and regression

No production code change is justified by this report alone. The narrowest useful addition is one MP-specific failure/retry scenario in the existing production-sized Longest/Blood Gulch lifecycle harness (prefer Longest for the first pass: one BSP and the smallest audited CTAG-plus-BSP subtotal; it is still only a test candidate, not an admitted map).

Use a **one-shot test-only fault** at the actual CTAG or CBSP stream/rebase seam after a nonzero prefix has been written to the candidate span. Drive it through CE's normal `scenario_load()` / BSP load path using the package-derived Longest HP2 and its raw-map oracle. Before faulting, either (a) load a known good MP map and explicitly model the normal teardown-before-replacement sequence, or (b) use the existing active-map rejected-preflight snapshot case to prove preflight refusal preserves the old map, then separately inject post-unload candidate failure. Do not claim transaction rollback of the old complete map if the production transition has already released it; the specified correct outcome there is safe-unpublished/null plus menu/error handoff.

Assert the following minimum contract at each failure/retry boundary:

- fault point proves a nonzero candidate prefix was written and no completion flag was set;
- CE scenario/tag/BSP globals and indices are either exactly the prior active-map snapshot (for preflight rejection) or all safe-null/unloaded after post-unload load failure;
- cache `tags_loaded`, `tag_header`, global tag instances/count, and per-tag base addresses are not published for the failed candidate;
- `ctag_mount`, source descriptor, parent owner and BSP/section scratch return to captured marks; no consumer generation/epoch advances on a rejected preflight, and a successful retry publishes one new generation;
- a no-fault retry in the same process loads, runs the existing collision/PVS query, and unloads cleanly;
- if the fixture adds local co-op players or AI bots, retain at least one player/bot datum across the failure boundary only if that is a supported transition; otherwise assert normal object/AI teardown before tag owner release and verify clean actor initialization after retry. Do not invent a bot API or count a no-op bot implementation as coverage.

Parameterize this transaction/fault case over all 13 MP packages **when the approved all-map memory topology can lawfully materialize them**. Before that topology exists, an oversized host transaction run can expand format/map diversity only; clearly label it host-only and do not mark any map capacity-qualified. The two already production-partition-sized host candidates can provide the first representative composed test without changing map admission.

## What this closes and what remains separate

Passing the proposed case would close one MP runtime relocation-publication/retry subcheck. It would not prove that every stock MP map fits, that co-op/bots are implemented, or that those systems pass gameplay parity. Separate gates remain:

- all 13 map source/package identity, successful CE tag/BSP validation, and safe runtime admission after Step 8's approved lossless residency design;
- co-op and AI-bot gameplay acceptance (actor/AI setup, map-reference lifetime, collision/path/PVS/environment consumers, repeated sessions), currently not supplied by loader atomicity fixtures;
- interpreter/recompiler or hardware evidence for the exact current guest image and physical EE arena peaks;
- full Step 7 BSP consumer coverage and target query acceptance. Step 7 remains partial under [`plans/7.hcu-remake-m2-m4.md:579-595`](../../plans/7.hcu-remake-m2-m4.md#L579).

Halo-64 is not a failure-semantics oracle here. Its port notes may remind us to retain stateful CPU-side gameplay/presentation state, but its N64 allocation choices or stubs do not qualify PS2 map relocation, co-op, bots, or arena budgets. No REA binary work is warranted: this is source/test composition over known package data, not unexplained shipped-binary behavior.

## Conclusion

For the thirteen-map multiplayer-only product, the generic relocation and rollback machinery is substantially covered in host fixtures, and the newer UI owner-exhaustion regression supersedes the older recommendation to add that same preflight test. The smallest material addition is an MP package-backed, CE-lifecycle late-write/rebase failure followed by same-process safe-state verification and retry. Co-op and bots must be treated as post-publication consumers and separately implemented/qualified; current `ps2_coop.c` and the absence of a PS2 bot module do not satisfy that product scope. No campaign case is needed, and none of this evidence should be promoted into capacity or guest acceptance.
