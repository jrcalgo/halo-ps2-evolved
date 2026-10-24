# M0 root refresh and next source-review batch

Date: 2026-10-21. Report-only audit. No ledger, source, or plan approval was
changed.

## Decision

M0 must remain open. The current machine-readable ledger is not bound to the
latest production-profile rooted object, and neither saved closure is a
fully-current, macro-free production closure:

* `docs/hcu-source-backed-review/hcu-ps2-external-review.json` has SHA-256
  `167541c881937a5da21a75cd2164296d91d1b6f0ff07ed1f2089a700248f8a2f` and
  names rooted object `f1a169d679ee354044390083945b9e74319ca0b833b01da25ff904f3ea1f5e3a`.
  Its 322 rows comprise 59 `pending` dispositions (31 toolchain, 14 excluded
  feature, 13 render, and 1 PS2 service); all 59 are still gate blockers, not
  implied approvals from their source notes.
* The saved ordinary production profile is
  `build/hcu-ps2-closure/all-no-bootstrap-memory/`, with
  `HALO_PS2_NO_BOOTSTRAP_MEMORY`, 370 compiled units, 0 failures, 322 live
  externals, and `gate: open`. Its `result.json` SHA-256 is
  `b51921421aae536b4cabe7950c51ef9838443f7f09f91952a341790d256d9b3b`, and
  its `rooted.o` SHA-256 is
  `cdbc2a9638054143608a50d3d18576411186840990bc2842df8cdcf6e710eaf8`.
  It uses manifest SHA-256
  `a64018b2b0de1edf0660ad4e9019d2738216db2ae5352c8a8503899ff9d6f93d` and
  prefix SHA-256
  `8edce2ba3c42b406db6c73cdca3c6c68e318c9df390a16c1db0f54321c8074b2`,
  both of which match the current files. But comparing all 370 recorded unit
  source hashes against the current HCU checkout finds six mismatches:
  `source/game/game.c`, `source/interface/first_person_weapons.c`,
  `source/objects/objects.c`, `source/units/units.c`,
  `port/ps2/src/ps2_animation_trace.c`, and `port/ps2/src/ps2_render.c`.
  So this is a useful previous production root, not a current-source freeze.
* The most recently built all-current closure is
  `build/hcu-ps2-closure/all-no-bootstrap-memory-m2-animation-trace/`.
  Its `result.json` SHA-256 is
  `6c1d0422e117d1a66fe4e36c46b13944cbe93ec00aaaa49c6245745445995b96`, its
  `rooted.o` SHA-256 is
  `0d1b6caaf72b0aa5706958748faa8e6d0dd624375f777b98646429590a4e83ec`, and
  all 370 recorded source hashes match the checkout. It is not the accepted
  production profile because it defines
  `HALO_PS2_M2_ANIMATION_TRACE`; do not substitute its root for the
  macro-free profile when signing off M0.

The associated parent-link probe is also not a substitute for the new
production closure. `build/hcu-parent-link-probe/result.json` SHA-256 is
`7aeae8beebb2388e9e7c8fc31a544ac0375012374aca74983b4c114351c418c1`. It
records HCU root `cdbc2a9638054143608a50d3d18576411186840990bc2842df8cdcf6e710eaf8`
and a linked ELF SHA-256 of
`e5a088d524697c08936f5a53efde779d85e7fe6baf61d90c1b4f46dec7215099`, but
records closure-report SHA
`39c91941bba26208cb781738addeb67f6cea53c9c90fee7dc235ca33a5059e09`, which
does not equal the current on-disk no-bootstrap `result.json` hash above.
The probe explicitly says `acceptance: false`, does not exercise a CE tick,
map load, arena binding, or render snapshot, and is diagnostic only. Preserve
the ELF and probe as historical evidence; regenerate them as a single frozen
run after refreshing the macro-free closure.

## Review reports that cannot yet close rows

The current exclusion, render, and toolchain reviews all assert older rooted
SHA `f1a169d...` and their own then-current ledger hashes. For example:

* [`m0-current-excluded-pending-review-2026-10-21.md`](../hcu-source-backed-review/m0-current-excluded-pending-review-2026-10-21.md)
  has SHA-256 `0dcd429dd40ee73982aeb33ddd2e9587c00f30c771c9e81ec27bb818f4c97201`.
* [`m0-current-render-pending-review-2026-10-21.md`](../hcu-source-backed-review/m0-current-render-pending-review-2026-10-21.md)
  has SHA-256 `75082835bde5255657787f6dea7da9b2f348e4735b7e14b3e6b3b0bc29fcc0db`.
