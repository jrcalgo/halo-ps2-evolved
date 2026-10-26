# C3 controller input recovery

## Finding

The slow movement and uneven look response were caused by repeatedly restarting the controller configuration sequence while the PS2 pad SDK was still completing an asynchronous request. The player was not being slowed by a crouch, mounted-seat state, airborne state, or a changed movement constant in the measured before case.

On the original trace, a full-throttle W request was `2.25` **world units per second**, but the grounded player moved at only `0.107` world units per second. The sample was at support 1123 with ground normal Z `0.999`, crouch fraction `0`, and speed multiplier `1`. Its `base_seat_index` was `2`, the standing animation seat; this is not a vehicle parent-seat index. Incoming velocity repeatedly returned to zero. In the same-spawn fixed run, W reached a median `2.245` world units per second after its initial ramp; its roughly two-second average was `2.02`. Steady S, A, and D trials measured medians of `1.976`, `1.986`, and `1.974` world units per second.

The original 0.60-second Right trial contains 18 camera rows and six `DS2 Config Finished` messages. Its look/facing changed on only six of the 18 rows. This directly matches the controller driver's repeated setup pattern. The separate manual recovery in the earlier session occurred after manual movement and jump activity, but that session was not a controlled test; the available evidence does not establish that jumping caused recovery.

## Cause and change

The SDK reports `PAD_STATE_EXECCMD` while a command is still busy, even when the controller's physical state is otherwise stable. The old driver treated that state as a disconnect, cleared its setup marker, and restarted `padSetMainMode` on the next stable poll. It also attempted press mode without waiting for main-mode completion. The configuration consequently competed with regular input reads.

The fix in `engine/src/platform/pad.c` tracks a phase per port and slot: main mode pending, press mode pending, and ready. It preserves a pending phase through `EXECCMD`, advances only after an accepted request completes, and backs off for rejected or failed requests. A real disconnect resets the sequence and clears the sample so stale button state cannot survive reconnection. Unsupported press mode is handled without blocking normal reads. Retries are bounded; the driver uses no heap and has no busy loop.

The real-source host fixture passed **12 tests and 7 subtests**. It covers multiple busy polls, no duplicate configuration requests, unsupported press mode, rejected and failed commands with retry, disconnect during configuration, reconnect with released input, and multitap logical mapping. Running the asynchronous regression case against a temporary copy of the pre-fix `pad.c` fails at the expected assertion that configuration must not restart. No movement speed, acceleration, collision, or look-sensitivity constants were changed.

## Fixed-run measurements

The fixed run began from the same spawn and support as the slow sample. W acceleration ramped from rest to normal speed; after the ramp its median was `2.245` world units per second. The approximately two-second W average, including acceleration, was `2.02`. S, A, and D each remained near `1.97–1.99` world units per second. Crouch-only input entered crouch as expected, while the tested W interval remained standing.

The fixed run printed five configuration completion messages during initialization, the last at guest time `103.9687` seconds. No further configuration messages appear after that point in the retained trace, including the later movement and look trials. During a 0.60-second Right input trial, 18 of 19 published-camera rows contained active look/facing changes; the extra row is the boundary sample before the input took effect. The 0.602-second Left trial had 17 active rows out of 18, again with one boundary sample. Published yaw followed the facing changes, and the camera stayed at the expected player-relative position.

Camera cadence during those trials was about 33 ms per row. This gives direct evidence that the published camera responds on the regular render cadence once pad setup stops repeating. It also shows why a 30 FPS average alone would have missed the earlier alternating-input behavior.

The old `observer` and draw-camera globals in the movement trace were not the live published camera: they contained default values. The authoritative camera rows are the `c3-render-camera` diagnostics, which read the published view. Likewise, `look-ce` is the latest normalized input-abstraction value at the diagnostic point, not a history of every consumed pad sample; it should not be used alone to infer missed input.

## Evidence and reproducibility

All movement values above are **world units**, not meters. The controlled fixed-run trials are in Blood Gulch at one view and one player, with no scripted autofire. The instrumented build enables diagnostic timing and movement tracing, so its frame timing is evidence about controller/camera response and should not be treated as a quiet-build performance qualification.

The pre-fix run used ELF SHA-256 `2196e7be2890b6d15c96291a0869baf13d259c7823a29fe06538553da0c45726`; the fixed run used ELF SHA-256 `760803a46e8f46aaaee8c106d671bdc1105e84c5d9188e17af997f17d270c27a`. The fixed launch manifest records the source pins, package hash, build flags, and recompiler configuration.

