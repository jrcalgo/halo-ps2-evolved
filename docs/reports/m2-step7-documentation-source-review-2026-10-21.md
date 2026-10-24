# M2 Step 7 — Documentation/source review for player-root cluster refresh

Date: 2026-10-21  
Scope: report-only documentation and source review for the next Step 7 slice:
execute Halo CE's real player-unit → ultimate-object-root lookup and cached
cluster refresh before combined-PVS aggregation. This report does not modify
implementation, tests, or the plan.

## Current disposition

The existing package-backed PVS fixture is credible for the narrower behavior
it claims: aggregate raw-map-derived player cluster rows and local-player
filtering over six published retail BSPs. It deliberately sets every
`unit_index` to `NONE`, and its `object_get_ultimate_parent()` adapter aborts
if called ([current qualification](m2-step7-player-pvs-aggregation-qualification-2026-10-21.md),
[implementation cross-review](m2-step7-player-pvs-implementation-crossreview-2026-10-21.md)).
Therefore it does not exercise the production root-resolution/cluster-refresh
branch in CE `players_compute_combined_pvs()`.

The next bounded test should retain CE's actual player aggregator, object
typed-datum lookup, ultimate-parent traversal, player iterator, BSP PVS-row
accessor, and bit-vector OR. Construct valid fixed-storage CE player/object
records (including generation identifiers and terminating parent link) and
drive a stale cached player cluster A from a child unit whose ultimate parent
has valid current cluster B. The oracle must prove `PVS(B)` is selected, not
`PVS(A)` or the child's cluster; use a source-map-derived pair whose PVS rows
differ. A separate `root.cluster_index == NONE` case must preserve CE's stale
player cluster fallback. This tests consumption of a current root location,
not how movement/collision produced that location.

This matches the source-backed fixture design already recorded in
[the player-root next-slice audit](m2-step7-player-root-refresh-next-slice-audit-2026-10-21.md).
Its proposed seam restrictions and acceptance list remain appropriate. In
particular, a fake root resolver would erase the behavior under test, while a
manually seeded root location must not be described as proof of live movement.

## Applicable documentation and comparisons

### Halo CE / HCU

