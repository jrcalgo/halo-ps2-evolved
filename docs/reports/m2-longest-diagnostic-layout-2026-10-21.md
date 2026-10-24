# Longest diagnostic memory-layout build — 2026-10-21

## Result

Added an opt-in `--tag-cache-bytes` argument to `tools/hcu_parent_link_probe.py` so a non-default boot-fixed tag/BSP division can be built without changing `WORLD_HCU_TAG_CACHE_BYTES`'s 2 MiB default. Non-default spans receive distinct parent-object, ELF, map, memory-audit, and result names; the result records the selected size. The value must be positive, 16-byte aligned, and below the 6,291,456-byte `current_bsp` total. This is a diagnostics facility, not approval to change the product profile.

The selected Longest candidate split was tag `4,477,120` bytes and BSP `1,814,336` bytes, a sum of exactly `6,291,456` bytes. Command:

```sh
python3 tools/hcu_parent_link_probe.py --asset-profile host --tag-cache-bytes 4477120
```

The build completed and emitted `build/hcu-parent-link-probe/result-tagcache-4477120.json`. The machine ELF is `build/hcu-parent-link-probe/hcu-gameplay-machine-tagcache-4477120.elf`, SHA-256 `5bc92000c1e6cf724e532edc5738a3834b27665a7e4419faecc31c85fd020229`; its map SHA-256 is `30b32f853976323eaa28a34af5d856408366fe57f3a2a98be41ea3bb7e1dc721`; memory-audit SHA-256 is `844f6b5eecd8a5872e50f1d1ba7a40d5c511d879a19fcd534dbf49464e6f2a7f`. The closure root object and source submodules were dirty; recorded parent/HCU/halo-ps2 pins are `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. Re-freeze source-file hashes before treating the result as reproducible from committed inputs.

The JSON reports `status=linked-diagnostic`, `acceptance=false`, zero undefined symbols, 2,087,044 LOAD file bytes, 2,114,588 BSS bytes, and necessary static placement checks passing. Its estimated minimum headroom before the untouched reserve is 9,674 bytes, but it explicitly does not verify the runtime boot-allocation pointer or target stack bounds. The result records `tag_cache_bytes=4,477,120`; it does not report a guest-derived CE claims allocation, arena canaries, or physical addresses.

Guest command attempted:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py \
  --mode interpreter --stage m3-memory-ready --timeout 75 \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine-tagcache-4477120.elf \
  --disc build/hcu-m1-disc-data.iso
```

It exited 127 before guest startup. `launcher.log` reports that Qt could not connect to the selected X display and could not initialize `xcb`. Retrying under `xvfb-run -a` produced the same pre-guest failure at its allocated display; an independent `xdpyinfo` check also could not connect. Xvfb's diagnostic identifies this sandbox's `/tmp/.X11-unix` directory as owned by `nobody`, while the server requires it to be root-owned to create its socket. No permission/ownership changes were attempted. The guest log is empty. This is host display infrastructure failure, not an image failure. No conclusion is made about the guest runtime split.

## Interpretation and limits

This experiment validates only that the build tooling can produce and distinguish the Longest candidate split while leaving default build settings and named region totals unchanged. It does not prove the CE claims buffer is 786,432 bytes at runtime, physical memory placement/canaries, any CTAG or CBSP materialization, actual `scenario_load`, collision/resource consumers, BSP unload/retry, full map live-set fit, or rendered pixels. The candidate must remain diagnostic and catalog admission remains closed.

The supported REA session opened this ELF and identified it as MIPS with SHA-256 above, but REA's currently available Ghidra/Hopper/IDA providers reject the R5900 MIPS profile. The exact binary therefore has no REA pseudocode in this session; linked ELF/map/memory-audit artifacts and any future PCSX2 logs are the available evidence. This constraint does not authorize interpreting strings or a linker map as proof of runtime behavior.

The next implementation dependency is still the bounded, no-write CTAG validation followed by post-unload direct-to-final-tag-span materialization described in sections B–E of [`m2-capacity-next-slice-2026-10-21.md`](m2-capacity-next-slice-2026-10-21.md). The existing HP2 visitor can deliver decoded bytes to a sink, but emits bytes before its final section CRC result; a safe cache publisher must preserve CE's unpublished failure contract and validate the complete CTAG image and relocations before publishing pointers.
