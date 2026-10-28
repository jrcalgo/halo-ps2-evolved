# C3.8 SPU2 playback measurement (fixture run r38, 2026-10-28)

Scope: Blood Gulch fixture (`bloodgulch_mounted_gunner_4p4bot`, PCSX2 recompiler, SPU2 Cubeb backend routed to a private
PulseAudio null sink and recorded with `parec`). This is emulator evidence, not console qualification.

## What exists now
- `tools/hcu_sound_bank.py`: decodes retail `snd!` permutations (Xbox ADPCM / PCM16) from the decompressed map and
  re-encodes them as SPU2 VAG ADPCM into an HSB1 bank (SHA-256 trailer). Selection is tiered (weapon fire/eject/ready/
  reload/overheat, impacts, explosions, drops) under a 1.5 MB SPU2 RAM budget: 109 permutations of 73 sounds.
  The bank is derived retail data and must not be committed.
- `src/stream/hcu_spu_playback.c`: portable player core (bank parse, 24 CORE1 voices, round-robin permutations, priority
  steal oldest-first among equal or lower priority, STOP releases the owner's voice, pitch and gain from the CE record).
- `src/stream/hcu_spu_hw_ps2.c`: libsd + sdrdrv IRX embedded, `sceSdRemote` register access, one-time verified upload
  through a 16 KB IOP staging buffer. audsrv was rejected: it leaks an IOP heap block per loaded sample.
- Drain path: `hcu_c3_sound_tick` now feeds each drained record to the player (tag path from `tag_get_name`).
- This PS2SDK's `libsdr.a` references `g_libsdr_cb_data` without defining it; an opaque block satisfies the link (the
  callback API is unused).

## Measured
- Field measurement (400 playback records): event, owner kind/datum, position, priority, gain, pitch and game time all
  arrive for fire, eject, weapon-ready and impact (metal hit) events. Fire and eject sounds do reach the recorder; the
  earlier "no evidence" was the drainer discarding them.
- Guest: bank 109 samples / 1,499,824 bytes uploaded in about 1 s at boot (about 4.6 s after power on), 152 key-ons in the
  first 85 s, worst per-request cost 0.65 ms (blocking RPC, 8 calls per start).
- Host capture (228.9 s, peak 26,652): silence until gameplay, then 307 of 915 quarter-second windows above RMS 200.
  Cross-correlation of the first 200 ms of the decoded retail source against the capture while the assault rifle fires:
  0.96 and 0.92 for the two AR fire permutations, 0.17 to 0.24 for pistol, shotgun and sniper fire, 0.00 on a silence
  control. The audible content is the retail AR fire sound.

## Not qualified / known gaps
- No pan or distance model: the listener is the unit camera, so gain only.
- Looping sounds, fades, dialogue and music (stereo, Ogg, streamed) are counted and ignored.
- Pitch is applied at key-on only; no bend while playing.
- Bank is a separate file next to the package, not an HCP2 chunk; integrity is its own SHA-256 trailer, not the profile's.
- Only 73 of 315 Blood Gulch sounds fit SPU2 RAM; the rest report `no_sample`.
- No hardware run; PCSX2's SPU2 is not cycle-accurate.
