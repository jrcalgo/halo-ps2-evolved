# Main menu: retail sky, HD ring, large planet (2026-11-07)

## What changed
* **Camera speed.** Menu timing now follows the EE system timer (`GetTimerSystemTime`, 147.456 MHz), not frame counts.
  The menu draws at 20-30 fps, so the frame/60 clock ran the glide and the title music 2-3x slow. The camera keeps the
  retail `ring_loop` constants (retarget every 200 ticks, 400-tick glide, 30 ticks/s; about a 73 s loop).
* **HD ring.** Inner ring 1024x128 and outer ring 1024x512 as PSMT8 with a dithered 256-colour palette each
  (was 1024x64 and 512x256 RGB5A1). The GS cannot address a texture wider than 1024, so the retail 2048x128 inner ring
  is halved horizontally. Hull light gain 364 -> 250 (darker hull).
* **No moon.** The Basis quad is gone (retail menu has no visible moon); its VRAM is reused.
* **Planet (2026-11-09: retail placement).** Threshold (retail 512x512 bitmap, PSMT8 with a transparent index) is the
  retail `sky_ui` quad exactly: corners (5744.7, 15141.7, -697.3), (-6378.5, 9882.3, -7881.6), (-545.4, 11610.9, 12501.7),
  (-12668.6, 6351.5, 5317.4) after the 80 degree node turn; centre azimuth 107.9, elevation 11.6, about 59 x 54 degrees,
  96.7 degrees from the ring. It shows low on the left only in the last third of the camera loop, as in retail.
  (Earlier it was built beside the ring at 80 degrees across; the retail camera path, 70 degree FOV and camera * 0.999
  parallax were already exact.)
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
