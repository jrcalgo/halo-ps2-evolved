# M2 exact artifact and PCSX2 launch audit — current rebuild

Date: 2026-10-21. This report extends the prior post-marker fault audit with an
REA inspection of the preserved failing image and the current rebuilt combined
ELF, and a format/content check of the supplied data ISO. It does not establish
a guest run for the current ELF, a bootable PS2 disc, a rendered scene, or M2
acceptance.

## Exact artifacts and source identity

| Role | Artifact | SHA-256 | Size |
|---|---|---|---:|
| Preserved pre-alignment failure | `build/m2-artifacts/failing-b347420832736d53.elf` | `b347420832736d5370c3dfa338522b9849d1cc1e726d554d0590ead49fb9c970` | 4,412,868 B |
| Current rebuilt combined HCU diagnostic | `build/hcu-parent-link-probe/hcu-gameplay-machine.elf` | `20950de9940b058a80a175b90824317607cf6ca09078747400001273fbd554ca` | 4,422,212 B |
| M2 data ISO (both retained copies) | `build/m2-artifacts/data-79f2855a59534836.iso`, `build/hcu-m1-disc-data.iso` | `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79` | 34,240,512 B |

The current checkout identifies parent HEAD `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU HEAD `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 HEAD `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. These are commit identities, not complete source pins: parent and submodule worktrees are dirty. The current HCU `source/hs/hs_runtime.c` SHA-256 is `5da91e2d6f8031e9af546a4625baeb75eed89f12deeeb957f26036425dc9c7ec`. The current link report binds the no-bootstrap rooted closure SHA-256 `0645f18c1bc7332b8f4ec161b85b947653e4673fdab1a7fa57fac4e7de64a3e1`; it still marks M0 open and the link itself diagnostic-only.

## REA and binary-layout observations

REA `open_binary` recognized the current ELF as ELF/MIPS with SHA-256
`20950de9940b058a80a175b90824317607cf6ca09078747400001273fbd554ca`. Its
current `binary_session` lists Ghidra as unsupported for this machine-specific
MIPS variant, Hopper as not admitting MIPS, and IDA as having no verified MIPS
lane. REA's GNU `objdump` operation runs successfully but reports
`architecture: UNKNOWN!` for these ELF32-little files. The ISO is rejected by
REA `open_binary` as an unsupported executable binary format; no decompilation
or ISO-package REA result is claimed.

Artifact-bound REA Evidence IDs:

- Current ELF fingerprint: `ev_2606c2940455508e7b976635c4d7ae19998faa26696d4d4836beb4f794e6dcd6`.
- Current ELF section headers: `ev_ed0240258f9a1b0d751b1aef147eaaf7c9303d63c8300408cc7fbf7b5aa60034`.
- Preserved failure ELF fingerprint: `ev_93d8515aff719898faf2b64ab51d3f7d8c621237b945c2a297376d40ba89e891`.
- Preserved failure ELF section headers: `ev_dbc9ffd78fa6723942beb190525a2075637681ecddcf484ba84c8571f60af07c`.
- Preserved failure ELF symbols: `ev_f8106eed99b5fbf323c330bac31033b0276efe71605a0d122db3d82ccd38c48d`.
- Current ELF symbols: `ev_8f3fa7aaadd407349d99dc2d135958e0d72447a7cc4ca4017286aa5993a764db`.

REA/objdump observed the same ELF32 little-endian executable entry point,
`0x001010b0`, in both files. `readelf` further reports MIPS 5900 / `abi2`
flags in both, consistent with the configured PS2 `-mabi=n32` build; it does
not show a transition to another ABI. Program headers differ only by `0x100`
bytes in this pair: the old LOAD has `p_filesz=0x1fcd04`, `p_memsz=0x40119c`,
while the current LOAD has `p_filesz=0x1fce04`, `p_memsz=0x40129c`. The current
`.text` is 0x40 bytes larger, `.rodata` is 0xc0 bytes larger, and `.bss` has
the same `0x20441c` size but begins 0x100 bytes later. This is a small static
image/layout delta, not evidence that the runtime fault was fixed or caused by
placement.

The symbol table provides a source/build cross-check, not execution evidence.
The preserved failure has `hs_stack_allocate` at `0x001f78b8` (size `0x224`)
and has no linked `hs_syntax_get_checked` symbol. The current image has
`hs_stack_allocate` at `0x001f7a98` (size `0x244`) and includes
`hs_syntax_get_checked` at `0x001f7290` (size `0xb4`). `scenario_load` keeps
size `0xf4` in both; its address moves from `0x0024cf9c` to `0x0024cfdc`.
These differences are consistent with later source/build changes, including
the documented PS2 stack-alignment and checked-syntax diagnostics, but no
instruction-level causal comparison is asserted because REA's available
disassembler does not support this R5900 variant. The existing exact-run fault
report remains the authoritative evidence for the prior `0x7d2cc6` guest
data-address exception and the subsequent clean 27db/4a UI-map runs.

## ISO layout and the BIOS prompt

REA cannot parse this ISO as an executable binary. Read-only `xorriso` inspection
reports ISO volume ID `ISOIMAGE`, no El Torito boot information, and exactly two
files: `/maps/ui.map` (33,582,080 B, SHA-256
`8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e`) and
`/maps/ui.hp2` (282,624 B, SHA-256
`c5b4760afa3b3e8484dc232b2332fb6855d52c0ca271c4427e29c745eec7b51c`).
Neither `SYSTEM.CNF` nor `BOOT.ELF` is present. This is a data-only ISO for
asset reads, not a bootable PlayStation 2 game disc. **Inference:** if this ISO
is selected as the BIOS boot disc, the “Please insert a PlayStation or
PlayStation 2 format disc” prompt is expected; it says nothing about the ELF's
ability to start. The accepted harness mode starts the ELF directly with
PCSX2's `-elf` option and treats the ISO/files as data inputs, rather than
asking the BIOS to boot the data ISO.

## Current PCSX2 attempt and correlation boundary

I attempted the current ELF using:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 QT_QPA_PLATFORM=offscreen \
  python3 tools/test_hcu_boot.py --mode interpreter --stage m2-ui \
  --stable-seconds 10 --timeout 90 \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf
```

