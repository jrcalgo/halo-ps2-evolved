# Step 7 — bounded search for a real visible-PVS sound geometry ray

## Result

No raw-source hit oracle was promoted. For Blood Gulch, the pinned source pair
`0 → 1` is PVS-visible and has encoded sound-distance byte `0`, but a bounded
sample of **900** listener-to-source segments produced no segment with exactly
one in-range collision-polygon contact. This is a negative result about this
sample, not proof that no qualifying ray exists in the map.

The search read the decompressed retail BSP, derived the collision-vertex
axis-aligned bounds, and used `random.Random(9411)` to sample points uniformly
inside those bounds. Point classification walked the serialized BSP3D planes
to a collision leaf, then mapped that leaf through the structure-leaf cluster
index. It retained 30 points in cluster 0 and 30 in cluster 1, then tested all
30 × 30 connecting segments against decoded collision-surface polygons using
their serialized planes and edge-ring vertices. The raw map SHA-256 was
`9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`.

No generated candidate was passed through CE. In particular, the scan did not
prove serialized leaf BSP2D face selection for a qualifying point, and did not
establish a test-safe dynamic-object scene for CE's wrapper. The existing sound
query passes structure, media, objects, scenery, and machines flags to
`collision_test_vector()` ([`game_sound.c:1004-1024`](../../submodules/halo-ce-universal/source/sound/game_sound.c#L1004)); the general CE wrapper can enumerate collideable objects after BSP traversal ([`collisions.c:642-690`](../../submodules/halo-ce-universal/source/physics/collisions.c#L642)). Disabling those flags, using the CE result as its own expected value, or substituting another controlled spy would not qualify real geometry. Keep the existing visible-PVS spy test labeled policy-only until a source-routed ray and bounded collision-owner closure are established.

## Source pins and limits

Parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`; halo-ce-universal
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`; halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The sample seed and counts above
describe the bounded one-off raw-source search; no production source, fixture,
plan, map, or package was modified. No test binary, target-memory result,
PCSX2 evidence, sound playback, or geometry-parity acceptance is claimed.
