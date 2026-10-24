# M2 guest fault address / EPC capture audit

**Scope:** report-only analysis of the latest combined guest image at SHA-256 `7e30d5c3ca0f4d32d8be9498d11c39a350b4a7e1fa2aa3cc5dc616dfc6cab7f9`, including PCSX2 run directories `emulator-m1-interpreter-0da9209b68cf495db52cf4f1fd49b7a2` and `emulator-m1-interpreter-10f1e07f70b0473e96f10dd26474320f`. No runtime code or shared plan was edited.

## Conclusion

The reported `0x7d2cc6`/`0x7d2cca` values are *bad data addresses*, not the faulting instruction PC. The latest run's memory report places `0x7d2cc6` inside the PS2-bound CE game-state allocation (specifically its CPU range), not inside the tag-cache span, the BSP span, or the loaded ELF text. This narrows the immediate access target, but does not establish which code issued the access or why the pointer is misaligned. Current logs do not include EPC/RA/stack, so a specific code root cause is not evidenced yet.

There is a safe, non-runtime-edit first path: use PCSX2's built-in R5900 debugger on an isolated datapath. The official PCSX2 command line supports `-debugger` to open the debugger and stop at entry; its debugger has an R5900 layout, a CP0 register view, disassembly, and imports ELF symbol tables. In this task's shell, that launch could not be completed because there was no available X display (`qt.qpa.xcb: could not connect to display :0.0`); no debugger screenshot or EPC was captured here. On the interactive desktop it should be attempted first. If the debugger cannot stop/report the guest EE exception itself, PS2SDK exposes a Level-1 exception-handler interface whose saved frame includes `cause`, `epc`, `badvaddr`, `sp`, and `ra`; a temporary diagnostic can record those values, but installing it is a code change and may replace kernel exception dispatch, so it needs an isolated diagnostic build and a review of handler ownership.

## Exact-run evidence

The current ELF hash is confirmed by `sha256sum build/hcu-parent-link-probe/hcu-gameplay-machine.elf` and each recent run's `result.json`. Run `0da9209b...` reaches `m2-ui-map-loaded`, logs unaligned stores to `0x7d2cc6` and `0x7d2cca`, loads from `0x7d2cc6`, then prints `branch delay!!`; the current harness records this run as failed after the stage marker. Run `10f1e07f...` has the same sequence, but its result says `passed` because it predates the current `GUEST_FAULT_MARKERS` update in `tools/test_hcu_boot.py`. The older “passed” result is therefore a marker-stability result from an earlier harness revision, not evidence that the guest remained healthy. The newer run is the relevant regression record.

Both logs also contain an early `Address Error, addr=0x1ff [store]` before the parent guest's machine-entry marker. This is temporally and spatially distinct from the post-UI `0x7d2cc6` fault; do not conflate it with the reproduced post-marker failure without additional evidence.

## Mapping the logged address to physical owners

The newest interpreter run reports:

- `resident_gameplay`: base `0x5012d0`, capacity `4,701,156` bytes, end `0x97ced4`.
- `current_bsp`: base `0x97ced0`, capacity `6,291,456` bytes.
- The parent binder allocates `game_state` first from `resident_gameplay`, with the CE request `HALO_PORT_GAME_STATE_SIZE`, and separately allocates the tag cache from `current_bsp` (`src/stream/hcu_memory_bind.c:33-56`).
- `HALO_PORT_GAME_STATE_SIZE = 0x305000 + 0x40000 = 0x345000` (`submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h:16-22`).

For this exact run:

| Range / value | Interpretation |
|---|---|
| game-state base `0x5012d0` | First resident allocation per `hcu_memory_bind_parent_v2` |
| game-state end `0x8462d0` | Base plus `0x345000` bytes |
| CPU subrange end `0x8062d0` | Base plus `HALO_PORT_GAME_STATE_CPU_SIZE` (`0x305000`) |
| bad address `0x7d2cc6` | `0x2d19f6` bytes from game-state base; inside the CPU subrange, but halfword-misaligned for a 4-byte access |
| second bad address `0x7d2cca` | Same CPU subrange, four bytes later, also halfword-misaligned |
| tag cache starts at `0x97ced0` | Both bad addresses are below this boundary; they are not direct pointers into the tag cache or BSP region |

This proves only that the faulting addresses numerically overlap the game-state allocation. Since the exception was caused by unaligned accesses, not an unmapped address, the log alone does *not* prove a buffer overrun or identify which CE datum/field owns the offset. A code PC (EPC) and registers/call path are required before attributing it to the player weapon, scripts, a bad packed struct, or overwritten memory.

