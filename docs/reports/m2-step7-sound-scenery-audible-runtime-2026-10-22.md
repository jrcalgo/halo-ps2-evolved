# M2 Step 7 — sound-scenery lifecycle and audible-path boundary

Date: 2026-10-22. Scope: one isolated source/data-backed review of CE sound
scenery and sound selection for the 13 supported stock multiplayer maps. This
is a subcheck, not Step 7 closure; campaign maps are intentionally excluded.

## Finding

The `ssce` (sound scenery) label is an object type, not proof that its
constructor emits a sound. CE's `sound_scenery_new()` only sets the object's
shadowless flag and returns success; `sound_scenery_delete()` is empty
([`sound_scenery.c:30-45`](../../submodules/halo-ce-universal/source/sound/sound_scenery.c#L30)).
This is byte-identical to Halo-64's same implementation (both source files
SHA-256 `05e206603253dc42984cc8f70282cf4ad482043633a9e733816bff4557932fd9`).
That comparison confirms a shared callback, not that Halo-64's N64 audio path
is suitable for PS2.

There is a real CE route from an object's *tag attachments* to looping sound:
`attachments_new()` dispatches an attachment whose group is `lsnd` to
`game_looping_sound_new()` and sets
`_object_has_attached_looping_sounds_bit`
([`objects.c:3410-3467`](../../submodules/halo-ce-universal/source/objects/objects.c#L3410)).
On deletion `attachments_delete()` calls
`game_looping_sound_delete()` for that attachment
([`objects.c:5139-5156`](../../submodules/halo-ce-universal/source/objects/objects.c#L5139)).
Separately, CE's per-tick `game_sound_update()` asks the scenario listener
selector for environment/background-loop state, sends the environment to
`sound_manager_set_sound_environment()`, computes combined PAS, and starts,
stops, or replaces the background looping sound
([`game_sound.c:820-861`](../../submodules/halo-ce-universal/source/sound/game_sound.c#L820)).
Thus proving an `ssce` placement's audible role requires resolving its actual
`obje.attachments` and running the generic object + sound-manager path; the
sound-scenery callback alone cannot do that.

## Retail multiplayer evidence

The pinned CTAG schema-footprint inventory (`docs/reports/retail-ctag-schema-footprint-v5.json`,
SHA-256 `746b572a4839736c63c69d00ac750f5a46e46202ae144e79d1dec6f4bf9ff46e`)
records the total bytes in the source `scenario.sound_scenery` and
`scenario.sound_scenery_palette` blocks. CE's schema asserts a placement size
of `0x28` and declares the palette as the scenario's `ssce` reference block
([`tag_schema_scenario.c:176,273,824-848,1311-1313`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_scenario.c#L176)).
Dividing these audited extents by their declared record sizes gives:

| Stock multiplayer map | Sound-scenery placements | Palette entries |
| --- | ---: | ---: |
| Beaver Creek | 8 | 1 |
| Blood Gulch | 2 | 1 |
| Boarding Action | 0 | 0 |
| Carousel | 0 | 0 |
| Chill Out | 0 | 0 |
| Damnation | 3 | 1 |
| Hang 'Em High | 0 | 0 |
| Longest | 0 | 0 |
| Prisoner | 0 | 0 |
| Putput | 0 | 0 |
| Rat Race | 0 | 0 |
| Sidewinder | 0 | 0 |
| Wizard | 0 | 0 |

This is source-map schema inventory, not evidence that any listed object was
created, has an `lsnd` attachment, or emitted audio. It does show where a
nonempty placement-based runtime fixture can be sourced without inventing
content: Beaver Creek, Blood Gulch, or Damnation. The all-map BSP listener
environment selector currently exercises selected CE palette queries on
Longest and Blood Gulch only; that check is distinct from sound-scenery object
creation and playback ([`m2-step7-mp-sound-environment-host-2026-10-21.md`](m2-step7-mp-sound-environment-host-2026-10-21.md)).

## Implemented narrow fixture

Added [`test_hcu_sound_scenery.py`](../../tests/test_hcu_sound_scenery.py)
and [`hcu_sound_scenery_host32.c`](../../tests/hcu_sound_scenery_host32.c).
The fixture compiles CE's unchanged `source/sound/sound_scenery.c` for host
ILP32, supplies only a typed object-lookup seam, and runs the real callback.
It verifies lookup index/type, successful construction, exactly the
shadowless-bit mutation (all other object bytes preserved), and that deletion
does not mutate state or perform a second object lookup. This isolates the
actual sound-scenery callback without fabricating an audio event.

Command (native ILP32 execution must be outside the SIGSYS-restricted sandbox):

```sh
python3 -m unittest discover -s tests -p test_hcu_sound_scenery.py -v
```

Result: **1 test passed** with approved unsandboxed native ILP32 execution. The
sandboxed invocation compiled and linked but execution was blocked by SIGSYS;
the successful run was repeated with elevated execution. Test source hashes:
C fixture `0485070fd14ec5b7306f78108d8d4c860de32eb6c31f310213255e075976aa05`,
Python runner `4a48f257381bdd646271c874ad3b8ecb625bbbb23e25f505215bc2b1cbe0ff74`.
HCU pin: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; Halo-64 pin:
`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.

## Audible runtime blocker and next implementation

The PS2 cache adapter is currently only a success-shaped placeholder:
`_sound_cache_sound_request()` discards `block/load/reference` and returns
`sound != NULL`
([`ps2_sound_cache.c:40-47`](../../submodules/halo-ce-universal/port/ps2/src/ps2_sound_cache.c#L40)).
It does not resolve sound bytes, decode them, queue a voice, or call SPU2.
Consequently neither the CE selector tests nor this callback fixture can
establish audible output. This is an implementation gap, not a test that can
be closed with a spy returning success.

The shortest evidence-backed continuation is to select one actual nonempty MP
sound-scenery palette/placement chain (prefer Beaver Creek or Blood Gulch),
resolve its palette `ssce` datum through the relocated tag image, read the
real sound-scenery object's attachment block, and assert its `lsnd` identity
and marker. Then drive CE object attachment creation and `game_sound_update()`
through a request-capture adapter that records resource identity, source
object/position, gain, pitch and loop state while keeping CE selection code
real. Separately implement PS2 sound-cache lookup/decode and the SPU2 voice
adapter, then run a deterministic short sample on PCSX2/hardware and capture
the request/voice result. Do not label the request-capture test “audible” or
claim SPU2 parity until that last platform stage passes.

REA is not needed for this slice: the CE implementation, Halo-64 comparator,
PS2 cache adapter, and converted source-data census are inspectable. This
report closes only the callback semantic check and narrows the exact missing
audible path; sound selection/runtime and actual PS2 playback remain open.
