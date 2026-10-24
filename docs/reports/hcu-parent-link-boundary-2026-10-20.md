# HCU + halo-ps2 Parent Link Boundary Probe

Date: 2026-10-20

This probe checks whether the current HCU R5900 object closure and the parent
halo-ps2 viewer objects can occupy one N32 EE executable. It is a link and
budget diagnostic, not a playable build or proof of production memory binding.

## Findings

1. The individual HCU and parent ELFs both use ELF32 little-endian N32 R5900
   ABI. HCU's `port/ps2/src/ps2_main.c` is currently a separate entry point,
   while `tools/ee-world.mk` builds the parent `engine/src/main.c` as the viewer
   executable. The HCU closure's linker separately includes `rooted.o`, PS2
   edge/memory/CRT objects, and the PS2SDK EE startup linkfile.
2. The first relocatable joint link failed on `model_find_marker`. HCU exports
   `short model_find_marker(short model_index, const char *name)` in
   `source/models/models.c`; the parent renderer exported
   `int model_find_marker(const model_section *, const model_info *, const
   char *)`. These are incompatible C symbols. The parent API was namespaced to
   `ps2_model_find_marker` in `engine/src/world/{model.c,model.h}` and its only
   runtime caller `engine/src/sim/fpview.c`; the parent model tests were updated.
   A rerun of `ld -r` across HCU rooted/platform objects and all parent viewer
   objects completed, and a symbol intersection check found no remaining
   duplicate global definitions in that object set.
3. A fully linked joint ELF using the external-only HCU memory provider and
   parent viewer sources linked successfully; `nm -u` reports zero undefined
   symbols. Artifact: `/tmp/hcu-parent-link-external-memory.elf`, SHA-256
   `062b3064c900e0856dabaa20f555be357bfbd8b2cc3d1c873d2ee295888164f0`.
   `size -A` reports `.text` 1,680,592, `.rodata` 369,336, `.data` 99,056,
   `.sdata` 4, and `.bss` 2,746,840 bytes. Thus the static text/constant/data
   sum is **2,148,988 bytes**, exceeding `elf_static` (2,097,152) by **51,836
   bytes**. The linked BSS is below `resident_gameplay` (6,815,744), but this is
   only section accounting; no address placement, overlap, high-water, or free
   RAM has been measured.
4. The bootstrap-memory joint ELF also linked, but its BSS was 10,369,456
   bytes, which exceeds `resident_gameplay` by 3,553,712 bytes. It is not a
   valid memory configuration. The external-only profile is the relevant
   direction, but its production caller does not exist yet.

## Explicit non-claims and remaining integration work

- The joint link was built from existing HCU closure objects and a direct
  parent viewer compile to `/tmp`; it does not change the two maintained build
  targets or prove they will stay linked together reproducibly.
- `-u halo_shell_main` retains the CE shell in the ELF, but parent
  `engine/src/main.c` does not call it. HCU `ps2_main.c` is not the entrypoint
  in this combined link. No CE tick or map load ran.
- The HCU wrapper allocator is linked, but parent `main` still calls `malloc`
  for its viewer arena before any HCU region bind. The parent allocation order
  and HCU wrapper policy therefore cannot be considered compatible merely
  because the linker succeeded.
- No call currently passes `mem_layout_v2_init` regions into HCU's
  `physical_memory_bind_*` functions before `physical_memory_allocate`; no
  tag-cache/BSP/validator scratch lifecycle or DVD owner is registered.
- The external-only link is still over `elf_static`; reduce or relocate only
  after attributing the 51,836-byte overage to sections and measuring the
  resulting EE performance. Do not borrow `uncommitted_reserve` to hide it.

## Reproduction notes

The source inputs were HCU `all-no-bootstrap-memory/rooted.o` plus its generated
platform object and PS2 ABI/CRT/edge/provider objects, with the direct parent
viewer compile from `tools/ee-world.mk` under `WORLD_OUTPUT=/tmp`, linked by the
pinned PS2SDK R5900 GCC and `ee/startup/linkfile`. The parent source compile
used the exact command emitted by `make -f tools/ee-world.mk` with explicit
`PS2DEV`, `PS2SDK`, and `PATH` for the pinned toolchain. Link flags included
`--gc-sections`, `-u halo_shell_main`, and HCU's malloc-family wrappers. This
was an exploratory command, not yet a maintained build target or acceptance
test; the next implementation should turn the object list, section accounting,
entrypoint ownership, and symbol-collision audit into a reproducible target.

Relevant source anchors: [`ps2_main.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_main.c#L14), [`ps2_memory.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L251), [`ee-world.mk`](../../tools/ee-world.mk#L1), [`main.c`](../../submodules/halo-ps2/engine/src/main.c#L137), [`memory-budget.json`](../../config/memory-budget.json#L8), [`mem_layout_v2_init`](../../submodules/halo-ps2/engine/src/core/mem.c#L73), [HCU `model_find_marker`](../../submodules/halo-ce-universal/source/models/models.c#L763), and [parent `ps2_model_find_marker`](../../submodules/halo-ps2/engine/src/world/model.c#L282).

## Reproduced joint-link probe (2026-10-20)

The earlier exploratory command is now maintained as [`tools/hcu_parent_link_probe.py`](../../tools/hcu_parent_link_probe.py). It runs the external-only HCU compile/link profile, compiles the parent viewer to a dedicated output directory, and links the parent objects with the HCU rooted closure plus PS2 port/platform objects. It leaves the parent `main` as the entry and uses `-u halo_shell_main` only to retain CE shell code for link/size measurement; it does not call the shell or bind arenas.

Initial reproduced artifact: [`hcu-parent-link.elf`](../../build/hcu-parent-link-probe/hcu-parent-link.elf), SHA-256 `9e775ca32155a5e91127fcdc15454a772f97fde82839d5d3a7b9aed4687183ce`; machine-readable record is refreshed in [`result.json`](../../build/hcu-parent-link-probe/result.json). Thirty-nine parent objects plus the HCU rooted closure linked with zero undefined symbols. Its `bss` was 2,746,800 bytes and LOAD file image was 2,154,500 bytes, 57,348 over the 2,097,152-byte `elf_static` cap. It contained 4,480 bytes of `.vutext`; the entire LOAD segment was counted.

**Section-granular `-Os` profile:** the probe now compiles the parent objects with `-ffunction-sections -fdata-sections`, links with `--gc-sections`, and tests `EE_OPTFLAGS=-Os` only for this diagnostic profile. This saves 18,176 LOAD bytes versus the earlier section-granular `-O2` image, but the current artifact (`89a001a5e92fe81ed8c1c6c04476ee25e65d13474be67133532f3bf0bf422bef`) is still 2,136,324 bytes, 39,172 over cap; `.bss` is 2,714,104 bytes, `.vutext` 4,480 bytes, and undefined symbols remain zero. `acceptance` remains false. No EE timing evidence supports carrying `-Os` into production flags, and the smaller image does not establish runtime entry, arena binding, CE tick, or map loading.
