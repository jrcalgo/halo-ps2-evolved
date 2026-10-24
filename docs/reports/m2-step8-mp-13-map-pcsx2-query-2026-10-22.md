# Step 8 multiplayer map query loop in PCSX2

Date: 2026-10-22  
Scope: target-sized candidate-owner diagnostic, all 13 stock multiplayer maps, load/query/unload in PCSX2 recompiler. This is not a retail-EE qualification or a rendered/gameplay acceptance result.

## Run identity and command

The exact combined parent/HCU diagnostic ELF is `build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf`, SHA-256 `a415df0741314c8e4594c0c3b042cd5cc9760753ae76a42549640c14a57acab9`. It was launched directly by `tools/test_hcu_boot.py`; the ISO was not booted or mounted. The run used PCSX2 recompiler, succeeded after 334.033 seconds, reached `game-initialize-done`, observed `step8-mp-capacity-complete maps=13 query_only=1`, then remained fault-free through the required two-second stability window.

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py \
  --mode recompiler --stage m3-memory-ready \
  --success-marker 'step8-mp-capacity-complete' \
  --timeout 600 --stable-seconds 2 \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf
```

Source pins recorded by the runner: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. BIOS SHA-256 `b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b`; PCSX2 SHA-256 `0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea`. Runner JSON SHA-256 `b72b3f69d8eeead6e87c227a1d0d98ab2351e3ed0560fad7cb8b72d0e308691f`; guest log SHA-256 `dd67e9d3a5ff447aad881e1079bfbac1f20888969bb305244cc47668c1656853`.

## Observed map results

Each row comes from the CE diagnostic after loading that map through the selected package/map-service path. It traversed every reported cluster PVS row, invoked the CE collision query and received the independently selected surface/material-type hit, then unloaded and reported intact candidate-owner guards.

| Multiplayer map | Clusters / PVS rows | Collision surface | Material type | Unload guards |
|---|---:|---:|---:|---|
| Beaver Creek | 29 / 29 | 39 | 2 | intact |
| Blood Gulch | 30 / 30 | 84 | 2 | intact |
| Boarding Action | 41 / 41 | 16 | 7 | intact |
| Carousel | 36 / 36 | 21 | 7 | intact |
| Chill Out | 10 / 10 | 1 | 7 | intact |
| Damnation | 12 / 12 | 7 | 7 | intact |
| Hang ’em High | 1 / 1 | 0 | 7 | intact |
| Longest | 1 / 1 | 2 | 7 | intact |
| Prisoner | 1 / 1 | 0 | 7 | intact |
| Putput | 9 / 9 | 4 | 7 | intact |
| Rat Race | 16 / 16 | 2 | 7 | intact |
| Sidewinder | 35 / 35 | 85 | 2 | intact |
| Wizard | 18 / 18 | 2 | 7 | intact |

No `HALO_PS2_FAIL` marker occurred. The trace contains 13 `step8-mp-capacity-query` and 13 `step8-mp-capacity-unloaded` records, followed by the all-map completion marker. The first 300-second attempt only reached Rat Race (10/13) and timed out; it is failure/partial evidence and is not the successful run identified above.

## Candidate arena and physical-placement observation

This profile is explicitly opt-in under `HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC`; the production binder and map admission remain unchanged. The test recarves existing ten-MiB combined map/texture backing as `tag=4,477,120 B + BSP=1,993,712 B` (`map=6,470,832 B`) and `texture=4,014,928 B`, total `10,485,760 B`. It does not enlarge the fixed arena total or spend the reserve. See [`hcu_main.c`](../../src/stream/hcu_main.c#L188-L220).

The runner observed the ELF ending at `0x004f4f14`, boot backing from `0x004f5150` to `0x019efbd2`, and the reserved interval beginning at `0x01a00000`; address arenas were valid, nonoverlapping, and canaries held. The measured image retained 61,230 bytes between boot end and reserve start, with 540 bytes alignment gap. The test BSP owner reached its 4,477,120-byte tag allocation; the diagnostic's texture region had zero allocations because the workload is query-only. This is PCSX2 virtual guest evidence, not a measurement on a physical PS2 EE.

## What this closes and does not close

This closes the Step 8 **candidate-layout all-map target-sized query subcheck**: all 13 MP maps passed the same guest image's CE map preflight, tag/BSP load, cluster/PVS traversal, selected collision-hit query, unload, and guard checks. It supplements the all-13 host package/texture tests and earlier one-map Sidewinder result.

It does **not** prove production binder adoption or production admission, complete map render residency, actual texture load/pin/eviction/DMA overlap (texture usage was zero in this diagnostic), all weapons/effects/animation/HUD/audio assets, bot or co-op workload capacity, sustained match-frame time, or physical EE placement/performance. Keep map admission closed and Step 8 open pending lossless production ownership integration and the full supported multiplayer workload. The host and PCSX2 diagnostics are not evidence that a map is currently playable/rendered.
