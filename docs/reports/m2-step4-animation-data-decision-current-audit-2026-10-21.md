# M2 Step 4 current decision-gate audit — 2026-10-21

## Verdict

**Step 4 is complete under its explicit decision-record fallback**, with a
strictly limited claim: the project has decided not to change animation-data
format or memory-region sizes at this time. This does not implement external
animation data, prove any map fits, close M2 capacity, or replace Step 3. No
corrective code or plan edit is needed. The minimum helpful follow-up is only
an optional source-identity addendum if future reviewers require every
decision-era working-tree edit to be pinned individually.

## Why the fallback is satisfied

Step 4 first asks for an external-data contract and its tests, then explicitly
permits stopping at a decision record when direct CE consumers cannot all use a
behavior-preserving bounded accessor ([`plans/7.hcu-remake-m2-m4.md:557-563`](../../plans/7.hcu-remake-m2-m4.md#L557)).
That is the selected branch. The source-backed feasibility report inventories
the three distinct `animation` payload fields and confirms that
`TAG_SCHEMA_DATA` is an in-image pointer/size claim, not an external-file
descriptor ([`m2-animation-data-contract-feasibility.md:7-17`](m2-animation-data-contract-feasibility.md#L7)).
It traces direct compressed-data readers, pointer lifetimes, schema validation,
and the four-frame-pointer case in aiming interpolation
([same report:19-36, 91-99](m2-animation-data-contract-feasibility.md#L19)).
It also explains why the range extractor does not supply stable external-record
identity, concurrent pin counts, or target I/O/tick costs
([same report:38-51, 93-99](m2-animation-data-contract-feasibility.md#L38)).

The v1 proposal is an unambiguous no-change disposition: preserve the existing
tag-image contract, all configured memory-region sizes and all map targets;
allocate no animation cache; do not use the reserve; defer externalization
([`m2-budget-proposal-animation-data-v1.md:1-7, 42-61`](m2-budget-proposal-animation-data-v1.md#L1)).
It does not pretend to be a budget increase proposal. Its acceptance
consequences keep capacity unresolved and state that no budget change is
authorized ([same report:63-82](m2-budget-proposal-animation-data-v1.md#L63)).
The current `config/memory-budget.json` SHA-256 is exactly the reviewed
`67ef6d6085de71c22e3998a355cb2f79a8123837b7b14e89593a0d497de21b74`; its 32
MiB total, 5,767,168-byte reserve, 6,815,744-byte `resident_gameplay`,
6,291,456-byte `current_bsp`, and 1,572,864-byte `streaming` region agree with
the proposal ([`memory-budget.json:1-20`](../../config/memory-budget.json#L1)).
The proposal therefore neither transfers bytes between regions nor spends
reserve in contradiction to the current budget.

The source reason remains material to this decision: the schema's animation
validator claims and validates in-image bytes ([`tag_schema_models.c:941-968`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_models.c#L941));
the accessor returns a raw pointer from `tag_data_get_pointer()`
([`model_animation_definitions.c:504-540`](../../submodules/halo-ce-universal/source/models/model_animation_definitions.c#L504));
compressed rotation/translation/scale helpers continue to read directly from
`animation->data` ([`model_animations.c:2196-2200`](../../submodules/halo-ce-universal/source/models/model_animations.c#L2196),
[`model_animations.c:2326-2345`](../../submodules/halo-ce-universal/source/models/model_animations.c#L2326),
[`model_animations.c:2470-2489`](../../submodules/halo-ce-universal/source/models/model_animations.c#L2470));
and aiming interpolation keeps four frame pointers at once
([`model_animations.c:1776-1805`](../../submodules/halo-ce-universal/source/models/model_animations.c#L1776)).
This is sufficient source evidence to decline a bounded external contract
without inventing a cache cap from the 1.5 MiB streaming region.

## Approval, provenance, and one caveat

The proposal now records implementation-owner acceptance dated 2026-10-21,
its scope, the exact current memory-budget hash, and an explicit statement that
this is neither user sign-off nor independent technical approval
([`m2-budget-proposal-animation-data-v1.md:9-22`](m2-budget-proposal-animation-data-v1.md#L9)).
The existing independent report-only gate audit verifies that addition and
recommends keeping Step 4 complete only as a design disposition
([`m2-step4-animation-data-decision-audit-2026-10-21.md:13-28`](m2-step4-animation-data-decision-audit-2026-10-21.md#L13)).
Thus the earlier reviewer-provenance caveat is resolved.

One reproducibility caveat is narrower than a gate failure: the feasibility
report pins the HCU baseline commit, while the current HCU worktree has
diagnostic animation-trace edits. Current working-file SHA-256 values are
`e4ee659ab348529cc51cb3aea0177cfdb903a6a84e1bb58f3e43d9ae5592851f` for
`source/models/model_animations.c`,
`1d9df3bcc9aa0fb8f3db101a2185c4e95becacd9273717a01e1343d59b281ee8` for
`source/models/model_animation_definitions.c`, and
`a3e8b5fa2e1b5fd27f17c9f0655b37145c6a076e1585ee8f6f330e4156e4aa79` for
`port/linux/game/tag_schema_models.c`. The inspected diffs add observer calls
under `HALO_PS2 && HALO_PS2_M2_ANIMATION_TRACE`; the ordinary accessor's
base-pointer factoring preserves its same `tag_data_get_pointer` behavior.
These edits do not introduce an external provider, change `TAG_SCHEMA_DATA`,
remove the raw-pointer consumers, or change the budget. The baseline evidence
therefore remains adequate for the selected conservative disposition. If
reproducibility policy wants a fully exact worktree pin, append those three
hashes and classify them as diagnostic instrumentation; no additional runtime
test is necessary for this decision-only gate.

## Required disposition

Keep the plan status **done — decision record only**. Do not require the
external-reference overflow/short-read/pinning tests: those apply only if the
project selects externalization, which it has explicitly deferred. Do retain
all non-claims: no externalization implementation, no new budget allocation,
no map admission, no capacity proof, and no overall M2 exit. Step 3 and the
remaining capacity/target-load gates stay independent and open.

Verification for this audit was read-only: current proposal/audit/source and
budget hashes were checked; the budget hash matched the review record. No code
or plan files were changed, and no runtime test was run because this is a
decision-provenance audit rather than an implementation change.
