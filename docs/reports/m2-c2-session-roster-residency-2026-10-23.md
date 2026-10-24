# C2 setup-time roster residency profiles

**Disposition: exact selected-image compilation and host-side size measurements; no production runtime admission or C2 fit claim.** The full C1 survival profile remains the retained roster archive. `tools/hcu_setup_residency.py` compiles a separately selected roster into one immutable CTAG image before any CE tag-arena allocation. The resulting CE image keeps all selected and transitive tag pointers valid for the entire match; this approach does not evict tags, rebind pointers, or predecode the full union.

## Rule checked against the acceptance contract

C1 requirement 4 in [`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md#L373) says to keep CE data resident for its actual pointer lifetime and store separately addressable render/media payloads so the complete selectable roster need not be decoded into one permanent copy. The session selection preserves the first rule: the selected CTAG remains resident until match teardown. It does not change C1 acceptance requiring each archived survival profile to bind all 255 combat/mounted occurrences ([same plan](../../plans/7.hcu-remake-m2-m4.md#L384)); it produces an additional setup selection from the retained actor catalog.

## Compiler contract

The compiler consumes the retained C1 actor roster and profile specs, resolves each selection by source-map name, source datum, path, and pinned source-map SHA-256, then filters only the actor roots. It keeps the selected C1 scenario's non-roster roots, including all schema-derived BSP tag dependencies, four Spartan asset roots, and the energy sword, gravity rifle, and fuel rod roots. It imports through the existing schema-driven `import_profile()` traversal, which follows typed tag references and tag indexes, then validates the resulting CTAG through the existing compiled-schema walker. The selected actor recipes are resolved back to their output tag datums; missing recipe closure fails compilation.

The exact setup input is chosen before CE allocation. The output CTAG is the whole CE image for that choice. Production integration must load only this selected image and keep it resident through match teardown. The existing C1 union package remains the archive used to offer every retained variant for later selections; it is not a fallback image for this setup.

Reproduce the six sample profiles and CTAG outputs with:

```sh
python3 tools/hcu_setup_residency.py --samples \
  --output-dir build/m2-c2-session-residency-2026-10-23
```

The per-selection manifests include the selected variant identities, exact roots, resolved placement recipes, imported actor-group tags, source-map hashes, CTAG digest, schema image bytes, relocation staging, and the selected map's BSP payload size. Sample CTAG digests are in the ignored build output's `matrix.json`.

## Blood Gulch measurements

All samples retain the same Blood Gulch scenario and BSP dependency closure. The profile includes 45 explicit BSP dependency roots, four Spartan asset roots, and all three special-weapon roots. Counts below are exact host importer output; the `CE + BSP` column is a payload lower bound against the nominal 10 MiB map/render backing.

| Setup selection | Retail variants selected | Local players + Spartan bots | CE image | BSP payload | CE + BSP | Payload margin to 10 MiB |
|---|---:|---:|---:|---:|---:|---:|
| Single Marine | 1 | 1 + 0 | 6,869,365 B | 1,303,092 B | 8,172,457 B | 2,313,303 B |
| Single Marine, 4P + 4 bots | 1 | 4 + 4 | 6,869,365 B | 1,303,092 B | 8,172,457 B | 2,313,303 B |
| Mixed three | 3 | 1 + 0 | 8,996,571 B | 1,303,092 B | 10,299,663 B | 186,097 B |
| Mixed seven | 7 | 1 + 0 | 11,492,562 B | 1,303,092 B | 12,795,654 B | **2,309,894 B over** |
| Mixed seven, 4P + 4 bots | 7 | 4 + 4 | 11,492,562 B | 1,303,092 B | 12,795,654 B | **2,309,894 B over** |
| Mounted Dropship gunner | 1 mounted | 1 + 0 | 4,795,978 B | 1,303,092 B | 6,099,070 B | 4,386,690 B |

The single case selects `a30:characters\marine\marine assault rifle`. The three-variant mix adds an `a10` Elite Major and a `d40` Grunt SpecOps with fuel rod. The seven-variant mix adds a Jackal, Hunter, Flood combat Elite, and Sentinel. All three required special weapons remain rooted in every measurement. The four-player/four-bot profile has the same CE image and CTAG digest as its one-player/seven-variant counterpart: four players and four bots reuse the same four Spartan asset roots, so those counts do not duplicate tag bytes. The mounted sample selects the retained `a30` Dropship turret gunner occurrence and includes its `vehi:c_dropship` parent and seat-9 placement recipe.

The selected root counts are not the final tag counts. The importer follows their full transitive closure: the Single Marine image contains 2,867 tags and 10 actor-group tags; Mixed Three contains 3,581 tags and 16 actor-group tags; Mixed Seven contains 4,101 tags and 29 actor-group tags; the mounted sample contains 2,236 tags and 7 actor-group tags. Those additional actor-group records are in the manifests and are brought in by real typed references/indexes from the scenario, BSP, selected recipes, and mounted parent.

The current full-union Blood Gulch C1 archive is **25,612,462 CE bytes** with package SHA-256 `07879a43baf4beb10cd01f81f494f0a864b69aaa2299018e1e7e1d15b1837c35`. The setup compiler marks that image as not loaded for every selection. All **255** retained catalog occurrences (248 combat and seven mounted) remain addressable by source map, datum, path, and source-map hash; this compiler can select either catalog kind. Its emitted setup image contains the map's required closure plus selected recipe closure, instead of all 255 archive roots. Production must wire this pre-allocation choice before it is a runtime residency guarantee.

## Individual recipe lower-bound matrix

The `--all-recipes` mode compiled one CE closure for each of the C1 roster's **75 unique placement recipes**, using its pinned canonical source occurrence and the same worst-CE base map (Blood Gulch). Every image retained the Blood Gulch scenario/BSP closure, all four Spartan asset roots, and sword/gravity/fuel-rod roots. The machine-readable result is [`m2-c2-session-residency-recipes-2026-10-23.json`](m2-c2-session-residency-recipes-2026-10-23.json); it carries all 255 occurrence-to-recipe mappings, per-profile CTAG and report hashes, and source-map/schema/profile pins. Detailed per-recipe roots are reproducible under `build/m2-c2-recipe-residency-2026-10-23/recipes/`.

**No single recipe exceeds** the remaining nominal map/render payload after the fixed Blood Gulch BSP (`10,485,760 - 1,303,092 = 9,182,668 B` for CE). All 75 fit this *payload floor*.

| Recipe | Canonical selected occurrence | CE | CE + BSP | Remaining nominal bytes for all other owners |
|---|---|---:|---:|---:|
| Largest | C10 Marine shotgun combat | 7,014,967 B | 8,318,059 B | 2,167,701 B |
| Smallest | C20 Flood infection | 4,782,999 B | 6,086,091 B | 4,399,669 B |

This answers only the single-recipe capacity question. A 2.17–4.40 MiB remainder must also hold measured renderer/texture owners, alignment, relocation overlap, claims/indexes, validator scratch, and other live owners; no such combined fit is established. It also does not qualify arbitrary mixed-roster combinations, as the seven-variant case above already exceeds the full payload budget.

## Limits and next integration point

The Single Marine profile leaves 2,313,303 bytes in the nominal payload arithmetic, but this does not establish an arena fit. Mixed Three leaves only 186,097 bytes before relocation staging, tag claims/indexes, validation scratch, alignment, texture/render/DMA owners, and other runtime storage. Mixed Seven already exceeds the full 10 MiB by 2,309,894 bytes before any of those owners. Therefore setup selection creates a concrete profile-size control, but an arbitrary mixed roster is not thereby admitted; the target setup must reject selections whose exact profile and full owner ledger do not fit.

The measurements exclude the CTAG relocation table from resident CE image size; the table is reported separately as loader staging. BSP values are C1 payload extents, not target runtime high-water. Media chunk streaming, decoded-media scratch, renderer residency, GS upload lifetime, runtime UI selection, and target EE qualification remain separate gates. The outputs are host-generated CTAGs and do not prove that production runtime selection has been wired to consume them.

The in-progress diagnostic-only group attribution in [`tools/ctag_schema_walk.py`](../../tools/ctag_schema_walk.py) adds report metadata for schema spans. It does not alter pointer normalization, CE image bytes, or profile walk decisions; this tool reuses the same importer but binds its own current script/walker hashes in its output manifests.
