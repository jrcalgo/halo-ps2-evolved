# M2 interpreter fault: independent artifact-delta audit

## Scope and outcome

This is a report-only comparison of the preserved failing image and the latest rebuilt image, their recorded interpreter runs, the data ISO identity, and the current HCU source layout. No source, build output, plan, or emulator state was modified by this audit.

Both exact interpreter runs reached `m2-ui-map-loaded` and then logged the same PS2 address-error sequence at the same effective address, `0x7d2dc6` (including stores at `0x7d2dc6` and `0x7d2dca`, followed by a load at `0x7d2dc6`). The latest ELF’s temporary allocation-owner trace maps that address into the first `hs_thread_datum`’s inline `stack_data`, at byte index `0x22`. This identifies the data object/range implicated by the reported effective address, **not** the instruction, source line, or logical writer that caused it. The PCSX2 log does not expose EPC, Cause, BadVAddr as a CPU exception frame, or a watchpoint trace; the text `Address Error, addr=...` is not an EPC.

The key implication is that this is reproducible across two distinct ELFs/source-output states and occurs shortly after the map-loaded marker. It does not yet establish whether an HCU instruction, a PS2 service, a script VM path, or a PCSX2 interpreter-specific behavior performs the misaligned operation. A guest-side EPC/cause capture or a debugger data watchpoint is required before attributing a code line.

## Exact artifacts and pins

| Item | Identity |
|---|---|
| Preserved failing ELF | `build/m2-artifacts/failing-b347420832736d53.elf`, SHA-256 `b347420832736d5370c3dfa338522b9849d1cc1e726d554d0590ead49fb9c970`, 4,412,868 bytes |
| Latest diagnostic ELF | `build/hcu-parent-link-probe/hcu-gameplay-machine.elf`, SHA-256 `5d01c22d52695b2fec5490350a8dca5098471f1796cac53ae84e39a96414f38d`, 4,412,908 bytes |
| Data ISO passed to both recorded runs | `build/m2-artifacts/data-79f2855a59534836.iso`, SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79` (the run manifest names the equivalent current path `build/hcu-m1-disc-data.iso`) |
| Parent source pin recorded by both runs | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` |
| HCU submodule pin recorded by both runs | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| halo-ps2 submodule pin recorded by both runs | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Latest HCU `game_state.c` working-tree state | Modified relative to the recorded HCU pin to add the temporary `HALO_PS2` owner trace in `source/saved games/game_state.c`; current file SHA-256 `804efe61bd9eb9db8c74c6e8d75d7a2684eb13296b3983c8370507e0f949a24e` (as reported by the parent session). The pin alone does not encode this uncommitted source delta. |

The run-result JSONs and full guest logs are retained beside each run:

* Preserved artifact run: `build/hcu-ps2-closure/emulator-m1-interpreter-6f826d3c62fc4a278f31b34be974f0b6/result.json` (SHA-256 `3b5f188efb1b0a17c25736565668d7ee0e0105298c673d17052cfbe9588b8ce7`); log `emulog.txt` (SHA-256 `79c94c24ef2db8d74bed9bb83161248301dcaf76c98fbeb4b6b14b40ab8ae9b9`).
* Latest diagnostic artifact run: `build/hcu-ps2-closure/emulator-m1-interpreter-bafa24f332b64801b87328df0367914e/result.json` (SHA-256 `8e60ff0331def377b93138d06795be99745f0ce88cd17af034364d400c289b21`); log `emulog.txt` (SHA-256 `aecc021c8453b5e1d4ae3f65078aa188fe337065c48210dc21f260e8ce2d34db`).

Both result records report `status: failed`, `stage: m2-ui`, interpreter mode, the same ISO digest and three source pins, and the ELF digest listed above. Their outcome is a post-marker guest exception, not a rendering result.

## ELF comparison

Both files are statically linked ELF32 little-endian MIPS N32 executables with debug information. The latest ELF is 40 bytes larger. `readelf -S` reports:

| Section | Preserved ELF | Latest ELF | Delta |
|---|---:|---:|---:|
| `.text` size | `0x18b7d8` | `0x18b730` | `-0xa8` |
| `.data` address / size | `0x0028b880` / `0x011db4` | `0x0028b780` / `0x011db4` | address `-0x100` |
| `.rodata` address / size | `0x0029d680` / `0x05f638` | `0x0029d580` / `0x05f708` | address `-0x100`, size `+0xd0` |
| `.bss` address / size | `0x002fcd80` / `0x20441c` | `0x002fcd80` / `0x20441c` | unchanged |

The output bytes and section layout are therefore not identical, even though the recorded source pins and disc digest match. The changed `.text`, `.rodata`, and data addresses caution against assuming that the owner-probe ELF differs from the preserved binary only by a diagnostic string. Do not use cross-ELF code addresses without symbolizing against the exact ELF used in that run. The shared failure effective address is a runtime data address, not a code address.

## Runtime comparison and address arithmetic

