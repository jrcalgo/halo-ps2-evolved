# M2 combined animation/BSP removal capacity bound (2026-10-21)

**Scope and conclusion.** This report-only calculation asks whether the most optimistic interpretation of the current `animation.data` externalization projection, combined with the most optimistic `compressed_vertex_data` subtraction, could make every stock campaign map fit the existing PS2 EE owner layout. **No.** In the deliberately impossible lower-bound model—zero EE cost for every externalized animation byte, zero EE cost for replacement BSP render data, and no extra adapter/index/staging bytes—the combined tag+BSP image for each mission is still 9,168,640–11,525,120 bytes after 16-byte binding alignment. The current `current_bsp` owner is 6,291,456 bytes and owns both the tag and BSP spans. Even if the spans were expanded and the other named owner capacities retained, the calculated all-owner total exceeds the 27,787,264-byte committed ceiling for every campaign mission, by at least 2,739,840 bytes for c20 and 5,390,880 bytes for a30. The 5,767,168-byte reserve remains untouched in this arithmetic.

These numbers are a bound, **not** a proposal to remove data. Neither replacement is currently proven safe or free in EE RAM. The BSP estimate subtracts source bytes but has no matching retail-derived HP2 output sizes; if the replacement VIF/BSPS packets, identity bridge, or CPU query data are EE-resident, they must be charged. Therefore the combined projection is more favorable than any presently demonstrated layout. M2 remains open.

## Evidence tuple and reproducibility

