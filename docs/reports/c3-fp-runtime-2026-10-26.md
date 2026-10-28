# First-person runtime fidelity check (2026-10-26)

## Scope and build

This was a visual-only PCSX2 check; it makes no FPS or hardware-performance claim. I used the frozen quiet four-view integration build from `build/c3/first-person-fix/integration/quiet-baseline-v4/desktop-launch.json` (ELF SHA256 `b570ee50188d43c3e271cee50bb61ed990ea327f83277d8696171986c3a64e17`). The launch manifest recorded all 43 source pins, package hash, absolute working directory, command line, and a new log path before process start. The guarded runner verified the live process, map-ready line from byte offset zero, and its 640×480 guest window.

The run directory is `build/c3/first-person-fix/runtime/quiet-baseline-v4/run-20261026T061302Z-2962cbc801d9/`. Map load was confirmed at emulator time 98.5239 s. Owner telemetry at map load showed zero backing allocation failures; the session ended normally after five captures. Four scissored views showed distinct perspectives and remained within their own quadrants during yaw, pitch, and movement. This is evidence for scissor isolation in these captured frames, not a broader world-render equivalence test.

## Inputs and observations

The captured sequence was `00-map-loaded.png`, Right held 1.0 s (`four-yaw-right.png`), Up held 0.5 s (`four-pitch-up.png`), pre-movement (`four-before-wall.png`), W held 2.5 s, then `four-after-wall.png`. Key-up events were recorded for each hold. In the last pair, the world changed independently in each quadrant after movement, while the first-person weapon remained attached to each view.

The candidate does **not** pass first-person placement/clipping fidelity: the hands and weapon still occupy an oversized part of the view and are cut off at the right and/or bottom edges. The defect is visible in the initial frame and persists through yaw, pitch, and movement. The captures do not establish that the viewmodel remains correctly occluded at a wall, and do not prove pixel identity of world pixels. No structured per-view pixel/counter snapshot was available in this quiet build.

## Artifacts

- `00-map-loaded.png`: SHA256 `a58bf2d3f353b642f8aacd6b1036763ec58bb1a748d5ef25cf6b2cc0f2da0f52`
- `four-yaw-right.png`: SHA256 `9e087afd8b3154d05a41ddfc82f8e5190f0585b1849d7dd58354d685a1758b14`
- `four-pitch-up.png`: SHA256 `1f519df09b42fba56eb69c16ec90cd441e8de2ff03274c3d3b3dcfdccfbdd043`
- `four-before-wall.png`: SHA256 `7128127f3a9a1144ab3d80baea76a6f60dd2b1733c84237e5038d373bff079b7`
- `four-after-wall.png`: SHA256 `c3d0c99e8538f5316f8d5c0dd7ee4e75b00ca462babf60f7a6fcdb7889c57a22`

`active.json` contains the copied manifest, source pins, ELF/package hashes, exact argv, launch log offset, PID/window identity, event ledger, and capture metadata. Earlier harness-collision attempts are marked invalid in their own run directories and are not counted as evidence.

## Result

Four-view scissor isolation and view-local input response were observed in this session. First-person scale/placement remains visibly wrong and clipped; further implementation work is needed before claiming the fix complete. No production source was changed during this validation.

## Fresh state-timeline diagnostic

I also ran the pose worker's fresh movement-trace build, not the earlier `fd49…` diagnostic. Manifest: `build/c3/first-person-fix/diagnostic/state-timeline/quiet-baseline-v1/desktop-launch.json`; copied manifest SHA256 `d0061dff6b18a63931b8dc9687456fa9a992737cd794742c17f162c80b1c0555`; ELF SHA256 `09507f1ac9362479ee7ea85480338b7d9a04e42acd9ddf95806b661d063c9a3e`; 45 source pins. Runtime artifacts are under `build/c3/first-person-fix/runtime/quiet-baseline-v1/run-20261026T070620Z-46d9adfb8bdc/`. The launch log began at byte offset 0 and the map-ready line was verified at 41,031 bytes. Emulator log SHA256 is `035667b74b132fcb9737a78d2360a8ce04d1ac28d0202ff283a4af0295a370d7`.

The requested settled CE pose samples show `state=0`, `moving_anim=-1:0`, overlay 13, interpolation 6:0, and the same near-identity relative root basis/translation across ticks 60, 120, and 300. The idle counter advances from 47 to 107 to 287 while state animation advances from `2:46` to `2:47` to `2:50`; this confirms the pose trace reached steady idle rather than only capturing startup. The corresponding `c3-camera` records (log lines 939, 1080, 1501) all report control FOV `1.22173` rad (70°) and observer FOV `0.87266` rad (50°). They report `draw-pos`, `draw-fwd`, and `draw-vfov` as zero, so that trace had no selected snapshot draw-camera values; the separate parent `FPVIEW` record still reports its per-view projection.

The exact requested state rows are:

