# M2 Group B capacity review — full-campaign lower-bound options

**Disposition: no evidence-backed repartition currently closes the full-campaign gap while preserving the current CE raw-pointer contract, all stock maps, the 5.5 MiB reserve, and all PS2 runtime owners.** The only presently credible direction is a source-backed, lossless residency redesign that replaces selected raw-pointer consumers with explicit stable identities and bounded leases. That is a substantial CE/HCU interface change, not an arena resize, and no field family has yet been shown to provide enough net savings after indexes, cache, staging, and concurrent pins. Keep gameplay-map admission closed and do not credit compressed-size projections.

This review is read-only against the current shared worktree. It does not modify source, tests, budget, or plan. `plans/5.hcu-remake.md` remains the acceptance authority; the M2 plan and audits below supply current implementation evidence.

## Current evidence identity

The checkout HEADs at review time are parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. All relevant trees are dirty, so these commits are not complete source pins. Key current-file hashes:

| Artifact | SHA-256 |
|---|---|
| `config/memory-budget.json` | `67ef6d6085de71c22e3998a355cb2f79a8123837b7b14e89593a0d497de21b74` |
| `config/hcu-ps2-memory-map.json` | `1dff9c71e47d0f988c6765bf6559ee9dc67d3e3c012779414a4881ee84504ad0` |
| `docs/reports/m2-d20-hangar-render-mapping-audit.md` | `cbccaa96828c05e68c106faf6564d217375f8e9ce1e035a60bfcb31f33b72bdc` |
| `docs/reports/m2-d20-hangar-bsps-render-mapping.json` | `6c8702ef053117413170a37243c02f222b005cf06e36edd9f1a3e0be392d8e01` |
| `docs/reports/m2-2026-10-21-budget-repartition-review.md` | `25e95391d49ece9d4fcba5c25b77b4e8c42a99a62243f4984f01a48751f7d1d4` |
| `docs/reports/m2-2026-10-21-capacity-candidate-audit.md` | `d268916e0a612e3ebb37e99085e029bf2667590707e6c10006527f43f616fafe` |
| `docs/reports/m2-budget-proposal-animation-data-v1.md` | `a7a91b83e5c75dcb957def44f65fc9a8ac2a38c3be2b4d819565641b50775da3` |
| `docs/reports/m2-animation-data-contract-feasibility.md` | `f0ee43d1baa00b74085c8ff82ebbdd3b93ea35efccd76a236d1584c9eb3d65cf` |

