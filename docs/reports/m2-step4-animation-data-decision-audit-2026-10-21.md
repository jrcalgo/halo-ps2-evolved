# M2 Step 4 decision-record audit — 2026-10-21

## Verdict

Step 4 is legitimately complete as a design-disposition gate, not as an animation-data implementation or capacity gate. The plan explicitly allows stopping at a decision record when a behavior-preserving external-data accessor cannot cover all direct CE consumers; the selected no-change disposition preserves the current tag-image contract and does not claim map fit ([`plans/7.hcu-remake-m2-m4.md:557-563`](../../plans/7.hcu-remake-m2-m4.md#L557)). This does not close Step 3, overall M2, or authorize a format/budget change.

## Evidence against the gate

- The feasibility report is source-backed and bounded to identified inputs: parent/HCU/halo-ps2 pins and the schema ELF plus range-report hashes are recorded at [`m2-animation-data-contract-feasibility.md:1-5`](m2-animation-data-contract-feasibility.md#L1). It traces the schema’s `TAG_SCHEMA_DATA` fields and validation, raw pointer lifetime, the direct compressed-path `tag_data_get_pointer` calls, and consumers retaining multiple pointers ([same report:11-17, 19-36](m2-animation-data-contract-feasibility.md#L11)). It explains why no stable record identity, lease lifetime, cache capacity, or target access budget can safely be inferred, then explicitly recommends preserving in-image data ([same report:91-105](m2-animation-data-contract-feasibility.md#L91)).
- The proposal makes a concrete, versioned choice rather than leaving alternatives open: preserve `TAG_SCHEMA_DATA`, allocate no animation cache, change no EE region, spend none of the 5,767,168-byte reserve, retain all retail maps as targets, and defer externalization ([`m2-budget-proposal-animation-data-v1.md:1-7, 27-46`](m2-budget-proposal-animation-data-v1.md#L1)). The stated consequences explicitly keep capacity unresolved and prohibit treating projections as placement proof ([same report:48-68](m2-budget-proposal-animation-data-v1.md#L48)). The region values match `config/memory-budget.json:4-20`.
- The plan’s Step 4 entry records the decision date and disposition and carefully limits its claim ([`plans/7.hcu-remake-m2-m4.md:563`](../../plans/7.hcu-remake-m2-m4.md#L563)). This matches Step 4’s fallback clause; typed-reference tests for overflow, short reads, corrupt checksums, unload-while-pinned, and repeated decode are not missing acceptance work because those are required only if selecting externalization ([same plan:559-561](../../plans/7.hcu-remake-m2-m4.md#L559)).

## Review/approval record

The prior audit flagged that the proposal did not name its reviewer. This is
resolved by the dated owner-review record now in
[`m2-budget-proposal-animation-data-v1.md`](m2-budget-proposal-animation-data-v1.md#L3):
the M2 integration owner (Codex implementation agent) accepted the bounded
no-change disposition on 2026-10-21 after checking the feasibility report,
pinned schema/range evidence, and current memory-budget identity. This records
implementation-owner acceptance only; it is not user sign-off or a claim of
independent technical approval. The separate report-only audit remains the
independent corroboration. No code, runtime test, external-data lease contract,
or budget modification is required by this decision-only gate.

## Recommendation

Keep Step 4 marked complete with its existing “design disposition only; capacity exit still open” qualification. Clarify the approval provenance only if the project requires a named independent reviewer. Do not weaken the decision’s explicit non-claims: no externalization implementation, no all-map fit proof, and no M2 capacity closure.
