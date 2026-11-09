# HUD in high definition on every map, and DualShock button glyphs in prompts (2026-11-08)

## What changed

1. **Native-resolution HUD on all 13 maps.** Before this change only the Blood Gulch package carried the HUD bitmaps
   (unit meters, ammo, weapon backgrounds, counters, radar sweeper and blip, reticles) at their authored size. The
   other 12 map packages were older builds, made before `NATIVE_RESOLUTION_HUD_BITMAPS` existed, and held half-size
   copies, so the shield, health, ammo, grenade counter and radar looked soft on those maps.
   All 13 packages are now rebuilt from the current converter. A scan of every package's `TEXS` chunk finds the same
   42 single-mip textures of 128 px or wider on each map.
2. **Message icons in high definition.** `ui\hud\bitmaps\combined\hud_msg_icons` and
   `ui\hud\bitmaps\hud_msg_icons_sm` (the weapon icon beside the pickup prompt and the other help-text glyphs) joined
   `NATIVE_RESOLUTION_HUD_BITMAPS` in `tools/hcu_profile_bitmap.py`.
3. **The pickup prompt shows the DualShock button.** The prompt ("press [button] to pick up [weapon]") now draws the
   physical PS2 button that CE binds to the action control, as vector shapes, so it is sharp at any scale.

## Which button is drawn

CE chooses the prompt's icon from the player's control binding: `hud_messaging.c` reads
`preferences.game_control_to_xbox_buttons[...]` for the action icon and indexes `hud_globals->messaging.button_icons`
with the result. The DualShock driver (`platform/pad.c`, published through `ps2_input_publish_dualshock`) maps the
physical pad onto Xbox analog slots in a fixed order, so the mapping back is exact:

| Xbox icon | DualShock |
|---|---|
| A | Cross |
| B | Circle |
| X | Square |
| Y | Triangle |
| Black | R2 |
| White | L2 |
| Left trigger | L1 |
| Right trigger | R1 |

If the player rebinds the action control, CE returns a different Xbox button and the prompt follows it. Icons with no
DualShock twin (the d-pad, start and back, stick presses) fall back to the map's own art.

## Where the code is

| Piece | File |
|---|---|
| Xbox icon to glyph, cursor advance, text alignment | `port/ps2/src/ps2_interface.c` `hud_hires_button_draw` (halo-ce-universal) |
| Request queue entry (`button_glyph`, at most 4 per view per frame) | `port/ps2/src/ps2_bitmap_requests.c`, `port/ps2/include/halo_ps2_bitmap_requests.h` |
| Parent dispatch (no texture lease) | `src/stream/hcu_bitmap_dispatch.c` |
| Glyph geometry and GS packet | `src/stream/hcu_bitmap_quad.c` `hcu_bitmap_quad_emit_glyph` |
| Test | `tests/hcu_bitmap_glyph_main.c`, `tests/test_hcu_bitmap_quad.py` |

`hud_hires_button_draw` is the same hook the Linux port uses for its Xbox glyphs; on PS2 it used to be an auto-stub that
returned 0, so the stock Xbox art was drawn at half size.

The glyphs are triangles drawn with source-over alpha (`GS_ALPHA(0,1,0,1,0)`), clipped to their own scissor. Face
buttons are a dark disc with a grey rim and a coloured symbol (blue cross, red circle, pink square, green triangle).
Shoulder and trigger buttons are a chamfered plate with a white label.

## Memory budget

The extra render code pushed the guest's file-backed size (`_fbss`) past the limit (0x370600 against 0x370000), so
budget version 8 (user-approved 2026-11-08) moves 65536 bytes from the uncommitted reserve to `elf_static`. The runtime
reserve now starts at 0x01d00000. All 13 guests and the menu link below the new limit (0x380000).

## Non-2D audit pin

Re-pinning was needed because the closure ELF the audit pins (`halo-local.elf`) was rebuilt. The audit inputs still
exist, so `audit_survival` was re-run against the rebuilt ELF's schema with the diagnostic's recorded ELF hash
replaced by the new one in a scratch copy. Every role, count and classification matched the committed r3 report, so
only the ELF hash in `docs/reports/m2-c2-survival-non2d-consumers-2026-10-28-r3.json` changed. The UI profile's
pins reference a staged catalog that no longer exists (`build/m2-c1-profiles-ui/...`); the 13 multiplayer maps use the
survival profile, so this was not needed.

## Package rebuild notes

* `build/retail-maps` is a symlink into a frozen tree, so `hcu_multiplayer_profiles.py` records the resolved frozen path
  in each package manifest, and the guest then asks the disc for that path. The rebuilt manifests were rewritten to the
  plain `build/retail-maps/decompressed/<map>.map` path that the earlier packages carried.
* The base ("selected") packages were gone, so they were regenerated from the 26 selection files with no
  `--render-media`; `hcu_render_media.py` runs afterwards and needs a render-free package.
* **Do not pass `--c3-object-profile-v3` (or `--c3-object-profile`).** They are opt-in lower-detail packings (64 px
  object textures, clustered LODs; vehicles limited to 3% of a cluster). The shipped packages are built without them.
  The first v6 build used the v3 profile by mistake: every map package came out about 5.8 MB smaller and vehicles,
  weapons and effect textures were low definition. The manifest tells them apart: a package built with a profile has
  an `object_profile` block, the shipped ones have none (Blood Gulch is 24.4 MB without it, 18.3 MB with it).
* After the packages are rebuilt, sed the symlink-resolved map path out of each manifest, then relink all 13 guests
  (`tools/hcu_build_mp_guests.py link`): the guests embed the per-map object table that comes from the package.

## Verification (headless PCSX2, Blood Gulch, 1 player)

The prompt was exercised with a temporary test hook (since removed) that spawned weapons in front of the player.

* A unit holding one weapon picks a second up automatically, so no prompt appears. The swap prompt needs a third weapon while the unit holds two (the hook gave a rocket launcher, then a sniper rifle).
* The prompt state is set by CE (`action_result` 6). `hud_hires_button_draw` is called every frame, the request reaches the parent, and the glyph is drawn next to the weapon icon.
* The default action binding is the Xbox X button, so the prompt shows the **Square** glyph (a pink square on the dark disc). An earlier version of this note said Cross: that was a bug, not the binding. `remap_sticks_for_local_player` (ui_widget.c, outside the PS2 closure) was a generated stub returning 0, so the prompt's button resolved to icon 0 (A) whatever the control was bound to, and the stock green "A" showed too. It is now implemented in `port/ps2/src/ps2_interface.c`.
* The weapon icon beside the prompt is the native-resolution `hud_msg_icons` art.
* A spawned weapon is only found by CE's nearby-item scan once it has a map cluster. A weapon placed exactly at ground height has `cluster=-1`, is never examined, and shows no prompt. Spawn it a little above the ground so it falls.
* Dropped test weapons despawn after about 30 s, so a screenshot taken later shows no prompt.

## Not done: prompt text

`rasterizer_draw_unicode_string` is a generated no-op stub in the PS2 link (`hcu-parent-link.map`), so no CE text is
drawn anywhere on the port: the prompt shows the button glyph and the weapon icon but not the words between them. This
was already true before this change (the stock-icon build shows the same gap). Drawing text needs a font renderer
(glyph atlas or vector strokes) behind `rasterizer_draw_unicode_string`; that is a separate piece of work.
