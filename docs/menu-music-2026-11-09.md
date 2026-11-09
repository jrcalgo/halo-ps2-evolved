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
