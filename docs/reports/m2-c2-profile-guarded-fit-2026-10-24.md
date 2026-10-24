# C2 guarded profile fit ledger (2026-10-24)

This report separates measured guest owner use from package-derived static floors. It covers the 26 selected session HCP2 packages plus the separate UI package. Machine-readable evidence, including each exact package, manifest, partition, ELF, guest log and result hash, is in `m2-c2-profile-guarded-fit-2026-10-24.json`. The per-row boot/load/release matrix is in `m2-c2-profile-matrix-2026-10-24.md`.

## Selected profile fits

**27 of 27 rows pass** the guarded-owner production CE load/release gate in PCSX2 interpreter mode. The 26 selected session rows load their selected scenario and BSP, release the owners, report zero allocation failures, and remain below the budget-v3 reserve. The UI package is measured separately. This gate does not exercise 4-player/4-bot gameplay, renderer readers, or PS2 hardware.

A session row joins guest evidence only when row name, map, profile ID, HCP package SHA and manifest SHA, partition, scenario, linked build identity, staged ELF hash and map-file hashes agree. The CE CTAG SHA is retained separately from the HCP package SHA. Static floors are not substituted for runtime measurements. For every measured owner, fit requires it to be bound, have positive capacity, `0 <= used <= peak <= capacity`, zero failures, and the registered static capacity where applicable. Missing or unbound owners stay unmeasured.

