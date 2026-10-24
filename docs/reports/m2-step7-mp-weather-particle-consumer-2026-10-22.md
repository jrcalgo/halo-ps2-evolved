# M2 Step 7 — stock multiplayer weather-particle consumer

Date: 2026-10-22  
Disposition: source-backed selection/dispatch slice passes for all 13 stock
multiplayer maps. It proves that the CE consumer selects the raw BSP's weather
palette for each cluster and that no stock multiplayer cluster can start a
weather-particle system. It does **not** exercise a real `rain` tag's particle
update, bitmap animation, weather physics, polyhedron clipping, PS2 rendering,
or target resource cost.

## Finding and why it matters

Every raw stock multiplayer BSP has one or two weather-palette entries, and
every such entry's `particle_system` reference is the `rain` group with datum
`NONE` (`0xffffffff`). The maps have 239 clusters total: 235 select palette 0;
the remaining four are Carousel clusters and select `NONE`. Damnation is the
only map with two palette entries; both are `NONE` for particle systems.
Therefore CE can (and this fixture verifies it does) enter the weather
selection code for a local player, but its resolved definition remains
`NONE`; it neither allocates weather particles nor runs the weather particle
update/render function on these retail MP maps. Wind remains a separate
weather-palette consumer and is not disabled by this finding.

This is useful Step 7 evidence rather than a claim that “weather works” by
visual inspection: there is no retail MP `rain` definition to exercise. If
custom maps later become supported, this no-rain result does not apply to them.

## CE source path and fixture

The fixture in [`tests/test_hcu_mp_weather_particle_consumer.py`](../../tests/test_hcu_mp_weather_particle_consumer.py)
parses the original decompressed Xbox maps, validates the BSP-root palette and
cluster block extents, reads the four-word tag reference at palette offset
`+0x20` (datum at `+0x2c`), and reads each cluster's signed weather index at
`+0x08`. The input must be exactly the expected map hash and the palette
reference group must be `rain`; unknown/missing references or out-of-range
cluster indices fail the test.

