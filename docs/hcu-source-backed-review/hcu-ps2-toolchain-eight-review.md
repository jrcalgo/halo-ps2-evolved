# Eight remaining toolchain externals

Date: 2026-10-20. The rooted object
`build/hcu-ps2-closure/all/rooted.o`
(`4a6dc9b2fb90dbe1f13d5bd55dda7d7db1a2f9df29c4e3c0593d731cb720dc29`) still lists these
eight names. The combined machine map
`build/hcu-parent-link-probe/hcu-gameplay-machine.map` resolves each one to a
pinned EE archive member. None is a body in `ps2_platform.c`. Provider names
alone are not the disposition; the live caller sections are.

## Compiler double helpers

`__extendsfdf2`, `__fixdfsi`, and `__truncdfsf2` are GCC soft-float helpers
(`libgcc/soft-fp/extendsfdf2.c`, `fixdfsi.c`, `truncdfsf2.c`), linked from
`libgcc.a(_sf_to_df.o)`, `(_df_to_si.o)`, and `(_df_to_sf.o)`.

`__fixdfsi` has four live sections: `fast_ftol`, `real_a_rgb_color_to_pixel32`,
and `real_argb_color_to_pixel32`, plus `dsound_volume_from_gain`.
`fast_ftol` in `source/cseries/cseries.h` converts through
`__builtin_rint((double)value)`, which is the promotion and the following
double-to-int. `__extendsfdf2` and `__truncdfsf2` are the same promotion on
the wider CE math set (actor movement, animation keyframes, collision). The
broad source-file lists are every translation unit that the compiler lowered;
the section list is the live call set. No hand-written substitute is linked.
Software-double time stays an M6 measurement.

## `floor`, `fmod`, and `sqrt`

`floor` is Newlib `s_floor.c` (`libm_a-s_floor.o`). The live sections are
animation keyframe selection (`animation_get_keyframe_rotation`,
`animation_get_keyframe_scale`, `animation_get_keyframe_translation` in
`source/models/model_animations.c`, which take `floor` of the frame index
before `fast_ftol`), `game_time_update`, decal placement, and the lens-flare
grid. Those callers need the mathematical floor, not a truncated cast.

`fmod` is Newlib `w_fmod.c` (`libm_a-w_fmod.o`). Live sections include
`first_person_weapons_update` (overcharge jitter frame wrap), `vehicle_update`
(tread and wheel wrap by `wheel_circumference` in `source/units/vehicles.c`),
`periodic_function_evaluate`, and the glow time wrap. A zero remainder would
freeze those cycles.

`sqrt` is Newlib `w_sqrt.c` (`libm_a-w_sqrt.o`). Live sections include
`distance2d`, `distance3d`, `fast_normalize2d`, `fast_normalize3d`, actor
movement, and collision pill tests. Those lengths and normals are simulation
inputs.

## `rint`

The only live sections are `fast_ftol`, `real_a_rgb_color_to_pixel32`, and
`real_argb_color_to_pixel32`. `fast_ftol` documents the Xbox `FISTP` contract:
round to nearest under the default control word
(`source/cseries/cseries.h`). The linked body is Newlib `s_rint.c`
(`libm_a-s_rint.o`). That file rounds with the `TWO52` add/subtract sequence.
It does not read an x87 control word. `ps2_crt.c` `_control87` stores a
software word and does not reprogram this routine, so the rooted callers keep
the default nearest rounding the comment requires. EE timing of the soft-float
sequence remains M6.

## `memcpy`

Newlib `memcpy.c` (`libc_a-memcpy.o`) copies `n` bytes and states that overlap
is undefined. The CE wrapper `csmemcpy` in `source/cseries/cseries.c` asserts
non-NULL pointers, a size below `MAXIMUM_MEMCPY_MEMMOVE_SIZE`, and
non-overlapping ranges before it calls `memcpy`. The other live sections
(object init, actor movement, input publish, animation orientations) use that
non-overlapping copy. Overlap is a caller precondition, not a missing body.
An EE byte-vector fixture is not required to name the owner.

## Disposition

All eight are `implemented`. They are not generated platform successes, and
they are not exclusions. Numeric cost and extra EE edge vectors stay on M6.
