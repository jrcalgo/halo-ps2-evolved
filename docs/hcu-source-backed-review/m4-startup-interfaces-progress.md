# Desktop HCU-plan Milestone 4 progress (2026-10-20; latest source refresh)

This report tracks Milestone 4 (“Finish the M1 startup interfaces”) in
`/home/ai/Desktop/HCU plan`. The overarching architecture and acceptance order
remain in [`plans/5.hcu-remake.md`](../../plans/5.hcu-remake.md). The Desktop
plan is updated with concise step status; this report retains detailed source
and run evidence. Milestone 4's four startup-interface steps passed for ELF
`e3577ca6ffc8f6f25d98e7930db0741f6dccfe099ae6a8133710861f938d7df2`.
Interpreter reached `m1-ui-map-request`. Recompiler reached `memory-ready`
with physical placement. No retail scene was drawn. M1 is complete on that
host ELF. Physical controllers and OPL/optical hardware are not an M1 exit.

## Current source/image update

The newest combined host-profile machine ELF is
`38dc08dcd642aeb8ab5fafd73ccdc3dd517d212585413f0e597f4d840f121e39`
(2,075,652 LOAD file bytes, 2,383,516 BSS bytes, zero undefined imports).
Its logical allocation audit has no unassigned owners or candidate-region
overages, but this exact image has not yet been run in PCSX2. The prior
`b38481f3...` guest run is historical evidence only.

The screenshot at `/home/ai/Pictures/ps2fail.jpg` shows the PS2 BIOS disc
fallback prompt. It does not identify a guest crash. `build/hcu-m1-disc-data.iso`
is intentionally data-only (it has `MAPS/UI.HP2` and `MAPS/UI.MAP`, but no
`SYSTEM.CNF` or boot ELF). Launching an ELF with that ISO attached treats it as
data media; it does not boot the ISO. If the diagnostic ELF exits, PCSX2 returns
to BIOS and the prompt is expected. `build/hcu-m1-boot-disc.iso` has a boot
system file and `BOOT.ELF`, but its embedded executable predates the current
machine ELF, so it must be regenerated before boot-from-disc qualification.

The fresh attempt in this agent session could not enter the guest: PCSX2's Qt
frontend failed to connect to the available X11 display. The harness therefore
has no current-source guest result. This is an infrastructure failure, not a
guest pass or guest failure. The user-provided earlier `memory-ready` output
belongs to ELF `2eb1f907...` and is not evidence for `38dc08dc...`.
Retrying with `QT_QPA_PLATFORM=offscreen` also exited before guest entry because
the AppImage has no offscreen Qt platform plugin. A direct Xvfb start could not
create its socket under the shared `/tmp/.X11-unix` ownership setup.

When a graphical session is available, the bounded current-image placement
rerun is:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py \
  --mode interpreter --stage m3-memory-ready \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf \
  --disc build/hcu-m1-disc-data.iso --require-physical-placement
