# Halo CE flashlight: retail behaviour and what the PS2 port should do (2026-11-10)

Sources: the retail Xbox `default.xbe` (extracted from `Halo - Combat Evolved.xiso.iso`, 2,535,424 bytes, SHA-256
`4094e994243ddeae3f1b478bde6a7ee81498218ccd7c9d7bc2327db547d95aae`), the retail map tags (`bloodgulch.map`,
`wizard.map` decompressed), `submodules/halo-ce-universal` (CE decomp, "CE" below), `submodules/halo-64` ("H64"), and the
current PS2 code. Observed = read from bytes/decompilation/source. Inferred = reasoned from observed facts. Unknown = not
established.

## How the REA work was done

REA's MCP Ghidra provider was not configured in this session (`GHIDRA_INSTALL_DIR` unset, `provider_unavailable`), so
`open_binary` on the image succeeded but no analysis tool could run. The Ghidra 12.1.4 that REA installed
(`~/.local/share/rea/ghidra`) was driven directly with `analyzeHeadless` instead: every XBE section was laid out at its
virtual address in one flat image (`scratchpad/rea/xbe_flat.bin`, VA 0x11000..0x3b47a0), imported as `x86:LE:32:windows`
at base 0x11000, auto-analysed, and the functions below were decompiled. The XBE is stripped: all names below are mine,
matched to CE by constants, structure offsets and control flow, not by symbols. No target was executed.

## What the retail flashlight is (observed)

### 1. A unit state machine (identical to CE and H64)
Retail `FUN_00044ad0` (4,627 bytes, the unit update; flags dword at unit+0x1B4, light power +0x2F0, battery +0x2F4, night
vision power +0x2F8) contains exactly the CE sequence (CE `units.c:6175-6310`, H64 `units.c:6040-6110`):

| retail | CE |
|---|---|
| battery -= 1/3600 per tick while on (`_DAT_001f0d54`), skipped when definition flag 0x1000000 | `units.c:6245`, `fucking_lasts_forever` |
| power += 1/6 per tick to 1.0 (`_DAT_001f0b90`) | `units.c:6255` |
| off: battery += 1/900 (`_DAT_001f0c18`) while < 1; power -= 1/24 to 0 (`_DAT_001f1210`) | `units.c:6267-6272` |
| on bit cleared when parented or dead | `units.c:6247-6250` |
| night vision power +1/12 on, -1/24 off (`_DAT_001f0d3c`) | `units.c:6289-6301` |
| toggle needs battery > 0.2 (`_DAT_001f0a9c`) | `units.c:6233` |

So power ramps up in 6 ticks (0.2 s) and down in 24 (0.8 s); a full battery lasts 2 minutes. The port runs this CE code
unchanged, so the state machine is already retail-exact. (The shipped CE fields are the same on the PS2 build.)

### 2. A dynamic spot light attached to the unit's `flashlight` marker
Retail tag `characters\cyborg\flashlight_cyborg` (`ligh`; bloodgulch and wizard agree), parsed at the offsets of CE's
`point_light_definition` (`object_lights.c:303`, `rasterizer_xbox_environment.c:353-430`):

| field | cyborg (Master Chief) | marine_armored |
|---|---|---|
| flags | 0x19: dynamic, supersize in first person, is-first-person-flashlight | 0x23: dynamic, **no specular**, don't fade with camo |
| radius | 6.0 wu (radius modifier 1.0..1.0: size does not change with power) | 3.0 wu |
| falloff / cutoff angle | 20 deg / 45 deg (cos 0.9397 / 0.7071) | same |
| specular radius multiplier | 2.0 (spot radius 12 wu, inner 6 wu) | 2.0 (unused: no specular) |
| colour | lower 0,0,0 to upper 1,1,1 (white), interpolated by the unit's `integrated_light_power` function | same |
| gel map | `characters\cyborg\bitmaps\spotlight cyborg` (128x128 Y8 cube) | same tag, never sampled (no specular) |
| lens flare | `characters\cyborg\flashlight_cyborg` (`lens`) | same |

The light follows the `flashlight` marker of the unit (CE `object_lights.c:1040-1280`, `light_update_transform` `:1985`)
and its intensity is the object function driven by `integrated_light_power` (`units.c:1175`).