| Profile | Tag peak / cap | BSP peak / cap | Game state peak / cap | Map-load staging peak / cap | Reserve margin | Result |
|---|---:|---:|---:|---:|---:|---|
| `beavercreek_marine_shotgun_4p4bot` | 6,838,920 / 6,838,928 | 724,992 / 730,208 | 3,107,696 / 3,166,208 | 180,548 / 1,048,576 | 396,582 | pass |
| `beavercreek_mounted_gunner_4p4bot` | 4,619,931 / 4,619,936 | 724,992 / 730,208 | 3,107,696 / 3,166,208 | 124,808 / 1,048,576 | 405,030 | pass |
| `bloodgulch_marine_shotgun_4p4bot` | 7,014,967 / 7,014,976 | 1,296,384 / 1,303,104 | 3,107,696 / 3,166,208 | 184,760 / 1,048,576 | 394,918 | pass |
| `bloodgulch_mounted_gunner_4p4bot` | 4,795,978 / 4,795,984 | 1,296,384 / 1,303,104 | 3,107,696 / 3,166,208 | 129,020 / 1,048,576 | 403,366 | pass |
| `boardingaction_marine_shotgun_4p4bot` | 6,892,084 / 6,892,096 | 1,343,488 / 1,354,160 | 3,107,696 / 3,166,208 | 181,872 / 1,048,576 | 395,686 | pass |
| `boardingaction_mounted_gunner_4p4bot` | 4,673,095 / 4,673,104 | 1,343,488 / 1,354,160 | 3,107,696 / 3,166,208 | 126,132 / 1,048,576 | 404,134 | pass |
| `carousel_marine_shotgun_4p4bot` | 6,811,643 / 6,811,648 | 507,904 / 515,248 | 3,107,696 / 3,166,208 | 179,796 / 1,048,576 | 397,222 | pass |
| `carousel_mounted_gunner_4p4bot` | 4,592,654 / 4,592,656 | 507,904 / 515,248 | 3,107,696 / 3,166,208 | 124,552 / 1,048,576 | 405,158 | pass |
| `chillout_marine_shotgun_4p4bot` | 6,786,551 / 6,786,560 | 567,296 / 573,424 | 3,107,696 / 3,166,208 | 178,360 / 1,048,576 | 398,118 | pass |
| `chillout_mounted_gunner_4p4bot` | 4,567,562 / 4,567,568 | 567,296 / 573,424 | 3,107,696 / 3,166,208 | 123,100 / 1,048,576 | 406,054 | pass |
| `damnation_marine_shotgun_4p4bot` | 6,881,623 / 6,881,632 | 1,320,960 / 1,326,816 | 3,107,696 / 3,166,208 | 182,108 / 1,048,576 | 395,942 | pass |
| `damnation_mounted_gunner_4p4bot` | 4,662,634 / 4,662,640 | 1,320,960 / 1,326,816 | 3,107,696 / 3,166,208 | 126,848 / 1,048,576 | 403,878 | pass |
| `hangemhigh_marine_shotgun_4p4bot` | 6,778,930 / 6,778,944 | 589,824 / 595,856 | 3,107,696 / 3,166,208 | 176,980 / 1,048,576 | 398,886 | pass |
| `hangemhigh_mounted_gunner_4p4bot` | 4,559,941 / 4,559,952 | 589,824 / 595,856 | 3,107,696 / 3,166,208 | 121,736 / 1,048,576 | 406,822 | pass |
| `longest_marine_shotgun_4p4bot` | 6,797,019 / 6,797,024 | 374,784 / 377,392 | 3,107,696 / 3,166,208 | 177,604 / 1,048,576 | 398,630 | pass |
| `longest_mounted_gunner_4p4bot` | 4,578,030 / 4,578,032 | 374,784 / 377,392 | 3,107,696 / 3,166,208 | 122,360 / 1,048,576 | 406,566 | pass |
| `prisoner_marine_shotgun_4p4bot` | 6,774,164 / 6,774,176 | 884,736 / 888,336 | 3,107,696 / 3,166,208 | 177,256 / 1,048,576 | 398,758 | pass |
| `prisoner_mounted_gunner_4p4bot` | 4,555,175 / 4,555,184 | 884,736 / 888,336 | 3,107,696 / 3,166,208 | 122,012 / 1,048,576 | 406,694 | pass |
| `putput_marine_shotgun_4p4bot` | 6,782,226 / 6,782,240 | 1,638,400 / 1,643,056 | 3,107,696 / 3,166,208 | 176,904 / 1,048,576 | 398,886 | pass |
| `putput_mounted_gunner_4p4bot` | 4,563,237 / 4,563,248 | 1,638,400 / 1,643,056 | 3,107,696 / 3,166,208 | 121,660 / 1,048,576 | 406,950 | pass |
| `ratrace_marine_shotgun_4p4bot` | 6,804,448 / 6,804,448 | 544,768 / 550,816 | 3,107,696 / 3,166,208 | 179,600 / 1,048,576 | 397,094 | pass |
| `ratrace_mounted_gunner_4p4bot` | 4,585,459 / 4,585,472 | 544,768 / 550,816 | 3,107,696 / 3,166,208 | 124,356 / 1,048,576 | 405,030 | pass |
| `sidewinder_marine_shotgun_4p4bot` | 6,913,928 / 6,913,936 | 1,984,512 / 1,993,744 | 3,107,696 / 3,166,208 | 182,868 / 1,048,576 | 395,558 | pass |
| `sidewinder_mounted_gunner_4p4bot` | 4,694,939 / 4,694,944 | 1,984,512 / 1,993,744 | 3,107,696 / 3,166,208 | 127,608 / 1,048,576 | 403,622 | pass |
| `wizard_marine_shotgun_4p4bot` | 6,792,902 / 6,792,912 | 552,960 / 556,944 | 3,107,696 / 3,166,208 | 178,192 / 1,048,576 | 398,630 | pass |
| `wizard_mounted_gunner_4p4bot` | 4,573,913 / 4,573,920 | 552,960 / 556,944 | 3,107,696 / 3,166,208 | 122,932 / 1,048,576 | 406,566 | pass |
| `ui` | 789,137 / 789,152 | 2,048 / 2,288 | 3,107,696 / 3,166,208 | 14,040 / 1,048,576 | 447,654 | pass |

Across the 26 session rows, cap-minus-peak margins are:
- Tags: 0 to 14 bytes.
- BSP: 2,608 to 10,672 bytes.
- Game state: 58,512 to 58,512 bytes.
- Map-load staging (`streaming_map_owner`): 863,816 to 926,916 bytes.
- Boot end below reserve start: 394,918 to 406,950 bytes.

Tag spans are exact-fit by construction. The smallest tag margin is 0 bytes; this is a measured fit at the registered bound, not additional slack. Every row’s exact counters and provenance are in the JSON.

## UI package

