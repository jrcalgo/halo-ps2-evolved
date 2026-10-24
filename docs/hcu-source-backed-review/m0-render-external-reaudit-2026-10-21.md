# Addendum: render-external report revalidated against the refreshed production root

Date: 2026-10-21

This addendum revalidates [the 23-row render external audit](m0-render-external-audit-2026-10-21.md) against the newer macro-free production closure. It is report-only: no ledger, source, plan, or build artifact was changed.

## Refreshed evidence

- `build/hcu-ps2-closure/all-no-bootstrap-memory/rooted.o`: SHA-256 `30b2a4a34c493441869f3e8128ba00405c64d8326c3047d6f505e355bea9f88a`.
- `build/hcu-ps2-closure/all-no-bootstrap-memory/result.json`: SHA-256 `58920f92393c15ce177b60dc608cf602b697f1fc0e2f85f34304b1f0b1082c78`.
- The refreshed ledger `docs/hcu-source-backed-review/hcu-ps2-external-review.json` now records the new rooted-object hash. It still contains 23 pending render-class rows.
- The selected HCU HEAD remains `6933490b2d16bb1c637295b6a0f3880ba23a7d56` (with local modifications).

## Comparison result

All 23 symbols in the previous report remain members of the fresh `rooted_link.live_externals` set. Their exact `caller_sections` match between the fresh closure result and refreshed ledger: **23/23 match, zero missing symbols, zero caller-section deltas**. Each ledger `caller_sources` SHA-256 was recomputed against the current HCU files: **no caller-source hash mismatch**. Thus the prior semantic findings and the fatal-only-vs-ordinary-presentation distinction carry forward unchanged for those 23 unresolved symbols.

Specifically, the following classifications remain supported by the current call graph:

- The ten `rasterizer_*` fatal-screen calls remain rooted only from `.text.halt_and_catch_fire`.
- `render_frame_present` remains rooted from `.text.main_present_frame` and `.text.screenshot_render.constprop.0`; it is still the separate ordinary frame/screenshot handoff and remains pending.
- `main_screen_shell_begin_fade` remains rooted from `.text.main_change_map_name`.
- `first_person_legs_reset`, the two HUD map lifecycle hooks, the seven debug helpers, and `ui_widgets_safe_to_load` retain the same caller sections listed in the prior report.

No recommendation in the previous 23-row table is promoted to an approved ledger disposition by this refresh. In particular, keep menu fade/audio state, ordinary parent-present ownership, fatal UX policy, and the widget lifecycle distinction as reported.

## Difference: HUD bitmap fallback is now implemented

The prior audit identified a concrete adjacent risk: generated `hud_hires_sprite_bitmap` returned `NULL`, while the Linux helper returns the authored bitmap when no replacement is available. That symbol was not one of the 23 pending rows, but it was a related PS2 implementation gap.

The fresh root no longer lists `hud_hires_sprite_bitmap` as a live external, and it is absent from the generated `ps2_platform.c` placeholders. Its PS2 owner is now present in `submodules/halo-ce-universal/port/ps2/src/ps2_interface.c:119-126` (file SHA-256 `767e9d44d92e59625b7090e4f397330ab85e2868bd505f4a5f18e4d75ce518db`). The function ignores the replacement sequence and returns the input `bitmap`, which is the correct identity fallback when PS2 has no high-resolution HUD replacement table. This matches the stock fallback documented in Linux `port/linux/game/hud_hires_tags.c:226-290` and prevents the null bitmap hazard described in the prior report.

Validation: `python3 -m pytest -q tests/test_hcu_hud_fallback.py` passed (**2 passed**). The test file SHA-256 at validation was `b749f65ec81596d66b5029e58e1bf656fb657f5e077598d34df71357b965760f`. This verifies the fallback behavior at the source/host-test level; it does not prove visible HUD rendering in PCSX2 or GS output.

## Gate status

The refreshed root confirms the previous audit remains applicable to the same 23 pending render externals. The HUD identity fallback is an independently resolved adjacency, not completion of the two pending HUD `tags_loaded` / `tags_unloaded` lifecycle hooks or the broader render/presentation path. M0 remains open until the ledger dispositions and tests are completed for these and all other external classes, and allocation ownership is reconciled.
