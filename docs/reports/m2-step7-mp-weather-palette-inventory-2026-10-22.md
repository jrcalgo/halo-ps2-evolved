# M2 Step 7 — multiplayer weather-palette and cluster-index inventory

Date: 2026-10-22  
Disposition: passed raw-source structural inventory for the 13 stock multiplayer maps. This is not a CE runtime wind test, package-relocation test, or PS2 capacity qualification. Campaign maps are excluded.

## Result

The new reproducible audit [`tools/audit_retail_mp_weather_palette.py`](../../tools/audit_retail_mp_weather_palette.py) walked every raw BSP in the 13 maps under `build/retail-maps/decompressed/`. It checks the BSP-root weather-palette and cluster block extents against each BSP image, counts weather-palette entries, counts cluster references by signed index, and fails on any palette count above CE's 32-entry `wind_states` storage or any cluster weather index other than `NONE` (`-1`) or an index inside that BSP's palette.

CE declares `wind_state` as 32 bytes and `wind_globals.wind_states[32]` in [`wind.c`](../../submodules/halo-ce-universal/source/scenario/wind.c#L59); `wind_update()` clamps the runtime iteration count with `MIN(weather_palette_block->count, NUMBEROF(wind_globals.wind_states))` ([`wind.c:188-211`](../../submodules/halo-ce-universal/source/scenario/wind.c#L188)). The structure schema independently names 32 as the maximum weather-palette entries ([`structures.h:35-36`](../../submodules/halo-ce-universal/source/structures/structures.h#L35)). This audit deliberately treats a source palette above 32 as a failure instead of relying on CE's clamp, because clamping would silently omit source entries.

| Multiplayer map | BSPs | Max palette entries / BSP | Cluster refs: valid index | `NONE` refs | Source-map SHA-256 | BSP0 SHA-256 |
|---|---:|---:|---:|---:|---|---|
| Beavercreek | 1 | 1 | 29 | 0 | `eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a` | `1fb6efe09129d9c477cac22e0462138b368e1b7e8228062110f2e3e52849c7c4` |
| Blood Gulch | 1 | 1 | 30 | 0 | `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1` | `8b3fa60e1f01fcec21c97c1916e7ca3ac8ed51a24f00eef18e4c8361d48e18bf` |
| Boarding Action | 1 | 1 | 41 | 0 | `34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522` | `2b1397a58285f6e6157c6591590a0df21c7b44ed488116599ac89534efa3a54d` |
| Carousel | 1 | 1 | 32 | 4 | `3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1` | `40a8324d3d9a8a5d238ecf9caa15a2b634a316d3552762c2be34adf06622b0cf` |
| Chillout | 1 | 1 | 10 | 0 | `52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb` | `2f8e7f85c0e52bf4a25bede449d1499068f629959bead6feb25574a47e8ad733` |
| Damnation | 1 | 2 | 12 | 0 | `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c` | `d3118effad059fde0083f0fd6abc45b824048fd6fe22867047ae6973ac330087` |
| Hang 'Em High | 1 | 1 | 1 | 0 | `e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f` | `4828fcc280c2c364e1e469dcf4626d2656ff6ca188cdcbdf3659f82992a3f4c3` |
| Longest | 1 | 1 | 1 | 0 | `e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` | `d2583ce3f53d5ff9f04ecaf163fed8f801e355d858c5254e954929f2c425530f` |
| Prisoner | 1 | 1 | 1 | 0 | `85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307` | `ea4000f883893868aa01df913f9dd9d239942e84d8f4a498f3017e87574d4f13` |
| Putput | 1 | 1 | 9 | 0 | `efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243` | `273326a59e3d13678ebad96704eb690e6dd79f2ad3c752d96f82de9de2fd49ca` |
| Rat Race | 1 | 1 | 16 | 0 | `577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e` | `060d953d098539f9247185ca342c47485dfd31942e1f2f98607dae9380fcfbce` |
| Sidewinder | 1 | 1 | 35 | 0 | `995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc` | `9e861ddb861fbaaf5b09a1431fa2acfa3f0f6c6bfee3a4fc4d64f90e75cb5a13` |
| Wizard | 1 | 1 | 18 | 0 | `978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb` | `c75e808bb3496a62e1c65fd01eade6b84ee38a2fdb72daade8fb18be6a155fdf` |

Across 13 BSPs, palette counts sum to 14 entries (a sum across separate maps, not simultaneous runtime demand). The maps contain 239 clusters: 235 cluster references point to palette index 0, and four Carousel clusters use `NONE`; no other values occur. Damnation is the only map with two weather-palette entries. No raw map approaches the 32-entry per-map limit.

## Reproduction and pinned inputs

Run from the repository root:

```sh
python3 tools/audit_retail_mp_weather_palette.py
```

The script emits a deterministic JSON report to stdout and exits nonzero on malformed source BSP extents, a missing/incomplete map set, any palette count above 32, or any invalid cluster weather index. It hashes the source map and each BSP, and records the source pins plus CE source-file hashes. This run used:

- Parent: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- halo-ce-universal: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- `wind.c` SHA-256: `b4464221406b8388a77815afd84a179f9b8fe2c835f841b34caa6f6bc815f911`
- `structures.h` SHA-256: `a641ae486a9d6736a13be1b2047fea033da1fa4434fc93b04b9187cb6351b66b`
- `src/stream/hcu_map_catalog.c` SHA-256: `14a2012ff370d8a8db2477b92c34fdbbca6cc027e8ac82814f644c9a653b3773`

Observed result: `pass=true`, 13 maps, 13 BSPs, zero violations. No native ILP32 or PCSX2 run is needed for this parser-only inventory.

## Limits and next evidence

This inventory confirms only that raw source palette counts and cluster indices fit the declared CE array bounds. It does not prove that the HP2/package conversion preserves these blocks, validate palette tag references or wind-definition semantics, call `wind_initialize_for_new_map()` / `wind_update()` / `scenario_get_current()`, test weather particles/polyhedra, establish tick-versus-render cadence, or measure PS2 memory/CPU and co-op/bot workload. A follow-up consumer test should pick an MP package and derive expected wind inputs from raw source bytes, then assert CE wind initialization/update/query output under controlled seeds. Any target-sized pool/high-water claim remains Step 8 evidence, not a consequence of these static counts.

The scan does not investigate Halo-64's altered behavior: the capacity and data expectations are taken from the pinned CE source and the multiplayer source maps. Halo-64 remains a comparison source only, not a basis for copying N64 limits or behavior.