```text
[  105.4421] HALO_PS2_FPPOSE sample target=60 local=0 window=0 game_time=60 state=0 state_anim=2:46 moving_anim=-1:0 overlay=13 idle=47 until_pose=413 interp=6:0 graph0=7 orientq=0,0,-0.0958281159,0.995391667 relF=0.99999547,0.00290176272,-0.000311758369 relL=-0.00290063024,0.999989092,0.00362309744 relU=0.000322207808,-0.00362232327,0.999993265 relP=0.143470019,-0.0467823073,-0.0738348067
[  107.4415] HALO_PS2_FPPOSE sample target=120 local=0 window=0 game_time=120 state=0 state_anim=2:47 moving_anim=-1:0 overlay=13 idle=107 until_pose=413 interp=6:0 graph0=7 orientq=0,0,-0.0958281159,0.995391667 relF=0.999995828,0.00283074379,-0.000253144419 relL=-0.00282981992,0.999989212,0.00365326903 relU=0.000263527036,-0.00365261734,0.999993265 relP=0.143454179,-0.0467921123,-0.0737401918
[  113.4496] HALO_PS2_FPPOSE sample target=300 local=0 window=0 game_time=300 state=0 state_anim=2:50 moving_anim=-1:0 overlay=13 idle=287 until_pose=413 interp=6:0 graph0=7 orientq=0,0,-0.0958281159,0.995391667 relF=0.999995708,0.00285933912,6.75249612e-06 relL=-0.00285933912,0.9999879,0.0039299326 relU=4.4554472e-06,-0.00393003225,0.999992192 relP=0.143401802,-0.0467935391,-0.0734903663
```

The exact tick records are:

```text
[  105.4092] HALO_PS2_LOCAL c3-camera tick=60 game=59 frame=53 steps=1 scheduler-us=33361 render-us=33368 qpc=15274316800 dropped=22 look-ce=-0.00000,0.00000 look-sensitivity=120.000,60.000 facing=2.68525,0.00000 delta=0.00000,0.00000 control-fov=1.22173 obs-pos=0.0000,0.0000,0.0000 obs-fwd=1.00000,0.00000,0.00000 obs-fov=0.87266 draw-pos=0.0000,0.0000,0.0000 draw-fwd=0.00000,0.00000,0.00000 draw-vfov=0.00000
[  107.4088] HALO_PS2_LOCAL c3-camera tick=120 game=119 frame=113 steps=1 scheduler-us=33366 render-us=33387 qpc=15569525504 dropped=22 look-ce=-0.00000,0.00000 look-sensitivity=120.000,60.000 facing=2.68525,0.00000 delta=0.00000,0.00000 control-fov=1.22173 obs-pos=0.0000,0.0000,0.0000 obs-fwd=1.00000,0.00000,0.00000 obs-fov=0.87266 draw-pos=0.0000,0.0000,0.0000 draw-fwd=0.00000,0.00000,0.00000 draw-vfov=0.00000
[  113.4157] HALO_PS2_LOCAL c3-camera tick=300 game=299 frame=293 steps=1 scheduler-us=33366 render-us=33375 qpc=16455145472 dropped=22 look-ce=-0.00000,0.00000 look-sensitivity=120.000,60.000 facing=2.68525,0.00000 delta=0.00000,0.00000 control-fov=1.22173 obs-pos=0.0000,0.0000,0.0000 obs-fwd=1.00000,0.00000,0.00000 obs-fov=0.87266 draw-pos=0.0000,0.0000,0.0000 draw-fwd=0.00000,0.00000,0.00000 draw-vfov=0.00000
```

`control-fov` is sampled from the player-control/first-person camera command (default 70°); `obs-fov` is sampled from the independent observer result (default 50°). CE's `set_window_camera_values` converts the observer result through its adjusted/display-FOV path before building the rasterizer camera. Neither traced number by itself is the final per-view draw FOV.

## Fallback-FOV runtime check

The pose worker supplied a separate fresh build whose only runtime change is the zero-observer fallback deriving FOV from the selected player's control FOV through CE's adjusted tangent and `2*atan(.75*tangent)` conversion. Manifest: `build/c3/first-person-fix/diagnostic/fallback-fov/quiet-baseline-v1/desktop-launch.json`; copied manifest SHA256 `0c326481709df7dae0cb1eeda586eeb4c77f297f8219216b637189eff77e2688`; ELF SHA256 `1b87c8e9cf74773ef2db0eb99f9794ae26a63182857f8f68465cfb13c022899f`; 46 source pins. Run artifacts are under `build/c3/first-person-fix/runtime/quiet-baseline-v1/run-20261026T072022Z-e9d411d35bcd/`; the map-ready marker was at emulator time 100.5616 s, and the emulator log SHA256 is `9e966ece311d6b38cb4083f396ca0a85c3e653206ef3ba352652e1d733687c9b`.

The parent `FPVIEW` record at log line 768 reports view 0 viewport `0,0,512,448`, `hfov=0.943470895`, aspect `1.14285719`, near `0.01171875`, and far `16`. At tick 300 the CE pose sample reports `state=0`, `state_anim=2:50`, `moving_anim=-1:0`, overlay 13, idle 287, `until_pose=357`, interpolation `6:0`, and root translation `(0.143401802,-0.0467935391,-0.0734903663)`. The full row is in `emu.txt` at line 1500.

The steady-idle screenshot `fallback-fov-idle-t300.png` (SHA256 `a5bbe08096cfdd231616a87c99033c8c35e9eade2bf0e3ffe106c1f391fbb73d`) shows more of the viewmodel within the right side of the frame than the fallback-off screenshot; its lower grip meets the bottom edge. I did not send yaw, pitch, or wall-walk input during this FOV-only check. The run ended after `quit`, and my PCSX2/Xvfb processes exited.

Captured `steady-idle-t300.png` at the requested settled state (SHA256 `823b49d580d5f9cca9db806b17fce9505a642e0d2dab74518e9829e90fc74435`). It still shows the weapon/hand oversized and clipped at the right/bottom. Since the framing was visibly incorrect, I did not send yaw, pitch, or wall-movement inputs; this diagnostic is an explicit placement failure, and no wall-occlusion conclusion follows. The runtime exited after `quit`; a host audit confirmed my PCSX2 and Xvfb processes were gone.
