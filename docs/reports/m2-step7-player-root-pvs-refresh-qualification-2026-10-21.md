# M2 Step 7 — CE player root-cluster refresh and NONE fallback

## Result

The package-backed retail transaction fixture now executes CE's real
`players_compute_combined_pvs()` through the player's valid child-unit → CE
object parent chain → typed root-object lookup. It verifies both the normal
root-cluster refresh and CE's fallback when the root cluster is `NONE`. The
native ILP32 test passed against the existing `a30` and `a50` package BSP
subcases: **1 passed, 1 deselected, 2 subtests passed in 132.33 s**.

The refreshed child deliberately begins in raw-source-derived cluster A while
its vehicle root is in distinct cluster B. For that case, CE updates only the
player's cluster to B, and both all-player and local-player 16-word PVS vectors
match the Python oracle derived from the raw map BSP. The fixture then restores
the player's prior cluster, sets the parent root location cluster to `NONE`,
and checks both vectors fall back to the original player cluster without
mutating that player record. Repeated calls in both states are stable. The
fixture also checks object headers/datums, the materialized PVS bytes, active
BSP publication identity, and collision-user depth remain unchanged. Eight
expected typed lookups are observed over the root-refresh and fallback calls.

## Source and test boundary

- The production behavior is CE `players_compute_combined_pvs()` in
  [`players.c:1789-1840`](../../submodules/halo-ce-universal/source/game/players.c#L1789),
  including the player-unit root walk and `NONE` guard before updating
  `player->cluster_index`.
- The fixture includes the pinned CE `objects.c` implementation in
  [`hcu_objects_host32.c`](../../tests/hcu_objects_host32.c), including real
  datum/type validation and ultimate-parent traversal. Only the external
  boundary required to select test object data is conditionally delegated to
  this real CE getter; the package transaction, CE PVS aggregation, data
  iterator, cluster-PVS accessor, and bit-vector union remain actual code.
- The raw-data oracle and package/source hash checks remain in
  [`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py)
  and generated `hcu_player_pvs_golden.h`. The native command was:

  ```sh
  PYTHONPATH=.:submodules/halo-ps2/tools \
    HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
    HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
    HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
    python3 -m pytest -s -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
  ```

The exact fixture and map hashes are `1987cadadc2e82683ec2daec201cc1e3502f85f735192a68076d4938b8bea95e`
and `03b0a6855b1da554f11827529b52d9287e257109f2fdbe8d4695b970ae516444`;
the updated C/Python inputs hash to
`006a8c2cbcf33ab996a529fb46a44c45fb7e257aa0a23c9c325c67540c45e7f6` and
`bd0e46901b7274565504f24d99c6449e529d99b87bb505b803d307953e47f55f`.

## Limits and remaining gates

This closes only the named host-side CE object-root/PVS refresh subcheck. The
player/object records are synthetic and the host fixture uses overprovisioned
arrays; it does not demonstrate that movement or collision updates the root
location on the target, run portal/frustum visibility, or establish EE capacity,
target pointer relocation, guest query results, or rendering. Step 8 remains a
hard dependency for a capacity-qualified target-sized query, and the current
all-campaign resident lower bounds still exceed the committed EE owner spans.
Do not promote this test to gameplay-map or Step 7 completion evidence.

Halo-64 remains useful only as an ownership/adapter comparator; its reduced
collision/gameplay scope and N64 memory limits do not define CE behavior or PS2
capacity. REA is not applicable because the implementation and map data are
inspectable and the evidence is a source-level host fixture, not a shipped
binary reverse-engineering task.
