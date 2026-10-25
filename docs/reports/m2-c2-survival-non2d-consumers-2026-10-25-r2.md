# M2 C2 survival non-2D consumer audit, re-run 2026-10-25 (r2)

Second re-run, from the same procedure as the 2026-10-25 report (commit 7479eda). The first 2026-10-25 report is kept as history.

## Why
The packager's pin check failed on `plans/7.hcu-remake-m2-m4.md` (changed in commit 24092d4). The new diagnostic was produced after that change.

## Procedure
1. Diagnostic: `python3 -I tools/hcu_multiplayer_profiles.py --profile survival-beavercreek --report-failures --verify-rebuild --output build/c3/c3-fplod/audit/survival-diag-2026-10-25-r2`. Exit 1 is expected (diagnostic only). Its `failure_stage` is `media`, with the stale-pin error.
2. Audit: `python3 -I tools/audit_hcu_profile_non2d.py --profile survival --diagnostic <dir>/survival-beavercreek.failure.json --ctag <dir>/survival-beavercreek.unadmitted.ctag --schema-elf build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf --output docs/reports/m2-c2-survival-non2d-consumers-2026-10-25-r2.json`

## Diff against the 2026-10-25 report
- Rows, roles, role counts, classifications and policy are unchanged (39 roles).
- Pins: the plan hash is the 24092d4 text. The diagnostic paths now point at the r2 directory.
- `diagnostic_error` quotes the stale-pin error for `plans/7.hcu-remake-m2-m4.md`. It is not a classification.