The map-level animation and BSP reports share schema ELF SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`; this is the required join key. Current report file hashes checked for this calculation:

| Artifact | SHA-256 | Use in calculation |
|---|---|---|
| [`retail-map-working-set-2fba411b.json`](retail-map-working-set-2fba411b.json) | `f6548404f3f0f2bc3814f23fd2ffba16506a63a15bd2193d61ed94dec2128aed` | Campaign `animation_data_bytes_candidate_externalization`, `tag_image_bytes_after_animation_data_externalization`, and per-map projected-BSP summary. |
| [`retail-bsp-schema-2fba411b.json`](retail-bsp-schema-2fba411b.json) | `8f59ff7e42c05380edb26aa0c94a569432e3ab14799aafe48559c42133abadc7` | Per-map/per-BSP `raw_bytes`, `compressed_vertex_data_bytes`, and arithmetic-only `bytes_if_compressed_vertices_externalized`. |
| [`retail-animation-ranges-2fba411b.json`](retail-animation-ranges-2fba411b.json) | `92a1d32f79f77a83ce1125dddb9b73c5a3c57ec94632ad0963e3602018b4f47a` | Independent animation record/payload range audit; cross-checks animation report lineage, not a runtime live-set measurement. |
| [`m2-budget-proposal-animation-data-v1.md`](m2-budget-proposal-animation-data-v1.md) | `a7a91b83e5c75dcb957def44f65fc9a8ac2a38c3be2b4d819565641b50775da3` | Explicit no-change disposition: retain animation data in the image pending identity, lifetime, parity, and EE measurement. |
| [`m2-bsp-compressed-vertices-parity-audit.md`](m2-bsp-compressed-vertices-parity-audit.md) | `2cc22d16bf9a4aaf43cefedbd3e3727502dc23243989f1ce00ca25b86d026cff` | Source consumer/parity audit; says subtraction is not an allocation topology or approval. |
| [`config/memory-budget.json`](../../config/memory-budget.json) | `67ef6d6085de71c22e3998a355cb2f79a8123837b7b14e89593a0d497de21b74` | Current v2 EE region caps, 27,787,264-byte committed ceiling, and forbidden 5,767,168-byte reserve. |
| [`m2-2026-10-21-budget-repartition-review.md`](m2-2026-10-21-budget-repartition-review.md) | `25e95391d49ece9d4fcba5c25b77b4e8c42a99a62243f4984f01a48751f7d1d4` | Matching baseline for exact ELF/BSS/game-state lower-bound components used in the sensitivity check below. |

The campaign rows are ten scenario maps from the same 24-map corpus. Each candidate tag value is copied from `tag_image_bytes_after_animation_data_externalization`; each candidate BSP value is the **maximum** `bytes_if_compressed_vertices_externalized` among that campaign map's `structure_bsps[]`, not a sum of all BSPs. This is the all-referenced-BSP test for one map at a time. The source schema artifact labels the BSP value as an arithmetic projection (raw BSP extent minus compressed-vertex extents); it does not contain a measured target allocation. The two JSON files’ common schema ELF hash prevents mixing unlike extraction builds. The prior capacity review also binds the corpus to the retail XISO SHA and warns that its schema ELF is not a gameplay guest ELF.

For each map:

```text
candidate_tag = compact_tag_image_bytes - animation_data_bytes_candidate_externalization
candidate_bsp = max(structure_bsps[].bytes_if_compressed_vertices_externalized)
aligned_tag = align16(candidate_tag)
aligned_bsp = align16(candidate_bsp)
tag_plus_bsp = aligned_tag + aligned_bsp
claims = ceil(tag_plus_bsp / 32) * 4
```

The CE PS2 claims formula is capacity-based (`tag span + BSP span`), implemented by `claims_address_space_capacity()` / `tag_validate_claims_buffer_size()` in [`tag_validate.c`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L248-L283). This table assumes the two spans could be bound at all; it does not imply the existing binder can do so. The current parent binder places both spans in `current_bsp` and claims in `resident_gameplay` ([`hcu_memory_bind.c`](../../src/stream/hcu_memory_bind.c#L41-L70)).

## Campaign result rows

All values are bytes. `largest raw BSP` and `largest projected BSP` may be different BSP records; the path shown for each column identifies the independently selected maximum. `Animation-only + raw BSP` is included to show the result if BSP bytes cannot be removed. `Combined best-case` assumes both removals with no cost for replacement data. `Current-owner excess` compares that combined candidate with the entire current 6 MiB `current_bsp` cap, before other map-related owners.

| Mission | Animation bytes hypothetically removed | Candidate tag remaining | Largest raw BSP retained (path, bytes) | Largest projected BSP after subtraction (path, bytes) | Animation-only + raw max BSP | Combined candidate tag + projected max BSP, aligned | Claims at that capacity | Excess vs. 6,291,456 `current_bsp` |
|---|---:|---:|---|---|---:|---:|---:|---:|
| a10 | 3,808,164 | 5,814,096 | `a10g`, 8,568,832 | `a10f`, 4,736,728 | 14,382,928 | 10,550,832 | 1,318,856 | 4,259,376 |
| a30 | 3,739,304 | 5,949,792 | `a30_b`, 7,174,144 | `a30_b`, 5,575,320 | 13,123,936 | **11,525,120** | **1,440,640** | **5,233,664** |
| a50 | 4,557,582 | 6,617,194 | `a50_control`, 7,159,808 | `a50_hangar`, 4,360,680 | 13,777,002 | 10,977,888 | 1,372,236 | 4,686,432 |
| b30 | 4,240,256 | 6,027,820 | `b30a`, 6,608,896 | `b30a`, 4,588,728 | 12,636,716 | 10,616,560 | 1,327,072 | 4,325,104 |
| b40 | 4,372,828 | 7,408,596 | `b40_b`, 5,838,848 | `b40_b`, 3,974,200 | 13,247,444 | 11,382,816 | 1,422,852 | 5,091,360 |
| c10 | 4,971,464 | 6,582,152 | `c10_interiord`, 5,988,352 | `c10_exteriora`, 4,310,616 | 12,570,504 | 10,892,784 | 1,361,600 | 4,601,328 |
| c20 | 2,553,220 | 3,714,320 | `c20_3`, 9,039,872 | `c20_3`, 5,454,320 | 12,754,192 | **9,168,640** | **1,146,080** | **2,877,184** |
| c40 | 4,695,648 | 6,490,696 | `c40_b`, 6,318,080 | `c40_b`, 4,257,528 | 12,808,776 | 10,748,240 | 1,343,532 | 4,456,784 |
| d20 | 4,490,730 | 5,556,266 | `d20_hangar`, 8,517,632 | `d20_hangar`, 5,206,496 | 14,073,898 | 10,762,768 | 1,345,348 | 4,471,312 |
| d40 | 4,625,914 | 5,676,770 | `d40b`, 7,907,328 | `d40b`, 4,518,168 | 13,584,098 | 10,194,960 | 1,274,372 | 3,903,504 |

The optimistic candidate is smallest for c20 (9,168,640 aligned bytes) and largest for a30 (11,525,120 aligned bytes). **Even c20 exceeds the entire `current_bsp` owner by 2,877,184 bytes**, before any actual replacement HP2 section, staging, or collision/query data. The hypothetical animation savings alone do not make the remaining tag images small enough to ignore this: the post-animation candidate tag is 3,714,320–7,408,596 bytes, with five campaign tags greater than the current `current_bsp` capacity even before adding any BSP.

The `animation-only + raw max BSP` column is not a complete resident map total either, but it demonstrates the dependency: without a proven BSP replacement, the required tag plus BSP is 12,570,504–14,382,928 bytes. Thus the compressed-vertex hypothesis is numerically important, but only under a no-cost replacement assumption that currently lacks output-size and parity evidence.

## Whole-budget sensitivity: even zero-cost replacements are not enough

The prior matching budget-repartition review used the then-current exact combined machine ELF with `p_filesz=2,086,532`, `.bss=2,114,588`, CE game-state binding 3,428,352, and system/kernel reservation 1,572,864. Those components sum to 9,202,336 bytes before tag/BSP spans, claims, and other named runtime regions. Using that same baseline only as a sensitivity calculation, and preserving **full current capacities** for every region except `resident_gameplay` and `current_bsp`, gives:

```text
other named runtime owners held at current caps
  (texture, dynamic, DMA, streaming, checkpoint, audio, frame scratch)  11,010,048