The separate `ui` row passed all 12 checks in 92.0 seconds. Tag peak 789,137 B (margin 15 B); BSP peak 2,048 B (margin 240 B); game-state peak 3,107,696 B (margin 58,512 B); map-load staging peak 14,040 B (margin 1,034,536 B); reserve margin 447,654 B. Package SHA-256: `4ad8b57b7515b074d16d2b89e4f1787a9e37d6f6ab6127ababe9ac1d40a72ed7`. ELF SHA-256: `abb0bc70e20d8dc8d9199b61b59cc5434365dab8b9711ce238649949fc0134f6`. The UI profile is a dedicated lifecycle package, not one of the 26 session packages.

### Native HCP2 lifecycle fixture

The native ILP32 CE lifecycle test passed using HCP2 package `4ad8b57b7515b074d16d2b89e4f1787a9e37d6f6ab6127ababe9ac1d40a72ed7` and manifest `a94a3f2f4aeafefce71aa533e5914960190b35c7625c94f288842b5980866633`, both produced from the current retail UI map and schema ELF `1b7e191b171710f5a5c0ae04d24fc1a8b8a3733b34481aa4f93fb15a580b5acf`. The package validates as 366 tags, 65 media chunks, and one BSP. The fixture verifies exact logical chunk inventory and hashes through the CE pre-unload map service, plus teardown/retry behavior. It does not claim renderer admission.

The earlier manifest `6c132493c374aa9d99ecef9e8b8dff77daaa9111c94917672831e71d6a153dec` was rejected because it pinned the stale schema ELF `56cd9fb82c4729b6870972c8d8be36fab78916ff1fa2026c5e22bf7cfe263037`; it was not repinned. A fresh isolated UI failure diagnostic, bitmap staging catalog, and non-2D audit were generated against the current schema. The audit is `partial`, identifies nine classified non-2D failures, and is not runtime-admitted. The selected package has no non-2D policy rows, so its manifest records `non2d_policy_evidence: null`; the audit is retained separately rather than presented as embedded package evidence. Full commands, input hashes, validator tuple, and the independent rebuild result are in `build/m2-ce-map-lifecycle-host-hcp2/fixture-provenance.json`. The separate concurrent test attempt that failed with `Text file busy` is preserved in `result-concurrent-attempt.json`; it is not counted as a CE failure.

## Supporting runtime diagnostics

These diagnostic runs use different ELFs and/or bootstrap fixture identities. They are recorded as observations and do not populate selected-profile rows. A run can have a clean terminal marker while remaining unqualified for profile fit because it did not register a selected HCP profile.

### 13-map capacity diagnostic

- Terminal result: `complete`; mode `capacity`; ELF SHA-256 `5685012e302479c0e6a9dd172bb67316ca8e94aa8346df36eb205b03da7641aa`; staged hash matches: `true`; linked build hash matches: `true`; PCSX2 elapsed 642.8 seconds.
- 13/13 stock maps completed the query-only capacity sequence. Generic bootstrap diagnostic peaks: tags 4,477,116 B, BSP 1,984,512 B; owner failures were zero. It did not register a selected profile (`partition-selected name=bootstrap qualified=0`, no `profile-runtime`), so it remains supporting capacity evidence. The pre-entry BIOS Address Error is retained in `boot_diagnostics`; it is not classified as a guest error.

### 2-player workload diagnostic

- Terminal result: `complete`; mode `workload2p`; ELF SHA-256 `3cf1bba1f63e8db6cbf5d0d7f474041772bfd2023655b8f10e75d150b5624cc5`; staged hash matches: `true`; linked build hash matches: `true`; PCSX2 elapsed 86.6 seconds.
- Sidewinder, 2 local players, 3 ticks: 2 units, 90 objects / 83 active; game-state high-water 3,107,696 B, object-pool high-water 78,104 B; both failure counters were zero. Bots and network co-op were not exercised. The independent validator pins this run’s manifest, log and ELF (`pins_valid=true`).

### 4-player workload diagnostic

- Terminal result: `complete`; mode `workload4p`; ELF SHA-256 `ca591e092c965f4d8b70df4cdd9bac89180d3b3ec05d39d359a8bdfeb8c9b3ec`; staged hash matches: `true`; linked build hash matches: `true`; PCSX2 elapsed 88.6 seconds.
- Sidewinder, 4 local players, 3 ticks: 4 units, 94 objects / 88 active; game-state high-water 3,107,696 B, object-pool high-water 92,768 B; both failure counters were zero. Bots and network co-op were not exercised. The independent validator pins this run’s manifest, log and ELF (`pins_valid=true`).

