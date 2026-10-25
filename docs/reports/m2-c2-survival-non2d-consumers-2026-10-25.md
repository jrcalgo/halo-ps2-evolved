# M2 C2 survival non-2D consumer audit, re-run 2026-10-25

## Why re-run
The closure ELF `build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf` was relinked on 2026-10-24.
Old schema ELF sha256 `56cd9fb82c4729b6870972c8d8be36fab78916ff1fa2026c5e22bf7cfe263037`.
Current `b1d3c7b0af253988aab8fc60a7a7618bb03435111784ddf784dd50f5d39280c5`.

## Procedure (no bootstrap flag needed)
1. Diagnostic, same flags as the 2026-10-24 residual-package lane:
   `python3 -I tools/hcu_multiplayer_profiles.py --profile survival-beavercreek --report-failures --verify-rebuild --output build/c3/c3-6e/audit/survival-diag-2026-10-25-vr`
   The producer does not read the non-2D report before writing the diagnostic. The stale-pin check raises inside the media-stage handler, which is recorded as `failure_stage: media`. Exit code 1 is expected (diagnostic only). Verify-rebuild passed.
   Result: `schema_elf_sha256` = current ELF; `unadmitted_ctag_sha256` `ec71d99d...`; 10,700 tags; `failure.json` sha256 `153f6a99...`.
2. Audit:
   `python3 -I tools/audit_hcu_profile_non2d.py --profile survival --diagnostic build/c3/c3-6e/audit/survival-diag-2026-10-25-vr/survival-beavercreek.failure.json --ctag build/c3/c3-6e/audit/survival-diag-2026-10-25-vr/survival-beavercreek.unadmitted.ctag --output docs/reports/m2-c2-survival-non2d-consumers-2026-10-25.json`

Result: status `partial`, `runtime_admitted` false, 39 roles, 186 non-2D occurrences, no `unknown_fail_closed`. The 2026-10-24 residual-package regeneration gave the same 39 roles and 186 occurrences.

## Diff vs m2-c2-survival-non2d-consumers-2026-10-23.json
- Tags: 18,579 -> 10,700. The current producer's diagnostic covers fewer tags. This is a scope change to flag, not a classification change.
- Roles: 36 -> 39. 36 common roles, plus 2 new, both `role_gated_no_current_ps2_payload_consumer`:
  - `levels\a30\bitmaps\reflection noise1` (cube, index 0)
  - `levels\b30\bitmaps\cubemap beach` (cube, index 0)
- Top-level classification: unchanged for all 36 common roles.
- Owner-level feature-gate sets changed for 2 common roles (same top-level class):
  - `vehicles\warthog\bitmaps\reflection diffuse metal` (cube, index 0)
  - `levels\b30\bitmaps\cube map forerunner interiors` (cube, index 0)
  The owner set now includes `ps2_environment_reflection_consumer_absent` or `ps2_glass_reflection_consumer_absent` for these images, because the owner walk now reaches different schema fields.
- Pins: ELF, plan (`a3cd7e16...`), CTAG, diagnostic, `objtex.py` and `texconv.py` re-derived to current bytes.

## Explanation of the producer change (10-23 diagnostic -> 10-25 diagnostic)

The 10-23 diagnostic (`build/m2-c1-survival-dedup/survival-beavercreek.failure.json`, written 2026-10-23 10:22) predates three producer commits. None of them is in the diagnostic:
- `aafdf78` "Qualify C1 multiplayer asset profiles on the v3 corpus" (2026-10-23 21:34). It adds:
  - closure-signature identities with alias merging (`source_aliases`, `conflicts`), so equal (group, path, signature) tags from several source maps share one row;
  - `bsp_dependency` roots (57) and a `structure_bsp` root for the beavercreek structure BSP.
- `693fc49` "Import multiplayer profiles with pinned hashes" (2026-10-24 01:54). It adds `runtime_normalizations` (sound owner relocation, and `external_source_sample_metadata_only` for sound samples from maps other than the mounted scenario map), `runtime_layout_probe`, `source_inputs`, and `presentation_provenance`.

Measured on the two diagnostics (old = 10-23, new = 10-25 verify-rebuild):
- Tag rows 18,579 -> 10,700. Every one of the 18,579 old (group, path, source map) occurrences is covered by a new row or its `source_aliases` (0 missing). So this is deduplication, not loss.
- Unique (group, path) identities: 3,347 -> 3,400. The 53 extra are beavercreek bitmap and shader tags reached through the new `bsp_dependency` roots. No identity was lost.
- Sound (`snd!`): 1,482 -> 1,483 unique paths. Its row count fell from 9,081 to 1,483 because cross-map duplicate sounds are merged by signature.
- Roots 272 -> 330 (the 58 added roots are `bsp_dependency` and `structure_bsp`).
- Old `runtime_normalizations` absent; new carries 19,850 (13,804 sound owner relocations and 6,046 `external_source_sample_metadata_only` foreign-sample records). These normalize foreign sample extents to metadata; they do not drop tags.

Role changes:
- `levels\a30\bitmaps\reflection noise1` and `levels\b30\bitmaps\cubemap beach` are new roles. Each is itself a `bsp_dependency` bitmap root in the new producer, so they are new because of the BSP roots. Both are role-gated, not unknown.
- `vehicles\warthog\bitmaps\reflection diffuse metal` gains a third role row with `ps2_environment_reflection_consumer_absent`, from the `senv.reflection_cube_map` owner. Occurrences unchanged (11). Caused by the merged owner walk.
- `levels\b30\bitmaps\cube map forerunner interiors` has the same gate sets. Owner records rose 15 -> 18 with occurrences unchanged (10), from the merged identities.

Assessment: all three changes come from intended producer changes (dedup/aliasing, BSP roots, foreign-sample policy). Nothing a survival or multiplayer runtime needs was dropped as an identity. Top-level classifications are unchanged. The packager's gating depends on the classification and the `FIELD_RULES` pins, not on owner-record multiplicity. Repointing is therefore justified.

## Repoint
`tools/hcu_profile_package.py` NON2D_REPORT and SURVIVAL_NON2D_REPORT now name the 2026-10-25 reports. The survival tests read the regenerated diagnostic at `build/m2-c2-residual-packages/survival-diag-2026-10-25/` (copy of the verify-rebuild output, failure.json sha256 `153f6a99...`, CTAG sha256 `ec71d99d...`).
