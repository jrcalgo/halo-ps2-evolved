# Step 7 — Invalid MP fog-reference safety, all 13 stock maps

Status: **this malformed-reference subcheck passes** on the native host ILP32
fixture. It does not close Step 7 or establish PS2 target memory/timing.

## What was executed

The package-backed 13-map fixture derives and hash-checks each stock map and
HP2 package, loads each map through the existing lifecycle, and runs twice per
map. A generated test-only C translation unit selects the fixture's raw-BSP
collision-oracle cluster, temporarily replaces its relocated `fog_reference`
with two invalid values, then calls CE's real
`scenario_get_fog_region_index(&location, NULL)`:

1. a high-bit fog-plane index equal to `fog_planes.count`;
2. a direct fog-region index equal to `fog_regions.count`.

Both lookups return `NONE`. The cluster reference is restored afterward. On
each call, the fixture verifies that the published structure-BSP, collision-
BSP and BSP3D pointers, global and scenario BSP indices, collision-user stack
depth, and every collision-user stack slot are unchanged. It also asserts the
restored reference equals the exact pre-probe value. Thus this specifically
tests CE's malformed-index guards and their no-publication/no-collision-stack-
side-effect contract, not arbitrary corrupt tag images.

The native unittest passed: **1 test, 83.446 seconds**. Its output has **26/26
probe rows** (13 maps × 2 lifecycle cycles); each row reports both invalid
lookups. Across those rows, maps with zero fog-plane/region counts reject the
zero indices, while Beaver Creek, Chill Out, and Damnation reject index 1 for
their count-1 fog arrays. The final fixture marker is `mp-host-collision
13-map CE hit/PVS/reload matrix passed; target capacity not tested`.

## Source and comparison basis

- The exercised implementation is CE `scenario_get_fog_region_index()` in
  [`scenario.c:632-692`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L632).
  Its `port:` guards reject an out-of-range high-bit plane index before array
  access and validate the resulting region index before returning it. The
  real function is retained in the test link map, and its source SHA is bound
  in the manifest.
- The generated probe is based on
  [`hcu_mp_capacity_main.c`](../../tests/hcu_mp_capacity_main.c) and is
  retained as `hcu_mp_capacity_main_invalid_all.c`; the map/package hash pins
  and lifecycle assertions are in
  [`test_hcu_mp_capacity.py`](../../tests/test_hcu_mp_capacity.py).
- Halo-64 comparison: its corresponding
  [`scenario.c:627-678`](../../submodules/halo-64/source/scenario/scenario.c#L627)
  follows the same high-bit-plane/direct-region selection shape, but lacks
  HCU's two invalid-index guards. That comparison is contextual only: this
  test validates the guarded behavior in the pinned HCU source, not Halo-64
  runtime behavior and not retail behavior on malformed tags.

## Reproduction

The runner compiles the fixture, creates a generated unittest, and retains
the exact inputs/artifacts. In a sandbox where native ILP32 execution is
blocked by SIGSYS, the runner itself reports the expected skip; execute the
generated test outside that sandbox to obtain the native pass:

```sh
python3 tools/test_hcu_mp_fog_invalid_refs_all.py
PYTHONPATH=build/m2-mp-invalid-fog-all-1792692847325171777:.:tests:tools:submodules/halo-ps2/tools \
HCU_MP_CAPACITY_RETENTION_DIR=build/mp-fog-verified-final \
python3 -m unittest -v \
  test_hcu_mp_capacity_fog_invalid_all.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision
```

The second command is the direct native ILP32 rerun that returned `OK`; the
first command's sandbox skip is not counted as execution evidence.

## Pins and exact artifacts

Parent/HCU/halo-ps2/halo-64 commits:
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c` /
`6933490b2d16bb1c637295b6a0f3880ba23a7d56` /
`71183bb0a9adc586cd267b2780c82bbc12cfd95b` /
`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.

The retained manifest contains the individual SHA-256 values for all 13 raw
maps and all 13 HP2 packages, along with source files, pins, and build outputs.
Key artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| Runner `tools/test_hcu_mp_fog_invalid_refs_all.py` | `194a7e9a0f024862cf0aa4f6e9354e734c966125cfbb37808891d9af6e09985c` |
| Generated unittest | `54feee0eac0b880e0e6585dcad1a0319af4af95fb83b84dafc5dd01bbe26d07c` |
| Generated injected C probe | `d5292e63d5b58828dd448ded6f8e7c0c2c57856b3450c434fd5ebf2b46847b9d` |
| CE `scenario.c` | `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0` |
| Halo-64 `scenario.c` | `0368b3bb31f8008f1ff2120f58c3d0c91e4c003a1009974d3f1cbd67810e1684` |
| Host ILP32 executable | `a0ee79ea79138a14bfa599e8437ff6aa69d4a9786ebbb5ab63ab47c909a35d69` |
| Link map | `355c76b4a18e598c300a367fd5ced3cc2b9344c662d740f467b0c198c4bcf198` |
| Native test/fixture output | `c791483a23a5790d0e111c354f180fe8b3b63adf7b907d033b08728e100aefed` |
| Source/pin/map/package manifest | `8978df92d54f52acde2606250b4b8af021b53608f5d07481e88cbdae32a743cf` |

## Limits

This is host ILP32 semantic evidence for the exact bounds-checked calls. It is
not EE/PCSX2 execution, target-sized allocation evidence, bot fog-perception
validation, weather-particle or visual fog behavior, exhaustive per-cluster
testing, or a general malformed-BSP fault matrix. No production semantics or
PS2 code changed. Other Step 7 consumer/collision/failure gates and Step 8
target-capacity gates remain open.
