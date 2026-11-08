# Main menu: retail sky, HD ring, large planet (2026-11-07)

## What changed
* **Camera speed.** Menu timing now follows the EE system timer (`GetTimerSystemTime`, 147.456 MHz), not frame counts.
  The menu draws at 20-30 fps, so the frame/60 clock ran the glide and the title music 2-3x slow. The camera keeps the
  retail `ring_loop` constants (retarget every 200 ticks, 400-tick glide, 30 ticks/s; about a 73 s loop).
* **HD ring.** Inner ring 1024x128 and outer ring 1024x512 as PSMT8 with a dithered 256-colour palette each
  (was 1024x64 and 512x256 RGB5A1). The GS cannot address a texture wider than 1024, so the retail 2048x128 inner ring
  is halved horizontally. Hull light gain 364 -> 250 (darker hull).
* **No moon.** The Basis quad is gone (retail menu has no visible moon); its VRAM is reused.
* **Planet.** Threshold (retail 512x512 bitmap, PSMT8 with a transparent index) is now about 80 degrees across and
  built at run time beside the ring (ring direction from the mean camera position, turned 30 degrees right and raised),
  drawn behind the ring. Retail leaves it ~95 degrees away from the ring.
* **Sky.** The retail sky model's space sphere (320 triangles) and galaxy band (16) are exported from `ui.map`
  (`halo_ce_sky_mesh.bin`, "HSK1", node rotation applied) and drawn 3D around the camera: nebula bitmap (dimmed to
  0.6), star bitmap tiled 16x10 (additive, 256x256 PSMT8, was 128x128), galaxy bitmap (additive, 1024x128 PSMT8).

## Package layout (`menu_textures.bin`)
ring inner T8, ring outer T8, map atlas, game type atlas, logo, buttons, planet T8, glyphs, space, stars T8, galaxy T8,
five 1 KB palettes (ring inner, outer, planet, stars, galaxy), HMUI art, HSK1 sky mesh, HCM3 camera, HMR2 ring mesh.
Older packages are not accepted. VRAM: 280 of 288 pages (`MENU_HD_CLUT_PAGE` 226 holds the palettes).

## Verification
Headless PCSX2 screenshots across the camera loop (stars, galaxy, large planet beside the ring, sharp ring). Not tested
on the desktop or hardware. Host test `tests/test_hcu_main_menu.py` passes. ISO: `HALO_PS2_v4_skyhd.iso`.
