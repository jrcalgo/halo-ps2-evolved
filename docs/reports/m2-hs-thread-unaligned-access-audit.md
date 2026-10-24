# M2 `hs thread` unaligned-access audit

**Scope.** Report-only review of the latest PCSX2 interpreter trace and its owning Halo CE data structure. No HCU runtime, tool, or plan files were changed by this investigation. The exact currently inspected ELF is `build/hcu-parent-link-probe/hcu-gameplay-machine.elf` (SHA-256 `5d01c22d52695b2fec5490350a8dca5098471f1796cac53ae84e39a96414f38d`). The corresponding latest interpreter run is `build/hcu-ps2-closure/emulator-m1-interpreter-bafa24f332b64801b87328df0367914e/` (result and logs identify the same ELF hash and source pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`).

## Findings

The run logs the `hs thread` allocation at game-state offset `0x2d1984`, size `0x21838`; after `m2-ui-map-loaded`, PCSX2 reports unaligned stores at `0x7d2dc6` and `0x7d2dca`, then loads at `0x7d2dc6`, followed by `branch delay!!` (`.../emulog.txt:444,548,553-558`). With the run's game-state base `0x5013d0`, the first bad address is base-relative `0x2d19f6`, exactly `0x72` bytes from the logged `hs thread` allocation start. The fault address is an effective data address, not the issuing instruction address; the log does not provide EPC, `$ra`, or a caller stack.

The allocation size independently identifies its layout: `0x21838 = sizeof(data_array) + 0x100 * 0x218`. HCU allocates exactly 256 records of size `0x218` in `hs_runtime_initialize` (`source/hs/hs_runtime.c:778`), and `data_allocation_size` returns `maximum_count*size + sizeof(struct data_array)` (`source/memory/data.c:85-89`). The datum size is asserted as `0x218` (`hs_runtime.c:420-434`). `data_initialize` sets `data->data = data + 1` (`data.c:91-108`). With `TAG_STRING_LENGTH == 31` (`source/tag_files/tag_files.h:13-16`), the R5900 ILP32 layout of `struct data_array` is 0x38 bytes (corroborated by the linked code's `lw` of the `data` pointer at offset `0x34` in `datum_try_and_get`, disassembly below).

There is an important arithmetic/layout discrepancy in the proposed interpretation that the fault is at the `type`/`flags` boundary of the first `hs_thread_datum`. Relative to the logged allocation start:

```text
allocation start                 +0x00
data_array header                +0x38
first hs_thread_datum             +0x38
identifier                        +0x38..+0x39
type / flags                      +0x3a / +0x3b
script_index                      +0x3c..+0x3f
sleep_until                       +0x40..+0x43
previous_sleep_until              +0x44..+0x47
stack pointer                     +0x48..+0x4b
result                            +0x4c..+0x4f
stack_data                        +0x50..+0x24f
observed bad address              +0x72
```

Therefore `+0x72` is **not** the first record's `type`/`flags` boundary (`+0x3a/+0x3b`). Under the source layout it is byte `stack_data[0x22]` in the first record. The expression `0x38 + 2` is `0x3a`, not `0x72`; the latter would require a 0x70-byte header, which is contradicted by both the source struct and linked access at `data_array.data` offset `0x34`. This is not merely theoretical: the fourth-byte-aligned-word access at an effective address ending in `...f6` is misaligned, while the destination lies in the thread's inline stack bytes. Do not attribute it to the type/flags fields or change their packing based on this trace.

The `hs thread` pool is a strong owner match, but it is not yet a causal attribution. The trace establishes that the bad effective addresses overlap that allocation; it does not prove that an HS thread pointer computed them, that the pointer was derived from the `stack_data` member, or whether earlier corruption redirected an otherwise valid access. The repeated stores 4 bytes apart and subsequent load to the first address are compatible with a multi-field update/copy involving an invalid or misaligned base, but this is inference only. The observed byte offset being inside `stack_data` makes stack-frame evolution worth checking first, not a proven cause.

## Relevant source paths and machine evidence

- `hs_thread_new` obtains a slot with `datum_new`, initializes `stack` to the inline `stack_data`, initializes the base frame, and writes `type`, `script_index`, `flags`, and sleep state (`source/hs/hs_runtime.c:1342-1378`). The `hs_stack_frame` begins with pointer, `long`, pointer, `short`, and flexible payload fields (`hs_runtime.c:404-411`); these naturally aligned fields should be checked if the base frame pointer is shifted/corrupted.
- The script thread loop dereferences `hs_thread_get(thread_index)` and then walks the current stack frame (`hs_runtime.c:2684-2737`). `hs_stack_allocate` obtains the datum and checks stack bounds before publishing the resulting frame; in the linked ELF it starts at `0x001f796c`, and its disassembly includes a load of `data_array.data` from offset `0x34` and a `datum_get` call. This is a useful candidate function to breakpoint, but absent EPC the current trace does not prove it issued the bad store.
- `datum_new` computes the record address as `data->data + size * absolute_index`, initializes the datum, and advances `first_free_absolute_index` (`source/memory/data.c:296-339`). A first new thread has a stride-aligned record start. `hs_thread_delete` calls `datum_delete`, which only clears the record's identifier and adjusts array counters (`hs_runtime.c:1381-1389`, `source/memory/data.c:351-374`); thread deletion alone does not explain a write at `stack_data+0x22`.
- `hs_thread_main` validates `valid_thread(thread)` before continuing through the script stack (`hs_runtime.c:2684-2733`). The macro checks the thread record lies in the array and that `stack` and the frame's payload/fill mark lie inside this record's inline stack (`hs_runtime.c:339-346`). This makes a first-instruction breakpoint on `hs_thread_main` useful for detecting preexisting stack-pointer damage, but the validation itself does not prove every later pointer is valid.
- The prior invalid syntax datum diagnostic may be a later, separate manifestation. The current run reaches address errors and `branch delay!!`; absence/presence of a later `hs-invalid-node` marker should not be treated as the source of these first unaligned accesses.

### Disassembly reproducibility

The ELF is ELF32 MIPS/N32, contains symbols and DWARF, and is not stripped. Commands below were run against the SHA above:

```sh
llvm-nm -n build/hcu-parent-link-probe/hcu-gameplay-machine.elf \
  | rg 'hs_stack_allocate|hs_thread_main|hs_runtime_initialize|datum_try_and_get|datum_new|datum_get|game_state_data_new'
llvm-objdump -d --start-address=0x0021b000 --stop-address=0x0021b100 \
  build/hcu-parent-link-probe/hcu-gameplay-machine.elf
llvm-objdump -d --start-address=0x001f796c --stop-address=0x001f7b90 \
  build/hcu-parent-link-probe/hcu-gameplay-machine.elf
```

`datum_try_and_get` disassembly at `0x0021b0b8-0x0021b0c8` reads `data_array.size` at `+0x22`, then `data_array.data` at `+0x34`, then reads the datum identifier. This is direct machine-code confirmation of the 0x38-byte header and the source-derived data pointer offset. The linked symbols include `datum_get` at `0x0021b100` and `datum_new` at `0x0021b554`; the `hs_stack_allocate` symbol is `0x001f796c`, and `hs_thread_main` is `0x001f8cf0`. These addresses are exact-build-only; recalculate after every link.

The `hs_thread_new` static symbol does not appear in `llvm-nm` for this image (likely inlined or internalized); do not assume a stable breakpoint address for it. Inspect the callers in the exact linked ELF or use its DWARF/source mapping after capturing a real PC.

## Best next debugger/instrumentation sequence

1. Keep the exact ELF and run directory immutable. In the PCSX2 R5900 debugger (not the IOP/R3000 view), break on the first EE Address Error and record `Cause`, `BadVAddr`, `EPC`, `ErrorEPC`, current PC, `$ra`, `$sp`, and the instruction at EPC. Expected `BadVAddr` is `0x7d2dc6` for the current run; it is not the PC. If the debugger will not stop on exception, set an execution breakpoint on the exact ELF's `hs_stack_allocate` (`0x001f796c`) and `hs_thread_main` (`0x001f8cf0`) and continue until the failure; at each breakpoint capture the thread index, `hs_thread_data` pointer, resulting datum pointer, `thread->stack`, and the computed frame destination.
2. Add a data watchpoint for the current bad effective address `0x7d2dc6` if that PCSX2 build supports EE write watchpoints. At the first hit, record the instruction and effective-address base register. Since the bad target is `thread base + 0x72` by the run's allocation logging, compare the effective base to the computed first-record address `hs_thread_data->data + 0x218*index`; do not interpret it as a `type` field without that comparison.
3. If watchpoints are unavailable, break on exact `hs_stack_allocate` and single-step all stores to the frame/stack region while watching `thread->stack`, `thread->stack->size`, frame `data`, and `size`. Add an execution breakpoint at `datum_get` (`0x0021b100`) only as an adjunct: it can expose invalid datum callers, but cannot by itself identify the writer that first accesses `0x7d2dc6`.
4. If a source-level diagnostic build is necessary, instrument only the HS stack boundary: immediately before each write in `hs_stack_allocate` / stack-frame push/pop, log the thread datum pointer, `stack_data` start/end, `thread->stack`, frame address, member offset, write width, computed destination, `thread_index`, and `$ra`-equivalent return address. Check that `thread->stack` is aligned to the compiled `hs_stack_frame` requirements and lies wholly in the same 0x218-byte datum. Use a preallocated record and defer printing until normal execution; do not print, allocate, or call FileXio inside the EE exception handler.
5. Correlate the captured EPC with `llvm-addr2line -f -C -e <exact-elf> <EPC>` and inspect that function's disassembly around the fault. Preserve pre-marker BIOS `0x1ff` separately; it is not the post-UI `0x7d2dc6` trace.

Do not “fix” this by changing `hs_thread_datum` packing, replacing unaligned operations with byte copies globally, or deleting/neutralizing scripts. A code change should follow only after the exact writing instruction and pointer provenance are captured.

## Current conclusion and open questions

**Established:** the exact interpreter run reaches `m2-ui-map-loaded`, then fails on unaligned stores/loads at game-state base-relative `0x2d19f6` / `0x2d19fa`; the logged `hs thread` game-state allocation covers the target; the target lies within the first datum's `stack_data` bytes under the compiled 0x38-byte data-array header and 0x218-byte datum stride; linked code confirms the data pointer field at offset `0x34`.

**Not established:** which instruction issues the bad access; whether the pointer is a thread stack/frame pointer, unrelated alias, or corruption; whether the first store causes the later `branch delay!!`; and whether a script/GC/data-array path is involved. The next decisive evidence is EPC plus registers at the first store (or a write watchpoint), not another source-level hypothesis.

**Halo-64 comparison:** Halo-64's N64 notes explain why that port removed/stubbed broad actor/script/effect systems under its smaller memory/CPU budget, but that is not a valid fix or precedent for this PS2 build. The relevant behavior must remain CE's script/thread semantics; the PS2 diagnosis should use the CE HCU code and the PS2-specific R5900 trace rather than inheriting N64 cuts (`submodules/halo-64/port/n64/NOTES.md:33` for the rendering/state distinction; the hardware constraints differ).
