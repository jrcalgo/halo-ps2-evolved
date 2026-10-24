# Step 7 CE player combined-PVS fixture closure review

Date: 2026-10-21  
Scope: report-only feasibility assessment for a host ILP32 fixture that calls
Halo CE's actual `players_compute_combined_pvs()` against the audited BSP data.  
Conclusion: feasible with a narrow compile/link closure, provided the fixture
labels exactly which branches are exercised and does not disguise adapter
stubs as CE behavior.

## Relevant production behavior

The target routine is a `static` function in
`submodules/halo-ce-universal/source/game/players.c:1789-1791`. It obtains the
active structure BSP, clears 64 bytes of output, and chooses the normal-game
branch unless `game_in_editor()` returns true (`players.c:1803-1805`). In normal
game mode it obtains the activating cluster, iterates `player_data`, optionally
filters to local players, and ORs each valid player's cluster PVS into the
output (`players.c:1807-1837`). It then includes the activating cluster PVS if
one exists (`players.c:1839-1848`). The editor branch instead derives a leaf
from observer camera 0 and includes that leaf's cluster PVS
(`players.c:1850-1877`).

For players with a non-`NONE` `unit_index`, CE follows the object's ultimate
parent and refreshes the player's cached `cluster_index` from the root object's
location (`players.c:1814-1824`). A deliberately narrow aggregation fixture
should set every player's `unit_index` to `NONE`; this exercises the actual
player aggregation and local-player filter without pretending to test object
identity, attachment/root traversal, or live location refresh.

The CE player datum contains the relevant `identifier`, `local_player_index`,
`unit_index`, and `cluster_index` fields in
`submodules/halo-ce-universal/source/game/players.h:82-97`. `player_data` is an
exported global (`players.h:459`) defined by the player subsystem
(`players.c:507`). A test wrapper defined in the same translation unit after
including `players.c` can call the otherwise-static routine without changing
production visibility. Alternatively, a narrowly guarded test seam could
export a wrapper; including the source is preferable for a fixture-only
translation unit.

## Exact direct dependencies and feasible boundary

For the normal-game path with `unit_index == NONE`, the routine directly needs:

| Dependency | Reason | Source reference |
|---|---|---|
| `global_structure_bsp_get()` | Select current BSP and read cluster count | `players.c:1803`; declaration `source/scenario/scenario.h:100` |
| `game_in_editor()` | Select normal-game versus editor-camera path | `players.c:1805`; PS2 stub exists at `port/ps2/src/ps2_local_profile.c:30` |
| `objects_get_activating_cluster_index()` | Include temporary activation PVS when present | `players.c:1807,1839-1848`; API `source/objects/objects.h:385-392` |
| `player_data`, CE iterator APIs | Enumerate player datums | `players.c:1808-1809`; declarations `source/memory/data.h:21-69` |
| `structure_bsp_get_cluster_pvs()` | Fetch each cluster's CE vector | `players.c:1829-1835`; implementation `source/structures/structure_bsp_definitions.c:45-68` |
| `bit_vector_or()` | Combine each PVS into result | `players.c:1829-1835`; implementation `source/math/integer_math.c:346-363` |
| `csmemset()` | Clear the 64-byte PVS output | `players.c:1804` |

Avoiding non-`NONE` player units removes the only direct calls to
`object_get_ultimate_parent()` and `object_get()` from this function
(`players.c:1814-1823`). Setting editor mode false removes observer-camera and
scenario-leaf dependencies (`players.c:1850-1877`). Returning `NONE` for the
activating cluster scopes out the additional activation-vector contribution;
that is valid for a test specifically named “player aggregation without
activation,” but not a complete coverage claim for CE's function.

