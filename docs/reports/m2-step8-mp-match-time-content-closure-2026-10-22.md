# M2 / Step 8: stock multiplayer match-time content closure

## Result and scope

This audit expands the prior static BSP/scenario texture inventory to the gameplay content a multiplayer match can select. It is strictly the 13 named Halo CE multiplayer maps; campaign maps are not inputs. The audited maps are Beaver Creek, Blood Gulch, Boarding Action, Carousel, Chill Out, Damnation, Hang 'Em High, Longest, Prisoner, Putput, Rat Race, Sidewinder, and Wizard. Their current decompressed files' hashes match the earlier “retail map” inventory. The prior reports identify their extraction source as XISO SHA-256 `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258`, but that original XISO is not currently in `build/`; this pass verifies the extracted map bytes, not a fresh extraction from that XISO.

For each map, the tool starts from all local `weap`, `eqip`, `bipd`, `vehi`, and `proj` tags, plus its `scnr`, `matg`, and `hudg` roots. It recursively follows references using the exact linked HCU tag schemas carried by the specified PS2 ELF. The source group inventory consequently includes the player/bot biped and animation graph references, the complete local arsenal and its first-person model/animation references, vehicles, projectiles, effects, HUD/interface resources, and their transitive tag references. A tag may be in the closure without being simultaneously instantiated during a particular match.

### Per-map results

All values below are bytes. “Tag union” is unique root/block/in-image data coverage for the walked gameplay tag closure; it excludes external `file_data` payload storage and BSP tag internals. MODL/OTEX/ANIM are independently converted pack sections for every reachable `mode`/`antr` tag, rather than the scenario-only selection. “Baseline” is the prior static report's TEXS + all LM sections + scenario-selected OTEX. The last column substitutes the full-closure OTEX output to show the specific render-texture closure delta; it is still only an offline section-size sum.

| MP map | Tags | Tag union | MODL | Full-closure OTEX | ANIM | Static baseline TEXS+LM+OTEX | TEXS+LM+full OTEX |
|---|---:|---:|---:|---:|---:|---:|---:|
| Beaver Creek | 1,650 | 4,104,243 | 4,516,944 | 2,759,776 | 652,160 | 1,281,824 | 3,165,792 |
| Blood Gulch | 1,713 | 4,260,147 | 4,563,904 | 3,027,136 | 651,344 | 2,144,640 | 3,466,272 |
| Boarding Action | 1,648 | 4,145,163 | 4,473,424 | 2,531,296 | 651,072 | 1,045,792 | 2,929,760 |
| Carousel | 1,620 | 4,069,999 | 4,386,720 | 2,563,008 | 651,072 | 890,272 | 2,774,240 |
| Chill Out | 1,596 | 4,039,887 | 4,364,416 | 2,309,632 | 651,072 | 773,024 | 2,656,992 |
| Damnation | 1,657 | 4,124,655 | 4,502,080 | 2,700,800 | 651,072 | 1,090,784 | 2,974,752 |
| Hang 'Em High | 1,599 | 4,046,207 | 4,364,576 | 2,629,696 | 651,072 | 1,181,184 | 3,065,152 |
| Longest | 1,610 | 4,062,687 | 4,384,976 | 2,522,752 | 651,072 | 1,010,816 | 2,894,784 |
| Prisoner | 1,590 | 4,036,383 | 4,363,088 | 2,629,536 | 651,072 | 1,159,776 | 3,043,744 |
| Putput | 1,584 | 4,046,051 | 4,351,296 | 2,273,344 | 651,072 | 597,632 | 2,481,600 |
| Rat Race | 1,606 | 4,054,303 | 4,420,736 | 2,386,560 | 651,072 | 922,368 | 2,799,840 |
| Sidewinder | 1,657 | 4,157,883 | 4,612,800 | 2,623,168 | 651,408 | 1,838,656 | 3,160,288 |
| Wizard | 1,626 | 4,060,275 | 4,376,288 | 2,638,144 | 651,424 | 943,520 | 2,827,488 |

