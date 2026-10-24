# Step 7 multiplayer sound-environment selector evidence

Date: 2026-10-21. This is a focused host-only follow-up for the multiplayer
scope in [`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md).
It exercises two retail multiplayer packages already used by the production-
sized CE lifecycle fixture; it does not close Step 7 or prove audio playback.

## What now passes

The test now derives environment palette candidates from the raw Xbox BSPs for
Longest and Blood Gulch, emits a generated golden, loads each package through
the real CE scenario lifecycle, and calls CE's actual
`scenario_get_sound_environment()` selector. The call uses the CE
`local_player_get_player_index()` implementation from `players.c` (compiled in
the existing player-PVS host TU), the controlled observer-camera bridge, real
relocated BSP palette entries, and the real CTAG sound-environment definition
through `sound_environment_definition_get()`. The CE selector is in
[`scenario.c:1310-1435`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1310);
its local-player iteration is explicit at `:1341-1347`, its BSP palette and
background selection at `:1377-1404`, and its environment interpolation at
`:1420-1435`. The local-player lookup body is
[`players.c:712-724`](../../submodules/halo-ce-universal/source/game/players.c#L712).

The test fixture and independently derived expected rows are in
[`hcu_mp_capacity_main.c:10-40`](../../tests/hcu_mp_capacity_main.c#L10),
[`hcu_mp_sound_environment_host32.c:47-124`](../../tests/hcu_mp_sound_environment_host32.c#L47),
and [`test_hcu_mp_capacity.py:62-111,190-219`](../../tests/test_hcu_mp_capacity.py#L62).
For each map, the raw BSP oracle expects BSP 0, cluster 0, palette 0, with these
retail datum references:

| Multiplayer map | Sound-environment datum | Background-sound datum |
| --- | ---: | ---: |
| Longest | -401275233 | -401406307 |
| Blood Gulch | -394066163 | -394197237 |

On both maps, the CE query runs twice per load cycle and twice across the
fixture's two load/unload cycles. The fixture checks the raw-derived palette
and tag identities, non-null CE tag resolution, return pointer, selected
background datum, no water-boundary transition for the selected fog-free
clusters, all 12 CE-interpolated environment values on both calls, unchanged
BSP publication/index, and unchanged collision-user depth. The
production-sized *host* limits remain tag 4,477,120 B, BSP 1,814,336 B, claims
786,432 B, map owner 1,048,576 B, and section scratch 524,288 B.

Command and result:

```text
python3 -m unittest discover -s tests -p test_hcu_mp_capacity.py -v
Ran 1 test in 9.589s — OK (native ILP32, outside the sandbox)
```

The retained guest-unrelated artifacts are bound by
[`manifest.json`](../../build/m2-mp-production-capacity/manifest.json),
SHA-256 `b3d99afccdd5d63d7d615c01aa227e6209f1ef14f7bb51b87adb6ee591dd9d1f`.
It records parent/HCU/halo-ps2 pins
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c` /
`6933490b2d16bb1c637295b6a0f3880ba23a7d56` /
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`, executable SHA-256
`3684f5195f8aabfbfa94a22312ee277e64dc687982b1a19746a29c6adfa27c7e`,
link-map SHA-256
`d65c337975688e675859ff048de610276816a9bac0c5cb406dbc867f15c6ef50`, and
generated raw-oracle header SHA-256
`57d1659852bed2c180b4d4660aebc41c2fa5ff003fd92c07e1f13e76a4ed377c`.
Package/source map SHA-256 pairs are Longest
`6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b` /
`e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` and
Blood Gulch
`ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011` /
`9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`.

## Limits and next work

This is two of 13 multiplayer maps and one fog-free listener per map. It does
not test four-player priority arbitration, fog precedence or water entry/exit,
`scenario_fog_at_point()` (which remains an unresolved bot-perception
behavior), sound request scheduling, actual sample playback/SPU2, weather or
wind cadence, another map's package, EE memory placement, PCSX2 gameplay-map
load, or rendering. The test's host arena capacities do not solve Sidewinder's
71,216-byte raw CTAG+BSP overage. Step 7 and Step 8 remain open.

Halo-64 informed only the state-versus-presentation boundary; no N64 cuts or
sound semantics were copied. REA was not used for this selector: CE source and
raw retail BSP/tag bytes provide the relevant oracle, while the unresolved fog
perception body needs a retail-specific oracle rather than a second source stub.

## All-13 raw BSP selector inventory refresh (2026-10-21)

The same focused fixture now inventories the raw BSP palette references for all
13 stock multiplayer maps (source-map SHA-256 values and rows are retained in
[`mp_sound_environment_source_inventory.json`](../../build/m2-mp-production-capacity/mp_sound_environment_source_inventory.json), SHA-256
`73ab20b7ecf5b0c78cf87ee41aad5f8103ab51694453f7b08c30488ed1324716`). Ten
maps contain at least one cluster meeting this narrow *fog-free environment
palette* selector precondition. Beaver Creek, Chill Out, and Damnation have no
such candidate under the oracle; this is inventory, not proof their sound
selection is empty in every runtime condition. Only Longest and Blood Gulch
are still executed through CE's package-backed selector harness. The inventory
therefore expands source coverage to 13/13 but does not turn into CE runtime
coverage for the other eleven.

After adding a one-shot late-B000 stream failure to the Longest case, the
refreshed native ILP32 run passed outside the sandbox:
`python3 -m unittest discover -s tests -p test_hcu_mp_capacity.py -v`
(1 passed, 12.146 s). The fixture confirmed a decoded prefix reached the CE BSP
destination, then verified the failed candidate was unpublished, CE globals
were null/unloaded, map owner and section scratch rewound, source descriptor
closed, and a same-process Longest preflight/load/query retry passed. Current
manifest SHA-256 is
`cfa9a9b387a3302006c041aadd903869577645b5c3a46a3247636cff7338d462`; it binds
ELF `e8732b9d14f14e156e5579f375afc88d032ceef58327b40b6279f9e96537e271`,
link map `465eafbf6d461c68d6e7d24b936d235dbe051be214ed04e2aaa005cd778dfb55`,
run log `2b3ed09aaf9ce76050c8cb0923158fe55a6dd3bd25bdb3a0839a91f4619d772a`,
the generated sound golden, actual generated C inputs, source catalog, all 13
raw map hashes, and the two exercised packages. It explicitly records
`ee_evidence: false`. This is one composed MP rollback/retry subcheck on
Longest, in addition to the prior Longest/Blood-Gulch successful lifecycle
queries. Collision diversity, bot fog, weather/wind, playback, rollback on
other maps, and target-capacity query evidence remain open.