The inspected `submodules/halo-ce-universal/docs/` contains `custom_edition_caches.md`
and `mods.md`; neither documents player-PVS aggregation or object-root refresh.
For the current question, the CE source is authoritative, not an inferred
contract from those docs. The cache guide does provide an important adjacent
constraint: CE reads structure BSP vertex data through the BSP/tag loading
path for **visibility, collision, and lights**, and its renderer-specific
vertex compression/Custom Edition adaptation occurs at load time
([`custom_edition_caches.md:297-301`](../../submodules/halo-ce-universal/docs/custom_edition_caches.md#L297)).
Thus BSP fields should not be discarded merely because a current query fixture
reads only PVS rows; Step 7's broader consumer disposition still governs.

The production CE behavior is explicit in source:

- [`players.c:1789-1836`](../../submodules/halo-ce-universal/source/game/players.c#L1789)
  clears the 64-byte output, iterates actual player datums, filters non-local
  players only in local-only mode, resolves `unit_index` to
  `object_get_ultimate_parent()`, reads the root's `location.cluster_index`,
  writes a non-`NONE` root cluster back to the player datum, and ORs that
  cluster's PVS row.
- [`objects.c:361-372`](../../submodules/halo-ce-universal/source/objects/objects.c#L361)
  follows parent indices until `NONE`; it has no local depth/cycle guard, so
  fixture records must satisfy CE's valid acyclic object-graph precondition.
- [`objects.c:287-307`](../../submodules/halo-ce-universal/source/objects/objects.c#L287)
  and [`objects.h:193-197`](../../submodules/halo-ce-universal/source/objects/objects.h#L193)
  show that object access is typed datum/header lookup, not merely an array
  index. The test must preserve CE's index/salt/type contract.
- [`objects.c:1841-1897`](../../submodules/halo-ce-universal/source/objects/objects.c#L1841)
  distinguishes attached child objects from roots and establishes root
  location/cluster membership when connecting an unparented object. A child
  unit's own `location.cluster_index` is not a substitute for its ultimate
  parent's location in the player PVS path.
- [`structure_bsp_definitions.c:45-68`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L45)
  and [`integer_math.c:346-363`](../../submodules/halo-ce-universal/source/math/integer_math.c#L346)
  are the real cluster-row accessor and OR operation used downstream.

The adjacent CE Custom Edition cache guide confirms that loaded BSP contents
participate in multiple consumers; it is not evidence that parent-specific
PVS state, player records, or runtime datum lifetimes can be externalized.
Keep all of these as CE-owned runtime records for the fixture and leave the
serialized BSP PVS span read-only.

### Halo-64 comparator

There is no `submodules/halo-64/docs/` directory in this checkout. The
available useful comparison is [`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33),
which records that simulation does not consume render results, while the
excluded renderer nevertheless has to advance frame/camera/first-person/HUD
state. This supports keeping the concern boundaries explicit: player root and
cluster state are simulation-owned CE data; a PVS vector is not itself a
rendered visibility result. Halo-64's N64 memory/CPU constraints and feature
cuts are not applicable sizing or behavior authority for the PS2 and must not
be copied into this test or the HCU port.

### halo-ps2 and other PS2-submodule documentation

Only `submodules/halo-ps2/docs/` was present among the current submodule
documentation trees; no additional PS2 submodule docs were found in the
checkout. The PS2 BSP format guide is useful for data interpretation, not CE
runtime parity: [`08-bsp-section.md:24-38`](../../submodules/halo-ps2/docs/08-bsp-section.md#L24)
documents Xbox leaf→cluster and cluster/subcluster relationships and explicitly
notes that one surface can belong to multiple clusters. Its portal/PVS
discussion at [`08-bsp-section.md:145-152`](../../submodules/halo-ps2/docs/08-bsp-section.md#L145)
describes the PS2 engine's separate point-to-cluster and portal traversal
representation. Do not conflate that custom HP2 `bsp_find_cluster()` or
renderer traversal with CE's `players_compute_combined_pvs()`; each may be
used as a cross-check only after matching the same raw Xbox source values.

The PS2 specs say the game targets a 30 Hz simulation and no runtime heap
allocation after level load ([`02-specs.md:23-30`](../../submodules/halo-ps2/docs/02-specs.md#L23),
[`02-specs.md:75-89`](../../submodules/halo-ps2/docs/02-specs.md#L75)); they
also label the 32 MiB region split as budgets that must be measured
([`02-specs.md:111-125`](../../submodules/halo-ps2/docs/02-specs.md#L111)).
Accordingly, the host fixture may use small static arrays to model CE record
layouts, but it cannot assign those bytes to PS2 `dynamic_simulation`, claim
that the real object/player pools fit, or support an EE performance claim.
The test should retain CE semantics and defer pool sizing to Step 8 and target
evidence.

## Specific acceptance implications for the next slice

1. Keep the existing package transaction and raw Xbox-map PVS oracle. Choose
   A/B rows from a published BSP where the vectors differ; bind source map,
   package, fixture ELF, link map, and generated golden hashes together.
2. Use real CE `data_array` iteration plus authentic CE `object_header_data`
   and `object_datum` records. Include a child `unit_index` whose parent link
   reaches a distinct root record; root B must differ from child A and stale
   player A. Keep activation `NONE` and editor false so those independent
   branches cannot mask results.
3. Assert after the CE call that exactly the expected `player.cluster_index`
   field was changed A→B, the complete PVS equals the raw oracle for B (and
   any other deliberate player contributions), repeated invocation is
   idempotent, and player-local filtering still excludes a non-local player's
   root contribution.
4. Add a root-`NONE` case to assert the CE source behavior: the aggregator does
   not overwrite the cached player cluster when the root has no cluster.
   Do not “fix” this behavior in a test adapter or reinterpret it as an error.
5. Keep invalid salt, wrong type, cycle, or out-of-range object graphs out of
   the valid-input parity golden. CE's function assumes valid live datums and
   parent chains. If robustness handling is desired, isolate it as a separate
   error-path test and document any intentional port guard as a `HALO_PS2`
   divergence.
6. Retain the exact link map and verify that real CE root and typed-datum
   functions are linked, while any unrelated object/render/collision callback
   remains fail-closed. A combined fixture link proves presence, not isolated
   incremental memory cost or target pool fit.
7. Report only “CE root lookup and cached cluster refresh feeding player PVS
   aggregation on host ILP32 for tested raw-map-backed BSP cases.” It does not
   establish movement/collision updating `object.location`, editor camera,
   activating-cluster state, portal/frustum traversal, target-capacity fit,
   PCSX2 gameplay-map operation, or visible rendering.

## Documentation/source gaps and stale-risk notes

- The CE docs do not spell out player/object/PVS semantics; use the exact
  pinned source revisions and source hashes already included in the
  qualification artifacts. Reconfirm source hashes before applying findings
  if HCU pins or the dirty worktree change.
- Halo-64's notes are a useful architectural comparison only. They do not
  define PS2 limits or provide a PVS parity oracle.
- `halo-ps2/docs/08-bsp-section.md` describes the bespoke renderer's compact
  HP2 BSP and openly records uncertain source-data semantics (including
  certain tie/portal and surface cases). It must not be treated as proof of
  CE runtime acceptance or as permission to strip CE fields.
- The current aggregation report's package-backed result remains host-only
  and deliberately skips the live-root branch. A future root-refresh report
  must replace that limitation only for this newly exercised branch, without
  upgrading Step 7/M2 status globally.

REA is **not applicable** here: the behavior under review is fully exposed in
the pinned CE source and raw Xbox map/tag data. REA would add little unless a
specific opaque retail executable behavior or unexplained binary/runtime
divergence becomes the subject of a later comparison.

## Re-evaluation protocol

This is the first dated review section for the user-requested iterative
documentation review. When the main task reaches a new Step 7 slice, append a
dated addendum to this same report containing the exact newly reached plan
substep, relevant docs/source citations, current implementation/evidence
comparison, contradictions or non-applicable advice, and revised acceptance
implications. Keep earlier findings intact unless exact new evidence
supersedes them, and clearly identify such supersession. Do not edit production
code, tests, or plan from this reviewer role.

## Addendum — Step 7 real player-root refresh and Step 8 capacity feasibility

Date: 2026-10-21  
Scope: follow-up on the now-added host fixture for live CE player→object-root
cluster refresh, plus the Step 8 capacity evidence that gates production-sized
queries. Report-only; no implementation or plan edits.

### Step 7 implementation review: what the changed fixture now proves

The implementation has advanced beyond the synthetic-only baseline described
above. `tests/hcu_objects_host32.c` includes CE's actual `objects.c` with a
test-only symbol rename for the real `object_get_and_verify_type()` body; the
fixture dispatches its object lookup to that compiled implementation only
inside the root-refresh case ([wrapper TU](../../tests/hcu_objects_host32.c#L1),
[fixture dispatch](../../tests/hcu_scenario_bsp_switch_main.c#L226)). The test
uses a genuine CE object-header table and object datums, one biped child whose
`parent_object_index` names a vehicle root, and a root cluster B distinct from
both the player's stale A and the child's own A. CE `players_compute_combined_pvs()`
therefore exercises `object_get_ultimate_parent()` and typed datum lookup,
mutates the player cluster A→B, and aggregates the root's PVS row. It checks
full output against a source-map-generated oracle, verifies the exact expected
player-record mutation and unchanged object records/PVS/publication/collision
state, then repeats calls to prove idempotence ([fixture setup/assertions](../../tests/hcu_scenario_bsp_switch_main.c#L865),
[runner roots and checks the real closure](../../tests/test_hcu_scenario_bsp_switch.py#L955)).
This is a meaningful CE consumer-path increment, not merely an adapter returning
a test-selected parent.

The changed code appears consistent with CE's actual contracts: the child
parent index encodes identifier 2 and slot 1; the root header carries that
identifier and a valid datum pointer; `object_array` has the CE header-record
stride/signature and identifier-zero policy; both embedded `_object_datum`
records set their type and parent fields; the actual `datum_get()` path is
retained. CE's own `object_get_and_verify_type()` reads the typed object datum
from the object header and asserts the requested type
([`objects.c:287-303`](../../submodules/halo-ce-universal/source/objects/objects.c#L287));
`object_get_ultimate_parent()` follows that real parent field until `NONE`
([`objects.c:361-372`](../../submodules/halo-ce-universal/source/objects/objects.c#L361)).
The local-player case is also preserved: the fixture's nonlocal record has a
distinct source-derived row; the local-only and all-player root-output vectors
are independently compared. Exact root symbols are asserted in the link map,
which avoids mistaking only a fake lookup adapter for coverage.

Remaining acceptance limits for this subcheck:

1. Add the CE-prescribed root-`cluster_index == NONE` case. Source behavior is
   conditional: `players_compute_combined_pvs()` overwrites the cached player
   cluster only when the root cluster is not `NONE`; otherwise the old player
   cluster remains the aggregation input ([`players.c:1814-1835`](../../submodules/halo-ce-universal/source/game/players.c#L1814)).
   The new valid-root case does not establish this fallback.
2. The root's current cluster B is seeded in its valid CE `location`; this
   proves the player consumer reads the root location and refreshes its cache,
   not that CE movement/collision updates that location from world position.
   Keep those two claims separate. If later asserting the causal location
   update, it needs a separate CE point/BSP or collision path fixture.
3. The synthetic records are valid hand-built CE layouts, not records emitted
   through full `object_new()` or player spawn. This is acceptable for the
   narrow root-read behavior, but do not infer pool creation/lifetime, spawn,
   movement, attachment callbacks, or simulation-tick integration.
4. The fixture uses `malloc(pvs_bytes)` for its byte-preservation snapshot and
   host overprovisioned transaction buffers. This is test harness memory only,
   never evidence that the PS2 path may allocate or that target-sized BSP bytes
   fit. Assert exact root lookup count and preserve the current fail-closed
   behavior outside the tested lookup window.
5. No editor-camera, activating-cluster, portal/frustum, or actual rendered
   visibility branch is covered. Halo-64's note that simulation and render
   state have distinct responsibilities remains a boundary comparator only
   ([`NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)); do
   not interpret combined PVS as a rendered set.

The current Step 7 result should be reported as “host ILP32 CE player-root
lookup, valid ultimate-parent traversal, root-cluster refresh, and PVS
aggregation for the tested retail package/BSP cases,” once its current native
run is attached to exact artifact/source/package hashes. It does not satisfy
the Step 8 dependency for a production-capacity target query.

### Step 8 capacity evidence: decisive constraint and current implication

The authoritative execution plan describes Step 8 as fixed bind order and
backing lifetime, but the campaign-wide capacity/guest gates are separate and
remain open ([Step 8 plan entry](../../plans/7.hcu-remake-m2-m4.md#L612)).
The most useful current capacity sources are the independent campaign candidate
audit and the Step 8/10 blocker/topology reviews
([candidate lower bound](m2-2026-10-21-capacity-candidate-audit.md),
[campaign topology](m2-campaign-capacity-topology-review-2026-10-21.md),
[Step 8/10 audit](m2-step8-step10-capacity-and-guest-blocker-audit-2026-10-21.md)).
They agree on the important distinction: the current complete-CTAG + one
complete unmodified CE BSP representation cannot fit the existing `current_bsp`
owner for any campaign map; `d40 + d40_space` is only the favorable raw-pair
lower bound, not a viable mission load. The d20 all-owner lower bound reaches
30,087,556 B against the 27,787,264 B committed budget (2,300,292 B over)
before many required owners. The claims bitmap grows with the configured
tag+BSP span capacities; it is not map-payload space and cannot be overlaid on
the CE image. A streamed HP2 visitor can remove duplicate encoded staging, but
cannot remove the final contiguous CE raw-pointer image requirement.

The CE Custom Edition cache guide is comparative, not a PS2 solution. It
documents desktop CE's 512 MiB address window, 256 MiB texture cache, and
read-in-place map/resource model ([`custom_edition_caches.md:128-145`](../../submodules/halo-ce-universal/docs/custom_edition_caches.md#L128)).
Its loader validates resource/BSP ranges within that large mapped cache and
performs BSP vertex adaptation in CE's cache path
([`custom_edition_caches.md:180-207`](../../submodules/halo-ce-universal/docs/custom_edition_caches.md#L180),
[`custom_edition_caches.md:297-301`](../../submodules/halo-ce-universal/docs/custom_edition_caches.md#L297)).
Those pages support retaining CE validation and all BSP consumer data; they
cannot justify assuming a file-backed pointer on PS2 or treating a decoded
HP2 stream as resident EE storage.

The halo-ps2 design material states the product aims at all ten campaign
missions, 30 Hz simulation, no post-load heap, and 32 MiB EE RAM
([`02-specs.md:23-30`](../../submodules/halo-ps2/docs/02-specs.md#L23));
it also has an aspirational region split and explicitly says the paper total
has zero headroom and must be measured
([`02-specs.md:111-125`](../../submodules/halo-ps2/docs/02-specs.md#L111)).
These are product/hardware constraints and conceptual design targets, not
evidence that the present HCU-linked CE ownership topology fits. The older
spec's 9 MiB resident-data and 7 MiB BSP rows are different from the current
repository's budget-v2 owner sizes. Current budget-v2 numbers and exact binder
interfaces win for acceptance. Do not add capacities from the older spec to
budget-v2, double-count external GS/IOP/SPU2 stores as EE backing, or treat
unused 5.5 MiB reserve as spare.

The PS2 `08-bsp-section.md` describes a separate compact HP2 structure:
cluster/portal visibility and point-location tree are encoded as custom
pointer-free tables, with uncertainty explicitly recorded for some source-data
semantics ([`08-bsp-section.md:24-59`](../../submodules/halo-ps2/docs/08-bsp-section.md#L24),
[`08-bsp-section.md:145-152`](../../submodules/halo-ps2/docs/08-bsp-section.md#L145)).
That format could only replace a CE field family after full consumer inventory,
parity and source-data proofs; it is not permission to drop CE collision,
PVS/sound, or tag pointers from the current hybrid. Other PS2 submodule docs
were not found in this checkout; halo-64 has port notes but no `docs/` tree.

Acceptance consequences:

- A target-sized Step 7 query is not yet feasible on current owners for a
  campaign BSP; campaign admission remains closed. The host test is still
  valuable as a correctness gate for CE root/PVS behavior, but not capacity
  evidence.
- Before attempting a campaign PCSX2/EE query, Step 8 needs a complete
  lossless, pointer-valid topology that fits every map and accounts for CE
  claims, CE fixed state, the complete BSP/tag live set, object/AI/script/
  effect pools, renderer packs, texture/lightmap residency, stream/decode
  workspaces, map-switch overlap and alignment, with the reserve untouched.
- A d20 live-set/access-lifetime experiment can determine whether typed
  externalization or phase reuse is safe and sufficient; the already-reported
  animation-data candidate is only an instrumentation candidate, because its
  direct pointer readers and concurrent frame lifetimes are not yet a cache
  contract. Halo-64's 16×4 KiB N64 animation cache is method-only and cannot
  supply PS2 cache size, timing, or eviction semantics
  ([`n64_anim.c:4-12,22-24,108-177`](../../submodules/halo-64/port/n64/src/n64_anim.c#L4)).
- The minimum evidence for closing this family is not “ELF boots” or “BSP
  query passed on a host.” Require one hash-frozen exact production image with
  target physical interval/canary and per-owner high-water proof, direct
  production package/media reads, CE globals and pointer lifetimes valid
  across load/query/unload/retry, source-derived query goldens, and a
  capacity-qualified gameplay-map run in both PCSX2 modes; real hardware
  timing/storage qualification remains separately required by product scope.

REA remains **not applicable** to either review as currently scoped: the root
refresh behavior is available in CE source, while the capacity conclusion is
computed from source/schema-derived map artifacts and explicit owner contracts.
Use REA if a specific opaque retail executable result or unexplained shipped
binary mismatch later needs analysis, not as a substitute for live-set or
physical-memory evidence.

### Follow-up state

This addendum supersedes the earlier suggestion that the root-refresh fixture
was merely a future slice; the implementation now exercises that branch for
valid, seeded root locations. It does **not** supersede the explicit fallback,
movement/collision, Step 8, target-capacity, portal/frustum, or render limits
above. Continue appending a new dated section to this same report when the
main task reaches another concrete part of the plan.