```

Repeat in recompiler mode and then at `--stage m1-boundary`. The ISO is mounted
as guest data while the ELF is launched; do not choose the data ISO as the
boot executable. A missing `host:/maps/ui.map` at the later probe means the
host asset root is unavailable, not that a scene rendered.

## Historical guest boundary update (older image only)

The older host-profile combined ELF is
`b38481f32b793788879ed70055eaafed8c3afaf962f2eb3186f58d4fd8707b54`.
The exact PCSX2 interpreter run at
[`emulator-m1-interpreter-e9dfc2e4b0be4fccaa91afee7f3e6f66`](../../build/hcu-ps2-closure/emulator-m1-interpreter-e9dfc2e4b0be4fccaa91afee7f3e6f66/result.json)
uses `--require-physical-placement`. It reaches the corrected ABI smoke,
`memory-ready`, `pad-ready`, and `storage-boot-ready`; embedded IOMANX and
FILEXIO load with IDs 28 and 29, respectively, and the post-load FileXio RPC
bind succeeds. The harness reports valid canaries, all nine nonoverlapping
arenas, and `linked_physical.passed=true` for all eight checks against the exact
ELF and link map. The final arena ends 26,926 bytes before the 26 MiB reserve.
This resolves the previously reported FileXio RPC startup failure.

The run is compiled for `host:/`, so its subsequent
`asset root host:/ failed ... maps/ui.map probe at stat` is expected and does
not exercise an optical or OPL mount. A new optical-profile diagnostic ELF
(`fece3f9bf04d714bcf1376cf3ff9e43273789c1ade781513a83db17c6ac155e0`) was
started against `build/hcu-m1-disc-data.iso`; it reached `memory-ready` but
stopped at `Gif Unit - GS packet size exceeded VU memory size!` before the
asset-probe marker. PCSX2 had exited by the time it was checked; the harness
was interrupted, leaving a `running` result record. Treat this attempt as
inconclusive and do not cite it as an optical pass or a guest regression. A
fresh bounded retry should capture PCSX2's final exit status and determine
whether the ISO profile/image reproduces the previously documented optical
path. The image shown as the PS2 “Please insert a PlayStation…” screen is the
BIOS fallback/reset after the guest returns or exits; it is not evidence that
the HCU scene rendered.

A later interpreter run of the same host-profile ELF hash `b38481f3...`
requested `m1-ui-map-request` but used a different PCSX2 settings hash
(`00fcadfe...`). Its guest log likewise stopped at the GS/VU packet-size
warning before any HCU machine-entry marker. PCSX2 was no longer running when
inspected; the harness was interrupted, so this result is also inconclusive.
Preserve the earlier same-ELF host run that reached `storage-boot-ready` as
valid evidence for that earlier settings tuple, but do not infer reproducible
M1-boundary startup until the emulator settings are frozen and the same-image
run completes with a finalized result.

## Step 1 — ABI and DMA/snapshot boundary

**Advanced; still partial.** The user-provided PCSX2 interpreter result at
`build/hcu-ps2-closure/emulator-m1-interpreter-80194266b5ce405282a5a152460f9174/result.json`
shows ELF `2eb1f907d781bcfe4fb6170ba698f05d58090510b818c595acb8f2921fb1c54e`
reached `memory-ready`. However, disassembly exposed that this older
`ps2_abi_check()` had optimized to `return 1`, so that run did not execute its
intended record checks. The probe records are now volatile; disassembly of the
rebuilt ELF `7833c801a8084d0f549f5e598a11667cf6393ed9579402b9ff813cda5f5d716d`
shows actual record stores and comparisons. A fresh guest run must still reach
memory-ready to prove the corrected target smoke executed. The ABI checker now
disassembles the optimized R5900 object and rejects a smoke reduced to a
constant result ([checker](../../tools/hcu_ps2_abi_host.py)); its automated
pytest wrapper also passes.

Added the parent-side `hcu_render_snapshot_matrix_from_ce()` bridge
([header](../../src/stream/hcu_render_snapshot.h),
[implementation](../../src/stream/hcu_render_snapshot.c)) to repack the pinned
CE 52-byte `real_matrix4x3` representation for halo-ps2 `mat4`, including CE's
separate scale. The host fixture includes the actual pinned HCU
`math/real_math.h` declaration (and asserts its live size and field offsets),
then exercises that CE-typed record through the real halo-ps2 point transform,
VU1 palette, and aligned DMA chain ([test](../../tests/test_hcu_render_snapshot.py)). The R5900 combined-link
probe compiles the adapter object, but section garbage collection removes its
symbol because a production CE snapshot caller is not wired yet. No live CE
object has been rendered through it. The eight toolchain rows are `implemented` from their live caller sections
([review](hcu-ps2-toolchain-eight-review.md)). The external-review gate is
closed for rooted object `4a6dc9b2fb90dbe1`. That does not finish this
milestone: the current image still has no PCSX2 run, and the parent renderer
still does not read the snapshot.

## Step 2 — Input boundary

**Host CE-to-PS2 sample path now exercised; guest/controller evidence still
open.**
The host tests cover the PS2 DualShock-to-XInput mapping, both four-player
multitap arrangements, insertion/removal and packet semantics, parent sample
publication, and poll-before-CE-snapshot ordering
([bridge tests](../../tests/test_hcu_ps2_input.py#L25),
[CE frame boundary](../../submodules/halo-ce-universal/source/input/input_xbox.c#L710)).
Added a compiled fixture that extracts and executes CE's actual
`input_frame_begin()` body with fake boundary functions, asserting poll → device
snapshot → mutex/frame activation ordering. This executes the CE boundary
function, but stubs `input_get_device_states()`; it does not prove CE's own
pressed/held/released state values against an attached controller. A second
fixture executes CE's actual `update_hold_ticks()` source body with a fake
clock and verifies press edge (`1`), held cadence (`2+` at CE's 30 Hz rate),
release (`0`), and a subsequent press. This covers CE's hold-time helper, not
the complete XInput-to-`game_input_state` snapshot chain.

Added a host-compiled fixture that extracts CE's actual per-gamepad body from
`input_get_device_states()` and executes it against the real PS2 XInput
provider. It opens a logical PS2 pad, publishes a sample, then verifies CE's
analog-A and D-pad press/held/released counters, analog value, and dead-zoned
stick state through CE's `input_get_gamepad_state()` getter. This closes the
previous host-only gap in the CE state transformation, but is still a host
simulation: it is not evidence of live PCSX2/controller hotplug behavior.

The current host-profile run is configured with a custom marker at FileXio
post-load, after `pad_init()` and storage startup. It confirms pad service and
module/RPC startup but stops before CE's live input snapshot in
[`hcu_main.c`](../../src/stream/hcu_main.c#L220). Therefore there is no guest
input-state result yet. Actual controller hotplug remains unverified.

## Step 3 — Stateful render adapter and snapshot consumers

**CPU frame/camera state now has executed synthetic tests; full snapshot remains
partial.** Added `tests/test_hcu_ps2_render_state.py`, which extracts and
executes the exact PS2 HCU `render_frame()` and `render_frame_pregame()` source
bodies with synthetic console/local-player windows. It verifies frame-index
advancement, window filtering, camera selection/copy, time delta, and the
no-valid-window/pregame cases without a scene renderer. The existing safe-frame
bounds test remains separate. The CE-matrix-to-parent palette test covers
another real consumer boundary.

The fixed double-buffer snapshot now carries CE camera, frame/time, first-person
node matrices, up to 2,048 object transforms, and effect switches. Its HCU
producer is linked to parent begin/commit hooks, with synthetic coverage for
publication, capacity, immutability and rejection. It does not yet carry HUD
quads or particle lifetimes. No production parent renderer reads
`hcu_render_snapshot_latest()` yet; consequently the matrix converter remains
dead-stripped and no CE matrix has reached a runtime DMA draw. No retail
scene/render pass is claimed. Details: [snapshot bridge review](m4-render-snapshot-bridge-review.md).

## Step 4 — File service, root probe, and OPL paths

**Host shims and profile contracts pass; guest FileXio bootstrap is now proven,
but a supported asset-root probe is not.** Existing FileXio bridge tests exercise stat/open/read/seek/EOF/close,
missing and directory paths, descriptor exhaustion, error cleanup, and repeated
open-close without heap growth ([bridge test](../../tests/test_hcu_file_bridge.py)).
Storage and profile tests cover deterministic `host:/`, `cdrom:/`, `mass:/`,
`smb0:/`, and `pfs0:/` selection and no-reset bootstrap
([profile tests](../../tests/test_hcu_asset_profiles.py),
[storage tests](../../tests/test_hcu_storage_boot.py)).

The guest probe is deliberately after pad and storage initialization and checks
`D:\\maps\\ui.map` before entering the CE shell
([probe call](../../src/stream/hcu_main.c#L222)). The supplied run terminates at
the probe with `host:/` selected and reports the expected missing root. This
does not test optical reads. The fresh optical-profile run is inconclusive at
the GS/VU packet error noted above. PCSX2 optical read and all OPL device roots
need later-stage guest evidence; real OPL USB/SMB/HDD and optical launch tests
require hardware and remain open as specified by the Desktop plan.

## Verification and next gate

Latest focused run after the host-side ABI/input/render/storage changes:

```text
pytest -q tests/test_hcu_ps2_input.py tests/test_hcu_ps2_render_state.py \
  tests/test_hcu_render_snapshot.py tests/test_hcu_ps2_rasterizer_bounds.py \
  tests/test_hcu_file_bridge.py tests/test_hcu_storage_boot.py \
  tests/test_hcu_asset_profiles.py tests/test_hcu_dma_palette.py
