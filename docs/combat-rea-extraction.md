# M13 Halo CE artifact and REA evidence

Status: exploratory evidence for the bounded M13 port, not a milestone acceptance
report. Values below are scoped to the supplied Xbox retail image and Blood
Gulch unless stated otherwise.

## Artifact chain and limitations

The source image is `/home/ai/Documents/Halo/Halo - Combat Evolved.xiso.iso`,
SHA-256 `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258`.
It is an Xbox XDVDFS/XISO image, not a standard ISO9660 executable/archive.
The container's root directory points to `default.xbe`; its `maps` directory
contains `bloodgulch.map`. The project already has a bounded XDVDFS reader in
`submodules/halo-ce-universal/port/linux/src/xiso.c`, and extracted/decompressed
map copies under ignored `data/retail/`. Existing M13 tests read those copies
through the pinned `halo-ps2` tag index. Neither the source image nor those
ignored extracted assets are modified by the tests.

REA 6.5.0 / Ghidra 12.1.4 could not load the XISO/XBE containers directly. To
inspect shipped code with REA, the XBE `.text` section was extracted as a raw
binary and opened as x86 at its observed virtual address `0x11000`. The XBE
SHA-256 is `6aebabb245d6a4951c00c790356a5aed2a84ff71fa37035078528343d7eae367`;
the exact raw section SHA-256 is
`e263c4e8af23f383f834217426b82d9a4766f6c127e4d1b816156d2f64eabd5e`.
This is derived input, not a successful direct analysis of the ISO. REA found
2,355 procedures and no defined strings in that section. Its dossier for
`FUN_00015bfd` (evidence `ev_9a4264fd17abe6368a4bd67e9331fd28bfd12bfe81517577fb11e91480b53416`)
shows an unnamed helper with stack-local 16-byte data and calls to other
unnamed helpers; no evidence ties it to combat. Consequently, no combat
behavior or gameplay constant is attributed to this Ghidra function. The XBE
has no useful combat symbols/strings in the analyzed section, so the shipped
code analysis is not enough to recover semantic gun/shield routines on its
own.

## Applicable retail values verified in map tags

These are binary tag observations from the supplied Blood Gulch map via the
existing tag reader, locked by `tests/test_play_weapons.py` and
`tests/test_vital.py`. They are not values inferred from REA pseudocode.

| Component | Retail observation | M13 use / boundary |
| --- | --- | --- |
| Cyborg vitality | body 75, shield 75 | Normalized runtime profile for the diagnostic target only. |
| Cyborg recharge | raw tag bits `0x3C088889` | Exact source velocity is retained; current recharge transition test checks the resulting step. |
| Cyborg shield stun | minimum applied shield damage 6; stun time 4.0 s | At this port's 30 Hz simulation rate, duration is 120 ticks; test checks below-threshold, hit and depletion behavior. |
| Cyborg indirect material | material index 1, damage material type 21, shield material type 22 | Current diagnostic sphere uses this indirect body material and the cyborg shield material; it has no collision-region attribution. |
| Cyborg indirect resistance | shield leak 0; shield multiplier 1; body multiplier 1 | Applied by the bounded cyborg profile. Other target/material profiles are not yet universally wired. |
| Pistol `weapons\\pistol\\bullet` | damage-definition material-21 body modifier 1.5; type-22 shield modifier 1.0 | Applied in the pistol-to-probe damage path. |
| Pistol projectile | initial velocity raw bits `0x41200001`; range 40; damage minimum/lower bound 25 | Retained in the projectile pack and exercised by the probe; impact-speed scaling is a distinct CE step. |
| Assault rifle `weapons\\assault rifle\\bullet` | type-21 body modifier 1.0; type-22 shield modifier 1.0 | Applied for the bounded probe path. |
| Assault-rifle projectile | damage minimum 10; initial velocity raw bits `0x412CCCCD` | Tag values are packed; complete flight and impact parity remain incomplete. |
| Pistol weapon/magazine | magazine max 12, initial reserve 60; trigger error acceleration `0.0666666701`, recovery `0.1666666716` | Pack extractor and tests read the retail fields; no assertion that all weapon transitions are complete. |
| Assault rifle weapon/magazine | magazine max 60, initial reserve 240 | Retail tag values are preserved in the play pack. |
| Shotgun | 15 projectiles per shot; initial reserve 24; enter/reload animation field 15 frames | Shot-count and spread paths use the tag data; source animation timing still gates reload parity. |
| Plasma pistol | 2 triggers; charge time `0.600000024` s; charged heat/value field 45; heat per round `0.159999996` | Both trigger records are packed; charge/release behavior is only partially integrated in EE. |

The broader inventory in `docs/combat.md` covers all 24 supplied maps and 23
distinct `weap` paths, but this report's damage-profile extraction is deliberately
limited to the Blood Gulch cyborg, pistol and assault-rifle bullet tags used by
the current diagnostic runtime. It must not be generalized to every actor,
weapon, collision material, melee path, explosion, sound, or visual effect.

## Behavioral source comparison

For semantic behavior, the pinned Halo CE source remains the usable source of
truth alongside tag values: `source/items/weapons.c` for trigger dispatch and
projectile creation; `source/items/projectiles.c` for flight/impact; and
`source/objects/damage.c` for shield/body damage and stun. Existing M13 checkpoint entries record the specific equations
and test fixtures compared against those files. REA's stripped XBE pass is a
secondary shipped-artifact check only, not source-level proof. The current EE
diagnostic sphere is not an actor or a substitute for Halo's collision model,
damage effects, sounds, or effects system.

## Reproduction / evidence

- `python3 -m pytest -q tests/test_arsenal.py tests/test_combat.py tests/test_gun.py tests/test_grenade.py tests/test_halo_random_directions.py tests/test_shot.py tests/test_vital.py tests/test_play_weapons.py`
- `WORLD_VARIANT=play python3 tools/build_world.py`
- `tests/test_vital.py` reads the collision and damage-effect values listed above.
- `tests/test_play_weapons.py` checks packed trigger, magazine, projectile, spread,
  material-modifier and animation data against the decompressed retail tags.
- REA evidence ID for the observed XBE-section procedure dossier:
  `ev_9a4264fd17abe6368a4bd67e9331fd28bfd12bfe81517577fb11e91480b53416`.

This evidence improves provenance for selected M13 inputs but closes no
completion gate by itself. Generic target damage/resistance, all-weapon runtime
parity, complete effect/audio behavior, varied-schedule replay, and physical
PS2 performance remain open.
