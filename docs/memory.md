# Memory record

M11's memory acceptance is met by the measurements below. The versioned split is `config/memory-budget.json` version 3. A byte counted in two regions is a failed account. Version 3 spent 262,144 bytes of the reserve on `elf_static` (user-approved 2026-10-24); the reserve is now 5,505,024 bytes.

## Budget

The contract is 28,049,408 bytes committed plus a 5,505,024-byte reserve, 32 MiB total (33,554,432 bytes). Version 2 was 27,787,264 committed plus 5,767,168 reserve. Host checks reject a total other than that and reject overlapping claims. Those checks do not run on the EE.

| Region | Bytes | Role |
|---|---:|---|
| system_kernel | 1,572,864 | kernel, stacks, IOP/EE buffers |
| elf_static | 2,359,296 | executable sections, constants, static tables |
| resident_gameplay | 6,815,744 | permanent data |
| current_bsp | 6,291,456 | map data |
| texture_cache | 4,194,304 | EE RAM for textures and lightmaps |
| dynamic_simulation | 2,621,440 | dynamic pool |
| dma_commands | 1,179,648 | DMA buffers |
| streaming | 1,572,864 | streaming pool |
| checkpoint | 524,288 | checkpoint storage |
| audio | 524,288 | audio staging |
| frame_scratch | 393,216 | frame scratch |
| uncommitted_reserve | 5,505,024 | reserve |

`elf_static` holds only the file-backed ELF bytes (PROGBITS, allocated). ELF NOBITS (`_end - _fbss`) is charged to `resident_gameplay` at boot, not to `elf_static`. Physically the file-backed sections must end by 0x00340000 (1 MiB low kernel plus `elf_static`), the boot backing must end by the reserve start 0x01a40000, and the reserve is [0x01a40000, 0x01f80000). The top 512 KiB [0x01f80000, 0x02000000) holds the kernel stack. The version 3 note: 262,144 B moved from the uncommitted reserve to `elf_static` after the production gameplay ELF's file-backed bytes measured 2,193,924 B against 2,097,152 B. See `docs/reports/m2-c2-budget-v3-2026-10-24.md`.

Stacks stay inside `system_kernel` until a measured split is versioned. GS VRAM is a separate 4 MiB store and is not one of these EE regions.

## Stream viewer image

Historical v2 measurement: `build/world-stream-elf/world.elf` had 2,202,312 bytes of allocated ELF sections (`SHF_ALLOC`), 105,160 bytes above the former 2,097,152-byte region. The prior v2 builds measured 2,199,488 and 2,127,664 allocated bytes. These section totals include NOBITS and are not the v3 `elf_static` metric; v3 uses file-backed PT_LOAD bytes and charges NOBITS to `resident_gameplay`. `.bss` remains dominated by the staging pool below. These are diagnostic ELFs, not the selected production-profile image.

Named diagnostic objects inside that `.bss`:

| Object | Bytes |
|---|---:|
| `storage` | 1,048,576 |
| `decoded.1` | 65,536 |
| `stack` (worker) | 16,384 |
| `header.2` | 2,112 |
| `reader` | 824 |
| `chainmem.0` | 256 |

Those six objects are 1,133,688 bytes. They are the staging pool, the lightmap decode buffer, the worker stack, the pack header, the reader, and the one-shot GIF chain. An earlier snapshot of this ELF, before the lightmap decode buffer, was 2,127,664 allocated bytes. Both figures are the same kind of measurement: allocated sections of one diagnostic ELF, not a full EE map.

Historical v2 interpretation: the diagnostic keeps a 1 MiB staging pool and a 64 KiB decode buffer in `.bss` so their addresses stay valid for DMA. Under v2's section-total comparison, it exceeded 2 MiB. Those bytes must not also be charged to `streaming` while they remain in NOBITS. The separate v3 decision transfers 262,144 bytes to `elf_static` based on the selected image's file-backed PT_LOAD measurement; see the C2 v3 report.

## World arena

The stream viewer asks for a 12 MiB arena (`arena_mb 12`, 12,582,912 bytes) with one boot-time `malloc`. After Blood Gulch loads, used bytes are 5,279,024. Each of the three unload/reload cycles returns to that same number. The logged high water is 6,314 KiB (6,465,536 bytes).

Cause: BSP, textures, lightmaps, object sections, and renderer tables share one arena. Effect: the high water is 174,080 bytes above the 6,291,456-byte `current_bsp` region, and the steady 5,279,024 bytes are not yet split across `current_bsp`, `texture_cache`, and `resident_gameplay`. The 12 MiB capacity is larger than any one of those regions. Reload proves the arena can return to its baseline. It does not prove the 32 MiB split.

