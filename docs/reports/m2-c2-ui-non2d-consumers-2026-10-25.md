# M2 C2 UI non-2D consumer audit, re-run 2026-10-25

Re-run because the closure ELF `build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf` was relinked on 2026-10-24.
Old ELF sha256 `56cd9fb82c4729b6870972c8d8be36fab78916ff1fa2026c5e22bf7cfe263037`; current `b1d3c7b0af253988aab8fc60a7a7618bb03435111784ddf784dd50f5d39280c5`.

The UI audit (`tools/audit_hcu_profile_non2d.py --profile ui`) does not read the ELF. Its catalog still records the old schema ELF as provenance.

Diff against `m2-c2-ui-non2d-consumers-2026-10-23.json`:
- 9 rows, same paths, image indices and types. Every classification and owner-field result is unchanged. None is `unknown_fail_closed`.
- `catalog`, `scope` and `policy` are unchanged.
- One re-derived pin: `plans/7.hcu-remake-m2-m4.md` sha256 changed from `674ba2c9...` to `a3cd7e16...`. The plan file was edited after 2026-10-23.

The survival report (`m2-c2-survival-non2d-consumers-2026-10-25.json`) is NOT written. Its audit needs a survival diagnostic regenerated against the current ELF, and that regeneration is blocked by the packager's own pin check on the old survival report. The packager was not repointed.