exact baseline (system + ELF file + BSS + CE game state)                  9,202,336
minimum candidate data (best mission c20, aligned tag+BSP)                9,168,640
claims at c20 candidate capacities                                       1,146,080
                                                                        ----------
optimistic total for c20                                                30,527,104
committed ceiling                                                       27,787,264
deficit before replacement packs / other omitted owners                  2,739,840
```

For the largest combined candidate, a30, the same arithmetic is 33,178,144 bytes, or 5,390,880 bytes over the committed ceiling. These are not exact target peaks: the machine ELF and map-schema ELF are distinct artifacts; the former is used only to ground a fixed-runtime baseline from the cited budget report, not to claim simultaneous guest measurements. The result is intentionally favorable to the proposed idea: it assumes (1) every animation byte removed from CTAG costs zero EE bytes, cache bytes, metadata, or staging; (2) every compressed BSP byte removed costs zero EE bytes; (3) the VIF render replacement is free or already accounted inside the other owners; (4) no BSP/adapter index or retained CPU query bytes; (5) no alignment beyond separate 16-byte spans; (6) no validation scratch or load-transition overlap; and (7) other owners need exactly their current full reservations, with no growth. Real requirements can only increase the map data total unless a separately measured owner reassignment is approved.

Therefore this does **not** prove that all possible PS2-specific residency designs are impossible. It does rule out the narrower claim that these two arithmetic subtractions alone make the all-campaign workload fit the current v2 owner bounds. Repartitioning could only proceed with measured live-set reductions in other named owners and a new explicit design. The current map has no demonstrated spare high-water for dynamic simulation, texture/lightmap, DMA, audio, streaming, or frame scratch; the reserve is not an available source.

## Why the projected savings are not admissible yet

### Animation

`animation_data_bytes_candidate_externalization` is the sum of resident payload extents extracted from retail maps; it is not a concurrently pinned working set, and moving a payload off the tag image does not make it disappear from EE memory if the runtime lease/cache must hold it. The current CE data contract is in-image `TAG_SCHEMA_DATA`; direct pointer paths include `animation_get_frame_data()`, three compressed-keyframe helper fetches, the `animation_get_default_data()` macro, and a direct `frame_info` walk. Consumers span movement/root motion, melee metadata, object/unit pose, devices/vehicles, first-person and render-sampled pose, and sky/camera paths. The current review therefore explicitly retains the in-image format; a safe lease design needs complete identities, lifetime/pin accounting, parity, error behavior, DVD/OPL timing, and target high-water evidence. See [`m2-budget-proposal-animation-data-v1.md`](m2-budget-proposal-animation-data-v1.md), [`m2-animation-live-set-access-inventory-2026-10-21.md`](m2-animation-live-set-access-inventory-2026-10-21.md), and [`m2-animation-lease-feasibility-independent-2026-10-21.md`](m2-animation-lease-feasibility-independent-2026-10-21.md).

### BSP vertices

CE reads compressed vertices for CPU visibility tests ([`structure_visibility.c:551-615`](../../submodules/halo-ce-universal/source/structures/structure_visibility.c#L551)), source collision-hit surface/material/barycentric recovery, diffuse/lightmap UV sampling, and object-light normal/radiosity sampling. Current HP2 `BSPn` geometry contains expanded, quantized VIF render batches but not full source surface/leaf identity, source normals/tangents/binormals, or incident radiosity. It reorders triangles and omits some faces; report audit found no corresponding retail HP2 packs and no bound output-size set. The converter's `bytes_if_compressed_vertices_externalized` is therefore only `raw BSP − source blob` arithmetic. Before subtracting a byte, the ledger must charge the replacement BSPS section in its actual EE/GS store, retain whatever source data CE collision/light queries still require, and account source-surface bridge indexes if introduced. See [`m2-bsp-compressed-vertices-parity-audit.md`](m2-bsp-compressed-vertices-parity-audit.md) and halo-ps2's [`08-bsp-section.md`](../../submodules/halo-ps2/docs/08-bsp-section.md#L1-L7).

### Halo-64 comparison

Halo-64 shows that a port can route animation reads through an N64 streaming seam (`submodules/halo-64/source/models/model_animation_definitions.c:498-537`) and uses cartridge-backed graph data. Its own animation source retains direct compressed-data accesses, so the public accessor alone is incomplete (`submodules/halo-64/source/models/model_animations.c:2031,2143,2246`). That is useful as an integration-seam comparison only; it does not make bytes free or establish PS2 cache capacity, CE pointer-lifetime parity, BSP identity equivalence, or PS2/DVD/OPL timing. No N64 memory/pool policy is applied here.

## Required next evidence before any capacity credit

1. Regenerate a single dirty-tree-aware evidence bundle tying exact source ISO/map hashes, schema ELF and CE tree, halo-ps2 converter tree/config, generated HP2 package and per-`BSPn` hashes, and the gameplay EE ELF together. Existing schema ELF and machine ELF identities must remain distinct.
2. For every BSP in every campaign scenario, build matching HP2 sections from the same source map and report raw source bytes, stripped blob extents, output section bytes, adapter/identity metadata, and EE versus GS placement. Do not infer zero cost from the section being a render pack.
3. Extend source/consumer audit and construct parity fixtures for CE visibility, source-surface/material lookup, collision, lightmap UV sampling, normals/radiosity, no-cluster/unreferenced faces, mirror geometry, and quantization/order cases. Retain a mapping or residual payload for every required CE semantic.
4. For animation, implement the whole-record identity/lifetime contract only after the complete bypass audit; instrument actual campaign, first-person, movement, and actor workloads. Measure concurrent pins, cache/metadata/staging high-water, DVD/OPL reads and worst tick stalls on the target. Preserve the current in-image oracle.
5. Reconcile actual physical EE owner intervals and high-water for the same gameplay ELF, including expanded claims, resident tag/BSP, replacement BSP data, dynamic actors/effects/AI, textures/lightmaps, DMA, streaming, audio, checkpoint, frame scratch, overlap and rollback. Keep GS, IOP, and SPU2 as separate stores and preserve the full reserve.
6. Only then recalculate candidate bounds with measured replacement costs and test the worst combined mission (currently a30 by the source-removal projection) plus the lowest-data c20 control in PCSX2 and target-relevant profiles. Require complete map/campaign functionality; a UI-only map or host parser cannot qualify capacity.

This report is supplemental evidence for M2 capacity design only. It changes no implementation, budget, campaign admission, or M2 gate.
