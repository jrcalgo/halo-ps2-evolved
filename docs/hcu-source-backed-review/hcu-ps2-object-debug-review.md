# M0 source review: object debug render toggles

## Disposition

Four rooted globals are `excluded-proven` for the PS2 product path: `debug_objects_biped_autoaim_pills`, `debug_objects_biped_physics_pills`, `debug_objects_devices`, and `debug_objects_vehicle_powered_mass_points`. The source call graph places their only reads in object debug-render callbacks, separate from each object's update/physics callbacks.

## Evidence

`biped_render_debug` in `source/units/bipeds.c:1402-1434` calls `biped_get_physics_pill` and `biped_get_autoaim_pill` to draw their already-computed bounds. It does not alter target acquisition, collision, or the physics pill. `source/objects/object_types.c:272` installs this function as the biped render callback.

`device_render_debug` in `source/devices/devices.c:630-683` formats and submits a debug string based on device power, power velocity, position, and group state. It does not assign those device values; `object_types.c:398` selects it for device debug rendering.

`vehicle_render_debug` in `source/units/vehicles.c:480-505` reads the powered-mass debug toggle, but the guarded mass-point loop is empty in the pinned source. It is installed as an object render callback at `object_types.c:286`; vehicle movement and powered-mass processing are elsewhere.

The ledger's caller maps also include script-global registration in `source/hs/hs_globals_external.c`, which exposes these controls to scripts/debug commands. No read outside the render callbacks or write affecting object simulation was found for the four reviewed symbols. If PS2 later supports developer geometry/text overlays, these can be reconsidered as render-only adapters; they are not required game-state owners for M0's local gameplay path.

## Regression guard

The focused test ties each disposition to the exact read sites and object render callback table, and verifies the two biped branches call debug-draw routines only. This proves source separation, not visual output parity.