### 3. First person: the light moves to the weapon's `flashlight` marker
Retail `FUN_000d7f10` is `first_person_weapon_center_flashlight` (CE `first_person_weapons.c:702`, H64
`first_person_weapons.c:687`): if the player's first-person weapon is visible (`byte [idx*0x1ea0 + base]`), it fetches the
weapon model marker named `"flashlight"` (string at VA 0x21bd78, only reference from this function) and sets
position = marker position - 0.5 * marker forward (`_DAT_001f0aa0` = 0.5, checked), forward/up = marker forward/up. Its only
caller (`0x92db8`, inside `FUN_00092890`, the light preprocess = CE `lights_preprocess_scene`) applies it to lights whose
definition has bit 4 (`is_first_person_flashlight`) and flags them as first-person-weapon lights.
With bit 3 (`supersize_in_first_person`) set the cluster list is skipped (CE `object_lights.c:1823-1840`), so the beam is
not cut by BSP cluster connectivity even when the gun muzzle is inside geometry.

### 4. What the beam does to the world (two retail passes)
- **Diffuse (objects and BSP)**: a point/spot light with radius 6 wu: per pixel distance falloff via
  `inverse_radius_squared = 1/r^2` and a cone term `clamp(dot(forward, dir) * s + o)` with
  `s = 1/(cos_falloff - cos_cutoff) = 4.29`, `o = -s * cos_cutoff` (CE `rasterizer_xbox.c:1093-1150`). Applies to the
  environment (`lights_render_diffuse`, `object_lights.c:1815`) and to models (`rasterizer_set_model_lighting_point_light`).
- **Specular spot with the gel (BSP only, cyborg only)**: retail `FUN_00076f50` (found from the pixel-shader words
  `0x00018C61`, `0x00011006`, ... at 0x7717b-0x7727c) is byte-for-byte CE `rasterizer_environment_specular_spot_light_begin`
  (`rasterizer_xbox_environment.c:3244-3330`): vertex constants = light position and `0.5/R`, the light's -forward, -left
  (forward x up), -up as three texture coordinate rows, and a cone ramp `forward * 1/(R-R/2)` with offset `-R/2/(R-R/2)`,
  where `R = specular_radius_multiplier * radius = 12 wu`; texture stage 1 is a **cube map** (`rasterizer_set_texture(1, 2, 1, ...)`),
  clamp addressing, linear filters, and the same 6-combiner pixel shader. The gel is therefore a perspective projection of the
  cube face the beam points into, and it fades in along the axis from 6 wu to 12 wu (beyond the 6 wu diffuse radius).
  The cube data (observed): face 0 (+X) is the bright ring pattern (mean 52, max 255, every texel non-zero); face 1 is
  all zero; faces 2-5 carry only faint wide-angle spill (max 19-37). Xbox stores cube faces 128-byte aligned
  (21,888-byte stride for the 128x128 + mips). So shipping face 0 as a 2D bitmap (what the port does) is faithful for every
  surface inside the 45 deg cone. The face/orientation convention (D3D +X: s = -z, t = -y) is inferred from the D3D8
  cube-face rule, not re-verified on hardware.

### 5. Lens flare
`flashlight_cyborg` (`lens`): primary map `effects\particles\lens flare\bitmaps\flares_generic`, two reflections (bitmap 0,
radius 0.05, brightness 1.0, both radius and brightness scaled by `light_to_camera`; bitmap 2, radius 0.10, brightness 0.6,
unscaled), near/far fade 10 / 15 wu, flare falloff / cutoff 60 / 85 deg. By the retail loop (CE `rasterizer_lights.c:930-1190`)
the `light_to_camera` function is zero when the viewer is behind the light and one when facing into it, so the flare is
what *other* players see when they look into a torch within 15 wu; the owner never sees it.

## What the PS2 port does today (observed, `ps2_render.c:843-960`, `hcu_render_objects.c` `flashlight_disc`)

For each view whose first-person unit has `integrated_light_power > 0`, it casts one ray from the **camera** along the
camera forward, 6 wu long, takes the first hit, and publishes one FX_LIGHT (pool centre, surface normal, radius = hit
distance clamped 0.3..6, intensity = power * (1 - t)); other bipeds with the torch on get the same from their camera/aim
(3 at most). The parent draws an additive Gouraud disc (16 x 4 rings, polar-mapped gel face 0, stretch up to 2.5 on slanted
surfaces, gain 0.6).

## Differences from retail, and what to change

1. **Origin and direction.** Retail: first person = weapon `flashlight` marker - 0.5 * forward, direction = marker forward;
   third person = the biped's `flashlight` marker (its model-space orientation, not the aim vector). Port: camera point and
   camera forward. Fix: in `ps2_c3_flashlight_probe`, call `first_person_weapon_center_flashlight(unit_index, &pos, &fwd, &up)`
   (already compiled in CE) for the viewing player, and `object_get_marker_by_name(unit, "flashlight")` for other bipeds
   (fall back to the camera when the marker is missing). The visible effect: the pool/beam originates low right of the screen
   centre and tracks the weapon sway, as in retail.
