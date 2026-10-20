# M0 rooted collision-debug symbol review

Twenty-two rooted symbols in the `collision_debug*` family are resolved as
`excluded-proven` for the PS2 product profile. This is a narrow diagnostic
exclusion, not a collision-engine omission.

The CE `source/physics/collision_debug.c` module consumes the debug globals,
constructs optional debug collision flags, performs probe/spray diagnostics,
and submits debug geometry. It is compiled by the broad source audit but is
not a selected input to the rooted PS2 link; the live exported data symbols
resolve through the generated platform object instead. Its globals are exposed by `source/hs/hs_globals_external.c` for
HaloScript/debug tooling, but no normal collision response call in the selected
source consumes them. `collision_debug_point`, `collision_debug_vector`, and
`collision_debug_repeat` have one additional live producer in
`source/units/bipeds.c`: inside `if (debug_biped_physics && owner_player_index
!= NONE)`, CE stores the current position/velocity and dimensions so the
diagnostic renderer can show the biped pill. The values are written after
`collision_move_pill` has returned and do not feed its collision count,
clipped position, clipped velocity, or support-surface result.

The PS2 link retains the normal pill/collision implementation; it omits only
the optional debug visualization/test module. No PS2 gameplay call should set
collision-debug flags to modify collision-test behavior because that code path
is not compiled. If a PS2 collision debugger is later added, these rows must be
reopened and the diagnostic flags must not leak into normal gameplay semantics.

The ledger entries are source-backed diagnostic exclusions with explicit
owners, not zero-return service approvals. Regression anchor:
`tests/test_hcu_external_review.py::test_collision_debug_symbols_are_diagnostic_only_and_unlinked` verifies all 22 rows, the source module's omission from the rooted link, the biped's post-result diagnostic-only writes, and the source producer/consumer boundary.
