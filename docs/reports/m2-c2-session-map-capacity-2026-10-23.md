# C2 session map capacity: selected roster profiles

This report post-processes the completed 26-profile setup-residency run: the Marine shotgun combat recipe and mounted gunner recipe, each on all 13 stock multiplayer maps with 4 player slots and 4 Spartan bots. It preserves the measured CTAG identities and separates memory by owner. These are the exact profiles measured; they do not establish the largest recipe on every map.

The machine-readable matrix is [m2-c2-session-map-capacity-2026-10-23.json](m2-c2-session-map-capacity-2026-10-23.json). Its source pins and per-profile CTAG hashes are authoritative. All 26 CTAG hashes, CE image lengths, and BSP payload lengths match the original completed matrix. Reaccounting did not rerun schema imports or change any CTAG image.

## Marine shotgun recipe by map

All values are bytes. “Render residual” is the 10 MiB candidate map/render backing less aligned CE payload, aligned BSP payload, and the 16-byte inner guard. Claims and relocation staging are separate owner floors, shown independently.

| Map | CE image | BSP payload | Render residual | Claims floor* | Relocation staging† |
|---|---:|---:|---:|---:|---:|
| Beaver Creek | 6,838,920 | 730,200 | 2,916,608 | 946,144 | 130,212 |
| Blood Gulch | 7,014,967 | 1,303,092 | 2,167,664 | 1,039,760 | 133,160 |
| Boarding Action | 6,892,084 | 1,354,156 | 2,239,488 | 1,030,784 | 130,672 |
| Carousel | 6,811,643 | 515,248 | 3,158,848 | 915,864 | 130,100 |
| Chill Out | 6,786,551 | 573,416 | 3,125,760 | 920,000 | 129,544 |
| Damnation | 6,881,623 | 1,326,816 | 2,277,296 | 1,026,056 | 131,292 |
| Hang ’Em High | 6,778,930 | 595,848 | 3,110,944 | 921,852 | 128,884 |
| Longest | 6,797,019 | 377,388 | 3,311,328 | 896,804 | 129,252 |
| Prisoner | 6,774,164 | 888,336 | 2,823,232 | 957,816 | 128,952 |
| Putput | 6,782,226 | 1,643,044 | 2,060,448 | 1,053,164 | 128,792 |
| Rat Race | 6,804,448 | 550,804 | 3,130,480 | 919,408 | 129,792 |
| Sidewinder | 6,913,928 | 1,993,740 | 1,578,064 | 1,113,460 | 131,764 |
| Wizard | 6,792,902 | 556,944 | 3,135,888 | 918,732 | 129,808 |

The Sidewinder Marine profile has the smallest measured map/render residual: 1,578,064 bytes, before renderer index/workspace, bounded conversion staging, texture residency, outer alignment slop/canaries, and other actual EE high-water costs. Thus the remaining number is a ceiling for those unmeasured map/render allocations, not an admission result. The mounted gunner profile on Sidewinder leaves 3,797,056 bytes by the same formula; exact mounted values for all maps are in the JSON.

* Claims floor uses the binder formula `ceil((tag_capacity + bsp_capacity) / 32) * 4`, substituting the measured aligned payload extents for unknown capacities. The current binder charges this to `resident_gameplay`, so this floor is not deducted from map/render backing.

† Relocation bytes are measured CTAG staging extent owned by streaming/map-load staging. They are not deducted from map/render backing. Cross-owner sums in the JSON are informational only.

## C2 design implication

This measurement does not establish that a separate permanent BSP rendering geometry copy fits. The next capacity design must measure renderer indices/workspace plus bounded 64 KiB conversion staging against the residual, and investigate whether rendering can consume CE-owned CBSP vertex storage while preserving simulation consumers and pointer lifetimes. No CE fields or BSP data are removed or reclassified by this report; ownership and lifetime parity need proof before such a design can be credited.

The original import run completed under session 49538. A corrective repeat was intentionally interrupted under session 3266 after 9 profiles when the owner separation was identified. The first run’s profile artifacts remain the measurement basis; its CTAG identities were rechecked against all current per-profile manifests during reaccounting.
