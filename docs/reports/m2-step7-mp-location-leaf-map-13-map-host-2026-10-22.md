# M2 Step 7 — stock-MP point-to-leaf and leaf-to-cluster queries

Date: 2026-10-22. This qualifies one representative source-backed location
query per stock multiplayer BSP through the real CE scenario API on a native
host ILP32 fixture. It is not PS2/EE capacity or rendering evidence, and it
does not close Step 7.

## Implemented result

The existing package-backed 13-map lifecycle fixture now directly exercises
`scenario_leaf_index_from_point()` and `scenario_location_from_point()` on
each loaded retail BSP, in both load/unload cycles (26 successful query rows).
Each query uses the start point from that map's independently derived raw
collision golden. The source oracle walks serialized BSP3D nodes and planes,
requires the start point to resolve to a valid leaf and a valid structure
cluster, and separately proves that the endpoint (`start + vector`) resolves
to `NONE`. CE must return the same raw-source start leaf and cluster, and
`NONE` for the outside endpoint through both APIs. The test also verifies
that the active BSP/index and collision-user depth are unchanged.

The fixture includes Prisoner (map 104) despite its separate collision path
and early return: the location query runs before that branch. The Python
test requires the exact one-case-per-map goldens on both cycles, so absent
source cases, a missing map, or an untested cycle fails closed. It does not
use synthetic expected leaves or substitute a host implementation for CE.

Relevant code:

- [`tests/test_hcu_scenario_bsp_switch.py:600-965`](../../tests/test_hcu_scenario_bsp_switch.py#L600) derives collision candidates from raw geometry and serialized BSP3D; [`:779-805`](../../tests/test_hcu_scenario_bsp_switch.py#L779) performs the independent point-to-leaf traversal and rejects malformed traversal.
- [`tests/hcu_mp_capacity_main.c:58-89`](../../tests/hcu_mp_capacity_main.c#L58) calls the actual CE point and location APIs, checks expected start leaf/cluster and outside `NONE`, and preserves the active-BSP state.
- [`tests/hcu_mp_capacity_main.c:119-131`](../../tests/hcu_mp_capacity_main.c#L119) selects the source-derived map golden and invokes the query before the Prisoner-specific branch.
- [`tests/test_hcu_mp_capacity.py:260-286`](../../tests/test_hcu_mp_capacity.py#L260) builds source-hash-bound collision/location cases and records the source endpoint expectation; [`:631-644`](../../tests/test_hcu_mp_capacity.py#L631) requires the complete 13-map × 2-cycle result matrix.
- CE defines the leaf accessor in [`scenario.c:611-616`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L611) and the point→leaf→cluster mapping and invalid-index fallback in [`scenario.c:861-900`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L861). Its underlying BSP3D point traversal and malformed-node-to-`NONE` behavior are in [`bsp3d.c:97-133`](../../submodules/halo-ce-universal/source/physics/bsp3d.c#L97).

## Verification

The sandboxed build/test command was:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools python3 -m pytest -q tests/test_hcu_mp_capacity.py
```

It compiled and retained the candidate but skipped executing native ILP32 due
to sandbox SIGSYS. The approved elevated run used this exact command from the
repository root and exited 0:

```sh
build/m2-mp-weather-wind-13/mp-weather-wind-location build/m2-mp-weather-wind-13/assets/
```

The retained log has 26 `mp-location ... status=passed` rows, 26 weather rows,
and 26 host-map lifecycle rows. Its final marker is:

```text
mp-host-collision 13-map CE hit/PVS/reload matrix passed; target capacity not tested
```

Exact identities:

- Parent / HCU / halo-ps2 pins: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
- CE `scenario.c` SHA-256: `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0`; CE `bsp3d.c` SHA-256: `5c445e73cd356d62d18336e45290dbb415f2a1c9267c6621d96a2fe46555d798`.
- Candidate executable `build/m2-mp-weather-wind-13/mp-weather-wind-location`, SHA-256 `97c7c2acbb1c8f7d8b2e896e3c610692deaa53a78753e34092f9b64c90e5fbc8`.
- Link map `build/m2-mp-weather-wind-13/mp-weather-wind-location.map`, SHA-256 `ab761f367689fccfe730aa06e74f079a6f380c8d700fd982580ee77153e65a04`.
- Collision golden compiled into the executable: `build/m2-mp-weather-wind-13/hcu_collision_golden.h`, SHA-256 `2b1b9f536114042023f0ab3c5f49c35faa22d8743595175953dfb706739a234a`.
- Raw-derived location inventory `build/m2-mp-weather-wind-13/mp_location_source_inventory.json`, SHA-256 `9fb270b5b171e492609ba552f9bd007686baaa9c94d4179c69f8e9a352eb2c7c`.
- Elevated output `build/m2-mp-weather-wind-13/native-run-location.log`, SHA-256 `55ca4859ff0cb622592959db05f028aabbeb5272ec0e979aa512845d60bb6dc8`.
- All 13 source-map and package digests are pinned in [`tests/test_hcu_mp_capacity.py:25-66`](../../tests/test_hcu_mp_capacity.py#L25) and recorded per case in the location inventory. The package conversion schema ELF is SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`.

## Scope limits and remaining work

This verifies one source-selected inside point and one outside endpoint per
BSP. It does not prove every leaf, boundary/portal tie, malformed-tree case,
player spawn/respawn use, or cluster-driven visibility behavior. The existing
fixture uses host-sized map/tag/BSP/claim/scratch arenas, so the run explicitly
does not qualify Step 8's PS2 capacity or target placement. It also does not
qualify rendering, geometry visibility, BSP edge/vertex collision diversity,
or the multiplayer game as playable. Step 7 and Step 8 remain open.
