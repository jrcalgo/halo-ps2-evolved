# M2 campaign-map capacity candidate audit (2026-10-21)

## Finding

**No retail campaign map can fit the current PS2 arena ownership model with a complete compact CTAG image, one unmodified CE BSP, and CE tag-validator claims resident simultaneously.** This is a static lower-bound rejection, not a measured guest peak: the best campaign combination in the audited corpus is `d40` plus its smallest referenced BSP (`d40_space`), and their final resident data alone require 10,310,876 bytes (10,310,880 after 16-byte binding alignment) in `current_bsp`, whose entire capacity is 6,291,456 bytes. The shortfall is at least 4,019,420 bytes before render packs, load overlap, canaries, or other map-owned bytes. The CE validator claims bitmap is a separate resident-gameplay owner, so it cannot make this current-BSP overflow disappear. Do not admit a campaign catalog entry, truncate a tag/BSP, move data into a different owner's region without an implemented contract, or spend the reserve on this evidence.

The result does **not** say that campaign maps can never be made to fit PS2 RAM. It says none fits the current fixed partition and ownership topology without a further measured, behavior-preserving memory-layout/data-residency design. Any such design must remain within budget version 2 unless a separately measured and approved budget revision says otherwise.

## Scope, evidence identity, and method

The scope is all ten stock campaign cache maps (`a10`, `a30`, `a50`, `b30`, `b40`, `c10`, `c20`, `c40`, `d20`, `d40`) from the 24-map retail corpus, not a user-selected small map. Their CTAG and BSP schema audits use schema ELF SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`. The current checked-in reports and hashes at inspection:

| Evidence | SHA-256 | What it establishes |
|---|---|---|
| `retail-map-working-set-2fba411b.json` | `f6548404f3f0f2bc3814f23fd2ffba16506a63a15bd2193d61ed94dec2128aed` | Per-map compact CTAG and BSP lower-bound summary; explicitly excludes claims, validation scratch, alignment/transition overlap, renderer, texture, streaming, and audio. |
| `retail-ctag-compaction-2fba411b-v2.json` | `be477e5cd229e46d55d8c9eeba8793f5ed7464322c9401009ff1304f7d1630ed` | Full compact CTAG image sizes and source/CTAG hashes. |
| `retail-bsp-schema-2fba411b.json` | `8f59ff7e42c05380edb26aa0c94a569432e3ab14799aafe48559c42133abadc7` | Per-map, per-BSP raw image and CBSP envelope sizes; reports 82 BSPs across 24 maps. |
| `retail-bsp-capacity-2fba411b.json` | `074c925d24dec5ea990e7cffcfce3dc544e8d208658c82b484deda20de6b4a2a` | Independent raw-size screen against 6 MiB `current_bsp`; 21 raw BSPs exceed it. |
| `retail-cbsp-catalog-package-audit-e4a97218.json` | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` | Package/source identity and catalog coverage; it explicitly makes no in-RAM fit claim. |
| `config/memory-budget.json` | `67ef6d6085de71c22e3998a355cb2f79a8123837b7b14e89593a0d497de21b74` | Budget-v2 region capacities and reserve. |
| `src/stream/hcu_memory_bind.c` | `4542021506d0873ad18f55e515ec22877d21eac38bd39bc939d61e186f720d17` | Current boot-fixed tag/BSP/claims owner topology. |

The source map set is from XISO SHA-256 `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258` as recorded by the M2 all-map audit. For the minimal candidate `d40`, decompressed map SHA-256 is `438452ef1896dd5bc2d3210b279f76e71b775f7eb2b7a8f8e29f4e5471d59a76`; its generated catalog package SHA-256 is `180c6c3e775227e7e7eac6987afaad45c477f1ca8acf03be5d99a37b462d358c` (39,004,160 bytes). The schema ELF identity is embedded in both current CTAG/BSP schema-derived output sets; the package audit matches `d40` to the same decompressed-source hash. The package byte count is a disc/package artifact size, not an EE residency number.

