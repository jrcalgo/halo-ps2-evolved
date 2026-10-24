# HCU local co-op gameplay closure audit

**Status:** source-closure finding; no PS2 implementation or runtime acceptance is claimed.

## Product constraint

The parent product scope explicitly includes a two-player local cooperative campaign ([scope item 7](../plans/0.native-ps2-halo-hybrid-port.md#L75)). Its M22 acceptance requires both players to complete the campaign, shared progression to remain consistent, and checkpoint restoration to work for both players ([M22](../plans/0.native-ps2-halo-hybrid-port.md#L1204)). Therefore, a symbol's location under HCU `port/linux/game/` does not by itself make it safe to omit: the source contains both network transport and campaign simulation extensions.

## Source evidence and ownership

- `source/units/units.c` includes `network_coop.h`, `coop_scripts.h`, and `coop_enemies.h` ([include site](../submodules/halo-ce-universal/source/units/units.c#L695)). The unit update and vehicle paths call follower suspend/board/exit operations and extra-enemy rider bookkeeping ([vehicle path](../submodules/halo-ce-universal/source/units/units.c#L4848), [rider path](../submodules/halo-ce-universal/source/units/units.c#L5404)).
- `source/ai/encounters.c` includes the extra-enemy module ([include site](../submodules/halo-ce-universal/source/ai/encounters.c#L314)) and consults it while placing squad members ([placement](../submodules/halo-ce-universal/source/ai/encounters.c#L2276), [extra spawn placement](../submodules/halo-ce-universal/source/ai/encounters.c#L3189)). These affect actor count and placement, not just presentation.
- `source/hs/hs_library_external.c` invokes co-op-aware object-list trigger handling and follower teleport/gather logic ([object-list/teleport path](../submodules/halo-ce-universal/source/hs/hs_library_external.c#L895), [arrival path](../submodules/halo-ce-universal/source/hs/hs_library_external.c#L1075)). `source/hs/hs.c` also routes script safe-to-save and equipment operations through `coop_scripts_*` ([script calls](../submodules/halo-ce-universal/source/hs/hs.c#L14164), [equipment call](../submodules/halo-ce-universal/source/hs/hs.c#L14983)).
- The helper contracts are documented in HCU headers: `coop_scripts.h` defines any-player trigger evaluation, gather-in-volume, follower teleport, vehicle boarding/exit, save safety, and shared equipment ([header](../submodules/halo-ce-universal/port/linux/game/coop_scripts.h#L13)); `coop_enemies.h` defines additional encounter enemy counts and placement, plus dropship rider lifecycle ([header](../submodules/halo-ce-universal/port/linux/game/coop_enemies.h#L13)); `network_coop.h` describes player collision, remote-device authority, shared vitality, structure-BSP readiness, and cinematic skip-vote behavior ([header](../submodules/halo-ce-universal/port/linux/game/network_coop.h#L47)).

These functions must be adapted to the local connection without importing Linux/desktop network transport or replacing stock campaign behavior with arbitrary zero/no-op bodies. The PS2 adapter now implements the local branch. Candidate transport-only replication hooks are the `network_coop_note_*` functions, but only after checking each call site and verifying the single local simulation already performs the corresponding mutation once.

## PS2 local-connection adaptation and closure verification

`tools/hcu_ps2_closure.py` classifies `coop_scripts_*`, `coop_enemies_*`, and local gameplay-facing `network_coop_*` state helpers as `simulation`. The new HCU PS2 adapter [`ps2_coop.c`](../submodules/halo-ce-universal/port/ps2/game/ps2_coop.c) defines all 25 symbols reachable in the current rooted closure. Its local branches preserve CE behavior: ordinary all-player trigger evaluation remains authoritative; `coop_scripts_safe_to_save` maps to `game_safe_to_save`; the script equipment helper still grants equipment to its requested unit; local players collide; devices are locally authoritative; the shared local BSP is immediately ready; and source callers retain their non-network cinematic skip and single-unit vitality behavior. Network-only follower gathering, extra-enemy multipliers/rider deferral, vote replication, and remote BSP synchronization do not run. The manifest includes the adapter as a PS2 source.

`network_coop_note_*` remains a separate excluded-prefix candidate for replication-only calls, subject to a call-site audit before M1. Co-op spectate/camera/draw helpers are classified as `render`; their camera target selection must still be verified against split-screen presentation. The adapter compiles in the R5900 closure; the rooted link reports no unresolved simulation/data/unclassified symbols and `hcu_ps2_link.py` now produces a zero-undefined ELF. These prove compilation and symbol closure only, not in-game local co-op parity.

## Required M5/M22 acceptance

Build reference fixtures from source and test two local command streams against the same authoritative simulation for: a player entering a script trigger while the other is outside; gathering and follower teleport; split-screen vehicle seat allocation and exit; extra encounter enemy count/placement and dropship riders; player-player collision setting; shared body/shield changes; BSP readiness; death/rejoin; cinematic skip and checkpoint progression. Validate actor and script memory high-water under the same scenes. The M5 checklist now names these behaviors; M22 remains the eventual full-campaign acceptance gate.

## Current limits

The adapter does not provide online/network co-op, and it does not by itself prove the full two-player campaign works. The 569 remaining generated platform definitions still require a call-site/side-effect audit; the corrected link explicitly rejects any future unresolved simulation/data/unclassified symbol. M1 and M5 remain open pending boot, platform implementation, arena accounting, and source/reference runtime tests.
