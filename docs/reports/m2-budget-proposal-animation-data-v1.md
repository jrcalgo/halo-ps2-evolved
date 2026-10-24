# M2 budget proposal v1 — retain in-image animation data

**Decision:** retain the current tag-image layout and budget. Do not externalize
`animation.data`, resize any EE region, spend the reserve, or claim map-fit from
the existing projections. This is a versioned no-change proposal for the M2
animation-data branch; it does not approve a new runtime format or close the
overall M2 capacity gate.

## Review record

Reviewed and accepted by the M2 integration owner (Codex implementation agent)
on 2026-10-21 as a decision-only, no-change disposition. The review checked the
source-backed consumer/feasibility report, its pinned schema/range evidence,
and the current [`memory-budget.json`](../../config/memory-budget.json)
(SHA-256 `67ef6d6085de71c22e3998a355cb2f79a8123837b7b14e89593a0d497de21b74`).
The accepted scope is limited to preserving the current in-image CE data
contract, all configured regions and the reserve, and all retail map targets;
it does not approve externalization, capacity claims, or a budget change. This
is an implementation-owner decision record, not a user sign-off or independent
technical review. The independent report-only gate audit is
[`m2-step4-animation-data-decision-audit-2026-10-21.md`](m2-step4-animation-data-decision-audit-2026-10-21.md),
which confirms this disposition satisfies the plan's decision-record fallback.

The feasibility report is pinned to the HCU baseline commit listed there. At
decision review time, three HCU working files also carried opt-in animation
trace instrumentation; their exact SHA-256 identities were
`e4ee659ab348529cc51cb3aea0177cfdb903a6a84e1bb58f3e43d9ae5592851f`
(`source/models/model_animations.c`),
`1d9df3bcc9aa0fb8f3db101a2185c4e95becacd9273717a01e1343d59b281ee8`
(`source/models/model_animation_definitions.c`), and
`a3e8b5fa2e1b5fd27f17c9f0655b37145c6a076e1585ee8f6f330e4156e4aa79`
(`port/linux/game/tag_schema_models.c`). The current audit confirms those
changes are conditional observer instrumentation/base-pointer factoring only;
they do not add an external provider, change schema ownership, remove raw-pointer
consumers, or alter this no-change decision. See
[`m2-step4-animation-data-decision-current-audit-2026-10-21.md`](m2-step4-animation-data-decision-current-audit-2026-10-21.md)
for the exact source review and caveat.

## Current accounting boundary

The 32 MiB EE memory map reserves 5,767,168 bytes and assigns 6,815,744 bytes
to `resident_gameplay`, 6,291,456 bytes to `current_bsp`, 1,572,864 bytes to
`streaming`, and fixed capacities to the other regions. These figures come
from [`config/memory-budget.json`](../../config/memory-budget.json) and the
memory-accounting rules in [`docs/memory.md`](../memory.md). This proposal
keeps every region byte-for-byte unchanged.

The current animation-range report measures 12,590 `animation.data` records
over the 24 stock maps, 60,788,194 total payload bytes across maps, a maximum
single record of 167,560 bytes, and a maximum per-map payload sum of 4,971,464
bytes (`c10`). Those totals are alternatives across maps, not simultaneous
resident requirements. The report is tied to schema ELF SHA-256
`2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`; see
[`m2-animation-data-contract-feasibility.md`](m2-animation-data-contract-feasibility.md)
and [`retail-animation-ranges-2fba411b.json`](retail-animation-ranges-2fba411b.json).

## Proposed disposition

| Item | v1 disposition |
|---|---|
| Schema meaning | Keep `animation.data` as in-image `TAG_SCHEMA_DATA`; preserve `frame_info` and `default_data` as separate fields. |
| Resident ownership | Keep tag bytes in the map’s existing resident tag-image owner. Do not count them a second time in `streaming`. |
| Cache/staging | Allocate no animation-specific streaming cache. Current evidence gives neither stable animation-record IDs nor maximum concurrent pinned frames. |
| EE region changes | None proposed. Do not transfer bytes between `resident_gameplay`, `current_bsp`, `streaming`, or `frame_scratch` using report-only projections. |
| Reserve | Keep all 5,767,168 bytes unspent. |
| Map support | Preserve all retail maps as product targets; no map is excluded to force a fit. Capacity qualification remains open until exact simultaneous resident bytes and load-overlap peaks are measured. |
| Externalization | Deferred. Reconsider only after a typed identity/lifetime contract covers every direct pointer consumer and passes decode, lease, failure, I/O, and EE tick-budget evidence. |

The no-change choice is evidence-driven. CE consumers keep raw pointers beyond
individual accessor calls, and aiming-screen interpolation can retain four
frame pointers concurrently. Compressed animation helpers also call
`tag_data_get_pointer` directly. The retail range extractor records source
extents and payload sizes but does not report active animation sets, concurrent
leases, cold/warm I/O latency, or worst tick stalls. A 167,560-byte maximum
record is therefore not a justified cache size, and the 1.5 MiB streaming arena
does not hold the largest map's full animation payload.

## Acceptance consequences

1. M2 step 4 has a selected design disposition and is not an implementation of
   external animation data.
2. M2 capacity remains unresolved. The all-map working-set report's projected
   fit under hypothetical externalization is not a measured placement result.
3. No change to `config/memory-budget.json` is authorized by this proposal.
4. A future proposal that changes region sizes must include the complete
   source-backed allocation ledger, per-map and load-transition high-water,
   physical ELF/arena placement, and unchanged-reserve proof before code adopts
   it.

## Reconsideration gates

Reopen this proposal only when the animation audit emits deterministic IDs
`(map hash, tag identity, graph element, field)`; all consumers can use a
behavior-equivalent bounded lease provider; schema validation sees the same
logical bytes; the 1–4 player/campaign working set and four-pointer
interpolation case are measured; and EE/PCSX2 evidence includes cache high-water,
DVD/OPL read/seek cost, worst blocked tick, unload/reload, corruption, and
rollback behavior. Until then, the in-image CE contract is the reference.
