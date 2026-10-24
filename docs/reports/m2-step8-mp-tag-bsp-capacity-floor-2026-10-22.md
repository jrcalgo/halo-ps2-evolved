# M2 Step 8 — Multiplayer CTAG + BSP residency floor

## Result

The current fixed cache split cannot admit any of the 13 stock multiplayer maps: the configured tag cache is 2 MiB, while every relocated CTAG image is 4.241–4.477 MiB. More importantly, the shared 6 MiB `current_bsp` arena itself is too small for Sidewinder's irreducible simultaneous data: its 4,378,160-byte CTAG image plus its largest decoded BSP image and in-arena relocation tail require **6,371,864 bytes**, exceeding the 6,291,456-byte arena by **80,408 bytes**. This excludes the separately owned 77,932-byte CTAG relocation scratch, tag-validation claims, alignment, cache metadata, and other live owners. Thus changing only the 2 MiB/4 MiB split cannot make Sidewinder fit; some measured, lossless repartition or representation change is required, and no reserve is assumed.

This is a hard lower-bound/capacity blocker, not target runtime evidence. The package-backed host fixtures previously used 16 MiB tag and 8 MiB BSP buffers; their successful queries do not contradict this result. The 13-map closure report's 4.0–4.26 MiB walked tag union is not the materialized CTAG image and must not be substituted for these exact image lengths.

## Per-map exact package floor

| Map | CTAG image | CTAG relocation scratch* | Largest CBSP image | CBSP rows in BSP-cache tail | Combined `current_bsp` floor | Delta vs 6 MiB arena |
|---|---:|---:|---:|---:|---:|---:|
| Beaver Creek | 4,319,568 | 77,292 | 724,992 | 5,172 | 5,049,732 | -1,241,724 |
| Blood Gulch | 4,477,116 | 79,328 | 1,296,384 | 6,672 | 5,780,172 | -511,284 |
| Boarding Action | 4,358,612 | 76,840 | 1,343,488 | 10,632 | 5,712,732 | -578,724 |
| Carousel | 4,277,864 | 76,268 | 507,904 | 7,308 | 4,793,076 | -1,498,380 |
| Chill Out | 4,252,432 | 75,712 | 567,296 | 6,084 | 4,825,812 | -1,465,644 |
| Damnation | 4,345,868 | 77,460 | 1,320,960 | 5,820 | 5,672,648 | -618,808 |
| Hang 'Em High | 4,246,076 | 75,052 | 589,824 | 5,988 | 4,841,888 | -1,449,568 |
| Longest | 4,263,624 | 75,420 | 374,784 | 2,568 | 4,640,976 | -1,650,480 |
| Prisoner | 4,241,088 | 75,120 | 884,736 | 3,564 | 5,129,388 | -1,162,068 |
| Putput | 4,250,464 | 74,960 | 1,638,400 | 4,608 | 5,893,472 | -397,984 |
| Rat Race | 4,270,452 | 75,960 | 544,768 | 6,000 | 4,821,220 | -1,470,236 |
| Sidewinder | 4,378,160 | 77,932 | 1,984,512 | 9,192 | 6,371,864 | **+80,408** |
| Wizard | 4,259,188 | 75,976 | 552,960 | 3,948 | 4,816,096 | -1,475,360 |

The “combined `current_bsp` floor” is the decoded CTAG image + the largest decoded CBSP image + its relocation table, since `ps2_cache.c` streams those CBSP rows into the unused tail of the fixed BSP cache before CE observes a successful read. The 36-byte CBSP envelope header lives in stack-local stream state and is not charged to the arena. CTAG relocation rows (marked *) are allocated from the map-owner arena in [`ctag_mount.c:396-433`](../../src/stream/ctag_mount.c#L396), not `current_bsp`; they are itemized to prevent double-charging or omission from the separate owner ledger. This estimate includes one authored BSP at a time; every audited map currently has one BSP.

## Source and reproducibility

- Current tag-cache default is 2 MiB: [`hcu_main.c:28-30`](../../src/stream/hcu_main.c#L28).
- Tag cache and the remaining disjoint BSP cache are both carved from `current_bsp`: [`hcu_memory_bind.c:43-56`](../../src/stream/hcu_memory_bind.c#L43), [`hcu-ps2-memory-map.json:90-92`](../../config/hcu-ps2-memory-map.json#L90), and the 6 MiB region in [`memory-budget.json:12`](../../config/memory-budget.json#L12).
- CE's cache adapter rejects CTAG images larger than the configured tag cache: [`ps2_cache.c:180-190`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L180).
- CBSP image and relocation rows must both fit the BSP cache; rows are deliberately placed after the image: [`ps2_cache.c:514-533`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L514), then validated/rebased in place at [`ps2_cache.c:600-628`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L600). CTAG relocation scratch is separately allocated from the map-owner arena at [`ctag_mount.c:396-433`](../../src/stream/ctag_mount.c#L396).
- Reproduction (from repo root, with all 13 generated retail MP packages available):

  ```sh
  python3 tools/audit_mp_tag_bsp_capacity_floor.py \
    build/m2-mp-all-map-packages/*.hp2 \
    build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2 \
    build/m2-mp-extra/prisoner-all-bsps.hp2 \
    build/m2-mp-wind-package/damnation-all-bsps.hp2 \
    --output build/m2-mp-render-assets/tag-bsp-capacity-floor-v2.json
  ```

  The command refuses to overwrite an existing JSON output. Script SHA-256 `a49ea9825c9af93cd352abc03ed91e3c60549f98f8c783f12291b39b15839201`; output JSON SHA-256 `5130b6332f6e395481f70ea1445a3ac161845dcaa5fae228abac0a5bb788d19a`. It records each input package SHA, source pins, decoded CTAG/BSP image and relocation lengths, and the budget hash.

## Step 8 disposition

This closes the static lower-bound calculation and identifies a concrete production blocker. It does not close arena ownership/high-water, target-sized query execution, match-time object/effect/texture residency, custom Energy Sword/Fuel Rod asset sources, co-op/bot capacity, or EE/PCSX2 map admission. Do not change region budgets or mark any map admitted from this audit alone. The next experiment must first measure CTAG compaction/eligible data separation and simultaneous claims/relocation needs, then either prove an alternate fixed-region placement inside the existing 32 MiB ledger or document a source-backed, lossless representation change; Sidewinder remains the minimum adversarial map for that decision.
