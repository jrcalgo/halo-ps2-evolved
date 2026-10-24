# M2 Step 7 — multiplayer nested BSP relocation extent census

Date: 2026-10-22. This implements the next narrow slice from [`m2-step7-nested-bsp-field-consumers-2026-10-22.md`](m2-step7-nested-bsp-field-consumers-2026-10-22.md): prove that the actual CE-loaded nested blocks remain within the correct mounted owner spans. It does not prove the consumers produce CE-parity behavior.

## Implementation and owner bounds

The isolated assertion helper is [`tests/hcu_mp_nested_bsp_census.h`](../../tests/hcu_mp_nested_bsp_census.h), called after successful `scenario_load()` from the existing two-cycle, 13-map package fixture ([`hcu_mp_capacity_main.c`](../../tests/hcu_mp_capacity_main.c)). The test runner retains this run under the separate path `build/m2-mp-nested-census-13/` when `HCU_MP_CAPACITY_RETENTION_DIR` is set, rather than overwriting the prior fixed-path artifact.

The census obtains owner ranges from actual load metadata, not guessed neighboring pointers:

- Scenario/tag owner: `physical_memory_get_tag_cache_base_address()` plus CE `cache_file_globals.header.tag_data_size`. The scenario root, scenario structure-BSP-reference block, and sound-scenery placement/palette blocks must fit this bounded extent.
- Active B000 owner: the loaded `scenario_structure_bsp_reference.base_address` and its source `file_size`; the base must equal the configured structure-BSP-cache base and file size must fit that cache capacity. The published BSP root and each non-empty target block must fit wholly within this active section extent.
- Extents are overflow-checked as `count * schema-stride` before comparing against `owner_bytes - (address - base)`. Strides use CE record layouts: `structure_bsp` cluster `0x68`, runtime decal `8`, detail-data root `0x40`, detail cell `0x20`, detail instance `6`, count `2`, z-vector `16`, lens-flare marker `0x10`, sound-scenery placement `0x28`, and palette entry `0x30`. Compile-time assertions check the duplicated private CE cluster/detail layouts against their source sizes.
- For each cluster, non-empty runtime-decal and lens-flare-marker index/count ranges must fit the corresponding root blocks. HCU’s recursive schema remains responsible for tag-reference and block-index validation; this census independently checks post-load address/extent ownership and published index ranges.

The path follows the production ownership semantics in CE: `cache_files.c` assigns each BSP reference a fixed cache base and validates the structure header and all requested extents against that reference's `file_size` ([`cache_files.c:1427-1488`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1427)); `structure_bsp` has dedicated pathfinding, decal, detail-data, and lens-marker blocks ([`structure_bsp_definitions.h:178-220`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h#L178)); recursive field declarations and nested detail validation are in [`tag_schema_collision.c:859-886,934-979,1532-1574`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L859). Sound-scenery object/palette arrays are distinct scenario-owned tag data ([`scenario_definitions.h:279-280`](../../submodules/halo-ce-universal/source/scenario/scenario_definitions.h#L279), [`tag_schema_scenario.c:824-828,1311-1313`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_scenario.c#L824)).

The legacy BSP `markers` block is intentionally not dereferenced: CE’s schema explicitly omits it and says it is never read ([`tag_schema_collision.c:934-936`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L934)). Its payload remains preserved/opaque; this census does not claim its pointer is relocated.

## Verification

Exact command, run outside the sandbox because native ILP32 is blocked there with SIGSYS:

```sh
HCU_MP_CAPACITY_RETENTION_DIR=build/m2-mp-nested-census-13 \
python3 -m unittest discover -s tests -p test_hcu_mp_capacity.py -v
```

Result: **1 test passed in 82.633 s**. The runner validated **26 census rows**: two successful CE load/query/unload cycles for every stock MP map ID 101–113, plus the existing collision, location, PVS, fog, weather, sound, and late-B000 failure/cleanup/retry assertions. The census itself used host-only 16 MiB tag and 8 MiB BSP arrays; it is not target-capacity evidence.

Observed census data (each row appeared twice, once per cycle):

| Map | Path surfaces | Path edges | Runtime decals | Detail roots | Lens-flare markers | Sound-scenery placements |
|---|---:|---:|---:|---:|---:|---:|
| beavercreek | 2476 | 0 | 8 | 1 | 0 | 8 |
| bloodgulch | 4916 | 0 | 8 | 1 | 0 | 2 |
| boardingaction | 3693 | 0 | 55 | 1 | 207 | 0 |
| carousel | 1117 | 0 | 0 | 1 | 0 | 0 |
| chillout | 1545 | 0 | 0 | 1 | 0 | 0 |
| damnation | 4053 | 0 | 0 | 1 | 22 | 3 |
| hangemhigh | 1695 | 0 | 2 | 1 | 0 | 0 |
| longest | 1227 | 0 | 2 | 1 | 0 | 0 |
| prisoner | 2840 | 0 | 0 | 1 | 0 | 0 |
| putput | 5429 | 0 | 7 | 1 | 892 | 0 |
| ratrace | 1474 | 0 | 0 | 1 | 0 | 0 |
| sidewinder | 6774 | 0 | 24 | 1 | 0 | 0 |
| wizard | 1559 | 0 | 0 | 1 | 0 | 0 |

The all-zero `pathfinding_edges` counts are an observation about these 13 package images only. They do not establish that the member is semantically unused; pathfinding-surface bytes are present and are the member read by CE AI path construction. The fixture includes bots through the existing HCU code closure but does not generate a bot path query.

Artifact identity: parent/HCU/halo-ps2 pins `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. ELF SHA-256 `4623d6d77323c1f38ee4eaf977d9c6fca0e82d0db4e995d67cea3e69b1db0814`; link-map `60666138eaa277b45e8d63dc495e7c2961e7d3db58573290dfba9f0f257dfcdd`; native run log `a9a1307aaf6f15a29e6a3dab2bd13d4ee22634cc1c5b01ef458a032a92c556a1`; manifest `1bbdbd2e9a3a62db94560f59a411cd938965a54def091c3c91102d694e5343c3`. Manifest: [`build/m2-mp-nested-census-13/manifest.json`](../../build/m2-mp-nested-census-13/manifest.json). Census/header SHA-256 `1df0e0a2efbbda7faef20b9d121a1f339cea63e9da2791c83ce8c882b77e59fb`; integrated fixture C `1bce6f99b619ef55c4135f241cabcc0cbb650ccf3b9571456f7e2019266ec48c`; runner `bef14ffd28aa24f41d5364a99e6cc78e96df552abcb3d7d470c364c53d5b14fe`.

## Limits / next slice

This closes only a bounded post-relocation address and byte-extent census for the listed structures. It does not compare fields against a raw-source per-field oracle, invoke decal PVS lifecycle, detail-object camera-cell selection, AI pathfinding, lens-marker clustering/presentation, sound-scenery object creation/audio, or exercise the PS2 rendering/audio adapters. The nested `markers` block remains deliberately outside the test because no valid relocated pointer contract exists. The 16/8 MiB host arrays do not prove Step 8 capacity, PS2 placement, map admission, or EE performance. Step 7 remains open pending those semantic consumer tests and its remaining collision/owner gates.
