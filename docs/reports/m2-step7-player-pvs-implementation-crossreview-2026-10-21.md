# M2 Step 7 player combined-PVS implementation cross-review

Date: 2026-10-21  
Disposition: **implementation and host evidence are sound for the narrow
normal-game player aggregation slice**. The test compares real CE output over
relocated retail BSP payloads with expected vectors independently decoded from
the source Xbox maps. It does not exercise the editor, activation, or live
object-location branches and must remain a partial Step 7 result.

## Cross-review scope and inspected artifacts

Reviewed the implementation in
[`tests/hcu_player_pvs_host32.c`](../../tests/hcu_player_pvs_host32.c),
[`tests/hcu_scenario_bsp_switch_main.c:781-858`](../../tests/hcu_scenario_bsp_switch_main.c#L781),
and [`tests/test_hcu_scenario_bsp_switch.py:163-241,735-758,790-1044`](../../tests/test_hcu_scenario_bsp_switch.py#L163).
Compared it with the CE implementation at
[`players.c:1789-1877`](../../submodules/halo-ce-universal/source/game/players.c#L1789),
player layout at [`players.h:82-121`](../../submodules/halo-ce-universal/source/game/players.h#L82),
the CE datum iterator at [`data.c:399-447`](../../submodules/halo-ce-universal/source/memory/data.c#L399),
the BSP PVS accessor at
[`structure_bsp_definitions.c:45-68`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L45),
and CE vector OR at
[`integer_math.c:346-363`](../../submodules/halo-ce-universal/source/math/integer_math.c#L346).
The retained artifacts in `build/m2-group-d-file-backed-transaction/` match
the hashes recorded by
[`m2-step7-player-pvs-aggregation-qualification-2026-10-21.md`](m2-step7-player-pvs-aggregation-qualification-2026-10-21.md):
ELF `d8745a7d…`, map `46f5c6b6…`, and golden header `b8714f29…`. All five
relevant HCU source files have the exact SHA-256 values listed in that
qualification report, and the HCU checkout is at its recorded commit; the
submodule's dirty changes are in other files, not these PVS/iterator sources.

## Findings

### CE function semantics: correct for claimed branch

The test-only TU includes the pinned CE `players.c` and exposes the static
aggregator with `hcu_test_players_compute_combined_pvs()`
([`hcu_player_pvs_host32.c:1-39`](../../tests/hcu_player_pvs_host32.c#L1)).
It fixes `game_in_editor()` to false and activating cluster to `NONE`, while
leaving the CE iterator, PVS row accessor, and bitwise aggregation calls real.
Those adapters are visibly documented as environmental scope, not CE
substitutions. Its `object_get_ultimate_parent()` adapter aborts if invoked.

The fixture initializes four correctly sized CE player records, sets all
`unit_index` values to `NONE`, supplies two local players with valid clusters,
one non-local player with a valid cluster, and one local player with `NONE`
cluster. It marks the manual array header valid with CE's `d@t@` signature,
sets bounded/count-consistent metadata, and gives each slot a nonzero datum
identifier ([`hcu_scenario_bsp_switch_main.c:821-840`](../../tests/hcu_scenario_bsp_switch_main.c#L821)).
The CE `data_iterator_new()` / `data_iterator_next()` path then visits these
records. Using `unit_index == NONE` correctly suppresses CE's root-object
location refresh (`players.c:1814-1824`) without bypassing the aggregation
loop. The test checks records remain byte-identical after both calls
([`hcu_scenario_bsp_switch_main.c:843-851`](../../tests/hcu_scenario_bsp_switch_main.c#L843)).

It calls the CE function for both `local_player_only == FALSE` and
`TRUE`, and requires different output vectors. This makes the non-local
player's selected cluster observably relevant to the all-player result while
being excluded from the local result. The player selection in Python is
source-driven: it searches the raw PVS matrix for two local clusters and a
non-local cluster whose row contributes at least one bit not already in the
local union ([`test_hcu_scenario_bsp_switch.py:207-241`](../../tests/test_hcu_scenario_bsp_switch.py#L207)).

### Oracle independence and expected-vector width: correct

The Python oracle reopens each original decompressed Xbox map, resolves BSP
extents from its source tag index, decodes the root and `cluster_data` address
from raw bytes, bounds the extent against the raw BSP image, and unpacks
little-endian PVS words itself ([`test_hcu_scenario_bsp_switch.py:163-206`](../../tests/test_hcu_scenario_bsp_switch.py#L163)).
Expected vectors are calculated from those raw rows, not from the relocated
CE accessor or CE routine. The surrounding package runner checks source-map
SHA against the audited package manifest, package SHA against the manifest,
and HP2 HMAP identity against the same source SHA before making the goldens
([`test_hcu_scenario_bsp_switch.py:834-879`](../../tests/test_hcu_scenario_bsp_switch.py#L834)).
The C fixture separately proves that the live PVS span lies within the
currently materialized BSP image and snapshots that span before calling CE
([`hcu_scenario_bsp_switch_main.c:806-819`](../../tests/hcu_scenario_bsp_switch_main.c#L806)).

Each expected vector is exactly 16 `unsigned long` words. Python initializes
all 16 words to zero, ORs the raw rows' `ceil(cluster_count / 32)` encoded
words, and writes all 16 into the generated header
([`test_hcu_scenario_bsp_switch.py:217-241,735-758`](../../tests/test_hcu_scenario_bsp_switch.py#L217)).
The target CE routine clears all 64 bytes and its CE `bit_vector_or()` combines
the required number of 32-bit words. The C test asserts `sizeof(unsigned long)
== 4`, compares all 16 words for both paths, and requires their inequality
([`hcu_scenario_bsp_switch_main.c:810-812,843-849`](../../tests/hcu_scenario_bsp_switch_main.c#L810)).
Thus high-word and zero-padding behavior is checked, not only a few leading
bits. Multiple clusters are intentionally provided: the audited maps include
12, 38, 39, 64, 72, and 82 clusters, covering one-, two-, and three-word
vectors and a 16-word result buffer.

One subtlety is intentional and correct: if a raw source row contains set bits
in the unused padding bits of its final word, Python preserves those bits;
CE's accessor returns the raw word and `bit_vector_or()` processes the whole
last word. The oracle is therefore testing actual encoded CE bit-vector
semantics, rather than masking to `cluster_count` and potentially disagreeing
with CE.

### Map binding, retained closure, and test assertions

The runner roots both the scenario-switch entry and PVS wrapper, compiles with
ILP32/short-wchar, function/data sections, and linker garbage collection, then
checks that the PVS function, wrapper, CE iterators, CE row accessor, and CE
OR routine appear in the retained map
([`test_hcu_scenario_bsp_switch.py:916-969`](../../tests/test_hcu_scenario_bsp_switch.py#L916)).
The final retained map has these expected implementations. Its selected
player-code sections include `players_compute_combined_pvs()` and the wrapper;
the many unrelated CE player sections listed elsewhere in the linker map are
in the “Discarded input sections” table. Thus the test does not pull the full
CE player gameplay implementation into the live closure.

This is an **integrated transaction binary**, not a PVS-only executable: the
link map also contains scenario switching, collision, sound-query, schema,
and file/package transaction dependencies required by the existing retail
fixture. The link map proves the required PVS functions are present and that
unrelated player functions are discarded; it is not a standalone accounting
of the incremental bytes attributable only to the PVS slice. The report's
phrase “measured retained closure” should be read with this fixture boundary
in mind. A separate PVS-only ELF/map would be needed to quantify its isolated
closure, but that is not needed to validate the current behavioral claim.

At runtime, `assert_relocated_player_pvs_aggregation()` is invoked from the
existing published-BSP consumer routine after each relevant map/BSP switch
([`hcu_scenario_bsp_switch_main.c:1098`](../../tests/hcu_scenario_bsp_switch_main.c#L1098),
with that consumer called at initial publication and subsequent selections at
[`hcu_scenario_bsp_switch_main.c:1684,1764,1779`](../../tests/hcu_scenario_bsp_switch_main.c#L1684)).
It finds the golden by map ID and current BSP index, checks cluster count,
compares both full vectors, checks player/PVS bytes and publication identity,
and emits a per-call marker. The Python harness requires a marker for each
expected BSP and matching cluster count
([`test_hcu_scenario_bsp_switch.py:1028-1044`](../../tests/test_hcu_scenario_bsp_switch.py#L1028)).
The fixture may query a given BSP more than once during the full transaction;
the parser collapses markers by BSP index rather than rejecting duplicate
markers. This is not a behavior-validation gap because every call performs
the vector assertions before emitting its marker, but if marker cardinality
is intended to be a strict one-query-per-BSP acceptance condition, the parser
should require exactly one marker per BSP or the documentation should keep
the current “at least one query per BSP” wording. Present docs correctly use
“for every published BSP” rather than claiming exactly one execution.

## Evidence limitations / required caveats

1. The routine's editor-camera branch is untested. `game_in_editor()` is a
   non-constant adapter returning false; its CE branch still exists in the
   compiled routine, but no test assertion covers it.
2. The activating-cluster contribution is intentionally fixed to `NONE` by
   an adapter. It does not verify `object_globals` state or CE's
   `objects_get_activating_cluster_index()` implementation.
3. The player-to-object root path and live `cluster_index` refresh are not
   tested because every player has `unit_index == NONE`. The aborting
   `object_get_ultimate_parent()` adapter prevents an accidental unsupported
   path from silently passing.
4. This is CE's aggregate cluster-PVS vector, not portal/frustum culling or
   the final render visibility set; no draw/render claim follows.
5. The package fixture is host-side and its BSP scratch/cache arrays are
   overprovisioned. It gives no Step 8 capacity, EE physical placement,
   PCSX2 gameplay-map, or rendered-scene evidence.
6. The test verifies source-derived expected vectors but does not persist the
   generated golden header as a tracked source artifact; it retains the header
   with the executable/map when the retention environment variable is set.
   Reproducibility depends on the source map/package files and audited
   manifest, whose hashes are checked by the runner.

## Cross-review disposition

Accept this as a completed **host-side CE player cluster-PVS aggregation and
local-player filtering subcheck** for the six exact source-hash-bound retail
BSPs listed in the qualification report. The all-16-word raw-map oracle,
CE iterator, actual CE aggregation, data immutability checks, and package/BSP
identity checks are credible and correctly scoped. Keep Step 7 partial: this
cross-review does not close remaining collision, other BSP-consumer,
failure-atomicity, Step 8 capacity, or target-query dependencies.

The qualification report's claim that the map includes the CE routine, real
iterator, PVS accessor, and OR implementation is verified. Avoid describing
the entire combined transaction link as a PVS-only closure; the combined
fixture contains other independently required CE/PS2 test closures.
