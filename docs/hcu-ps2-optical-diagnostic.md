# HCU optical-profile diagnostic — 2026-10-20

This is PCSX2 ISO evidence, **not** physical optical-media or OPL USB/SMB/HDD qualification, and not a completed M2 map/render pass.

The 2026-10-20 rebuild reproduced this exact result: PCSX2 recompiler run [`9843611b071e49fdb4949e33666427d2`](../build/hcu-ps2-closure/emulator-m1-recompiler-9843611b071e49fdb4949e33666427d2/result.json) used the same ELF and ISO hashes below, reached the M1 boundary, verified non-overlapping guest addresses with 22,745 bytes before reserve, and halted at 48.2422 s during the same UI geometry/BSP stage. This is a repeatability check, not a new capability or gate closure.

The current optical-profile parent/HCU machine ELF is SHA-256 `563b65914a91070297e79384e6c8f5f4a03fdb9c05acd97c61cded24362032fc`, built with deterministic `cdrom:/` asset root ([link report](../build/hcu-parent-link-probe/result-optical.json)). It was run in PCSX2 recompiler mode with the prepared [boot/data ISO](../build/hcu-m1-boot-disc.iso), SHA-256 `5c21cf894efb9da1d77b1e0189cf7b162b190d498e87ac616b6664a45e226237`. The exact [guest result](../build/hcu-ps2-closure/emulator-m1-recompiler-9ba2786a903742999666cb7d2cd53430/result.json) records parent `a2575e957feefbdff27febedabf60590401e6bcc`, HCU `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`, halo-ps2 `c8db480d1af1cd7ca5a3d29805e791233138b732`, BIOS hash, PCSX2 hash, and profile settings hash. The result is terminally `failed` at the later M2 map-load stage, but the runner now explicitly records that M1's `game-initialize-done`/`m1-ui-map-request` boundary was reached and preserves the guest-reported physical layout: ELF end `0x4f0508`, boot start `0x4f0720`, boot end `0x19fa727`, reserve `0x1a00000`, and 22,745 bytes of headroom. Those addresses are non-overlapping; they are the runtime marker values, not a measured high-water for all allocations.

| Guest time | Observed operation |
|---:|---|
| 5.40 s | FileXio opened `UI.MAP`, 33,582,080 bytes. |
| 5.50 s | HMAP loaded, 72 bytes. |
| 6.55 s | CTAG loaded, 1,547,396 bytes. |
| 6.65 s | CRNG loaded, 2,900 bytes. |
| 46.36 s | Full source SHA-256 verification finished; map preflight passed. |
| 48.09 s | CTAG/CRNG mount completed (`result=0`, `active=1`); CE's UI cache reports `levelsuiui` loaded and opens the mounted cache. |
| 48.20 s | UI scenario load halted: geometry references have no vertex/index buffers, then CE cannot read the required 2,048-byte structure-BSP header at offset `0x800`. |

The run establishes guest-side ISO path open, section reads/decoding, source hashing, CTAG/CRNG mount, and CE cache open. The SHA-256 pass takes about 40 seconds after section loading and is a measured startup latency concern. Do not bypass it without a documented integrity design and corruption tests. The later failure is in render-geometry/BSP availability, not FileXio or the viewport check; no scene was rendered. The machine initializes CPU bounds through the [`ps2_edge.c` adapter](../submodules/halo-ce-universal/port/ps2/src/ps2_edge.c), and its geometry calculation has a separate [CPU fixture](../tests/test_hcu_ps2_rasterizer_bounds.py). The map service is in [`hcu_map_service.c`](../src/stream/hcu_map_service.c); FileXio path normalization and HP2 section reads are in [halo-ps2 `file.c`](../submodules/halo-ps2/engine/src/stream/file.c) and [`section.c`](../submodules/halo-ps2/engine/src/world/section.c).

This improves M1 evidence for the PCSX2 optical profile only. Remaining M1 storage qualification is physical optical media and actual OPL-launched USB, SMB, and HDD mounts, including missing-device behavior and repeated open/close high-water checks without IOP reset. M2 still needs a complete scenario/BSP/geometry load, rollback/unload, measured capacities, and rendering evidence. The guest run's terminal failure is captured as a failed `m2-ui` attempt in its result JSON; its successful earlier storage/mount operations remain diagnostic evidence and do not change that stage outcome.
