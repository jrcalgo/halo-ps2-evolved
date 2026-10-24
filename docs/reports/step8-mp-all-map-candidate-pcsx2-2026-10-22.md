# Step 8 stock multiplayer map target-capacity diagnostic

## Candidate capacity decision

The same bounded candidate split can hold each of the 13 stock multiplayer
map CTAGs and its active BSP image plus relocation table. The maximum CTAG is
Blood Gulch at 4,477,116 bytes, rounded to a 4,477,120-byte tag span. The
maximum BSP owner payload is Sidewinder at 1,993,704 bytes, rounded to a
1,993,712-byte BSP span. Together these use a 6,470,832-byte map owner, which
exceeds the existing 6,291,456-byte `current_bsp` span by 179,376 bytes.
Sidewinder is the limiting combined resident floor at 6,371,864 bytes, leaving
98,968 bytes in the candidate map owner before omitted owners and transition
overlap.

The diagnostic recarves the existing adjacent `current_bsp` and
`texture_cache` allocations into a 6,470,832-byte map owner and a 4,014,928-byte
texture span. Total backing remains 10,485,760 bytes. The all-map host texture
section fixture bound this texture span for all 13 maps: decoded owner peak
2,144,672 bytes, CRC-failure transient peak 2,550,720 bytes, and shared section
scratch peak 98,352/524,288 bytes. This supports the tested section workload;
it does not prove full runtime texture residency or rendering.

The exact map/package rows and hashes are retained in
[`tag-bsp-capacity-floor-v2.json`](../../build/m2-mp-render-assets/tag-bsp-capacity-floor-v2.json), SHA-256
`5130b6332f6e395481f70ea1445a3ac161845dcaa5fae228abac0a5bb788d19a`.
The retail source map hashes and independent collision rays are in
[`mp-collision-shared-edge-source-oracle.json`](../../build/mp-collision-shared-edge-source-oracle.json), SHA-256
`ff26f43f8e474f59397c441d246b93e3a45f39fdaefca555d5eb7e3bfb54b95a`.

| Map | CTAG bytes | BSP image + relocations | Pair floor | HP2 package SHA-256 |
|---|---:|---:|---:|---|
| Beaver Creek | 4,319,568 | 730,164 | 5,049,732 | `4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc` |
| Blood Gulch | 4,477,116 | 1,303,056 | 5,780,172 | `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011` |
| Boarding Action | 4,358,612 | 1,354,120 | 5,712,732 | `2c12e7c0cf555698b837397666b1f343a6864fe16deeffb0b0d4a007e869acd0` |
| Carousel | 4,277,864 | 515,212 | 4,793,076 | `e24191ed1e660dfb3c9c9bcd88abcff61c366690f6d903f3b0622eb2c2e751b4` |
| Chill Out | 4,252,432 | 573,380 | 4,825,812 | `727abc7401a530892f1136f082a6254544915e0d85f2a068f63d9530189b1bf0` |
| Damnation | 4,345,868 | 1,326,780 | 5,672,648 | `ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d` |
| Hang 'Em High | 4,246,076 | 595,812 | 4,841,888 | `1e2a4df7a5ba17d0742bd30484fcfe63db011e6c47a87ac0f2d06ac6f5cab58f` |
| Longest | 4,263,624 | 377,352 | 4,640,976 | `6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b` |
| Prisoner | 4,241,088 | 888,300 | 5,129,388 | `3bb10f06c785da93fe0f7257be9f06519b7ccb6c155801a7a04a5e6d56352136` |
| Putput | 4,250,464 | 1,643,008 | 5,893,472 | `6d66e4ecf9c51b3ae417d85356de9ff66c14bc9fc19dd4a2bd2a2954f6b4f3bd` |
| Rat Race | 4,270,452 | 550,768 | 4,821,220 | `a735d4a5bef86cc7277ae888a1ef9da25f28f0ab6e45dff010da53dc41e685da` |
| Sidewinder | 4,378,160 | 1,993,704 | 6,371,864 | `968ab65ea7ae6fbd15925ed28eb0f8eafc267c78f53150b59b4cc1dea2d017f5` |
| Wizard | 4,259,188 | 556,908 | 4,816,096 | `00bf468d4d8c96e234ef21e5bfb59b410cac7c3e8c9f4f848ea20fbfacf01c57` |

## Diagnostic implementation and inputs

Only the `HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC` ELF admits these maps. The
ordinary preflight branch remains UI-only. The diagnostic visits the 13 maps
in table order, performs a CE scenario load, queries every cluster PVS row,
checks one positive collision hit against the independent source-derived
surface/material tuple, unloads, verifies CE map globals are unpublished, and
checks the outer canaries after every unload. Its completion marker is emitted
only after every row passes.

The final ELF is
`build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf`,
SHA-256 `beee81293b9059ca2f51c04e6b49897e607e332750fe7f14fa201c2077258bf0`.
Build report SHA-256 is
`613b3e3bf0f1cf5a45679050df9cb37839973379a5b0b644937af43c809e4c7c`.
The HLE `maps/` directory contains all 13 hash-pinned decompressed map sources
and corresponding all-BSP HP2 packages.

