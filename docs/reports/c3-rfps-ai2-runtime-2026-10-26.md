# C3 renderer profiling follow-up (2026-10-26)

## Frozen runs

Ran the archived timing ELFs sequentially using `build/c3/fps-next/ai2/profile_case.py` on private Xvfb displays. Each manifest validated against its ELF, package, staged paths, and 35 archived source pins before launch. The v2 and v3 source pins match; v4 was not run after the whole-batch hook gap was found. No builds or source edits occurred during these runs.

| Views | ELF SHA256 prefix | Map ready (emulator time) | Counter samples | Captures | Runner result |
|---:|---|---:|---:|---:|---|
| 2 | `ee5909446455892f…` | 98.9996 s | 13 | 10 | bounded 150 s |
| 3 | `ec86c2e873c17b76…` | 95.6224 s | 10 | 10 | bounded 150 s |

Artifacts are under `build/c3/render/fps-next-ai2-v2-staged/` and `build/c3/render/fps-next-ai2-v3-staged/`; each contains `active.json`, `summary.json`, `emu.txt`, `launcher.log`, and the captured Xvfb root frames. Both runs reached the map and emitted fine renderer counters. Their `summary.json` files preserve the parsed rows and the actual timeout status. PCSX2 and Xvfb were stopped by the runner; a host process audit afterward found no remaining profile processes.

## Fine renderer timings

Values below are emulator instrumentation medians, with the observed range in parentheses. These are phase diagnostics from PCSX2 and do not measure native PS2 performance.

| Views | Clip gather | Clip group | Batch records in | Polygons out | GS wait / present | Framebuffer select |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 3.969 ms (2.340–5.987) | 0.022 ms (0.020–0.028) | 581 (126–581) | 71 (56–110) | 14.820 ms (3.883–15.062) | 0.000 ms |
| 3 | 3.889 ms (3.406–6.962) | 0.029 ms (0.027–0.036) | 155.5 (106–578) | 71 (56–122) | 4.343 ms (1.584–11.787) | 0.000 ms |

The capture at each run's 6-second mark preceded map rendering and is only a startup frame. Later captures contain the loaded map; capture records include paths, sizes, and timing in `active.json`/`summary.json`.

## Prior hook-broken run results (superseded for whole-batch coverage)

Those earlier hook-broken v2/v3 logs contained no `HALO_PS2_LOCAL c3-batch` records, although they did contain `c3-clip-perf` and `c3-present-perf`. Their scheduler/input/player/publication/parent/snapshot/idle phase sums were unavailable, so those earlier runs could not close the whole-frame budget. The later v9 run below supersedes that instrumentation gap for the 2-view tuple. Do not combine the earlier rows with v9 as a matched comparison.

These emulator runs rank guest-side hypotheses only; they do not establish hardware FPS. No quality settings or fidelity behavior were changed.

## Frozen v9 hook verification run

After the missing hook was traced and corrected, the verifier froze a new two-view ELF. Its manifest was revalidated with 36 source pins and the staged package path. One fresh private-Xvfb run used that ELF, with output isolated in `build/c3/render/fps-next-ai2-v2-staged/run-20261026T065716Z-ef8cc56ab830/`. The manifest SHA256 is `5b6b700ae5931eef20c77fb70ec0765ca11abf29076a2526fe1a8fec3c6536ac`; the ELF SHA256 is `eace658942edfe7423b7ce6d2e8e93a9fe848cb07f5bff973e60e8bb71090d65`; the emulator log SHA256 is `58e38914d5fdf8c55db021dc1498c9412884c4598816be58911c1d12951b7399`.

The map loaded, a full live-world capture was recorded at elapsed 126 s (`capture-09-126s.png`, SHA256 `cc258ddf6f9327da93fd393c7502d10209336217963b5cfb0832ce708b916660`), and the bounded run produced 12 `c3-batch` summaries with `n=30` samples each, alongside 13 clip and present phase records. The runner ended at its 150 s bound and cleaned up its PCSX2/Xvfb processes.

Across the 12 whole-batch summaries, median reported phase values were input 0.559 ms, player 0.144 ms, input-end 0.001 ms, game-time 16.724 ms, publication 9.809 ms, parent 26.128 ms, snapshot 0.000 ms, and idle 0.000 ms. Batch interval bins and dropped-tick values are recorded in the full `summary.json`; the repeated dropped count may be cumulative and is not interpreted here as new drops per summary. Clip gather/group medians were 2.340/0.020 ms and vsync wait median was 3.261 ms; framebuffer selection remained 0.000 ms. These are guest-side instrumentation values from one v9 2-view run, not a matched before/after comparison or a native hardware FPS claim. The earlier v2/v3 rows above came from the prior hook-broken tuple and should not be combined with v9 as a comparable pair. No 4-view follow-up was run.