Across the 13 alternative maps, the unique path union contains 1,767 tag paths and the summed per-map tag-union count is 53,207,883 bytes. That sum is a catalog total, not a concurrent allocation. Blood Gulch is largest for the walked in-image tag union (4,260,147 bytes), MODL output (4,563,904), OTEX output (3,027,136), and combined static-TEXS/LM plus full-closure OTEX output (3,466,272). The latter is below the nominal 4,194,304-byte `texture_cache` reservation in [`config/memory-budget.json`](../../config/memory-budget.json#L13), but is not proof that those sections are actually owned by or resident in that arena.

The schema walk also records 894–897 `file_data` descriptors/map, with declared byte totals of 11,016,000–11,460,456 across the walked records. Reachable bitmap tags refer to 16,409,600–19,622,400 unique source pixel-interval bytes/map in the decompressed map inputs (Blood Gulch is 19,622,400). These are *input/source extents*, not a recommendation to retain raw bitmap pixels on EE RAM; the conversion pipeline moves selected render data to converted packs. The complete per-map breakdown and source flags are in the JSON. The raw in-image tag union alone is below the 6,815,744-byte `resident_gameplay` reservation, but is not the converted CTAG image size or a resident high-water result; relocation/compaction, stripped graphics fields, file-data ownership, CE global data, and allocator metadata still determine actual fit.

## Findings that constrain Step 8

1. Scenario-selected object assets materially undercount a match's content. For Beaver Creek the prior selected object set was 12 models, 875,808-byte OTEX, and 371,248-byte ANIM; the closure contains 53 models, 2,759,776-byte OTEX, and 652,160-byte ANIM. Across maps, full closure OTEX is 2,273,344–3,027,136 bytes versus scenario-only OTEX 389,376–1,705,504 bytes in the companion inventory. The full closure adds 38–41 model tags and 14–17 animation-graph tags over the scenario/sky baseline, depending on the map.
2. The closure includes weapon-held content, not just placed objects: CE's weapon interface definition has explicit `first_person_model` and `first_person_animations` references ([`weapon_definitions.h`](../../submodules/halo-ce-universal/source/items/weapon_definitions.h#L72)); first-person weapon update resolves the graph and animation state from those references ([`first_person_weapons.c`](../../submodules/halo-ce-universal/source/interface/first_person_weapons.c#L2329)). The recursive graph therefore discovers the arsenal's model/animation references even though the scenario does not place each weapon.
3. Every audited retail MP map has 15 weapon tags, 14 equipment tags, 2 biped tags, 3 vehicle tags, and 16 projectile tags. The source-map name scan finds the Gravity Rifle in all 13 maps, but no Energy Sword or Fuel Rod tag in any of them. **The two requested custom weapons cannot be covered by this stock retail-MP closure:** their tag roots, models, FP models/animation, projectile/effect dependencies (Fuel Rod), converted assets, and runtime residency need a separately provisioned mod/port asset source and must be added to the acceptance closure. This is an asset-source gap, not an inference that those weapons cannot be implemented.
4. The recursively reached groups include HUD/interface tags and transitive effects: each map closure has 1 `hudg`, 318 `effe`, 66 `jpt!`, 96 `part`, 7 `pctl`, 8 `cont`, and its reachable biped/vehicle/weapon/projectile families. These are source tag counts, not proof that every effect particle or interface bitmap is simultaneously decoded or resident. Retail source presence and decompressed tag closure also do not imply that this port has converted or implemented the corresponding rendering/audio path.
5. Dynamic gameplay pool constraints are a separate measurement. The pinned CE PS2 limits retain source/Xbox capacities, not accepted EE byte allocations: e.g. 2,048 object slots and a 1 MiB object pool are declared in [`halo_ps2_limits.h`](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L30), object initialization allocates the object data array and object memory pool ([`objects.c`](../../submodules/halo-ce-universal/source/objects/objects.c#L1039)), AI uses a 256-actor array ([`actors.c`](../../submodules/halo-ce-universal/source/ai/actors.c#L564)), and particles allocate 1,024 × 0x70-byte data entries ([`particles.c`](../../submodules/halo-ce-universal/source/effects/particles.c#L230)). These allocations are routed via CE `game_state_data_new`/memory-pool ownership and cannot be equated with measured occupancy of the 2,621,440-byte `dynamic_simulation` reservation. A multiplayer acceptance fixture must measure actual allocations and high-water under maximum supported players/bots, vehicles, projectiles, effects, and simultaneous ordnance.

## What these numbers mean—and do not mean

- The tag-union measure is a deduplicated byte-range union of schema-defined tag roots, reflexive blocks, and in-tag-image data. The JSON separately lists file-data records/bytes by source flags, unresolved references, and opaque roots. It does not include every external bitmap/sound payload as tag-image bytes. The one `sbsp` root per map is intentionally left opaque in this tag walk; BSP geometry and TEXS/LM packages are accounted by the separate static inventory and must not be double-counted as walked tag bytes.
- MODL, OTEX, and ANIM are exact output lengths and hashes from the pinned offline converter, for all reachable model and animation-graph tags. They are independently produced sections; **do not add MODL + OTEX + ANIM + walked tag bytes and describe that sum as simultaneous EE residency.** Their runtime loading, sharing, pinning, first-person weapon-switch overlap, arena assignment, alignment, staging buffers, and eviction lifetimes have not been measured. OTEX is the texture-bearing section; MODL/ANIM do not consume the nominal texture-cache merely because they accompany it in a pack.
- [`world_load()`](../../submodules/halo-ps2/engine/src/world/world.c#L58) and [`world_load_objects()`](../../submodules/halo-ps2/engine/src/world/world.c#L103) load sections into a caller-supplied `arena_t`; these APIs alone do not prove the caller uses the `texture_cache` reservation for TEXS/LM/OTEX or that MODL/ANIM have a dedicated live owner. Step 8 must establish the actual caller/arena and measure retained bytes plus temporary source/decode overlap.
- The biggest measured pack-section subtotal here (TEXS + LM + full OTEX) is 3,466,272 bytes, but it does not establish cache fit: decoded source copies, GS upload staging, texture deduplication policy, fragmentation, simultaneous map transition, renderer pins, and arena routing are outside this offline conversion result. Likewise MODL at 4.35–4.61 MiB and ANIM at ~651 KiB are independent output sizes, not dynamic-pool occupancy.
- Stock multiplayer maps' tag inventory does not bound co-op/bot *counts* or runtime creation pressure. It only bounds relevant tag content available from these map files. Network player limits, bot population, and CE pool actual/high-water accounting require explicit port policy and runtime tests.

## Reproduction and evidence identity

The audit implementation is [`tools/audit_mp_match_content_closure.py`](../../tools/audit_mp_match_content_closure.py#L1); the earlier static baseline is [`tools/audit_mp_render_asset_bound.py`](../../tools/audit_mp_render_asset_bound.py#L1) with results/method in [`m2-step8-mp-static-render-asset-inventory-2026-10-22.md`](m2-step8-mp-static-render-asset-inventory-2026-10-22.md). Run from the repository root:

```sh
python3 tools/audit_mp_match_content_closure.py \
  build/retail-maps/decompressed \
  --schema-elf build/hcu-ps2-closure/all-no-bootstrap-memory-m2-ui-lifecycle/halo-local.elf \
  --static-inventory build/m2-mp-render-assets/static-render-assets-v2.json \
  --output build/m2-mp-render-assets/match-content-closure-v1.json
```

The command refuses to overwrite an output file. Verified with `python3 -m py_compile tools/audit_mp_match_content_closure.py` and the full 13-map command above. The generated JSON is [`build/m2-mp-render-assets/match-content-closure-v1.json`](../../build/m2-mp-render-assets/match-content-closure-v1.json), SHA-256 `386aba12cd02db1d8a88eeff806c67cb2cece1756c51ee13cdd102db796e9f71`. Inputs recorded in that JSON: schema ELF SHA-256 `05ad9097da392140af5d24f00f9676565f3108134dfce12262d0358fc35e227f`; HCU commit `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; halo-ps2 commit `71183bb0a9adc586cd267b2780c82bbc12cfd95b`; tool SHA-256 `c5f83c68d634aca37dcf80e763fd1d1854339e61eb009cbde7f6ba4a165f2d22`. Every decompressed map has its own source SHA-256 in the JSON, as do per-map converted sections.

## Next evidence needed

1. Establish the production ownership path for every emitted section (including `MODL`, `OTEX`, `ANIM`, TEXS, and LM) from pack open to eviction/unload; instrument allocator owner, bytes, high-water, alignment, and retained source/decode staging on EE/PCSX2.
2. Add match fixtures that spawn the supported maximum local/network player and bot mix, switch through all weapons (including the custom Energy Sword and Fuel Rod provision), mount each vehicle, and exercise representative projectiles/effects. Record dynamic-pool and texture-owner peaks and fail on exhaustion; preserve replay/state parity.
3. Derive the special-weapon asset closure from their actual tag roots and conversion input, then rerun the same closure/conversion measurement. Do not mark the static asset subcheck or Step 8 capacity gate complete based on retail maps alone.

The concrete existing diagnostic entry point is [`tools/run_world_viewer.py`](../../tools/run_world_viewer.py#L1), whose options include `--objects`, `--play`, `--cache-route`, and `--framebuffer`. It is currently a static-world viewer and does **not** instantiate the full HCU MP match arsenal, bot/co-op mix, or a measured object/texture-cache owner. The next useful implementation test is therefore a dedicated match-content residency smoke built on the HCU/EE runtime and exposed alongside the current viewer; running `--objects --cache-route` is only an interim static-scene diagnostic, not acceptance for this inventory.

This work closes a previously missing, reproducible *offline content inventory* slice of Step 8. It does not close Step 7's target-sized BSP-query dependency, the runtime owner/high-water tests, the special-weapon asset gap, or Step 8 as a whole.
