# M0 source review: effect, contrail, weather and shadow render switches

## Disposition

Five rooted switches remain pending: `render_contrails_enabled`, `render_particles_enabled`, `render_particle_systems_enabled`, `render_weather_particle_systems_enabled`, and `render_shadows`. They are source-backed controls whose CE defaults are true; they cannot be treated as harmless false stubs in a port that promises visible gameplay parity.

## Source findings

- `render_contrails_enabled` is defined `TRUE` in `source/render/render.c:150` and gates contrail geometry submission in `source/render/render_contrails.c:459-478`.
- `render_particles_enabled` defaults true (`render.c:151`) and gates particle-datum enumeration, visibility filtering, first-/third-person ownership checks, and sprite submission in `source/render/render_particles.c:136-162`. This is render-side, but it carries CE effect visibility and first-person presentation semantics; it needs a PS2 snapshot/renderer owner.
- `render_particle_systems_enabled` defaults true (`render.c:152`) and gates `particle_systems_render` (`source/effects/particle_systems.c:1714-1745`). It also gates `weather_particle_systems_render` (`weather_particle_systems.c:756-791`). That latter routine writes the local system's leaf/cluster and underwater state, chooses its palette definition, creates/deletes it when definition changes, then renders it. Consequently, the call is not just a final draw primitive: suppressing it can suppress a weather-system lifecycle transition during rendering.
- `render_weather_particle_systems_enabled` defaults true (`render.c:153`) and is set by `render_effects` alongside the other toggles (`render.c:158-163`), and is exposed to HaloScript. The selected weather render routine does **not** test this variable; it tests `render_particle_systems_enabled` instead. This is a source-contract discrepancy, not proof that the global is unneeded: scripts can observe it and the setter updates it. Keep pending until the intended CE semantics and whether the PS2 script VM exposes that state are audited.
- `render_shadows` defaults true in `source/render/render_objects.c:264` and gates the entire `render_object_shadows` pass, including rasterizer shadow begin/end and object submission (`render_objects.c:374-401`). A false default suppresses the CE pass, so the PS2 shadow policy and state transfer need an explicit decision.

## Required M0 follow-up

Keep all five pending. The PS2 adapter should preserve these choices across the HCU tick/render snapshot boundary; for `render_particle_systems_enabled`, separately decide whether CE's render-driven weather lifecycle is retained, refactored to simulation, or proven equivalent. Add parity fixtures that toggle each HaloScript global and compare the CE state/visible-submission outputs, including a change in weather palette and a disabled-render interval. The current test only guards the source-backed findings and pending status; it is not a behavior/parity fixture.