`structure_bsp_get_cluster_pvs()` directly checks the requested cluster and
that the cluster-data block contains its vector, then calculates the vector
address using CE's bit-vector sizing (`structure_bsp_definitions.c:49-67`). The
fixture must therefore initialize `clusters.count`, `cluster_data.address`,
and `cluster_data.size` consistently with the actual audited retail BSP, not
inject arbitrary expected outputs. `bit_vector_or()` combines exactly
`BIT_VECTOR_SIZE_IN_LONGS(count)` words (`integer_math.c:346-363`). Under the
existing host ILP32 build flags, this preserves the target's 32-bit `unsigned
long` word behavior.

## Player data construction options

The CE `data_array` and iterator layouts are declared in
`source/memory/data.h:21-69`; `data_iterator_new()` and
`data_iterator_next()` are implemented in `source/memory/data.c:399-447`.
`data_iterator_next()` walks live records up to `data->count`, skipping empty
headers and returning each live datum (`data.c:431-447`). This is useful to
exercise real slot iteration, sparse holes, and record ordering.

Preferred fixture approach: compile the real CE `memory/data.c` iterator path,
initialize a small inline `data_array` plus datum backing according to the CE
layout, and create a few live datums using CE APIs where that does not pull in
irrelevant allocation services. The data array's `data` field points immediately
after its header under `data_initialize()` (`data.c:91-112`); `data_make_valid()`
marks it valid and clears its records via the CE deletion path (`data.c:341-348`).
Because this lifecycle may pull additional helpers, inspect the map after
linking. A smaller fallback is to manually seed a valid signature, counts,
record headers, and data pointer, then call the real CE iterator routines.
Hand-written iterator adapters are less valuable because they cease to test
the CE iteration semantics.

Use multiple live players with deliberate differences: local and nonlocal
`local_player_index`, clusters with overlapping and distinct PVS bits, one
`NONE` cluster, and optionally a deleted slot between live records. Call the
CE routine once with `local_player_only == FALSE` and once with `TRUE`.
Compare every output word to a separately computed OR of the audited raw BSP
cluster vectors. Also check zero live players (all-zero output), all-nonlocal
records in local-only mode (all-zero output), and untouched/sentinel words
beyond the cluster vector's required word count if the output semantics make
those relevant. Be careful that the routine always clears all 64 bytes before
ORing (`players.c:1804`), so the expected full 16-word output must account for
zero padding.

## Compile/link and runner recommendation

The current scenario-switch fixture establishes a practical pattern: generate
HCU MSVC-semantics compatibility headers, compile as ILP32 with
`-fshort-wchar`, `-ffunction-sections`, and `-fdata-sections`, link with
`--gc-sections`, retain a link map, then execute the small host binary
(`tests/test_hcu_scenario_bsp_switch.py:650-706`). Its existing runner compiles
`tests/hcu_scenario_bsp_switch_main.c` with `scenario.c` and an explicit root
symbol (`test_hcu_scenario_bsp_switch.py:682-695`).

Prefer a separate players-PVS fixture C file and one runner method rather than
adding player globals or dependencies to the scenario-switch transaction
fixture. Root only a test wrapper symbol, inspect the link map, and verify that
the retained closure is limited to the CE routine, data iteration, BSP PVS
accessor, bit-vector OR, and clearly named fixture adapters. Record unresolved
imports and exact closure rather than assuming section GC trimmed everything.
The test should compile against the same source pins already recorded by the
enclosing Step 7 evidence. A normal source include of `players.c` may compile a
large translation unit, but per-function/per-data sections should allow the
linker to discard unrelated player functions; compile success and a clean,
reviewed link map are required before calling that closure small.

The main fixture in `tests/hcu_scenario_bsp_switch_main.c` defines scenario/BSP
globals, common host adapters, and the retail transaction flow; its ordinary
test main begins at line 1789 (`hcu_scenario_bsp_switch_main.c:1789-1859`).
Avoid changing those globals or its transaction main just to accommodate this
consumer. A standalone test avoids accidental interaction with schema,
collision, map-switch and lifecycle assumptions.

## Explicit limitations and acceptance language

1. **Covered:** CE normal-game player aggregation, local-player filtering,
   real CE data iteration (if the real iterator option is used), and OR of the
   audited BSP's CE cluster PVS vectors.
2. **Not covered by the narrow fixture:** editor-camera path, activation-cluster
   contribution unless the actual CE object activation owner is linked,
   player-to-object root resolution, and refresh from a live object location.
3. **Do not call a stub an activation test.** The real activation state is held
   in `object_globals` and interpreted by `objects_get_activating_cluster_index`
   (`source/objects/objects.c:586-630`). A test adapter returning `NONE` is only
   an explicit “no activation” scenario.
4. **Do not treat this as Step 7 completion.** This is one meaningful CE BSP
   consumer check. Remaining Step 7 coverage and the target query/capacity
   dependency still require their own evidence.

## Recommended next implementation slice

Build a new minimal ILP32 executable with a wrapper around
`players_compute_combined_pvs()`. Use the actual CE function, actual
`data_iterator_*`, actual `structure_bsp_get_cluster_pvs()`, and actual
`bit_vector_or()`. Load the candidate CE player datums from the existing
hash-bound audited BSP package/oracle rather than re-decoding expected values
from a hand-authored fixture. First test no-activation normal-game behavior;
then, only if closure remains bounded, add an activation fixture using actual
`object_globals` and `objects_get_activating_cluster_index()` semantics.
Keep editor and object-root-refresh behavior separately listed as uncovered
unless their own real dependencies and corresponding golden fixtures are added.