The run manifest binds the exact current ELF hash above, but PCSX2 exited with
status 127 before the first guest marker. The launcher log says the selected
AppImage has no Qt `offscreen` platform plugin (it advertises Wayland and XCB).
The normal XCB attempt likewise could not connect to configured display `:0.0`;
the `:110` attempt failed before guest startup because Xvfb could not create
any X listener while `/tmp/.X11-unix` is owned by `nobody:nogroup`. Therefore
these attempts are host GUI-launch failures, not guest behavior and not a new
runtime regression. No current-image PCSX2 guest log/screenshot exists.

The latest valid guest evidence is still the distinct prior ELF
`4a9bcce6fcc15b5f41298073ad0d8c37304528ec1148aac33bf2caf7757ba41e`: its UI
scenario reaches `m2-ui-map-loaded` in interpreter and recompiler and remains
fault-free over the recorded stability intervals, but its viewport is black.
It is UI/tag-load evidence only. The present `20950de...` link is explicitly
diagnostic-only, with parent `main` retaining HCU shell without calling it;
the integrated gameplay entry is a separate path in the link result and has
not been observed on this exact ELF. Do not equate the UI-map success pair,
the current unlaunched ELF, and the BIOS disc prompt.

## Assessment and next action

1. Do not try to boot the data ISO from the BIOS. Use the direct `-elf` route
   with the data ISO or HLE `host:/` assets, or build a separate bootable PS2
   disc with a valid `SYSTEM.CNF`/boot executable if optical-boot qualification
   is required.
2. Restore a working PCSX2 GUI display path (or invoke an existing authorized
   desktop session) before interpreting any new test as guest evidence. Do not
   change `/tmp/.X11-unix` ownership or replace system Qt packages to get around
   this environment boundary.
3. Rebuild and retain the exact integrated production ELF, then run that hash
   in both PCSX2 modes through UI-load and the eventual gameplay-map stage.
   The current link report states that its entry does not call the parent-to-HCU
   path and that the UI callback alone is implemented, so this ELF is not yet
   the M2/M3 gameplay acceptance image.
4. Keep the prior stack-alignment fix regression tests, but do not claim the
   REA section/symbol comparison as the cause of the old exception. EPC or
   instrumented caller evidence is still required to resolve an actual future
   guest fault.

Focused tests after the audit: `python3 -m pytest -q
tests/test_hs_ps2_stack_alignment.py tests/test_hcu_boot_physical.py
tests/test_hcu_parent_link_probe.py tests/test_hcu_map_catalog.py
tests/test_retail_ui_ctag_mount.py tests/test_hp2_stream_retail.py` → **24
passed**. This validates host contracts/build-report checks, not the missing
current-image PCSX2 guest run.