For the host C fixture, Python extracts and compiles the current CE bodies of
[`scenario_location_underwater()`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L694)
and [`weather_particle_systems_render()`](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c#L753)
verbatim. It supplies the raw cluster and palette entries, checks all 239
cluster selections and system-state outputs, and spies on CE's
`weather_particle_system_new`, delete, and per-system render/update boundary.
The assertions require no create/delete/update calls for all retail MP inputs.
A separate synthetic `rain` datum `7` control proves the fixture is sensitive:
the same CE body must create and update a non-`NONE` definition. The synthetic
case is only a harness control and is not counted as retail-map evidence.

`scenario_get_fog_region_index()` is stubbed to `NONE` in this isolated test,
so it covers the real CE cluster-fallback branch in
`scenario_location_underwater()`, not plane/region fog selection. That
limitation cannot change whether any stock-MP weather palette starts rain:
every raw palette entry has a `NONE` particle-system datum, including any
entry selected by a fog-region override. The CE return still carries
underwater state, which this fixture does not assert from raw fog planes.

## Raw inputs

| Map | Clusters queried | Palette entries | Rain refs `NONE` | Clusters selecting `NONE` | Raw BSP SHA-256 |
|---|---:|---:|---:|---:|---|
| Beavercreek | 29 | 1 | 1 | 0 | `1fb6efe09129d9c477cac22e0462138b368e1b7e8228062110f2e3e52849c7c4` |
| Blood Gulch | 30 | 1 | 1 | 0 | `8b3fa60e1f01fcec21c97c1916e7ca3ac8ed51a24f00eef18e4c8361d48e18bf` |
| Boarding Action | 41 | 1 | 1 | 0 | `2b1397a58285f6e6157c6591590a0df21c7b44ed488116599ac89534efa3a54d` |
| Carousel | 36 | 1 | 1 | 4 | `40a8324d3d9a8a5d238ecf9caa15a2b634a316d3552762c2be34adf06622b0cf` |
| Chillout | 10 | 1 | 1 | 0 | `2f8e7f85c0e52bf4a25bede449d1499068f629959bead6feb25574a47e8ad733` |
| Damnation | 12 | 2 | 2 | 0 | `d3118effad059fde0083f0fd6abc45b824048fd6fe22867047ae6973ac330087` |
| Hang 'Em High | 1 | 1 | 1 | 0 | `4828fcc280c2c364e1e469dcf4626d2656ff6ca188cdcbdf3659f82992a3f4c3` |
| Longest | 1 | 1 | 1 | 0 | `d2583ce3f53d5ff9f04ecaf163fed8f801e355d858c5254e954929f2c425530f` |
| Prisoner | 1 | 1 | 1 | 0 | `ea4000f883893868aa01df913f9dd9d239942e84d8f4a498f3017e87574d4f13` |
| Putput | 9 | 1 | 1 | 0 | `273326a59e3d13678ebad96704eb690e6dd79f2ad3c752d96f82de9de2fd49ca` |
| Rat Race | 16 | 1 | 1 | 0 | `060d953d098539f9247185ca342c47485dfd31942e1f2f98607dae9380fcfbce` |
| Sidewinder | 35 | 1 | 1 | 0 | `9e861ddb861fbaaf5b09a1431fa2acfa3f0f6c6bfee3a4fc4d64f90e75cb5a13` |
| Wizard | 18 | 1 | 1 | 0 | `c75e808bb3496a62e1c65fd01eade6b84ee38a2fdb72daade8fb18be6a155fdf` |

The source maps are hash-pinned in the test. The hashes match the checked-in
`docs/reports/m2-step7-mp-weather-palette-inventory-2026-10-22.md` inventory;
the table above records the corresponding individual BSP image identities.

## Cadence and PS2 bounds

CE's dispatch calls the per-system update/render only if the resolved
definition remains non-`NONE` ([`weather_particle_systems.c:776-790`](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c#L776)).
For a map that does have a system, CE updates it from the weather render pass:
`system->time_delta_sec` comes from `render.time_delta_since_tick_sec`,
fractional `TICKS_PER_SECOND` is accumulated into leftover ticks, and particle
animation/physics uses that frame delta ([`weather_particle_systems.c:509-558`](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c#L509)).
Thus this code path remains render-cadence-sensitive and needs a real rain-tag
fixture before claiming interpolation/update parity. This test deliberately
does not assert PS2 cadence or change that CE behavior.

CE's retail pool bound is 512 weather particles, with up to 8 types, 8 visible
weather polyhedra, 26 particle boxes, and five clipping planes
([`weather_particle_systems.c:91-98`](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c#L91)).
Those pool constants are not measured PS2 high-water or RAM approval. Since
the 13 stock MP maps cannot activate a system, they contribute no active rain
particle demand; custom rain tags or map additions would require separate EE
pool/CPU/render qualification rather than copying the Halo-64 pool.

## Halo-64 comparison

The pinned Halo-64 source (`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`)
retains essentially the same weather selection dispatch, but gates
`MAXIMUM_NUMBER_OF_WEATHER_PARTICLES` to 1 under `HALO_N64`, sets
`weather = FALSE` in that build, and explicitly comments that its native
renderer does not call the Xbox weather pass
([`Halo-64 weather_particle_systems.c:91-103`](../../submodules/halo-64/source/effects/weather_particle_systems.c#L91)).
That is an N64 renderer/capacity cut, not CE behavior and not evidence for a
PS2 limit. The PS2 port should retain CE's 512-particle source semantics unless
a measured PS2 capacity/performance result justifies a documented port change;
the stock MP raw tags simply make that pool inactive today.

## Reproduction and identities

Run:

```sh
python3 tests/test_hcu_mp_weather_particle_consumer.py -v
```

Result: `1 test passed` (the C fixture compiles and executes during the test;
it checks 13 maps / 239 cluster queries and the synthetic rain-dispatch
sensitivity control). `git diff --check -- tests/test_hcu_mp_weather_particle_consumer.py`
passed.

Source pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, CE
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`, Halo-64
`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.

SHA-256 identities:

- Test: `a7b0fc527b66bcc3bd2a480afdb53dcac88ede3c6f7e0ea35a8b74c95e682b50`
- CE weather consumer: `5c6f2cbe81276d89203890b1dbba3eb833125b2eb1c8c24c4c96dd74d61360b3`
- CE scenario consumer: `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0`
- Halo-64 weather source: `3ecbba33df12c901c4cb2549c78970b05afce6290a40fe98839f8b0dde49c712`

REA was not applicable: the behavior is explained by the current CE source and
the exact raw retail map/tag bytes; no opaque binary behavior needed to be
recovered. No production source was modified.
