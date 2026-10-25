# M2 C2 UI non-2D consumer audit, re-run 2026-10-25 (r2)

Second re-run of `tools/audit_hcu_profile_non2d.py --profile ui`. The first 2026-10-25 run is kept as history.

Why: the packager's pin check failed on `plans/7.hcu-remake-m2-m4.md`, which changed in commit 24092d4. The UI audit does not read the ELF.

Diff against `m2-c2-ui-non2d-consumers-2026-10-25.json`:
- Rows, roles, classifications, catalog, scope and policy are unchanged (9 rows, none `unknown_fail_closed`).
- One re-derived pin: `plans/7.hcu-remake-m2-m4.md` now has the sha256 of the 24092d4 text.