Build provenance for this exact ELF: parent HEAD
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU HEAD
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 HEAD
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. SHA-256s of the compiled dirty
inputs (and the independent source/fixture artifacts) are recorded below so
the diagnostic can be reproduced without treating the dirty worktree as an
implicit source pin:

| Input | SHA-256 |
|---|---|
| `src/stream/hcu_main.c` | `13dbb8ec50a4582a2d11b532ad5c5b11ed6570b898b45bfc37c465d80957fe6c` |
| `src/stream/hcu_map_service.c` | `149e81bc5c2bde41808261122a6eece035155981345cff9711fb2979e2d03087` |
| `submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c` | `cfe4d4bfb5afa3bda46e955be762d590968f0de787666b684a682f517558c956` |
| `tools/hcu_ps2_link.py` | `243660ce3d29808ed93d7c909019e71611cc2211d821c49b8835de4927d37b3c` |
| `tools/hcu_parent_link_probe.py` | `2067a4a150d9bd9d226f3926a06a87a9975c35a9b02abbb93a94e607b399a9a1` |
| `tools/ee-world.mk` | `ab3e452e202d9ece25e40bbb0d48484d6af918f75b090e6f1f8b2a2feeff6b26` |
| `tools/audit_mp_collision_edge_pairs.py` | `f59b1ed39ebd764ad28a8868039359930415700ea135d195950b1d4cc83396e3` |
| `tools/audit_mp_tag_bsp_capacity_floor.py` | `a49ea9825c9af93cd352abc03ed91e3c60549f98f8c783f12291b39b15839201` |
| `tools/test_halo_ps2_mp_texture_runtime.py` | `039e31d0e705fe89112a83e68c096d1075f67204838b2695898227d3a720ebb6` |
| `tools/verify_hcu_mp_candidate_combined_textures.py` | `73761d834e293efac7a919e70ab83a5b629578d3119079fafb459946c4970dec` |
| `build/mp-collision-shared-edge-source-oracle.json` | `ff26f43f8e474f59397c441d246b93e3a45f39fdaefca555d5eb7e3bfb54b95a` |
| `build/m2-mp-render-assets/tag-bsp-capacity-floor-v2.json` | `5130b6332f6e395481f70ea1445a3ac161845dcaa5fae228abac0a5bb788d19a` |

## Guest status

The first recompiler attempt used a 300-second timeout and stopped while
loading Sidewinder, after 11 maps had completed their query/unload/canary
checks. It did not reach the 13-map completion marker and is a timeout, not a
pass. Result SHA-256:
`c92935e3a31c7ffb065717af7b44b77385c903d58466ba10140215313e25b921`;
partial guest log SHA-256:
`65024d7763daeb3f44d83b45cde12e27ccc0421bae9c5926e0ba4e97a0c11787`.

The 900-second recompiler rerun passed all 13 map rows, including every PVS
row, its oracle collision hit, and unload/canary checks. The log ends with
`step8-mp-capacity-complete maps=13 query_only=1`; game initialization and the
stable completion marker were observed, and `host_assets_unchanged=true`.
Result SHA-256:
`a8cc5da2c8c3a04b3aa5277456da743b370fe5dba69937bb5618292bcbd5a9a1`;
guest log SHA-256:
`d871200f50b2259f819f024a8f238951c783042aebe55c6fb411a3335b458a25`.
This run used the exact ELF SHA above.

An earlier interpreter attempt was intentionally interrupted during Rat Race
after 10 completed rows; it was not a guest crash. It was superseded by the
serial rerun below. The final interpreter rerun passed all 13 maps in order:
all 13 query rows report collision hits and `pvs_rows == clusters`, all 13
unloads report `guards=ok`, and the log ends with
`step8-mp-capacity-complete maps=13 query_only=1`. The harness observed game
initialization, the completion marker stable for 5.017 seconds, and
`host_assets_unchanged=true` (the before/after UI map and HP2 hashes match).
Wall time was 647.23 seconds. Result SHA-256:
`4d3c3b4c8cd1ff3e8bb53553c6aae526ba5bcd419ed6626f22c66dbaa66d4ade`;
guest log SHA-256:
`7dae6dc1f90a62f9d60d4ca256faaa2f27e2852dfae44ab86efd2598600f0178`.
It used the same exact ELF SHA above. An ordered-row check independently
verified the 13 map starts, query rows, and unload rows against the expected
stock-map order.

## Limits

The candidate establishes arithmetic room for the audited CTAG/BSP corpus and
the tested host texture-section workload, with successful all-13 guest
query/unload runs in both PCSX2 modes. It does not prove a production memory
binder, complete match-time asset closure, texture pins/eviction, renderer
residency, multiplayer gameplay, EE hardware performance, or campaign maps.
Production budgets and normal map admission remain unchanged. Step 8 remains
open pending the separate common multiplayer owner/lifetime gates.
