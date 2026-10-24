# M2 Step 7 — CE multiplayer sound-scenery placement/lifecycle evidence

Status: focused host-runtime slice passed; this does not close Step 7.

## Result

Added a package-backed fixture that compares CE's sound-scenery scenario-object path against the raw sound-scenery placement and palette blocks in all 13 pinned stock Halo CE multiplayer maps. The fixture calls the actual CE `object_new_from_scenario` implementation and actual `sound_scenery_new` / `sound_scenery_delete` callbacks. Its narrow test seams replace the live object-pool allocation and type-placement boundary; it is not a full simulation, audio, or PS2-target test.

Map census: 13 placements total—Blood Gulch 2, Beaver Creek 8, Damnation 3; the other ten maps have zero. There are three nonempty sound-scenery palettes, one per map with placements. Every source placement has an unnamed entry (`name_index == NONE`) and an in-range palette index; the palette group is `ssce` and its reference resolves to a sound-scenery tag. Each map is tested across both scenario-load cycles in the inherited 13-map host lifecycle matrix. For every placement, the test independently checks all ten raw 32-bit words, selected palette reference, CE-generated position/orientation/variant, object placement callback, and the sound-scenery callback lifecycle.

The source explains the scope of this result. `object_new_from_scenario` validates palette/name state, obtains the referenced definition, builds placement data from the scenario position/rotation/variant, creates the object, then places it (`submodules/halo-ce-universal/source/objects/objects.c:4035`). The sound-scenery definition registers the `ssce` group, scenario block offsets and stride, and the new/delete callbacks (`submodules/halo-ce-universal/source/objects/object_types.c:375`). CE's `sound_scenery_new` sets the object's shadowless flag; delete does nothing (`submodules/halo-ce-universal/source/sound/sound_scenery.c:30`). Thus this fixture validates object placement/lifecycle setup, not an emitted sound. No SPU2 request, sound playback, runtime audio asset, real object pool admission, in-game rendering, or EE/PCSX2 result is claimed.

## Reproduction and artifacts

Command (run outside the restricted sandbox because host ILP32 execution can fail with SIGSYS):

```sh
HCU_MP_CAPACITY_RETENTION_DIR=build/m2-mp-sound-scenery-runtime-final \
  python3 -m pytest -q tests/test_hcu_mp_sound_scenery_runtime.py -x
```

Result: `1 passed in 85.89s`. The test compiles an ILP32 host harness and runs the inherited package-backed CE scenario/BSP matrix for all 13 stock maps and two cycles. The relevant persistent run output is `build/m2-mp-sound-scenery-runtime-final/run.log`; it contains 26 per-map-cycle success rows. This binary is a host test artifact, not the PS2 game ELF.

Source/map/package identities are retained in `build/m2-mp-sound-scenery-runtime-final/manifest.json` (SHA-256 `dbb10b83d410806b466e42c7aa92e4c87253641b7c84b4a147ef55ce54adaf27`). Pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The 13 decompressed stock map and HP2 package hashes are listed in that manifest.

Run artifact hashes:

- `run.log`: `1cc3825a8fc19f0c491e4d03664b4eed36bd616ecb8ac910a9d2f3d27670dc74`
- host fixture executable: `fc3738cc06a7562eaa911e792061184e1569b65e99cee6a2d65b4efac26a43a6`
- test: `tests/test_hcu_mp_sound_scenery_runtime.py`, SHA-256 `659ab98a333118719c39573e8a34b6c8d070e13c5bdd771baf6db7d1ce766736`
- C assertions: `tests/hcu_mp_sound_scenery_runtime_host32.c`, SHA-256 `0e192d100408dec2633bda914c79e4320b9804b7f4c741e9bdc31c78199f375b`

## Residual Step 7 gaps

- Sound-scenery tag references and placement are covered; actual sound selection, sound-tag resolution/playback, SPU2 behavior, and lifecycle interaction with an admitted production object pool are not.
- This is host execution against package-backed map payloads, not target-sized BSP/tag arena evidence.
- The source parser currently requires unnamed sound-scenery placements and `ssce` palette groups; it deliberately fails if future/source variants violate those assumptions rather than silently accepting them.
- This result covers only the sound-scenery placement consumer. It does not complete the BSP field/consumer inventory, collision topology coverage, relocation failure atomicity, or Step 8 capacity gates.
