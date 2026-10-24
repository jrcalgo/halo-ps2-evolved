# M2 C2 r3 lane: selected-session packages (C2.1), 2026-10-23

Lane: selected-packages. Machine record: [m2-c2-r3-selected-packages-2026-10-23.json](m2-c2-r3-selected-packages-2026-10-23.json).
Packages: `build/m2-c2-r3-selected-packages/pkg/<name>/<name>.hcp` (second independent build set in `pkg2/`).
Selections: `build/m2-c2-r3-selected-packages/selections/<name>.selection.json`, generated from each row's
`selection` block in `build/m2-c2-session-map-capacity-2026-10-23/profiles/`. Audit: `tools/c2_selected_package_report.py`.

## Verdict

**C2.1 selected packages: partial.** Producer and byte-identity evidence pass for all 26 session rows. The native
mount preflight does not pass for any selected row, so no row is "fit-qualified" by this lane.

| evidence | result |
|---|---|
| Verified failure fixed: `flee` (snd!) sample outside the package's files | fixed in the producer; the validator is unchanged |
| 26 selected packages built (`hcu_multiplayer_profiles.py --session-selection`) | 26/26 rc 0 |
| Two independent process builds byte-identical | 26/26 (`pkg` vs `pkg2`) |
| Strict producer validation (`hcu_profile_validate.parse_package`, expected SHA and profile id) | 26/26 passed |
| Native mount preflight (`tests/test_hcu_profile_mount.py`) | **0/26 passed** (see failure below) |
| `tests/test_hcu_profile_import.py` (import path changed) | 15 passed |
| In-process `--verify-rebuild` | **fails**: `profile build failed: sidewinder-marine-shotgun4p4bot: independent rebuild differs` (not investigated; the two-process check above is the evidence used) |

## Root cause and producer fix

The selected sidewinder session takes the `c10` marine shotgun variant. Its closure carries 3,814 `snd!` sample extents
from `c10.map` (and 18 from `c40`, 1 from `a50`). The package is mounted against `sidewinder.map` only, so a
sample extent into `c10.map` is a file range outside the mounted map's files. The validator refused it at mount time:

```
tag 'sound\dialog\marines\aussie\conditional\combat2\actions\flee' (snd!): pitch_ranges[0].permutations[0].samples has 16632 bytes at 06e14000, outside the map's files
```

Fix (`tools/hcu_profile_import.py`, `import_profile`): when a scenario root is given, every file-data sample whose source
map is not the scenario's mounted map has its size and file offset zeroed in the output image, and its descriptor is
dropped from `resources`. Each dropped extent is kept under `runtime_normalizations` with
`policy: external_source_sample_metadata_only`, its source key, source datum, original byte count, source offset and
payload SHA-256. The validator is unchanged. The mounted map's own extents are unchanged. This matches the manifest's
existing `resource_policy` (`metadata_only_spu2_unqualified`): raw sample playback was never qualified for these
extents.

## Native mount preflight: failing, exact output

`tests/test_hcu_profile_mount.py` now parametrizes all 26 selected rows plus `ui`. Every selected row exits 15 in
`tests/hcu_profile_mount_main.c` (`read_tags`, line 450), and the failure is silent. Reproduction on one row:

```
$ HCU_PROFILE_MOUNT_ARTIFACTS=build/m2-c2-r3-selected-packages/pm python3 -m pytest -q \
    "tests/test_hcu_profile_mount.py::test_actual_profile_hcp_mounts_through_ps2_cache[sidewinder_marine_shotgun_4p4bot-package23-manifest_path23]"
E       assert 15 == 0
E        +  where 15 = CompletedProcess(args=[... 'hcu-profile-mount-fixture', ... 'sidewinder.map'], returncode=15, stdout='', stderr='').returncode
```

Instrumenting a scratch copy of the fixture (`read_tags`) shows the first failing check is the raw source tag-data read
at line 251 (`cache_file_read(NONE, tag_data_offset, tag_data_size, s_tag_cache, &complete, TRUE)`):

```
raw read rc=-1 complete=2 off=40683008 size=6913928 cap=6913936
read_tags fail at source line 251
```

The reported `tag_data_size` (6,913,928) is not the `sidewinder.map` header value (7,364,724 at 0x14), and raising the
fixture's tag-cache constant alone does not clear the failure. The fixture is outside this lane (`tests/hcu_profile_mount_main.c`),
and the cause is inside its raw-source read path, not in the package bytes; `ui` and every package's producer validation
pass. The producer validator's own check on these packages is complete (see the table above).

## Per-package bytes against the partition rows