- [Pre-fix emulator log](../../build/c3/movement/trace-20261025-r1/guest/play/desktop-20261026T004234Z-emu.txt)
- [Pre-fix launch manifest](../../build/c3/movement/trace-20261025-r1/guest/desktop-launch.json)
- [Pre-fix active-run manifest](../../build/c3/movement/trace-20261025-r1/guest/desktop-active.json)
- [Original controller event ledger](../../build/c3/movement/trace-20261025-r1/input/ledger.json)
- [Recovered-session checkpoint log](../../build/c3/movement/trace-20261025-r1/checkpoints/user-base-recovery-20261026T004918Z/emu.txt)
- [Recovered-session checkpoint metadata](../../build/c3/movement/trace-20261025-r1/checkpoints/user-base-recovery-20261026T004918Z/checkpoint.json)
- [Fixed-run emulator log](../../build/c3/movement/trace-20261025-r2/guest/play/desktop-20261026T010708Z-emu.txt)
- [Fixed-run launch manifest and source pins](../../build/c3/movement/trace-20261025-r2/guest/desktop-launch.json)
- [Fixed-run active manifest](../../build/c3/movement/trace-20261025-r2/guest/desktop-active.json)
- [W input byte ledger](../../build/c3/movement/trace-20261025-r2/input/ledger.json)
- [Right/Left input byte ledger](../../build/c3/movement/trace-20261025-r2/input/camera-ledger.json)
- [Movement and crouch input byte ledger](../../build/c3/movement/trace-20261025-r2/input/movement-controls-ledger.json)
- [Real-source pad regression fixture](../../tests/hcu_pad_poll_main.c)
- [Pad fixture shim](../../tests/hcu_pad_shim/libpad.h)
- [Host test driver](../../tests/test_hcu_ps2_input.py)

The fixed diagnostic build's source pins identify the pad implementation and header as SHA-256 `7d4977d8b30e136acd2b0d87be8460b6a4f64fcd6b76c186f9604df50975cf82` and `99fe95173bc30cd4019bb73d20a8839b415c14d7b058b09834158d0438e7ef59`. The associated revision set was parent `fae47ca17812c45f23c002af94db21df240e5305`, CE `15534fc33a275019b6659bc5effb3958a4e63768`, and renderer `7e43fbb91cc62cf760f107271f688c73a9eac8e9`. The source changes are committed as engine `ed88dbc`, CE diagnostics `6e35c0c`, and parent `8be0d23`; these commits contain the same source contents as the retained instrumented run.

The pad-state repair is separate from the known oversized/intersecting first-person weapon mesh. That rendering issue was not changed or measured here.

## Quiet-run verification

The corrected quiet build was launched separately with parent `8be0d23`, CE `6e35c0c` and renderer `ed88dbc`. Its ELF SHA-256 is `3e5d95311b8485dad19a32b6196f5b571f63b1642fe995b6723f833632b30619` and its package SHA-256 is `23d41d49c5e755da415f068e6420745eca8d51a71474d40c7335cca834273aac`. Timing, C3 telemetry and movement tracing are all disabled. The movement/camera/timing diagnostic strings are absent from the ELF, and the quiet log contains no corresponding per-frame rows.

PCSX2 reported `production-ce-map-loaded result=1 map=bloodgulch` at log time `95.7116` seconds. A one-second W hold followed by a 0.60-second Right hold produced visible displacement and rotation from the fresh spawn, before any test jump. All test keys were released. The log stayed at 43,035 bytes throughout those inputs; its last controller configuration completion was at `99.4505` seconds and no completion messages recurred during the test. This is qualitative manual-control verification: the quiet build does not measure world speed or camera angle. The diagnostic results above provide those measurements.

The initial owned-window captures contained a solid black stripe over their right 441 pixels. Moving and raising that same emulator window from client geometry `(960, 482, 640, 480)` to `(3200, 647, 640, 480)` on the secondary monitor produced a full-width gameplay capture. The stripe was a window-placement/capture artifact, not evidence of a rendering regression. The full capture shows Blood Gulch terrain, HUD and weapon/arm geometry, with PCSX2's OSD reporting **29.97 FPS, 59.94 VPS and 100% emulation speed**. That single OSD observation is separate from the timed [multiview A/B measurements](c3-multiview-fps-ab-2026-10-25.md). The oversized/intersecting weapon mesh remains visible and unqualified.

The verified quiet process group is `931368`; it was left running with all test keys released. Read the active manifest to check whether this remains the current session before controlling it.

- [Quiet launch manifest and source pins](../../build/c3/movement/fixed-quiet-20261025-r1/quiet-optimized-v1/desktop-launch.json)
- [Quiet active-session manifest](../../build/c3/movement/fixed-quiet-20261025-r1/quiet-optimized-v1/desktop-active.json)
- [Quiet emulator log](../../build/c3/movement/fixed-quiet-20261025-r1/quiet-optimized-v1/play/desktop-20261026T012149Z-emu.txt)
- [Quiet input ledger](../../build/c3/movement/fixed-quiet-20261025-r1/quiet-optimized-v1/input-ledger.json)
- [Full quiet gameplay capture](../../build/c3/movement/fixed-quiet-20261025-r1/quiet-optimized-v1/gameplay-quiet.png)
- [Capture geometry and image hash](../../build/c3/movement/fixed-quiet-20261025-r1/quiet-optimized-v1/window-capture-geometry.json)