The preserved-run log reports `m2-ui-map-loaded` at 31.8715 s, followed by the first `Address Error` at 32.1361 s: 0.2646 s later. The latest-run log reports the marker at 30.7372 s and the first error at 31.0016 s: 0.2644 s later. Both then report the same sequence of unaligned stores/loads at `0x7d2dc6` and `0x7d2dca`, followed by a branch-delay diagnostic. This close marker-relative timing is consistent with the same post-load behavior being exercised; it is not proof of an identical instruction path.

In the latest run, the diagnostic line at 6.7780 s records:

```text
owner=hs thread type=data array offset=0x2d1984 size=0x21838 base=0x5013d0
```

Arithmetic from those *observed* values:

* `0x7d2dc6 - 0x5013d0 = 0x2d19f6` bytes into the game-state CPU allocation.
* `0x2d19f6 - 0x2d1984 = 0x72` bytes into the `hs thread` allocation.
* Its `data_array` header is `0x38` bytes, leaving `0x72 - 0x38 = 0x3a` bytes into element zero.
* `hs_thread_datum.stack_data` begins at offset `0x18` in the `0x218`-byte record, so the address corresponds to `stack_data[0x3a - 0x18]`, index `0x22`.

The owner interval is `[0x7d2d54, 0x7f458c)` by arithmetic from the trace’s base, offset, and size, so all logged addresses in this sequence fall inside the same allocation. Source layout corroboration: `submodules/halo-ce-universal/source/hs/hs_runtime.c:420-434` lays out `hs_thread_datum` and asserts its `0x218` size; the inline byte buffer is `stack_data[0x200]`. `submodules/halo-ce-universal/source/saved games/game_state.c:873-891` creates a named data-array allocation and initializes its records. `game_state_malloc` records allocation size before advancing the CPU allocation pointer (`game_state.c`, around lines 549-582); the temporary trace is after the allocation record and before that pointer advance, so it does not alter array size/order or data contents.

This establishes only a destination/data neighborhood. An effective address reported by the emulator does not say which instruction generated it, whether the underlying expression was a valid or corrupted pointer, whether a multi-byte operation straddles the address, or which earlier write may have damaged the pointer. The report also cannot determine whether the logged address is the initial exception’s BadVAddr or a later retried/secondary access; the log presents it as the reported faulting address but omits the exception frame.

## REA and static-tool limits

REA `open_binary` successfully recognized the latest file as MIPS ELF and recorded its SHA-256. The active analysis providers then rejected the target: Ghidra reports that machine-specific MIPS variants need a separately supported processor profile; Hopper does not admit MIPS; IDA is not configured and its adapter also has no verified MIPS lane. Thus REA supplied file-format/architecture identification, not procedures, disassembly, pseudocode, or address-to-source evidence. Host `/usr/bin/objdump` recognizes the file as ELF32 little-endian but reports `architecture: UNKNOWN!`; no R5900-capable `objdump`/`addr2line` was found in the checked tool paths. This report deliberately does not claim an REA decompilation or an instruction/source attribution.

## Recommended evidence needed to resolve the source line

1. Use the exact latest ELF (`5d01c22d…`) and current matching ISO/configuration to capture the EE exception context at the **first** `Address Error`: CP0 Cause, EPC, BadVAddr, Status, plus GPRs and HI/LO. The supplied log has the effective address only; preserve a raw PCSX2 debugger capture or guest-side exception frame.
2. If the emulator’s debugger can be driven, set a guest data write/access watchpoint on `0x7d2dc6` (aligned range covering at least the surrounding `0x7d2dc0–0x7d2dd0`) before continuing from the ELF entry. Record the first hit’s EPC, access width, direction, and call stack; distinguish watched accesses from the repeated post-exception log spam.
3. Symbolize EPC and the delay-slot address against this exact ELF’s DWARF/symbol table with an R5900-aware `addr2line`/disassembler. Confirm source and line at the recorded HCU working-tree revision, not solely at the submodule pin.
4. Add instrumentation only if debugger capture is unavailable. Prefer a temporary, narrowly scoped PS2 exception handler/logging hook that chains/preserves the existing handler and prints the full exception state; verify the handler does not mask or transform the fault. Keep this diagnostic distinct from the current data-owner print.
5. Once the exact faulting instruction is known, trace where its effective address or base/index register originated. If that points into `hs_thread_datum.stack_data`, inspect the script/thread state lifecycle and writes around that record before changing array layout or alignment.

## Limits and conclusion

The binaries were not launched as host programs; only the retained PCSX2 records were inspected. ISO execution is not established: the result records use an ELF plus a data-disc argument (`boot_from_disc` false in the harness contract). The ISO digest is identical between runs, but this audit does not claim byte-level equivalence for the HLE host `maps/ui.hp2` root.

The most defensible conclusion is: two exact interpreter runs, on different MIPS ELFs with matching source pins and disc data, show the same post-UI-load unaligned access sequence into an address that the newer build’s instrumentation maps to the first HaloScript thread’s inline stack bytes. This substantially narrows the data owner while leaving the instruction, cause, and responsible source path unresolved. No fix should be selected solely from this address-to-data mapping.
