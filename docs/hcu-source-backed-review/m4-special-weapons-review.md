# M4 Group I — source-backed special-weapons review

**Date:** 2026-10-20  
**Scope:** M4 step 19 only: handheld Fuel Rod, Energy Sword, Gravity Rifle.  
**Disposition:** research and host source/tag fixtures prepared; none of these paths is accepted as integrated HCU/PCSX2 combat. This report does not close M4 or authorize retiring the parent M13 implementations.

## Evidence and limits

The gameplay source reviewed is the pinned `halo-ce-universal` submodule at
`6933490b2d16bb1c637295b6a0f3880ba23a7d56` (repository root
`submodules/halo-ce-universal`). Relevant code is the actual CE implementation,
not the comparison simulations in `src/game/`: [`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c),
[`projectiles.c`](../../submodules/halo-ce-universal/source/items/projectiles.c),
[`bipeds.c`](../../submodules/halo-ce-universal/source/units/bipeds.c),
[`units.c`](../../submodules/halo-ce-universal/source/units/units.c), and
[`damage.c`](../../submodules/halo-ce-universal/source/objects/damage.c).
The tag-derived weapon rows come from the local 24-map artifact
`build/combat-m13/all-map-weapons.json` (SHA-256
`3f76909c988d322d48ff51445cf1ce6d580e095a60487614f26914928e5007a0`),
and the deeper retail projectile/effect audit is
[`docs/m13-step10-fuel-rod-flight-investigation.md`](../m13-step10-fuel-rod-flight-investigation.md)
(SHA-256 `4d13d608ecf1df65019761090037bb394146466424326abdb352459aaa7e4047`).
Those reports identify retail map files and tag paths; the extracted map/tag
payloads themselves are not checked into this repository. Values below are
reported from those audits, not freshly re-decoded by this investigation.

This was source and tag-report investigation, not an ISO binary REA pass. The
available repo data gives tag values and decompiled source behavior. No
address-mapped retail executable pseudocode or timing trace was produced, so no
binary-level claims are made. The added host tests deliberately call
themselves source/tag contract tests: they check the actual pinned source and
reported retail rows, but do not execute a CE tick or prove EE behavior.

## CE mechanics and exact ownership boundary

### Generic projectile weapons: Fuel Rod

The retail campaign `weap` record at `weapons\\fuel rod gun\\fuel rod` has
one primary trigger, one projectile per shot, 10 rounds/s, 1.25 s charge,
trigger flags `0x8`, magazine 4 loaded / 12 total, 4 rounds reloaded, and
5-second reload. Its `rounds_per_shot` is **zero**. CE's generic
[`weapon_trigger_begin_firing`](../../submodules/halo-ce-universal/source/items/weapons.c#L2863)
owns the charge-state transition. In
[`weapon_trigger_fire`](../../submodules/halo-ce-universal/source/items/weapons.c#L2591),
the magazine path gates against `rounds_per_shot`, subtracts that exact value,
and then marks the trigger fired. This is why the retail 4/12 counter is not
spent by ordinary firing; replacing the zero with one because this is an
explosive would be a tag-parity regression. The adapter must preserve the
source's exceptional zero-cost behavior and test the interaction between
empty magazine, charge, trigger release, and refire rather than assuming
`weapon_new`'s 4/12 is consumed.

[`trigger_create_projectiles`](../../submodules/halo-ce-universal/source/items/weapons.c#L2373)
derives owner from the weapon, selects the trigger marker (or weapon origin
under the corresponding tag flag), aims unless the tag forbids aiming, and
creates the configured number of projectile objects. This is the generic path
the handheld rod must use; firing from the camera or from a parent-only
`shot_def` is not equivalent. CE [`projectile_new`](../../submodules/halo-ce-universal/source/items/projectiles.c#L521)
sets the collision ignore handle to the owner's ultimate parent and initializes
arming/detonation/attachment data. The projectile update/collision path owns
flight, medium classification, material selection, and response. The tag's
air gravity scale is 1.0 and range interval 0–100; underwater gravity scale is
0.4 and interval 0–10. CE explicitly computes deceleration from the selected
interval, but in air assigns the water upper bound (10) to the auxiliary
maximum-damage-distance field as an original-game quirk
([`projectile_calculate_deceleration`](../../submodules/halo-ce-universal/source/items/projectiles.c#L1165),
with the field/range declarations in
[`projectile_definitions.h`](../../submodules/halo-ce-universal/source/items/projectile_definitions.h#L84)).
Do not “correct” this apparent mismatch in the PS2 port.

The projectile's direct `impact_damage` is null. A target collision therefore
must not invent direct hit-point damage. A material can select the detonation
response; [`projectile_detonate`](../../submodules/halo-ce-universal/source/items/projectiles.c#L1337)
dispatches the linked explosion with owner context. The tag audit reports 30
material responses, mostly detonate with two overpenetrate and one reflect;
the linked explosion contains the 40/75/75 `jpt!` blast, owner-immunity and
detonate-explosives flags (`0x21`), an effect/particle/audio chain, and a
zero-damage shockwave part. Runtime effect processing and AoE target
eligibility/falloff belong to CE effects/damage, not the parent's projectile
collision callback. Preserve owner object/player/team through projectile,
effect, and `damage_data`; prove exactly-once detonation and victim selection
against a live CE actor and structure material.

Presentation is constrained by the supplied tag set: the weapon has no
recoverable first-person model/animation graph. The parent M13 path's borrowed
launcher/flak seat is therefore a transitional comparison, not a tag-backed
CE pose. Once HCU weapon logic owns the trigger, the tag-faithful fallback is
CE hands/arms presentation without inventing a fuel-rod view model; verify the
exact visibility conditions in
[`first_person_weapons.c`](../../submodules/halo-ce-universal/source/interface/first_person_weapons.c#L498)
and the parent-branch retirement warning in
[`m3_first_person_pose_auditor.md`](../investigations/m3_first_person_pose_auditor.md#L120).

### Energy Sword: melee arbitration, not a gun or projectile

The retail sword root has no magazine, trigger, or projectile; it references
the `weapons\\energy sword\\melee` damage tag, and its weapon melee-response
reference is null (the tag audit). CE's player melee path begins in
[`biped_update`](../../submodules/halo-ce-universal/source/units/bipeds.c#L4355):
it accepts a player melee request only when no melee is already active, the
weapon permits melee, and the unit is not zoomed; it starts the melee action,
stops reload, obtains timing from the weapon's first-person melee animation,
and schedules the impact at the private key frame. At the attack tick it calls
`unit_cause_player_melee_damage`. That function samples the biped head marker,
uses a fixed 5×5 collision-ray fan around the aim vector, excludes the
attacker, resolves child objects to parents, and gives priority to a biped
candidate over non-biped candidates (then the nearer biped). It uses the
weapon-specific melee damage when present and preserves owner object/player/
team in the `damage_data`; the damage path carries the selected collision's
node, region, material, and plane. See
[`unit_cause_player_melee_damage`](../../submodules/halo-ce-universal/source/units/units.c#L8996)
and [`object_cause_damage`](../../submodules/halo-ce-universal/source/objects/damage.c#L1428).

There is an important source boundary: `weapon_melee_attack()` in
[`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c#L839)
is empty. The current source search also found no explicit `lunge` routine or
lunge state in the examined CE biped/unit/weapon paths. The CE melee fan,
animation timing, selection/arbitration, and damage are therefore source-backed;
Halo 2-style forward lunge is **not** proven to be stock CE behavior. Step 19's
requested lunge must be specified as an explicit `port:` behavior in HCU, with
an independently agreed envelope/target rule and CE baseline separated from
that extension. Do not claim retail parity by merely invoking `weapon_melee_attack`.

Presentation is split: HCU owns melee state/animation timing and authoritative
collision/damage; the parent halo-ps2 adapter may draw the already accepted
sword orientation/pose but must not move the biped, select a target, or feed
pose corrections back into simulation. This follows the accepted component
boundary in [`plans/5.hcu-remake.md`](../../plans/5.hcu-remake.md#L28) and the
M3 first-person pose audit
([`m3_first_person_pose_auditor.md`](../investigations/m3_first_person_pose_auditor.md#L131)).
The sword/gravity pose exception is presentational only; it does not license a
parallel parent melee simulator.

### Gravity Rifle: shared flame projectile, distinct weapon definition

Retail weapon roots in the supplied multiplayer-map audit use a separate
`weapons\\gravity rifle\\gravity rifle` weapon tag with a 200/200 magazine,
400 total, 3.4-second reload, one round per shot, one projectile, and 30 shots
per second. Its trigger points to `weapons\\flamethrower\\flame`. The
flamethrower instead has a 600/100/1200 ammo profile, 15 shots/s, one round per
shot, and a `projectiles_cannot_be_aimed` trigger flag. The roots share the
projectile/effect route but not weapon cadence, ammo, reload, heat, or
weapon-specific trigger flags. In particular, the gravity rifle must not be
replaced by the flamethrower's `weap` record or by an invented conventional
bullet path. See the tag audit's comparison rows
([`fuel-rod-flight-investigation.md`](../m13-step10-fuel-rod-flight-investigation.md#L288)).

The shared flame projectile/effect has a persistent/contact-oriented route;
its detonation graph links the low-value 10/10/10 flame damage part. A
single-shot `projectile_new` smoke is insufficient: CE projectile update and
effect callbacks determine recurring contact, damage cadence, and effect
lifetimes. The same report explicitly says M13 does not yet execute this graph
in its parent runtime (ibid. lines 976–977, 785–786). HCU M4 tests must keep the
gravity rifle's own weapon datum and trigger state while following the shared
flame projectile and effect definitions, then compare cadence, ammo depletion,
contact damage, extinguishing/expiry, owner filters, and simultaneous effects
against the corresponding CE source/tag fixture. Do not import the entire
flamethrower heat/waste-ammo policy unless it exists on the gravity-rifle tag
or source route.

## PS2 constraints and presentation decisions

M4's hard EE budget is `dynamic_simulation` 2,621,440 bytes and
`frame_scratch` 393,216 bytes; the reserve is 5,767,168 bytes and remains
untouched ([`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md#L396),
[`config/memory-budget.json`](../../config/memory-budget.json#L4)). The
projectile/effect pools, not renderer GS eDRAM or IOP/SPU2 stores, consume the
simulation arena. Persistent flame must not allocate one EE object per rendered
particle; use the CE gameplay records and bounded effect/contact work, and
measure their aggregate high-water. Fuel-rod collision/effect traversal must
also have bounded collision iterations and effect/AoE candidates. The CE source
has a projectile collision iteration ceiling (`MAXIMUM_PROJECTILE_COLLISIONS_PER_UPDATE`)
and a combining-projectile ceiling in [`projectiles.c`](../../submodules/halo-ce-universal/source/items/projectiles.c#L250);
the PS2 port must audit every other nested effect/target loop rather than
assuming these two constants cap the whole blast graph. The sword fan performs
up to 25 vector collision queries per active melee impact; preserve its result
ordering but profile worst-case four-player + actor traffic on the EE before
increasing candidate counts. Avoid double-precision math or unbounded dynamic
allocation in new `HALO_PS2` paths.

M4 exit remains the plan's complete arsenal gate in both interpreter and
recompiler. These three host fixtures are prerequisites only: they do not prove
CE tag loading, M3 collision integration, target runtime, replay-equivalent
traces, correct PS2 memory high-water, or that the rendering adapter is
reconciled with the authoritative CE first-person pose. Fuel Rod's existing
parent pose is explicitly temporary; the sword/gravity pose is an accepted
PS2 presentation exception; none of those visual facts establishes combat
simulation parity.

## Required follow-up before marking step 19 complete

1. Build a host fixture around the production CE trigger/projectile/effect
   functions (or a narrow, production-linked seam) with the extracted retail
   records. Cover Fuel Rod zero-cost ammo, charge/release, air-water transition,
   material table dispatch, no direct damage on null `impact_damage`,
   exactly-once effect/AoE with owner/team filter, and deterministic RNG.
2. Add the minimal explicit PS2 lunge policy to HCU only after recording its
   intended bounds as a port extension. Test no-target, competing target,
   obstruction, simultaneous melee requests, attack-tick timing, sword damage
   selection, response-null behavior, shield/body/death, and presentation
   independence. A host test of stock CE's 5x5 fan is not a lunge test.
3. Exercise Gravity Rifle's own trigger/ammo state through the shared flame
   projectile route; contrast one tag field at a time with the flamethrower so
   source evidence determines what is shared and what remains unique.
4. Integrate actor collision and damage once M3 designates CE collision as
   production owner. Capture stable simulation traces and EE pool high-water;
   execute interpreter and recompiler parity only after the combined M4 image
   exists.
5. Keep the parent special-weapon profiles and presentation adapters until
   their exact retirement conditions in M4/M6 are met; do not delete or
   replace them on the strength of this report.

## Test artifact

[`tests/test_hcu_special_weapon_source.py`](../../tests/test_hcu_special_weapon_source.py)
contains host-run source/tag contract checks. They assert that the reviewed CE
functions still express the paths described above and that the locally
available extracted-tag audit has the expected three special-weapon records.
They intentionally do not label themselves executable weapon simulation.