Converted pack sizes, which are files rather than the arena, were checked against those regions at M09 and at the later static-sky object pack:

| Pack | Bytes | Region it was compared with | Region bytes |
|---|---:|---|---:|
| BSP | 405,504 | current_bsp | 6,291,456 |
| Objects, first conversion | 2,344,960 | resident_gameplay | 6,815,744 |
| Objects, static-sky variant | 2,441,216 | resident_gameplay | 6,815,744 |
| Textures | 350,208 | texture_cache | 4,194,304 |

Decompressed TEXS is 406,016 bytes and lightmap `LM0` is 33,120 bytes. Those live in the arena after load, not as the compressed pack files (TEXS stored 332,670, `LM0` stored 13,315).

## DMA command buffers

The renderer allocates two frame chains and two upload buffers with `memalign`, uncached:

| Buffer | Quadwords | Bytes, each | Bytes, both |
|---|---:|---:|---:|
| Frame chain (`CHAIN_QW`) | 32,768 | 524,288 | 1,048,576 |
| Upload chain (`UPLOAD_QW`) | 4,096 | 65,536 | 131,072 |

The sum is 1,179,648 bytes. Budget version 2 sets `dma_commands` to that size and reduces `frame_scratch` by the same 131,072 bytes, so the 26.5 MiB committed total and the 5.5 MiB reserve stay put. No frame-scratch high water has been measured. M06 and M08 logged chain high-water of 20 quadwords against a 64-quadword diagnostic chain; that is a different, smaller ELF, not this world viewer.

## GS VRAM

VRAM is 4,194,304 bytes (1,048,576 words of 4 bytes). The video path allocates two 512×448 `GS_PSM_16S` framebuffers and a 24-bit depth buffer, page aligned, then takes the next page as `tex_base`. A qualified stream log records `tex_base` at word 458,752 and 288 pages (2,359,296 bytes) of texture window. Cache pages after the font page are 271 (2,220,032 bytes). 458,752 words times 4, plus the 288-page window, is the entire 4 MiB.

Cause: nothing in VRAM sits past the texture window. Effect: a diagnostic GIF upload has nowhere to go except a framebuffer or the texture cache. The lightmap-page lease uploaded 8,192 bytes at block 7,168, which is the start of that window. The cache still believed those pages were resident, so the canyon drew from the overwritten VRAM. Qualified runs call `bsp_render_invalidate_textures` before the same frame builds, and the frame uploads the real pages again. The recompiler capture after that flush shows Blood Gulch. The unfixed capture does not.

## Per-frame upload cap and GS cache pressure

`tc_init` sets the frame upload budget to 1,536 × 1,024 = 1,572,864 bytes (1.5 MiB). A request larger than the whole budget counts as a failure. A request that does not fit in the bytes still left this frame counts as a deferral. A request that finds no evictable page counts as a failure. An entry used on this frame or the previous frame is pinned and is not a victim.

The 12-view sweep, physical cache 271 pages:

| Cap (pages) | Cap bytes | Evictions | Failures | Deferred |
|---:|---:|---:|---:|---:|
| 96 | 786,432 | 9 | 1,426 | 0 |
| 160 | 1,310,720 | 7 | 7 | 0 |
| 164 | 1,343,488 | 3 | 3 | 0 |
| 166 | 1,359,872 | 2 | 2 | 0 |
| 168 | 1,376,256 | 1 | 1 | 0 |
| 172 and above, through 220 | 1,409,024 and up | 0 | 0 | 0 |

The 96-page and 168-page rows were repeated in both CPU modes. At 96 pages, frame 300 matched the uncapped image and that frame's profiler sample had no failure. The other 1,425 failures were earlier in the sweep. At 168 pages, frames 120, 240, and 300 matched the uncapped image, and the sweep still had one failure.

Cause: at the first frame of a new view the previous view is still pinned, so the new pages and the pinned pages have to fit together. Below 172 pages they do not, and the new request fails instead of evicting a pinned entry. At 172 pages the union fits, so the sweep never evicts. Effect: this route has no probed cap that both churns the cache and admits every request. Deferred uploads stayed at zero, so the 1.5 MiB frame budget was not the limiter. Route-wide texture completeness stays open. Emulator wall time is not a memory or performance result.

## Staging ownership

