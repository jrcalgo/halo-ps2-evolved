# M2 Step 7 failure-atomicity audit

Date: 2026-10-21  
Scope: report-only audit of CE/HCU CTAG and CBSP publication, scenario/BSP rollback, and arena ownership in the current M2 Step 7 fixtures. This is not a PS2 capacity, emulator, rendering, or retail-parity qualification.

## Finding

The major failure-atomicity paths named in Step 7 are already covered more thoroughly than the general plan status suggests. There are three complementary evidence layers:

1. The real CE initial map lifecycle fixture composes `scenario_load()`/`scenario_unload()` with the production parent map service and injects late CTAG visitor failure after bytes reach the destination, post-copy CE tag-validation rejection, and initial B000 late-write failure; it verifies CE publication is absent, the parent map owner/source and arenas are released, then exercises retry. The harness description and asserted stdout/manifest gates are in [`tests/test_hcu_ce_map_lifecycle.py:18-123`](../../tests/test_hcu_ce_map_lifecycle.py#L18) and its exact linked production/CE source closure is [`tests/test_hcu_ce_map_lifecycle.py:51-90`](../../tests/test_hcu_ce_map_lifecycle.py#L51).
2. The CE initial-lifecycle injected CTAG fault fails the same callback *after* its bytes have been copied into CE's destination, not before writing; the write witness and forced failure are explicit at [`tests/hcu_ce_map_lifecycle_main.c:153-185`](../../tests/hcu_ce_map_lifecycle_main.c#L153). The test then checks unpublished tag/scenario globals, no live mount/source, zero owner usage, closed descriptor, and retry at [`tests/hcu_ce_map_lifecycle_main.c:215-263`](../../tests/hcu_ce_map_lifecycle_main.c#L215). A separate post-copy CE tag validation fault confirms the candidate image was materialized before rejection and checks cleanup plus complete scenario retry at [`tests/hcu_ce_map_lifecycle_main.c:266-300`](../../tests/hcu_ce_map_lifecycle_main.c#L266).
3. The retail a30/a50 BSP-switch fixture exercises the production HP2 visitor, CTAG mount, PS2 cache adapter, and CE `scenario_switch_structure_bsp()` against real converted package/map inputs. It has snapshots for CE BSP globals/indexes, per-tag base pointers, full owner/scratch cursors, mount ownership, and cache bytes at [`tests/hcu_scenario_bsp_switch_main.c:319-356`](../../tests/hcu_scenario_bsp_switch_main.c#L319). It verifies failed CBSP outer CRC, inner CRC, and relocation rebase restore the previous B000 publication and bytes then allow same-process retry ([`tests/hcu_scenario_bsp_switch_main.c:1442-1480`](../../tests/hcu_scenario_bsp_switch_main.c#L1442)); ordinary candidate read, CE capacity verifier, and CE BSP schema failures rematerialize B000 ([`tests/hcu_scenario_bsp_switch_main.c:1512-1560`](../../tests/hcu_scenario_bsp_switch_main.c#L1512)); failure of both candidate and old BSP leaves safe-null CE state and menu handoff, with parent scratch unwound ([`tests/hcu_scenario_bsp_switch_main.c:1562-1582`](../../tests/hcu_scenario_bsp_switch_main.c#L1562)).

The production ownership code has explicit transaction marks and rollback: `ctag_mount` marks and releases candidate BSP scratch on load/validation/backend failure ([`src/stream/ctag_mount.c:68-105`](../../src/stream/ctag_mount.c#L68)); HCU's preflight releases its temporary map-arena span on all validation outcomes ([`src/stream/hcu_map_service.c:405-510`](../../src/stream/hcu_map_service.c#L405)); and CE's switch unloads the prior BSP before loading a candidate, retries the old reference on failure, or clears globals/menu-falls-back when restoration fails ([`scenario.c:1101-1204`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1101)). CE scenario unload clears pointers before releasing the parent map owner ([`scenario.c:390-425`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L390)); tag validation is performed before CE publishes `tag_header`, `global_tag_instances`, and `tags_loaded` ([`cache_files.c:1288-1314`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1288)).

## Boundary matrix

| Boundary | Current evidence | Assessment |
|---|---|---|
| CTAG malformed relocation / streamed validator failure | Step 9 lifecycle fault mutates a final relocation target while retaining active mount, confirms pre-copy rejection leaves the poisoned destination and tag globals unpublished, then repairs/retries on same mount (plan evidence at `plans/7.hcu-remake-m2-m4.md:677`). | Covered for validator rejection before materialization; distinct from late visitor partial write. |
| CTAG stream/visitor fails after destination write | Real CE `scenario_load()` lifecycle hook writes then fails; checks no published tags/scenario and parent owner teardown/retry. | Covered at initial scenario-load boundary. The UI test's entire payload may be delivered in one decoded chunk, but it proves partial-destination visibility and failure ordering, not a multi-chunk prefix-length matrix. |
| CE `tag_validate_tags()` rejects materialized CTAG | Actual validator runs successfully, test wrapper rejects once immediately before CE cache globals publication; full cleanup and retry verified. | Covered at initial load boundary. |
| Initial B000 CBSP visitor late-write failure | Real CE initial scenario-load path has B000 fault injection and rollback/retry (runner asserts marker). | Covered, though the exact whole-owner digest/highwater checks are weaker than the reusable lifecycle snapshot machinery in other cases. |
| Candidate CBSP outer CRC, image CRC, relocation/rebase | Real retail package transaction direct visitor path; prior published B000 snapshot and same-process retry asserted. | Covered for converted a50 package with test-only capacity bypass; not target sizing. |
| Candidate CE schema rejection / port verifier rejection | Real CBSP materializes, CE schema or fixture's capacity-verifier seam rejects, CE reloads the old BSP. | Covered as failure/rollback composition; injected verifier is not itself an independent measurement of hardware capacity. |
| Candidate read failure and rollback-read failure | Retail transaction tests candidate failure restoring old BSP, and both reads failing to safe-null/menu. | Covered. |
| Parent owner/mount/arena cleanup across successful unload and initial load rejection | Lifecycle fixture counts owner releases and asserts owner/scratch zero, mount/source closed; snapshot is also verified for transaction failures. | Substantively covered on host ILP32. |
| Preflight invalid package while old map is active | Lifecycle diagnostic asserts rejected gameplay preflight preserves active UI snapshot (exact marker in `tests/test_hcu_ce_map_lifecycle.py:124-130`). | Covered at the synthetic/host lifecycle seam; source/reason matrix is outside Step 7 and belongs to the loader/preflight steps. |
| Runtime CE BSP publication on collision/query failure | The collision wrapper query asserts output and non-mutation after success; the CE switch transaction checks state on load/schema failure. | No explicit fault injection into the query consumers themselves, but these are read-only consumers and such a test would not materially add publication rollback coverage. |

## Narrowest meaningful remaining fixture

The current blocker is not a missing generic “arena rollback” test. That behavior is exercised at several owners and layers. The one valuable failure-mode hole within this concern is **actual bounded arena exhaustion at the transaction seam**, rather than another format/CRC rejection:

- In `ctag_mount.load_bsp_extent()`, a failed `load_section()` or `mount_bsp()` must leave the candidate scratch cursor at its pre-call mark and leave `bsp_active` false ([`ctag_mount.c:88-105`](../../src/stream/ctag_mount.c#L88)). The existing retail direct-visitor transaction bypasses the materialized-section loader; thus it does not exercise the real `load_bsp_extent()` branch under scratch exhaustion.
- In `hcu_map_service_preflight()`, `load_section()` failures for HMAP/CRNG/CBIX, CTAG relocation-scratch allocation failure, or source-hash scratch exhaustion should release the preflight mark and leave no staged request/source leak; current lifecycle evidence has source/visitor/validation faults, but no explicit `arena_alloc()` failure at these exact production callsites (`preflight_ctag_stream()` uses an owner allocation for relocation metadata at [`hcu_map_service.c:122-187`](../../src/stream/hcu_map_service.c#L122), and the enclosing rollback mark is at [`hcu_map_service.c:405-510`](../../src/stream/hcu_map_service.c#L405)).

Recommended single fixture: add a test-only, one-shot allocator failure seam scoped to a `hcu_map_service` preflight of the already hash-bound UI fixture. First allow HMAP/CRNG/CBIX loads, then fail the relocation-vector allocation in `feed_ctag_first_pass()` after at least one temporary preflight section was allocated. Assert (a) preflight returns false, (b) `map_arena.used` and `section_scratch.used` equal their captured entry marks, (c) `source.active` is false and descriptor closed, (d) `mount.active` is false, (e) `preflight_ready`, `staged_entry`, `staged_map`, and `ctag_info` are cleared, and (f) the next no-fault preflight and complete `scenario_load()` succeed without process restart. This directly proves the production preflight cleanup contract for a resource-exhaustion failure and same-process recovery without repeating schema walker edge cases from Step 6 or the existing CRC/visitor/CE rollback suite.

If adding an allocator seam is judged too invasive, the closest low-intrusion alternative is to initialize the lifecycle fixture's *preflight owner arena* with capacity that admits HMAP/CRNG/CBIX but cannot satisfy the bounded CTAG relocation allocation, then retry with the normal arena. The test must calculate and assert the intended threshold from actual allocation sizes and not describe this host-sized fault as PS2 capacity evidence.

This proposed fixture closes only the “allocator/owner exhaustion unwinds transaction state” subcheck. It does not close Step 7 as a whole: independent collision hit/miss golden behavior, remaining relevant CE consumers, map capacity, target runtime, and render acceptance are separate gates.

## Existing commands to reproduce evidence

The map lifecycle harness compiles a native ILP32 link using real CE scenario/cache/tag code plus parent HCU map service. Its Python runner skips only if the package/source assets or compiler are unavailable, and the binary can be blocked by the sandbox with SIGSYS. Use the approved native ILP32 execution environment when the sandbox reports that skip:

```sh
PYTHONPATH=. HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q -rs tests/test_hcu_ce_map_lifecycle.py -x
```

Retail BSP transaction (a30/a50) plus schema/collision/query checks:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

These are historical reproduction instructions, not a claim that they were rerun during this report-only audit. Current artifact hashes, package hashes, and pins must be collected from the new run before updating acceptance records. The detailed Step 7 suite status remains in [`plans/7.hcu-remake-m2-m4.md:597-601`](../../plans/7.hcu-remake-m2-m4.md#L597).

## Halo-64 and REA applicability

Halo-64's [`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33) is relevant only as a reminder that graphics-side drawing stubs must not erase stateful simulation/frame/camera behavior. It provides no authority for HCU's CTAG/CBSP failure semantics, no PS2 memory/capacity evidence, and no rollback oracle.

REA is not applicable here. This audit inspects current CE/HCU source, tests, and raw converted retail data; there is no failing shipped executable whose hidden behavior needs binary reconstruction. The relevant oracle is source plus package bytes and test assertions.

## Conclusion

Record Step 7's failure atomicity as **substantially implemented on host ILP32**, not as a wholly open category. The optional allocator-exhaustion injection above is the narrowest new fixture with meaningful marginal coverage. Do not let that fixture imply capacity, and do not mark Step 7 complete while its independent collision oracle, consumer disposition, and target/capacity dependencies remain open.
