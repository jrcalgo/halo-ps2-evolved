# M13 combat implementation record

**Status: incomplete, in progress (2026-10-18).** The governing acceptance criteria are in [M13 of the plan](../plans/0.native-ps2-halo-hybrid-port.md#16-milestone-m13--implement-weapons-projectiles-and-damage).

The first checkpoint adds `src/game/combat.{h,c}`, a bounded, fixed-tick combat state machine. It has four player slots, two carried weapon slots each, 16 targets, 16 pickups, 32 projectiles, and 32 presentation events per player. The host fixture checks pickup, equip, semi-automatic and automatic fire, magazine depletion, reload, shield spill into health, death, melee, grenade throw, explosion, projectile-pool saturation, and equal results when presentation work occurs between identical simulation ticks. A grenade uses a separate explosive definition, independent of the held weapon. The C source has no heap allocation.

This code is a **synthetic prototype**, not a port of Halo's weapon semantics. Its pistol, assault rifle, rocket, and grenade test values were chosen for exercising transitions; they are not retail constants. The ray/sphere test does not query Blood Gulch's collision BSP, the target array is not the M12 player object system, there is no player-versus-player damage, and the module has not been linked into or run on an EE ELF. It therefore cannot close M13 or serve as the production gun implementation. The pinned Halo CE source is authoritative for one-for-one gun behavior. PS2 work must preserve those outcomes while using the PS2 submodule's renderer, pack, memory, and platform boundaries. A clean-room substitute is acceptable only after equivalence is demonstrated against the source and reference scenarios.

## Source audit and full weapon scope

The pinned `halo-64` source has `source/items/weapons.c`, `weapon_definitions.h`, `projectiles.c`, and `source/objects/damage.c`. The original reload path uses `rounds_total` and `rounds_loaded` and derives reload duration from a first-person animation; some weapons can reload again for another increment. The firing path resolves trigger, magazine, projectile and damage-effect tags. The current prototype instead uses a simple reserve count and a fixed reload tick field. Those differences must be reconciled from tags and source before reference matching.

The locally supplied decompressed Xbox Blood Gulch map indexes these `weap` tags:

| Group | Weapon tags / required behavior |
|---|---|
| Human handheld | assault rifle, pistol, shotgun, rocket launcher, sniper rifle, flamethrower; pellet count/spread and shotgun per-shell reload need distinct state |
| Covenant handheld | plasma rifle, plasma pistol, needler, gravity rifle; heat/overheat, charge, tracking and supercombine need distinct state |
| Vehicle-mounted | Warthog gun, Scorpion cannon, Ghost gun; mount ownership and projectile/damage paths need coverage |
| Objective items | ball and flag; pickup/carry/drop/melee interactions need coverage, though they are not ordinary guns |
| Grenades | frag and plasma `eqip`/`proj` pairs; fuse, bounce, attachment and blast behavior need coverage |

This is the Blood Gulch inventory only. Before M13 closure, inventory the other multiplayer maps and campaign-required tags so “all weapons” means all relevant retail families, not merely those present on Blood Gulch. The current state machine implements none of the weapon-specific behaviors above faithfully. Vehicle weapons, objective items, and grenades need separate command and ownership paths. Portability of original source should be tested in a narrow R5900 compile closure before replacing those behaviors with approximations.

`tools/audit_weapons.py` now reads the verified 32-bit magazine and trigger layouts through the pinned `halo-ps2` tag index. It bounds-checks reflexives, links projectile references by tag ID, and writes only an ignored report at `build/combat-m13/weapons.json`. Blood Gulch has 15 weapon tags: 13 firing weapons plus ball and flag. The audit finds the source tag fields for pistol/assault-rifle magazines, shotgun's 15 projectiles per shot, the plasma pistol's two triggers and 0.6-second charge field, and Scorpion's two triggers. The tag field `reload_seconds_tag` is **not** yet the authoritative runtime reload duration: the original code uses first-person animation time. The tag audit is a conversion input, not weapon-behavior proof.

## Verification and remaining gates

`python3 -B -m unittest discover -s tests -p test_combat.py -v` and `test_weapons_audit.py` pass. The combat test compiles with C11 warnings as errors. An AddressSanitizer/UndefinedBehaviorSanitizer run also passes with leak detection disabled because LeakSanitizer cannot run under the command runner's tracing. `src/game/combat.c` cross-compiles with the pinned `mips64r5900el-ps2-elf-gcc` 15.2.0 as an object. After rebuilding the stale portal viewer, `python3 tools/test_host.py` passes 55 project tests and 12 upstream synthetic scripts; the four render tests launched visible PCSX2 runs. The full-suite result is host/emulator regression evidence, not an integrated combat run. The log is retained privately under `build/combat-m13/test-host.log`.

Next: derive each weapon's magazine, triggers, projectile and damage references from retail tags into a versioned private conversion report; compare tick transitions with the pinned original source and xemu where possible; integrate combat commands and state with the M12 EE player and collision world; implement BSP occlusion, player damage, recharge, death and respawn; exercise all families, simultaneous explosions and pool limits; run visible PCSX2 interpreter/recompiler scenarios and independent replay qualification. Physical-console qualification remains M23.
