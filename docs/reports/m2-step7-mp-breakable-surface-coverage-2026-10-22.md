# Step 7 MP breakable-surface inventory and CE query

Status: **stock-MP breakable coverage is present for the only map with source breakable surfaces**, Prisoner. A new source-hash-pinned test inventories the collision-surface breakable bit across all 13 stock multiplayer maps; the existing package-backed CE fixture exercises the actual Prisoner hit/broken-miss/restore transitions through `collision_test_vector()`. This does not close the broader Step 7 collision gate.

## All-13 raw source inventory

Added `tests/test_hcu_mp_breakable_inventory.py`. It verifies each decompressed map against the all-MP source SHA pins in `tests/test_hcu_mp_capacity.py:21-34`, locates exactly one BSP and collision BSP, bounds-checks the raw collision-surface block, then counts surface flag bit 3 and collects breakable index/material metadata. The raw `<iiBBh` surface format and bit assignment are corroborated by the CE source: the flag enum declares breakable at bit 3 (`submodules/halo-ce-universal/source/physics/collision_bsp.c:96-102`), and `collision_surface` stores `flags`, `breakable_surface_index`, and `material_index` (`submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h:52-62`).

The inventory found:

| Stock MP source maps | Breakable-flagged surfaces | Invisible-flagged surfaces |
|---|---:|---:|
| Beaver Creek, Blood Gulch, Boarding Action, Carousel, Chill Out, Damnation, Hang 'em High, Longest, Putput, Rat Race, Sidewinder, Wizard | 0 each | 0 each |
| Prisoner | 8: surfaces 401, 457, 902, 960, 2834, 2835, 2838, 2839 | 0 |

Prisoner's breakable records all have flags `9` (two-sided plus breakable), and use bitmap indices 0 and 1. This finding means the product input is not devoid of breakables: Prisoner is the demonstrated stock-MP route; the other maps do not offer a second map-specific breakable case to test.

Reproduction:

```sh
python3 -m unittest discover -s tests -p test_hcu_mp_breakable_inventory.py -v
```

Result: `Ran 1 test ... OK`. The complete map-by-map raw BSP and surface inventory is retained at `build/m2-mp-breakable-inventory-13/inventory.json`, SHA-256 `bf9191b746a978595bf5fc951e2ee5b2e670bcd93f5204ef1f89e923718ed56c`. It contains the source-map and raw-BSP hashes, decoded counts, and all flagged surface tuples. The source map and HP2 package hashes are pinned by the existing all-13 matrix (`tests/test_hcu_mp_capacity.py:21-49`), which rejects missing or mismatched package inputs.

## CE collision path and existing runtime proof

The existing source-derived Prisoner oracle in `tests/test_hcu_scenario_bsp_switch.py:1191-1302` fully decodes the collision surface polygons, derives a ray from raw planes/vertices, finds the duplicate/coplanar group, walks BSP3D and serialized leaf BSP2D routing, and accepts CE's selection only within that proven group. The selected query reaches surface 457 in the group `[457, 2835]`, material 9, breakable index 1. It avoids falsely treating the duplicate surface as a uniquely intersected polygon.

The real package-backed query in `tests/hcu_mp_capacity_main.c:126-141,199-247` checks the loaded CE surfaces/group, proves the breakable bit starts clear, sets it and requires `collision_test_vector()` to hit with the expected surface/index/material/flags/t, clears it and requires a miss, restores the saved full bitmap, and confirms the restored query remains a miss and the BSP bytes/global published pointers are unchanged. CE collision filtering is source-backed: an unextant breakable surface is omitted while selecting leaf surfaces (`submodules/halo-ce-universal/source/physics/collision_bsp.c:1391-1414`); after a leaf returns a candidate, the vector path applies the ignore-breakable flag and otherwise publishes the hit result (`:2253-2290`). No production collision logic was changed for this slice.

The most recent elevated native ILP32 all-13 host semantic run includes the real Prisoner breakable transitions in both lifecycle cycles. It used executable SHA-256 `ecc096846afaa6e22328f4b7c5e49c326add527e8fcd1318a08321b3c095fc55`, link-map SHA-256 `9490fc66f329fe27f3ae726168121b2bf21c9c62326d284da655640fb95d7192`, and `build/m2-mp-weather-wind-13/native-run-final.log` SHA-256 `7992858a40f0d65ae455b0bb083e5715df4769e261cc24c5ebb7f3369b3f3ccc`. That run exited 0 and contains two `collision-breakable-group map=104 surfaces=457,2835 selected=457 index=1 status=passed` rows, alongside 26/26 all-map lifecycle cycles. Its overall marker explicitly says target capacity was not tested.

## Evidence limits

The inventory checks raw retail surface flags; the CE behavior test is one source-derived Prisoner case, not a test of all eight flagged surfaces or of breakable damage/destruction/effects. The run uses host-sized map/BSP/claims buffers and does not prove PS2 EE capacity, timing, target memory placement, rendering, or damage propagation. Continue Step 7's remaining topology and consumer gates and Step 8's target capacity work; do not mark either milestone complete from this result.

Source identities for the native run are parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
