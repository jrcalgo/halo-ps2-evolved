# Step 8: source-backed Energy Sword and Fuel Rod asset closure

## Result

The current extracted retail CE source corpus already contains real CE tag roots for both retained custom multiplayer weapons, even though neither root occurs in any of the 13 stock multiplayer maps:

| Custom MP weapon | Existing retail source root | Schema-walked refs | Offline converted outputs |
|---|---|---|---|
| Energy Sword | `weapons\\energy sword\\energy sword` in `data/retail/weapon-audit-maps/a50.map` | 34 tags; 0 unresolved references; 0 `antr`; 1 `mode`; includes the `weap`, melee `jpt!`, 2 `effe`, particle/decal/bitmap/shader/light/sound references | MODL 9,616 B; OTEX 13,152 B; empty ANIM section 80 B |
| Fuel Rod | `weapons\\fuel rod gun\\fuel rod` in `data/retail/weapon-audit-maps/c40.map` | 96 tags; 0 unresolved references; 0 `antr`; 2 `mode`; includes the `weap`, `proj`, 11 `effe`, 2 `jpt!`, particles, 8 `snd!`, shader/bitmap and sound dependencies | MODL 105,392 B; OTEX 23,008 B; empty ANIM section 80 B |

These are retail CE source tags taken from campaign-map images in the already-extracted 24-map corpus, not user-made Custom Edition tags and not evidence that campaign content is in multiplayer scope. The result gives a concrete source basis for porting these requested weapons into the multiplayer asset pipeline. The remaining integration is to provision an explicit custom-MP asset source or modify/package each required multiplayer map so that these roots and their full dependency closures are available to runtime tag lookup and the normal converters.

The CE weapon schema has first-person model and animation references at [`weapon_definitions.h:72-77`](../../submodules/halo-ce-universal/source/items/weapon_definitions.h#L72). In both selected roots, those references are null (`tag_id == 0xffffffff`); the recursive closures contain no animation-graph (`antr`) tags. Therefore the retail CE assets do **not** supply a first-person model or animation for either weapon. Keep the project's separately sourced sword pose/model and Fuel Rod first-person presentation work; do not mistake the converted world-model and effect closure for a complete first-person package. Sword's current user-approved Halo 2 pose/model assets and the project-authored gravity-rifle work have distinct provenance and are not pulled into this CE tag closure.

Fuel Rod's root carries 42 `file_data` records declaring 348,012 bytes, and its reached bitmaps reference 747,264 unique source pixel bytes (two source images were reported undecodable by the current bitmap metadata reader). Sword has one `file_data` record declaring 25,920 bytes and 163,712 unique bitmap pixel bytes. These are source extents, not bytes to add to the converted pack sizes or a runtime-residency estimate. Audio is a dependency inventory only: Fuel Rod reaches eight `snd!` tags and Sword one, but this audit does not convert or qualify sound payloads/playback.

## Reproduction and identity

The audit uses the compiler-derived HCU tag schemas from ELF SHA-256 `05ad9097da392140af5d24f00f9676565f3108134dfce12262d0358fc35e227f`, with HCU commit `6933490b2d16bb1c637295b6a0f3880ba23a7d56` and halo-ps2 converter commit `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The audit corpus was extracted from the retail XISO whose recorded SHA-256 is `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258`; that original XISO is not present in the build tree, so this reproduces from the retained map inputs and their direct SHA-256 values:

- Sword source map `a50.map`: `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`.
- Fuel Rod source map `c40.map`: `d7465f07a675a86785a329b9ab3d8a5a20b25b7ca7d05bafeb7ca87b02b20be9`.
- Generated inventory JSON `build/custom-weapon-capacity/closure-v1.json`: `dad712bce1723373b3ead28aa4731c1b6b40c189d016d7527130c7d0af33789b`.
- `tools/audit_custom_weapon_asset_closure.py` SHA-256: `811fcbab259feb62ed32a4a9e773da4ff11c94139b0019015b3d3b81dd81f2b1`.
- Imported schema-walk/converter driver `tools/audit_mp_match_content_closure.py` SHA-256: `c5f83c68d634aca37dcf80e763fd1d1854339e61eb009cbde7f6ba4a165f2d22`.

From repository root (choose a new output path; tool refuses to overwrite):

```sh
python3 -m py_compile tools/audit_custom_weapon_asset_closure.py
python3 tools/audit_custom_weapon_asset_closure.py \
  --maps data/retail/weapon-audit-maps \
  --schema-elf build/hcu-ps2-closure/all-no-bootstrap-memory-m2-ui-lifecycle/halo-local.elf \
  --output build/custom-weapon-capacity/closure-reproduced.json
```

The same tool ran successfully at the output path above. It invokes the linked-schema walker in [`audit_mp_match_content_closure.py`](../../tools/audit_mp_match_content_closure.py) and the pinned halo-ps2 model/animation converters; it does not write extracted source tag data into the checkout. The current generated JSON is retained as a build artifact for review, not a committed runtime package.

## Step 8 interpretation and remaining provisioning

This closes only the source-root and offline converted-content inventory question for these two weapons. It does not close Step 8 capacity or asset integration: converted byte lengths are independent outputs, not concurrent EE residency; there is no PS2 arena/high-water measurement, map admission test, weapon-switch texture pin test, runtime sound test, custom map round-trip, or PCSX2/EE match run here. Nor does this show the complete Halo 2 sword first-person asset path: the sword work in this port intentionally uses the separately sourced user-approved pose/model rather than a retail CE FP graph.

For complete multiplayer support, provision and test:

1. A versioned custom weapon source bundle (or deterministic map patch) that copies each `weap` root and all schema-walked referenced tags into the runtime-loadable custom-MP tag image. Preserve the dependency paths and tag IDs/references through the actual converter; do not manually recreate the CE roots.
2. The sword's separate first-person model/pose source and the Fuel Rod first-person model/pose source (the CE references are null), plus any animation/marker adapter data required by the HCU first-person interface. Record their independent source hashes and ownership.
3. Required bitmap/file-data payloads and an explicit audio extraction/conversion route. Resolve Fuel Rod's two undecodable bitmap metadata records before treating its visual package as lossless.
4. A repeat of this closure against the final custom multiplayer bundle, plus converted-pack hash checks, runtime tag resolution, weapon select/swap tests, and measured EE `resident_gameplay`, `texture_cache`, `dynamic_simulation`, and audio high-water under the supported maximum player/bot mix.

No runtime residency, PS2 hardware compatibility, or completion of Step 8 is claimed by this report.