## PCSX2 debugger capture procedure (preferred, no guest-source edits)

Use a fresh copy of a known-good PCSX2 test datapath so debugger/cache settings and pipeline-cache writes do not alter the saved run record or the user's normal profile. The current `test_hcu_boot.py` setup keeps each test's settings under its run directory; copying the `data` directory to a new scratch directory is sufficient for isolation. Do not load a saved state from a different ELF hash.

1. Start the exact ELF and ISO in interpreter mode with a scratch datapath and the debugger option. Equivalent command (replace `$DEBUG_ROOT` with a new temporary directory):

   ```sh
   APPIMAGE_EXTRACT_AND_RUN=1 /home/ai/.local/bin/pcsx2 \
     -debugger -datapath "$DEBUG_ROOT/data" -nofullscreen \
     -logfile "$DEBUG_ROOT/emulog.txt" \
     -elf "$PWD/build/hcu-parent-link-probe/hcu-gameplay-machine.elf" -- \
     "$PWD/build/hcu-m1-disc-data.iso"
   ```

   The app's official CLI describes `-debugger` as opening the debugger and breaking at the entry point. On Linux with the AppImage, the current `APPIMAGE_EXTRACT_AND_RUN=1` avoids relying on FUSE. The attempt in this analysis environment failed before the guest launched because `DISPLAY=:0.0` had no reachable X server; run from the interactive desktop/session that previously launched PCSX2.
2. In the debugger choose the `R5900` layout (not `R3000`, which is the IOP), then ensure the `Registers` dock includes the `CP0` tab and the disassembly dock is visible. Resume to the UI fault. PCSX2's official docs say the R5900 register dock exposes CP0 and the debugger imports `.symtab`/`.strtab` symbols from the boot ELF by default. This ELF contains those sections (verified with `readelf -S`), as well as DWARF sections; PCSX2's current docs say DWARF is not supported, so rely on ELF function symbols and offline `llvm-addr2line` for source mapping.
3. At the first address exception, record **Cause, BadVAddr, EPC, ErrorEPC, PC, `$ra`, `$sp`**, plus the disassembly at EPC and the surrounding instructions. In this context `BadVAddr` should match the reported `0x7d2cc6` or `0x7d2cca`, while EPC/PC should be a code address in the executable; only the latter can be passed to an address-to-line mapper.
4. If PCSX2 doesn't pause automatically on a guest exception, set an execution breakpoint at HCU's `datum_get` symbol and continue. The linked ELF has `datum_get` at `0x0021b100` (verify per exact ELF using `readelf -s`; do not hard-code across rebuilds). Break there and capture `a0` (the `data_array *`), `a1` (datum index), `$ra`, `$sp`, and the relevant stack words. The observed bad syntax index was `0x01ffe4f0`; a conditional breakpoint on `a1 == 0x01ffe4f0` would locate the script-node failure path if the debugger's condition editor accepts the documented expression syntax. This identifies the invalid datum caller, but by itself it does not explain the earlier unaligned accesses.
5. If the breakpoint UI supports data/write breakpoints, add one for `0x7d2cc6` and capture the issuing code PC before it reaches the exception handler. The official debugger page confirms generic breakpoint-dialog expressions, but I did not find authoritative confirmation that this build supports a data-access watchpoint; treat that capability as something to verify in the UI, not an assumption.
6. Convert the captured code EPC to a function/source location using the exact ELF, for example:

   ```sh
   llvm-addr2line -f -C -e build/hcu-parent-link-probe/hcu-gameplay-machine.elf 0x<CAPTURED_EPC>
   ```

   Save the debugger settings, run directory, exact ELF hash, and screenshot/log with the capture. Verify interpreter and recompiler separately only after an interpreter trace is stable.

## Temporary EE exception diagnostic fallback

If the GUI debugger cannot expose guest `BadVAddr`/EPC before the kernel continues or halts, the SDK contains a grounded fallback path. `submodules/ps2sdk/ee/eedebug/include/ee_debug.h:28-37` defines `EE_ExceptionHandler(struct st_EE_RegFrame *)` and `ee_dbg_set_level1_handler`; the frame definition in `submodules/ps2sdk/common/include/ps2_debug.h:58-111` contains GPRs, `cause`, `epc`, `errorepc`, `badvaddr`, and saved `sp`/`ra`. The PS2SDK dispatcher extracts the exception code from `frame->cause` and invokes the handler at `submodules/ps2sdk/ee/eedebug/src/ee_debug.c:33-42`; `ee_dbg_install(1)` redirects the level-1 vectors at `:173-234`.

