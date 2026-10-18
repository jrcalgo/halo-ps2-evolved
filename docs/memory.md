# Memory record

M11's acceptance line "total committed memory remains within its budget" is open. This file is the measured record behind that line. The versioned split is `config/memory-budget.json`. A byte counted in two regions is a failed account, and the 5.5 MiB reserve is not available to hide an overflow.

## Budget

The contract is 26.5 MiB committed plus 5.5 MiB reserve, 32 MiB total (33,554,432 bytes). Host checks reject a total other than that and reject overlapping claims. Those checks do not run on the EE.

| Region | Bytes | Role |
|---|---:|---|
| system_kernel | 1,572,864 | kernel, stacks, IOP/EE buffers |
| elf_static | 2,097,152 | executable sections, constants, static tables |
| resident_gameplay | 6,815,744 | permanent data |
| current_bsp | 6,291,456 | map data |
| texture_cache | 4,194,304 | EE RAM for textures and lightmaps |
| dynamic_simulation | 2,621,440 | dynamic pool |
| dma_commands | 1,179,648 | DMA buffers |
| streaming | 1,572,864 | streaming pool |
| checkpoint | 524,288 | checkpoint storage |
| audio | 524,288 | audio staging |
| frame_scratch | 393,216 | frame scratch |
| uncommitted_reserve | 5,767,168 | reserve |

Stacks stay inside `system_kernel` until a measured split is versioned. GS VRAM is a separate 4 MiB store and is not one of these EE regions.

## Stream viewer image

`build/world-stream-elf/world.elf` has 2,202,312 bytes of allocated ELF sections (`SHF_ALLOC`). That is 105,160 bytes above the 2,097,152-byte `elf_static` region. The previous build of this ELF, before the cache-miss callback, was 2,199,488; the 2,824-byte increase is code. An earlier snapshot, before the lightmap decode buffer, was 2,127,664. `.bss` remains dominated by the staging pool below. All three figures are allocated sections of one diagnostic ELF, not a full EE map.

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

Cause: the diagnostic keeps a 1 MiB staging pool and a 64 KiB decode buffer in `.bss` so their addresses stay valid for DMA. Effect: this ELF does not fit the 2 MiB `elf_static` region. Moving the 1,133,688 bytes onto the streaming region on paper, while they still occupy `.bss`, would count them twice. The reserve stays unspent. A budget edit has to follow a measurement that shows where those bytes actually sit.

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

Budget version 2 gives the measured DMA chains their own bytes. The stream ELF's 1,133,688 bytes of staging, decode buffer, worker stack, reader, and one-shot chain are charged to `streaming` (1,572,864). The other 1,068,624 allocated bytes fit in `elf_static`. Steady arena sections fit as well: BSP raw 611,856 in `current_bsp`, TEXS 406,016 plus lightmaps 33,120 in `texture_cache`, and models, scenario, animation, and object textures 3,734,272 in `resident_gameplay`. The OTEX load scratch is 1,089,940 bytes and fits in the spare of `current_bsp` while it is live; arena high water was 6,465,536. Those assignments are not double-counted.

Kernel and IOP occupancy are still unmeasured. `system_kernel` remains a 1,572,864-byte reservation, not a reading. No physical PS2 has reported a high water. The M11 memory acceptance stays open until that reservation is either measured or replaced.
