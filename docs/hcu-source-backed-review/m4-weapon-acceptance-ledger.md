# M4 weapon and objective acceptance ledger

**Disposition: preparation artifact only; M4 not accepted.** This report is
Group H's source/evidence inventory for steps 17–18 of
[`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md#remake-m4--replace-duplicate-m13-combat).
It is governed by the M13 acceptance scope in
[`plans/0.native-ps2-halo-hybrid-port.md`](../../plans/0.native-ps2-halo-hybrid-port.md#16-milestone-m13--implement-weapons-projectiles-and-damage).
M3 collision ownership and the CE production tick are prerequisites; this
ledger does not claim either exists. `source/tag audit passed` means only that
the cited source path and supplied-map tag inventory were inspected. `Open`
means no qualifying M4 trace is present. A parent `WORLD_PLAY` trace is never
an HCU M4 pass.

## Evidence pins and qualification rules

The checked-in M13 record identifies the HCU and halo-64 source pins and the
retail XISO SHA-256; see [`docs/combat.md`](../combat.md#source-audit-and-full-weapon-scope)
and [`docs/m13-step10-fuel-rod-flight-investigation.md`](../m13-step10-fuel-rod-flight-investigation.md#evidence-identity-and-method).
The current combined HCU plan snapshot pins parent `70e2ed0c`, HCU `6933490b`,
and halo-ps2 `71183bb0` ([`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md#finish-hcu-remake-m2-m3-and-m4)).
Those identities are not interchangeable with the older M13 play ELF evidence.
The private all-map inventory at `build/combat-m13/all-map-weapons.json` is
ignored build output, not a checked-in acceptance artifact. Its checked-in
summary reports 24 maps and 23 distinct weapon paths; tag presence and decoded
fields do not establish runtime parity.

Source behavior references (pinned HCU source paths):

| Concern | CE source and behavior boundary |
|---|---|
| Weapon creation and magazine/trigger state | [`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c#L845) `weapon_new`; initializes datum state using the loaded definition. |
| Projectile creation/origin/owner | [`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c#L2373) `trigger_create_projectiles`; resolves firing origin, owner and target, then calls `object_new`. |
| Trigger cadence, ammo, effects, misfire | [`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c#L2591) `weapon_trigger_fire`; ammo gates/consumption and effect/misfire RNG order. |
| Begin, charge, overheat, underwater gate | [`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c#L2863) `weapon_trigger_begin_firing`; rejects invalid magazine/overheated/underwater cases and dispatches charge/overload/fire. |
| Charge release and normal trigger progression | [`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c#L2963) `weapon_trigger_release_charge`; [`weapon_update`](../../submodules/halo-ce-universal/source/items/weapons.c#L3016) owns per-tick weapon transitions. |
| Projectile setup/flight/collision | [`projectiles.c`](../../submodules/halo-ce-universal/source/items/projectiles.c#L521) `projectile_new`, [`projectile_update`](../../submodules/halo-ce-universal/source/items/projectiles.c#L665), and collision response in the same routine. |
| Detonation, attached damage and effects | [`projectiles.c`](../../submodules/halo-ce-universal/source/items/projectiles.c#L1337) `projectile_detonate`; selects ordinary/super-combine effects and attached damage. |
| Damage material/region, shield/body/death | [`damage.c`](../../submodules/halo-ce-universal/source/objects/damage.c#L1680) `object_cause_damage` resolution; target collision-model nodes select damage parts/materials, followed by unit vitality handling. |
| Melee | [`weapons.c`](../../submodules/halo-ce-universal/source/items/weapons.c#L839) `weapon_melee_attack` is empty in the pinned source. Energy-sword lunge/melee therefore needs an explicitly marked `port:` implementation and parity oracle; a call to this stub is not sword behavior. |

The core CE source defines semantic paths; the 23 tag paths below come from
the supplied retail maps. Paths are canonicalized to lowercase backslash form.
The exact all-map set is also checked by
[`test_m4_weapon_acceptance_ledger.py`](../../tests/test_m4_weapon_acceptance_ledger.py).

## Per-tag ledger

Every path has `M4 integrated: OPEN` because no current HCU guest combat trace
is recorded for it. The `tag/source` column is an audit result, not a behavior
pass. “Parent diagnostic only” explicitly excludes HCU qualification.

| Canonical `weap` path | Source/tag and current evidence | Cadence/ammo/reload/charge | Material/region/shield/death | Pool, AoE/effects, ownership | Replay/render invariance | M4 status |
|---|---|---|---|---|---|---|
| `weapons\assault rifle\assault rifle` | Tag/profile audited; parent live-biped PCSX2 cadence/damage smoke is recorded in M13, not HCU. | Partial parent cadence; reload open; HCU untested. | Parent smoke only; material/region parity open. | Exhaustion/effects/ownership open. | HCU host+guest replay open. | OPEN |
| `weapons\pistol\pistol` | Tag/profile audited; parent live-biped PCSX2 smoke is recorded in M13, not HCU. | Partial parent cadence; reload open; HCU untested. | Parent smoke only; material/region parity open. | Exhaustion/effects/ownership open. | HCU host+guest replay open. | OPEN |
| `weapons\shotgun\shotgun` | Tag/profile audited; parent PCSX2 smoke accounts for 15 pellets against actor/BSP, not HCU. | Pellet discharge partial on parent; shell reload open; HCU untested. | Parent counts actor/BSP events only; material/region parity open. | Multi-pellet exhaustion, effects and owner filters open. | HCU host+guest replay open. | OPEN |
| `weapons\sniper rifle\sniper rifle` | Tag/profile audited; no qualifying HCU trace. | Cadence, latch/release, reload, zoom open. | Penetration, material/region, headshot/shields/death open. | Pool and effects open. | Open. | OPEN |
| `weapons\rocket launcher\rocket launcher` | Tag/profile and response-enum mapping audited; no HCU AoE trace. | Cadence/reload/latch open. | Direct and blast damage/region/shields open. | Detonation exists as source semantics; runtime AoE, LOS/owner/team filters, effects and pool exhaustion open. | Open. | OPEN |
| `weapons\plasma pistol\plasma pistol` | Trigger-pair host model and selected parent trigger dispatch are partial; no HCU guest trace. | Charge/release host partial; heat, overcharge, misfire and ammo/reload full parity open. | Impact/material/region/shield/death open. | Charged effects, pool and owner filters open. | HCU replay open. | OPEN |
| `weapons\plasma rifle\plasma rifle` | Tag/profile only for M4. | Cadence, heat/overheat, misfire, ammo/reload open. | Damage/material/region/shield/death open. | Effects/ownership/exhaustion open. | Open. | OPEN |
| `weapons\needler\needler` | Separate source/tag investigation and partial parent steering/node-attachment evidence; source-parity acquisition/supercombine remains open. | Cadence/ammo/reload tag audit; integrated cadence and ammo trace open. | Attachment and fuse damage incomplete; region/shield/death open. | Supercombine, effects, simultaneous detonation and pool isolation open. | Current-build HCU replay and render-schedule test open. | OPEN |
| `weapons\flamethrower\flamethrower` | Tag/nested damage references inventoried; no integrated contact path. | Continuous firing, ammo/heat/reload open. | Contact material/region/shield/death open. | Continuous effects/audio and pool behavior open. | Open. | OPEN |
| `weapons\fuel rod gun\fuel rod` | Deep source/tag flight audit exists; parent diagnostic profile is not M4. | Trigger charge/cadence and rounds-per-shot require HCU trace; reload open. | Air/water flight tag values audited; BSP medium transition, material response and damage remain open. | Tagged detonation/AoE, owner/LOS filters, effects and pool behavior open. | HCU interpreter/recompiler replay open. | OPEN |
| `weapons\gravity rifle\gravity rifle` | Tag/profile identifies a flame-projectile family; no HCU runtime trace. | Cadence/ammo/heat/reload open. | Weapon-specific contact/impact and damage regions open. | Its own tagged projectile/effect/owner/exhaustion path open; do not alias flamethrower. | Open. | OPEN |
| `weapons\energy sword\energy sword` | Tag path audited; CE `weapon_melee_attack` is empty, so PS2 melee behavior requires explicit source-informed implementation. | No ordinary magazine; arbitration, cooldown and attack timing open. | Lunge hit region, shields/body/death open. | Melee effects/ownership and bounded state open. | Animation-tick and render invariance open. | OPEN |
| `weapons\flag\flag` | Objective weapon path present; not an ordinary firearm. | Pickup/carry/drop state open. | Melee/object collision and damage semantics open. | Team/objective ownership, scoring and reset open. | Replay/render invariance open. | OPEN |
| `weapons\ball\ball` | Objective weapon path present; not an ordinary firearm. | Pickup/carry/drop state open. | Collision and damage semantics open. | Oddball possession/scoring/ownership/reset open. | Replay/render invariance open. | OPEN |
| `weapons\fuel rod gun\hunter fuel rod` | Actor weapon/tag path audited; parent camera-fired route is not equivalent. | Actor cadence/aim/charge/ammo open. | Actor-origin collision/material/damage/shield/death open. | Actor owner/team filters and detonation/effects/pool open. | Open. | OPEN |
| `characters\sentinel\sentinel` | Sentinel weapon/tag path audited; no actor-origin HCU firing trace. | Actor cadence/aim/ammo open. | Beam damage/material/region/shield/death open. | Owner/effects/exhaustion open. | Open. | OPEN |
| `vehicles\warthog\warthog gun` | Vehicle weapon/tag path audited; mount origin absent from M4 evidence. | Mount cadence/ammo open. | Vehicle shot collision/damage region/shield/death open. | Gunner ownership/team filters and effects/pool open. | Open. | OPEN |
| `vehicles\ghost\ghost gun` | Vehicle weapon/tag path audited; mount origin absent from M4 evidence. | Mount cadence/ammo open. | Collision/damage region/shield/death open. | Owner/effects/pool open. | Open. | OPEN |
| `vehicles\scorpion\scorpion cannon` | Tag profile and parent trigger-pair routing partial; mounted firing origin is fail-closed outside its host profile. | Primary/secondary magazine routing host partial; mounted cadence/reload open. | Shell/secondary collision and damage region/shield/death open. | Ownership, shell AoE/effects and exhaustion open. | HCU guest replay open. | OPEN |
| `vehicles\banshee\banshee gun` | Vehicle weapon/tag path audited; mount origin absent from M4 evidence. | Mounted cadence/ammo open. | Collision/material/region/shield/death open. | Owner/effects/pool open. | Open. | OPEN |
| `vehicles\wraith\wraith mortar` | Vehicle weapon/tag path audited; no mounted projectile trace. | Cadence/ammo/reload open. | Mortar collision, detonation, material/region/shield/death open. | AoE, owner/team filters, effects and exhaustion open. | Open. | OPEN |
| `vehicles\c gun turret\c gun turret gun` | Turret weapon/tag path audited; no mount/marker trace. | Cadence/ammo open. | Collision/material/region/shield/death open. | Turret owner/effects/pool open. | Open. | OPEN |
| `vehicles\c_dropship\cd_gun\cd gun turret gun` | Turret weapon/tag path audited; no mount/marker trace. | Cadence/ammo open. | Collision/material/region/shield/death open. | Turret owner/effects/pool open. | Open. | OPEN |

## Cross-arsenal acceptance matrix

| Required evidence | Present evidence | Disposition |
|---|---|---|
| CE source function and tag crosswalk | M13 source/tag audits cover the all-map 23 `weap` paths and selected tag-derived profiles. | **Source/tag audit: passed. Runtime behavior: open.** |
| Cadence, reload, charge/release, heat and ammo | Parent pistol/rifle/shotgun smoke and selected-trigger host models cover narrow cases. | **Partial parent/host evidence only; HCU parity untested.** |
| Projectile material and hit region | CE source describes material response and collision-model region selection; parent M13 implements some potential-response logic. | **No comprehensive HCU target/material trace. Open.** |
| Shield depletion, body spill, death/cleanup | Synthetic parent combat tests and limited parent live-biped smokes exist. | **Not proof of CE `object_cause_damage` path. HCU open.** |
| Projectile/effect pool exhaustion isolation | Parent synthetic combat prototype tests its own pool; no M4 CE shared-routine fixture has been identified. | **Not tested for HCU.** |
| Simultaneous explosions, ownership and filters | CE detonation source is inspected; integrated event ordering/owner filters have no qualifying HCU trace. | **Open.** |
| Replay under interpreter/recompiler and varied render schedules | Older parent diagnostic traces exist. | **No current HCU gameplay trace; open.** |
| PS2 `dynamic_simulation` capacity | Budget is 2,621,440 bytes in [`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md#ownership-and-budget). Current static ELF checks do not measure combat runtime high-water. | **No actor/projectile/effect high-water evidence; open.** |

### Exact pool-isolation fixture block

Do not add a test that only exercises the parent `combat_world`, `shot_world`,
or synthetic fixed target: those are different ownership/pool implementations
and cannot establish CE pool isolation. The reusable CE object/projectile/effect
allocation routine must first be callable from a host fixture with deterministic
failure injection at the actual fixed-pool allocator boundary. Once available,
the fixture should:

1. Construct a valid CE object world, a live unrelated target with sentinel
   transform/velocity/vitality, and a deterministic RNG state/tick.
2. Fill the actual CE projectile pool to its configured capacity through CE's
   projectile creation path; snapshot canonical object handles/generations,
   transforms, velocity, health/shields, tick and RNG.
3. Attempt one additional weapon shot through CE trigger update. Assert the
   rejected projectile allocation is reported as failure, does not consume
   ammo or mutate the unrelated sentinel (unless the pinned source explicitly
   consumes ammo before allocation), does not corrupt any live pool datum, and
   advances tick/RNG exactly as CE source dictates.
4. Repeat with effect-pool exhaustion and with two same-tick explosive
   projectiles; compare canonical damage/event order against an unexhausted
   reference and prove failure is isolated to the failed event.
5. Run the same seed/input/tick sequence with zero, one and multiple snapshot
   publications between ticks. Hash simulation-only fields; exclude render and
   audio output.
6. Record capacity, high-water, failed-allocation count, `dynamic_simulation`
   arena bytes, and reserved 5,767,168-byte region unchanged.

**Current blocker:** Group H found no single checked-in callable CE weapon →
projectile → allocator routine that this new test can exercise without wiring
M3/M4 production integration, and this group's write set forbids production
simulation changes. Therefore step 18's fixture is **not added**; step 18 stays
open until the real shared routine and deterministic allocator boundary are
available. This is an interface dependency, not permission to substitute a
parent synthetic model.

## Evidence / test performed for this report

The new host-only test checks that this ledger contains exactly the 23
canonical retail weapon paths from the current checked-in M13 inventory summary,
that every path is marked open for integrated M4 evidence, that all required
acceptance dimensions and CE source functions are named, and that the report
does not misrepresent the synthetic/parent pool test as CE proof. It is a
documentation-integrity check only; it does not execute weapon simulation.