### UI lifecycle/failure-retry diagnostic

- Terminal result: `complete`; mode `lifecycle`; ELF SHA-256 `62c78489a0e1ba600fa7a369983f3312796f9cbbeeb12d6cfc3ed333d0d33640`; staged hash matches: `true`; linked build hash matches: `true`; PCSX2 elapsed 145.6 seconds.
- The diagnostic completed two UI reload cycles. It injected a pre-unload failure and verified the old live state remained; then injected a post-unload failure, verified safe empty state, retried successfully, unpublished CE globals before owner release, and completed both cycle markers. This diagnostic was not a selected HCP profile run.

The `historical_source_identity` records in the JSON bind both corrected diagnostics to the retained build-candidate source snapshots and object digests recorded in each diagnostic build report. The listed snapshots and digests do not establish the complete historical source closure. The JSON records whether matching object bytes remain available; mutable shared-directory files count as retained bytes only when they match the recorded digest.

| Run | `hcu_main.c` snapshot | `hcu_map_service.c` snapshot | lifecycle C snapshot | recorded `hcu_main.o` digest | recorded `hcu_map_service.o` digest | recorded lifecycle test object digest |
|---|---|---|---|---|---|---|
| Capacity | `6ffe7df825221760b92f0ec634ab63b80855e21d673f28457e3e7520081d4f6c` | `19397b3b8b2f9910eb26a7a3e3566a4a7c06f2a1adb8617ceb6526bc292c8e50` | `fbb640f112c3c5dbc34887551817fb374a66a271f9bcc778926ec8384f48d71d` | `8c83a6946cd8e311333981b712320d5b905027ee12fe11b2915679e132477d48` | `ec3861ce0846fed1eb62e5fbe865c61d09e0bd66f4c5d8b93465234dd066708e` | unknown |
| UI lifecycle | `6ffe7df825221760b92f0ec634ab63b80855e21d673f28457e3e7520081d4f6c` | `19397b3b8b2f9910eb26a7a3e3566a4a7c06f2a1adb8617ceb6526bc292c8e50` | `fbb640f112c3c5dbc34887551817fb374a66a271f9bcc778926ec8384f48d71d` | `e264bab3c88062f7db8c423daf00f5dc26e47f6b177977578f14a344bd5245be` | `7e3bc348bc7eb3e6dee031394c16b4aa0b75922f0bf5cd7592254b2eadc4052e` | unknown |

## Owners and limits

In the selected-profile headless loader, `render_chunks`, `render_texture`, `gs_window`, `gs_texture`, and `widget_pool` are unbound and remain unmeasured. Zero is not reported as their capacity fit. The `streaming_map_owner` counter is map-load metadata, CE resource staging, and CTAG relocation arena high-water; it is not decoded HCP asset residency. The selected-profile guest emits no decoded asset-cache high-water counter, so decoded residency remains unmeasured. The JSON retains the historical source-field alias `residency_streaming_map_owner` and exposes its corrected meaning as `map_load_staging`. The sidewinder local-player fixtures provide actual game-state/object-pool peaks, but they are separate bootstrap diagnostic builds and cannot be copied across package rows.

No selected row represents spawned bots or a 4-player/4-bot match; the 4P diagnostic only spawns four local player units. The fit matrix does not prove renderer-reader drain, integrated DMA activity, target EE timing, network co-op, or visual output. C2.7/C2.8 carry-over proofs C3.10/C3.11 remain open. Step 7 and Step 8 remain open.

## Failed and partial attempts

The first capacity capture stopped at the 600-second host timeout after 11 of 13 maps; it is retained under `build/m2-c2-resume-fit/guest/capacity/` and is not counted. The succeeding isolated run is under `build/m2-c2-resume-fit/guest/capacity-rerun/`, has a 642.8-second runtime and all 13 query markers. Historical pre-patch capacity output that reported a post-free allocation delta is partial evidence only; the corrected oracle samples live memory before free and verifies both the live and after-free deltas.

All PCSX2 diagnostics preserve the pre-entry `Address Error, addr=0x1ff` line as a BIOS boot diagnostic. The table requires a machine-entry marker and classifies error markers as guest failures only after machine entry.
