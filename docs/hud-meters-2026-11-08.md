# HUD meters (shield, health, battery, heat, ammo)

## What was wrong
- The old PS2 meter used the texel's alpha as the fill order. CE's meter bitmaps (`hud_unit_meters`,
  `hud_ammo_meters`, A8Y8 256x256) keep the fill order in Y and the shape in alpha, so every
  partly transparent texel got the wrong fill and the meters showed as boxes.
- The stray "0" at the left of the screen was the port-only live score text
  (`game_engine_draw_live_score`). It is now under `HALO_PS2_LIVE_SCORE` and off.

## How CE draws a meter (decoded from `rasterizer_xbox_dynavobgeom.c`)
- Y >= flash alpha: empty colour, keeps (255 - empty alpha) of the backdrop.
- Otherwise: `(1-Y)*min + Y*max` plus `flash_colour * max(0, 1 - 2*clamp01(4*(threshold - Y)))`,
  keeps tint alpha (1 - opacity) of the backdrop.
- Result is `colour * shape alpha * tint.rgb` added to the retained backdrop.
- The flash animation (ammo spent, shield or health hit) is the flash colour and threshold the CE
  HUD code already sends each frame (`hud_draw_meter`, `reference_time`); no PS2 timing code.

## PS2 implementation
- `texconv.py` bakes a meter bitmap as PSMT8 with index `(shape level << 6) | (Y >> 2)`, shape levels
  {0,127,191,255} (`TF_METER`, `TEX_F_METER`).
- `hcu_bitmap_meter_build_clut` builds a 256-entry CLUT per draw from the request (min, max, flash,
  background, tint colours and the threshold). `meter_emit_palette` uploads it inline into a scratch
  CLUT slot that the lease holds (`lease->reserved` = slot + 1) and draws with alpha blend, or
  premultiplied blend when a colour exceeds its alpha.
- A resident-hit descriptor carries the texture flags, otherwise only the first upload takes the meter path.
- Needs a package rebuilt with the new texconv (pin in `docs/reports/m2-c2-survival-...-r3.json`).

## Verified
- Blood Gulch spawn (plasma pistol): shield slab, health ticks and heat grid are clean shapes, no boxes, no "0".
  Logged requests: shield threshold 253, health 255, heat 0 (empty, as expected at no heat).
- Not verified on screen: the flash animation itself (no damage was dealt in the capture).
- The plasma pistol's battery icon interior is a static bitmap, not a meter request.
