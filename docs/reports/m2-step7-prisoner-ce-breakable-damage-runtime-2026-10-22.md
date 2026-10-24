# M2 Step 7: Prisoner CE breakable damage/runtime slice

## Result

The real CE breakable-surface state subsystem now has a package-backed host
fixture for the one stock multiplayer map that contains breakable collision
surfaces: Prisoner. The test selects a raw-source-derived collision ray, runs
CE `collision_test_vector()`, passes its returned breakable index and material
type into CE `breakable_surface_damage()`, observes nonlethal vitality loss,
then lethal damage, the cleared collision bit and a collision miss. It invokes
CE `breakable_surfaces_reset()` and verifies vitality, the extant bit, and the
original collision hit return. The same sequence passes in both Prisoner load
cycles of the 13-map lifecycle test.

This closes a real gap in the previous flagged-surface query: that earlier test
manually toggled a fixture-owned byte array and never called CE's breakable
state/damage implementation. It does **not** close player/weapon impact
integration, particle/audio effects, target-sized capacity, or EE behavior.

## Source behavior exercised

- CE initializes all per-map breakable bits as extant and vitality to `1.0`,
  and reset uses the same initialization path
  ([`breakable_surfaces.c:123-166`](../../submodules/halo-ce-universal/source/physics/breakable_surfaces.c#L123)).
- CE damage validates the damage tag group and material range, reads the
  scenario's actual material definition, applies CE's damage minimum/scale,
  material modifier, and maximum-vitality normalization, then clears the
  extant bit when vitality reaches zero
  ([`breakable_surfaces.c:200-245`](../../submodules/halo-ce-universal/source/physics/breakable_surfaces.c#L200)).
- CE collision traversal suppresses a breakable surface when its indexed
  bitmap bit is cleared and returns the surface/breakable/material identities
  on a hit ([`collision_bsp.c:1404-1412`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1404),
  [`collision_bsp.c:2273-2290`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2273)).
- Halo-64 is a comparison only: its `breakable_surface_damage()` has the same
  vitality arithmetic and collision-bit transition
  ([`halo-64 breakable_surfaces.c:156-203`](../../submodules/halo-64/source/physics/breakable_surfaces.c#L156)).
  CE's added damage-tag/material bounds and network notification are retained;
  no Halo-64 omission is copied into this fixture or port.

## Fixture design and boundaries

[`test_hcu_mp_breakable_runtime.py`](../../tests/test_hcu_mp_breakable_runtime.py)
reuses the existing hash-pinned 13-stock-MP CE package lifecycle/collision
fixture, adding the production CE `breakable_surfaces.c` translation unit and
a dedicated adapter in
[`hcu_mp_breakable_runtime_host32.c`](../../tests/hcu_mp_breakable_runtime_host32.c).
The CE effect routine is replaced only in a temporary generated test copy with
a no-op because this test isolates the vitality/bitmap/collision state machine;
`breakable_surface_effect_enabled` is also false. Material definitions come
from the loaded Prisoner scenario. The controlled damage-effect datum is
synthetic and returned through a narrow tag-get wrapper so the fixture tests
CE's arithmetic deterministically. The network-co-op notification is a test
no-op. These adapters mean this is not a real weapon/projectile damage test
and says nothing about particles, sounds, or network replication.

The existing fixture uses host-sized 16 MiB tag and 8 MiB BSP arrays, and
its target map is still admitted only by the diagnostic host harness. It is
not EE RAM/capacity evidence. No REA/XBE analysis was needed for this source
and package-backed state-transition check.

## Verification and identities

Command (the sandbox terminates native ILP32 execution with SIGSYS, so this
run used the approved unsandboxed native test execution):

```sh
python3 -m pytest -q tests/test_hcu_mp_breakable_runtime.py -x
```

Result: **1 passed** (the nested existing fixture ran the 13-map lifecycle and
collision matrix, including two Prisoner cycles; the new breakable sequence
ran once per Prisoner cycle). The retained log contains:

```text
prisoner-breakable-runtime map=104 surface=457 breakable=1 material=9 vitality=1.0->0.75->broken reset=restored collision=restored effect_path=disabled status=passed
```

The host fixture still reports its 16 MiB tag and 8 MiB BSP capacities and
must not be presented as target sizing.

| Input/artifact | SHA-256 |
|---|---|
| Parent HEAD | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` |
| halo-ce-universal HEAD | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| halo-ps2 HEAD | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Halo-64 comparison HEAD | `17541f4444baabb47d1a0deb917f26ccb7b6bc5c` |
| Prisoner decompressed Xbox map | `85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307` |
| Prisoner all-BSP HP2 package | `3bb10f06c785da93fe0f7257be9f06519b7ccb6c155801a7a04a5e6d56352136` |
| Schema ELF used by package fixture | `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa` |
| CE breakable source | `a8349a2a064dcdc969153ebf81eaaa2a5528dc56c733ab0f1efb75e7d680a8e9` |
| New C test adapter | `78af8a7b5d3784cd8d2fe3de2de353756f6815218c1e2efd89faeeddedd768aa` |
| New Python runner | `e6da6bafbc86967a0f748293042d7dd790983ed7574c812bd199e1af65cf4d91` |
| Retained host executable | `b2ab7e8b7726ebfcf65201b1b47af3b2d1c4a55e06ebac40adbb03e54361825a` |
| Retained link map | `9af12377beac0f1ae803ed4e44ef47f8e4d14a8e3648f0b98532d91a95a64ef8` |
| Retained complete test log | `d6aa2af46af438fc7a204d171e2d13aa11bba9ac9a87023bf94e59406de11935` |

## Remaining Step 7 gates

This is one map-backed CE state slice. Remaining work includes a true gameplay
damage caller (weapon/projectile/area damage) and effect-chain validation;
failure-atomicity across all BSP/map load stages; the still-uncovered BSP
consumer and visibility/fog/weather/audio paths; and query/capacity evidence
inside the accepted PS2-sized memory plan. Step 7 remains open.
