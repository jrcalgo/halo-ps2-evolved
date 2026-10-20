# M13 Step 10 investigation — retail weapon behaviors and fuel-rod flight

Status: read-only investigation. This report makes no gameplay, fixture, pack,
or plan changes. It began as a bounded fuel-rod flight investigation and has
been expanded to audit all 23 retail `weap` paths in the supplied XISO. The
fuel-rod flight/effect evidence below remains the deep dive; the later
inventory records each path's trigger, magazine, projectile, direct-damage and
effect links, source family, current port boundary, confidence, and remaining
work. Needler-specific guidance, attachment and combine analysis is delegated
to [`combat-needler-audit.md`](combat-needler-audit.md) and is reconciled here,
not duplicated.

## Why this is a useful bounded investigation

The current M13 play path retains projectile initial/final velocity, gravity,
maximum range, and damage values, implements final-speed crossing, and now
packs both air/water distance intervals and water gravity. The fuel-rod tag is
unusual: it has no maximum range or impact damage tag, but different air and
water upper bounds and nonzero water gravity scaling. Host fixtures now check
the selected air and water first-tick values, water disappearance tick, and a
tick-boundary transition. They do not model CE's collision-driven media
transition within a tick, nor do they execute the linked detonation effect.
Because the tag has no direct impact-damage reference, blast damage must remain
distinct from direct hit scaling.

## Evidence identity and method

- Retail XISO: `/home/ai/Documents/Halo/Halo - Combat Evolved.xiso.iso`,
  SHA-256 `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258`.
- XISO extraction route: pinned `halo-ce-universal/port/linux/src/xiso.c`,
  followed by the existing map/tag reader. The campaign map containing both
  `weapons\\fuel rod gun\\fuel rod` and
  `weapons\\fuel rod gun\\hunter fuel rod` is `data/retail/weapon-audit-maps/c40.map`,
  SHA-256 `d7465f07a675a86785a329b9ab3d8a5a20b25b7ca7d05bafeb7ca87b02b20be9`.
  This ignored map is extracted from the supplied XISO and was only read.
