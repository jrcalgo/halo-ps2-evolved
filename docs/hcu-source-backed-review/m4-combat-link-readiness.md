# M4 combat-link readiness (2026-10-20)

This is a source-backed readiness audit for M4 step 1 in
[`plans/5.hcu-remake.md`](../../plans/5.hcu-remake.md#L331). It is not an M4
implementation or acceptance claim. M4 step 1 explicitly depends on the
converted tag system and the M3 collision owner; neither is yet shown as a
production gameplay path in the current guest evidence.

## Current guest boundary

The user's latest PCSX2 interpreter run is recorded in
`build/hcu-ps2-closure/emulator-m1-interpreter-80194266b5ce405282a5a152460f9174/result.json`.
It used the combined ELF SHA-256
`2eb1f907d781bcfe4fb6170ba698f05d58090510b818c595acb8f2921fb1c54e`, the
source pins parent `1e1a9c1550521dd1c24ed10e64524d60f189a3f7`, HCU
`c77bef1dc48a5bc99cf0547ac9d1c7c73ef46c96`, and halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. It passed the
`HALO_PS2_LOCAL memory-ready` marker and the test's physical interval and
canary checks. The harness is configured to terminate at that marker; it
explicitly reports `outcome: memory-placement-observed-not-playable`,
`reached_game_initialize_done: false`, and `linked_physical: null`. Thus the
run does not test later lifecycle stages. This is useful M1 memory evidence,
not weapon, projectile, damage, or collision runtime evidence.

## CE combat call graph already present in the source

The HCU source has the appropriate retail gameplay pieces, but M4 needs them
reached through one tick and one collision/damage authority:

1. [`game_tick`](../../submodules/halo-ce-universal/source/game/game.c#L331)
   orders units, AI, players, effects, first-person weapon state, game rules,
   scripts, objects, HUD, and player effects. In particular, it calls
   `units_update()` before `objects_update()` and updates first-person weapon
   state at lines 357–394. That ordering is the parity baseline; a parent-side
   manually sequenced weapon loop is not equivalent.
2. CE's object-type table routes weapon lifecycle to
   `weapon_new`/`weapon_update` and projectile lifecycle to
   `projectile_new`/`projectile_update` ([object type registrations](../../submodules/halo-ce-universal/source/objects/object_types.c#L294),
   [projectile registration](../../submodules/halo-ce-universal/source/objects/object_types.c#L347)).
   `weapon_new` initializes loaded/reserve magazine values and trigger state
   from the loaded weapon tag ([weapons.c](../../submodules/halo-ce-universal/source/items/weapons.c#L845)).
   `projectile_new` establishes the ultimate-parent ignore filter, detonation
   and arming timers, and attachment state from the projectile definition
   ([projectiles.c](../../submodules/halo-ce-universal/source/items/projectiles.c#L521)).
3. CE damage resolution selects damage-resistance material records from the
   target collision model and has a default fallback; M4 must preserve the
   selected region/material and ownership semantics rather than routing every
   hit to a synthetic body target ([damage.c](../../submodules/halo-ce-universal/source/objects/damage.c#L1680)).
4. A source-level exception is already visible: `weapon_melee_attack()` is an
   empty function in the pinned HCU source ([weapons.c](../../submodules/halo-ce-universal/source/items/weapons.c#L839)).
   The energy sword therefore needs a clearly marked PS2 port implementation
   in HCU; merely linking the generic stock function cannot satisfy its M4
   requirement.

## Current integration gap

The combined machine entry in
[`hcu_main.c`](../../src/stream/hcu_main.c#L118) allocates and binds the
machine arenas, initializes pad/storage/map services, and then enters the CE
shell; the successful guest trace intentionally terminates at the earlier
memory-ready marker before those later steps are observed.
The current link contains `game_tick`, `weapon_new`, and `projectile_new`
symbols, but symbol presence only demonstrates compilation/linkage. It does
not establish that the local game lifecycle reaches a loaded scenario and
calls `game_tick` with valid CE game globals.

The parent M13 diagnostic path is explicitly separate and remains synthetic:
[`play_ee.c`](../../src/game/play_ee.c#L543) advances its own simulation tick,
parent movement, `gun_tick_seeded`, `shot_tick`, and parent vitality/target
records. Its actor hit branch applies diagnostic `combat_targets` or `vital`
damage rather than CE object damage ([hit resolution](../../src/game/play_ee.c#L685)).
The optional HCU machine target and the `WORLD_PLAY` target are also selected
as separate build branches in [`ee-world.mk`](../../tools/ee-world.mk#L50).
This diagnostic is valuable as a parity fixture, but is not the authority to
which HCU combat has been connected.

## M4 step 1 disposition and next work

**Disposition: not started; upstream integration prerequisites remain open.**
Do not wire the parent `shot_tick()` into HCU as a shortcut. Before the first
combat implementation can be meaningfully tested, complete the upstream
sequence in the primary plan: reach the M1 initialized game boundary; complete
M2 production tag/BSP ownership and rollback; then establish M3's CE tick,
object identity, collision owner, and immutable post-tick snapshot. These are
the exact prerequisites M4 step 1 names, and the current memory-ready trace
does not satisfy them.

Once those interfaces exist, implement M4 in this order:

1. Add a CE-backed fixture that constructs a valid weapon datum from a loaded
   tag and proves one `game_tick` advances trigger/ammo and projectile state.
   Hash simulation state before/after tick and compare against the pinned CE
   source oracle; run without rendering between ticks and with multiple renders
   between ticks.
2. Route projectile collision through the single M3 collision owner and feed
   the resulting target datum, owner/ultimate-parent, hit material/region, and
   damage definition into CE's impact/damage path. Cover surface impact and
   actor impact separately.
3. Add grenade equipment, throw/release, fuse, collision, and AoE to the same
   owner/tick path; test owner exclusion, simultaneous blasts, damage filters,
   and dynamic-pool exhaustion with atomic tick behavior.
4. Only after generic CE weapon/projectile/damage works, proceed to the
   all-weapon M13 ledger, then the bespoke fuel-rod replacement and the
   energy-sword/gravity-rifle `port:` behavior required by M4 steps 2–4.

No implementation was changed by this audit. The next executable gate is the
upstream M1 initialization boundary, not an M4 combat smoke. M4 remains
incomplete under the milestone table.