The retained closure record [`m2-longest-artifact-freeze.md`](m2-longest-artifact-freeze.md) binds this schema ELF to parent/HCU/halo-ps2 commits `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`, R5900 GCC 15.2.0, manifest SHA-256 `8fa834f2185dd9dae225c51ef236d6491e2ab9449c3e6f7cc9eb2eb7c407485a`, and prefix SHA-256 `8edce2ba3c42b406db6c73cdca3c6c68e318c9df390a16c1db0f54321c8074b2`. This is a schema/packing ELF, not the combined gameplay-machine ELF: no guest map load or runtime peak is attached to it. The source worktrees were dirty during inspection; the report hashes above identify the actual capacity/config/binder files inspected more precisely than commit IDs alone.

Calculation uses **complete, already-compact CTAG image bytes** plus the complete source BSP image for each candidate. No field is removed or projected away. CBSP envelope bytes are treated as encoded input/staging, not added to persistent BSP image residency; they still require a separate bounded loading path and transient scratch. Claim bytes are computed by the actual CE formula from the capacities of the bound tag and separate-BSP spans, not from the number of populated tags.

## Current arena ownership and the claims calculation

Budget v2 has `resident_gameplay = 6,815,744`, `current_bsp = 6,291,456`, `streaming = 1,572,864`, `frame_scratch = 393,216`, and `uncommitted_reserve = 5,767,168` bytes. All are distinct owners, and the reserve is unavailable ([budget rows](../../config/memory-budget.json#L4-L20); governing account [plans/5.hcu-remake.md](../../plans/5.hcu-remake.md#L265-L267)).

At current boot, [`hcu_main.c`](../../src/stream/hcu_main.c#L17-L19) defaults `HALO_HCU_TAG_CACHE_BYTES` to 2,097,152. [`hcu_memory_bind_parent_v2()`](../../src/stream/hcu_memory_bind.c#L41-L56) places that single tag span first in `current_bsp` and assigns the 4,194,304-byte tail to the separate BSP span. HCU validator claims are then allocated in `resident_gameplay` by [`hcu_memory_bind_parent_v2()`](../../src/stream/hcu_memory_bind.c#L65-L70). In `tag_validate.c`, the PS2 claims address space is the sum of tag-cache and BSP-cache capacities, and the bitmap uses one 32-bit word per 32 addressable bytes, rounded up ([`claims_address_space_capacity()`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L248-L258), [`tag_validate_claims_buffer_size()`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L272-L283)). Thus the current 6,291,456-byte combined cache span requires:

```text
ceil((2,097,152 + 4,194,304) / 32) * 4 = 786,432 bytes of claims
```

That 786,432 is a **capacity-derived owner**, not a map payload, not a live tag-size estimate, and not free space. It remains simultaneously resident while CE validates the tag image/BSP. Expanding tag/BSP spans changes this claims obligation and must be accounted at the same time.

## Campaign candidate lower bound

For each campaign map, I joined `compact_tag_image_bytes` from the 2fba CTAG working-set result with the smallest *complete* referenced `raw_bytes` and CBSP envelope from its per-BSP schema rows. Choosing the smallest BSP for each map makes this a deliberately favorable lower bound; an actual spawn/zone choice may be larger. Even the smallest pair is larger than the entire `current_bsp` owner:

| Map | Complete compact CTAG | Smallest referenced raw BSP | CTAG + one raw BSP | Excess over 6,291,456 current BSP |
|---|---:|---:|---:|---:|
| a10 | 9,622,260 | 1,529,856 | 11,152,116 | 4,860,660 |
| a30 | 9,689,096 | 6,199,296 | 15,888,392 | 9,596,936 |
| a50 | 11,174,776 | 3,835,904 | 15,010,680 | 8,719,224 |
| b30 | 10,268,076 | 4,022,272 | 14,290,348 | 7,998,892 |
| b40 | 11,781,424 | 1,288,192 | 13,069,616 | 6,778,160 |
| c10 | 11,553,616 | 4,704,256 | 16,257,872 | 9,966,416 |
| c20 | 6,267,540 | 6,864,896 | 13,132,436 | 6,840,980 |
| c40 | 11,186,344 | 1,400,832 | 12,587,176 | 6,295,720 |
| d20 | 10,046,996 | 3,807,232 | 13,854,228 | 7,562,772 |
| d40 | 10,302,684 | 8,192 | **10,310,876** | **4,019,420** |

`d40` is the most favorable CTAG-plus-one-BSP combination even though `c20` has the smallest campaign CTAG: `c20`'s smallest referenced BSP is still 6,864,896 bytes. `d40_space` is an 8,192-byte source BSP and its CBSP envelope is 8,444 bytes. The `d40` source and package hashes are recorded above and in the all-map package audit; its BSP references and exact extents are in [`retail-bsp-schema-2fba411b.json`](retail-bsp-schema-2fba411b.json#L327214) and its package identity in [`retail-cbsp-catalog-package-audit-e4a97218.json`](retail-cbsp-catalog-package-audit-e4a97218.json#L120-L125). The joined all-map figures can be reproduced from [`retail-map-working-set-2fba411b.json`](retail-map-working-set-2fba411b.json#L223-L230) and the map-specific BSP rows in the schema report; the full per-map schema ELF identity is at [`retail-map-working-set-2fba411b.json:548`](retail-map-working-set-2fba411b.json#L548).

Even ignoring the BSP, `d40`'s 10,302,684-byte CTAG image alone exceeds the **entire** current-BSP arena by 4,011,228 bytes, and exceeds the current 2,097,152-byte tag-cache binding by 8,205,532 bytes. The encoded CTAG payload is 10,445,548 bytes; attempting to retain that payload in the 1,572,864-byte streaming arena would exceed it by 8,872,684 bytes. A streamed reader can eliminate that staging copy, but cannot shrink the final image or the selected CE BSP. Current code still performs whole-section loads through `world_load_section_with_scratch()` and mounts CTAG/sections through the current owner path ([`section.c`](../../submodules/halo-ps2/engine/src/world/section.c#L23-L90), [`ctag_mount.c`](../../src/stream/ctag_mount.c#L67-L104)); the M2 design report requires bounded visitor/materialization while preserving CRC, relocation, and publication semantics ([`m2-streamed-ctag-destination-design.md`](m2-streamed-ctag-destination-design.md)).

If the `d40` tag+BSP capacities were enlarged to their minimum aligned extents, the CE claims bitmap would itself rise to:

```text
tag span 10,302,688 + BSP span 8,192 = 10,310,880 addressable bytes
ceil(10,310,880 / 32) * 4 = 1,288,860 bytes of claims in resident_gameplay
```

This is 502,428 bytes more claims than today's 786,432, yet it still does not make the data fit: the tag+BSP spans alone exceed `current_bsp` by 4,019,424 bytes after alignment. The current architecture does not bind these tag bytes in `resident_gameplay`; its binder allocates CE game state there before claims. Moving the tag image there would be a new owner/layout design and plainly cannot accommodate a 10.3 MiB image in the 6.8 MiB region. Moving only part of a CE tag cache across owners is also not supported by the single-span `physical_memory_bind_tag_cache()` interface and cannot be inferred safe for CE pointers. The existing CE and parent owners must remain disjoint unless a new interface proves otherwise.

## Do not confuse section size with a live peak

| Quantity | What it means | What it does **not** prove |
|---|---|---|
| `compact_tag_image_bytes` | Complete materialized CTAG tag-image bytes, already excluding only the converter's represented Xbox render interval and relocation wire table. This is the final tag-cache lower bound used above. | Not the complete resident map, not CE game state, and not a measured allocation/high-water. |
| CTAG `payload_size` | Uncompressed CTAG wire section including envelope/relocation entries. `d40` is 10,445,548 B; it is a transient input/verification quantity, not an additional steady-state owner if streaming is implemented. | Not the final compact tag image; not the on-disc HP2 package size. |
| Raw BSP `raw_bytes` | Complete original CE structure-BSP image which the schema audit says must remain preserved unless a specific field is proven unnecessary. `d40_space` is 8,192 B. | Not the CBSP envelope and not proof that CE has loaded or queried it. |
| CBSP envelope bytes | Encoded package section used to reconstruct the raw BSP; `d40_space` envelope is 8,444 B. | Not a second persistent copy that must remain after successful materialization; nevertheless current full-buffer APIs can make it a transient staging owner. |
| Package `package_bytes` | Whole HP2 package on storage; d40 package is 39,004,160 B. | Not bytes simultaneously resident in EE RAM. |
| Validator claims | Bitmap sized from configured **capacity** of tag+BSP spans (currently 786,432 B). | Not based on actual populated map extents and not safe to overlay on the tag image. |
| Current measured peaks | UI-only fixtures: streaming ~1.55 MB and frame scratch ~275 KB; these are unrelated package cases. | Not d40, campaign, renderer, audio, or BSP guest peaks. |

The 2fba working-set report explicitly excludes the claims bitmap, schema-validation scratch, alignment and old/new-map overlap, PS2 render packs, textures, streaming, and audio. Its `lower_bound` and projected-animation fields are feasibility screens, not acceptance. Any arithmetic that externalizes animation data or compressed BSP vertices is excluded from this decision: no CE reference-lifetime contract, physical destination, or parity proof authorizes deleting those bytes. The 24-map raw-BSP audit independently records 21 blocks larger than the current 6,291,456-byte BSP region, with largest `c20_3 = 9,039,872` bytes; do not truncate a BSP to force it through ([`retail-bsp-capacity-2fba411b.json`](retail-bsp-capacity-2fba411b.json), [`plans/5.hcu-remake.md`](../../plans/5.hcu-remake.md#L354-L356)).

## Decision and critical next implementation/test

1. Keep all campaign catalog entries closed. The current code has an explicit UI/bootstrap tag-cache default, a tag-plus-BSP single-span split, and no reserve fallback; the plan states that full campaign scope remains required ([`plans/5.hcu-remake.md`](../../plans/5.hcu-remake.md#L233-L240), [`hcu_main.c`](../../src/stream/hcu_main.c#L17-L19), [`hcu_memory_bind.c`](../../src/stream/hcu_memory_bind.c#L41-L70)).
2. Before coding another map loader slice, produce a versioned ownership proposal that tests the *unprojected* 24-map data sizes against every fixed EE owner and the simultaneous costs: current linked ELF/BSS charged to resident/static owners, CE game state, claims, complete tag image, largest spawn-relevant BSP, render/visibility/collision packs, texture/lightmap cache, animation and sound staging, HP2 decoder/scratch, retained metadata, canaries/alignment, and transition peak. Keep GS eDRAM, IOP, and SPU2 as separate hardware stores and do not count them as EE pointers.
3. The critical first executable capacity test should be the least-data campaign fixture `d40` with the exact source/package tuple above, but use its **full CTAG plus an explicitly selected valid BSP**. Assert at bind time that no allocation overlaps and that candidate tag/BSP spans, validator claims, resident-gameplay occupancies, staging, and all other owners fit without reserve; verify exact capacity-derived claims with the CE implementation. The tiny `d40_space` combination is useful to prove immediate impossibility; for an operational load test choose the scenario's real spawn/initial BSP (likely larger) and audit why it is selected. Do not use the host-overprovisioned a30/a50 transaction tests as capacity evidence.
4. If the v2 partition cannot pass this truthful byte ledger, stop and present measured alternatives: source-backed streamed/externally backed data with consumer lifetime/parity tests, or a versioned budget proposal based on actual EE high-water. No map filtering, truncation, compressed-vertex loss, raw allocation/heap fallback, or silent use of the 5,767,168-byte reserve is acceptable.
5. Only after a complete production-sized topology exists should the team add R5900 canary/high-water instrumentation, direct bounded CTAG and CBSP materialization, CE tag/BSP validation and collision/environment queries, same-process unload/retry tests, then run one exact hash-pinned gameplay scenario in both PCSX2 modes. A successful package parser or UI-only marker is not a gameplay-map capacity pass.

This report is evidence/guidance for M2 Steps 8 and 10; `plans/5.hcu-remake.md` remains the acceptance authority, and no milestone status is changed here.
