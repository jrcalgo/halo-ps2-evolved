# M2 Step 7 — stock-MP grazing collision query

## Result

Added one raw-source-derived near-parallel contact to the existing isolated host ILP32 collision fixture and ran the real CE `collision_test_vector()` path. Beaver Creek's structure BSP accepts the candidate on both map-load cycles. The returned surface, leaf, material/type, plane designator, and hit fraction match the raw float32 source oracle. The native test passed (1 test, 65.918 s); this is host semantic evidence, not R5900/PS2 RAM or EE performance evidence.

The returned query was:

| Field | Oracle and CE result |
|---|---:|
| Map / map ID | Beaver Creek / 103 |
| Surface | 39 |
| Edge | serialized polygon vertices 0–1; contact inset 0.01 world units |
| Incidence cosine | 0.025 (about 1.43° from tangent to the surface plane) |
| Start leaf | 178; segment endpoint leaves the BSP |
| Material index / type | 0 / 2 |
| Plane designator | 47 |
| Expected `t` / CE `t` | 0.499996965 / 0.499997 (within `2e-4`) |
| CE selected face | 39, exactly the unique raw-oracle first polygon |

The expected face was not selected from CE output. The candidate generator screens the raw serialized collision planes and vertices first, requires exactly one first-contact polygon, computes the raw start leaf and BSP2D route, and only then emits the CE assertion. The grazing ray therefore exercises shallow-angle traversal and surface routing without a fabricated unique-face expectation.

## Search bounds and outcome

The source scan was run for all 13 stock multiplayer package maps and their single structure BSP each. On every BSP it visits valid, non-breakable surfaces with valid material types and approximately unit collision-plane normals (`0.9 < |n| < 1.1`), then every polygon edge. Its bounded candidate grid uses edge-midpoint insets `{0.01, 0.02, 0.05}`, incidence cosines `{0.025, 0.05, 0.1}`, and both edge-tangent signs. Candidates must be inside the polygon, produce exactly one raw-oracle first hit at `0.1 < t < 0.9`, route to that face through the source leaf's BSP2D reference, start in a valid leaf, and end outside. It records the first qualifying candidate per map. The audited scan found at least one per map; the CE runtime fixture presently validates the Beaver Creek representative only. This is not a proof for angles/insets outside that grid.

## Implementation and source basis

- `tools/audit_mp_collision_edge_pairs.py:302-356` builds the bounded raw float32 grazing candidate from serialized surfaces and routes it through the source BSP oracle.
- `tools/test_hcu_mp_collision_edge.py:31-55,100-108` packages the Beaver Creek candidate only after source qualification; its injected test invokes the actual CE vector query and asserts exact surface/material/plane/leaf plus bounded `t`.
- CE's public `collision_test_vector()` forwards the vector to the structure BSP, then publishes the CE result fields (`source/physics/collisions.c:478-560`). CE's leaf path uses the leaf's BSP2D references, projected hit point, and selected surface (`source/physics/collision_bsp.c:1821-1888`).
- The underlying retail BSP's collision tree, planes, leaf ordering, and leaf references are documented by the PS2 parser notes (`submodules/halo-ps2/docs/08-bsp-section.md:22-28`). This report does not change the PS2 parser, production collision rules, map admission, or memory budgets.

## Reproduction and evidence identity

Run from the generated directory after the sandbox's compile/skip pass:

```sh
cd build/m2-mp-edge-runtime-1792685860740420752
python3 -m unittest -v test_hcu_mp_edge_generated.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision
```

The native run exited 0. `retained/run.log` records the exact case twice, once for each lifecycle cycle:

```text
mp-grazing map=103 surface=39 leaf=178 incidence_cosine=0.0250 t=0.499997 status=passed
```

Pins used: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`; HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.

SHA-256:

| Artifact | SHA-256 |
|---|---|
| Beaver Creek decompressed retail map | `eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a` |
| Candidate/runtime manifest | `4f26d2d2ac5acf16d8a45b2a4343c891981b3b28be57416dea82339511d767ae` |
| Generated C golden header | `0ae099356b7a1bd63f89baa5a32aa13c95845f51a108f10ebf65e06297c09950` |
| Native executable | `bd28e69c19ecb9a89cd116f85f171e1304cb6b359c8c24542d7d5959f3ca0b9a` |
| Native executable link map | `35df302a9547d8be3a367dbf1f825d41aee7f9d551f29971855d3d9d74fdb5a8` |
| Native run log | `1b6a2639c30389249565143cf6ed181ed0bf887b30d58024131db3b9866c3278` |
| Source candidate auditor | `f59b1ed39ebd764ad28a8868039359930415700ea135d195950b1d4cc83396e3` |
| Fixture/test generator | `11f715e0cf22a63dac00750194f7233967c318e8956faa890aa7a085756aaa85` |

## Limitations

This closes only a bounded grazing-ray host subcheck for Step 7. It does not establish target-sized collision-query capacity (Step 8 dependency), R5900 correctness/performance, all possible tangent/vertex arrangements, or full collision-system parity. The generated binary is linked from the pinned CE source but executed as host ILP32 with the fixture's host-sized arenas.