- Source pins: `halo-ce-universal` `7524ba61689a912bdec234d9687b178f0b0e7389`;
  `halo-64` `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.
- Tag parsing used the existing bounds-checked `Region` reader and
  `tools/play_weapons.py` trigger/projectile/magazine layouts, resolving tag
  IDs to each map's tag paths. Current `PRJ2`/`PRS1` serialization now includes
  both environment range pairs and water gravity (the earlier report text that
  said the extractor did not retain them is stale). Cross-map inventory used
  the ignored 24-map extraction; each value below is retail tag evidence, not
  a measured retail runtime trace.
- REA 6.5.0 is available in this session. A direct
  `mcp__rea__open_binary` attempt on the supplied XISO returned
  `unsupported_target` / `unsupported binary format`. This agrees with the
  earlier artifact investigation in `docs/combat-rea-extraction.md`: the XISO
  and XBE container are not directly accepted; its extracted, stripped XBE
  `.text` analysis produced 2,355 unnamed procedures and no combat attribution.
  No semantics are claimed from REA pseudocode here. REA is not evidence for the
  tag values below; they come from the supplied retail map tag. A future
  source-address-specific REA analysis would require a defensible mapping from
  the XBE code to the source routines, which the current stripped output does
  not provide.

## Retail tag observations

The `fuel rod` weapon in `c40.map` points to the same-named `proj` tag used by
the Hunter fuel-rod weapon. Both weapon paths resolve to this projectile.

| CE projectile field | Retail value | Interpretation / parity consequence |
|---|---:|---|
| flags | `0x00000003` | Source flag word; do not infer target/guidance semantics without the enum audit. |
| detonation timer start | `1` | CE enum is “after first bounce”; no timer duration is configured (`timer_lower_bound == timer_upper_bound == 0`). |
| maximum range | `0` | No explicit maximum-range detonation path. |
| air gravity scale | `1.0` | Full global gravity while classified in air. |
| air damage range | `[0, 100]` | The source computes an air deceleration coefficient from this interval. |
| water gravity scale | `0.4` | Reduced gravity while wholly under media. |
| water damage range | `[0, 10]` | The source computes the water coefficient from this interval. |
| initial velocity | `0.4666666985` units/tick | About 14 units/second at 30 ticks/second. |
| final velocity | `0.1666666716` units/tick | About 5 units/second. |
| impact damage reference | `NONE` (`0xffffffff`) | No direct object impact damage tag is referenced by this projectile. |
| extracted maximum-damage distance field | `10.0` | This is the retail water upper bound, also assigned by CE in its air initialization branch (see below). |

The current M13 pack row for the fuel rod records the same initial velocity
(raw float bits `0x3eeeeef0`), final velocity, gravity and 10-unit
`maximum_damage_distance`; `damage_minimum/lower/upper` are zero because the
impact-damage reference is null. The pack's `damage` fields must not be read as
the detonation blast's damage: that is reached through projectile/effect
handling, which is separate from direct `impact_damage` in the source.

## Source semantics and cross-check

Pinned CE declares the air and water damage intervals separately in
`submodules/halo-ce-universal/source/items/projectile_definitions.h:84-104`.
`projectile_calculate_deceleration_from_distances` computes
`(initial_velocity² - final_velocity²) / (2 * (maximum_distance - minimum_distance))`
when the velocities and distance interval differ from zero
(`source/items/projectiles.c:1110-1128`).

`projectile_calculate_deceleration` selects the water interval and gravity
context when the projectile is wholly under media. In air it selects the air
interval, but deliberately sets runtime `maximum_damage_distance` to the
*water* upper bound; the source comment explicitly says this is retained from
the original game. Both branches start the deceleration timer immediately
because the lower-bound distance is zero (`source/items/projectiles.c:1165-1210`).
For this tag, that means coefficient derivation is based on a 100-unit air
interval or a 10-unit water interval, while the runtime auxiliary distance is
10 in either case. Do not “correct” the air assignment to 100 just because the
field name suggests it: that would differ from the checked CE source.

The flight loop applies deceleration once its timer reaches one, integrates
average velocity within the tick, clips the within-tick speed crossing to
`0.99 * final_velocity`, then applies air/water gravity. It checks the explicit
maximum-range detonation separately. When there is no explicit range/timer and
minimum velocity permits it, the zero-lifetime projectile can disappear at
the final-speed condition (`source/items/projectiles.c:822-864`). The visible
range/damage transition is thus an interplay among tag range, derived
coefficient, final speed, and the source's disappearance condition—not a simple
“delete at air upper distance” rule.

On collision, CE normalizes the candidate velocity and computes
`clamp((speed - final_velocity) / (initial_velocity - final_velocity), 0, 1)`
when initial and final speeds differ (`source/items/projectiles.c:1501-1543`).
This factor is passed into `damage_data` only when the projectile has an
`impact_damage` reference and the collision is an object
(`source/items/projectiles.c:1545-1555`). The retail fuel-rod projectile has
no such reference, so no direct target damage should occur through this branch
even though its speed changes. Its detonation effect, material response and
effect-driven blast/damage remain separate behavior to audit before declaring
the full fuel-rod attack correct.

The pinned Halo-64 source has the same range coefficient and air/water runtime
selection equations (`submodules/halo-64/source/items/projectiles.c:1171-1188,
1252-1276`). Its air-branch comment labels the water-upper-bound assignment a
known bug preserved for exact matching and notes the corrected alternative;
that is useful evidence of the source quirk, not permission to silently change
the selected Halo CE baseline. Halo-64 also contains N64-only tracer
instrumentation outside these semantics and does not supply a PS2
implementation or authorize N64 gameplay reductions.

## Parity risks for the current port

1. The pack/runtime now preserves both air and water range pairs and water
   gravity, and `shot.c` reselects the environment at the beginning of each
   tick. The source instead discovers media during collision/update work; the
   scene fixture's tick-wide `underwater` boolean does not prove exact
   mid-tick transition ordering or retagging from actual media geometry.
2. `tests/shot_main.c` and `tests/test_shot.py` now assert fuel-rod air/water
   first-tick values, water disappearance at fixture tick 33, and a transition
   after ten air ticks. These are port/source-equation fixture checks, not a
   direct execution of the unchanged CE routine or retail runtime trace.
3. Because impact damage is `NONE`, current projectile hit events must not
   invent a direct damage amount from a zero-valued damage profile. The
   intended blast result depends on detonation/effect/area-damage semantics and
   must be tested through that separate path.
4. The source uses single-precision `real` and advances in fixed simulation
   ticks. The port should not calculate the path using host-only doubles or
   variable elapsed frame time if it expects replay-identical outcomes.

## Fuel-rod detonation/effect chain now assessed

The `proj` tag links to `weapons\\fuel rod gun\\effects\\explosion`; its
impact-damage, attached-detonation-damage, super-detonation,
detonation-started, and flyby-sound refs are null. Thus it is accurate that
direct collision has no impact-damage tag, but incorrect to conclude the
projectile is harmless: its material response can dispatch the linked effect,
whose event parts contain the gameplay damage. The same projectile tag is
referenced by both handheld and Hunter weapon tags.

The extracted explosion effect is deterministic (`flags=0x2`), has runtime
danger radius 8, two locations, one event with zero timing bounds, four parts,
and one particle-system record. Its parts reference primary `jpt!`
`weapons\\fuel rod gun\\explosion`, `pctl` Hunter-fuel-rod explosion,
`snd!` `sound\\sfx\\weapons\\fuel rod gun\\explosion`, and shock-wave
`jpt!` `weapons\\frag grenade\\shock wave`. The primary damage tag has
falloff radius 0.5 and cutoff radius 1.5, damage bounds 40/75/75, area radius
0, flags `0x21` (owner-immunity and detonate-explosives bits in pinned source),
and cyborg-body/shield material modifiers 1.0/1.0. The shock-wave damage tag
has falloff/cutoff 3.5/8 and zero damage. Tag payload evidence supports the
links and values; it does not by itself prove runtime event timing or damage
against a live actor.

In CE, `projectile_detonate` creates the projectile effect with owner context
(`projectiles.c:1337-1498`); effect damage parts create damage data and call
the area-damage path (`effects/effects.c:1738-1760`). The area path gathers
eligible objects, applies owner/team restrictions and line-of-sight/falloff,
then invokes object damage (`objects/damage.c:1929-1963,2507-2595`). For this
tag, the positive-radius damage falloff reaches zero at 1.5 units, with full
scale through 0.5; radius-zero core handling uses the source's direct collision
line path. This is a source-derived interpretation of the fields; exact
per-object final health still depends on actor collision region, shield,
damage material, immunity/team state, and deterministic damage RNG. The
effect's deterministic flag and damage part mean visual culling must never be
allowed to erase gameplay damage. Presentation particles and sound can be
budgeted separately only after the simulation-bearing event is preserved.

Current `play_ee` projectile handling calls direct projectile vitality on the
diagnostic sphere but does not dispatch a `SHOT_DETONATE` event into the
tagged effect or area-damage system. It also does not carry a CE object/team
owner datum through the shot. Therefore fuel-rod movement is better represented
than its actual attack result. Source/tag evidence is sufficient to specify
what the next effect interface must represent; remaining questions are runtime
ordering, source pool exhaustion, effect-update tick, damage-RNG consumption,
target enumeration/occlusion, and actor/vital integration rather than absence
of the blast tag.

## PS2 EE RAM/CPU considerations

This behavior does not justify per-projectile heap allocations or a large
lookup table. Preserve the four range endpoints and the two gravity scales in
the already selected projectile-definition record (or a compact source-order
profile) and compute one coefficient on spawn / on media transition using the
same float operations as the source. A handful of floats per selected weapon
is negligible relative to the 32 MiB plan, but any fixed pool growth must be
counted against the existing projectile-pool and EE BSS budgets; the current
32-entry diagnostic combat pool is fixed (and is not established as a game
high-water capacity). Avoid recalculating the coefficient every tick.

CPU cost is a few float multiplies/divides on spawn or on a rare medium
transition; the per-tick work is already dominated by collision traversal and
should remain bounded by the existing maximum collision iterations. The
port's single precision and exact operation order should be retained; a
precomputed reciprocal is only acceptable after proving it preserves the
reference tolerance and state hash. No PCSX2 or physical-EE performance claim
follows from this source/tag analysis.

## Expanded all-weapon tag/source audit (23 paths)

The following inventory resolves retail trigger→projectile links, magazine
records, projectile direct-damage/effect/audio refs, and the current port
boundary. Tag references were resolved by tag ID across the supplied extracted
maps using the bounds-checked reader and the layouts in
`tools/play_weapons.py`. Source structure is pinned
`halo-ce-universal` (`weapon_definitions.h:112-165`,
`projectile_definitions.h:45-105`); CE trigger creation/origin/owner selection
is in `source/items/weapons.c:2373-2588`, firing/state code in
`weapons.c:2600-2760`, and projectile flight/impact/effect dispatch in
`projectiles.c:521-864,1110-1210,1337-1614,1786-1846`. Matching
`halo-64` routines were used only as a portable-source cross-check. Retail tag
links have high confidence; source-to-port assessments are code inspection,
not runtime parity results.

| # | Weapon path | Trigger → projectile; loaded/total | Direct damage / projectile effect | Scope; current status and gap |
|---:|---|---|---|---|
| 1 | `weapons\\pistol\\pistol` | primary → `weapons\\pistol\\bullet`; 12/60 | impact `weapons\\pistol\\bullet`; effect null; bullet flyby | Handheld. Basic EE camera shot and projectile/vitality smoke exist; not full firing-effect/audio, actor-region, or CE effect parity. |
| 2 | `weapons\\assault rifle\\assault rifle` | primary → `weapons\\assault rifle\\bullet`; 60/240 | impact same-named; effect null; bullet flyby | Handheld automatic. Host cadence/ammo and generic shot exist; full EE trigger-state, actor collision/damage and audiovisual dispatch remain. |
| 3 | `weapons\\shotgun\\shotgun` | primary → `weapons\\shotgun\\pellet`; 12/24 | impact same-named; effect null; 15 projectiles/shot | Handheld. Cone/distribution equation has host coverage; integrated 15-pellet collision/damage, shell insertion/reload animation parity remain. |
| 4 | `weapons\\sniper rifle\\sniper rifle` | primary → `weapons\\sniper rifle\\sniper bullet`; 4/12 | impact same-named; effect null; bullet flyby | Handheld latched. Tag/profile exists; zoom, actor-region/headshot attribution, penetration and trigger release parity remain. |
| 5 | `weapons\\rocket launcher\\rocket launcher` | primary → `weapons\\rocket launcher\\rocket`; 2/4 | impact null; effect `weapons\\rocket launcher\\effects\\rocket explosion` | Handheld explosive. Effect-driven AoE/owner filtering and sound/visual dispatch are absent from generic shot runtime. |
| 6 | `weapons\\plasma pistol\\plasma pistol` | primary → `weapons\\plasma pistol\\bolt`; secondary → `weapons\\plasma rifle\\charged bolt`; no magazine | impact refs same-named; primary effect null, charged effect `weapons\\plasma rifle\\effects\\detonate`; plasma flyby | Handheld dual-trigger charge/overcharge. Bounded host pair and selected EE dispatch exist; charged projectile/effect, full heat, failure and runtime parity remain. |
| 7 | `weapons\\plasma rifle\\plasma rifle` | primary → `weapons\\plasma rifle\\bolt`; no magazine | impact same-named; effect null; plasma flyby | Handheld heat weapon. Host heat/cadence components exist; overheat, misfire/RNG, effect and full EE state remain incomplete. |
| 8 | `weapons\\needler\\needler` | primary → `weapons\\needler\\needle`; 20/80 | impact `weapons\\needler\\impact damage`; attached `weapons\\needler\\detonation damage`; effects `weapons\\needler\\effects\\needle detonate` and `...\\explosion`; flyby linked | Handheld guided/attach/combine. Do not duplicate: see [Needler audit](combat-needler-audit.md), which identifies guidance, attachment/fuse, supercombine and attached damage as gaps. |
| 9 | `weapons\\flamethrower\\flamethrower` | primary → `weapons\\flamethrower\\flame`; 100/600 | direct impact null; effect `weapons\\flamethrower\\effects\\flame detonation` | Handheld continuous flame. Persistent contact/area cadence, waste-ammo/heat behavior, effect and sound are not represented by generic shot. |
| 10 | `weapons\\fuel rod gun\\fuel rod` | primary → `weapons\\fuel rod gun\\fuel rod`; 4/12 (round cost zero) | direct impact null; effect `weapons\\fuel rod gun\\effects\\explosion` | Handheld charged explosive. Deep dive above covers flight; collision-driven media crossing, effect/AoE execution, ownership and audio remain. Potential-response fields/selection are now packed and implemented, but still need integrated material-ID and effect-path fixtures. |
| 11 | `weapons\\gravity rifle\\gravity rifle` | primary → borrowed `weapons\\flamethrower\\flame`; 200/200 | flame effect `weapons\\flamethrower\\effects\\flame detonation`; direct impact null | Handheld using shared flame projectile. Selection/render/profile is not proof of gravity-rifle behavior; flame damage/effect integration is absent. |
| 12 | `weapons\\energy sword\\energy sword` | no triggers, projectile, or magazine | no projectile refs | Melee weapon. CE uses unit melee (`source/units/units.c:8857-9136`); synthetic melee smoke is not sword lunge/state/arbitration/animation/damage/effect parity. |
| 13 | `weapons\\flag\\flag` | no trigger/projectile/magazine | none | Objective item, not gun. Carry/attach/drop/scoring interfaces are outside current play actor runtime. |
| 14 | `weapons\\ball\\ball` | no trigger/projectile/magazine | none | Objective item, not gun. Carry/attach/drop/scoring interfaces are outside current play actor runtime. |
| 15 | `weapons\\fuel rod gun\\hunter fuel rod` | primary → shared `weapons\\fuel rod gun\\fuel rod`; no magazine | shared fuel-rod effect; impact null | AI/character weapon. Shared projectile data has high confidence; AI cadence/aim/owner/difficulty and infinite-ammo behavior need actor/AI interfaces. |
| 16 | `characters\\sentinel\\sentinel` | primary → `characters\\sentinel\\beam`; no magazine | impact same-named; projectile effect null | Character/AI beam. Requires Sentinel origin, aiming and beam update path; camera-origin player dispatch is not equivalent. |
| 17 | `vehicles\\warthog\\warthog gun` | primary → `vehicles\\warthog\\bullet`; no magazine | impact same-named; effect null | Mounted. CE marker origin/owner depends on vehicle gunner; EE deliberately rejects mounted-origin trigger pending vehicle/mount support. |
| 18 | `vehicles\\ghost\\ghost gun` | primary → `vehicles\\ghost\\ghost bolt`; 50/300 | impact same-named; effect null | Mounted, magazine/chamber. Vehicle seat/origin, owner, actor collision and sound/effects remain unsupported. |
| 19 | `vehicles\\scorpion\\scorpion cannon` | primary → `vehicles\\scorpion\\tank shell` (magazine 1/9999); secondary → `vehicles\\scorpion\\bullet` (magazine index -1) | shell impact null/effect `vehicles\\scorpion\\shell explosion`; secondary impact same-named/effect null | Mounted dual trigger. Origin is blocked; shell AoE/effect and secondary trigger routing are separate gaps. |
| 20 | `vehicles\\banshee\\banshee gun` | primary → `vehicles\\banshee\\banshee bolt` (magazine index -1); secondary → `vehicles\\banshee\\banshee fuel rod` (magazine 1/9999) | primary impact same-named/effect null; secondary impact null/effect `vehicles\\banshee\\fuel rod explosion` | Mounted dual weapon. Origin, secondary ammo/effect semantics, blast and audio remain open. |
| 21 | `vehicles\\wraith\\wraith mortar` | primary → `vehicles\\wraith\\wraith mortar`; 10/50 | impact null; effect `vehicles\\wraith\\effects\\wraith mortar explosion` | Mounted explosive. Vehicle muzzle, ballistic collision, AoE/owner and effect/audio execution are absent. |
| 22 | `vehicles\\c gun turret\\c gun turret gun` | primary → `vehicles\\c gun turret\\c gun turret`; no magazine | damage tag `vehicles\\c gun turret\\bolt`; effect null | Mounted/character turret. Origin, owning actor, damage material and firing/audio dispatch remain. |
| 23 | `vehicles\\c_dropship\\cd_gun\\cd gun turret gun` | primary → shared `vehicles\\c gun turret\\c gun turret`; no magazine | shared C-gun bolt damage tag; effect null | Dropship-mounted. Shares projectile, not vehicle/seat lifecycle; no dropship actor/mount interface exists in the play path. |

### Per-path trigger, firing-mode, charge and heat properties

This second all-path crosswalk makes the behavior-bearing trigger fields
explicit; values are retail tag floats/counts, not observed rates from a retail
run. `RPS` is initial→final rate of fire in shots/second, `cost` is rounds per
shot, `pellets` is projectiles per shot, and the charge column is charge time /
charged duration in seconds. “Heat/rnd” is per-trigger heat generated. Source
field layout is `weapon_trigger_definition` in
`source/items/weapon_definitions.h:112-165`; trigger cadence, charge, ammo and
heat transitions are in `source/items/weapons.c:1935-1975,2600-2760,2847-2962,
3016-3390`. Weapon-level secondary modes are enum values in `weapons.c:289-296`
(0 normal, 1 slaved to primary, 2 inhibits primary, 3 alternate ammo, 4
multiple primary ammo). The present 23-tag set has only Banshee mode 2. These
values explain why “magazine absent” does not imply the path is ordinary
unlimited fire: charge/heat, `uses_weapon_origin`, projectiles-per-shot and
weapon-mode rules remain distinct.

| # | Weapon | Trigger profile (primary; secondary when present) | Additional state / applicable gap |
|---:|---|---|---|
| 1 | Pistol | RPS 3.5→3.5; cost 1; 1 projectile | Ordinary fixed-rate, single-round clip weapon; firing effect/region damage remain. |
| 2 | Assault rifle | 15→15; cost 1; 1 projectile | Automatic fixed-rate; age/cadence and muzzle/audio parity remain. |
| 3 | Shotgun | 1→1; cost 1 shell; 15 projectiles | Fan is one trigger shot with 15 independent projectiles; shell reload is not 15 ammo. |
| 4 | Sniper rifle | 2→2; cost 1; 1 projectile | Latched trigger flag; zoom, unzoomed-error, region/penetration and release behavior need a retail trace. |
| 5 | Rocket launcher | 0.5→0.5; cost 1; 1 projectile | Latched explosive shot; projectile impact is null and blast comes from linked effect. |
| 6 | Plasma pistol | Primary 0→0; cost 0; charge 0.6 s, charged 45 s; heat/rnd 0.16. Secondary: charged plasma bolt, heat/rnd 1.0; flag word `0x4` (partial-ammo flag) | No ammo magazine; weapon heat thresholds both 1.0, heat loss 0.65/s. The high charged duration and secondary’s full heat make release/overheat ordering material; the partial-ammo flag has no magazine to operate on. |
| 7 | Plasma rifle | 7→10; cost 0; heat/rnd 0.08 | Heat threshold 1.0, loss 0.3/s; no magazine. Host heat model does not establish complete source heat/misfire/effect ordering. |
| 8 | Needler | 3→10; cost 1; 1 projectile | Rate ramps; guided/attachment/combine state is separately audited in Needler report. |
| 9 | Flamethrower | 15→15; cost 1; heat/rnd 0.04125 | Heat threshold 1.0, recovery threshold 0.0, loss 0.475/s; trigger flag `0x800` is `projectiles_cannot_be_aimed`, not the discharging-spews bit. Repeated persistent flame/contact is not equivalent to one shot per tick. |
| 10 | Fuel rod gun | 10→10; cost 0; charge 1.25 s; 1 projectile | Retail tag has 4/12 rounds but trigger cost zero; charge timing and actual ammo decrement must be observed in the correct CE runtime path. |
| 11 | Gravity rifle | 30→30; cost 1; 1 projectile | Borrows flamethrower flame projectile but fires at 30/s in tag; this is a distinct trigger profile from flamethrower and needs persistent contact parity. |
| 12 | Energy sword | no trigger | Melee only; use unit melee path and sword tag link, not a zero-rate gun. |
| 13 | Flag | no trigger | Objective carry/melee/scoring path, not a gun. |
| 14 | Ball | no trigger | Oddball carry/melee/scoring path, not a gun. |
| 15 | Hunter fuel rod | 10→10; cost 0; charge 1.25 s; 1 projectile | Shares fuel-rod projectile but separate AI weapon/root; AI target/aim/difficulty/owner behavior missing. |
| 16 | Sentinel | 30→30; cost 0; 1 beam projectile | Weapon-origin actor beam; not player camera fire; beam lifetime/AI aim and collision cadence absent. |
| 17 | Warthog gun | 8→15; cost 0; 1 projectile | Rate accelerates and uses mount origin; no vehicle/seat/owner simulation. |
| 18 | Ghost gun | 5→6; cost 1; 1 projectile | Weapon-origin + identical-projectile-error flags; 0.3 s chamber tag; vehicle ammo/chamber not run in player path. |
| 19 | Scorpion cannon | Primary tank shell 0→0; cost 1; 1 projectile; secondary bullet 15→15; cost 1; 1 projectile | Primary latched + weapon-origin and selects magazine 0 (1/9999); secondary magazine index -1. Mode 0 normal; both are mount-marker paths. |
| 20 | Banshee gun | Primary bolt 5→6; cost 1; 1 projectile; secondary fuel rod 0→0; cost 1; 1 projectile | Both use weapon origin; mode 2 inhibits primary. Primary magazine index -1; secondary selects magazine 0 (1/9999), with its own 0-rate trigger. |
| 21 | Wraith mortar | 0.5→0.5; cost 1; 1 projectile | Weapon-origin explosive, 0.3 s chamber; blast effect/owner and mount path absent. |
| 22 | C-gun turret | 4→5; cost 0; 1 projectile | Heat threshold/recovery 1.0, loss 0.1/s; weapon-origin + identical-error flags. Needs turret owner/cadence and beam/projectile runtime. |
| 23 | Dropship C-gun | 8→10; cost 0; 1 projectile | Same projectile and heat settings as #22 but different rate; not safe to collapse its trigger profile or mount lifecycle into the C-gun turret. |

The vehicle weapon roots' `ai_firing_parameters` refs are `actv` actor
variants, which CE `actor_combat_get_firing_parameters` resolves to ranged
combat burst geometry and separate berserk/new-target/moving firing patterns
(`source/ai/actor_combat.c:456-510`; actual attack/control use in
`actor_combat.c:594,1237,2393`). Supplied tag references map as follows:

| Weapon root | AI firing-parameter actor variant |
|---|---|
| Warthog gun | `vehicles\\warthog\\warthog gunner` |
| Ghost gun | `vehicles\\ghost\\ghost pilot` |
| Scorpion cannon | `vehicles\\scorpion\\scorpion pilot` |
| Banshee gun | `vehicles\\banshee\\banshee pilot` |
| Wraith mortar | `vehicles\\wraith\\wraith pilot` |
| C-gun turret | `vehicles\\c gun turret\\c gun turret gunner` |
| Dropship C-gun | `vehicles\\c_dropship\\cd_gun\\cd gun turret gunner` |

This is a source/tag-verified relation, not a claim that a player-controlled
vehicle uses all AI burst behavior. Static tags show different pilot/gunner
variants, so AI firing profile must not be replaced by vehicle trigger RPS
alone. The port currently has none of these actor-variant selections, vehicle
seats, burst loops or owner assignment; AI firing needs bounded target and
burst work under PS2 CPU limits.

An additional all-root pass checked `weapon.ai_firing_parameters` at
`_weapon_definition` +0xB4 (`weapon_definitions.h:188`; weapon-tag root
+0x3BC): it is null for roots #1-16, including Hunter fuel rod and Sentinel,
and non-null for all seven mounted
roots #17-23 (the crosswalk above). This does not mean Hunter/Sentinel AI has
no actor firing parameters. In CE, `actor_combat_get_firing_variant_definition`
uses the weapon-linked `actv` override when present and otherwise falls back
to the actor's own variant (`source/ai/actor_combat.c:438-461`). The supplied
Hunter and Sentinel variants resolve that fallback as follows:

| AI weapon / actor variant tags | `ranged_combat.reference` | Verified combat values | Port interpretation / gap |
|---|---|---|---|
| Hunter / `characters\\hunter\\hunter` and `...\\hunter major` | `weapons\\fuel rod gun\\hunter fuel rod` | Max range 20; actor ROF 0; first-burst delay 1.0–1.5 s; combat range 2.5–3.0; target tracking 0.5, lead 0.25, manual weapon-damage modifier 0.5; burst duration 2 s and separation 1.75–2.25 s | The firing variant references the separate Hunter `weap`, whose primary trigger is 10/s with 1.25-s charge and zero rounds per shot. Actor ROF 0 takes CE's immediate-trigger branch; weapon charge/rate still remains a separate state. No actor aim/origin/charge/owner service in current EE path. |
| Sentinel normal / `characters\\sentinel\\sentinel` | `characters\\sentinel\\sentinel` | Max range 12; actor ROF/error 0; first delay .25–.75 s; combat range 5–8; tracking/lead .5/.5; burst radius .5, angle 60°, return length .8–1.1, burst .8–1.2 s, separation 1–1.5 s | Actor firing/burst profile is distinct from the Sentinel weapon root's 30/s trigger and beam material response. EE has neither actor target selection nor beam lifetime/origin. |
| Sentinel major / defensive and shielded variants | Same Sentinel `weap`; major actor ref changes to `characters\\sentinel\\sentinel_defensive` | Same 12 range, .25–.75 s first delay and 5–8 combat band; burst radius .35, angle 30°, duration 1.2–1.6 s, separation .8–1.2 s (the non-major version uses .5 radius/60°, .8–1.2 s and 1–1.5 s) | Variant selection changes combat burst geometry even though the weapon root/projectile is shared; actor-variant selection must not be collapsed into the weapon trigger record. |

These actor/variant references and values are present in supplied `b30.map`,
`c10.map`, and `d40.map`; CE structure offsets are asserted in
`source/ai/actor_definitions.h:318-415` and `source/ai/actor_perception.c:910-986`.
CE actor combat applies team difficulty to nonzero actor ROF, optional firing-
pattern rate modifier, then derives trigger delay, while a zero rate directly
sets the primary trigger (`actor_combat.c:1300-1317,2370-2405`). For PS2 these
are tag-resident constants, not grounds for running whole AI combat in every
shot: keep variant IDs/data immutable and actor target/burst iterations fixed
and bounded. Exact encounter variant selection, target order and difficulty
random draws still require scenario/actor runtime evidence.

The seven already-listed vehicle gunner/pilot variants were also checked for
their ranged-combat numeric profiles (in addition to resolving their `actv`
IDs). Values are tag observations, not proof an AI occupant is instantiated
in every vehicle scenario. Angles are radians in the tag; the degree values
below are for readability.
The representative records came from `b30.map` for Warthog, Ghost, Banshee,
both C-guns, and Hunter; `c10.map` for Sentinel; `a10.map` for Scorpion; and
`a50.map` for Wraith. Repeated occurrences in the other multiplayer maps were
consistent in the fields compared.

| Weapon-associated `actv` | Max range; actor ROF / error | First delay; new-target time; combat range | Tracking / lead / damage modifier | Burst geometry (origin radius / angle; duration; separation) |
|---|---|---|---|---|
| Warthog gunner | 20; 0 / 0 | .5–.75 s; 4 s; unset | 1 / 0 / 0 | .4 / 30°; 1.8–2.4 s; .8–1.0 s |
| Ghost pilot | 16; 8 / 1° | .5–1.5 s; 10 s; 7–10 | .7 / .7 / .5 | .4 / 20°; .35–.6 s; .75–1.25 s |
| Scorpion pilot | 70; .5 / 1° | 4–6 s; 15 s; 25–35 | 1 / 0 / .5 | 0 / 0°; .1 s; 4–6 s |
| Banshee pilot | 35; 4 / 1° | 0; 1 s; 25–50 | 1 / .8 / .5 | .4 / 20°; 1–1.25 s; .6–.8 s |
| Wraith pilot | 140; .5 / 1° | 4–6 s; 15 s; 25–70 | 1 / 0 / .5 | 0 / 0°; .1 s; 4–6 s |
| C-gun turret gunner | 50; 8 / 0 | .5–2 s; 10 s; unset | .3 / .8 / .333 | .75 / 0°; 1.5–2.5 s; 3–6 s |
| Dropship C-gun gunner | 25; 8 / 0 | .5–2 s; 10 s; unset | .3 / .8 / .333 | .75 / 0°; 1.5–2.5 s; 3–6 s |

The variant-specific `new target / moving / berserk` tuples are also part of
the static behavior profile; each tuple is (burst-duration multiplier,
burst-separation multiplier, rate-of-fire multiplier, error-angle multiplier)
and a zero means that modifier is not applied by the source's `> 0` tests:
Warthog `[(1.5,0,0,0),(0,0,0,0),(0,0,0,0)]`; Ghost and Banshee
`[(.75,1.5,1,2),(.75,1,0,2),(2,.5,1.25,5)]`; Scorpion and Wraith
`[(0,0,0,5),(0,0,0,0),(0,0,0,0)]`; both C-guns
`[(0,0,.5,2),(0,0,0,0),(0,0,0,0)]`. Hunter has new-target
`(0,0,0,2)` and moving `(2,2,0,2)`; Sentinel normal/defensive/shielded has
new-target `(1.5,.75,0,0)`, moving `(.5,1.5,.75,0)`, while major variants use
moving `(.75,1.25,0,0)`. CE selects berserk, new-target or moving pattern
before deriving actor burst/trigger behavior (`actor_combat.c:466-510`); these
are not weapon tag firing-effect records.

`actor_ranged_combat_properties` offsets are asserted/declared in
`source/ai/actor_definitions.h:318-415`; the weapon/variant selection and
trigger-delay rules are in `actor_combat.c:438-461,1300-1317,2370-2405`.
Notably, Warthog actor ROF 0, Scorpion 0.5/s, and Wraith 0.5/s differ from
the corresponding weapon tags (8→15/s, shell 0 RPS plus chamber, and .5/s),
while C-gun actor ROF 8/s differs from its 4→5/s weapon root. CE layers actor
burst/difficulty control over the weapon trigger state; these two rates must
not be substituted for each other or flattened into one `gun_def`. On the EE,
the AI/mount simulation is not present, so these rows are static reference
data only. They show why a future AI port needs per-variant immutable profiles
and capped target/burst loops rather than one per-projectile compatibility
branch.

For the nontrivial flag set, CE defines `latched`, `uses_weapon_origin`,
`projectiles_cannot_be_aimed`, and `projectiles_have_identical_error` in
`weapon_definitions.h:47-63`. In the extracted set these matter to sniper,
rocket, fuel rod, flamethrower, Ghost, Scorpion, Banshee, Wraith and both
C-guns. The flamethrower flag is projectiles-cannot-be-aimed, not
`discharging_spews`. The EE camera path intentionally rejects weapon-origin
triggers, so mounted/AI entries above are tag/source audit results only. Current `gun.c`
implements a bounded approximation for ordinary single-trigger rate/ammo,
heat, latch and charge; the entries above expose which paths require either
dual-trigger, mounted-origin, persistent-flame/beam, or actor-specific source
semantics instead. Exact parity remains to be established through source-order
fixtures and, where actor/mount/effect services are absent, is explicitly
blocked rather than inferred from tag values.

### Weapon-by-weapon CE behavior and parity findings

The matrix below joins each distinct XISO weapon root to its distinctive
source-side state path and the tag facts that determine it. Shared CE trigger
and projectile primitives are cited once in the surrounding sections; this
matrix records the per-root specialization so the 23-path list is not mistaken
for a behavior audit. “Verified” means pinned source or supplied tag, not a
retail runtime capture. Port status is the current M13 code inspection.

| # / root | Weapon-specific CE behavior and tag fact | Current port gap / PS2-facing acceptance point |
|---:|---|---|
| 1 Pistol | Ordinary single-trigger bullet, fixed 3.5/s, one round per shot, 12/60, projectile `weapons\\pistol\\bullet`; weapon function/tag family includes illumination and melee links. Trigger creates the projectile from player aim through `trigger_create_projectiles` (`weapons.c:2373-2588`), then material impact selects jpt!/effect from projectile response (`projectiles.c:1337-1614,1786-1846`). | EE fires the selected camera profile; impact is not full source impact/effect/region processing. Keep one projectile per shot. Test 3.5/s ready/release order, ammo and material-selected damage; avoid per-tick tag traversal. |
| 2 Assault rifle | Automatic 15/s, one round/projectile per shot, 60/240; standard `weapons\\assault rifle\\bullet` impact. Its root function modes include ammo and integrated-light data, which are separate from trigger firing. | Host cadence/ammo and basic EE shots exist; not full continuous light/effect/audio or actor damage. Test exact 15/s trigger phase and 60-round depletion; cap at one projectile/tick. |
| 3 Shotgun | One 1/s trigger event consumes one shell and creates 15 `weapons\\shotgun\\pellet` projectiles via tag distribution; each pellet independently follows material-response/direct-damage processing. CE distribution occurs after trigger error sampling (`weapons.c:2533-2556`). | Host cone/distribution fixtures exist, but integrated 15 collision/damage traces, first/last-shell reload animation choice and per-pellet effects are not complete. Fifteen collisions per shot are a deterministic EE budget ceiling to account for; test all pellets under fixed seed and fixed target geometry. |
| 4 Sniper rifle | Fixed 2/s one-projectile trigger is latched and has zoom/unzoomed-error flags; projectile is `weapons\\sniper rifle\\sniper bullet`. Source uses trigger latched/released state (`weapons.c:1972-1975,3240-3252`); root has zoom/function metadata and the impact tag is separate from actor hit-region selection. | No zoom/reticle/view-state or source head/body region pipeline in the combat probe. Test trigger latch until release, zoom-state cone, region damage and collision ordering; keep high-damage effects behind explicit actor classification. |
| 5 Rocket launcher | 0.5/s latched explosive, one rocket, 2/4 magazine; projectile impact_damage is null while `weapons\\rocket launcher\\effects\\rocket explosion` supplies detonation/blast behavior. | Projectile profile exists, but detonation effect/AoE owner/team filter not integrated. Test direct impact does not apply fabricated direct damage, blast executes once, and nearby-target query is bounded. |
| 6 Plasma pistol | Two trigger records, normal secondary mode: primary uncharged bolt has 0.6-s charge and 0.16 heat/shot; secondary charged bolt has heat/shot 1.0 and links plasma detonate effect; weapon heat cap/recovery 1.0 and loss .65/s, no magazine. Source distinguishes primary fire-before-charge, release-charge and secondary projectile dispatch (`weapons.c:2847-2962,3135-3390`). | Host pair covers selected charge/release logic and EE dispatches selected triggers, but heat transition/effect/overheat sequence is not source-complete. Test tick order through charge, release, overheat and cooldown; no ammo-mag state or allocation. |
| 7 Plasma rifle | Single automatic heat weapon ramps 7→10/s, cost 0, heat .08/shot, cap/recovery1.0, loss .3/s; separate overheat effect and no magazine. | Host heat/cadence model exists; misfire/RNG, overheat effect, heat visual, and function-value evaluation absent. Test cap/recovery and seeded overheat transition; bounded one projectile per tick. |
| 8 Needler | 3→10/s ramp, 20/80; projectiles carry guided angular velocity, attach/detonation damage links and supercombine/effect paths. Its detailed source/tag state is covered in [`combat-needler-audit.md`](combat-needler-audit.md). | Reconcile that audit: target acquisition, full >2-unit wander, attachment/combine damage/effects remain. Bound target scan and active needle pool; do not re-audit or merge the separate Needler findings here. |
| 9 Flamethrower | 15/s one flame trigger projectile per event, 100/600 waste-round magazine, .04125 heat/shot, cap1/loss.475/s; linked flame detonation effect. Trigger bit `0x800` means projectiles cannot be aimed. This tag profile is not semantically a single ballistic pellet: continuous flame/contact and heat/function inputs matter. | Generic projectile hit cannot implement contact cadence, damage duration, waste-mag refill, heat effects or audio. Test stable contact over ticks and bounded flame/effect work; never use unbounded particles as gameplay projectiles. |
| 10 Fuel rod | 10/s nominal rate plus 1.25-s charge, trigger rounds-per-shot zero despite 4/12 tag magazine; shared Hunter projectile; no direct impact damage, effect-linked explosive, air/water deceleration and material potential records (deep dive above). Source order for charge and projectile processing is cited above. | Flight/POT data exists but effect/AoE, actual ammo semantics, collision-driven media change, and owner filtering remain. Test held/released charge and round count against CE trace before deciding the 4/12 tag is gameplay ammo; cap blast actors/projectile collision work. |
| 11 Gravity rifle | Single 30/s one-round trigger with 200/200 magazine profile, but projectile ref borrows `weapons\\flamethrower\\flame`; this differs sharply from flamethrower's 15/s and 100/600 heat/waste profile. | Tag reuse is verified, behavior equivalence is not. Test gravity-rifle cadence, collision/contact, ammo and damage separately from flamethrower; if it creates a persistent field, model it with bounded fixed slots rather than per-tick allocations. |
| 12 Energy sword | No `weapon_trigger_definition`, magazine or projectile; root references melee damage `weapons\\energy sword\\melee` but no weapon melee response. CE routes player attacks through unit melee arbitration, collision, damage and response timing (`units.c:8857-9180,9279-9285`). | Current synthetic melee is not sword lunge/target arbitration/timing/animation. Test range, lunge and response against source; bounded target candidates and no projectile-pool cost. |
| 13 Flag | No firearm trigger; objective root links melee damage and melee-response, and its weapon identity is checked by `weapon_is_flag` (`weapons.c:731`). CTF pickup/drop/carrier/scoring uses game-mode callbacks. | No carrier/team/CTF scoring lifecycle. Test pickup, attach, drop/reset, flag melee and scoring as objective state, not ammo. |
| 14 Ball | No firearm trigger; Oddball root has melee damage/response and game-mode transfer/score behavior separate from flag. | No carrier/transfer/score loop. Test pickup, transfer, scoring and reset; fixed one-carrier state and no projectile allocation. |
| 15 Hunter fuel rod | AI weapon root has 10/s + 1.25-s charge, zero round cost, no finite magazine/FP graph, and shares the handheld fuel-rod projectile/effect/material data. CE AI source chooses actor aim/origin and firing profile rather than player camera (`weapons.c:2373-2517`; actor firing path in `actors.c`). | Shared projectile data does not grant player-fire parity: actor target, difficulty, charge, ammo and owner are missing. Test AI-specific charge/aim/launch separately; keep actor candidate search bounded. |
| 16 Sentinel | Character weapon, 30/s, no finite magazine, projectile `characters\\sentinel\\beam` with material-specific default effects and potential reflection records. Weapon origin and actor aim are required. | No Sentinel actor origin/beam lifetime/update in camera shooter. Test AI beam target/update and material reflection separately; bound per-tick beam segments/collision work. |
| 17 Warthog gun | Vehicle trigger accelerates 8→15/s, no finite magazine; projectile `vehicles\\warthog\\bullet`, weapon-marker origin and vehicle gunner owner context. | Current camera path rejects origin weapon. Test gunner seat/marker/owner before firing; one projectile per tick max at tag cadence; defer vehicle pools to explicit PS2 budget. |
| 18 Ghost gun | Mounted bolt accelerates 5→6/s, 50/300 rounds, magazine must be chambered (0.3-s tag chamber), uses weapon origin and identical-projectile-error flag. Projectile impact is direct damage, not an explosive effect. | No vehicle/mount state. Test chamber-gated cadence, marker origin, target-owner exclusion and ammo depletion; do not use player eye fallback. |
| 19 Scorpion cannon | Two origins/triggers: primary latched tank shell at magazine0 (1/9999, 4-s chamber, 0-RPS tag rate) and secondary bullet at magazine index -1, 15/s; weapon secondary mode normal. Shell uses detonation effect with material-specific detonation links; secondary uses separate bullet profile. | Trigger routing/vehicle mount not in EE; a camera proxy cannot prove shell timing. Test primary chamber/latched order and independent secondary fire, ammo routing and shell AoE under mounted source; fixed one-shell/effect event pools. |
| 20 Banshee gun | Two weapon-origin triggers; mode2 secondary inhibits primary. Primary bolt 5→6/s, magazine index -1; secondary fuel rod has 0-RPS tag rate and magazine0 (1/9999), with its own explosive/effect links. | No aircraft seat/origin, mutually inhibiting trigger timing, or secondary explosive. Test inhibition/release and per-mode ammo/projectile path; bound dual-trigger state and effect/audio concurrency. |
| 21 Wraith mortar | 0.5/s mounted explosive, cost1, 10/50 magazine, 0.3-s chamber; null direct impact damage, `wraith mortar explosion` effect. | No vehicle marker/ballistic mount/AoE/effect path. Test chamber timer and one detonation; cap ballistic collision loops and nearby blast candidates. |
| 22 C-gun turret | Turret trigger accelerates 4→5/s, cost0, weapon origin, identical-error flag; heat threshold/recovery1.0 and loss.1/s; references shared turret projectile and `vehicles\\c gun turret\\bolt` damage. | No actor/vehicle mount or heat/effect services. Test heat gating and target-relative error under actual owner; bound repeated projectile and impact queries. |
| 23 Dropship C-gun | Separate weapon root uses same C-gun projectile and heat values but 8→10/s trigger rate and dropship mount/owner. It is not numerically identical to the stationary/turret C-gun. | No dropship actor/seat lifecycle. Test distinct rate and owner context before sharing only projectile/damage data; do not alias trigger profile or allocate unbounded vehicle simulation. |

Per-weapon evidence for projectile material profiles and linked direct/attached
damage/effect refs is in the 23-path crosswalk and material response tables
above. Those tables distinguish (a) direct impact damage, (b) attached damage,
(c) material response/detonation effects and (d) weapon-level effect tags. A
null in one category must not be filled with a value from another. In all
cases, RAM/CPU conclusions are budget constraints and bounded test proposals,
not measured physical EE performance; console qualification remains a later
gate.

### Source comparison: pinned CE versus Halo-64

Halo-64 provides a portable-source comparison for each major family here, but
it is not a substitute for the supplied retail tag values or a retail Xbox
runtime trace. The matching routines reviewed are:

| Behavior family | halo-ce-universal | Halo-64 | Cross-check result / limitation |
|---|---|---|---|
| Trigger cadence, charge/release, projectile creation, alternate-trigger ordering | `source/items/weapons.c:1935-1975,2373-2588,2600-2760,2847-2962,3016-3390` | `source/items/weapons.c:1739-1780,2157-2390,2393-2785,2938-3139` | Both retain tag-driven trigger profiles and explicit source state transitions. This supports Halo-64 as a source-structure comparison; it does not resolve missing actor/mount services or prove retail frame hashes. |
| Magazine reload, chamber and animation timer | `source/items/weapons.c:1351-1428,1524-1595,1713-1755` | `source/items/weapons.c:1222-1295,1382-1418,1565-1598` | Both use animation graph frame counts for reload and a separate chamber timer; not `MAG2.reload_time`. This directly rules out tag seconds as a parity timer. |
| Projectile flight, deceleration, collision, potential response and detonation | `source/items/projectiles.c:680-730,1110-1128,1169-1270,1337-1614,1786-1846` | `source/items/projectiles.c:680-730,1171-1254,1340-1682,1800-1860` | Both expose air/water deceleration and material-response stages. Halo-64 potential selection includes the unit-only flag and seeded response path; local port still needs equivalent surface classification, effect dispatch and collision-driven medium updates. |
| Melee and grenade release | `source/units/units.c:4482-4545,8857-9180,11837-11928` | `source/units/units.c:4310-4368,8573-8788,11092-11190` | Similar unit-side arbitration, throw-state, actor/player origin and velocity composition; neither source tree supplies this port's actor/mount runtime. |
| Sound payload/codec | `source/sound/sound_manager.c:298-317`, `source/sound/sound_dsound_xbox.c:2079-2162` | Xbox audio implementation in `source/sound/` | Source confirms Xbox ADPCM is an Xbox format path. It does not provide a PS2 decoder or EE voice/mix timing; codec conversion remains a platform service, not a weapon-family behavior approximation. |

Where exact source-to-source semantics appear aligned, this report records the
common algorithm, not an assertion that all Halo-64 differences are absent.
Retail-derived trigger and projectile tag fields remain the numeric oracle;
dynamic events (target choice, vehicle ownership, random-state advancement,
collision ordering and audiovisual effects) require fixtures/runtime
interfaces that are not in the current play harness.

### Thrown grenades (outside the 23 `weap` paths)

The supplied all-map index also contains `eqip` roots
`weapons\\frag grenade\\frag grenade` and
`weapons\\plasma grenade\\plasma grenade`; their projectile/material data is
not a firearm trigger and therefore must not be lost by calling the 23-root
weapon list exhaustive for combat. CE stores grenade-type inventory on the
unit, constrains pickup against the scenario `game_globals_grenade` maximum,
and selects/throws through the unit animation state rather than a weapon
magazine (`source/units/units.c:2024-2177,4482-4545,11837-11928`). Release
uses actor grenade aiming for AI or the player camera/grenade-origin offsets,
then adds the unit's translational velocity and applies premature-throw power
scaling (`units.c:11837-11923`). The projectile update controls whether the
fuse starts immediately, on first bounce, or only after rest; countdown action
is distinct from direct impact damage (`source/items/projectiles.c:680-730`).
The portable Halo-64 unit/projectile copies contain corresponding inventory,
throw-release and projectile timer paths; the source-level order is useful for
porting but still needs retail trace confirmation for exact actor/object
ordering.

The extracted tag tests record two types: frag has 0.5-s fuse, 1.5-unit blast
falloff and 2.5-unit cutoff; plasma has 2-s fuse, 0.5-unit falloff and 2-unit
cutoff. Both link 80 minimum / 120 maximum blast damage in the supplied
profile; the projectile timer-start enums are 1 for frag and 2 for plasma
(`after_first_bounce` and `when_at_rest`, respectively; enum definition at
`source/items/projectiles.c:188-197`, tag enum at projectile base +4). Note
the CE/Halo-64 switch at `projectiles.c:700-709` has no `break` after the
first-bounce case, so it falls through and the final condition is
`stopped_after_collision`; the effective source condition is therefore
rest-after-collision for both modes in these source trees, not a simple “any
collision starts frag fuse” rule. This surprising source behavior needs an
instrumented trace before emulating it. Both projectile material 0 records
reflect, with tag-derived separate parallel and perpendicular friction. Frag
has potential reflect at material 28 (angle 0-.5236 rad, speed .0333-33.3333,
skip 0) and potential overpenetrate at 29 (skip .2); plasma potential response
4 is flagged `only_against_units` on 26 material indices, while material 16
potentially reflects with no such flag. The current `src/game/grenade.c`
implements fixed-capacity thrown
grenades, player-eye origin/aim, gravity/collision, fixed seeded fuse RNG,
rest-only countdown, unit-surface stick selection, and bounded AoE profile
damage. It is not yet a CE unit-animation/inventory implementation: pickup
type caps, grenade cycling, interrupted/early release, AI aim, grenade-origin
tag offsets, held-weapon throw blocking, inherited unit velocity, network
ordering and original projectile/effect dispatch are not all represented by
the visible player path. The current implementation uses explicit extracted
profiles in code rather than a general tag-backed grenade/equipment runtime.

PS2-specific constraint: reserve a fixed grenade pool and stable slot order;
do not allocate on throw or detonation. Each active grenade can require a
bounded collision loop (current cap four per tick) and blast candidate scan;
simultaneous events multiply both EE work and audio/effect pressure. Test both
types for pickup/cap, type switch, early/full-power release, velocity inheritance,
surface-dependent bounce/stick, rest-timed fuse, direct-hit versus detonation
damage and simultaneous blasts with fixed seeds. The current player-collision
smoke is not proof of retail unit, AI, or console behavior.

The trigger records generally contain one firing-effect record (two on the
plasma rifle and plasma-pistol trigger pair where applicable); its six optional
tag references resolve null in this extraction. Do not infer that there is no
muzzle flash or firing sound: model markers/animations/functions, projectile
material-response effects, and sound permutations are separate tag systems.
The EE pack now retains bounded firing-effect data and seeded selection state,
but does not execute visual/audio/damage effect references. `weapons.c` resolves
origin from weapon markers, selects owner/team, and distinguishes player aim
from AI (`2392-2517`); the current camera path rejects `uses_weapon_origin`
triggers rather than pretending they are mounted parity.

Weapon-root refs add two non-projectile facts: the energy sword's
`melee_attack_damage` is `weapons\\energy sword\\melee` (matching the melee
tag already noted in `docs/combat.md`), while the flag and ball also each point
to their own `...\\melee` damage tag and `...\\melee_response`. Most handheld
firearms also have family-specific melee damage and response tags; fuel rod,
gravity rifle, Hunter fuel rod, Sentinel, and the mounted weapons tested here
have these refs null. Energy sword's weapon melee-response ref is null, so do
not assume its damage ref by itself describes the full lunge/response state.
Weapon-level `detonation_effect` is null in this inventory; plasma pistol and
plasma rifle instead have `overheated_effect` refs, the pistol/Needler have
ready effects, and mounted weapon tags resolve AI firing-parameter refs to
their gunner/pilot actor tags. These references reinforce that the three
no-trigger tags are not all equivalent: sword has a weapon melee damage link;
flag and ball combine objective identity with melee links.

The weapon-root melee JPT! links and their base damage triples were checked
separately from trigger projectile damage:

| Weapon roots | Weapon melee JPT! link | Base triple |
|---|---|---:|
| Pistol, assault rifle, shotgun, sniper rifle, rocket launcher, plasma pistol, plasma rifle, Needler | Each root's same-family `weapons\\<family>\\melee`; each has corresponding `<family>\\melee_response` | 40 / 50 / 60 |
| Flamethrower | `weapons\\flamethrower\\melee`, with `weapons\\flamethrower\\melee_response` | 60 / 70 / 80 |
| Energy sword | `weapons\\energy sword\\melee`; no weapon melee-response tag | 151 / 151 / 151 |
| Flag and ball | `weapons\\flag\\melee` / `weapons\\ball\\melee`, each with its corresponding melee-response tag | 80 / 80 / 80 |
| Fuel rod, Gravity rifle, Hunter fuel rod, Sentinel, Warthog, Ghost, Scorpion, Banshee, Wraith, C-gun turret and dropship C-gun | NONE | — |

These are tag references/values, not proof that player melee always uses the
weapon-root JPT!. CE `unit_cause_melee_damage` normally uses the unit's melee
definition; `non_players_use_melee_damage` selects the weapon-root JPT! in that
unit damage branch, while the player melee path has its own arbitration and
response (`source/items/weapon_definitions.h:26-44`,
`source/units/units.c:8880-8955,8990-9180`). The energy-sword root's 151 damage
link therefore cannot alone establish lunge envelope, who selects it, hit
timing, shield spill or response animation. Test the unit and weapon branches
separately; fixed candidate counts and one bounded damage event per resolved
melee target suit the EE better than allocating hit records.

Each resolved projectile tag has a 33-record material-response block.
Material records carry separate default, potential and detonation effects;
most bullet/bolt families have many material-specific default impact effects,
while fuel-rod and Wraith families additionally have non-null potential or
detonation effects. For example, fuel rod's defaults include generic/metal
impact effects and its potential choices include dirt, metal, sand, stone and
wood; Scorpion shell and Wraith mortar have projectile-specific detonation
responses. These are real gameplay/presentation links that the `PRJ2` default
response subset does not fully serialize. They require correct BSP/object
material mapping and RNG/event ordering before visual effect parity can be
assessed. The per-map tag scan used the CE 160-byte material-response stride
and `projectile_definitions.h` field order; no effect can be dropped from
simulation solely because its visual output exceeds a PS2 presentation budget.

Across all weapons, keep direct `impact_damage`, attached damage and
effect-driven damage separate. Explosive tags commonly have null direct impact
damage but a `jpt!` part inside an `effe` tag. CE effect damage execution is in
`source/effects/effects.c:1738-1760`; area target collection, owner/team
filtering, occlusion and falloff are in
`source/objects/damage.c:1929-1963,2507-2595`. Current play combat uses one
fixed diagnostic sphere, not a general actor/object/team/region query, so it
cannot establish these branches. Projectile material response has default and
potential choices plus effects and friction; CE selection is
`projectiles.c:1595-1614`, response handling `1786-1846`. Current `POT1`/`POT2`
profiles carry the potential fields and the shot path evaluates those gates;
the remaining gaps here are material-ID correlation with converted BSP/object
surfaces and the material/effect references and effect-dispatch path. Needler
specifics are owned by its dedicated report.

## Whole-inventory PS2 resource implications

The 23 weapons reuse fewer projectile definitions (notably Hunter/fuel rod,
gravity rifle/flame, and dropship/C-gun). Cache immutable definitions once and
keep per-shot state in fixed pools; do not replicate 33-material tables for
each active weapon. The plan's 32 MiB budget reserves 2.5 MiB for simulation /
effects, 0.5 MiB frame scratch, 1 MiB DMA, and 0.5 MiB audio. The viewer's
32-projectile diagnostic cap is not a campaign high-water result. Actor,
vehicle, effect, AoE target, and audio voice/decode capacity must be measured
and given deterministic overflow behavior. Avoid unbounded target scans,
heap allocation per effect, and per-tick material-table parsing. CPU-sensitive
costs include guided projectile steering, BSP collision, AoE target traversal,
RNG/effect ordering and audio mixing. Tag/source review provides no EE/PCSX2
performance measurement, final pool capacity, or audio codec/voice profile.

For audio specifically, CE supports uncompressed, Xbox ADPCM, IMA ADPCM and
Ogg modes plus mono/stereo channels (`source/sound/sound_manager.c:298-317`);
the Xbox path builds PCM or XBOX_ADPCM formats
(`source/sound/sound_dsound_xbox.c:2079-2162`). `config/memory-budget.json`
reserves 512 KiB for audio staging. PS2 must decode/stream those selected
permutations through bounded buffers and voice pools; no claim that an Xbox
ADPCM block is directly playable by PS2 hardware is warranted. The filtered
tag subset's codec and permutation-size metadata is extracted below; runtime
decode, concurrent voices, and mixer cost remain measurable blockers for a
final audio budget.

## Additional source/tag-only audit completed

### Numeric material-response records

I re-read each distinct combat `proj` block (33 records, 160 bytes each) from
the extracted maps using `projectile_material_response_definition` at
`submodules/halo-ce-universal/source/items/projectile_definitions.h:34-66`.
The `ORDER` paths reuse projectile tags; 20 distinct projectile tags are
referenced by those weapon paths. Two additional grenade projectile tags are
included below because fuel-rod/impact effect references lead into grenade
material/effect families. These are tag facts, not evidence that those
materials occur on the current Blood Gulch firing path. Material indices are
the CE material-type ordering in `source/game/game_globals.c:100-135` (0 dirt,
1 sand, 2 stone, 3 snow, 4 wood, 5-7 hollow/thin/thick metal, etc.).

| Projectile tag | Default response counts (of 33) | Potential response / non-default behavior | Effects and notable values |
|---|---|---|---|
| pistol bullet | disappear 30, overpenetrate 2, reflect 1 | none | 33 default impact-effect references |
| assault-rifle bullet | disappear 18, overpenetrate 13, reflect 2 | none | 33 default effects; initial-friction 0.7 at materials 11,13-15,17,21,23-24 |
| shotgun pellet | disappear 28, overpenetrate 3, reflect 2 | none | 33 default effects |
| sniper bullet | disappear 17, overpenetrate 14, reflect 2 | none | 33 default effects |
| rocket | detonate 32, overpenetrate 1 | material 29 potential detonate, skip fraction 0.9, no angle/velocity bounds | 21 default effects; potential effect null |
| plasma-pistol bolt | disappear 32, reflect 1 | none | 33 default effects |
| plasma-rifle bolt | disappear 31, overpenetrate 1, reflect 1 | none | 33 default effects |
| charged plasma bolt | disappear 33 | potential detonate at 0-28 and 30-32; material 29 potential overpenetrate; skip 0, no bounds | 33 potential effects, no default effects |
| Needler needle | attach 27, reflect 4, overpenetrate 2 | potential reflect at 2,5,6,7,9; upper angle bounds 25°,35°,35°,35°,15° respectively; lower 0, no velocity bounds, skip 0 | 33 default and 5 potential effects; angular noise on 2,5-7,9,10,12,16,30; reflect friction .3 at 2,5-7,9,12 and .15 at 16,30; initial friction is 0 for all materials |
| flamethrower flame | disappear 31 | none | 17 default effects |
| fuel rod | detonate 30, overpenetrate 2, reflect 1 | potential detonate at 0-29 and 31-32; material 29 skip 0.9, otherwise 0; no bounds | 30 default effects and 33 potential effects |
| Sentinel beam | disappear 18, overpenetrate 12, reflect 1 | potential reflect at 10,12,18,22,25,26,28,30; angle 0..π except material 28's zero upper bound disables angle gating | 23 default effects and 8 potential effects |
| Banshee bolt | disappear 31, overpenetrate 1, reflect 1 | none | 33 default effects |
| Banshee fuel rod | disappear 29, overpenetrate 1, detonate 3 | potential detonate at materials 0-29; mat 29 skip .9, others 0; no bounds | 4 default-effect refs, 7 potential-effect refs (other potential-response slots have null effect refs) |
| C-gun turret projectile | disappear 32, reflect 1 | none | 32 default effects |
| Ghost bolt | disappear 31, overpenetrate 1, reflect 1 | none | 33 default effects |
| Scorpion bullet | disappear 19, overpenetrate 12, reflect 2 | none | 33 default effects; initial-friction .7 at 11,13-15,17,21,23-24 |
| Scorpion tank shell | detonate 33 | none | detonation-effect refs at 0-9,28-29,31 (12 records); no default effects |
| Warthog bullet | disappear 16, overpenetrate 16, reflect 1 | none | 32 default effects; initial-friction .7 at 4-6 (maximum distance 2) and 11,13-15,17,21,23-24 (distance 0) |
| Wraith mortar | detonate 32, overpenetrate 1 | potential detonate at 0 and 2, skip 0, no bounds, potential-effect refs null | 21 default effects; detonation-effect refs at 0-9,28-29,31-32 |
| fragment-grenade projectile (grenade/effect dependency) | reflect 32, overpenetrate 1 | material 28 potential reflect (angle 0-.524 rad; velocity .033-33.333; skip 0); material 29 potential overpenetrate (skip .2) | 32 default effects; detonation refs at 0-2,4-9,28-29; default reflect friction varies by material |
| plasma-grenade projectile (grenade/effect dependency) | reflect 32, overpenetrate 1 | materials 0-8,11-15,17,19-25,27,29-31 (26 total) potential response 4 (`attach`) with `only_against_units` flag; material 16 potential reflect without that flag | 32 default effects; detonation-effect reference at every material |

`fuel rod` and Hunter fuel rod share the same projectile record; Gravity rifle
reuses the flamethrower flame definition; Scorpion and Banshee trigger variants
account for multiple weapon paths per projectile. Source material selection
is not a single unconditional lookup: `projectiles.c:1501-1614` derives impact
velocity and angle (including random noise), selects the potential response
only if response is nonzero, configured angle/velocity gates pass (an upper
bound of zero disables that gate), optional unit-only flag passes, and
`real_random() >= potential_skip_fraction`. The two noise calls and this
potential-selection draw are part of replay-visible RNG order. CE applies the
selected default/potential effect only above the impact-velocity threshold,
then processes response and friction/attach/detonation-started behavior at
`projectiles.c:1630-1846`. Source RNG helpers are in
`source/math/real_math.h:1637-1654`. The pinned Halo-64 source retains the same
condition and response/effect selection at `source/items/projectiles.c:
1658-1682`, corroborating this portable-source interpretation.

For implementation ordering, the source executes the two `real_random_range`
calls unconditionally in this order: velocity perturbation
`[-velocity_noise,0]`, then angle perturbation `[-angular_noise,+angular_noise]`.
Only after those does the `&&` chain test nonzero potential response, angle
bounds, velocity bounds, optional unit-only flag, and finally draw
`real_random()` for the skip test. Thus a configured potential response can
consume a third RNG value even with zero skip fraction; the third draw is
short-circuited when an earlier condition fails. If selected, the potential
effect replaces the default effect for that collision. Relevant tag fields
are `potential_response` +36, flags +38, skip fraction +40, angle lower/upper
+44/+48, velocity lower/upper +52/+56 and potential-effect tagref +60 within
each 160-byte material record. All nonzero potential-response records in the
20 distinct weapon-projectile set have `potential_flags == 0`; the unit-only
branch is nevertheless active in the two separate grenade projectile
dependencies, as detailed above.

Nonzero potential records in the 20-tag weapon projectile set are exactly: rocket
material 29 (detonate, skip .9, no bounds); charged plasma bolt materials
0-28 and 30-32 (detonate) and 29 (overpenetrate), all skip 0/no bounds;
Needler materials 2,5,6,7,9 (reflect, angle ranges [0,25°], [0,35°],
[0,35°], [0,35°], [0,15°], no speed bounds/skip 0); handheld/Hunter fuel rod
materials 0-29,31,32 (detonate, skip .9 only at 29); Sentinel beam materials
10,12,18,22,25,26,28,30 (reflect, angle 0..π except 28's zero upper bound
disables that test); Banshee fuel rod materials 0-29 (detonate, skip .9 only
at 29); Wraith mortar materials 0 and 2 (detonate, no bounds/skip 0; potential
effect refs null); and the rocket/fuel-rod/Needler conditions just stated.
The grenade dependencies additionally have fragment-grenade material 28
potential reflect with angle [0,.524] rad, speed [.033,33.333], skip 0, and
material 29 potential overpenetrate/skip .2; plasma-grenade potential attach
on the unit-only materials listed above and potential reflect on material 16.
This list is
the tag-side test vector for the condition evaluator; it does not establish
which records a particular retail map collision will encounter.

To make weapon coverage explicit rather than requiring the reader to join the
23-row inventory to the unique-tag table mentally, this is the per-weapon
material-response crosswalk. `none` means no `proj` tag is referenced by the
weapon root; it is not a claim that ordinary unit/world collision has no
material behavior.

| Weapon path # | Trigger/material profile(s) | Path-specific material finding |
|---:|---|---|
| 1 Pistol | primary: pistol bullet | 33 per-material default effects; disappear/overpenetrate/reflect distribution in the projectile table; no potential response |
| 2 Assault rifle | primary: assault-rifle bullet | 33 default effects; overpenetration initial friction .7 on the listed flesh/armor material slots; no potential response |
| 3 Shotgun | primary: shotgun pellet (15 pellets per shot) | 33 default effects; same per-pellet response profile as projectile table; no potential response |
| 4 Sniper rifle | primary: sniper bullet | 33 default effects, no potential response; material outcomes still separate from region/headshot attribution |
| 5 Rocket launcher | primary: rocket | material 29 has 0.9-skip potential detonate, with null potential effect; default detonation behavior remains tag-driven |
| 6 Plasma pistol | primary: plasma-pistol bolt; secondary: charged plasma bolt | primary has 33 default effects and no potential response; charged shot uses 33 potential effects and detonate except mat 29 overpenetrates |
| 7 Plasma rifle | primary: plasma-rifle bolt | 33 default effects, no potential response; heat/overheat state is a separate weapon path |
| 8 Needler | primary: Needler needle | attach-dominant defaults, five angle-gated potential reflections, material noise and reflect friction; see dedicated Needler audit for guidance/combining |
| 9 Flamethrower | primary: flamethrower flame | 17 material default effects; the persistent flame/continuous damage loop is not equivalent to one generic projectile hit |
| 10 Fuel rod | primary: fuel rod | full per-material potential detonation table; material 29 alone has skip 0.9, all records omit angle/velocity bounds |
| 11 Gravity rifle | primary: shared flamethrower flame | shares the flame's 17 material effects; this shared projectile tag does not establish Gravity-rifle cadence/contact behavior |
| 12 Energy sword | none | melee weapon root; damage/response is unit-melee behavior, not a projectile material table |
| 13 Flag | none | objective/carry item with its own melee damage and response; no projectile material profile |
| 14 Ball | none | Oddball objective/carry item with its own melee damage and response; no projectile material profile |
| 15 Hunter fuel rod | primary: shared fuel-rod projectile | same 33 material records and potential/effect references as handheld fuel rod; AI/owner/weapon-origin behavior differs |
| 16 Sentinel | primary: Sentinel beam | 23 default effects and eight potential reflections with angle metadata; no unit-only potential flag is set, while Sentinel actor/material mapping still requires runtime proof |
| 17 Warthog gun | primary: Warthog bullet | 32 default effects; material-specific initial friction includes a 2-unit distance cap on slots 4-6 |
| 18 Ghost gun | primary: Ghost bolt | 33 default effects, no potential response |
| 19 Scorpion cannon | primary: tank shell; secondary: Scorpion bullet | shell detonates for all 33 materials with 12 material detonation-effect refs; secondary is a separate bullet profile with 33 default effects and overpenetration friction |
| 20 Banshee gun | primary: Banshee bolt; secondary: Banshee fuel rod | primary has 33 default effects; secondary has material 0-29 potential detonation (mat 29 skip .9) plus three default detonate materials |
| 21 Wraith mortar | primary: Wraith mortar | all materials default to detonate except one overpenetrating slot; two potential detonation records and fourteen detonation-effect links |
| 22 C-gun turret | primary: C-gun turret projectile | 32 default effects; one reflect slot, no potential response |
| 23 Dropship C-gun | primary: shared C-gun turret projectile | same 32 default effects and response table as #22; dropship origin/owner/actor lifecycle remains distinct and unsupported |

### Direct projectile damage-tag values for every distinct trigger profile

The table reports the `jpt!` `damage_minimum`, `damage_lower_bound` and
`damage_upper_bound` triples referenced by each projectile's direct
`impact_damage`; it is not final target damage. CE combines the tag's scalar,
material modifiers and regional/target state in
`source/objects/damage.c:1472-1477`; impact routing and the distinction between
object damage and effect/AoE damage are in `source/items/projectiles.c` and
effect code. Values were read from supplied XISO tags via
`tools/play_weapons.py:510-536` layouts. `NONE` means no direct impact jpt!, not
“zero-damage weapon.” Needler lists its separate attached-damage jpt! because
its impact jpt! is numerically zero while attachment detonation is not.

| Projectile path / weapon roots using it | Direct impact jpt! and base triple | Attached jpt! and base triple | Important qualification |
|---|---|---|---|
| `weapons\\pistol\\bullet` — #1 | `weapons\\pistol\\bullet`: 25 / 25 / 25 | NONE | Actor-region/material modifiers still alter final damage. |
| `weapons\\assault rifle\\bullet` — #2 | `weapons\\assault rifle\\bullet`: 10 / 10 / 10 | NONE | Per-shot base triple; high cadence makes bounded target/damage work important. |
| `weapons\\shotgun\\pellet` — #3 | `weapons\\shotgun\\pellet`: 8 / 18 / 25 | NONE | Applied per pellet; tag distribution emits 15 independent projectiles. |
| `weapons\\sniper rifle\\sniper bullet` — #4 | `weapons\\sniper rifle\\sniper bullet`: 101 / 101 / 101 | NONE | Region/zoom/actor response is not included in the triple. |
| `weapons\\rocket launcher\\rocket` — #5 | NONE | NONE | Blast is through `rocket explosion` effect; do not infer direct hit damage. |
| `weapons\\plasma pistol\\bolt` — #6 primary | `weapons\\plasma pistol\\bolt`: 10 / 16 / 20 | NONE | Trigger's charged secondary is a separate projectile below. |
| `weapons\\plasma rifle\\charged bolt` — #6 secondary | `weapons\\plasma rifle\\charged bolt`: 70 / 70 / 70 | NONE | Charged detonation effect is separately linked. |
| `weapons\\plasma rifle\\bolt` — #7 | `weapons\\plasma rifle\\bolt`: 10 / 12 / 14 | NONE | Heat does not change the static jpt! triple without source damage/state scaling. |
| `weapons\\needler\\needle` — #8 | `weapons\\needler\\impact damage`: 0 / 0 / 0 | `weapons\\needler\\detonation damage`: 10 / 10 / 10 | Direct collision jpt! is not the attached explosion. Supercombine has its own effect/damage behavior. |
| `weapons\\flamethrower\\flame` — #9 and gravity rifle #11 | NONE | NONE | Flame detonation/contact effect carries damage semantics; shared projectile doesn't prove weapon-specific cadence. |
| `weapons\\fuel rod gun\\fuel rod` — #10/#15 | NONE | NONE | Shared handheld/Hunter projectile; blast jpt! is in linked effect parts, not projectile impact_damage. |
| `characters\\sentinel\\beam` — #16 | `characters\\sentinel\\beam`: 1 / 1 / 1 | NONE | Actor beam uses its own material/effect profile; target region not included. |
| `vehicles\\warthog\\bullet` — #17 | `vehicles\\warthog\\bullet`: 16 / 16 / 24 | NONE | Mounted owner/region context absent. |
| `vehicles\\ghost\\ghost bolt` — #18 | `vehicles\\ghost\\ghost bolt`: 10 / 10 / 14 | NONE | Mounted chambering/owner state is separate. |
| `vehicles\\scorpion\\tank shell` — #19 primary | NONE | NONE | Blast jpt! is through shell explosion effect; Scorpion secondary bullet is another projectile. |
| `vehicles\\scorpion\\bullet` — #19 secondary | `vehicles\\scorpion\\bullet`: 10 / 10 / 10 | NONE | Secondary trigger's magazine index is -1. |
| `vehicles\\banshee\\banshee bolt` — #20 primary | `vehicles\\banshee\\banshee bolt`: 10 / 10 / 14 | NONE | Banshee primary is distinct from secondary rod. |
| `vehicles\\banshee\\banshee fuel rod` — #20 secondary | NONE | NONE | Fuel-rod blast is effect-linked; secondary uses magazine0 and inhibits primary under mode2. |
| `vehicles\\wraith\\wraith mortar` — #21 | NONE | NONE | Blast jpt! is in Wraith mortar explosion effect. |
| `vehicles\\c gun turret\\c gun turret` — #22/#23 | `vehicles\\c gun turret\\bolt`: 8 / 12 / 14 | NONE | Shared projectile/JPT; firing rate and mount ownership differ between turret and dropship roots. |

These fields are only the base JPT triples. The audit also found 33 per-
material modifier values in each direct damage tag; no final unit damage can
be claimed without the collision material, unit/vehicle damage multiplier,
region, shield/health ordering, and effect path. Existing M13 selected-profile
shot damage is not evidence of the complete JPT calculation. On EE, preselect
the appropriate projectile/JPT profile and reuse bounded damage scratch; do
not copy all 33 material arrays per live projectile or resolve tag paths during
each hit. Test base scalar and material/region multipliers separately under a
fixed damage seed.

### Direct-hit JPT category and flag closure across all projectile weapons

The preceding table inventories all base triples; this additional pass closes
the remaining static question of whether a damage value carries a weapon
category or damage-policy flags. The values below are from retail projectile
`impact_damage` references in supplied maps and pinned tag offsets (JPT damage
category at root +0x1C6; damage flags at +0x1C8). The category enum and flag
names are in `submodules/halo-ce-universal/source/objects/damage.c:188-230`.
For flags, the table reports encoded bits and only describes bits whose source
semantics can be supported by the inspected code; it does not infer balance
or game-mode results from a name alone.

| Direct projectile damage tag | Weapon route(s) | CE category | JPT damage flags | Source-backed note |
|---|---|---|---:|---|
| `weapons\\pistol\\bullet` | Pistol | 2 bullet | `0x2` | Bit 1 is `can_cause_headshots`; source applies the head-material instant-kill rule only when actor/material attribution supplies it (`damage.c:1229-1248`). |
| `weapons\\assault rifle\\bullet` | Assault Rifle | 2 bullet | `0x0` | No encoded JPT damage-policy bits. |
| `weapons\\shotgun\\pellet` | Shotgun (each of 15 pellets) | 12 shotgun | `0x0` | Each pellet uses the same JPT profile; aggregate hit damage depends on pellet collision count. |
| `weapons\\sniper rifle\\sniper bullet` | Sniper Rifle | 5 sniper | `0x2` | Same head-material/headshot gate as pistol; does not by itself prove hit-region parity. |
| `weapons\\plasma pistol\\bolt` | Plasma Pistol primary | 10 plasma | `0x4` | Bit 2 name is `pings_resistant_units`; no final damage/ping result inferred here. |
| `weapons\\plasma rifle\\charged bolt` | Plasma Pistol charged secondary | 10 plasma | `0x4` | Side-effect field is 3; charged-bolt detonation/effect path remains distinct. |
| `weapons\\plasma rifle\\bolt` | Plasma Rifle | 10 plasma | `0x804` | Encodes bits 2 and 11 (`pings_resistant_units`, `can_cause_multiplayer_headshots`); source confirms bit 11 doubles head-material damage only in multiplayer (`damage.c:1243-1248`). |
| `weapons\\needler\\impact damage` | Needler needle direct collision | 2 bullet | `0x0` | Base damage is 0/0/0; attached-detonation damage is a separate tag/path (see Needler report). |
| `characters\\sentinel\\beam` | Sentinel | 2 bullet | `0x0` | Actor-beam path, not a player-mounted gun. |
| `vehicles\\warthog\\bullet` | Warthog gun | 8 mounted weapon | `0x0` | Mount owner and target region still matter. |
| `vehicles\\ghost\\ghost bolt` | Ghost gun | 8 mounted weapon | `0x4` | Has bit 2 `pings_resistant_units`; do not treat it as owner or friendly immunity. |
| `vehicles\\scorpion\\bullet` | Scorpion secondary | 8 mounted weapon | `0x0` | Distinct from null-impact tank shell primary. |
| `vehicles\\banshee\\banshee bolt` | Banshee primary | 8 mounted weapon | `0x4` | Has bit 2; distinct from null-impact fuel-rod secondary. |
| `vehicles\\c gun turret\\bolt` | C-gun turret and dropship C-gun | 8 mounted weapon | `0x4` | Shared damage tag; trigger rate and owner/mount lifecycle are not shared. |

The six projectile routes with null direct `impact_damage` are Rocket,
Flamethrower/Gravity Rifle flame, Fuel Rod/Hunter Fuel Rod, Scorpion shell,
Banshee fuel rod, and Wraith mortar; their linked damage is only through the
relevant effect graph documented below. **Implementation implication:** the
current EE's generic shot result must not collapse category/flags into a
weapon-wide default, apply headshots without a validated material/region, or
invent direct damage for those six effect-driven paths. A fixed small JPT-ID
table keeps the 14 distinct direct profiles shared across weapons and avoids
per-shot parsing/copies; deterministic actor/material integration remains a
runtime gate. This finishes source/tag classification for direct-hit damage
across all 23 weapon paths, including dual-trigger and shared-projectile roots.

### Nested effect damage for explosive and persistent-flame paths

I also followed each projectile's root effect, detonation-started effect, and
non-null 33-material default/potential/detonation `effe` refs through their
effect event/part blocks (`effect_definitions.h:29-86`). Nested `jpt!` parts
were resolved to supplied cache tags. These base triples are effect-part
damage definitions, not projectile impact damage. CE creates damage from the
selected part in `source/effects/effects.c:1738-1760`, then resolves area
targets and falloff in `source/objects/damage.c:1929-1963,2507-2595`.

| Weapon path(s) | Effect graph → nested damage part | Base JPT triple | What this establishes / remaining question |
|---|---|---:|---|
| Rocket launcher #5 | `weapons\\rocket launcher\\effects\\rocket explosion` → `weapons\\rocket launcher\\explosion` | 80 / 300 / 330 | Blast exists despite null projectile impact jpt!. Graph also references `weapons\\frag grenade\\shock wave` at 0/0/0; source blast scale, owner/team filter and event-once proof remain. |
| Handheld and Hunter fuel rod #10/#15 | `weapons\\fuel rod gun\\effects\\explosion` → `weapons\\fuel rod gun\\explosion` | 40 / 75 / 75 | Shared explosion damage is separate from direct collision. Graph also references zero-damage frag shock wave. |
| Scorpion shell #19 primary | `vehicles\\scorpion\\shell explosion` → `vehicles\\scorpion\\shell explosion` | 80 / 351 / 351 | Null direct shell impact does not mean no damage. Graph also contains zero-damage frag shock wave; blast query still needs runtime proof. |
| Banshee fuel rod #20 secondary | `vehicles\\banshee\\fuel rod explosion` → `vehicles\\banshee\\fuel rod explosion` | 40 / 75 / 75 | Secondary explosive is distinct from primary bolt; vehicle owner/AI/team context is absent in player runtime. |
| Wraith mortar #21 | `vehicles\\wraith\\effects\\wraith mortar explosion` → `vehicles\\wraith\\explosion` | 50 / 90 / 110 | Projectile has null direct impact; its distinct `vehicles\\wraith\\shock wave` is 0/0/0. Confirm falloff and deterministic multi-target selection. |
| Flamethrower #9 / Gravity rifle #11 | `weapons\\flamethrower\\effects\\flame detonation` → `weapons\\flamethrower\\explosion` | 10 / 10 / 10 | Shared low-value contact/explosion part does not prove that the two weapon roots schedule it at the same cadence. |

These are the damaging nested effect-part jpt! dependencies resolved for the
explosive and flame projectile profiles in the audited trigger set. Other
projectile effect graphs remain important for material impact/presentation;
their reachable parts in this recursive pass did not resolve to another
damaging jpt!. That is not evidence that those weapons never deal damage:
Needler attached damage is a direct `attached_detonation_damage` link
(10/10/10), and bullet/plasma damage is in the direct-impact table above. The
player port does not execute these effect graphs. Store compact converted
damage/effect IDs rather than full effect/particle systems in resident weapon
state; enforce fixed part/target/voice limits and profile source-equivalent
blast traversal on EE.

Current M13 `PRS1` serialization in `tools/play_weapons.py:455-472,789-830`
and `src/game/shot.h:24-52` retains default response, initial/parallel/
perpendicular friction, angular/velocity noise, and the potential response,
flags, skip fraction and angle/velocity bounds for its 33 slots. `POT1`/`POT2`
records are packed by `tools/play_weapons.py:455-472,789-830`, copied into the
selected profiles in `src/game/play_fp.c`, and evaluated by
`src/game/shot.c:227-235,480-560`. The impact path consumes seeded draws in
source order for velocity noise, angle noise, then (when the CE gate passes)
the potential skip/selection test. What remains absent is material-linked
default/potential/detonation effect reference and effect scale serialization/
dispatch, plus the maximum-distance friction input. This is a source-backed
partial implementation, not complete material parity: BSP/object material
mapping equivalence and effect/RNG service integration still need fixtures.

### Ammo, reload, chamber and first-person animation crosswalk

`MAG2.reload_time` is a retail tag field, not the CE magazine reload timer.
In pinned CE, `weapon_get_first_person_animation_time` reads the selected first-
person animation graph's mapped animation `frame_count` (or returns zero if
the graph/clip is absent) (`source/items/weapons.c:1351-1428`).
`weapon_magazine_start_reload` sets `original_time` and `state_timer` from that
helper, after choosing the shotgun shell-reload variant
(`weapons.c:1713-1755`). On finish, CE first applies the waste-magazine flag,
loads `min(rounds_reloaded, rounds_total)`, caps at `rounds_loaded_maximum`,
updates total ammo unless infinite, marks unchambered, and may chain another
reload (`weapons.c:1524-1560`). Chambering is a separate state using
`chamber_time * TICKS_PER_SECOND` (`weapons.c:1564-1595`), not `reload_time`.
Halo-64 has corresponding routines at `source/items/weapons.c:1222-1295,
1382-1418,1565-1598`; it confirms the same broad frame-count reload, capped
round insertion, chained reload and separate chamber timer semantics. It is a
portable-source cross-check, not an independent retail-runtime measurement.

The extractor derives animation frame counts by following each weapon's first-
person graph reference and animation-type mapping (`tools/play_weapons.py:131-
220`, with the `WEAPON_FP_ANIM` field at `scenconv.py:173`). AMO1 stores the
resolved frame counts; MAG2 stores the raw tag magazine fields. AMO1 does not
preserve the graph path or animation-index mapping, so the following graph and
clip evidence is recorded here explicitly. `—` means no magazine/reload path;
`missing` means the supplied weapon pack has no usable first-person reload
graph/clip and AMO1 encodes zero, not that a MAG2 seconds value can replace it.

| # | Weapon | Loaded / total; reload amount | FP graph; reload frames (shotgun enter) | MAG2 reload / chamber | Ammo-state finding and gap |
|---:|---|---|---|---|---|
| 1 | Pistol | 12 / 60; 12 | `weapons\\pistol\\fp\\fp`; 67 | 2.17 s / 0 | Discrete clip refill; legacy EE path handles basic reload, but exact state/animation messages and effects are not integrated. |
| 2 | Assault rifle | 60 / 240; 60 | `weapons\\assault rifle\\fp\\fp`; 87 | 3.4 s / 0 | Full-mag refill; legacy path has basic reload, same exact-state/animation/effect gap. |
| 3 | Shotgun | 12 / 24; 1 | `weapons\\shotgun\\fp\\fp`; 12 (enter 15) | 0.4 s / 0 | Incremental shell reload; CE enters per-shell and selects first/last-shell animation variants. A single generic timer would be wrong. |
| 4 | Sniper rifle | 4 / 12; 4 | `weapons\\sniper rifle\\fp\\fp`; 94 | 0 / 0 | Clip refill. `reload_time=0` does not mean instantaneous CE animation. |
| 5 | Rocket launcher | 2 / 4; 2 | `weapons\\rocket launcher\\fp\\fp`; 125 | 5 s / 0 | Clip refill; seconds differ from mapped graph frame count. |
| 6 | Plasma pistol | no magazine | `weapons\\plasma pistol\\fp\\fp`; 9; ready 14 | — | Charge/heat trigger state, not MAG2 reload. AMO1 frame counts do not implement charge/release/overheat. |
| 7 | Plasma rifle | no magazine | `weapons\\plasma rifle\\fp\\fp`; reload clip missing; ready 29 | — | Heat/overheat state, no finite MAG2 rounds. Reload animation reference is unavailable; do not synthesize it from a duration. |
| 8 | Needler | 20 / 80; 20 | `weapons\\needler\\fp\\fp`; 70 | 1 s / 0 | Clip refill; dedicated Needler report covers projectile behavior, not a substitute for reload-state parity. |
| 9 | Flamethrower | 100 / 600; 100 | `weapons\\flamethrower\\fp\\fp`; 104 | 3.4 s / 0 | Waste-round magazine flag is set; CE empties old clip before inserting refill, with heat/fuel behavior separate. |
| 10 | Fuel rod gun | 4 / 12; 4 (trigger cost 0) | no graph reference; missing (0 in AMO1) | 5 s / 0 | Tag rounds and trigger cost conflict means the firing path does not consume the ordinary finite clip cost. Reload parity is unresolved; 5 s must not be substituted for missing frame count. |
| 11 | Gravity rifle | 200 / 200; 200 | no graph reference; missing (0) | 3.4 s / 0 | Current tag magazine appears full-capacity; no recoverable FP reload animation. Its imported flame projectile does not define ammo state. |
| 12 | Energy sword | no magazine | no graph reference; missing | — | Melee-only. Weapon function asks for ready; no magazine reload/chamber semantics. |
| 13 | Flag | no magazine | `weapons\\flag\\fp\\fp`; reload clip missing | — | Carryable objective, not gun; graph has ready (21 frames) but no reload clip. |
| 14 | Ball | no magazine | `weapons\\ball\\fp\\fp`; reload clip missing | — | Objective; ready clip (28 frames), no magazine reload. |
| 15 | Hunter fuel rod | no finite magazine rounds | no graph reference; missing | — | AI weapon; trigger has no finite player magazine state. |
| 16 | Sentinel beam | no finite magazine rounds | no graph reference; missing | — | Actor beam, not player reload path. |
| 17 | Warthog gun | no finite magazine rounds | no graph reference; missing | — | Mounted actor weapon; mount/owner state absent. |
| 18 | Ghost gun | 50 / 300; 50 | no graph reference; missing (0) | 2 s / 0.3 s | Tag has clip and chamber values but no recoverable FP reload graph; vehicle state cannot use an invented animation timer. |
| 19 | Scorpion cannon | 1 / 9999; 1 (primary magazine; secondary index -1) | no graph reference; missing (0) | 0 / 4 s | Primary shell uses magazine 0; secondary bullet has no magazine index. Chamber timer is 4 s; mounted state is missing. |
| 20 | Banshee gun | primary magazine index -1; secondary magazine 1 / 9999 | no graph reference; missing | MAG2 record has 0/9999/9999/1; reload 0 / chamber 4 s | Primary bolt has no magazine index; secondary fuel rod uses magazine 0. No recoverable FP graph; EE rejects weapon-origin triggers. |
| 21 | Wraith mortar | 10 / 50; 10 | no graph reference; missing (0) | 2 s / 0.3 s | Tag timing fields exist, but there is no player FP reload graph; mounted reload/chamber state is unsupported. |
| 22 | C-gun turret | no finite magazine rounds | no graph reference; missing | — | Turret-origin firing; no player magazine path. |
| 23 | Dropship C-gun | no finite magazine rounds | no graph reference; missing | — | Shared C-gun projectile does not imply shared magazine or weapon-owner state. |

This exhausts the supplied weapon roots for a usable first-person reload graph:
the eight finite/charge handheld guns with a mapped reload clip are pistol,
assault rifle, shotgun, sniper, rocket launcher, plasma pistol, Needler and
flamethrower (plasma rifle has a graph but no reload clip); remaining ammo-
bearing fuel-rod, Gravity-rifle and vehicle tags have no weapon-root FP
animation reference from which the current pack can recover a reload frame
count. The three objectives have FP graphs but lack a reload clip because they
are not magazine weapons. The pack's AMO1 zero means unavailable/not
applicable; it does not encode graph identity, and raw MAG2 seconds are not a
parity fallback. Current `play_fp` loads profile frame counts and the EE's
legacy single-trigger `gun_tick` does execute a simplified reload/chamber
sequence from AMO1 counts and chamber seconds. It does not reproduce CE's
first-person animation messaging/reload effects, all shotgun state/animation
variants, or the missing-graph timing cases; trigger-pair magazines do not
share the legacy magazine state machine. Thus “basic reload exists” is not a
claim of exact CE timer/state parity. Exact timer/state hashes remain an
acceptance-test gap for every magazine-bearing path.

### Weapon-family assessment and PS2 implications

This is the source/tag-grounded family review; the earlier 23-row table gives
the tag-path-specific links. All profile tag facts are strong-confidence
retail evidence; behavior statements are pinned source, and implementation
status is code inspection (not parity result).

| Family / paths | CE behavior and source/tag evidence | Port status / concrete gap | PS2 risk and bounded test |
|---|---|---|---|
| Hitscan-like bullets: pistol, AR, sniper; pellet fan: shotgun | CE resolves trigger owner/origin/state in `weapons.c:2373-2760`; projectile impact and material response in `projectiles.c:1337-1614,1786-1846`. Tags link specific impact damage and default material response. Shotgun tag is 15 pellet projectiles per shot. | Pistol/AR/sniper have selected profile/projectile smoke; shotgun has distribution/cone coverage. No retail actor-region attribution, per-pellet integrated collision/damage/effects, or complete reload/chamber/weapon-state parity. Sniper zoom/head-region path remains separate. | Cap collision candidates and shotgun pellets at tag count (15); fixed pool/stack buffers, no per-pellet allocation. Test per-weapon cadence, reload/chamber event trace, head/body region, 15 independent deterministic impacts and material response. |
| Plasma charge/heat: plasma pistol, plasma rifle | Trigger pair includes charged secondary projectile, charge/release and heat behavior; source trigger/weapon state `weapons.c:2600-2760,3158-3205`; tags have charged projectile/effect and overheat refs. | Host pair tests cover some charge/release. Eligible plasma pistol primary/secondary are EE-dispatched, but charged effect, overheat/misfire and full heat/function animation remain absent. Plasma rifle has no MAG2 magazine or reload clip; heat is not ammo. | Avoid floating-point-heavy repeated function evaluation; use fixed-point/tick state if parity proven. Test charge threshold/release, heat, overheat/vent and primary-v-secondary effect ordering with source-seeded RNG. |
| Needler: needler | Needle projectile/material tags, attach/detonate damage and effect graph; see dedicated `docs/combat-needler-audit.md`. | Existing host steering/attachment pieces are not actor-target selection/supercombine/complete damage/effect dispatch; cite dedicated report for details. Ammo reload values crosswalked above. | Bound target scan and attached-needle pool; test target loss, candidate ordering, fuse, supercombine and reload under fixed entity cap. |
| Persistent flame: flamethrower, gravity rifle | Both trigger profiles point to flame projectile, whose tag has persistent/impact effect records; flame trigger uses ammo/heat functions. Gravity rifle borrows flame projectile and has its own firing/magazine profile. Source firing/state is not equivalent to one-shot bullet handling. | Generic shot model does not reproduce persistent flame contact cadence, repeated damage, waste-ammo, heat, or weapon-specific gravity-rifle behavior. | Flame lifetime/contact work must be capped and aggregate damage cadence; avoid spawning one entity per visual particle. Test deterministic multi-tick contact, fuel waste, heat and gravity-rifle-vs-flamethrower profile differences. |
| Explosives: rocket launcher, fuel rod, Hunter fuel rod, Scorpion shell, Banshee rod, Wraith mortar | Projectile definitions carry media/range/deceleration and material detonation data; effects link blast damage. Fuel rod detailed above; Hunter shares projectile but actor ownership differs. CE projectile/effect dispatch `projectiles.c:521-864,1110-1210,1786-1846`. | Fuel rod flight fields and potential selection now exist; no general effect execution/AoE ownership or source-compatible effect RNG. Direct impact null for explosive tags cannot stand in for blast damage. Vehicle/AI origins absent. | Bound projectile count, collision iteration, nearby-actor AoE candidate count, and effect/audio voices; static source does not establish PS2 timing. Test direct-impact-null vs exactly-once detonation/AoE, owner exclusion/team rules, material detonation and air/water transitions. |
| Guided attachment: Needler | See above and Needler report. | Not re-audited here. | Track fixed needle/entity cap; no unbounded proximity scans. |
| Beam/energy: Sentinel, C-gun and shared dropship C-gun | Tag response blocks show material effects/potential reflections; Sentinel has actor origin, C-gun tag's weapon root and projectile links are shared by dropship variant. | No beam lifetime/update or actor/mount origin/owner state in player camera path; shared projectile does not mean shared weapon lifecycle. | Fixed beam segment count and material traversal; test AI/mount origin separately from player-camera tests; bound repeated collision queries. |
| Vehicle guns: Warthog, Ghost, Scorpion, Banshee, Wraith, C-gun, dropship C-gun | Trigger origins are weapon markers and owner/seat data; magazine/chamber profiles differ (crosswalk above). Scorpion/Banshee are dual-trigger, with distinct secondary projectiles. | EE refuses `uses_weapon_origin`; no vehicle actor, mount seat, ammo routing, model-marker, or owner-team interface. Generic camera shot must remain explicitly excluded. | Keep vehicle tags/profile data resident but do not allocate vehicle simulation pools before global vehicle budget; tests need explicit mount/owner interface and bounded seat/projectile counts. |
| Melee/objectives: energy sword, flag, ball | CE unit melee collision/arbitration and damage/effect path is `source/units/units.c:8857-9136`; objective pickup/drop/scoring in CTF/Oddball modules. Retail root links differ: sword has melee damage but no response; flag/ball have damage and response tags. | Synthetic melee smoke is not sword lunge/state/animation, response timing, or objective carrier/score parity. No trigger/magazines. | Bound melee query count and objective carrier state. Test target arbitration, lunge envelope/ticks, damage/response, pickup/drop/reset/scoring separately; no projectile pool impact. |

All weapon families share a sound/effect dispatch dependency. The inspected
131-tag combat sound subset is 5.63 MiB encoded Xbox ADPCM (metadata below),
but only a bounded streaming cache and small fixed voice pool can fit the
512-KiB resident audio reservation. The current port has no measured PS2
decoder CPU cost or simultaneous-voice high-water. No per-frame full-tag scans,
heap allocations, or unbounded projectile/actor searches are acceptable under
the 32-MiB RAM target; the exact task-specific frame budgets still need physical
PS2 profiling.

### Weapon functions, trigger paths, melee and objective links

Beyond trigger→projectile and magazine values in the 23-row table, each retail
weapon root's four `function_modes` and object-level function records were
checked using `weapon_definition` (`weapon_definitions.h:171-215`) and
`object_definition` (`objects/object_definitions.h:86-115`). Modes are
requesting data channels, not proof of rendering: pistol asks for illumination;
AR asks for integrated-light, primary-ammo and illumination; shotgun asks for
primary-ejection-port, illumination and integrated-light; sniper asks for
illumination and ready; plasma pistol asks for heat, primary-charged,
illumination and age; plasma rifle asks for heat, illumination and age; Needler
asks for illumination and primary-ammo; flamethrower asks for primary-firing,
primary-ammo and heat; fuel rod asks for illumination and primary-charged;
Gravity rifle asks for illumination; sword asks for ready; Hunter rod asks for
illumination and primary-charged; Sentinel asks for illumination; Warthog,
Ghost, Scorpion, Wraith and C-gun paths ask for their applicable primary-rate
plus illumination; Banshee asks for illumination and primary-charged. Flag and
ball have no function modes. Object function names include ammo display,
muzzle/firing flash, flashlight/compass, scope activity, charge/age/heat,
Needler glow/remaining needles, flamethrower fuel/flames/idle sound, sword
blade glow and mounted-gun blur. Those model/function records are separate
from trigger `firing_effect` records, whose optional tagrefs were null in the
previous pass; neither fact substitutes for evaluated per-frame function
input and first-person/object rendering.

`weapon_trigger_definition` is two 276-byte records in the retail schema.
The notable paths are: plasma pistol primary uncharged bolt and secondary
charged bolt; Scorpion primary shell uses magazine 0 (1/9999), while its
secondary bullet uses magazine index -1; Banshee primary bolt has magazine
index -1 and its secondary fuel rod uses magazine 0 (1/9999), with secondary-
trigger mode inhibiting primary; Hunter fuel rod has
a trigger but no finite magazine; Sentinel and mounted/AI weapons use
weapon-origin data rather than player camera aim. Triggers without a finite
magazine or with per-shot cost 0 must not be treated as “no ammunition state”:
plasma charge, continuous heat, turret ammo and AI ownership have distinct CE
state. The CE behavior is implemented through trigger creation and firing
state (`source/items/weapons.c:2373-2588,2600-2760`), and the current camera
path intentionally rejects `uses_weapon_origin` until mounts/actors exist.

Retail root links confirm the energy sword's `melee_attack_damage` is
`weapons\\energy sword\\melee`, and its melee-response field is null. Flag
and ball each have their own melee-damage and melee-response tags. Most
handheld firearms use family melee links; fuel rod, Gravity rifle, Hunter rod,
Sentinel and mounted weapon definitions audited here have null weapon melee
links. CE's unit melee path normally uses the unit definition's melee damage,
but the `non_players_use_melee_damage` weapon flag can select a weapon's
`melee_attack_damage`; damage is given owner/team/player context and is sent
through either area damage or the target-specific damage path
(`source/units/units.c:8880-8955`). The player melee path additionally
performs collision arbitration and can choose a weapon melee-response effect
(`units.c:8990-9180,9279-9285`). Thus the sword's reference is not enough to
reconstruct its lunge, damage timing, counter/response or animation. Retail
flag identity is the weapon flag tested by `weapon_is_flag` (`weapons.c:731`);
CTF/oddball use separate pickup/drop/game-mode callbacks (`game_engine_ctf.c`
and `game_engine_oddball.c`, e.g. pickup/drop callbacks at 743-812 and
875-885). The ball has a separate Oddball scoring/transfer loop. Treating
flag/ball as guns or as simple melee actors would omit carrier, team, scoring,
and drop/reset behavior.

### Sound permutation metadata and payload sizes

The combat-tag sound subset was collected from the extracted 24-map retail
XISO for paths under `sound\\sfx\\weapons\\`, `sound\\sfx\\vehicles\\`,
and Sentinel impact sounds (`sound\\sfx\\impulse\\impacts\\sentinel*`).
This namespace filter yields 131 distinct `snd!` paths, 138 pitch ranges and
241 declared permutations. It is a useful lower-bound-ish candidate set, not
a proof of every sound reachable by every actor/effect/animation. Source
layouts are `sound/sound_definitions.h:90-160` (root codec at offsets 108/110,
pitch ranges at 152, 72-byte pitch range, 124-byte permutation, `samples`
tag-data size and cache file offset at permutation +64/+72). Source codec
values are in `sound/sound_manager.c:298-317`: encoding 0 mono / 1 stereo;
compression 0 none, 1 Xbox ADPCM, 2 IMA ADPCM, 3 Ogg.

Across this filtered set, all 241 permutation records select Xbox ADPCM
(compression 1); 236 are mono and 5 stereo. Summed tagged encoded sample
payload size is 5,897,088 bytes (about 5.63 MiB), largest individual
permutation 134,064 bytes, median 17,172 bytes. All nonempty `samples`
file-offset+size ranges checked in-bounds against their decompressed cache
map; this verifies tag metadata/range integrity, not audio decoding or audible
quality. For the fuel-rod explosion sound specifically, the two mono Xbox
ADPCM permutations `fuelrod_explo1` and `fuelrod_explo2` each contain 36,756
bytes at `a30.map` offsets `0x69ffc00` and `0x6a08c00`; the first 16 hex
characters of SHA-256 are `8de851326c28372b` and `25e2be1d282df86e`. Their
payloads are different. The fuel-rod firing sound has one mono Xbox ADPCM
permutation, 19,908 bytes. The C-gun firing sound has one such permutation,
64,332 bytes; the Needler fire sound has three, 9,900 bytes each. These are
specific examples, not the complete event-to-sound graph.

The sum of distinct compressed payload sizes cannot be compared directly to
the plan's 512 KiB resident audio reservation: data can be cached/streamed and
only some voices are concurrent. The source confirms Xbox ADPCM output format
handling (`source/sound/sound_dsound_xbox.c:2079-2162`), but provides no PS2
decoder, EE mixer profile, voice high-water, DMA contention measure, or
decoded-buffer lifetime for this port. At 44.1-kHz mono 16-bit PCM a single
second is 88,200 bytes, but source permutation duration is not safely inferred
from encoded byte size without correct codec framing/rate/duration metadata;
measure actual decode. The high-level PS2 constraint remains a bounded
streaming/decode buffer and fixed voice pool rather than loading every distinct
permutation resident.

### Explicit source/tag completion boundary

At this point static source and supplied-tag work is exhausted for the
requested categories: all 23 retail `weap` roots, the two grenade `eqip`
families and their projectile/material/effect records, their magazines and
trigger modes; direct and nested damage categories/flags; all damage-bearing
effect graphs; root and actor-variant AI firing profiles; melee/objective links;
reachable weapon-family sound metadata; and relevant pinned CE/Halo-64 source
behavior have been inspected. Remaining unknowns need missing runtime
interfaces/evidence: live actor/vehicle ownership and hit regions;
retail-equivalent BSP/object material IDs and unit-only potential-response
gating; full source-order RNG with effect dispatch; the complete grenade
inventory/animation/AI path; sound decoding/mixing and concurrent voices; and
EE/PCSX2/console timing, pool high-water and RAM measurements. These cannot be
settled by further reading the same static tags. They remain acceptance-test
and M23/runtime gates, not reasons to invent behavior from tag values.

## Recommended acceptance tests (candidate scenarios, not yet finalized M13 parity tests)

Finalize expected values from the source/tag audit and freeze the random seed,
spawn state, collision geometry, tick count, and event ordering before treating
these as parity fixtures:

1. **Tag record identity:** Assert both fuel-rod weapon paths select the same
   projectile tag and verify exact air/water intervals, gravity factors,
   initial/final velocity, max range, timer fields, and null impact-damage
   reference from the retail `c40.map` tag. Verify the packed runtime record
   preserves all required inputs.
2. **Air coefficient and trajectory:** Spawn in air with fixed orientation and
   no collision, compare the source equation's coefficient and every-tick
   position, velocity, odometer, deceleration timer, and final disappearance
   tick. Include the crossing tick to check average-velocity integration and
   0.99 final-speed clamp.
3. **Water coefficient and trajectory:** Spawn wholly under media and repeat
   using water gravity and the 0–10 distance interval. Check coefficient,
   vertical acceleration, crossing tick, and disappearance without assuming
   that air's upper bound applies.
4. **Air-to-water transition:** Cross a deterministic media boundary mid-flight.
   Compare the exact update tick at which the medium flag changes and the
   recomputed coefficient/timer behavior against CE source order. This is the
   important case that a spawn-only environment test misses.
5. **Direct-impact separation:** Collide with a damageable object before
   disappearance and assert zero direct projectile damage because
   `impact_damage == NONE`; separately assert that material detonation/effect
   dispatch occurs once. Do not mark the blast damage part passing until its
   effect tag and area-damage route are audited and source-backed.
6. **Replay and EE bounds:** Repeat the same seeded case with zero/one/four
   presentation passes and require identical projectile-state/event hashes.
   On EE/PCSX2, measure the selected projectile state size, pool high-water,
   collision work and frame time in a bounded scenario; keep a separate
   physical-PS2 timing gate for M23.
7. **All-23 tag conformance:** For each `ORDER` path, byte-check trigger count,
   trigger flags/rates/projectile IDs, magazine/refill/chamber values,
   projectile root refs, direct/attached damage refs, and all trigger and
   projectile material-effect tag refs against extracted source tags. Include
   all 24 maps' path resolution and duplicate-projectile aliases; do not assert
   gameplay behavior from this inventory test.
8. **Family behavior selection:** Build separate pinned-source traces for
   pistol/rifle direct shots; all 15 shotgun pellets; sniper latch/region;
   rocket, fuel-rod, Wraith and Scorpion-shell AoE; plasma charge/heat;
   flamethrower/gravity-rifle continuous damage; Needler guidance/attach/combine
   (using its report); and Sentinel/Hunter AI. Record exact seed, owner, state,
   event ordering and damage/effect outputs at every fixed tick.
9. **Melee and objective:** Verify sword, flag and ball root melee references
   against their unit/game-engine call paths; test melee reach/arbitration,
   damage response, objective pickup/carry/drop/score and simultaneous damage
   under actual object/actor state. A no-trigger weapon assertion is not a
   behavior test.
10. **Mounted weapons:** For Warthog, Ghost, Scorpion, Banshee, Wraith, C-gun
    and dropship C-gun, drive source vehicle/gunner ownership and marker
    transforms; test each trigger, magazine mode, damage/effect path and
    alternate-mode input. Camera-origin firing must remain rejected.
11. **PS2 audio/resource gates:** Inventory referenced sound codecs,
    permutations and decoded sizes; measure streaming buffer, voice and mixer
    CPU high-water within the 512 KiB audio reservation. Independently profile
    projectile/effect/AoE pool and EE CPU worst cases; never drop simulation
    damage to satisfy a presentation/audio budget.

## Remaining unknowns

- The linked fuel-rod effect's tag data and pinned-source event/damage RNG
  order are now established above, but no live actor blast result, source-vs-
  port damage hash, bounded effect-pool exhaustion, or audio playback was
  measured. Remaining work is runtime integration and trace validation, not
  missing static retail effect data.
- For all 23 weapon roots, the report now closes the requested trigger,
  projectile/material, direct and effect-linked damage, ammo/reload, function
  request, melee/objective, and AI/vehicle firing-profile source/tag questions
  that can be answered from the supplied cache set. It also records the 131
  combat-named sound tags' codec/size metadata. It does not claim a complete
  recursive audiovisual asset graph for every function/model marker: doing so
  is a separate presentation-asset inventory, not a remaining unresolved
  trigger/projectile/damage behavior question.
- Exact damage outcomes still require a real actor/vehicle/object graph,
  collision regions and damage materials, owner/team/immunity state, target
  enumeration and source-compatible effects/audio services. In particular,
  energy sword, flag and ball need distinct melee/objective state, while
  Sentinel/Hunter and five mounted weapon families need actor/AI/vehicle input
  and origin interfaces.
- The 131-path combat-named sound subset's codec and encoded-size metadata is
  extracted, but payload decode correctness, event/permutation choice under
  runtime RNG, complete recursively reachable audio coverage, concurrent voice
  demand, and PS2 decode/mixer cost remain unresolved runtime/interface work.
  CE's codec constraints are documented above.
- The stripped retail XBE analysis provides no useful symbol-to-source mapping
  for these routines. A more targeted REA result requires matching code
  addresses/bytes against a known build or symbols; no such match is currently
  in evidence.
- This report made no new runtime/PCSX2 or physical-PS2 combat test. Existing
  play projectile checks are fixed diagnostic-probe tests documented in
  `docs/combat.md`; they do not validate 23 weapons in live gameplay.

### Weapon-wide source/tag closure and exhaustion statement

The all-weapon matrix covers #1–11 player handheld roots, #12 sword melee,
#13–14 objective weapons, #15–16 actor/AI weapons, and #17–23 vehicle/turret
weapons. The final gap-driven pass checked all 23 root AI firing-parameter
links, added Hunter/Sentinel fallback actor profiles and all seven vehicle
gunner/pilot numeric profiles, and classified every non-null direct-impact JPT
by damage category/flags. The direct/effect-linked JPT, tag reload versus CE
animation reload, melee/objective references, material-response profiles,
and six distinct explosive/flame effect roots are documented above. Findings
are based on pinned halo-ce-universal definitions/algorithms, Halo-64 source
comparison, and supplied retail cache records; they are not live retail traces.

No further source/tag-only weapon trigger, projectile, damage, reload,
melee/objective, or AI firing-profile facts are assessable within this Step 10
combat scope from the supplied records. Remaining questions need interfaces or
execution evidence rather than additional tag reading: scenario-selected
actor/vehicle ownership and firing origin; exact collision/material/target
ordering; runtime effect RNG and damage application; complete audiovisual
reachability/codec playback; and RAM/CPU/audio voice high-water on EE/PCSX2 or
console. For PS2 budgeting, keep 33-entry damage/material arrays shared by
profile, projectile and effect slots fixed-capacity, shotgun's 15-pellet work
bounded, and the 5.63-MiB encoded Xbox-ADPCM sample set streamed rather than
resident against 32 MiB system memory / 512 KiB resident audio budget. Actual
EE CPU cost, PS2 ADPCM conversion and concurrent voice demand remain measured
runtime gates; no static inference can close them.

## References

- `submodules/halo-ce-universal/source/items/weapon_definitions.h:112-215`
- `submodules/halo-ce-universal/source/items/projectile_definitions.h:34-105`
- `submodules/halo-ce-universal/source/items/weapons.c:2373-2588,2600-2760`
- `submodules/halo-ce-universal/source/items/projectiles.c:521-864,1110-1128,1165-1210,1337-1614,1786-1846`
- `submodules/halo-ce-universal/source/effects/effects.c:1738-1760,2297-2322`
- `submodules/halo-ce-universal/source/effects/effect_definitions.h:29-86`
- `submodules/halo-ce-universal/source/objects/damage_effect_definitions.h:42-62,168-184`
- `submodules/halo-ce-universal/source/objects/damage.c:219-230,1929-1963,2507-2595`
- `submodules/halo-ce-universal/source/ai/actor_definitions.h:318-415`
- `submodules/halo-ce-universal/source/ai/actor_combat.c:438-510,1300-1318,2370-2405`
- `submodules/halo-ce-universal/source/math/random_math.c:217-225`
- `submodules/halo-ce-universal/source/units/units.c:8857-9136`
- `submodules/halo-ce-universal/source/game/game_globals.c:100-135`
- `submodules/halo-ce-universal/source/game/game_engine_ctf.c:743-812`
- `submodules/halo-ce-universal/source/game/game_engine_oddball.c:337-343,875-885`
- `submodules/halo-ce-universal/source/sound/sound_manager.c:298-317,2455-2485`
- `submodules/halo-ce-universal/source/sound/sound_dsound_xbox.c:2079-2162`
- `submodules/halo-64/source/items/projectiles.c:822-864,1171-1188,1252-1276,1420-1470`
- `submodules/halo-64/source/items/projectiles.c:1658-1682`
- `tools/play_weapons.py::trigger_records`, `magazine_records`,
  `trigger_projectiles`, `firing_effect_records`, and `projectiles`
- `docs/combat.md` (current M13 implementation boundaries)
- `docs/combat-needler-audit.md` (Needler family findings)
- `docs/combat-rea-extraction.md` (REA container/stripped-XBE limitations)
- `config/memory-budget.json` (PS2 audio-staging reservation)
- Supplied retail XISO and extracted `c40.map` hashes recorded above.

### Appendix — compact explosive/flame effect-to-damage extraction

This appendix is a focused pack-format recommendation, not an implementation
change. “Verified” means present in pinned CE source or parsed retail map
records; recommendations and behavior not replayed are marked as inference.

**Verified structure and offsets.** The CE `effe` root is 0x40 bytes:
`flags` +0, loop indices +4/+6, danger radius +8, locations tag block +0x28,
events tag block +0x34. Each 0x44-byte event has flags +0, skip fraction +4,
delay low/high +8/+0xC, duration low/high +0x10/+0x14, parts block +0x2C,
particles block +0x38. Each 0x68-byte part has environment/disposition/
location/flags +0/+2/+4/+6, runtime base-class group +0x14, 16-byte
`tag_reference` +0x18, and velocity/radius fields beginning +0x40. See
`submodules/halo-ce-universal/source/effects/effect_definitions.h:29-86`.

For a `jpt!` root, falloff/cutoff/cutoff-scale/area-effect flags are +0/+4/+8/
+0xC. The `damage` substructure starts at +0x1C4 (452): side effect/category/
flags +0/+2/+4, core radius +8, minimum/lower/upper +0xC/+0x10/+0x14,
vehicle passthrough/camouflage modifiers +0x18/+0x1C, and 33 material
multipliers +0x3C. These offsets follow pinned CE's structure in
`objects/damage_effect_definitions.h:42-62,168-184`; the report's existing
`tests/test_grenade.py` extraction independently reads the same base triple
at root +464. Damage-effect flag bit 0 means do not scale by distance;
damage flags used below are owner-immune bit 0, detonates-explosives bit 5,
and flaming-death bit 7 (`objects/damage.c:214-230`).

**Verified supplied-tag records.** Six distinct effect graphs serve seven
weapon routes (Gravity Rifle shares Flamethrower's projectile/effect profile).
Each root has `effe` flags `0x2` (must-be-deterministic bit 1), one event
(flags 0, skip 0, delay 0..0, duration 0..0), and a part-0 `jpt!` reference;
part environment/disposition/location/flags are all zero. Values below were
parsed from supplied retail cache maps (`b30.map`, `a10.map`, `b40.map`,
`putput.map`).

| Weapon route | Effect root → part-0 JPT | Falloff / cutoff / cutoff-scale | Core; min / lower / upper | Category / damage flags | Other verified parts |
|---|---|---:|---:|---|---|
| Rocket launcher | `weapons\\rocket launcher\\effects\\rocket explosion` → `weapons\\rocket launcher\\explosion` | 0.5 / 2 / 0 | 0.6; 80 / 300 / 330 | 4 high-explosive / `0x20` detonates-explosives | zero-damage frag shock wave, explosion sound, particle control, decal, light |
| Fuel Rod Gun and Hunter fuel rod | `weapons\\fuel rod gun\\effects\\explosion` → `weapons\\fuel rod gun\\explosion` | 0.5 / 1.5 / 0 | 0; 40 / 75 / 75 | 4 high-explosive / `0x21` owner-immune + detonates-explosives | zero-damage frag shock wave, sound, particle control |
| Scorpion primary | `vehicles\\scorpion\\shell explosion` → same-named JPT | 1.5 / 3.25 / 0 | 0; 80 / 351 / 351 | 8 mounted-weapon / `0x20` detonates-explosives | zero-damage frag shock wave, sound, particle control, decal, light |
| Banshee secondary | `vehicles\\banshee\\fuel rod explosion` → same-named JPT | 1 / 2 / 0 | 0; 40 / 75 / 75 | 4 high-explosive / `0x21` owner-immune + detonates-explosives | zero-damage frag shock wave, sound, particle control |
| Wraith mortar | `vehicles\\wraith\\effects\\wraith mortar explosion` → `vehicles\\wraith\\explosion` | 1.5 / 2.5 / 0 | 0; 50 / 90 / 110 | 8 mounted-weapon / `0x20` detonates-explosives | zero-damage Wraith shock wave, sound, particle control |
| Flamethrower and Gravity Rifle | `weapons\\flamethrower\\effects\\flame detonation` → `weapons\\flamethrower\\explosion` | 0.4 / 0.4 / 0 | 0; 10 / 10 / 10 | 7 flame / `0x80` flaming-death | sole damage-bearing part in the one-event graph |

**Verified CE ordering and RNG/ownership.** Effect creation retains an owner
object; `effect_set_event` seeds event 0 and selects global gameplay RNG for
`must_be_deterministic` effects (`effects.c:1500-1540,2810-2845`). The range
helper always advances the LCG even for equal bounds (`random_math.c:217-225`),
so zero-width delay and duration ranges still consume deterministic draws.
Event completion checks skip fractions for subsequent events; these one-event
graphs do not enter that loop. Part execution follows tag order; for a JPT
part CE copies owner player/object/team when available, uses the effect scale
and location/origin/epicenter/forward, then calls AoE damage
(`effects.c:1740-1761,1800-1897`). Other presentation parts may have separate
random work.

AoE queries objects in a sphere of `cutoff_radius` and processes returned
order. Units with nonzero `area_of_effect_core_radius` receive four offset LOS
ray checks; otherwise the source performs an epicenter-to-bounds-center LOS
test (`damage.c:1933-1964,2374-2485`). It then applies invisibility/LOS,
owner immunity, friendly-team filtering, and special infection-form gates;
eligible targets get center-distance falloff. If JPT flag bit 0 is clear,
the falloff factor becomes `damage.scale`; `object_cause_damage` draws
`real_random_range(lower,upper)` and combines it with minimum as
`(1-scale)*minimum + random*scale`, before multiplier, actor difficulty,
game-mode modifiers and shield/body/material handling
(`damage.c:2500-2596,1435-1500,1510-1840`). Fuel Rod/Banshee `0x21` blocks
self-damage but not teammates; team immunity is separate damage flag bit 3
(`0x8`), absent here. Rocket/Scorpion/Wraith do not set owner immunity. These
are source/tag facts; exact port object order requires runtime traces.

**Inference — PS2-safe record.** Offline-convert tag references to compact
IDs; do not resolve tag paths during collision. A 48-byte aligned damage-part
record can hold effect/profile IDs, part index/flags, JPT flags, damage flags,
side-effect/category, falloff/cutoff/cutoff-scale/core radius, and minimum/
lower/upper damage. Keep each unique 33-entry material multiplier array
shared by JPT ID (132 bytes as float32, or validated fixed-point), not copied
into projectile instances. Put sound/particle/decal/light IDs in a separate
bounded presentation table. Static target/effect caps and no per-hit heap
allocation are appropriate for EE; the Rocket's 0.6 core radius implies the
four-ray unit LOS case. Exact caps/encoding need profiling and are not claimed
as measured PS2 results.

**Unsupported/runtime blockers.** Current shot profiles do not execute `effe`
graphs or serialize part order, AoE radii/scales, 33 material modifiers or
damage flags. Missing CE parity also includes object-sphere order, owner/team
ancestry, actor attribution, LOS policy/ray limits, breakable-surface AoE,
difficulty/gametype multipliers, shield/body ordering, deterministic global
RNG interleaving, and complete audiovisual parts. Needler's attached 10/10/10
JPT is a distinct attachment/supercombine path, not one of these AoE routes.
Tags/source establish layout and algorithm, but parity/resource behavior needs
instrumented reference traces plus EE/emulator runs.