The EE pool is the 1,048,576-byte `storage` block, four slots, stride 262,144. The worker stack is 16,384. The reader object is 824. The diagnostic log reports those three as 1,065,784 bytes, and that sum is inside `.bss`. Occupying all four slots reaches a 1,048,576-byte high water. A fifth request is rejected. A cancelled read keeps its slot until the worker finishes. A held buffer keeps its slot until the consumer releases it. A DMA lease keeps its slot until `staging_dma_complete`; release and map drain fail before that. Ticket serials stop at `UINT64_MAX` instead of wrapping.

The host regression uses four 256-byte slots and reaches a 1,024-byte high water. That is the same state machine, not an EE allocation.

Cause of the lightmap lease: compressed `LM0` is 13,315 bytes, which fits in one stride, and the decoded section is 33,120 bytes, which fits in the 65,536-byte decode buffer and in a second slot. Page 0 is 8,192 bytes. Effect: those bytes stay allocated from the read until GIF DMA of that page completes.

The following frame forces every BSP texture miss through that same pool. All 16 mip0 images, 299,040 bytes, are packed into two slots. Each slot is leased for its full 262,144-byte stride, so the hold is 524,288 bytes inside the existing 1,048,576-byte pool. The arena copies are overwritten with `0x5A` until the next frame's GIF wait, then copied back. No second pool is allocated.

Cause: `bsp_render_set_world` copies the texture callback, so a later change to `world->source.texture` does not affect uploads. The diagnostic replaces the copied callback for one frame and drops the texture claims, so the rebuild's misses DMA the staging copies. Effect: release fails until that frame's GIF DMA has been waited out. Recompiler `world-stream-recompiler-889aa026a06a4286b4198d19a172816f` and interpreter `world-stream-interpreter-cfbbe1668b754f54bee51f793630c6d6` both log `cache_miss_source=staging textures=16 bytes=299040 slots=2` and `cache_miss_dma=ok textures=16`. The recompiler's final frame still shows Blood Gulch, with the profiler failure count at 0. The callback is restored after that one frame, so later uploads read the arena again.

## Other ELFs

The accepted platform ELF, over 600 guest seconds in both CPU modes, reported heap 1,261,568 bytes and DMA high-water 20 of 64, with intact guards. The accepted hybrid ELF reported heap 1,269,760 bytes and chain high-water 20. Those heaps are not the world arena and are not added to the stream viewer's totals.

Host visibility storage for the 448-camera audit peaked at 4,034 bytes. That number is not EE memory.

## Not yet measured

Historical v2 arena attribution gave the stream ELF's 1,133,688 bytes of staging, decode buffer, worker stack, reader, and one-shot chain to `streaming` (1,572,864), with the other 1,068,624 allocated bytes in `elf_static`. The measured arena sections were BSP raw 611,856 in `current_bsp`, TEXS 406,016 plus lightmaps 33,120 in `texture_cache`, and models, scenario, animation, and object textures 3,734,272 in `resident_gameplay`. OTEX load scratch was 1,089,940 bytes during its load; arena high water was 6,465,536. These are the viewer's v2 measurements and are not the C2 selected-image v3 accounting.

## Kernel, stack, and IOP-side EE buffers

The homebrew link starts `.text` at `0x00100000`. A running probe on the project BIOS reports the same layout before `SifInitRpc`, after it, after `rom0:SIO2MAN`, and after `rom0:PADMAN`:

| Reading | Value |
|---|---|
| `_end` of the probe | `0x0012b7a0` |
| `EndOfHeap()` | `0x01fdf000` |
| Stack pointer | `0x01ffed10` |
| `_stack_size` | 131,072 |
| 32 MiB top | `0x02000000` |

The first 1,048,576 bytes are outside the linked image. The kernel owns them. From `EndOfHeap()` to the top of RAM is 135,168 bytes: the 131,072-byte stack plus 4,096 bytes of gap. Loading SIO2MAN and PADMAN did not move `_end` or `EndOfHeap()`, so those IOP modules did not take an EE user-heap buffer. Their EE-side RPC state stays inside the kernel region or the small probe image.

Those two reserved ends total 1,183,744 bytes. `system_kernel` is 1,572,864, leaving 389,120 bytes unused. The stream viewer's `_end` is `0x00319fe0`. Its heap therefore runs from there to `0x01fdf000`, 30,167,072 bytes, which holds the 12,582,912-byte arena and the 1,179,648-byte DMA chains.

No physical PS2 has repeated this map. That does not change the emulator measurement.
