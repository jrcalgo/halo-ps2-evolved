# Step 7 MP fog-plane consumer — Beaver Creek

Date: 2026-10-22. This is a host ILP32 semantic subcheck for a stock
multiplayer map. It does not close Step 7 or establish EE capacity.

## Implemented and verified

The production-sized MP fixture now loads a schema-converted Beaver Creek
package alongside Longest and Blood Gulch and invokes the existing real-CE
`assert_relocated_fog_plane()` consumer helper for its source-derived fog
chain. The raw Xbox BSP oracle selects BSP 0, cluster 0, high-bit fog reference
`-32768` (plane 0), region 0, fog palette 0, and fog datum `-397670698`; the
plane normal/distance and weather fallback are embedded in the generated
golden. CE then checks the relocated cluster→plane→region→palette/tag chain,
`scenario_get_fog_region_index()` on both sides of the plane,
`scenario_location_underwater()`, `scenario_location_water_depth()`, weather
selection, and unchanged active BSP publication/collision-user depth. The
fixture requires two exact `fog-plane map=103 bsp=0 cluster=0` success markers,
one for each load/unload cycle, so an empty/missing golden cannot silently
pass.

This exercises a fog plane with `underwater=0`; it does not cover bot
`scenario_fog_at_point()` perception, which remains a separate unresolved
retail-CE behavior. It also does not execute weather particle simulation,
wind cadence, or SPU2 sound playback. The package was built with the retained
schema ELF `build/m2-artifacts/schema-2fba411b-prior/halo-local.elf` (SHA-256
`2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`) using
`tools/pack_retail_ctag_hp2.py --include-all-bsps`; this historical schema
artifact is explicitly recorded in the current test manifest and the
package itself is content-hashed. Do not mistake the package's identity for a
fresh production PS2 package build.

## Verification and evidence identity

Commands (run outside the sandbox because native ILP32 execution is blocked
there with SIGSYS):

```text
python3 -m py_compile tests/test_hcu_mp_capacity.py
python3 -m pytest -q tests/test_hcu_map_catalog.py tests/test_hcu_ce_map_lifecycle.py tests/test_hcu_mp_capacity.py
4 passed, 2 skipped in 27.03s
```

Retained manifest:
[`build/m2-mp-production-capacity/manifest.json`](../../build/m2-mp-production-capacity/manifest.json),
SHA-256 `9af254d0b0835975eed6db4848528c86a6f71c442d0076394ea097837973ed36`.
It binds the host executable SHA-256
`9b6aa06788622edfdcc9803b71db0cf272288db1a463ac1520037a296e140f08`, link
map `6667b6644ba40bbd5cb297c3fa75185184ca97bdf1bee8b3706d03a286726e4b`,
run log `902f43f2946b94539a8b7330bd283d0f1d7d536f82d4d935330c2781f1a7b3e4`,
fog golden `e70fff5b8c5d533780d42119972cb5c1684e10f3faa2f70bf15760f5d2499419`,
and Beaver Creek package SHA-256
`4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc`.
Pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The manifest explicitly says
`ee_evidence: false`; host capacities are candidate limits only.

The test-only `HCU_M2_MP_HOST_ORACLE` admission list now permits Beaver Creek
in addition to Longest/Blood Gulch. The ordinary production admission branch
is unchanged and still rejects every gameplay map. Halo-64 is used only as a
comparison for retaining CPU-side camera/state work when drawing backends are
removed; no N64 fog behavior or budgets are used.

## Remaining Step 7/8 gaps

This adds one valid MP fog-plane case. The field/consumer report still calls
for Chill Out and Damnation fog cases, wind/weather simulation and bounds,
MP sound/PAS/playback, material/lightmap/visibility and pathfinding consumer
tests, broader collision/breakable cases, retail bot fog-perception evidence,
and exact target-sized queries. Step 8 still lacks a measured all-map capacity
topology, including Sidewinder and the simultaneous bot/co-op/render/audio
workload. No map-admission or rendered-game claim follows.
