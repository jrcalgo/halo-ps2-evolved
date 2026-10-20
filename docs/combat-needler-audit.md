# M13 Step 8 weapon-family audit: Needler

**Status:** read-only source/tag investigation; no gameplay edits and no parity
scenario is finalized by this report. This is a separate Step 8 family report
as required by [M13 in the native PS2 port plan](../plans/0.native-ps2-halo-hybrid-port.md#16-milestone-m13--implement-weapons-projectiles-and-damage).

## Scope and evidence identity

- Behavioral source: pinned `halo-ce-universal` commit `7524ba61`; the relevant
  definitions and projectile/weapon code are also present in pinned
  `halo-64` commit `17541f4`. Halo CE is the authority; matching code in the
  portable fork is a comparison, not a second retail oracle.
- Tag evidence: local user-supplied Xbox retail Blood Gulch map at
  `data/retail/weapon-audit-maps/bloodgulch.map`, SHA-256
  `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`.
  The tag index/path and 32-bit reflexive layouts were read with the existing
  `halo-ps2` `MapData`/`Region` reader and the bounds-checked field offsets in
  `tools/play_weapons.py`; the independent inventory is
  `build/combat-m13/all-map-weapons.json` (ignored local output). Retail bytes
  and derived tag payloads remain private and are not reproduced here.
- Relevant resolved Blood Gulch records: `weapons\needler\needler` (`weap`),
  `weapons\needler\needle` (`proj`),
  `weapons\needler\effects\explosion` (`effe`),
  `weapons\needler\effects\needle detonate` (`effe`),
  `weapons\needler\impact damage` (`jpt!`),
  `weapons\needler\detonation damage` (`jpt!`), and
  `sound\sfx\impulse\impacts\needler_projectile` (`snd!`).
- REA shipped-artifact evidence: not applicable to this scoped audit. No Needler
  executable/disc behavior was inferred from a shipped artifact; the findings
  below are explicitly source- and tag-derived.

## Source behavior and tag-backed profile

The Needler is not just a fast bullet with a cone. Its projectile carries three
coupled special behaviors: a guided target, attachment to collision objects,
and an attached-projectile combining/explosion path. Relevant exact source
locations are in `submodules/halo-ce-universal/source/items/`:

| Behavior | CE source evidence |
|---|---|
| Trigger and projectile tag layouts | `weapon_definitions.h:112-165`; `projectile_definitions.h:45-105` |
| Trigger projectile creation, cone error, target acquisition/assignment | `weapons.c:2373-2588`, especially `2476`, `2531-2557`, `2565-2578` |
| Timer/arming initialization and initial velocity | `projectiles.c:521-562`, `584-590` |
| Target steering | `projectiles.c:753-814` |
| Timer start rules and tick progression | `projectiles.c:695-723` |
| Material response dispatch and attach behavior | `projectiles.c:1501-1535`, `1786-1846` |
| Needle-combine counting and super-detonation choice | `projectiles.c:1357-1417` |
| Attached damage at detonation | `projectiles.c:1449-1463` |

The retail Needler has one trigger. Its `weap` trigger record says: initial and
final rate 3 and 10 shots/s; rate acceleration and deceleration fields 0.5 and
0.15 s; magazine index 0; one round and one projectile per shot; no charge,
heat, or age increment; inner error 2° and lower/upper outer error 4°; and
runtime rate acceleration/deceleration 0.06666667 s and 0.22222222 s, with
runtime error acceleration/deceleration 0.06666667 s and 1 s. These are the
decoded tag values, not asserted tick outcomes. The magazine record has 80
initial/maximum total rounds, 20 loaded maximum, 20 rounds reloaded, and a
1-second tag reload field. As elsewhere in CE, that tag field alone does not
prove the in-game reload duration; source animation/state transitions must be
checked.

The `proj` tag has flags `0x0b` (bits 0, 1, and 3 in the pinned
`projectile_definitions.h` enum: orient along velocity, ballistic aim,
super-combining explosion), detonation timer start mode 2 (when at rest),
timer lower/upper 0.75 s, minimum velocity 0.06666667, maximum range 20,
air-gravity scale 0, initial/final velocity 0.13333334, and guided angular
velocity 1.57079637 rad/s. Arming time is 0. The `super_detonation` effect is
`weapons\needler\effects\explosion`; ordinary projectile effect is
`weapons\needler\effects\needle detonate`; flyby sound is
`sound\sfx\impulse\impacts\needler_projectile`.

The projectile has 33 material-response records. In the decoded table, the
default response is CE enum value 4 (attach) for materials 0-9, 11-15, 17,
19-27, 30, and 31. Materials 10, 16, 18, and 32 use value 2 (reflect); 28 and
29 use value 3 (overpenetrate). This is distinct from the port's `SHOT_*`
enumeration and must be translated explicitly. The response records have zero
`initial_friction`; their attach/reflect/overpenetrate action is the meaningful
Needler collision fact. Materials 21 and 22 (the current cyborg body and shield
profile material slots) both attach. The projectile references `impact damage`
and `detonation damage`: tag-derived damage bounds for impact are 0/0/0, while
attached detonation damage is 10/10/10 with body/shield material modifiers 1/1.
Thus applying the impact tag's zero to vitality is not a substitute for the
later attached-damage event.

In CE, `trigger_create_projectiles` asks `player_aim_projectile` for an
aim-assist target when firing from a player, then stores that target on the new
projectile (`weapons.c:2476`, `2575-2578`). Every projectile with a valid target
and positive guided angular velocity is steered each update (`projectiles.c:
753-814`); the Needler value makes the nominal rotation increment
`pi/60` radians per 30-Hz simulation tick before player-difficulty scaling.
Steering uses the target center of mass and a deterministic periodic wander
offset, attenuated inside 10 units and zeroed at 2 units. The tag value alone
does not imply every needle homes: target acquisition must return an object.

On contact with an attach-response material, CE sets the projectile at rest,
attaches it to a collided object when applicable, and starts the timer when it
is resting. The Needler's 0.75-second timer is 22.5 nominal 30-Hz ticks; the
exact firing/update order and float threshold determine the observed detonation
tick and must be measured against source. A later needle scans siblings on the
same parent; when it finds at least six eligible same-definition projectiles,
it marks the super-combine path. The explosion path further gates the large
combine on the parent being a biped and either non-player-controlled or in a
running game engine (`projectiles.c:1378-1417`). Detonation applies the
attached-damage tag to the parent (`1449-1463`). Do not assume a universal
“seven needles always cause damage” rule without accounting for parent kind,
game mode, attachment success, update ordering, and projectile lifetime.

## Current port coverage and concrete gaps

This audit found the following current coverage in the worktree; it is not an
acceptance claim:

- `tools/play_weapons.py` extracts the Needler trigger, magazine, primary and
  selected-trigger projectile records, material-response codes, friction,
  potential-response fields, trigger cone values, attached-damage values,
  guided angular velocity, and firing-effect metadata. `tests/test_play_weapons.py`
  byte-checks these packed records; the selected Needler loader verifies
  material-2 potential reflection and its 25-degree upper angle bound, plus the
  1.57079637 rad/s guided angular velocity.
- `src/game/arsenal.c` plus `tests/test_arsenal.py` exercise all 23 records in a
  host firing model. The Needler test only requires a second shot before tick
  10 and exactly 20 shots before the clip is empty; it does not verify the
  source-derived full cadence/error RNG trace or projectile behavior.
  `tests/test_gun.py` also has a basic Needler magazine/reload smoke. Those are
  useful candidate fixtures, not CE-parity proof.
- The integrated EE path can dispatch selected trigger records and create
  camera-origin projectiles (`src/game/play_ee.c:131-165, 299-331`). It caches
  projectile data into generic `shot_def` records in `src/game/play_fp.c`.
  Primary and trigger profiles now include CE projectile flags, timer start and
  bounds, attached damage, response/noise/friction fields, and all
  potential-response gates.
- `src/game/shot.c` maps CE response 4 to bounded attachment, stores an
  attached-target bit, starts the configured at-rest fuse, and emits the
  attached-damage event once at detonation. A host integration fixture verifies
  zero impact damage, the Needler's 0.75-second fuse (23 ticks at 30 Hz), one
  10-point attached event, and no duplicate event consumption. This is a
  static-target host association, not CE's object parent/node attachment model.
- `shot_tick` applies the tagged guided turn when a caller explicitly supplies
  a target within 2 units. This is the exact CE subcase where deterministic
  wander has zero scale; a host fixture checks the Needler's `1.57079637 / 30`
  radian tick turn and confirms displacement uses the pre-steering average
  velocity. The `PRJ1`/`PRJ2` value survives the selected cache. This is not
  live Needler behavior: the play fire call does not perform CE aim-assist
  target acquisition, and guidance farther than 2 units needs CE's generated
  periodic wander table plus identifier/time phase. The diagnostic sphere is
  not a retail biped and cannot host sibling needle children. Supercombine
  counting, parent/player/game-mode gates and super-detonation effects remain
  absent.

## PS2 implementation constraints

Preserve CE outcomes while keeping Needler state bounded. Do not add a dynamic
heap or allocate object state per tick. The current play projectile pool has
16 fixed slots; the Needler supercombine threshold is six existing
attached needles plus the triggering needle, so the pool can represent one
complete seven-needle sequence, but not many concurrent full sequences. Pool
failure behavior must be compared with CE `object_new` failure before defining
its semantics. Any parent links and sibling scan must remain fixed-capacity,
preserve definition identity, and avoid merging needles attached to different
targets.

Guidance adds per-active-needle target lookup, vector normalization/cross
products, periodic wander evaluation, and rotation. On R5900, measure worst-case
cost at the configured pool cap and avoid per-frame trigonometric work for
needles without a target. Any lookup table or fixed-point optimization must
preserve tested steering vectors and seed/tick outcomes. Keep additional state
within the M13 resident-gameplay allocation and report exact static/runtime
accounting; do not treat a small current `.bss` total as evidence that all
object, actor, effect, audio, and stack costs fit. Effect/audio side effects
should be deferred behind a presentation boundary and must not change combat
ordering or results.

## Candidate fixed-tick scenarios (not yet parity tests)

Finalize expected values by comparing the pinned CE source transitions and
tag records, then capture canonical state and random seed after each tick.

1. **Cadence, error, and ammunition:** start Needler idle with the retail
   magazine; hold primary for a bounded interval longer than 90 ticks; record
   each shot tick, rate/error fractions, cone draws/directions, loaded/reserve
   count, and reload transition. Include empty clip and interrupted reload.
2. **Targeted vs untargeted flight:** use identical initial projectile state
   once without an aim-assist target and once with a fixed target. Record
   per-tick position/velocity, wander input, steering angle, range and object
   pool state; include target deletion and a target crossing inside the 2-unit
   wander cutoff. Keep camera/muzzle origin and source random seed fixed.
3. **Single attachment and fuse:** collide with a 21/22-material target and a
   representative attach surface; assert attachment/rest state, no immediate
   impact vitality change, fuse tick count, detonation event and the exact
   10-point attached damage transfer. Contrast a material 10 reflection and a
   material 28/29 overpenetration.
4. **Combine threshold / ownership gates:** attach needles to one target in
   controlled order, checking the six-existing-plus-current boundary, ordinary
   detonation versus super-detonation, child timer/arming changes, single
   player biped, AI biped, and running multiplayer biped. Record effect and
   damage dispatch separately.
5. **Bounded pool and update order:** fill all slots with mixed live, attached,
   and expiring Needler projectiles; attempt additional shots and run simultaneous
   fuse expirations in stable object order. Assert no memory corruption and
   compare CE spawn/drop/deletion and sibling-count ordering.
6. **Render-schedule independence:** replay the same Needler scenario with
   normal, suppressed, and delayed presentation work and compare the canonical
   combat-state/seed hashes. This is only meaningful after the actor,
   attachment, and projectile state interfaces are stable.

## Open questions / next family-specific work

- What exact target-selection rules and tie-breaks does `player_aim_projectile`
  apply for a Needler shot, and what are the difficulty modifiers for each
  player/non-player target case? Read the corresponding aim-assist source and
  derive a deterministic fixture before implementing homing.
- Which actor/object types permit attachment and how are parent/child links,
  node attachment, deletion, and damage-team ownership updated on each path?
- Confirm full timer seed consumption and exact observed 0.75-second rest fuse
  tick; the two tag bounds being equal do not by themselves establish random
  draw behavior or event ordering.
- Establish impact and attached-damage behavior under shields, body material,
  invulnerability, and multiplayer team rules; current diagnostic vitality is
  not a generic actor damage implementation.
- Confirm material enum mapping from converted BSP/object collision data to the
  Needler's 33 tag response slots; raw integer equality must not be assumed
  across layouts.
- Audit needles-per-parent and pool exhaustion under the actual CE simulation
  schedule, then choose a PS2-fixed capacity from measurements rather than
  extrapolating from the current 16-shot viewer pool.
- Extend tag and host coverage to assert all above Needler fields and tag paths,
  then build a source-derived fixed-tick trace. Only after that trace passes
  should Step 9 designate it a parity scenario.

**Conclusion:** the bounded port now carries the Needler's tag-driven attach,
rest-fuse, attached-damage, potential material-response data and guided angular
velocity. Host fixtures cover attach/fuse/damage and the close-range
zero-wander steering subcase. That is not full Needler parity: aim-assist target
acquisition, generated wander behavior, real parent/child attachment, combine
ownership/order, and super-detonation effects remain absent. M13 must remain
incomplete until those behaviors and the broader runtime gates pass.
