# Step 7 — Multiplayer fog-plane side and underwater query

Status: **position-sensitive CE queries pass on the three stock multiplayer
BSPs with valid raw fog-plane chains**. This closes only this fog-selection
subcheck. It does not establish PS2 target capacity, visual fog rendering, or
bot fog attenuation, and does not close Step 7.

## What was tested

[`scenario_get_fog_region_index()`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L632)
was already tested on all 239 clusters of the 13 stock MP maps with
`position == NULL` by the all-map source oracle. That test did not exercise a
plane side. This fixture adds actual non-null point calls and invokes
[`scenario_location_underwater()`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L694)
on the selected and opposite sides.

[`tools/test_hcu_mp_fog_plane_sides.py`](../../tools/test_hcu_mp_fog_plane_sides.py)
is a focused extension of the existing package-backed fixture and raw-BSP
oracle in [`tools/test_hcu_mp_fog_selection_all.py`](../../tools/test_hcu_mp_fog_selection_all.py).
It generates the C assertions into the retained all-map fixture; it does not
modify HCU production code. Plane candidates are sourced from the raw Xbox
BSP `cluster.fog_reference`, `fog_planes[].region_index`, and all four raw
plane coefficients, with region/palette bounds checked against the raw map.
The C side compares relocated HCU plane coefficients with those raw goldens,
derives points from the raw equation beyond either side by more than the plane
offset, then runs the actual CE selector and underwater consumer.

Only three MP maps contain valid fog-plane → region → fog-palette → fog-tag
chains in the pinned retail source set:

| Map | Plane-side rows per lifecycle | Two-cycle rows | Source map SHA-256 | Raw BSP SHA-256 |
| --- | ---: | ---: | --- | --- |
| Beaver Creek | 29 | 58 | `eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a` | `1fb6efe09129d9c477cac22e0462138b368e1b7e8228062110f2e3e52849c7c4` |
| Chill Out | 10 | 20 | `52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb` | `2f8e7f85c0e52bf4a25bede449d1499068f629959bead6feb25574a47e8ad733` |
| Damnation | 12 | 24 | `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c` | `d3118effad059fde0083f0fd6abc45b824048fd6fe22867047ae6973ac330087` |

For each row, the test verified:

1. The relocated cluster reference and plane→region index agree with the
   source-derived golden.
2. The generated point on the selected side returns that region; the point on
   the opposite side returns `NONE`.
3. `scenario_location_underwater()` returns the fog definition's water flag
   for the selected side, false for the opposite side, and the expected
   region-weather palette or cluster-weather fallback for each side (invalid
   palette indices normalize to `NONE`).
4. BSP publication pointers/index and the collision-user stack remain
   unchanged after the queries. All three maps are queried in both lifecycle
   cycles, so this also exercises the consumer after map reload.

Observed `underwater=0` on every candidate. These shipped multiplayer fog
definitions are air-type in this data set; there is no valid water-flagged MP
sample here. The test verifies the air-side result and selection/palette
behavior, but it must not be cited as proof of a retail water-fog example.

## Execution and evidence

The invocation `python3 tools/test_hcu_mp_fog_plane_sides.py` compiled the
fixture successfully. The sandbox skipped native ILP32 execution with SIGSYS,
so the retained executable was run in the approved native execution context:

```sh
build/mp-fog-selection-1792696425464382832/mp-weather-wind-location \
  build/mp-fog-selection-1792696425464382832/assets/ \
  > build/mp-fog-selection-1792696425464382832/run.log 2>&1
```

Exit status: **0**. The captured output contains 102
`mp-fog-plane-sides ... status=passed` rows (58/20/24 above), all 26
all-map fog-selection summaries passed across the two lifecycle cycles, and
the final `mp-host-collision 13-map CE hit/PVS/reload matrix passed` marker.
The test executable is host ILP32, not R5900/PCSX2 evidence.

Source pins (parent / HCU / halo-ps2 / Halo-64):
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c` /
`6933490b2d16bb1c637295b6a0f3880ba23a7d56` /
`71183bb0a9adc586cd267b2780c82bbc12cfd95b` /
`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.

| Artifact | SHA-256 |
| --- | --- |
| Unique runner `tools/test_hcu_mp_fog_plane_sides.py` | `39abe39198ba846c169a09c1cbdb9598a192f11c78ccdb7af1a00ce393dd8b1f` |
| Generated C fixture | `b52b8a92ce701fb96d8de4934e389014958251811c2111255b1b37443cef126b` |
| Host ILP32 executable | `04c2f76b0941ef1e5f1b5180785f3e3e03f19448ca8787bc7ec8473157d19a82` |
| Link map | `87da11db93785493a86b392a021f83a427d8efaef57fa8009d1fa98445d4cbf2` |
| Raw 13-map fog-reference and plane inventory | `eb440489d2e1ec8bc4f5e8932f75664ca1a3a7b305a74ea6c43092231e7210dc` |
| Native execution log | `4ee1a6e478f6ec3072ed5daa51242bd2a8dee4a849a595821f6832d2fda80b76` |

HCU's [`scenario_fog_at_point()`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L803)
remains a separate constant-zero stub. Bot perception/attenuation is not
invoked by these calls, and these geometric plane-side results do not prove
that AI fog attenuation is necessary or define its behavior. Halo-64's
[`scenario_fog_at_point()`](../../submodules/halo-64/source/scenario/scenario.c#L780)
is also a zero stub, a comparison only—not retail Xbox behavior evidence.
