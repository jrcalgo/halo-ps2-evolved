# HCU PlayStation 2 compile closure

M0 closure gate: the reachable image is classified, no simulation symbol is unresolved, and every byte in that image is named to one store.

Command: `HALO_BUILD_JOBS=4 python3 tools/hcu_ps2_closure.py --layer all`

| Item | Value |
|---|---|
| Compiler | `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0`, `-Os` |
| HCU commit | `c406a4149ddebae4f45462ce4c1e8d9cce0567c2` |
| Manifest | `submodules/halo-ce-universal/port/ps2/port.json` |
| Units | 343 compiled, 0 failed |
| Roots | `game_initialize`, `game_tick`, `halo_shell_main`, `actors_update`, `hs_update` |
| Report | `build/hcu-ps2-closure/all/result.json` |

The rooted link keeps only sections those roots reach (`ld -r --gc-sections`). `HALO_N64` and `HALO_LINUX` are unset. AI, HaloScript, sound, and cutscenes stay in the manifest. Pool macros are the Xbox sizes, not the N64 ceilings and not budget version 2.

## Live relocations

773 symbols were unresolved before the local-game and game-state definitions. After `ps2_local.c` and `ps2_data.c`, no unresolved symbol is simulation or data.

| Class | Count | Meaning |
|---|---:|---|
| Excluded feature | 317 | Desktop, online, Bink, editor, and debug calls. Not given zero-return bodies |
| Render | 184 | Drawing calls. `halo-ps2` owns GS/VU1. A call that changes simulation state still has to run |
| Toolchain | 137 | C runtime and soft-float `double` helpers. Single precision remains an open port rule |
| PS2 service | 116 | File, time, pad, cache, and memory calls for the platform layer |

`ps2_local.c` follows the desktop code's local-connection path: this machine deals its own damage, deletes its own objects, and uses the first free datum index. `ps2_profile.c` replaces `source/cseries/profile.c`. The Xbox profiler kept a 1,129,812-byte frame history. Timing calls stay in the game and do not change simulation. Halo-ps2 owns the PlayStation 2 profiler.

## Named bytes

Store is EE RAM. Figures are the rooted link.

| Bytes | What | Region | Region size | Result |
|---:|---|---|---:|---|
| 1,642,528 | `.text` 1,280,356, `.data` 90,928, `.rodata` 271,244 | `elf_static` | 2,097,152 | Fits, 454,624 bytes spare |
| 551,763 | `.bss` permanent tables, including the 76,008-byte script stack, 65,536-byte tag scratch, 53,248-byte vehicle homes, and 49,152-byte object-bounds cache | `resident_gameplay` | 6,815,744 | Fits |

`resident_gameplay`, `current_bsp`, `texture_cache`, `dynamic_simulation`, `dma_commands`, `streaming`, `checkpoint`, `audio`, `frame_scratch`, and the 5,767,168-byte reserve have no further live bytes in this link. The Xbox cache units that would size textures and sounds are excluded. GS eDRAM, IOP RAM, and SPU2 RAM have no live bytes yet. The reserve is unspent.

The sum of every compiled object, before discarding unreachable sections, was 3,692,075 bytes of code and constants. That sum is not the linked image.