2. **Reach and falloff.** Retail lights within 6 wu (diffuse) and 12 wu along the axis (gel); falloff is `1 - d^2/R^2`-like per
   pixel, cone term smooth between 20 deg and 45 deg. Port: ray capped at 6 wu, linear `1 - t`, hard 45 deg disc edge with the gel
   ring supplying all the shaping. Fix: cast 12 wu, fade the gel along the axis from 6 to 12 wu, and weight the disc by
   `cone = clamp(cos * 4.29 - 3.03, 0, 1)` per ring (the rings already sit at 25/50/75/100 % of the cone's footprint radius,
   i.e. at known angles).
3. **Gel projection.** Retail is a perspective (cube-face) projection. Port: polar mapping on a disc, stretched. For a surface
   perpendicular to the beam they coincide; on slanted surfaces they differ. Fix: compute each vertex's UV from the
   light-to-vertex vector `d`: `u = 0.5 - 0.5 * (up . d) / (fwd . d)`, `v = 0.5 - 0.5 * (left . d) / (fwd . d)`; drop the stretch heuristic.
4. **Per-biped gel.** Marines' torch (`flags 0x23`, no specular) has no gel: only the diffuse brightening. Port draws the gel for
   every biped. Fix: carry a "specular" bit from the unit's light definition (cyborg yes, marine no) and draw the marine pool as
   the smooth cone-weighted disc without the ring texture.
5. **Objects are lit too.** Retail brightens models inside the cone (diffuse model lighting); the port's additive disc only brightens
   what it overlaps in the frame, which includes objects standing in the pool. Acceptable approximation; a per-object point light
   in the EE lighting path would be the exact fix and is a larger change.
6. **Lens flare.** Not implemented. The new first-person flare pipeline (`lights_port_first_person_flares`, `flare_pass`) can be
   reused: for lights with `lens_flare` and a unit parent, publish the two reflections for views other than the owner's.
7. **Camo and power.** Retail scales colour by `1 - active_camouflage` unless flag bit 5 is set (marine: set); keep that if the pool
   is ever used on a cloaked biped. Power, battery and ramp already come from CE.

## Evidence checked on the port (2026-11-10)

- Lit Wizard room, first person: the pool washed out at gain 0.8, so gain 0.6 (commit d9c2750).
- Longest (dark interior, sniper, debug ISO `v54_flare`, shot `fn_v54_flare_3_gel_b.png`): the ring-textured pool is visible on the
  wall at 0.6 gain; it reads slightly pale because the ambient is dark and the add is uniform white.

## Unknowns

- Exact retail attenuation curve of the diffuse term in the pixel shader (the combiner words were not decoded; the vertex
  constants and the CE formula above are what is verified).
- The D3D cube-face orientation of the gel (symmetric rings make it nearly invisible).
- How retail orders the diffuse and specular passes against fog (not needed for the port).
- Third-person owner view with the real `flashlight` biped marker was not captured; the debug biped pool on Longest was not
  clearly visible in the screenshot.

## Citations

- CE: `source/units/units.c:5995-6016, 6175-6310`, `source/objects/object_lights.c:303-345, 1040-1285, 1815-1990`,
  `source/interface/first_person_weapons.c:702-730`, `source/rasterizer/xbox/rasterizer_xbox.c:1093-1150`,
  `source/rasterizer/xbox/rasterizer_xbox_environment.c:353-430, 1825-1840, 3244-3330`,
  `source/rasterizer/rasterizer_lights.c:930-1190`.
- H64 (same decomp, identical logic; its N64 port has no dynamic-light renderer, so nothing there implements the visual):
  `source/units/units.c:6040-6110` (power +1/6, battery +1/900, power -1/24 at lines 6061/6073/6078),
  `source/objects/object_lights.c:1015-1030` (center flashlight),
  `source/interface/first_person_weapons.c:687-720`, `source/rasterizer/xbox/rasterizer_xbox_environment.c:1225` (gel on stage 1),
  `README.md:351,364` and `port/n64/src/xdk_input.c:21` (flashlight is a held D-pad/C-right press).
- Retail XBE (Ghidra addresses = virtual addresses): `0xd7f10` center flashlight, `0x92890` light preprocess, `0x44ad0` unit update,
  `0x76f50` specular spot light begin, `0x1262f0`/`0x1260f0` colour interpolate(+scale); constants `.data` 0x1f0aa0 (0.5), 0x1f0b90 (1/6),
  0x1f0c18 (1/900), 0x1f0d3c (1/12), 0x1f0d54 (1/3600), 0x1f1210 (1/24).
- PS2: `submodules/halo-ce-universal/port/ps2/src/ps2_render.c:843-960`, `src/stream/hcu_render_objects.c` (`flashlight_disc`, `flashlight_pass`).