For an isolated diagnostic image only, register a handler for the address-load and address-store exception codes (verify the EE exception-code mapping from the SDK headers), copy the frame fields into a preallocated, 16-byte-aligned static record, and stop/loop in a controlled way so the guest cannot continue mutating corrupted state. Avoid formatting or file I/O in the exception context; inspect the record through the PCSX2 debugger or expose it after a safe return to the main loop. Check existing kernel-handler ownership first, and keep the change behind a temporary compile-time diagnostic define. Do not copy PS2Link's whole `installExceptionHandlers()` unchanged: `submodules/ps2link/ee/excepHandler.c:135-147` replaces the normal VTLB/common vectors, and its callback prints and sleeps (`:45-80`), which has assumptions not established for this standalone guest.

The debug callback is a fallback proposal, not performed here. Installing it alters exception behavior and needs a throwaway source branch/image plus comparison against the unmodified ELF.

## Distinguish from the M2 CTAG/BSP capacity blocker

The post-UI target `0x7d2cc6` maps into game-state CPU bytes in `resident_gameplay`; it is not an address in the `current_bsp` tag-cache/BSP spans. The UI run does materialize/load its current CTAG and B000 sections before the fault, but the fault does not establish successful gameplay map loading. Large gameplay-map CTAG/BSP staging, separate scratch/arena sizing, collision load, and map/render qualification remain separate M2 gates. This address mapping makes the immediate reported access less likely to be a direct write into the staged CTAG bytes, but it does not rule out a bad tag-derived pointer or earlier corruption of game state.

## Evidence-backed next steps

1. Capture EPC/BadVAddr/RA/SP for the exact ELF with PCSX2 R5900 debugger, preserving the old ELF/logs and using an isolated datapath.
2. If PCSX2 cannot halt on the guest exception, capture the first `datum_get(a1=0x01ffe4f0)` in the debugger, then decide whether the temporary SDK exception callback is necessary for the earlier unaligned access.
3. Use `BadVAddr` plus EPC and disassembly to classify the instruction (word load/store, halfword access, load-delay/branch-delay context) and map its caller with symbols/`llvm-addr2line`; inspect whether the computed target pointer was derived from a tag field, game-state field, or stale pointer.
4. Only then choose an implementation fix. Do not accept “disable the offending script” or a guessed byte swap as resolving the earlier address errors unless the trace proves the same causal path.

## Source and artifact references

- [`test_hcu_boot.py`](../../tools/test_hcu_boot.py:51) — fault-marker detector; lines 255–300 implement boundary/stability logic. The pre-change `10f1e07f...` report predates this detector; compare with newer run `0da9209b...`.
- [`hcu_memory_bind.c`](../../src/stream/hcu_memory_bind.c:33) — game-state-first and tag-cache-second physical allocation.
- [`halo_ps2_limits.h`](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h:16) — game-state CPU/GPU allocation sizes.
- [`ps2_memory.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c:141) and [`game_state_xbox.c`](../../submodules/halo-ce-universal/source/saved%20games/game_state_xbox.c:186) — bound game-state base is what CE uses for the game-state buffer under `HALO_PS2`.
- [`ee_debug.h`](../../submodules/ps2sdk/ee/eedebug/include/ee_debug.h:28), [`ps2_debug.h`](../../submodules/ps2sdk/common/include/ps2_debug.h:58), and [`ee_debug.c`](../../submodules/ps2sdk/ee/eedebug/src/ee_debug.c:33) — possible bounded exception-diagnostic API/frame.
- [`excepHandler.c`](../../submodules/ps2link/ee/excepHandler.c:45) and [`exceptions.S`](../../submodules/ps2link/ee/exceptions.S:84) — PS2Link example captures BadVAddr/Cause/EPC and GPRs, but is not assumed safe to transplant wholesale.
- Exact guest artifacts: `build/hcu-ps2-closure/emulator-m1-interpreter-0da9209b68cf495db52cf4f1fd49b7a2/{result.json,emulog.txt,launcher.log}` and earlier harness result `.../emulator-m1-interpreter-10f1e07f70b0473e96f10dd26474320f/{result.json,emulog.txt,launcher.log}`; linked ELF and map at `build/hcu-parent-link-probe/hcu-gameplay-machine.elf` and `hcu-parent-link.map`.
- PCSX2 official [Debugger documentation](https://pcsx2.net/docs/advanced/debugger/) and [Command Line Options](https://pcsx2.net/docs/advanced/cli/) document the R5900/CP0 UI, symbol import, and `-debugger` entry-break option.