Partition rows are from `build/m2-c2-session-map-capacity-2026-10-23/matrix.json` (the r2 budget's 26 session rows).
CE image and BSP payload match their rows exactly for all 26 (`ce_matches_row`, `bsp_matches_row` in the JSON). The
claims column is the row's exact word-rounded capacity floor, which the package does not store. Media is independently
addressable and not resident. Relocation staging is loader staging, not resident map/render.

| package | HCP bytes | CE image | CE resident | BSP payload | media (independent) | claims floor (row) | relocation staging | remaining after floor |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| beavercreek_marine_shotgun_4p4bot | 27942218 | 6838920 | 6838920 | 730200 | 20672616 | 946140 | 130212 | 1840288 |
| beavercreek_mounted_gunner_4p4bot | 21384880 | 4619931 | 4619931 | 730200 | 16544328 | 668767 | 82200 | 4384662 |
| bloodgulch_marine_shotgun_4p4bot | 29553137 | 7014967 | 7014967 | 1303092 | 22099204 | 1039758 | 133160 | 994783 |
| bloodgulch_mounted_gunner_4p4bot | 22995783 | 4795978 | 4795978 | 1303092 | 17970916 | 762384 | 85148 | 3539158 |
| boardingaction_marine_shotgun_4p4bot | 27906677 | 6892084 | 6892084 | 1354156 | 20582988 | 1030780 | 130672 | 1078068 |
| boardingaction_mounted_gunner_4p4bot | 21349323 | 4673095 | 4673095 | 1354156 | 16454700 | 753407 | 82660 | 3622442 |
| carousel_marine_shotgun_4p4bot | 26895513 | 6811643 | 6811643 | 515248 | 19655120 | 915862 | 130100 | 2112907 |
| carousel_mounted_gunner_4p4bot | 20338255 | 4592654 | 4592654 | 515248 | 15526832 | 638488 | 82088 | 4657282 |
| chillout_marine_shotgun_4p4bot | 26555056 | 6786551 | 6786551 | 573416 | 19342696 | 919996 | 129544 | 2076253 |
| chillout_mounted_gunner_4p4bot | 19997702 | 4567562 | 4567562 | 573416 | 15214408 | 642623 | 81532 | 4620627 |
| damnation_marine_shotgun_4p4bot | 28343289 | 6881623 | 6881623 | 1326816 | 21028768 | 1026055 | 131292 | 1119974 |
| damnation_mounted_gunner_4p4bot | 21785935 | 4662634 | 4662634 | 1326816 | 16900480 | 748682 | 83280 | 3664348 |
| hangemhigh_marine_shotgun_4p4bot | 27120721 | 6778930 | 6778930 | 595848 | 19917432 | 921848 | 128884 | 2060250 |
| hangemhigh_mounted_gunner_4p4bot | 20563383 | 4559941 | 4559941 | 595848 | 15789144 | 644474 | 80872 | 4604625 |
| longest_marine_shotgun_4p4bot | 26622976 | 6797019 | 6797019 | 377388 | 19401516 | 896801 | 129252 | 2285300 |
| longest_mounted_gunner_4p4bot | 20065718 | 4578030 | 4578030 | 377388 | 15273228 | 619428 | 81240 | 4829674 |
| prisoner_marine_shotgun_4p4bot | 27280270 | 6774164 | 6774164 | 888336 | 20081504 | 957813 | 128952 | 1736495 |
| prisoner_mounted_gunner_4p4bot | 20722932 | 4555175 | 4555175 | 888336 | 15953216 | 680439 | 80940 | 4280870 |
| putput_marine_shotgun_4p4bot | 27165229 | 6782226 | 6782226 | 1643044 | 19957956 | 1053159 | 128792 | 878539 |
| putput_mounted_gunner_4p4bot | 20607891 | 4563237 | 4563237 | 1643044 | 15829668 | 775786 | 80780 | 3422913 |
| ratrace_marine_shotgun_4p4bot | 26881791 | 6804448 | 6804448 | 550804 | 19650116 | 919407 | 129792 | 2081309 |
| ratrace_mounted_gunner_4p4bot | 20324533 | 4585459 | 4585459 | 550804 | 15521828 | 642033 | 81780 | 4625684 |
| sidewinder_marine_shotgun_4p4bot | 29531846 | 6913928 | 6913928 | 1993740 | 22181836 | 1113459 | 131764 | 332869 |
| sidewinder_mounted_gunner_4p4bot | 22974508 | 4694939 | 4694939 | 1993740 | 18053548 | 836085 | 83752 | 2877244 |
| wizard_marine_shotgun_4p4bot | 26672426 | 6792902 | 6792902 | 556944 | 19452736 | 918731 | 129808 | 2087375 |
| wizard_mounted_gunner_4p4bot | 20115184 | 4573913 | 4573913 | 556944 | 15324448 | 641358 | 81796 | 4631749 |

## Open items (not closed by this lane)

- Native mount preflight is failing for all 26 rows (fixture raw source read, outside this lane).
- In-process `--verify-rebuild` reports `independent rebuild differs`; two-process builds are byte-identical.
- Renderer indexes, live set, simultaneous staging and workload peaks remain unmeasured.
- The import change applies to every profile built with a scenario root. The archived corpora were not regenerated, so their bytes are unchanged; a future rebuild of a session profile with cross-map samples will differ.
- Sound samples from other source maps are metadata only; a self-contained package would need those extents carried or relocated.

## Documents read for this lane

Read in full: `submodules/halo-ce-universal/docs/custom_edition_caches.md`, `docs/mods.md`; `submodules/halo-ps2/docs/`
01 through 14 (all), `reports/map-headers.txt`, `reports/tag-index.md`, `reports/tag-inventory.md`; `submodules/ps2sdk/docs/code.css`.
`docs/reports/m2-c2-status-2026-10-23.json` and the C2 section of `plans/7.hcu-remake-m2-m4.md` were read before the work.