19 passed, 2 subtests passed
python3 tools/hcu_ps2_abi_host.py
host ILP32/R5900 ABI layouts pass; R5900 ABI smoke emits stores, loads, and comparisons
git diff --check
passed
```

The latest host-profile combined link is `38dc08dc...` (2,075,652 LOAD file
bytes, 2,383,516 BSS bytes, zero undefined imports). A fresh current-image
guest run remains required; the attempted run failed before guest entry because
the PCSX2 frontend could not connect to X11. The older `b38481f3...` run proves
only its exact tuple. The optical-profile ELF `fece3f9b...` remains over the
static file cap by 14,596 bytes and its prior run is inconclusive. Rebuild the
bootable ISO with the exact current ELF, then run bounded interpreter and
recompiler guest tests through physical placement and the M1 boundary. OPL
USB/SMB/HDD and physical optical tests remain hardware gates.

The focused verification above passes, but it does not close M0. The current
source-backed external gate still has eight pending dispositions
(`__extendsfdf2`, `__fixdfsi`, `__truncdfsf2`, `floor`, `fmod`, `memcpy`,
`rint`, `sqrt`), and the logical M0 gate consequently reports one error.
`git diff --check` passes. The new toolchain audit makes source-backed
disposition of the eight rows possible, but the ledger still needs those rows
reviewed/updated and the exact link rebuilt before M0 can close.
