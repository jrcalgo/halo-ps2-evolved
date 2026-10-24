# M2 Step 7 — CE live player-root and cluster-refresh next-slice audit

Date: 2026-10-21  
Disposition: **feasible as a bounded, package-backed host consumer test, with a
strict boundary around what the fixture can claim.** CE's real root lookup and
`players_compute_combined_pvs()` refresh branch can be retained without
substituting fake parent-resolution semantics. A meaningful first test can use
real CE `data_array`/datum access, `object_get_and_verify_type()`,
`object_get_ultimate_parent()`, and `structure_bsp_get_cluster_pvs()` over
retail-package BSP PVS rows. It can prove that a player's stale cached cluster
is refreshed from its actual root object's current `location.cluster_index`
and that the refreshed cluster's PVS contributes to CE output.

It cannot, by merely seeding a `object_datum.location.cluster_index`, prove
that physics/collision correctly updates a moving object's location from its
position. That next causal link requires either a real CE location-update path
with its collision/BSP dependencies or a separately scoped source-derived
starting-location query. Do not label a seeded root location as live movement
or full player simulation.

## Existing Step 7 evidence and adjacent coverage

The current player-PVS qualification invokes CE's actual static
`players_compute_combined_pvs()` with the real CE player iterator, BSP PVS row
accessor, and vector OR. It covers ordinary local-game aggregation and the
local-player filter on six package-backed retail BSPs. All four synthetic CE
player datums have `unit_index == NONE`; `game_in_editor()` is fixed false and
the activating cluster is fixed to `NONE`. The wrapper aborts if object-root
lookup is attempted. This is deliberately correct scope control, not a gap in
that report's assertions ([qualification](m2-step7-player-pvs-aggregation-qualification-2026-10-21.md),
[fixture wrapper](../../tests/hcu_player_pvs_host32.c#L1),
[CE implementation](../../submodules/halo-ce-universal/source/game/players.c#L1789)).

The independent implementation cross-review rechecked that the real iterator,
PVS accessor, and OR implementation remain in the measured closure, while
explicitly listing live object-root refresh as uncovered
([cross-review](m2-step7-player-pvs-implementation-crossreview-2026-10-21.md)).
The separate player aggregation closure review had already recommended keeping
object-root refresh distinct and listed the exact call boundary
([closure review](m2-step7-player-pvs-closure-review-2026-10-21.md)).
Adjacent Step 7 evidence now includes package-backed CE collision hit/miss and
directional-face cases, CE BSP-location/weather consumers, and bounded map
transaction rollback/retry. Those do not execute a player datum pointing at a
live CE object root, nor do they execute a player tick. The collision fixtures
deliberately keep object adapters fail-closed
([collision qualification](m2-step7-independent-collision-golden-qualification-2026-10-21.md),
[location/weather qualification](m2-step7-ce-location-weather-qualification-2026-10-21.md)).

Plan consequence: this is a discrete subcheck of Step 7's CE BSP consumers and
must be appended only as such. It does not close Step 7, satisfy its target
capacity/retail runtime conditions, or waive Step 8 residency/capacity
dependencies in [the authoritative plan](../../plans/7.hcu-remake-m2-m4.md).

## Exact CE behavior to exercise

The ordinary-game branch in
[`players_compute_combined_pvs()`](../../submodules/halo-ce-universal/source/game/players.c#L1789)
does the following ([source lines 1803–1848](../../submodules/halo-ce-universal/source/game/players.c#L1803)):

1. Selects the active structure BSP and clears the complete 64-byte combined
   vector.
2. Iterates actual CE player datums. In local-only mode it skips a record whose
   `local_player_index` is `NONE`.
3. For a player with `unit_index != NONE`, resolves the ultimate parent object
   using `object_get_ultimate_parent(player->unit_index)`; reads that root
   object via `object_get()`; and, if the root location has a non-`NONE`
   `cluster_index`, writes that cluster back into `player->cluster_index`.
4. ORs the selected cluster's PVS into the 64-byte output.
5. Separately ORs any activating cluster. The first root-refresh slice should
   hold activation at `NONE` exactly as the current slice does, so activation
   cannot mask or confuse player-root inclusion.

The source tests `player->unit_index`, resolves `root_object_index`, and uses
the root's cluster; it does not validate object datum presence or bound parent
chain depth inside the function. Accordingly, test fixture construction must
make all identifiers, references, and termination links valid. A malformed
datum test belongs to robustness/security coverage and must not be mixed into a
parity golden that is meant to exercise valid CE inputs.

`object_get_ultimate_parent()` is the real CE traversal in
[`objects.c:361-372`](../../submodules/halo-ce-universal/source/objects/objects.c#L361).
It follows `parent_object_index` until `NONE`, returning the final/root index.
`object_get()` calls CE `object_get_and_verify_type()` through the production
macro ([`objects.h:193-197`](../../submodules/halo-ce-universal/source/objects/objects.h#L193));
the actual typed lookup is in
[`objects.c:287-307`](../../submodules/halo-ce-universal/source/objects/objects.c#L287)
and obtains the header through CE `datum_get()`.

## Can real CE object semantics be retained safely?

### Yes: root traversal and stale-cluster refresh

The first test is technically bounded if the compile/link closure confirms the
following actual CE implementations are retained:

- `players_compute_combined_pvs()` from `players.c`;
- `object_get_ultimate_parent()` and `object_get_and_verify_type()` from
  `objects.c`;
- `datum_get()` and (if used to construct records) `data_initialize()`,
  `data_make_valid()`, and `datum_new_at_index()` from `memory/data.c`;
- the existing real `data_iterator_new/next()`,
  `structure_bsp_get_cluster_pvs()`, and `bit_vector_or()` dependencies.

The CE `object_header_data` global is the real authoritative lookup table
([`objects.c:215`](../../submodules/halo-ce-universal/source/objects/objects.c#L215),
[`objects.h:494`](../../submodules/halo-ce-universal/source/objects/objects.h#L494)).
Its records are CE `object_header_datum` values containing the datum salt,
flags/type, cluster cache, size, and pointer to the corresponding
`object_datum` ([`objects.h:219-228`](../../submodules/halo-ce-universal/source/objects/objects.h#L219)).
The pointed-to `object_datum` contains the CE `_object_datum`, which in turn
contains `location` and `parent_object_index`
([`objects.h:256-318`](../../submodules/halo-ce-universal/source/objects/objects.h#L256)).
This naturally allows a valid child unit with a valid parent chain to resolve
to a root whose location differs from the child's, thereby testing the CE root
semantics rather than a hand-written adapter.

Use small, aligned, fixed-size test storage for real CE data-array headers,
object header records, object datums, and players. No `malloc` or fake lookup
should be needed in the fixture. Either initialize arrays via CE data APIs or
document and validate a manual CE-layout initializer if the full `data.c`
allocation/lifecycle pulls unrelated services. If construction uses
`datum_new_at_index()`, preserve CE's nonzero generation identifier and
`identifier_zero_invalid` semantics; a raw index with a mismatched salt must
not accidentally be accepted. The CE iterator itself constructs datum indices
as `identifier << 16 | absolute_index`
([`data.c:399-447`](../../submodules/halo-ce-universal/source/memory/data.c#L399)).

The fixture should maintain two deliberately different cluster values:
`player.cluster_index` starts at a valid but stale cluster `A`, while the
root object's valid current location is cluster `B`. The player has a live,
valid `unit_index` that names a child object attached to the root. Select `A`
and `B` using the raw source-map oracle already used by the aggregation test,
with PVS rows `PVS(A) != PVS(B)`; a stronger case has a third local player's
cluster so expected output is `PVS(B) OR PVS(C)`, not `PVS(A) OR PVS(C)`. The
local-only and all-player outputs should still differ via a valid nonlocal
player datum. Run the same call twice: first call must change the cached
cluster A→B and produce the B-based vector; second call must be idempotent.

That is a real CE consumer-path test. The test supplies a valid current CE
object location as input; it does not claim to reproduce how a moving actor
acquired that location.

### Not yet: proving location refresh from position/physics

CE location assignment is a separate path. `scenario_location_from_point()`
uses `bsp3d_test_point()` and then maps the resulting leaf to a structure
cluster ([`scenario.c:861-908`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L861));
collision paths update `collision.location` from the contacted leaf (e.g.
[`collisions.c:560-591`](../../submodules/halo-ce-universal/source/physics/collisions.c#L560)).
The `players_compute_combined_pvs()` reader only consumes the already-current
`object.location.cluster_index`. Therefore a root object manually initialized
at B is not proof that CE correctly moved it from A to B. To qualify that
cause, a later separate test must execute the actual bounded CE update that
owns location for the relevant object/player path—ideally CE point-to-leaf
location mapping over the same raw-derived BSP, and only then broaden to the
physics/collision state transition where appropriate. Do not pull the full
player tick merely to claim this narrow read/refresh behavior; it would greatly
expand the source closure and bring unrelated gameplay/platform services.

The object array pointer itself is a legitimate test boundary only if it is
populated with authentic CE datums and the identifiers/links satisfy CE's
contracts. A fake `object_get_ultimate_parent()` or fake `object_get()` would
erase the exact behavior under test and is unacceptable. Existing fixture
adapters should stay fail-closed for every unrelated collision, editor,
activation, render, and gameplay dependency.

## Required package and oracle data

Use the existing hash-bound retail `a30`/`a50` packages and original Xbox
decompressed maps already recorded by the current PVS/collision reports. Keep
the package image as the bytes CE reads; derive expected values independently
from raw Xbox data (never from CE's output).

At minimum, the oracle needs:

1. Two in-range cluster PVS rows with different bit vectors. The existing
   `retail_source_player_pvs_oracle()` already discovers clusters with
   distinguishable PVS contributions and produces all 16 expected words.
2. A legitimate cluster relationship for the selected root. Prefer a scenario
   player spawn or named scenario object whose raw position can be resolved
   through the source BSP3D tree and `structure_leaf` records to the same
   cluster B. If the test only sets a live root location directly, label the
   location as a fixture input, and retain the independent raw PVS oracle for
   the expected output.
3. CE cluster count and PVS storage consistent with the selected published
   BSP, and valid `object_header_data`/player datum records whose capacities,
   counts, salts, and pointers are in-bounds.
4. A valid object graph of at least two object records: player unit → attached
   child (if needed for demonstrating ultimate-parent behavior) → root with
   `parent_object_index == NONE`. For the minimum test, the player unit may
   itself be the root; but that verifies only a one-node traversal. A child/root
   chain adds meaningful proof that parent traversal—not merely direct lookup—
   is real. Add a three-node chain only if some CE-supported gameplay setup
   needs it; don't invent arbitrary graph depth.

Potential map-data source: the already materialized `scenario` and BSP data
exposed by the package-backed fixture. The current PVS test constructs
synthetic player datums rather than reading a scenario spawn, so raw spawn
selection and raw BSP3D location mapping need explicit implementation and
cross-check before claiming data-derived player placement. Retail object
placement fields are not a substitute for a player spawn, and a static scenario
placement is not a runtime player's object datum.

## Fixture seams and fail-closed behavior

Retain only narrow environmental seams:

| Seam | Allowed behavior in this slice | Fail-closed rule |
|---|---|---|
| `game_in_editor()` | Return `FALSE` to select the ordinary game branch | Any editor-camera observer/scenario-leaf call aborts |
| `objects_get_activating_cluster_index()` | Return `NONE` to isolate player-root contribution | Any activation-object behavior is separately unqualified; do not claim activation coverage |
| player iterator/global BSP | Use actual CE `player_data`, iterator, current BSP and actual PVS implementation | No fake `players_compute_combined_pvs`, data iterator, PVS getter, or OR |
| object lookup | Link actual `object_get_ultimate_parent()` and `object_get_and_verify_type()` over actual CE `object_header_data` and object datums | Any unrelated object service callback aborts; invalid index/type should use CE's real assertion behavior, not silently return a valid root |
| raw oracle | Independent Xbox map/package parser chooses cluster rows and expected bit vectors | Never derive golden values from the CE output or a checked-in opaque vector |

For valid-input parity, the objects and player datums must remain byte-stable
except for the expected `player.cluster_index` A→B write. Snapshot player
records before/after and assert that exact field is the sole changed field.
Object header bytes, root and child datums, BSP PVS bytes, current BSP
publication identity, scenario BSP index, and collision-user depth must remain
unchanged. Check `player.unit_index`, local-player status, and the root's
location cluster before and after. Place guard bytes around all fixed storage
and assert no overwrite. If pool/table invalidity tests are later desired,
isolate them as explicit CE error-path tests; a valid-record golden must never
depend on undefined lookup behavior.

## Exact tests and evidence required for this subcheck

1. **Root-chain refresh:** stale player cluster A, player unit child, child
   parent root, root cluster B; call actual CE aggregator; assert cached cluster
   becomes B and exact raw-oracle output equals `PVS(B)`.
2. **Root versus child distinction:** child has a different valid cluster A
   from root B; prove output uses B, not child A. CE's production branch
   intentionally looks up `object_get_ultimate_parent()`.
3. **No stale fallback when root has a valid cluster:** A != B and root B is
   valid, proving the old cache is overwritten. If root cluster is `NONE`, CE
   leaves the cached player cluster unchanged; this is a distinct CE semantic
   worth testing as a second case, with expected output from stale A. Do not
   turn it into a fake failure policy.
4. **Local filtering:** use one non-local player with a distinct cluster and
   confirm local-only excludes it even when its unit has a valid object graph;
   all-player mode includes it. This catches accidental early iteration/lookup
   differences.
5. **Idempotence:** repeat the exact aggregation without changing any object
   state and verify identical PVS plus no second player mutation.
6. **Sparse datum iteration (optional if cheap):** leave a real deleted player
   slot between valid records using CE data semantics; confirm real iterator
   skips the empty record. This is adjacent to, not required for root-refresh
   correctness since real iteration is already qualified in the current slice.
7. **Closure review:** retain link map and show the actual root and typed lookup
   symbols plus iterator/PVS/OR symbols. Any fake object-root adapter is a test
   failure. Review unresolved symbols, source references, and aggregate bytes;
   do not infer EE budget compliance from a host link.
8. **Run and provenance:** use the established approved native ILP32 retail
   package command, exact source pins, package manifest/map hashes, fixture
   executable/map hashes, generated raw oracle hash, and logs. The regular
   sandbox SIGSYS skip is not evidence. No PCSX2/EE scene or Step 8 capacity
   claim follows from this host test.

## Remaining scope and dependency ordering

This next slice would close only the **CE player root resolution and cached
cluster refresh into PVS aggregation** for its explicit valid root-chain cases
and the audited BSPs. It would still leave these Step 7 items open:

- deriving the runtime root object's current cluster from movement/collision,
  rather than supplying a valid location datum to the aggregator;
- editor-camera PVS, activating-object PVS, and moving activation ownership;
- collision edge/grazing/vertex and flagged/breakable/invisible-surface cases;
- player movement and dynamic object/actor collision integration;
- failure-atomicity and bounded residency/capacity for full scenario data;
- Step 8 resident map high-water/capacity, required before target collision or
  gameplay claims;
- production PS2 target/PCSX2 gameplay run and render evidence required by
  later plan gates.

Do not jump to target validation by assigning these host object records to
`dynamic_simulation`: a test's fixed host arrays are not a measured CE runtime
pool. The Step 7 PVS evidence and this proposed follow-up are ordinary-game
state consumers; Halo-64 is useful only as a comparator for keeping simulation
ownership distinct from rendering ([`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)).
Its N64 omissions/capacity do not determine this PS2 fixture or port. REA is
not appropriate here: CE source, its data layouts, and retail map/package bytes
are directly inspectable, and no opaque executable behavior is needed.

## Source references

- CE player aggregator: [`players.c:1789-1877`](../../submodules/halo-ce-universal/source/game/players.c#L1789)
- CE object root and typed lookup: [`objects.c:287-307`](../../submodules/halo-ce-universal/source/objects/objects.c#L287),
  [`objects.c:361-372`](../../submodules/halo-ce-universal/source/objects/objects.c#L361)
- CE object/player record declarations: [`objects.h:219-228,256-318`](../../submodules/halo-ce-universal/source/objects/objects.h#L219),
  [`players.h:82-121`](../../submodules/halo-ce-universal/source/game/players.h#L82)
- CE datum lookup/iteration: [`data.c:91-112,399-447`](../../submodules/halo-ce-universal/source/memory/data.c#L91)
- CE point-to-location semantics: [`scenario.c:611-614,861-908`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L611)
- CE BSP cluster PVS and OR: [`structure_bsp_definitions.c:45-68`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L45),
  [`integer_math.c:346-363`](../../submodules/halo-ce-universal/source/math/integer_math.c#L346)
- Current coverage and adjacent Step 7 plan ledger:
  [`PVS qualification`](m2-step7-player-pvs-aggregation-qualification-2026-10-21.md),
  [`PVS cross-review`](m2-step7-player-pvs-implementation-crossreview-2026-10-21.md),
  [`plan Step 7`](../../plans/7.hcu-remake-m2-m4.md#L600)