The render-mapping audit uses decompressed `d20.map` SHA `30d8fc02bcd209a7ce03174d8cf6cf771dd3621837d9a2d02111718dcc5e792c`, `d20_hangar` source BSP SHA `a8e8174997a793831bd0504484582172e3802688a51d6b32a61e30c5962001ab`, and generated BSPS v2 section SHA `1442a7da4494a6be9ff45753e65a0fc72c8eb03e75ee94aeda2b80786c67c3bb` ([mapping audit](m2-d20-hangar-render-mapping-audit.md#L5-L16)). The audit warns that the generated section came from the currently checked-out, dirty halo-ps2 converter; the HCU/PS2 commit IDs alone do not bind that output.

## Lower-bound capacity, with owners charged once

Budget v2 contains 33,554,432 EE bytes, commits 27,787,264 bytes, and leaves 5,767,168 bytes (5.5 MiB) unavailable. Its named owners include kernel/system 1,572,864; ELF file-backed sections 2,097,152; permanent gameplay 6,815,744; current map/BSP 6,291,456; textures/lightmaps 4,194,304; dynamic simulation 2,621,440; DMA 1,179,648; streaming 1,572,864; checkpoint 524,288; audio 524,288; and frame scratch 393,216 ([`config/memory-budget.json`](../../config/memory-budget.json#L1-L20)). Most of these are required roles with unknown gameplay peaks, not spare RAM.

The whole-image d20 lower bound in the independent budget review charges six disjoint categories once: kernel/system reservation, ELF `PT_LOAD` file bytes, ELF `.bss`, CE game-state backing, the complete compact CTAG plus largest complete raw BSP, and the CE validation-claims bitmap. For d20 + `d20_hangar`, aligned values are 1,572,864 + 2,086,532 + 2,114,588 + 3,428,352 + 18,564,640 + 2,320,580 = **30,087,556 bytes**, which is **2,300,292 bytes above the entire committed ceiling**, before all other runtime owners, alignment/guards, decode scratch, render assets, or map transition overlap ([`m2-2026-10-21-budget-repartition-review.md`](m2-2026-10-21-budget-repartition-review.md#L48-L72)). This isn't a 2.3 MiB “savings target”: because the omitted systems still need nonzero physical storage, the actual required reduction is larger.

The owner boundaries matter:

* ELF file-backed sections and `.bss` are distinct portions; current `PT_LOAD` file bytes are 2,086,532 and `.bss` is 2,114,588. Those are exact diagnostic ELF figures from the capacity review, not proof that the physical current-image layout is accepted ([budget review](m2-2026-10-21-budget-repartition-review.md#L21-L25)).
* CE game-state backing is 3,428,352 bytes. The embedded 1 MiB object-pool claim belongs inside that backing and must not be charged again as a second object pool; transient simulation still needs its own measured dynamic-pool owner ([`hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L1-L8), [`halo_ps2_limits.h`](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L18-L22)).
* CE claims are additional: current CE PS2 code derives bitmap size from configured tag+BSP address capacities (`ceil(capacity/32) * sizeof(unsigned long)`), while the parent binder gives those two single contiguous spans disjoint storage in `current_bsp` and allocates claims from `resident_gameplay` ([`hcu_memory_bind.c`](../../src/stream/hcu_memory_bind.c#L41-L70), [`tag_validate.c`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L244-L283)).
* `current_bsp` tag/BSP bytes must not be counted again as `resident_gameplay`, `streaming`, renderer data, or claims. CBSP/CTAG encoded wire bytes are transient only if the loader actually decodes boundedly and releases them; they are not a free second copy during the current whole-section path.
* GS eDRAM (4 MiB), IOP RAM (2 MiB), and SPU2 RAM (2 MiB) are separate hardware stores, not backing for CE EE pointers ([`hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L101-L105)). Geometry/texture data uploaded to GS can potentially change which EE render copies are needed, but cannot replace CE collision, BSP queries, or tag pointers. IOP/SPU2 capacity likewise cannot be subtracted from EE lower bounds.

The campaign comparison is not merely a `current_bsp` partition problem. The best CTAG + smallest-BSP pair (`d40` + 8 KiB `d40_space`) is 10,310,876 bytes (10,310,880 aligned), while the all-campaign requirement includes d20 + its largest BSP at 18,564,628 (18,564,640 aligned) ([capacity audit](m2-2026-10-21-capacity-candidate-audit.md#L43-L69), [budget review](m2-2026-10-21-budget-repartition-review.md#L29-L45)). Even the `d40` maximum BSP (`d40b`, 7,907,328 bytes) produces 18,210,016 aligned tag+BSP bytes; adding capacity-derived claims of 2,276,252 and the fixed 9,202,336-byte kernel+ELF+BSS+game-state subtotal gives **29,688,604 bytes**, already 1,901,340 bytes over committed RAM before every other subsystem. This arithmetic is a lower-bound screen, not an observed target peak.

## Does the new d20_hangar mapping create a capacity path?

It does not. It answers a render-geometry identity question for one BSP, not whether the original CE data can be discarded or where replacement/query state lives.

The experiment maps all 49,859 source render surfaces to one expanded output triangle and compares 149,577 corners. It measures maximum Euclidean position error 0.0018664 world units and exact lightmap UVs for that case, but finds six diffuse-UV components outside the converter's ±64 range and up to 512.0001 UV error after clamping/quantization. Its candidate surface-to-batch index alone is 199,436 bytes before metadata/staging/alignment ([render audit](m2-d20-hangar-render-mapping-audit.md#L17-L44)).

The source compressed-vertex extents are 3,311,136 bytes; the generated BSPS section is 3,876,512 bytes. If BSPS is an additional EE-resident representation, replacing all of those CE bytes with BSPS plus the bridge is **negative savings of 764,812 bytes**, before retaining any CE-only fields or staging. If BSPS already exists in the renderer's live footprint, it must be counted once in that owner and can only offset CE bytes after proof that both representations have the same lifetime and all needed consumers are satisfied. Neither scenario currently closes the d20 deficit.

More fundamentally, BSPS VIF batches lack the CE CPU-query data and identity semantics: source surface IDs/leaf associations, normals/tangent frames, incident radiosity, and unquantized UVs. CE uses compressed vertex data in visibility, collision-hit-to-surface/material/barycentric resolution, lighting, and UV sampling ([`m2-bsp-compressed-vertices-parity-audit.md`](m2-bsp-compressed-vertices-parity-audit.md#L20-L63)). A render mapping is not a collision/material/object-lighting replacement. It should earn no whole-BSP memory credit until a source-backed CE consumer conversion proves equivalence for every consumer and topology.

## Capacity strategy assessment

| Candidate | Can it materially close the full-campaign lower bound now? | Reason |
|---|---|---|
| Reassign only `current_bsp`, `resident_gameplay`, or streaming/frame arenas | **No.** | The d20 partial subtotal already exceeds all committed RAM; those other owners cannot be reduced to zero, and gameplay high-water is not measured. Larger contiguous spans also enlarge CE claims. |
| Consume the 5.5 MiB reserve | **Prohibited; also not sufficient evidence.** | Reserve is expressly uncommitted. It is not a capacity strategy under the product contract. |
| Put CE tag/BSP bytes in GS, IOP, or SPU2 memory | **No under present CE interfaces.** | These stores are not CPU-addressable as one stable CE raw-pointer image; GS/IOP/SPU2 have different access and ownership. Only genuinely render-only assets may be candidates for GS-only lifetime after consumer proof. |
| Stream/decode CTAG and CBSP directly into final spans | **Necessary loader improvement; not enough for campaign fit.** | It can remove encoded full-section staging and overlap, but it cannot remove the complete compact CTAG/raw BSP final images demanded by current contiguous-pointer APIs. |
| Use BSPS output instead of CE compressed vertex data | **No; evidence currently shows net negative or no admissible credit.** | New BSPS section plus surface index outweighs the measured candidate CE bytes; CE still needs collision surface identity, normals/radiosity, and original precision/UV fallback. |
| Externalize animation data to one bounded cache | **Not supported by current evidence.** | CE consumers retain raw pointers; interpolation can hold four frame pointers simultaneously, direct compressed helpers read `animation.data`, and the extracted 4.97 MiB c10 sum is not an active-set/lease high-water. No cache size or net saving is proven ([animation contract](m2-animation-data-contract-feasibility.md#L1-L70), [no-change proposal](m2-budget-proposal-animation-data-v1.md#L18-L68)). |
| Lossless typed backing/paging with CE consumer conversion | **Potentially viable as an architecture, not yet evidence-backed as sufficient.** | It could avoid materializing cold fields at once while preserving logical bytes, but requires stable IDs, explicit leases/pins, logical validation, conversion of every raw-pointer consumer, cache/metadata/staging accounting, I/O latency bounds, and parity. No measured field-class savings exists today. |

Thus, if “full Halo CE pointer semantics” means every tag/BSP data field remains simultaneously available at its original CE pointer address, **no whole-image layout fits** all campaign requirements and all other budget owners within v2/reserve. If the intended requirement is semantic parity while converting internal raw-pointer uses to typed leases, that might yield a path, but it is not “preserving exact raw-pointer semantics”; it preserves logical data and behavior through a redesigned API. Do not represent those as the same guarantee.

## Next concrete source-backed experiment

Do not prototype another capacity resize based on this render mapping. The next useful experiment is a **field-level cold-data residency/lease proof on the hardest d20 case**, with zero data discarded and no budget change:

1. Freeze one coherent evidence tuple: retail map/source SHA; HCU schema ELF and dirty-tree patch hash; converter/halo-ps2 worktree hash; generated CTAG, CBSP, BSPS and all parent render/resource pack hashes; exact runtime ELF and config hashes. The mapping report presently pins the map and generated section but not a whole gameplay runtime or matching package.
2. Starting from `d20` + `d20_hangar`, walk the CE tag/schema and BSP consumer call graph, classifying each candidate range as (a) required every tick, (b) only during bounded query, (c) render-only and safely GS-resident, or (d) opaque/unknown and therefore resident. Include AI, scripts, collision, lighting, sound, effects, animation, tag validation and 1–4 player paths; do not use Halo-64's N64 cuts as permissions.
3. For any class proposed to page, establish stable identity `(map hash, tag index/path+datum identity, field/element, logical offset, length, digest)`, enumerate every pointer escape and maximum simultaneous pin set, and convert a *single bounded consumer path* to acquire/release a typed lease. Keep canonical bytes and CE whole-image behavior available as oracle. Reject candidates where a pointer is retained past lease release or where validation cannot observe the same logical bytes.
4. Implement an offline dual-path parity tool first: run the same CE accessor/query against resident and leased providers; compare bytes and outcomes, including malformed ranges, eviction pressure, simultaneous leases (at least four where callsites retain four), map switch/unload, and read failures. Count all metadata, compressed source, expanded cache pages, DMA-ready copies, and scratch. Compressed storage size is not EE savings unless it lives off EE and can be fetched within worst-case EE tick/I/O deadlines.
5. Calculate the **net saving** as removed resident bytes minus simultaneously resident lease cache, page table/identity metadata, decompressor/I/O scratch, pinned working set, renderer bridge, and transition overlap. Extend to every campaign map/BSP only after one consumer proves the mechanism, then measure real HCU gameplay active sets and EE/PCSX2 latency.

If no sizeable class can pass all five gates, the next meaningful progress is to retain the existing pointer model and collect production phase/lifetime high-water evidence for the exceptional possibility of safe temporal arena sharing; do not call unmeasured memory “free.” Even that will not alter d20's 30,087,556-byte whole-image lower bound unless it eliminates a whole-image representation or revises a genuinely unnecessary owner based on measurements.

## Sources and limits

* Product map scope: [`plans/5.hcu-remake.md`](../../plans/5.hcu-remake.md#L233-L267).
* Capacity arithmetic and CE claims: [`m2-2026-10-21-budget-repartition-review.md`](m2-2026-10-21-budget-repartition-review.md#L19-L72).
* Map candidates: [`m2-2026-10-21-capacity-candidate-audit.md`](m2-2026-10-21-capacity-candidate-audit.md#L1-L69).
* d20 render-batch mapping and explicit negative/zero-credit conclusion: [`m2-d20-hangar-render-mapping-audit.md`](m2-d20-hangar-render-mapping-audit.md#L17-L48).
* CE compressed BSP consumer audit: [`m2-bsp-compressed-vertices-parity-audit.md`](m2-bsp-compressed-vertices-parity-audit.md#L20-L116).
* Animation lifetime evidence: [`m2-animation-data-contract-feasibility.md`](m2-animation-data-contract-feasibility.md#L1-L100), [`m2-budget-proposal-animation-data-v1.md`](m2-budget-proposal-animation-data-v1.md#L18-L68).
* Machine-store split: [`config/hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L101-L105).

This is a report-only capacity assessment, not a map acceptance result, budget authorization, or M2 milestone closure. It has no PCSX2/EE runtime measurement; exact live high-water for all owners remains unknown.
