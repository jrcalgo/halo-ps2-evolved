# C3 current Blood Gulch FPS A/B — 2026-10-26

## Result

| Build | FPS[P], 11 samples | VPS | Speed |
|---|---:|---:|---:|
| Baseline | 14.7136 mean (13.99–15.98) | 59.9427 mean | 100% |
| Quiet candidate | 29.97 mean/median (29.97–29.97) | 59.9391 mean | 100% |

Each variant had a warmed, clean 50-second window sampled every five seconds. The 6000-VSync capture hold was excluded. Both used the same visible 640×480 Blood Gulch one-view/one-player run, PCSX2 recompiler settings, HCP, controls (manual, autofire off), and `perf_replay=false`. FPS[P] came from the actual PCSX2 game-window OSD; VPS and emulation speed are reported separately. The FPS[P] ratio is 2.0369×. At matched guest capture tick 3601, native render counters were 1791 baseline and 3586 quiet (~2.0042×). Both reported 89 objects, 89 refs, 167 palettes, and zero overflow, idle violation, emission failure, early release, commit rejection, or write refusal.

The quiet build enables `HCU_C3_OBJECT_FASTPATH`, `HCU_C3_OBJECT_VIEW_CACHE`, `HCU_C3_BINDING_SEAL`, and `HCU_C3_SNAPSHOT_INDEX`; all four are off in baseline. `HCU_C3_REALTIME_SCHEDULER=1` in both. Prepare cache, telemetry, timing, and movement trace are off in both.

## Rendering and scope

At tick 3601, camera/world records and the world-plus-HUD pixel crop match. The same first-person weapon and hand resources are selected and remain visible, but 40 of 41 first-person palette matrices differ and the gun/hand pose shifts a few pixels. This is consistent with a different idle/bob phase under changed render cadence; the evidence does not establish that the animation-cadence difference is harmless. The full images are not identical. The capture angle shows no Warthog pixels, so vehicle appearance is not qualified by this run.

This measurement uses HCP SHA `23d41d49c5e755da415f068e6420745eca8d51a71474d40c7335cca834273aac`, containing 64px object-texture variants. The later full-detail HUD HCP `c727` was not measured. The result is for this one-view workload only.

## Frozen pair and provenance

| Artifact | Baseline | Quiet candidate |
|---|---|---|
| Launch manifest | [`baseline-v3/desktop-launch.json`](../../build/c3/fps-current-fresh/baseline-v3/desktop-launch.json) — SHA256 `7bf01297e78edf0281d6871338d9338dc537e3b0aef8b808bf65689b221ee1a9` | [`quiet-v3/desktop-launch.json`](../../build/c3/fps-current-fresh/quiet-v3/desktop-launch.json) — SHA256 `d4801efe8fead2b8d6e212ef42bdafd0529d8dfd81f47f308b02b93cd6acbe77` |
| Guest ELF | SHA256 `0fc8b0025cff9ffc97a36bf7a8b3f9d74679f9c8f4a06a6895f89d7341827e39` | SHA256 `d52d8aa2920b2d037cd5172c1195f84630de6f30ba392ff61639c41b06f93e75` |
| Link report | SHA256 `60fedb43d00f0528cb7810234e035c88a665340c1057183709f547c955cc1227` | SHA256 `ec278fe785989178f8fda13e1272d75c494d312989d5d10b0c4b0eff322ad3b0` |
| Closure report | SHA256 `7ce6fd19f211d606081a83c8fe1802299265418e2ce9a4da0aa6d410ae916539` | SHA256 `a905c8543c342301569cb272bf6d3c86ec2f715d4050ef5dd97a629f911b3797` |

Both share cycle header SHA `45febcd6c25b3afb536f126dd98d34de3fd644fe81141fc3c267c0f1c83645a6`, render header SHA `90bb00aa54516c61f58d7d639681884567e223dc6be908ded45d82bddc92b5cb`, workload header SHA `c250df07842d2c0faa734c91a70a519f333e3d98b5985c1423e3a6e4f049788b`, and PCSX2 INI SHA `5d3173dc12579312c2ae918404d17f2cf76c905d9df89ac7c6ce2ef431977329` (effective settings SHA `fd83aaca6ab26473bf867c89f23cbdbbd5b8732da7dae99475dd1f883460db5c`). The HCP sidecar SHA is `6ff0602c42cd538494780708a295b8e2bcae49df5947049480526834ae53954c`.

The physical frozen source snapshot matches all 3,224 pins (manifest SHA `483eb6c3e8f9f9da4d60987f4ca5f0aa3d46926e80f242abeeacb78fda52a61e`). Each link closure reports 342 selected sources, 375 compiled units, and zero failures. The FPS fixes are committed as parent `eea0c5b` and engine `e066b54`, after this build freeze. The measured ELFs use the frozen bytes. A later caller error-counter adjustment is not included in these measurements. Fifteen live-tree files differ from the frozen pins; this run makes no full current-tree qualification.

## Evidence

- [Full machine-readable run and provenance report](../../build/c3/fps-runtime-fresh/current-pair/report.json)
- [OSD, screenshot, and pixel/snapshot parity README](../../build/c3/fps-runtime-fresh/current-pair/README.md)
- [Detailed parity data](../../build/c3/fps-runtime-fresh/current-pair/parity.json)
- [Baseline and quiet capture directories](../../build/c3/fps-runtime-fresh/current-pair/baseline-v3/capture-valid-1/) and [quiet](../../build/c3/fps-runtime-fresh/current-pair/quiet-v3/capture-valid-1/)
