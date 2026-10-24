# Step 7 PVS, player-cluster, portal, and leaf consumer follow-up

Date: 2026-10-21. Report-only audit for the multiplayer product scope in
[`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md). Campaign
maps are excluded. Co-op and AI bots remain in scope when running a
multiplayer map. No implementation or plan file was changed, and no tests were
run for this report.

## Bottom line

The most important remaining source-backed gap is now narrow and testable:
run CE's real player combined-PVS consumer and root-cluster refresh on
**multiplayer package data**, not only on the existing `a30`/`a50` campaign
packages. The recent Longest/Blood Gulch fixture materially helps: it loads
real CE scenario/BSP state, checks an independent source-derived collision
tuple and every raw PVS row, and repeats load/query/unload at the candidate
arena sizes. But its PVS query calls `structure_bsp_get_cluster_pvs()` directly;
it does not create CE player datums or exercise `players_compute_combined_pvs()`
([`hcu_mp_capacity_main.c:5-42`](../../tests/hcu_mp_capacity_main.c#L5)).

There is already a good CE player aggregate/root-refresh fixture, but it is
bound to `a30` and `a50`, which are campaign maps and therefore cannot close a
multiplayer-only acceptance gate. Its raw oracle is generalizable, and the
same two packages also support location/weather and sound consumer fixtures;
those findings should be treated as implementation patterns, not as evidence
for the supported multiplayer map set. The minimal next implementation is to
extend the current MP capacity transaction fixture with one real CE
player-PVS invocation per Longest and Blood Gulch load, using the map's raw
PVS rows to choose valid local/non-local/root clusters and construct
independent expected unions. Keep its current per-cluster raw-PVS comparison.

Portal/frustum traversal is a separate rendering adapter, not currently a
qualified CE runtime consumer. The offline topology test validates a tiny
graph and reciprocal links only; it does not run the PS2 runtime visibility
algorithm or compare its visible clusters/batches to CE. Do not close this as
part of the player-PVS fix. Keep portal/frustum behavior as an explicit
rendering follow-up under M3 unless the current Step 7 field ledger assigns a
specific BSP field to a Step 7 semantic gate.

## Source-backed behavior and current evidence

### Multiplayer player PVS and cluster ownership

CE's ordinary-game path clears a 64-byte output, enumerates the actual CE
player-data array, optionally excludes nonlocal players, follows each valid
player unit to its ultimate parent, refreshes `player.cluster_index` from the
root object's current location when that cluster is not `NONE`, ORs the
selected cluster PVS rows, and finally includes the activating cluster when
present ([`players.c:1789-1848`](../../submodules/halo-ce-universal/source/game/players.c#L1789)).
The existing host test invokes the actual static CE helper, real CE player
iterator, PVS accessor, bit-vector OR, and—after its follow-up—real CE object
parent/type lookup. Its source-derived test cases prove local-only/all-player
aggregation, root refresh, `NONE` fallback, repeat stability, and unchanged
object/PVS/publication state. However, its raw-map golden generation and
package manifest still select only `a30`/`a50`
([`test_hcu_scenario_bsp_switch.py:452-555`](../../tests/test_hcu_scenario_bsp_switch.py#L452),
[`m2-step7-player-root-pvs-refresh-qualification-2026-10-21.md`](m2-step7-player-root-pvs-refresh-qualification-2026-10-21.md)).
Treat it as a valuable algorithm-level test, not multiplayer acceptance.

The MP fixture currently loads Longest and Blood Gulch twice and checks every
cluster row against source-map bytes, including the self bit, alongside one
collision hit and map lifecycle preservation
([`m2-multiplayer-production-capacity-host-2026-10-21.md`](m2-multiplayer-production-capacity-host-2026-10-21.md),
[`hcu_mp_capacity_main.c:5-42`](../../tests/hcu_mp_capacity_main.c#L5)).
This gives strong location-independent PVS payload evidence for those two MP
maps. It does **not** prove CE's player iteration/filtering/root refresh or
activation contribution on those maps. None of these host fixtures prove
target-sized EE operation; the MP capacity report explicitly limits its
evidence to native ILP32 and two maps.

### Leaf/location consumers

CE maps a point through `global_bsp3d_get()` to a leaf, then maps that leaf to
the BSP leaf's `cluster_index`, rejecting out-of-range leaves or clusters to
`NONE` ([`scenario.c:861-901`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L861)).
The collision test in the current MP capacity fixture confirms selected CE
collision start/hit leaf indices against the independent raw collision
golden. The broader CE scenario-switch test checks collision result leaf and
cluster fields against raw source data, but the reported package subcases are
campaign `a30`/`a50` ([`hcu_scenario_bsp_switch_main.c:1823-1895`](../../tests/hcu_scenario_bsp_switch_main.c#L1823)).
So the MP fixture is the right place to retain/extend the selected collision
leaf assertions; it should additionally run `scenario_location_from_point()`
directly on source-oracle points spanning at least two known leaves, a
clusterless leaf, and a point resolving to `NONE` if the raw map contains
those cases. This would establish the point→leaf→cluster mapping independently
of collision wrapper bookkeeping. Do not claim that a seeded root
`location.cluster_index` proves physics updated it from position.

The current player-PVS fixture fixes `game_in_editor() == FALSE` and the
activating-cluster getter to `NONE` for its narrow normal-game test
([`hcu_player_pvs_host32.c:12-33`](../../tests/hcu_player_pvs_host32.c#L12)).
The editor-only branch in CE derives visibility from observer camera 0's leaf
([`players.c:1850-1873`](../../submodules/halo-ce-universal/source/game/players.c#L1850));
the editor is outside the declared multiplayer product path, so this is not a
required parity gap. The activating-cluster path is in the ordinary game
branch, however, so it remains untested product behavior. Its owner is
`objects_get_activating_cluster_index()` and should be tested with the real CE
object state if a multiplayer scenario exercises activation; a stub returning
`NONE` is not evidence for that contribution.

### Portal/frustum visibility

CE's `structure_visibility_find_camera()` locates the camera through the BSP3D
tree and maps its leaf to a cluster; a missing/invalid result resets sky and
cluster state conservatively
([`structure_visibility.c:363-417`](../../submodules/halo-ce-universal/source/structures/structure_visibility.c#L363)).
When a cluster is available, CE traverses portals filtered by PVS and clipped
portal hulls, builds per-cluster frusta, then selects subcluster surfaces
([`structure_visibility.c:1653-1818`](../../submodules/halo-ce-universal/source/structures/structure_visibility.c#L1653),
[`structure_visibility.c:1830-1987`](../../submodules/halo-ce-universal/source/structures/structure_visibility.c#L1830)).
These are BSP-data consumers, but the actual PS2 draw path is the separate
halo-ps2 renderer. Its parent visibility wrapper has a conservative
all-cluster variant and an out-of-world fallback variant
([`src/world/visibility.c:1-12`](../../src/world/visibility.c#L1),
[`src/world/visibility_portal.c:1-14`](../../src/world/visibility_portal.c#L1));
the upstream portal algorithm is in
[`engine/src/render/vis.c:89-177`](../../submodules/halo-ps2/engine/src/render/vis.c#L89).
The existing [`test_visibility_audit.py`](../../tests/test_visibility_audit.py)
checks a synthetic two-cluster topology and rejects a missing reciprocal link,
bad plane, or reversed sides. It does not call `vis_run()`, exercise projection
or near-plane handling, or compare camera-visible clusters/batches to CE.

That means portal/frustum runtime parity is **not proven**. Its implementation
and acceptance belong with the render adapter/scene gate, not with the
smallest Step 7 PVS closure. If Step 7 must disposition each source member,
record portal/subcluster/surface-reference and bounds fields as retained and
their CE/PS2 owners as above; do not infer that a validated graph equals a
validated visibility result.

## Smallest next implementation/test

Extend `tests/hcu_mp_capacity_main.c` and its runner
[`tests/test_hcu_mp_capacity.py`](../../tests/test_hcu_mp_capacity.py) to add
one `mp_player_pvs_query(map_id)` after each successful `scenario_load()`:

1. Generate player cluster choices and expected 16-word unions from the same
   original Longest/Blood Gulch map bytes already used for collision/PVS
   goldens. Select two local clusters, one nonlocal cluster that changes the
   all-player union, and a distinct root cluster that changes the local union.
2. Populate actual CE `player_data` records and valid CE object headers/datums
   using the already-working isolated CE fixture construction pattern; one
   local player's unit is a child whose ultimate parent has that root cluster.
   Keep other actors disconnected only where the CE iterator expects that
   representation. Do not stub `object_get_ultimate_parent()` or
   `object_get_and_verify_type()`.
3. Call real `players_compute_combined_pvs()` through the existing test
   wrapper for both all-player and local-player-only modes. Check all 16 output
   words, that only the intended player's cached cluster changes, root
   `NONE` falls back to the old valid cluster, and a repeated call is
   idempotent. Add activating-cluster behavior only if actual CE activation
   owner can remain in this measured closure; otherwise mark it as an explicit
   remaining consumer row.
4. Assert the active scenario/BSP identity, complete materialized PVS bytes,
   object data, owner/scratch usage, and map publication are unchanged except
   for the expected player cached cluster. Retain link map and hash the
   executable, runner, source maps, and packages.
5. Execute this against Longest and Blood Gulch in the existing repeated
   load/query/unload sequence. Require it to pass in the approved native ILP32
   path. Later, once Step 8's capacity design enables these maps, rerun a
   capacity-qualified target query; host arrays are not target evidence.

This avoids broadening the player test to editor code or full portal rendering
and closes a real CE consumer gap on the actual multiplayer product fixtures.

## What closes each adjacent subcheck

| Consumer | Evidence needed | Current disposition |
|---|---|---|
| Per-cluster retail PVS payload | Full raw-map row comparison for every cluster on supported MP maps | Longest/Blood Gulch pass; remaining 11 MP maps open |
| CE player aggregation/local filter/root refresh | Real CE player iterator and object-root chain; raw-derived expected all/local vectors on MP package maps | Existing pass is only campaign `a30`/`a50`; MP fixture is next |
| CE player activating-cluster contribution | Real CE activation owner plus expected PVS contribution from raw MP row | Open; normal-path test stubs activation to `NONE` |
| Point→leaf→cluster | Real CE `scenario_location_from_point()` and raw-map points/golden leaf+cluster, including no-cluster/outside cases | Collision leaf endpoints partly covered; direct MP consumer query open |
| Editor camera leaf→PVS | Only needed if editor mode becomes product scope | Not a multiplayer acceptance item currently |
| BSP portal/frustum/surface selection | Runtime PS2 `vis_run()`/adapter compared with CE/source oracle for camera positions, boundaries, near-plane portals, and expected visible batches/surfaces; exact artifact and target/PCSX2 visible result | Synthetic graph audit only; no CE/PS2 runtime differential |

Halo-64 is relevant only for its explicit separation of CPU-owned camera/frame
state from the renderer ([`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)).
It provides no portal/PVS oracle and its renderer cuts or N64 limits must not be
copied. REA is not applicable: this is inspectable source and raw-map data, not
an opaque executable investigation.
