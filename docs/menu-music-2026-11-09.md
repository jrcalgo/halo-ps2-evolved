# Main menu music: every title1 recording (2026-11-09)

Retail `ui.map` has one music set for the menu: the looping sound `sound\music\title1\title1`
(start `title1\in`, loop `title1\loops`, no stop sound, no detail sounds). Its sound tags hold:

| bank name | recording | length |
|---|---|---|
| `title1\in` | intro (permutation 0, 26 fragments) | 33.29 s |
| `title1\loops` | loop 1 (permutation 0 chain, 24 fragments) | 30.46 s |
| `title1\loops2` | loop 2 (permutation 1 chain, 83 fragments) | 108.32 s |
| `title1\loops3` | loop 3 (permutation 2 chain, 47 fragments) | 61.06 s |

The old bank took only the first loop. `tools/build_hcu_menu_audio.py` now finds every chain start (a permutation no
other permutation continues into) and extracts all of them. Nothing else in the XISO is menu music (`xdemos`
ambient.wma and the Bink videos are other programs' audio).

## Fit
SPU2 holds 2,076,656 bytes and the bank is never paged, so the four recordings (about 4.0 MB of mono VAG at the retail
44.1 kHz) are resampled to the highest uniform rate that fits (`fit_rate`, steps of 50 Hz; about 15.5 kHz). The UI clicks
keep their own rate. Bank: 2,070,080 bytes resident, SPU end 0x1fe650.

## Playback (`hcu_main_menu_run`)
Intro first, then the loops in retail's way: each time a loop ends another is picked at random, none twice before the
others have played. Each piece is a one-shot voice scheduled from the first start at the previous piece's length
(`hcu_spu_sound_length_ms`), so the frame rounding does not add up. A bank without the extra loops falls back to the old
single looping voice.

## Verified
Headless PCSX2 (`HALO_PS2_v18_music.iso`): intro at 8.77 s, `loops2` at 42.07 s, `loops` at 150.42 s (42.07 + 108.3);
captured audio is non-silent. Not ear-tested.

## Streaming from disc (full quality)
The resident bank above is the fallback. The menu plays the music from disc at the retail 44.1 kHz in stereo:
- `tools/build_hcu_menu_music.py` writes `menu_music.hms` ("HMS1", 11.7 MB, ISO name `MMUSIC.HMS`): the four pieces as
  left/right SPU2 VAG, 16 KB slices interleaved per channel, flags unset, each piece's first block independent of
  history (filter 0). About 40 dB SNR against the retail PCM.
- `src/stream/hcu_spu_stream.c`: voices 22 (left) and 23 (right), hard panned, keyed on together. Each channel loops a
  ring of two 16 KB halves in the last 64 KB of SPU2 RAM (0x1F0000..0x200000; the fallback bank is budgeted to leave it).
  The player sets loop-start on the ring's first block and loop-end|repeat on its last; as the voice crosses into one
  half the other is refilled (one disc read + one upload per channel, on separate ticks). Pieces play back to back
  with no gap; silence once none is queued. `hcu_spu_reserve_voices` keeps the sound player off voices 22/23.
- The menu queues the intro and a random loop, tops the queue up as pieces start (no repeat until all three played), and
  logs `menu-music stream refills=.. underruns=.. read_fails=..` every 16 refills (0.65 s each).
- Host test `tests/test_hcu_spu_stream.py` simulates SPU2 RAM and two voices: piece order, loop wraps, a 150 ms stall,
  a failed read (plays silence, counted).

This is a deliberate exception to "never page audio": it writes SPU2 RAM during playback, but only the half the voice
has left. A late refill repeats a half, it cannot play other data. Headless PCSX2: 160 refills, 0 underruns, 0 read
fails over 104 s, piece change on time. Not tested on real hardware or by ear.
