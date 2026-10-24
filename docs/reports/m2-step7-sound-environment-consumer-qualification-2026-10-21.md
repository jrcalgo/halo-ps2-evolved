# M2 Step 7 — CE sound-environment palette consumer qualification

Date: 2026-10-21  
Scope: execute the production Halo CE listener sound-environment selector
against the currently published BSPs from the audited `a30` and `a50` HP2
packages. This closes a selected host consumer subcheck only; it does not
qualify audio playback, target BSP capacity, or a gameplay map on PCSX2.

## Implementation and evidence

The package transaction now roots `scenario_get_sound_environment()` from
`source/scenario/scenario.c` and links CE's actual default sound-environment
definition. In CE, the function iterates four local-player slots, reads the
observer camera's cluster, arbitrates fog and cluster palette environments by
priority, selects the matching background-sound reference, tracks water-boundary
transitions, and blends the environment fields ([`scenario.c:1310-1452`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1310)).
The structures it consumes are the BSP's 0x68-byte cluster records and
0x50/0x74-byte sound/background palette entries
([`structure_bsp_definitions.h:89-134`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h#L89)).

The existing retail CE transaction fixture now supplies one real CE local
player slot and a controlled camera cluster through the observer bridge, then
calls the unmodified CE selector while the package BSP is published. It finds
a cluster with a valid sound-environment palette reference, resolves that
reference through the actual loaded CE tag cache, and checks the returned
environment pointer, its first CE blend step, water-boundary result, and
selected background-sound reference. The query is in
[`hcu_scenario_bsp_switch_main.c:1424-1489`](../../tests/hcu_scenario_bsp_switch_main.c#L1424).
The Python runner roots and verifies the function in the native fixture link
map and rejects a package run that emits no sound-environment query
([`test_hcu_scenario_bsp_switch.py:1236-1310`](../../tests/test_hcu_scenario_bsp_switch.py#L1236)).

The native ILP32 package-backed command passed after strengthening the source
oracle:

```text
APPIMAGE_EXTRACT_AND_RUN=1 PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -s -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Result: **1 passed, 1 deselected, 2 package subtests passed in 144.32 s**.
The test also retains the existing source-hash-verified `a30`/`a50` CTAG/CBSP
transaction, rollback, collision, PVS, and sound-distance assertions. Test
inputs are the audited package manifest and raw decompressed maps; their
identities are frozen in the manifest
[`retail-cbsp-catalog-package-audit-e4a97218.json`](retail-cbsp-catalog-package-audit-e4a97218.json).

The follow-up oracle in [`test_hcu_scenario_bsp_switch.py:163-263`](../../tests/test_hcu_scenario_bsp_switch.py#L163)
independently walks each raw Xbox BSP's clusters and sound/background palette
blocks, selecting the first fog-free cluster with a valid environment
reference. It verifies the production CE output matches the raw-source cluster,
palette slot, environment datum, and background datum for every such BSP. The
derived `a30` candidates are B000 cluster 9 / palette 1 / environment -303100807
/ background -303625103 and B001 cluster 0 / palette 0 / environment -303166344
/ background -303887251. The `a50` candidates are B000 cluster 0 / palette 0 /
environment -297988922 / background -298185533, and B001–B003 cluster 0 /
palette 1 / environment -295760664 / background -295957275. No-fog filtering
ensures the tested path is the BSP cluster palette path rather than the fog
override path.

Exact fixture/artifact identities from the passing run:

- Parent HEAD: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` (dirty worktree).
- HCU submodule HEAD: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.
- halo-ps2 submodule HEAD: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
- C fixture SHA-256: `e624b97273bb3a7b5c02e11a996dff3ce8fce4343bad8eaf6c1d44487c52614a`.
- Observer/sound test bridge SHA-256: `80f94fd92e535677eb3fac4651f8386288b593658aecefd63fe8bfc4803f9482`.
- Python runner SHA-256: `1b20576ec6549edc60ea9ff0b21d6cd4a292cee2c5ebd23bff73550eb4374ff9`.
- Native ILP32 executable SHA-256: `bbf2ad2e44cfc187f299736efe12b16fb7729e846cc01c17c9f27b46bb8469df`.
- Link-map SHA-256: `0eca3864e7b2386cfe78e53120c08bf28faf62745226537e664a4d353181fd4a`.

## Limits and remaining Step 7 work

The camera/player and BSP are real CE structures, and palette/tag lookups use
the package-loaded CE tag cache. The source oracle's layouts are bounded by the
raw BSP extents and the CE compiler-derived structure offsets; it independently
compares every candidate BSP row that the fixture emits. The fixture still
does not cover fog-priority arbitration, equal-priority multi-listener ties,
nor does it invoke the SPU2 mixer or prove a sound asset was decoded or heard.

Still open: priority/tie scenarios; fog-region selection; no-palette/default
behavior; visible-PVS geometry/sound consumers and the remaining fog/weather/wind
consumer families; failure atomicity across CE publication/arena state; target
EE query and capacity evidence. The 16 MiB-class host fixtures remain
overprovisioned relative to the PS2's 6 MiB `current_bsp` region. Keep Step 7
and M2 open until the plan's target-capacity and consumer-family gates pass.