* [`m0-current-toolchain-pending-review-2026-10-21.md`](../hcu-source-backed-review/m0-current-toolchain-pending-review-2026-10-21.md)
  has SHA-256 `d18c2d57f5d05ce6d7ecc86300f8f6f7b02a3a25cc248983cbe09a29470e6bc5`.
* [`m0-pending-file-cache-getters-batch.md`](../hcu-source-backed-review/m0-pending-file-cache-getters-batch.md)
  has SHA-256 `a69181f5c4c6989a683cfa531c96c56c88417695ed98162af0b4f7e12f516b31`.

Their source traces remain useful leads. They cannot yet serve as current
ledger dispositions because they name root `f1a169d...`, while the saved
macro-free production root is `cdbc2a...`; the current ledger itself still
names `f1a169d...`. In particular, section-name equality does not prove that
the source/object/root is identical, and source-file hashes must be checked
for each row after the fresh build. The current ledger's 322-symbol count
matching the two root counts is not identity evidence.

This finding is independently consistent with the repository closure note:
[`docs/hcu-ps2-closure.md`](../hcu-ps2-closure.md) labels older 507/706 counts
historical and says successful linking is not semantic sign-off. Do not
combine those historic totals with the current 322-symbol set.

## Disjoint batch to advance after root refresh

Advance one-symbol batch `display_error_when_main_menu_loaded` as a PS2 local
session reachability review. It is the only current `ps2-service/pending`
row, disjoint from the currently pending toolchain, render, and excluded-
feature families. It is also a useful consistency probe because older reports
conflict:

* The current row in
  [`hcu-ps2-external-review.json`](../hcu-source-backed-review/hcu-ps2-external-review.json)
  has empty owner/reason/evidence/test fields.
* [`hcu-ps2-batch-2-review.md`](../hcu-source-backed-review/hcu-ps2-batch-2-review.md)
  previously called it `excluded-proven`, based on local connection setup and
  false network-game creators.
* [`hcu-ps2-ui-error-state-review.md`](../hcu-source-backed-review/hcu-ps2-ui-error-state-review.md)
  instead warns that it stores an error for a later menu transition and
  should remain pending until exact reachability/state ownership is resolved.

The exact source justifies a narrow test, not a blanket decision. CE
`source/main/main.c:3637-3658,3700-3703` calls the function only on failed
client/server frame paths; `source/interface/ui_widget.c:1970-1984` stores
the first queued error in `widget_globals.main_menu_deferred_error_code` and
logs on a second. The current PS2 source
`port/ps2/src/ps2_network_local.c:47-54,124-145` rejects creation of global
client/server objects and resets client-start state to local; CE
`source/main/main.c:2845-2880` initializes ordinary solo startup as
`_game_connection_local`. Yet the linked generated body is still empty in
`build/hcu-ps2-closure/all-no-bootstrap-memory/ps2_platform.c:159`, and the
only rooted section is `.text.main_loop` (closure entry names function
`main_loop`). These facts support local-profile unreachability only if the
accepted startup invariant and every connection transition are demonstrated.

Recommended advancement sequence after regenerating the authoritative
macro-free root and ledger:

1. Verify the exact rooted entry still has only `.text.main_loop`; refresh the
   caller/source hash for `source/main/main.c` and confirm the PS2 creator and
   frame-start implementations selected by the exact manifest.
2. Instrument a local startup/frame test to assert connection stays
   `_game_connection_local`, client/server frame routines cannot enter their
   network failure paths, and the error-queue stub is not reached during
   ordinary local menu/map/tick flow.
3. Separately force an unavailable network connection in a test harness. If
   that state is product-unreachable, assert it is rejected/reset before
   stock error-queue state is required. If such states are in scope, implement
   the queue state even without widget drawing and test its later menu
   consumption or explicit safe discard.
4. Reconcile batch-2's earlier `excluded-proven` claim with the UI-state
   report and this test before changing the ledger. Do not infer a valid
   no-op merely from the current generated empty body.

This batch can advance M0 review work but cannot close M0 by itself. The
ledger still has 58 other pending rows after it, and M0 also depends on
allocation-owner reconciliation in
[`m0-allocation-ownership.md`](../hcu-source-backed-review/m0-allocation-ownership.md).

## Reproducibility facts

At report time the parent repository HEAD was
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU HEAD was
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 HEAD was
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The HCU submodule is dirty;
these commit IDs alone do not identify the source tree used by the build.
The report's decision is therefore tied to the hashes above and should be
recomputed after the next source change or rebuild.
