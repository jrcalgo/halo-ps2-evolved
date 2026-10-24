# Investigator prompt contract

Repository: `/home/ai/Documents/GitHub/haloce-decomp-ps2`

## Rules

- **Report-only.** Create or update only your assigned file under `docs/investigations/`.
- Do **not** edit shared implementation: `tools/hcu_ps2_*.py`, HCU `port/ps2` production sources, parent `src/game` gameplay, `port.json`, or submodule pins.
- Cite evidence as `path:line` or symbol names. Mark unknowns explicitly.
- Do not invent pool sizes or close M0–M3 gates from estimates.
- Retail map bytes stay out of tracked source; use aggregate reports in `docs/reports/` only.

## Evidence baseline (Round 1)

- Parent HEAD: `a2575e957feefbdff27febedabf60590401e6bcc`
- HCU HEAD: `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`
- `halo-local.elf` SHA-256 (if present): `e45b4719d35450a77f2a541a7ed8abb877e5fbef495fc918539f8da91de597a2`

## Report template

```markdown
# <investigator_id>

## Mission

## Inputs examined

## Findings

## Interface contracts for the main agent

## Recommended tests / fixtures

## Dependencies on other investigators

## Open questions

## Handoff summary
```

Round 2 appends `## Corroboration` with Agreements, Conflicts, Updated handoff.

## Seed documents

- [plans/5.hcu-remake.md](../../plans/5.hcu-remake.md)
- [plans/remake-cowork.md](../../plans/remake-cowork.md)
- [docs/hcu-ps2-closure.md](../hcu-ps2-closure.md)
- [docs/hcu-ps2-platform-placeholder-audit.md](../hcu-ps2-platform-placeholder-audit.md)
- [docs/hcu-tag-loader-contract.md](../hcu-tag-loader-contract.md)
- [docs/hcu-local-coop-audit.md](../hcu-local-coop-audit.md)
- [docs/source-audit.md](../source-audit.md)
- [docs/reports/tag-index.md](../reports/tag-index.md)
- [docs/reports/tag-payload-inventory.md](../reports/tag-payload-inventory.md)
- [config/memory-budget.json](../../config/memory-budget.json)
